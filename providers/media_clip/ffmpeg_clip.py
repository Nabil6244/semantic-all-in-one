"""Download a clip segment from a remote media URL using ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

LogFn = Callable[[str], None]


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is not installed or not on PATH.")
    return path


def _ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe is not installed or not on PATH.")
    return path


def probe_duration(url: str) -> Optional[float]:
    try:
        proc = subprocess.run(
            [
                _ffprobe(),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
        raw = (data.get("format") or {}).get("duration")
        return float(raw) if raw else None
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return None


def download_clip(
    url: str,
    dest: Path,
    start: float,
    duration: float,
    *,
    log: LogFn = print,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Path:
    if should_stop and should_stop():
        raise IOError("download cancelled")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Must keep a real media extension for ffmpeg's muxer (001.mp4.part breaks — muxer sees ".part").
    tmp = dest.with_name(f"{dest.stem}_tmp{dest.suffix}")
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    start = max(0.0, float(start))
    duration = max(0.1, float(duration))
    fmt = dest.suffix.lower().lstrip(".") or "mp4"
    cmd = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-i", url,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
        "-f", fmt,
        "-y",
        str(tmp),
    ]
    log(f"[CLIP] ffmpeg segment {start:.1f}s + {duration:.1f}s")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    if proc.returncode != 0:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise RuntimeError(f"ffmpeg clip failed: {tail or 'unknown error'}")
    if should_stop and should_stop():
        tmp.unlink(missing_ok=True)
        raise IOError("download cancelled")
    tmp.replace(dest)
    return dest
