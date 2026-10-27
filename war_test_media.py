"""Sample clips for the War Documentary render tests: the project's Images/ clips when they are there (Images/ is not in git), else
short generated stand-ins of the same size, length and audio, made once per machine."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_SPECS = {"007.mp4": ("1920x1080", 2.93, True), "008.mp4": ("1280x720", 8.0, True), "013.mp4": ("1920x1080", 10.6, False)}   # name -> size, seconds, has audio
_DIR = Path(tempfile.gettempdir()) / "war_test_media"


def clip(name: str) -> str:
    real = ROOT / "Images" / name
    if real.is_file():
        return str(real)
    size, dur, audio = _SPECS[name]
    out = _DIR / name
    if not out.is_file() and shutil.which("ffmpeg"):
        _DIR.mkdir(parents=True, exist_ok=True)
        tmp = _DIR / f".{name}.{os.getpid()}.mp4"   # one per process: parallel test modules never write the same file
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24:duration={dur}"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-c:a", "aac", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(tmp)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        tmp.replace(out)
    return str(out)
