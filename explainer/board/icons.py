"""Eight flat code-drawn board icons (Milestone 1). Each is drawn in a 100 x 100 design space, flat role colour with a thin dark outline, at 4x and
reduced with LANCZOS, so the result is anti-aliased and deterministic. No files, no network, no generated art: the shapes are the art.

    icon_sprite("icon:drop", "blue", 160)  ->  RGBA Pillow image, 160 x 160

Ids: icon:drop, icon:person, icon:house, icon:coin, icon:gear, icon:document, icon:clock, icon:warning, plus the props from props.py (prop:*)."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Callable, Dict, Tuple

from PIL import Image, ImageDraw

from . import theme as T
from .props import PROPS

SS = 4      # supersampling factor


def _poly_gear(cx, cy, r_out, r_in, teeth):
    pts = []
    for i in range(teeth * 2):
        a0 = math.pi * 2 * i / (teeth * 2) - math.pi / (teeth * 2) / 2
        a1 = math.pi * 2 * (i + 1) / (teeth * 2) - math.pi / (teeth * 2) / 2
        r = r_out if i % 2 == 0 else r_in
        pts += [(cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1))]
    return pts


def _drop(d, c, o, w):
    d.ellipse([20, 40, 80, 96], fill=c)
    d.polygon([(50, 6), (78, 56), (22, 56)], fill=c)
    d.ellipse([20, 40, 80, 96], outline=o, width=w)
    d.polygon([(50, 6), (78, 56), (22, 56)], fill=c)
    d.ellipse([22, 44, 78, 94], fill=c)
    d.line([(50, 6), (23, 52)], fill=o, width=w)
    d.line([(50, 6), (77, 52)], fill=o, width=w)
    d.ellipse([30, 62, 42, 78], fill=(255, 255, 255))


def _person(d, c, o, w):
    d.ellipse([34, 8, 66, 40], fill=c, outline=o, width=w)
    d.rounded_rectangle([18, 46, 82, 96], radius=26, fill=c, outline=o, width=w)


def _house(d, c, o, w):
    d.rectangle([20, 46, 80, 92], fill=c, outline=o, width=w)
    d.polygon([(10, 48), (50, 12), (90, 48)], fill=(240, 232, 200), outline=o)
    d.line([(10, 48), (50, 12), (90, 48), (10, 48)], fill=o, width=w, joint="curve")
    d.rectangle([42, 62, 58, 92], fill=(240, 232, 200), outline=o, width=w)


def _coin(d, c, o, w):
    d.ellipse([8, 8, 92, 92], fill=c, outline=o, width=w)
    d.ellipse([22, 22, 78, 78], outline=o, width=w)
    d.line([(52, 32), (52, 68)], fill=o, width=w + 1)
    d.line([(42, 42), (52, 32)], fill=o, width=w + 1)


def _gear(d, c, o, w):
    d.polygon(_poly_gear(50, 50, 46, 34, 8), fill=c, outline=o)
    pts = _poly_gear(50, 50, 46, 34, 8)
    d.line(pts + [pts[0]], fill=o, width=w, joint="curve")
    d.ellipse([34, 34, 66, 66], fill=(192, 192, 192), outline=o, width=w)


def _document(d, c, o, w):
    d.polygon([(22, 6), (62, 6), (80, 24), (80, 94), (22, 94)], fill=(240, 232, 200))
    d.line([(22, 6), (62, 6), (80, 24), (80, 94), (22, 94), (22, 6)], fill=o, width=w, joint="curve")
    d.polygon([(62, 6), (62, 24), (80, 24)], fill=c, outline=o)
    for y in (42, 56, 70):
        d.line([(32, y), (70, y)], fill=o, width=w)


def _clock(d, c, o, w):
    d.ellipse([8, 8, 92, 92], fill=(250, 250, 250), outline=o, width=w)
    d.line([(50, 50), (50, 22)], fill=c, width=w + 3)
    d.line([(50, 50), (70, 60)], fill=c, width=w + 3)
    d.ellipse([44, 44, 56, 56], fill=o)


def _warning(d, c, o, w):
    pts = [(50, 8), (94, 88), (6, 88)]
    d.polygon(pts, fill=c)
    d.line(pts + [pts[0]], fill=o, width=w, joint="curve")
    d.line([(50, 36), (50, 64)], fill=o, width=w + 2)
    d.ellipse([45, 71, 55, 81], fill=o)


ICONS: Dict[str, Callable] = {"icon:drop": _drop, "icon:person": _person, "icon:house": _house, "icon:coin": _coin, "icon:gear": _gear,
                              "icon:document": _document, "icon:clock": _clock, "icon:warning": _warning}


ICONS.update(PROPS)                 # Milestone 2: the eight props are accepted wherever an icon asset is


def icon_ids() -> list:
    return sorted(ICONS)


@lru_cache(maxsize=256)
def icon_sprite(asset: str, role: str, px: int) -> Image.Image:
    fn = ICONS[asset]
    col = T.THEME.roles.get(role, T.THEME.roles["blue"])
    big = Image.new("RGBA", (100 * SS, 100 * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    # draw in design units by scaling every coordinate: wrap the drawing calls through a scaled proxy
    fn(_Scaled(d, SS), col, T.THEME.outline, 3)
    return big.resize((px, px), Image.LANCZOS)


class _Scaled:
    """Forwards Pillow draw calls with coordinates multiplied by `k` (so the icon functions can be written in a 100 x 100 space)."""

    def __init__(self, d: ImageDraw.ImageDraw, k: int):
        self.d, self.k = d, k

    def _pts(self, p):
        if isinstance(p, (list, tuple)) and p and isinstance(p[0], (list, tuple)):
            return [(x * self.k, y * self.k) for x, y in p]
        return [v * self.k for v in p]

    def _kw(self, kw):
        kw = dict(kw)
        if "width" in kw:
            kw["width"] = max(1, int(kw["width"] * self.k))
        return kw

    def polygon(self, pts, **kw):
        self.d.polygon(self._pts(pts), **{k: v for k, v in self._kw(kw).items() if k in ("fill", "outline")})

    def ellipse(self, box, **kw):
        self.d.ellipse(self._pts(box), **self._kw(kw))

    def rectangle(self, box, **kw):
        self.d.rectangle(self._pts(box), **self._kw(kw))

    def rounded_rectangle(self, box, radius=0, **kw):
        self.d.rounded_rectangle(self._pts(box), radius=radius * self.k, **self._kw(kw))

    def line(self, pts, **kw):
        self.d.line(self._pts(pts), **self._kw(kw))
