"""Lightweight frame sampling for video QA."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from providers.base import MediaType


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not available")
    return path


def sample_frames(
    path: Path,
    media_type: MediaType,
    *,
    cache_dir: Optional[Path] = None,
    duration: Optional[float] = None,
) -> List[Path]:
    """Return 1–3 representative frame paths (cached under cache_dir when set)."""
    path = Path(path)
    if not path.is_file():
        return []
    if media_type == MediaType.IMAGE:
        return [path]

    dur = duration
    if dur is None or dur <= 0:
        from .technical import probe_local_media

        dur, _, _ = probe_local_media(path)
    dur = max(0.5, float(dur or 3.0))

    if cache_dir is not None:
        key = hashlib.sha256(f"{path.resolve()}:{dur:.2f}".encode()).hexdigest()[:16]
        out_dir = Path(cache_dir) / key
        out_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(out_dir.glob("frame_*.jpg"))
        if existing:
            return existing[:3]
    else:
        out_dir = Path(tempfile.mkdtemp(prefix="vq_frames_"))

    stamps = [0.08, max(0.15, dur * 0.5), max(0.2, dur - 0.15)]
    if dur < 1.5:
        stamps = [0.05, dur * 0.5]
    frames: List[Path] = []
    for i, t in enumerate(stamps[:3]):
        dest = out_dir / f"frame_{i:02d}.jpg"
        if dest.is_file():
            frames.append(dest)
            continue
        cmd = [
            _ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-q:v",
            "4",
            "-y",
            str(dest),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25, check=False)
        if proc.returncode == 0 and dest.is_file():
            frames.append(dest)
    return frames
