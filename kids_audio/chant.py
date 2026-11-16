"""Rhythmic chants: a spoken line (any TTS) re-timed so every word lands on the music's beat grid.

python3 -m kids_audio.chant job.json
job = {"voice": "line.mp3", "words": [{"text","t0","t1"}...] (seconds in the voice file), "bpm": 104, "out": "chant.wav"}
Prints {"file", "dur", "words": [{"text","t0","t1"}] (seconds from the chant start = beat 1), "beats": n, "beat": s}.

Rules: one word per beat; short words ("with", "me", "the"...) share a beat as eighth notes; each sentence ends by
filling its bar; a word that is too long for its slot is sped up (pitch kept, at most 1.7x). Each word's onset, not
its silent lead-in, sits on the beat.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

from .library import read_audio, write_wav
from .synth import SR

SHORT = {"a", "an", "the", "with", "me", "and", "to", "in", "on", "my", "your", "we", "you", "it", "is", "of", "at", "for", "be", "so", "do", "go", "oh"}


def _norm(w):
    return "".join(c for c in w.lower() if c.isalnum() or c == "'")


def _atempo(x, factor):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav"); write_wav(a, x)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a, "-af", f"atempo={factor:.4f}", b], check=True, timeout=600)
        return read_audio(b)


def slots(words, text_words=None):
    """Beat slots (start, length in beats) for each word, and the total number of beats (whole bars)."""
    out, pos = [], 0.0
    ends = [bool(text_words and k < len(text_words) and text_words[k].rstrip()[-1:] in ".!?") for k in range(len(words))]
    for k, w in enumerate(words):
        n = _norm(w["text"]); half = n in SHORT and len(n) <= 4
        if half and k + 1 < len(words) and pos % 1 == 0 and _norm(words[k + 1]["text"]) in SHORT:
            ln = 0.5                                                           # "with me": two eighth notes in one beat
        elif half and pos % 1 == 0.5:
            ln = 0.5
        else:
            ln = 1.0 if pos % 1 == 0 else 0.5
        out.append((pos, ln)); pos += ln
        if ends[k]:
            pos = float(np.ceil(pos / 4) * 4)                                  # the sentence ends its bar
    total = int(np.ceil(pos / 4) * 4) or 4
    return out, total


def cuts(v, words, clean_db=-20.0):
    """Sample cut points around each word, and whether each inner cut sits in a real pause.

    TTS word timestamps (Edge) are often far off in connected speech ("row your boat": a 0.45 s "row" reported
    as 0.18 s), so cutting at them chops words mid-vowel. Each boundary instead goes to the quietest 10 ms
    between the two words. When even that spot is loud (clean_db under the line's loudest 10 ms is the line),
    the words run together and must not be pulled apart: clean[k] is False for the cut after word k."""
    n = v.shape[1]; hop = int(0.01 * SR)
    env = np.sqrt(np.mean(v.mean(0)[:n // hop * hop].reshape(-1, hop) ** 2, 1)) if n >= hop else np.zeros(1)
    env = np.convolve(env, np.ones(3) / 3, mode="same")
    top = float(env.max()) or 1.0; quiet = top * 10 ** (clean_db / 20)
    bounds, clean = [max(0, int((words[0]["t0"] - 0.04) * SR))], []
    for k in range(len(words) - 1):
        a, b = words[k], words[k + 1]
        lo = max(a["t0"] + 0.06, a["t1"] - 0.08)
        hi = max(lo + 0.02, min(b["t1"] - 0.06, b["t0"] + 0.30))
        i0, i1 = int(lo * SR) // hop, min(len(env), int(hi * SR) // hop + 1)
        if i1 > i0:
            i = i0 + int(np.argmin(env[i0:i1])); cut, ok = i * hop, bool(env[i] <= quiet)
        else:
            cut, ok = int(b["t0"] * SR), False
        bounds.append(max(bounds[-1] + hop, min(n, cut))); clean.append(ok)
    tail = int((words[-1]["t1"] + 0.05) * SR)                                  # last word: keep its audible tail
    loud = np.nonzero(env > 0.02 * top)[0]
    if loud.size:
        tail = max(tail, (int(loud[-1]) + 2) * hop)
    bounds.append(min(n, max(bounds[-1] + hop, tail)))
    return bounds, clean


def chant(job):
    bpm = float(job.get("bpm", 104)); beat = 60.0 / bpm
    v = read_audio(job["voice"]); words = job["words"]; text_words = job.get("text", "").split() if job.get("text") else [w["text"] for w in words]
    if len(text_words) != len(words):
        text_words = [w["text"] for w in words]
    sl, total = slots(words, text_words)
    dur = total * beat + 0.4; out = np.zeros((2, int(dur * SR))); placed = []
    bd, clean = cuts(v, words)
    groups, g = [], [0]                                                        # words with no pause between stay one piece
    for k in range(1, len(words)):
        if clean[k - 1]:
            groups.append(g); g = [k]
        else:
            g.append(k)
    groups.append(g)
    for g in groups:
        k0, k1 = g[0], g[-1]
        x = v[:, bd[k0]:bd[k1 + 1]].copy(); src = x.shape[1]
        if src < 32:
            continue
        pos = sl[k0][0]
        f = int(0.005 * SR); ramp = np.linspace(0, 1, f); x[:, :f] *= ramp; x[:, -f:] *= ramp[::-1]
        room = (sl[k1][0] + sl[k1][1] - pos) * beat * 0.97
        if x.shape[1] / SR > room:
            x = _atempo(x, min(1.7, (x.shape[1] / SR) / room))
            if x.shape[1] / SR > room:                                         # still long: fade out the tail
                n = int(room * SR); x = x[:, :n]; gl = int(0.02 * SR); x[:, -gl:] *= np.linspace(1, 0, gl)
        env = np.abs(x).max(0); on = int(np.argmax(env > 0.12 * env.max()))      # the piece's audible onset goes on the beat
        start = int(round(pos * beat * SR)) - on
        if start < 0:
            x = x[:, -start:]; start = 0
        n = min(x.shape[1], out.shape[1] - start); out[:, start:start + n] += x[:, :n]
        scale = x.shape[1] / src; end = start / SR + n / SR
        for j, k in enumerate(g):
            t0 = pos * beat if j == 0 else start / SR + (bd[k] - bd[k0]) * scale / SR
            t1 = end if k == k1 else start / SR + (bd[k + 1] - bd[k0]) * scale / SR
            placed.append({"text": words[k]["text"], "t0": round(t0, 3), "t1": round(max(t0, t1), 3)})
    write_wav(job["out"], out)
    return {"file": job["out"], "dur": round(dur, 3), "words": placed, "beats": total, "beat": round(beat, 5)}


if __name__ == "__main__":
    print(json.dumps(chant(json.load(open(sys.argv[1])))))
