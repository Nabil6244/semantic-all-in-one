"""A neutral dark backdrop for stretches of the timeline that have no footage (no clip for a scene, nothing before the first clip, no footage at all).

The war style never fills a gap with an unrelated clip: the maps and cards of those scenes sit on this plain plate, which is not footage and
is not presented as footage. One small clip per project, made once by ffmpeg and cached in the project's state folder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

from ..render import Shot

FPS = 25
LENGTH_S = 10.0
NAME = "war_backdrop_v1.mp4"


def ensure_backdrop(state_dir: str | Path) -> Optional[str]:
    """Path of the cached backdrop clip (made on first use); None when ffmpeg cannot make it."""
    d = Path(state_dir)
    out = d / NAME
    if out.is_file() and out.stat().st_size > 0:
        return str(out)
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / (NAME + ".part.mp4")
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x151a22:s=1280x720:r={FPS}:d={LENGTH_S}",
               "-vf", "vignette=PI/3,setsar=1,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-colorspace", "bt709",
               "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-an", str(tmp)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not tmp.is_file():
            return None
        tmp.replace(out)
        return str(out)
    except (OSError, subprocess.SubprocessError):
        return None


def _f(t: float) -> int:
    return int(round(t * FPS))


def fill_gaps(shots: Sequence[Shot], total_end: float, backdrop: Optional[str]) -> List[Shot]:
    """Shots covering [0, total_end] with no hole: every gap (before the first clip, between clips, after the last) gets a backdrop shot.
    Shots are returned in time order; overlapping or out-of-order input is left as it is. Without a backdrop file the input is returned."""
    ordered = sorted(shots, key=lambda s: s.start)
    if not backdrop or total_end <= 0:
        return ordered
    out: List[Shot] = []
    cursor = 0.0
    for s in ordered:
        if _f(s.start) > _f(cursor):
            out.append(Shot(backdrop, cursor, s.start))
        out.append(s)
        cursor = max(cursor, s.end)
    if _f(total_end) > _f(cursor):
        out.append(Shot(backdrop, cursor, total_end))
    return out
