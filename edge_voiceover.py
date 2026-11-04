"""Free voiceover from a script using Microsoft Edge's neural voices (edge-tts).

Synthesis runs on Microsoft's servers, so this costs almost no local CPU.
The script is split on sentence ends into pieces, the pieces are fetched
a few at a time, each piece is retried on its own, and the pieces are
joined with ffmpeg. Word timings come back with the audio and are written
next to it, so a later step can skip a transcription pass.

This is an unofficial endpoint: callers should treat any failure as
"fall back to the user's own audio file".
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Callable, Optional

DEFAULT_VOICE = "en-US-AndrewNeural"
MAX_CHUNK_CHARS = 1500
PARALLEL = 4
RETRIES = 3
PAUSE_SEC = 0.25


def ensure_installed(say=None) -> bool:
    """True when edge-tts can be imported. If not (and this is not a frozen build), install it once with pip into the running
    Python, telling the caller what is happening through say(text)."""
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        pass
    if getattr(sys, "frozen", False):
        return False
    if say:
        say("Setting up the voices (one time, about a minute)...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "edge-tts>=6.1"],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return False
    import importlib
    importlib.invalidate_caches()
    try:
        import edge_tts  # noqa: F401,F811
        return True
    except ImportError:
        return False


def split_script(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split on sentence ends so no piece is longer than max_chars
    (a single oversize sentence is cut at spaces)."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    pieces: list[str] = []
    cur = ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        while len(sent) > max_chars:
            cut = sent.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            head, sent = sent[:cut], sent[cut:].lstrip()
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(head)
        if cur and len(cur) + 1 + len(sent) > max_chars:
            pieces.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
    if cur:
        pieces.append(cur)
    return pieces


def _concat_line(path: str) -> str:
    """One line of an ffmpeg concat list: single-quoted, with ' written as '\\''."""
    return "file '" + path.replace("'", "'\\''") + "'\n"


def _rate(speed: float) -> str:
    return f"{int(round((speed - 1.0) * 100)):+d}%"


async def _fetch_piece(edge_tts, text, voice, speed, pitch_hz, path):
    last: Optional[Exception] = None
    for attempt in range(RETRIES):
        try:
            kw = dict(rate=_rate(speed), pitch=f"{pitch_hz:+d}Hz")
            try:
                comm = edge_tts.Communicate(text, voice, boundary="WordBoundary", **kw)
            except TypeError:   # older edge-tts has no boundary option (word timings are then empty)
                comm = edge_tts.Communicate(text, voice, **kw)
            words = []
            with open(path, "wb") as f:
                async for ev in comm.stream():
                    if ev["type"] == "audio":
                        f.write(ev["data"])
                    elif ev["type"] == "WordBoundary":
                        words.append({
                            "word": ev["text"],
                            "start": ev["offset"] / 1e7,
                            "end": (ev["offset"] + ev["duration"]) / 1e7,
                        })
            if os.path.getsize(path) == 0:
                raise RuntimeError("empty audio")
            return words
        except Exception as e:  # network / throttle: retry this piece only
            last = e
            await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"voiceover piece failed after {RETRIES} tries: {last}")


def _duration(path: str, ffprobe: str = "ffprobe") -> float:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True, check=True, timeout=1800)
    return float(out.stdout.strip())


async def _run(pieces, voice, speed, pitch_hz, workdir, progress):
    import edge_tts
    sem = asyncio.Semaphore(PARALLEL)
    done = 0

    async def job(i, t):
        nonlocal done
        async with sem:
            p = os.path.join(workdir, f"piece_{i:04d}.mp3")
            w = await _fetch_piece(edge_tts, t, voice, speed, pitch_hz, p)
            done += 1
            if progress:
                progress(done, len(pieces))
            return p, w

    return await asyncio.gather(*[job(i, t) for i, t in enumerate(pieces)])


def synthesize(text: str, out_mp3: str, voice: str = DEFAULT_VOICE,
               speed: float = 1.0, pitch_hz: int = 0,
               ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
               progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """Write the voiceover to out_mp3 and word timings to out_mp3 + '.words.json'.
    Returns {'path', 'duration', 'pieces', 'words_path'}."""
    pieces = split_script(text)
    if not pieces:
        raise ValueError("empty script")
    with tempfile.TemporaryDirectory() as wd:
        results = asyncio.run(_run(pieces, voice, speed, pitch_hz, wd, progress))
        # silence between pieces, same codec so concat is clean
        gap = os.path.join(wd, "gap.mp3")
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             "anullsrc=r=24000:cl=mono", "-t", str(PAUSE_SEC),
             "-c:a", "libmp3lame", "-b:a", "48k", gap], check=True, timeout=1800)
        lst = os.path.join(wd, "list.txt")
        offset, words = 0.0, []
        with open(lst, "w") as f:
            for p, w in results:
                f.write(_concat_line(p))
                f.write(_concat_line(gap))
                words += [{**x, "start": x["start"] + offset,
                           "end": x["end"] + offset} for x in w]
                offset += _duration(p, ffprobe) + PAUSE_SEC
        os.makedirs(os.path.dirname(os.path.abspath(out_mp3)), exist_ok=True)
        base = [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst]
        enc = ["-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k", out_mp3]
        # loudnorm to -14 LUFS (the app's level); if that step ever fails the plain join is still written
        try:
            ok = subprocess.run(base + ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] + enc, timeout=1800).returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        if not ok or not os.path.isfile(out_mp3) or os.path.getsize(out_mp3) == 0:
            subprocess.run(base + enc, check=True, timeout=1800)
    words_path = out_mp3 + ".words.json"
    with open(words_path, "w") as f:
        json.dump(words, f)
    return {"path": out_mp3, "duration": _duration(out_mp3, ffprobe),
            "pieces": len(pieces), "words_path": words_path}
