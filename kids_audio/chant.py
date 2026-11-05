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


def chant(job):
    bpm = float(job.get("bpm", 104)); beat = 60.0 / bpm
    v = read_audio(job["voice"]); words = job["words"]; text_words = job.get("text", "").split() if job.get("text") else [w["text"] for w in words]
    if len(text_words) != len(words):
        text_words = [w["text"] for w in words]
    sl, total = slots(words, text_words)
    dur = total * beat + 0.4; out = np.zeros((2, int(dur * SR))); placed = []
    for k, (w, (pos, ln)) in enumerate(zip(words, sl)):
        a = max(0.0, w["t0"] - 0.015); b = min(w["t1"] + 0.05, words[k + 1]["t0"] if k + 1 < len(words) else v.shape[1] / SR)
        x = v[:, int(a * SR):int(b * SR)].copy()
        if x.shape[1] < 32:
            continue
        f = int(0.005 * SR); ramp = np.linspace(0, 1, f); x[:, :f] *= ramp; x[:, -f:] *= ramp[::-1]
        room = ln * beat * 0.97
        if x.shape[1] / SR > room:
            x = _atempo(x, min(1.7, (x.shape[1] / SR) / room))
            if x.shape[1] / SR > room:                                         # still long: fade out the tail
                n = int(room * SR); x = x[:, :n]; g = int(0.02 * SR); x[:, -g:] *= np.linspace(1, 0, g)
        env = np.abs(x).max(0); on = int(np.argmax(env > 0.12 * env.max()))      # the word's audible onset goes on the beat
        start = int(round(pos * beat * SR)) - on
        if start < 0:
            x = x[:, -start:]; start = 0
        n = min(x.shape[1], out.shape[1] - start); out[:, start:start + n] += x[:, :n]
        t0 = pos * beat; placed.append({"text": w["text"], "t0": round(t0, 3), "t1": round(start / SR + n / SR, 3)})
    write_wav(job["out"], out)
    return {"file": job["out"], "dur": round(dur, 3), "words": placed, "beats": total, "beat": round(beat, 5)}


if __name__ == "__main__":
    print(json.dumps(chant(json.load(open(sys.argv[1])))))
