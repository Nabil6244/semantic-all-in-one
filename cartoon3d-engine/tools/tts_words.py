#!/usr/bin/env python3
"""Speak lines with a free Edge voice and save each line's mp3 plus exact word timings.

Usage: tts_words.py JOB.json
JOB = {"voice": "...", "rate": "-6%", "lines": [{"text": "...", "out": "/path/line0.mp3"}, ...]}
Writes <out>.words.json next to each mp3: [{"text": "Ball", "t0": 0.11, "t1": 0.52}, ...] (seconds from the line start).
Lines whose mp3 and words file already exist are skipped (cache)."""
import asyncio
import json
import os
import sys

import edge_tts


async def speak(text, voice, rate, out):
    words, audio = [], bytearray()
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    async for chunk in com.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            t0 = chunk["offset"] / 1e7
            words.append({"text": chunk["text"], "t0": round(t0, 3), "t1": round(t0 + chunk["duration"] / 1e7, 3)})
    if not audio:
        raise RuntimeError(f"no audio for: {text!r}")
    with open(out, "wb") as f:
        f.write(audio)
    with open(out + ".words.json", "w") as f:
        json.dump(words, f)


async def main(job):
    for line in job["lines"]:
        out = line["out"]
        if os.path.exists(out) and os.path.exists(out + ".words.json"):
            continue
        for attempt in range(3):
            try:
                await speak(line["text"], job.get("voice", "en-US-JennyNeural"), job.get("rate", "+0%"), out)
                break
            except Exception as e:  # network hiccup: retry twice, then fail loudly
                if attempt == 2:
                    raise RuntimeError(f"Edge voice failed for {line['text']!r}: {e}")
                await asyncio.sleep(1.5)


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        asyncio.run(main(json.load(f)))
