"""A neutral atmosphere plate for stretches of the timeline that have no footage (no clip for a scene, nothing before the first clip, no footage at all).

The war style never fills a gap with an unrelated clip: the maps and cards of those scenes sit on this plate, which is not footage and is not
presented as footage. It is not flat black either: a very dark blue-grey field with a soft light drifting on a closed path, a fine tactical
grid that creeps one cell and wraps, a vignette and fine grain, so a gap reads as a deliberate, living backdrop. One clip per project, made once by
ffmpeg and cached in the project's state folder (24 s, the light and the grid loop seamlessly; gap shots start at different offsets so two
neighbouring gaps never look the same).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

from ..render import Shot

log = logging.getLogger("cinematic_explainer.war.backdrop")
FPS = 25
LENGTH_S = 24.0
CELL = 80                     # grid cell in px; the grid creeps exactly one cell per loop
NAME = "war_backdrop_v3.mp4"
MAX_OFFSET_S = 12.0           # a piece is at most 11 s, so an offset up to 12 s never runs past the end of the 24 s clip


def _light_expr() -> str:
    """geq luma of the soft light on a 320x180 field (X, Y px; T s): a gaussian blob on a closed elliptical path with period LENGTH_S."""
    w = 2 * 3.141592653589793 / LENGTH_S
    cx = f"(160+70*cos({w:.6f}*T))"
    cy = f"(90+28*sin({w:.6f}*T*2))"
    return f"48+34*exp(-(pow(X-{cx},2)+pow((Y-{cy})*1.3,2))/(2*pow(80,2)))+6*(Y/180)"


def ensure_backdrop(state_dir: str | Path) -> Optional[str]:
    """Path of the cached backdrop clip (made on first use); None when ffmpeg cannot make it."""
    d = Path(state_dir)
    out = d / NAME
    if out.is_file() and out.stat().st_size > 0:
        return str(out)
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / (NAME + ".part.mp4")
        steps = int(LENGTH_S * FPS)
        # the grid layer scrolls one cell per loop (speed is a fraction of the frame per frame), then is screened over the light field
        vscroll = CELL / 720 / steps
        graph = (f"color=c=black:s=320x180:r={FPS}:d={LENGTH_S},format=yuv444p,"
                 f"geq=lum='{_light_expr()}':cb='134+6*(1-Y/180)':cr='126-3*(1-Y/180)',scale=1280:720:flags=bicubic[lt];"
                 f"color=c=black:s=1280x720:r={FPS}:d={LENGTH_S},format=yuv444p,"
                 f"drawgrid=w={CELL}:h={CELL}:t=1:c=white@0.13,scroll=vertical={vscroll:.8f}:horizontal={vscroll:.8f}[gr];"
                 f"[lt][gr]blend=c0_mode=screen:c1_expr='A':c2_expr='A',vignette=PI/10,noise=alls=5:allf=t:all_seed=5,"
                 f"setsar=1,format=yuv420p")
        cmd = ["ffmpeg", "-v", "error", "-y", "-filter_complex", graph, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-an", str(tmp)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not tmp.is_file():
            log.warning('backdrop not made: %s', (r.stderr or '')[-400:])
            return None
        tmp.replace(out)
        return str(out)
    except (OSError, subprocess.SubprocessError):
        return None


def _offset(at: float) -> float:
    """Where in the loop a gap shot starts: a fixed function of its start time, spread over 0..MAX_OFFSET_S, so neighbouring gaps differ."""
    return round((at * 5.3 + 1.7) % MAX_OFFSET_S, 2)


def _f(t: float) -> int:
    return int(round(t * FPS))


def _plate(backdrop: str, a: float, b: float) -> List[Shot]:
    """Plate shots for [a, b]: a long gap is cut where the 24 s loop wraps, so no piece ever runs past the end of the clip and holds a frame."""
    out: List[Shot] = []
    pos, t = _offset(a), a
    while _f(b) > _f(t):
        room = LENGTH_S - pos
        if room < 0.2:
            pos, room = 0.0, LENGTH_S
        ln = min(b - t, room, 10.0)
        out.append(Shot(backdrop, t, t + ln, seek=round(pos, 3)))
        t += ln
        pos = (pos + ln) % LENGTH_S
    return out


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
            out.extend(_plate(backdrop, cursor, s.start))
        out.append(s)
        cursor = max(cursor, s.end)
    if _f(total_end) > _f(cursor):
        out.extend(_plate(backdrop, cursor, total_end))
    return out
