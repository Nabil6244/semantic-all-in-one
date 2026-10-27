"""War Documentary style tokens: palette, status colours, type, geometry, timings. One place; every card and map reads from here.

Fonts: installed system fonts first (nothing is downloaded at runtime), then the fonts the app already ships, then PIL's default.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import ImageFont

from .. import look as L

W, H = L.W, L.H
FPS = L.FPS

# ---- palette: charcoal, navy, muted earth, cream; red and blue held back for emphasis ----
CHARCOAL = (18, 20, 24, 255)
INK = (10, 12, 16, 255)
NAVY = (14, 24, 40, 255)
PANEL = (16, 22, 32, 235)          # card background over dimmed footage
PANEL_LINE = (70, 82, 100, 255)
EARTH = (96, 88, 70, 255)
EARTH_DARK = (52, 48, 40, 255)
SAND = (150, 138, 108, 255)
CREAM = (236, 230, 214, 255)
CREAM_DIM = (176, 170, 156, 255)
GREY = (140, 146, 156, 255)
RED = (190, 52, 52, 255)           # warning / emphasis, never "the enemy" by itself
BLUE = (64, 112, 170, 255)         # secondary accent, never "the friendly side" by itself
AMBER = (214, 168, 58, 255)
WATER = (22, 36, 54, 255)
LAND = (44, 50, 56, 255)
LAND_LIGHT = (66, 72, 78, 255)
BORDER = (110, 118, 128, 255)

# Map affiliation is always written next to the colour (a label or a legend); these two fills are neutral-toned accents, not teams.
FILL_A = (150, 70, 62, 255)
FILL_B = (62, 98, 140, 255)
FILL_NEUTRAL = (88, 94, 100, 255)

STATUSES = ("confirmed", "attributed", "disputed", "unverified", "illustrative")
STATUS_LABEL: Dict[str, str] = {"confirmed": "CONFIRMED", "attributed": "ATTRIBUTED", "disputed": "DISPUTED",
                                "unverified": "UNVERIFIED", "illustrative": "ILLUSTRATIVE"}
STATUS_COLOUR: Dict[str, Tuple[int, int, int, int]] = {"confirmed": (84, 150, 112, 255), "attributed": BLUE, "disputed": AMBER,
                                                       "unverified": GREY, "illustrative": CREAM_DIM}


def status_of(params: dict) -> str:
    s = str((params or {}).get("status") or "unverified").lower()
    return s if s in STATUSES else "unverified"


# ---- geometry: 16:9, safe margins ----
MARGIN_X = int(W * 0.05)
MARGIN_Y = int(H * 0.06)
SAFE = (MARGIN_X, MARGIN_Y, W - MARGIN_X, H - MARGIN_Y)
LOWER_ZONE_Y = int(H * 0.86)       # only shot headlines and chips live below this line

# ---- timings (reference A measured, +-0.1 s; see docs/styles/cinematic_explainer_research.md 0b) ----
IN_S = L.CARD_IN_S                 # 0.3
OUT_S = L.CARD_OUT_S               # 0.2
ROW_S = 0.3
DRAW_S = 0.5                       # rules and lines
COUNT_S = L.COUNT_S                # 0.4
CAMERA_S = 2.4                     # map camera push
PULSE_S = 1.6                      # location pulse period
MIN_HOLD_S = 1.5

# ---- type ----
_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

_CANDIDATES: Dict[str, list] = {
    "display": ["/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
                "C:/Windows/Fonts/ARIALNB.TTF", "C:/Windows/Fonts/impact.ttf", "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf"],
    "serif": ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "C:/Windows/Fonts/georgiab.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"],
    "serif_regular": ["/System/Library/Fonts/Supplemental/Georgia.ttf", "C:/Windows/Fonts/georgia.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
}
_BUNDLED = {"display": ("heavy",), "serif": ("serif",), "serif_regular": ("serif",), "bold": ("bold",), "regular": ("regular",),
            "heavy": ("heavy",)}


def font(kind: str, size: int):
    """kind: display (condensed caps), heavy (wide bold), bold, regular (UI sans), serif, serif_regular. Cached; never raises."""
    key = (kind, int(size))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    f: Optional[ImageFont.FreeTypeFont] = None
    for path in _CANDIDATES.get(kind, []):
        if os.path.isfile(path):
            try:
                f = ImageFont.truetype(path, int(size))
                break
            except OSError:
                f = None
    if f is None:
        f = L.font(_BUNDLED.get(kind, ("bold",))[0], int(size))
    _FONT_CACHE[key] = f
    return f


def fonts_in_use() -> Dict[str, str]:
    """Which font file each role resolved to (for the plan report / logs)."""
    out = {}
    for k in ("display", "serif", "bold"):
        f = font(k, 20)
        out[k] = getattr(f, "path", "default")
    return out
