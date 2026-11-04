"""Sentence timing from a real voiceover, for camera travel that follows the narrator's actual silences.

    python3 tools/narration_timing.py voiceover.wav out/narration.json [--model small]
    node render.mjs story.csv --narration out/narration.json ...

Uses faster-whisper (already in the app's .venv) with word timestamps; a sentence ends at . ! or ?. Output:
    {"sentences": [{"start": s, "end": s, "text": "..."}], "silences": [{"start": s, "end": s}]}
Silences are gaps of 0.6 s or more between sentences: the timeline puts every camera move inside one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def sentences_from_words(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if w["word"].strip().endswith((".", "!", "?")):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [{"start": round(s[0]["start"], 3), "end": round(s[-1]["end"], 3), "text": "".join(x["word"] for x in s).strip()} for s in out]


def silences_between(sentences, min_gap=0.6):
    return [{"start": a["end"], "end": b["start"]} for a, b in zip(sentences, sentences[1:]) if b["start"] - a["end"] >= min_gap]


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("audio"); p.add_argument("out"); p.add_argument("--model", default="small")
    a = p.parse_args(argv)
    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(a.audio, word_timestamps=True, vad_filter=True)
    words = [{"word": w.word, "start": w.start, "end": w.end} for s in segs for w in (s.words or [])]
    sents = sentences_from_words(words)
    Path(a.out).write_text(json.dumps({"sentences": sents, "silences": silences_between(sents)}, indent=1), encoding="utf-8")
    print(json.dumps({"event": "done", "sentences": len(sents), "out": a.out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
