"""Free singing without a singing engine: a spoken line (any TTS) is re-pitched and re-timed onto a melody, using only NumPy.

python3 -m kids_audio.sing job.json
job = {"voice": "line.mp3", "words": [{"text","t0","t1"}...] (seconds in the voice file),
       "tune": [[[midi, beats], ...], ...] (one list of notes per word; a word with two notes has two syllables),
       "bpm": 110, "out": "sung.wav", "transpose": optional semitones}
Prints {"file", "dur", "words": [{"text","t0","t1"}] (seconds from the song start), "beat": s, "transpose": semitones}.

Method: pitch-synchronous overlap-add. Each pitch period of the voice is cut out with a window and re-placed at the spacing of
the target note, which changes the pitch while keeping the voice's own tone. Vowels stretch to fill the note, consonants keep their
speed so words stay clear. The melody moves to the octave and key nearest the voice, so nothing is pushed out of range.
"""
import json
import sys

import numpy as np

from .library import read_audio, write_wav
from .synth import SR

_LOW, _HIGH = 75.0, 500.0
_HOP = 0.005


def midi_hz(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def f0_track(x):
    """(f0 in Hz per hop, 0 where unvoiced). Normalised autocorrelation on a 16 kHz copy."""
    step = SR // 16000
    y = np.convolve(x, np.ones(step) / step, "same")[::step]
    n, hop = 640, int(_HOP * 16000)
    lo, hi = int(16000 / _HIGH), int(16000 / _LOW)
    frames = max(1, (len(y) - n) // hop + 1)
    out = np.zeros(frames)
    level = np.sqrt(np.mean(y ** 2) + 1e-12)
    win = np.hanning(n)
    for i in range(frames):
        fr = y[i * hop:i * hop + n]
        if len(fr) < n or np.sqrt(np.mean(fr ** 2)) < 0.25 * level:
            continue
        fr = (fr - fr.mean()) * win
        spec = np.fft.rfft(fr, 2 * n)
        ac = np.fft.irfft(np.abs(spec) ** 2)[:hi + 2]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        # taper removes the bias toward long lags that the window introduces
        k = lo + int(np.argmax(ac[lo:hi]))
        best = ac[k]
        for div in (2, 3):                                     # prefer the true period over a multiple of it
            j = int(round(k / div))
            if j >= lo and ac[max(lo, j - 2):j + 3].max() > 0.85 * best:
                k = max(lo, j - 2) + int(np.argmax(ac[max(lo, j - 2):j + 3])); best = ac[k]
                break
        if best > 0.45 and 0 < k < len(ac) - 1:
            a, b, c = ac[k - 1], ac[k], ac[k + 1]
            d = a - 2 * b + c
            out[i] = 16000.0 / (k + (0.5 * (a - c) / d if d else 0.0))
    # remove lone voiced blips and fill one-frame holes
    v = out > 0
    for i in range(1, frames - 1):
        if v[i] and not v[i - 1] and not v[i + 1]:
            out[i] = 0
        elif not v[i] and v[i - 1] and v[i + 1]:
            out[i] = 0.5 * (out[i - 1] + out[i + 1])
    return out


def _pitch_marks(x, f0):
    """Sample positions of one peak per pitch period through the voiced runs."""
    marks = []
    i, n = 0, len(f0)
    hop = _HOP * SR
    while i < n:
        if f0[i] <= 0:
            i += 1
            continue
        j = i
        while j < n and f0[j] > 0:
            j += 1
        p = i * hop
        end = j * hop
        while p < end:
            per = SR / f0[min(n - 1, int(p / hop))]
            a, b = int(p), int(min(len(x) - 1, p + per))
            m = a + int(np.argmax(np.abs(x[a:b + 1]))) if b > a else a
            if not marks or m > marks[-1]:
                marks.append(m)
            p = max(m, p) + per * 0.8 if m > p else p + per
        i = j
    return np.array(marks, dtype=np.int64)


def _source_time(tau, dur, s0, s1, voiced_at):
    """Output time -> source time: voiced parts stretch to fill the note, unvoiced parts keep their speed when they fit."""
    samples = np.linspace(s0, s1, 200)
    v = voiced_at(samples)
    ds = (s1 - s0) / 199.0
    un = (~v).sum() * ds
    vo = v.sum() * ds
    rate_v = max(vo / max(1e-6, dur - un), 1e-3) if dur > un + 0.25 * vo else (s1 - s0) / dur
    rate_u = 1.0 if dur > un + 0.25 * vo else (s1 - s0) / dur
    cum = np.concatenate([[0.0], np.cumsum(np.where(v, ds / rate_v, ds / rate_u))[:-1]])
    return np.interp(tau, cum * (dur / max(cum[-1], 1e-6)), samples)


def _render_note(x, marks, f0, s0, s1, dur, f_to, f_from, out, norm, at):
    """One note: the grains of source [s0, s1] placed at the note's pitch spacing, into out starting at sample `at`."""
    hop = _HOP * SR
    voiced_at = lambda t: f0[np.clip((np.asarray(t) * SR / hop).astype(int), 0, len(f0) - 1)] > 0
    tau = 0.0
    while tau < dur:
        s = float(_source_time(np.array([tau]), dur, s0, s1, voiced_at)[0])
        idx = int(s * SR / hop)
        here = f0[min(len(f0) - 1, max(0, idx))]
        wob = 1.0 + 0.012 * np.sin(2 * np.pi * 5.5 * tau) * min(1.0, max(0.0, (tau - 0.25) / 0.15))   # a little vibrato on long notes
        glide = min(1.0, tau / 0.03)
        target = np.exp(np.log(f_from) + (np.log(f_to) - np.log(f_from)) * glide) * wob
        if here > 0 and len(marks):
            k = int(np.searchsorted(marks, s * SR))
            k = min(len(marks) - 1, max(0, k if k < len(marks) and (k == 0 or abs(marks[k] - s * SR) < abs(marks[k - 1] - s * SR)) else k - 1))
            per = int(SR / here)
            step = 1.0 / target
            a, b = marks[k] - per, marks[k] + per
        else:
            per = int(0.006 * SR)
            step = 0.004
            c = int(s * SR)
            a, b = c - per, c + per
        if a >= 0 and b < len(x):
            g = x[a:b] * np.hanning(b - a)
            o = at + int(tau * SR) - per
            if o >= 0 and o + len(g) < len(out):
                out[o:o + len(g)] += g
                norm[o:o + len(g)] += np.hanning(b - a)
        tau += step


def sing(job):
    voice = read_audio(job["voice"]).mean(0)
    words, tune, bpm = job["words"], job["tune"], float(job.get("bpm", 110))
    if len(words) != len(tune):
        raise ValueError(f"{len(words)} sung words but {len(tune)} tune entries")
    beat = 60.0 / bpm
    f0 = f0_track(voice)
    voiced = f0[f0 > 0]
    all_notes = [n for w in tune for n in w if n[0] is not None]
    # the melody moves to the key and octave nearest the voice
    home = 12 * np.log2(np.median(voiced) / 440.0) + 69 if len(voiced) else 60
    # a song passes one "transpose" for all its lines, so the key stays the same from line to line
    transpose = int(job["transpose"]) if job.get("transpose") is not None else int(round(home - np.median([n[0] for n in all_notes])))
    marks = _pitch_marks(voice, f0)
    total = sum(n[1] for w in tune for n in w) * beat
    out, norm = np.zeros(int((total + 0.5) * SR)), np.zeros(int((total + 0.5) * SR))
    t, prev, timed = 0.0, None, []
    for w, notes in zip(words, tune):
        sung = sum(b for _, b in notes) * beat
        tot = w["t1"] - w["t0"]
        start, pos = t, 0.0
        length = sum(b for m, b in notes if m is not None) or 1.0
        for m, b in notes:
            d = b * beat
            if m is not None:
                share = b / length
                s0 = w["t0"] + pos * tot
                s1 = s0 + share * tot
                f = midi_hz(m + transpose)
                # leave a small breath after the sung part so notes stay separate
                _render_note(voice, marks, f0, s0, s1, max(0.06, d * 0.92), f, prev or f, out, norm, int(t * SR))
                prev = f
                pos += share
            t += d
        timed.append({"text": w["text"], "t0": round(start, 3), "t1": round(start + sung * 0.92, 3)})
    y = out / np.maximum(norm, 0.08)
    # level like the source voice; a soft fade removes clicks at the note ends
    src = np.sqrt(np.mean(voice[voice != 0] ** 2) + 1e-12)
    got = np.sqrt(np.mean(y[y != 0] ** 2) + 1e-12)
    y = np.clip(y * (src / got), -1, 1)[: int(total * SR)]
    write_wav(job["out"], np.vstack([y, y]))
    return {"file": job["out"], "dur": round(total, 3), "words": timed, "beat": beat, "transpose": transpose}


if __name__ == "__main__":
    print(json.dumps(sing(json.load(open(sys.argv[1], encoding="utf-8")))))
