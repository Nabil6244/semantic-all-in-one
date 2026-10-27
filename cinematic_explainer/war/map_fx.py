"""Depth, light and context effects for the tactical map (maps_tactical.py): pure functions, deterministic, cached statics.

  LOOKS / pal(look)          palettes: night (default), blueprint, table (mid-tone briefing table)
  shade_coast(img, sea, ...) coastline rim light on land and a lighter continental shelf in the sea (no invented terrain: only the coast shapes
                             already in the Natural Earth outlines drive it)
  spotlight(img, cx, cy)     darkens everything away from the subject so the named places carry the frame
  grain(img, frame)          fine animated film grain (deterministic per frame index)
  locator(...)               small corner map of the wider theatre with the current frame outlined

Honesty: nothing here draws terrain, frontlines or positions; it only changes light, contrast and framing.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import geo_data as G
from . import maps as MP

LOOKS = ("night", "blueprint", "table")

_PAL: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "night": {"sea": (13, 19, 27), "land": (36, 41, 48), "neigh": (31, 35, 42), "border": (118, 128, 142), "obl": (60, 68, 80), "river": (84, 138, 196),
              "rim": (96, 150, 206), "shelf": (30, 52, 78)},
    "blueprint": {"sea": (8, 22, 44), "land": (16, 46, 82), "neigh": (13, 37, 68), "border": (122, 180, 232), "obl": (40, 88, 138), "river": (130, 196, 244),
                  "rim": (120, 190, 250), "shelf": (22, 60, 104)},
    "table": {"sea": (44, 60, 74), "land": (98, 106, 94), "neigh": (80, 88, 82), "border": (198, 204, 192), "obl": (126, 134, 120), "river": (112, 164, 204),
             "rim": (214, 220, 204), "shelf": (66, 88, 106)},
}


def pal(look: Any) -> Dict[str, Tuple[int, int, int]]:
    return _PAL.get(str(look or "night"), _PAL["night"])


def shade_coast(img: Image.Image, sea: Tuple[int, int, int], look: str = "night", tol: int = 10) -> Image.Image:
    """Rim light along every coast (land side) and a lighter shelf in the sea near land. One pass per cached mosaic."""
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    sea_mask = (np.abs(arr - np.array(sea, dtype=np.int16)).sum(axis=2) <= tol)
    w, h = img.size
    k = 3 if w > 2400 else 2
    sm = Image.fromarray((sea_mask * 255).astype(np.uint8)).resize((max(1, w // k), max(1, h // k)), Image.BILINEAR)
    rim_r = 2.2
    shelf_r = 14.0
    land_blur = np.asarray(sm.filter(ImageFilter.GaussianBlur(rim_r)).resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0   # sea fraction near a point
    sea_far = np.asarray(sm.filter(ImageFilter.GaussianBlur(shelf_r)).resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0
    p = pal(look)
    out = arr.astype(np.float32)
    land = (~sea_mask)[..., None]
    rim = (np.clip(land_blur * 1.25, 0, 1) * (~sea_mask))[..., None]
    out += rim * (np.array(p["rim"], dtype=np.float32) - out) * 0.55 * land                         # soft light edge on the land side of a coast
    shelf = (np.clip(1.0 - sea_far * 1.0, 0, 1) * sea_mask)[..., None]                                # sea pixels with land within ~ shelf_r px
    out += shelf * (np.array(p["shelf"], dtype=np.float32) - out) * 0.85
    inner = (np.clip(1.0 - land_blur, 0, 1))[..., None] * land                                        # a hair of lift away from the coast: land reads as a surface
    out += inner * 3.0
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


_SPOT: Dict[Tuple[int, int, int, int], Image.Image] = {}


def spotlight(img: Image.Image, cx: float, cy: float, r0: float = 330.0, r1: float = 820.0, strength: float = 0.38) -> Image.Image:
    """Darken the map away from (cx, cy): clear inside r0, `strength` black beyond r1."""
    w, h = img.size
    key = (w, h, int(r0), int(r1))
    big = _SPOT.get(key)
    if big is None:
        yy, xx = np.mgrid[0:2 * h:2, 0:2 * w:2].astype(np.float32)      # half-resolution gradient, scaled up (it is smooth)
        r = np.hypot(xx - w, yy - h)
        a = np.clip((r - r0) / max(1.0, r1 - r0), 0, 1)
        a = a * a * (3 - 2 * a)
        big = Image.fromarray((a * 255).astype(np.uint8), "L").resize((2 * w, 2 * h), Image.BILINEAR)
        _SPOT[key] = big
    cx = int(max(0, min(w, cx)))
    cy = int(max(0, min(h, cy)))
    m = big.crop((w - cx, h - cy, 2 * w - cx, 2 * h - cy)).point(lambda v: int(v * strength))
    return Image.composite(Image.new(img.mode, img.size, (0, 0, 0, 255) if img.mode == "RGBA" else (0, 0, 0)), img, m)


_NOISE: Optional[np.ndarray] = None


def grain(img: Image.Image, frame: int, amount: float = 5.0) -> Image.Image:
    """Fine film grain: a fixed noise field sampled at a per-frame offset (deterministic)."""
    global _NOISE
    w, h = img.size
    if _NOISE is None or _NOISE.shape[0] < h * 2:
        rng = np.random.RandomState(20241027)
        _NOISE = (rng.standard_normal((h * 2, w * 2)) * amount).astype(np.float32)
    ox = (frame * 37) % w
    oy = (frame * 53) % h
    n = _NOISE[oy:oy + h, ox:ox + w]
    a = np.asarray(img.convert("RGB"), dtype=np.float32) + n[..., None]
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    return out.convert(img.mode)


# ------------------------------------------------------------------------------------------------ locator inset ---------------------------
LOC_W, LOC_H = 176, 112
_LOC: Dict[str, Tuple[Image.Image, MP.View]] = {}


def _locator_base(look: str, theme: str) -> Tuple[Image.Image, MP.View]:
    key = f"{look}:{theme}"
    if key in _LOC:
        return _LOC[key]
    p = pal(look)
    pol = theme == "political"
    v = MP.View(math.radians(31.0), G.merc(52.0), math.radians(40.0), LOC_W, LOC_H)
    ss = 3
    sea = (10, 22, 52) if pol else p["sea"]
    big = Image.new("RGBA", (LOC_W * ss, LOC_H * ss), sea + (255,))
    d = ImageDraw.Draw(big)
    vb = v.bounds()
    for f in G.countries():
        hi = f.iso in ("UKR", "RUS", "BLR")
        fill = (p["land"] if hi else p["neigh"]) if not pol else (52, 58, 74)
        MP._draw_feature(d, f, v, vb, fill + (255,), (p["border"] if not pol else (150, 156, 170)) + (255,), sea + (255,), ss, 1)
    img = big.reduce(ss).convert("RGB")
    _LOC[key] = (img, v)
    return img, v


def locator(img: Image.Image, view: MP.View, look: str, theme: str, pts: Sequence[Tuple[float, float]], x: int, y: int, k: float,
            accent=(246, 196, 52)) -> Optional[Tuple[int, int, int, int]]:
    """Draws the corner locator at (x, y) (top-left), fading in with k; returns its rectangle (for label placement) or None when the frame is as wide
    as the locator itself (it would add nothing)."""
    if view.lon_span >= 58.0 or k <= 0:
        return None
    base, lv = _locator_base(look, theme)
    lay = base.convert("RGBA")
    d = ImageDraw.Draw(lay)
    vb = view.bounds()
    x0, y0 = lv.px(vb[0], G.merc(vb[3]))
    x1, y1 = lv.px(vb[2], G.merc(vb[1]))
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    if x1 - x0 < 8:
        c = (x0 + x1) / 2
        x0, x1 = c - 4, c + 4
    if y1 - y0 < 6:
        c = (y0 + y1) / 2
        y0, y1 = c - 3, c + 3
    d.rectangle([x0, y0, x1, y1], outline=accent + (255,), width=2)
    for la, lo in pts:
        px, py = lv.pt(la, lo)
        d.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(255, 255, 255, 255))
    d.rectangle([0, 0, LOC_W - 1, LOC_H - 1], outline=(170, 176, 186, 255), width=1)
    if k < 1.0:
        lay.putalpha(Image.new("L", lay.size, int(255 * k)))
    img.alpha_composite(lay, (x, y))
    return (x, y, x + LOC_W, y + LOC_H)
