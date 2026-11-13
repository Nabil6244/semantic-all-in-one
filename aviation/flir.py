"""Infrared / targeting-pod look (docs/aviation/J11_REFERENCE_STUDY.md J7) - only for clips that ARE infrared footage by their
own title (FLIR, infrared, thermal, targeting pod); ordinary footage is never dressed up to look like this.

    is_flir(title) -> bool
    graded(path) -> path            a cached infrared-graded copy of the clip next to it (grey, harder contrast, a little sensor
                                    noise), made once with ffmpeg; the original is returned when ffmpeg fails
    lay_hud(t, dur, p) -> RGBA      a tracking box that settles on the frame centre, corner ticks, a crosshair, the mode labels
                                    'IR' / 'WHT HOT' - labels of the look only, never invented readings or numbers
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw

from cinematic_explainer.war import motion as M

from . import style as S

W, H = S.W, S.H
_FLIR = re.compile(r"\bflir\b|\binfra-?red\b|\bthermal\b|\btargeting pod\b|\btargetting pod\b|\bir footage\b|\bforward[- ]looking\b", re.I)
GRADE = "format=gray,eq=contrast=1.35:brightness=0.03,noise=alls=7:allf=t,format=yuv420p"


def is_flir(title: str) -> bool:
    return bool(_FLIR.search(str(title or "")))


def graded(path: Any) -> str:
    src = Path(str(path))
    dst = src.with_name(src.stem + ".flir.mp4")
    if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime:
        return str(dst)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", GRADE, "-an", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "20", str(dst)], check=True, timeout=600)
        return str(dst)
    except Exception:
        return str(src)


def lay_hud(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    sc = S.scale()
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    ink = (235, 235, 235, 220)
    k = M.ease_out(M.clamp01(t / 0.9))
    bw, bh = int((420 - 160 * k) * sc), int((300 - 110 * k) * sc)             # the box closes in on the target
    cx, cy = W / 2 + 6 * sc * (1 - k), H / 2 - 4 * sc * (1 - k)
    d.rectangle((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), outline=ink, width=2)
    c = int(26 * sc)
    for x0, y0, dx, dy in ((40, 40, 1, 1), (W - 40, 40, -1, 1), (40, H - 40, 1, -1), (W - 40, H - 40, -1, -1)):
        x0, y0 = int(x0 * sc) if dx > 0 else int(W - 40 * sc), int(y0 * sc) if dy > 0 else int(H - 40 * sc)
        d.line((x0, y0, x0 + dx * c, y0), fill=ink, width=3)
        d.line((x0, y0, x0, y0 + dy * c), fill=ink, width=3)
    g = int(14 * sc)
    d.line((W / 2 - 3 * g, H / 2, W / 2 - g, H / 2), fill=ink, width=2)
    d.line((W / 2 + g, H / 2, W / 2 + 3 * g, H / 2), fill=ink, width=2)
    d.line((W / 2, H / 2 - 3 * g, W / 2, H / 2 - g), fill=ink, width=2)
    d.line((W / 2, H / 2 + g, W / 2, H / 2 + 3 * g), fill=ink, width=2)
    f = S.font("body", 16)
    d.text((int(80 * sc), int(70 * sc)), "IR", font=f, fill=ink)
    d.text((W - int(170 * sc), int(70 * sc)), "WHT HOT", font=f, fill=ink)
    return out
