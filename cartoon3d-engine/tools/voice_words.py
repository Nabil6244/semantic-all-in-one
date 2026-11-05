#!/usr/bin/env python3
"""Word times for a recorded voice-over (faster-whisper, local, the cached 'base' model; nothing is downloaded when it is cached).

Usage: voice_words.py VOICE OUT.json
Writes {"duration": s, "words": [{"text", "t0", "t1"}, ...]} and a OUT.json.sig file. A second run on the same voice file
(path, size, saved time) reuses the saved times: transcribing takes a while."""
import json
import os
import sys


def sig(path):
    st = os.stat(path)
    return [os.path.abspath(path), st.st_size, st.st_mtime_ns, "base"]


def onsets(src, words):
    """Whisper often starts a word in the pause before it: move each start to where the word's own sound rises
    (10 ms level above the word's peak - 24 dB, at least -45 dBFS), searching up to the word's end."""
    import subprocess
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32); n = len(x) // 160
    db = 20 * np.log10(np.sqrt((x[: n * 160].reshape(-1, 160) ** 2).mean(1)) + 1e-9)
    for i, w in enumerate(words):
        a, b = int(w["t0"] * 100), max(int(w["t0"] * 100) + 1, int(w["t1"] * 100) - 3)
        if a >= n:
            continue
        if db[a:min(b, n)].max(initial=-120) < -40:           # the whole word was placed in silence: its sound comes later
            b = int(words[i + 1]["t0"] * 100) if i + 1 < len(words) else n
        seg = db[a:min(b, n)]
        if not len(seg):
            continue
        thr = max(-45.0, float(seg.max()) - 24)
        k = int(np.argmax(seg))                                 # the word is the burst around its loudest moment:
        while k > 0 and (seg[k - 1] > thr or seg[max(0, k - 4):k].max() > thr):   # walk back to where that burst starts (gaps under 40 ms bridged),
            k -= 1                                              # so the tail of the previous word before a pause is not taken
        if k > 0:
            span = w["t1"] - w["t0"]; w["t0"] = round((a + k) / 100, 3); w["t1"] = round(max(w["t1"], w["t0"] + min(span, 0.6)), 3)


def main(src, dst):
    if os.path.isfile(dst) and os.path.isfile(dst + ".sig"):
        try:
            if json.load(open(dst + ".sig")) == sig(src):
                print(json.dumps({"words": len(json.load(open(dst))["words"]), "cached": True}))
                return
        except Exception:
            pass
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segs, info = model.transcribe(src, word_timestamps=True, language="en", vad_filter=False, beam_size=5)
    words = [{"text": w.word.strip(), "t0": round(w.start, 3), "t1": round(w.end, 3)} for s in segs for w in (s.words or []) if w.word.strip()]
    onsets(src, words)
    json.dump({"duration": round(info.duration, 3), "words": words}, open(dst, "w"))
    json.dump(sig(src), open(dst + ".sig", "w"))
    print(json.dumps({"words": len(words), "cached": False}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
