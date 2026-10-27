"""Cinematic Explainer look pack: tokens, fonts and easing. Opt-in and self-contained: nothing here is imported by another style.

Measured motion (reference A, +-0.1 s, docs/styles/cinematic_explainer_research.md): backdrop dims in 0.2 s, a card fades in 0.3 s,
a number counts for 0.4 s and its rule draws in 0.5 s, list rows fade in 0.3 s, source-card words darken as they are spoken.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FPS = 25

RED = (214, 28, 40, 255)
YELLOW = (255, 213, 0, 255)
NAVY = (14, 22, 36, 255)
PAPER = (244, 239, 228, 255)
INK = (24, 24, 28, 255)
GHOST = (176, 172, 164, 255)
WHITE = (255, 255, 255, 255)
GREY = (190, 194, 200, 255)

DIM_IN_S = 0.2        # footage dims under a card
CARD_IN_S = 0.3
CARD_OUT_S = 0.2
COUNT_S = 0.4
RULE_S = 0.5
WORD_S = 0.12         # a source-card word darkens over this long
BACKDROP_BRIGHTNESS = 0.34
BACKDROP_SHRINK = 12  # blur by scaling the footage down by this factor and back up (cheap, moving, deterministic)

_ROOT = Path(__file__).resolve().parents[1]
_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def ramp(t: float, start: float, length: float) -> float:
    """0 before `start`, 1 after start + length, linear between."""
    if length <= 0:
        return 1.0 if t >= start else 0.0
    return min(1.0, max(0.0, (t - start) / length))


def font(kind: str, size: int):
    """heavy: Outfit ExtraBold (numbers, headlines) / bold: Inter Bold / serif: Cormorant Garamond Bold (source cards).
    Only fonts the app already ships. A condensed face (the reference uses Oswald-like type) is not bundled: see the style guide."""
    key = (kind, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    f = None
    try:
        if kind == "serif":
            f = ImageFont.truetype(str(_ROOT / "gfx-core" / "fonts" / "CormorantGaramond-VF.ttf"), size)
            f.set_variation_by_axes([700])
        else:
            name = {"heavy": "Outfit-ExtraBold.ttf", "bold": "Inter-Bold.ttf", "regular": "Inter-Regular.ttf"}[kind]
            f = ImageFont.truetype(str(_ROOT / "assets" / "fonts" / name), size)
    except (OSError, KeyError):
        f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def blank() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def fade(img: Image.Image, a: float) -> Image.Image:
    a = min(1.0, max(0.0, a))
    if a >= 0.999:
        return img
    r, g, b, al = img.split()
    return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * a))))


def card_alpha(t: float, dur: float) -> float:
    """Fade in over CARD_IN_S, out over CARD_OUT_S before `dur`."""
    return min(ramp(t, 0.0, CARD_IN_S), 1.0 - ramp(t, dur - CARD_OUT_S, CARD_OUT_S))


def spaced(d: ImageDraw.ImageDraw, xy, text: str, f, fill, spacing: float = 0.1) -> float:
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + f.size * spacing
    return x


def spaced_width(d: ImageDraw.ImageDraw, text: str, f, spacing: float = 0.1) -> float:
    return sum(d.textlength(ch, font=f) + f.size * spacing for ch in text)


def lerp_color(c0, c1, k: float):
    k = min(1.0, max(0.0, k))
    return tuple(int(round(a + (b - a) * k)) for a, b in zip(c0[:3], c1[:3])) + (255,)
