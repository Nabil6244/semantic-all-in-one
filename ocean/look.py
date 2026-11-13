"""Ocean channel identity (docs/ocean/PATTERNS.md sections 3-4): one palette and type for every set, card and caption.

    WATER_TOP, WATER_MID, WATER_DEEP      the home water gradient (light near the surface, near-black at the bottom)
    ABYSS_*, SAND_*, KELP_*, ISLAND        set colours
    ORANGE (key words, numbers), RED (danger words), WHITE, SOFT (small caption words), INK
    font(role, size)                       title / heavy / body / regular, scaled to the frame
    scale()                                frame width / 1280: every layout is written in 1280 x 720 units
"""

from __future__ import annotations

from aviation import style as _AV

W, H = _AV.W, _AV.H

WATER_TOP = (34, 92, 122, 255)
WATER_MID = (16, 56, 82, 255)
WATER_DEEP = (6, 18, 30, 255)
ABYSS_TOP = (14, 22, 40, 255)
ABYSS_DEEP = (4, 5, 12, 255)
ABYSS_TINT = (54, 26, 78, 255)       # the purple glow of the deep sets
SKY_TOP = (150, 170, 182, 255)
SKY_LOW = (196, 206, 210, 255)
ISLAND = (30, 40, 48, 255)
SAND_TOP = (214, 182, 128, 255)
SAND_LOW = (176, 140, 92, 255)
KELP = (58, 92, 54, 255)
KELP_DARK = (34, 60, 36, 255)
RAY = (190, 228, 240)                # god-ray colour (alpha added per ray)
SPECK = (200, 230, 240)

ORANGE = (246, 168, 40, 255)
RED = (232, 72, 60, 255)
WHITE = (246, 248, 250, 255)
SOFT = (214, 226, 232, 255)
INK = (16, 20, 26, 255)
TEAL = (64, 150, 140, 255)


def font(role: str, size: int):
    return _AV.font(role, size)


def scale() -> float:
    return _AV.scale()
