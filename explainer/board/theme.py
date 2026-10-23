"""Board theme (Phase 1): colours, fonts and small drawing helpers for the Explainer board look. Pure Pillow, imports nothing from the application.

Fonts (see explainer/assets/fonts/README.txt): Patrick Hand for body lettering, Kalam Bold for outlined display titles, Inter SemiBold for chips.
Look rules come from docs/explainer/explainer_style_guide.md sections 1 to 3: flat light-grey board, flat objects with a thin dark outline,
dark ink body lettering with wide letter spacing, heavy yellow outlined title, dark pill chips. Values marked PROVISIONAL are proposals."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

PKG = Path(__file__).resolve().parents[1]
FONT_BODY = PKG / "assets" / "fonts" / "PatrickHand-Regular.ttf"
FONT_TITLE = PKG / "assets" / "fonts" / "Kalam-Bold.ttf"
FONT_CHIP = PKG.parent / "assets" / "fonts" / "Inter-SemiBold.ttf"


@dataclass(frozen=True)
class Theme:
    board: Tuple[int, int, int] = (192, 192, 192)        # #C0C0C0, measured in the reference (+-8)
    ink: Tuple[int, int, int] = (38, 38, 40)
    paper: Tuple[int, int, int] = (240, 232, 200)        # #F0E8C8 cream card (+-8)
    outline: Tuple[int, int, int] = (38, 38, 40)
    title_fill: Tuple[int, int, int] = (244, 204, 48)    # PROVISIONAL yellow
    title_stroke: Tuple[int, int, int] = (70, 44, 20)    # PROVISIONAL dark brown
    chip_fill: Tuple[int, int, int] = (30, 32, 38)
    chip_text: Tuple[int, int, int] = (250, 250, 250)
    roles: Dict[str, Tuple[int, int, int]] = None        # filled in __post_init__ substitute below
    body_px: int = 72
    label_px: int = 52
    title_px: int = 128
    chip_px: int = 44
    tracking_em: float = 0.06                            # PROVISIONAL "wide letter spacing", fraction of the font size
    outline_px: int = 5
    body_lower: bool = False                             # the guide says lower case; off by default so proper nouns keep their capitals


ROLES = {"blue": (66, 120, 206), "green": (60, 160, 100), "gold": (226, 170, 40), "red": (212, 70, 66)}   # PROVISIONAL flat object colours
THEME = Theme(roles=ROLES)


@lru_cache(maxsize=64)
def font(kind: str, px: int) -> ImageFont.FreeTypeFont:
    path = {"body": FONT_BODY, "title": FONT_TITLE, "chip": FONT_CHIP}[kind]
    return ImageFont.truetype(str(path), max(6, int(px)))


def tracked_width(f: ImageFont.FreeTypeFont, text: str, tracking: float) -> float:
    return sum(f.getlength(c) for c in text) + tracking * max(0, len(text) - 1)


def draw_tracked(d: ImageDraw.ImageDraw, xy: Tuple[float, float], text: str, f: ImageFont.FreeTypeFont, fill, tracking: float, anchor: str = "l") -> None:
    """Draw `text` one character at a time with `tracking` extra pixels between characters. anchor: l (left), m (centre) on the baseline-ish 'ls' line
    is avoided: the y given is the top of the text box ('la' / 'ma')."""
    x, y = xy
    if anchor == "m":
        x -= tracked_width(f, text, tracking) / 2
    for c in text:
        d.text((x, y), c, font=f, fill=fill, anchor="la")
        x += f.getlength(c) + tracking


def tracked_bbox(xy: Tuple[float, float], text: str, f: ImageFont.FreeTypeFont, tracking: float, anchor: str = "l") -> Tuple[int, int, int, int]:
    x, y = xy
    w = tracked_width(f, text, tracking)
    if anchor == "m":
        x -= w / 2
    asc, desc = f.getmetrics()
    return int(x), int(y), int(x + w + 2), int(y + asc + desc + 2)


def body_text(t: Theme, text: str) -> str:
    return text.lower() if t.body_lower else text


def draw_chip(im: Image.Image, center: Tuple[int, int], text: str, t: Theme = THEME) -> Tuple[int, int, int, int]:
    """A dark rounded pill with white sans text (a year, a ratio). Returns its box."""
    d = ImageDraw.Draw(im)
    f = font("chip", t.chip_px)
    w = f.getlength(text)
    pad_x, pad_y = int(t.chip_px * 0.6), int(t.chip_px * 0.3)
    asc, desc = f.getmetrics()
    box = (int(center[0] - w / 2 - pad_x), int(center[1] - (asc + desc) / 2 - pad_y), int(center[0] + w / 2 + pad_x), int(center[1] + (asc + desc) / 2 + pad_y))
    d.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=t.chip_fill)
    d.text((center[0], (box[1] + box[3]) / 2), text, font=f, fill=t.chip_text, anchor="mm")
    return box


def draw_object(d: ImageDraw.ImageDraw, center: Tuple[int, int], r: int, role: str, t: Theme = THEME) -> None:
    """Placeholder flat object (a disc) in the guide's style: flat role colour, thin dark outline, no gradient. Real icons come in Phase 3."""
    cx, cy = center
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=t.roles.get(role, t.roles["blue"]), outline=t.outline, width=t.outline_px)
