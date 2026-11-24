"""Stand-in voice when Edge is flaky: one sentence per request, each kept in vo_pieces/ (resume-safe), retried with a
growing pause, then joined with short gaps (0.25 s between sentences, 0.6 s between paragraphs) and mastered to -14 LUFS.
Run: python3 vo_make.py [narration_tts.txt]"""
import asyncio
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
import edge_voiceover as E  # noqa: E402

VOICE = "en-US-AndrewNeural"
TXT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "narration_tts.txt"
PIECES = HERE / "vo_pieces"


async def fetch(text, out):
    tmp = out.with_suffix(".part.mp3")
    await edge_tts.Communicate(text, VOICE).save(str(tmp))
    if tmp.stat().st_size < 2000:
        raise RuntimeError("tiny audio")
    tmp.replace(out)


def get(text):
    out = PIECES / f"{hashlib.md5((VOICE + text).encode()).hexdigest()[:12]}.mp3"
    for k in range(10):
        if out.is_file():
            return out
        try:
            asyncio.run(fetch(text, out))
        except Exception as e:  # noqa: BLE001
            print(f"  retry {k + 1}: {str(e)[:50]}", flush=True)
            time.sleep(4 + 4 * k)
    raise SystemExit(f"Edge gave no audio for: {text[:60]}")


def silence(sec, out):
    if not out.is_file():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(sec),
                        "-c:a", "libmp3lame", "-b:a", "48k", str(out)], check=True)
    return out


if __name__ == "__main__":
    PIECES.mkdir(exist_ok=True)
    paras = [p for p in TXT.read_text().split("\n\n") if p.strip()]
    parts, n = [], sum(len(E.split_sentences(p)) for p in paras)
    done = 0
    for pi, para in enumerate(paras):
        for si, s in enumerate(E.split_sentences(para)):
            parts.append(get(s))
            done += 1
            print(f"{done}/{n}", flush=True)
            last = si == len(E.split_sentences(para)) - 1
            parts.append(silence(0.6 if last else 0.25, PIECES / ("gap_long.mp3" if last else "gap_short.mp3")))
    wavs = []
    for i, p in enumerate(parts[:-1]):                    # decode all to one format so the join is clean
        w = PIECES / f"j{i:04d}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-ar", "48000", "-ac", "1", str(w)], check=True)
        wavs.append(w)
    lst = PIECES / "join.txt"
    lst.write_text("".join(f"file '{w}'\n" for w in wavs))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-af",
                    "highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=5:release=60,loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-ar", "48000", "-b:a", "192k", str(HERE / "manual_vo_mastered.mp3")], check=True)
    for w in wavs:
        w.unlink()
    print("voice done")
