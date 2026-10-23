"""Fixed-slot layout for the Milestone 1 cue kinds (header, card, icon, chip, arrow). Pure geometry and text fitting; no drawing, no files.
Rules: docs/explainer/explainer_cue_schema.md ("Layout")."""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from . import theme as T

Rect = Tuple[int, int, int, int]
W, H = 1920, 1080
MARGIN = 96
SAFE: Rect = (MARGIN, MARGIN, W - MARGIN, H - MARGIN)
SLOTS = {
    "H1": (640, 96, 1152, 190), "H2": (1312, 96, 1824, 190),
    "C1": (640, 230, 1152, 510), "C2": (1312, 230, 1824, 510), "C3": (640, 610, 1152, 890), "C4": (1312, 610, 1824, 890),
    "K1": (640, 904, 960, 980), "K2": (1000, 904, 1320, 980), "K3": (1360, 904, 1680, 980),
    "B": (640, 900, 1824, 984), "BL": (640, 900, 1232, 984), "BR": (1232, 900, 1824, 984),      # caption band (shares the strip with the chips)
}
SLOT_CLASS = {"header": ["H1", "H2"], "card": ["C1", "C2", "C3", "C4"], "icon": ["C1", "C2", "C3", "C4"], "chip": ["K1", "K2", "K3"], "caption": ["B", "BL", "BR"]}
DEFAULT_SIZE = {"header": (512, 94), "card": (512, 280), "icon": (512, 280), "chip": (320, 76), "caption": (1184, 84), "visual": (0, 0)}
ARROW_GAP = 14
ARROW_MIN_LEN = 40
HEAD_LEN = 34
FIT_MAX_PX, FIT_MIN_PX, FIT_STEP, FIT_MAX_LINES = 52, 40, 4, 3
CARD_PAD = 28
CARD_ICON_PX, CARD_ICON_GAP = 120, 22


def intersects(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def inside(a: Rect, outer: Rect = SAFE) -> bool:
    return a[0] >= outer[0] and a[1] >= outer[1] and a[2] <= outer[2] and a[3] <= outer[3]


def inflate(a: Rect, k: int) -> Rect:
    return (a[0] - k, a[1] - k, a[2] + k, a[3] + k)


def clamp(a: Rect) -> Rect:
    return (max(0, a[0]), max(0, a[1]), min(W, a[2]), min(H, a[3]))


def visible_overlap(on_a: float, hide_a: Optional[float], on_b: float, hide_b: Optional[float]) -> bool:
    """Two elements can be on screen together when each starts before the other is cleared."""
    return (hide_b is None or on_a < hide_b - 1e-9) and (hide_a is None or on_b < hide_a - 1e-9)


def wrap(words: Sequence[str], f, max_w: float, tracking: float) -> List[str]:
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w) if cur else w
        if T.tracked_width(f, trial, tracking) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, box_w: float, box_h: float, kind: str = "body", max_px: int = FIT_MAX_PX, min_px: int = FIT_MIN_PX,
             max_lines: int = FIT_MAX_LINES, th: T.Theme = T.THEME) -> Optional[Tuple[int, List[str]]]:
    """Largest size from max_px down to min_px (step 4) at which `text` wraps into at most `max_lines` lines inside the box; None if it never fits."""
    words = T.body_text(th, text).split()
    if not words:
        return None
    for px in range(max_px, min_px - 1, -FIT_STEP):
        f = T.font(kind, px)
        tr = px * th.tracking_em
        lines = wrap(words, f, box_w, tr)
        asc, desc = f.getmetrics()
        need_h = len(lines) * (asc + desc) * 1.0
        if len(lines) <= max_lines and need_h <= box_h and all(T.tracked_width(f, ln, tr) <= box_w for ln in lines):
            return px, lines
    return None


def arrow_geometry(src: Rect, dst: Rect) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Start and end of an arrow between the facing edges of two boxes (ARROW_GAP away from each), or None when they are too close."""
    cs = ((src[0] + src[2]) / 2, (src[1] + src[3]) / 2)
    cd = ((dst[0] + dst[2]) / 2, (dst[1] + dst[3]) / 2)
    dx, dy = cd[0] - cs[0], cd[1] - cs[1]
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return None
    ux, uy = dx / n, dy / n

    def exit_dist(r: Rect) -> float:
        hw, hh = (r[2] - r[0]) / 2, (r[3] - r[1]) / 2
        return min(hw / abs(ux) if abs(ux) > 1e-9 else 1e18, hh / abs(uy) if abs(uy) > 1e-9 else 1e18)

    a = exit_dist(src) + ARROW_GAP
    b = exit_dist(dst) + ARROW_GAP
    if n - a - b < ARROW_MIN_LEN:
        return None
    return (cs[0] + ux * a, cs[1] + uy * a), (cd[0] - ux * b, cd[1] - uy * b)


def segment_hits(p0, p1, rect: Rect, pad: int = 8, step: float = 4.0) -> bool:
    """True when the segment passes through `rect` (grown by pad), sampled every `step` pixels."""
    r = inflate(rect, pad)
    n = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / step))
    for i in range(n + 1):
        x = p0[0] + (p1[0] - p0[0]) * i / n
        y = p0[1] + (p1[1] - p0[1]) * i / n
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            return True
    return False
