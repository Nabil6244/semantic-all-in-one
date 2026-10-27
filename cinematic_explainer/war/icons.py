"""Generic class silhouettes, editorial overlay helpers and trivial flags for the War Documentary style.

Silhouettes stand for a CLASS (tank, air defence, drone ...), never for a specific model. Everything is drawn with PIL primitives on a 4x
canvas and scaled down, so edges are antialiased and the result is identical on every run.

    draw_icon(class_id, size, colour)                  square RGBA silhouette (cached)
    CLASS_LABEL[class_id]                              the generic label shown when a model is not confirmed
    draw_arrow / draw_bracket / draw_circle_marker / draw_pin   antialiased editorial marks drawn onto an RGBA image
    draw_flag(code, size)                              (w, h) RGBA badge for a trivial stripe flag, or None for any other code
"""

from __future__ import annotations

import math
from typing import Callable, Dict, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

SS = 4

CLASS_LABEL: Dict[str, str] = {
    "tank": "TANK", "ifv": "INFANTRY FIGHTING VEHICLE", "apc": "ARMOURED PERSONNEL CARRIER", "artillery": "ARTILLERY",
    "rocket_artillery": "ROCKET ARTILLERY", "mortar": "MORTAR", "missile_ballistic": "BALLISTIC MISSILE",
    "missile_cruise": "CRUISE MISSILE", "air_defense": "AIR-DEFENCE SYSTEM", "interceptor": "INTERCEPTOR MISSILE",
    "drone": "UNCREWED AIRCRAFT", "fighter": "FIGHTER AIRCRAFT", "helicopter": "HELICOPTER", "bomber": "BOMBER AIRCRAFT",
    "ship": "NAVAL VESSEL", "radar": "RADAR", "ew": "ELECTRONIC WARFARE", "logistics": "LOGISTICS VEHICLE", "generic": "MILITARY EQUIPMENT",
    "institution": "INSTITUTION",
}

Colour = Tuple[int, int, int, int]
_ICON_CACHE: Dict[Tuple[str, int, Colour], Image.Image] = {}


# ---------------------------------------------------------------- silhouettes (0..100 coordinate box) ----------------------------------

def _wheel(d, cx, cy, r, c):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)


def _poly(d, pts, c):
    d.polygon(pts, fill=c)


def _rot(pts: Sequence[Tuple[float, float]], deg: float, cx: float = 50, cy: float = 50):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def _tank(d, c):
    d.rounded_rectangle([8, 64, 92, 82], radius=9, fill=c)
    for x in (18, 32, 46, 60, 74, 86):
        _wheel(d, x, 73, 4, (0, 0, 0, 0))
    d.rectangle([14, 52, 86, 66], fill=c)
    _poly(d, [(32, 52), (38, 36), (66, 36), (72, 52)], c)
    d.rectangle([66, 40, 99, 45], fill=c)


def _ifv(d, c):
    d.rounded_rectangle([8, 66, 90, 82], radius=8, fill=c)
    for x in (20, 36, 52, 68, 82):
        _wheel(d, x, 74, 3.5, (0, 0, 0, 0))
    _poly(d, [(8, 66), (14, 48), (74, 48), (92, 62), (92, 66)], c)
    _poly(d, [(38, 48), (42, 36), (62, 36), (66, 48)], c)
    d.rectangle([62, 40, 84, 43], fill=c)
    d.rectangle([22, 40, 30, 48], fill=c)


def _apc(d, c):
    _poly(d, [(6, 64), (10, 44), (66, 44), (86, 56), (94, 62), (94, 70), (6, 70)], c)
    for x in (22, 42, 64, 80):
        _wheel(d, x, 72, 9, c)
        _wheel(d, x, 72, 4, (0, 0, 0, 0))
    d.rectangle([40, 36, 56, 44], fill=c)
    d.rectangle([54, 38, 72, 41], fill=c)


def _artillery(d, c):
    d.rounded_rectangle([14, 62, 74, 76], radius=5, fill=c)
    for x in (24, 42, 60):
        _wheel(d, x, 78, 7, c)
        _wheel(d, x, 78, 3, (0, 0, 0, 0))
    _poly(d, [(36, 62), (42, 48), (60, 44), (62, 62)], c)
    _poly(d, _rot([(52, 42), (99, 42), (99, 47), (52, 47)], -18, 52, 45), c)


def _truck(d, c, x0=6, x1=94, base=66):
    _poly(d, [(x0, base), (x0, base - 20), (x0 + 16, base - 20), (x0 + 24, base - 10), (x0 + 26, base)], c)
    d.rectangle([x0 + 26, base - 6, x1, base + 4], fill=c)
    for x in (x0 + 12, x0 + 38, x0 + 56, x1 - 10):
        _wheel(d, x, base + 8, 8, c)
        _wheel(d, x, base + 8, 3.5, (0, 0, 0, 0))


def _rocket_artillery(d, c):
    _truck(d, c)
    rack = _rot([(34, 46), (90, 46), (90, 58), (34, 58)], -24, 34, 58)
    _poly(d, rack, c)
    for i in range(3):
        tube = _rot([(34, 49 + i * 4), (95, 49 + i * 4), (95, 51 + i * 4), (34, 51 + i * 4)], -24, 34, 58)
        _poly(d, tube, (0, 0, 0, 0))


def _mortar(d, c):
    d.ellipse([24, 80, 76, 92], fill=c)
    _poly(d, _rot([(46, 82), (54, 82), (54, 24), (46, 24)], 18, 50, 82), c)
    d.line([(52, 52), (24, 80)], fill=c, width=3)
    d.line([(56, 52), (80, 80)], fill=c, width=3)


def _missile_ballistic(d, c):
    _poly(d, [(42, 22), (50, 2), (58, 22)], c)
    d.rectangle([42, 22, 58, 78], fill=c)
    _poly(d, [(42, 62), (30, 86), (42, 78)], c)
    _poly(d, [(58, 62), (70, 86), (58, 78)], c)
    d.rectangle([44, 78, 56, 90], fill=c)
    d.rectangle([42, 40, 58, 43], fill=(0, 0, 0, 0))


def _missile_cruise(d, c):
    d.rounded_rectangle([8, 45, 86, 57], radius=6, fill=c)
    _poly(d, [(82, 45), (99, 51), (82, 57)], c)
    _poly(d, [(40, 45), (56, 45), (48, 33)], c)
    _poly(d, [(40, 57), (56, 57), (48, 69)], c)
    _poly(d, [(8, 45), (20, 45), (12, 35)], c)
    _poly(d, [(8, 57), (20, 57), (12, 67)], c)
    d.rectangle([58, 38, 70, 45], fill=c)


def _air_defense(d, c):
    _truck(d, c, 4, 74, 74)
    for i in range(4):
        tube = _rot([(36 + i * 11, 20), (46 + i * 11, 20), (46 + i * 11, 64), (36 + i * 11, 64)], -14, 52, 64)
        _poly(d, tube, c)
        cap = _rot([(36 + i * 11, 16), (46 + i * 11, 16), (46 + i * 11, 20), (36 + i * 11, 20)], -14, 52, 64)
        _poly(d, cap, (0, 0, 0, 0))
    d.rectangle([14, 36, 17, 56], fill=c)
    d.pieslice([4, 26, 28, 50], 120, 300, fill=c)


def _interceptor(d, c):
    parts = [[(30, 46), (84, 46), (84, 54), (30, 54)], [(84, 46), (98, 50), (84, 54)], [(38, 46), (48, 46), (36, 34)],
             [(38, 54), (48, 54), (36, 66)], [(70, 46), (76, 46), (70, 38)], [(70, 54), (76, 54), (70, 62)],
             [(30, 46), (30, 54), (14, 50)]]
    for q in parts:
        _poly(d, _rot(q, -38, 50, 50), c)
    for a, b in (((10, 44), (4, 44)), ((6, 52), (0, 52))):
        d.line(_rot([a, b], -38, 50, 50), fill=c, width=2)


def _drone(d, c):
    d.ellipse([40, 42, 60, 58], fill=c)
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        ex, ey = 50 + dx * 30, 50 + dy * 24
        d.line([(50, 50), (ex, ey)], fill=c, width=3)
        d.ellipse([ex - 12, ey - 5, ex + 12, ey + 5], outline=c, width=2)
        _wheel(d, ex, ey, 2.5, c)
    d.rectangle([46, 56, 54, 62], fill=c)


def _fighter(d, c):
    _poly(d, [(50, 2), (56, 24), (58, 66), (62, 88), (50, 82), (38, 88), (42, 66), (44, 24)], c)
    _poly(d, [(56, 36), (96, 66), (96, 72), (56, 62)], c)
    _poly(d, [(44, 36), (4, 66), (4, 72), (44, 62)], c)
    _poly(d, [(56, 74), (74, 90), (74, 94), (54, 86)], c)
    _poly(d, [(44, 74), (26, 90), (26, 94), (46, 86)], c)


def _helicopter(d, c):
    d.ellipse([22, 44, 70, 72], fill=c)
    d.rectangle([66, 50, 94, 56], fill=c)
    _poly(d, [(90, 38), (96, 38), (96, 62), (90, 56)], c)
    d.rectangle([14, 30, 84, 33], fill=c)
    d.rectangle([44, 33, 48, 44], fill=c)
    d.line([(24, 82), (68, 82)], fill=c, width=3)
    d.line([(34, 72), (34, 82)], fill=c, width=3)
    d.line([(58, 72), (58, 82)], fill=c, width=3)


def _bomber(d, c):
    _poly(d, [(50, 6), (55, 20), (56, 40), (98, 62), (98, 72), (56, 62), (55, 76), (62, 90), (62, 94), (50, 90),
              (38, 94), (38, 90), (45, 76), (44, 62), (2, 72), (2, 62), (44, 40), (45, 20)], c)
    for x in (24, 76):
        d.ellipse([x - 3, 54, x + 3, 66], fill=(0, 0, 0, 0))


def _ship(d, c):
    _poly(d, [(4, 62), (96, 62), (84, 80), (14, 80)], c)
    d.rectangle([30, 46, 70, 62], fill=c)
    d.rectangle([42, 34, 58, 46], fill=c)
    d.rectangle([49, 14, 51, 34], fill=c)
    d.rectangle([74, 54, 90, 57], fill=c)
    d.rectangle([12, 54, 26, 62], fill=c)


def _radar(d, c):
    d.pieslice([14, 14, 70, 70], 120, 300, fill=c)
    d.line([(42, 42), (74, 42)], fill=c, width=3)
    d.rectangle([62, 38, 68, 84], fill=c)
    d.rectangle([40, 82, 90, 90], fill=c)
    _wheel(d, 74, 42, 3, c)


def _ew(d, c):
    _truck(d, c, 4, 70, 74)
    d.rectangle([58, 22, 61, 66], fill=c)
    for r in (10, 18, 26):
        d.arc([60 - r, 22 - r, 60 + r, 22 + r], 200, 340, fill=c, width=3)
        d.arc([60 - r, 22 - r, 60 + r, 22 + r], 20, 160, fill=c, width=3)


def _logistics(d, c):
    _truck(d, c, 4, 94, 66)
    d.rectangle([32, 34, 94, 64], fill=c)
    d.line([(63, 34), (63, 64)], fill=(0, 0, 0, 0), width=2)


def _generic(d, c):
    for (x, y, sx, sy) in ((16, 16, 1, 1), (84, 16, -1, 1), (16, 84, 1, -1), (84, 84, -1, -1)):
        d.line([(x, y), (x + sx * 20, y)], fill=c, width=6)
        d.line([(x, y), (x, y + sy * 20)], fill=c, width=6)
    d.rectangle([38, 38, 62, 62], fill=c)


def _institution(d, c):
    _poly(d, [(8, 34), (50, 8), (92, 34)], c)
    d.rectangle([8, 36, 92, 42], fill=c)
    for x in (16, 34, 52, 70):
        d.rectangle([x, 46, x + 12, 80], fill=c)
    d.rectangle([6, 82, 94, 90], fill=c)


_DRAWERS: Dict[str, Callable] = {
    "tank": _tank, "ifv": _ifv, "apc": _apc, "artillery": _artillery, "rocket_artillery": _rocket_artillery, "mortar": _mortar,
    "missile_ballistic": _missile_ballistic, "missile_cruise": _missile_cruise, "air_defense": _air_defense, "interceptor": _interceptor,
    "drone": _drone, "fighter": _fighter, "helicopter": _helicopter, "bomber": _bomber, "ship": _ship, "radar": _radar, "ew": _ew,
    "logistics": _logistics, "generic": _generic, "institution": _institution,
}


def class_id(value: Optional[str]) -> str:
    v = str(value or "").strip().lower()
    return v if v in _DRAWERS else "generic"


def draw_icon(class_id_: str, size: int, colour: Colour = (236, 230, 214, 255)) -> Image.Image:
    """Square RGBA silhouette of a generic class. Unknown class ids give the generic marker."""
    cid = class_id(class_id_)
    size = max(8, int(size))
    key = (cid, size, tuple(colour))  # type: ignore[arg-type]
    hit = _ICON_CACHE.get(key)
    if hit is not None:
        return hit.copy()
    big = size * SS
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    scaled = _Scaled(ImageDraw.Draw(layer), big / 100.0)
    _DRAWERS[cid](scaled, tuple(colour))
    out = layer.resize((size, size), Image.LANCZOS)
    if len(_ICON_CACHE) > 128:
        _ICON_CACHE.clear()
    _ICON_CACHE[key] = out
    return out.copy()


class _Scaled:
    """ImageDraw wrapper that takes the 0..100 coordinate box and scales it up. Transparent fills erase (cut-outs)."""

    def __init__(self, draw: ImageDraw.ImageDraw, k: float):
        self._d, self._k = draw, k
        self._im = draw._image  # type: ignore[attr-defined]

    def _s(self, v):
        if isinstance(v, (int, float)):
            return v * self._k
        return [self._s(x) if not isinstance(x, tuple) else tuple(a * self._k for a in x) for x in v]

    def _fill(self, kw):
        fill = kw.get("fill")
        return fill

    def _erase(self, shape_fn):
        mask = Image.new("L", self._im.size, 0)
        shape_fn(ImageDraw.Draw(mask), 255)
        clear = Image.new("RGBA", self._im.size, (0, 0, 0, 0))
        self._im.paste(clear, (0, 0), mask)

    def _do(self, name: str, geom, kw):
        kw = dict(kw)
        fill = kw.get("fill")
        if isinstance(fill, tuple) and len(fill) == 4 and fill[3] == 0:
            def fn(dr, v):
                kw2 = dict(kw)
                kw2["fill"] = v
                if "outline" in kw2:
                    kw2["outline"] = v
                getattr(dr, name)(geom, **kw2)
            self._erase(fn)
        else:
            getattr(self._d, name)(geom, **kw)

    def polygon(self, pts, fill=None):
        self._do("polygon", [(x * self._k, y * self._k) for x, y in pts], {"fill": fill})

    def rectangle(self, box, fill=None, outline=None, width=1):
        self._do("rectangle", [v * self._k for v in box], {"fill": fill})

    def rounded_rectangle(self, box, radius=0, fill=None):
        self._do("rounded_rectangle", [v * self._k for v in box], {"radius": radius * self._k, "fill": fill})

    def ellipse(self, box, fill=None, outline=None, width=1):
        kw = {"fill": fill}
        if outline is not None:
            kw["outline"] = outline
            kw["width"] = max(1, int(width * self._k))
        self._do("ellipse", [v * self._k for v in box], kw)

    def pieslice(self, box, start, end, fill=None):
        self._do("pieslice", [v * self._k for v in box], {"start": start, "end": end, "fill": fill})

    def arc(self, box, start, end, fill=None, width=1):
        self._do("arc", [v * self._k for v in box], {"start": start, "end": end, "fill": fill, "width": max(1, int(width * self._k))})

    def line(self, pts, fill=None, width=1):
        self._do("line", [(x * self._k, y * self._k) for x, y in pts], {"fill": fill, "width": max(1, int(width * self._k))})


# ---------------------------------------------------------------- editorial overlay helpers (antialiased, drawn onto an RGBA image) -----

def _local(img: Image.Image, bbox: Tuple[float, float, float, float], pad: int, painter: Callable[[ImageDraw.ImageDraw, float, float], None]):
    x0 = int(max(0, math.floor(bbox[0]) - pad))
    y0 = int(max(0, math.floor(bbox[1]) - pad))
    x1 = int(min(img.width, math.ceil(bbox[2]) + pad))
    y1 = int(min(img.height, math.ceil(bbox[3]) + pad))
    if x1 <= x0 or y1 <= y0:
        return
    w, h = x1 - x0, y1 - y0
    layer = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    painter(ImageDraw.Draw(layer), x0, y0)
    small = layer.resize((w, h), Image.LANCZOS)
    region = img.crop((x0, y0, x1, y1))
    img.paste(Image.alpha_composite(region, small), (x0, y0))


def draw_arrow(img: Image.Image, p0, p1, colour: Colour, width: float = 4, head: float = 16, progress: float = 1.0, dashed: bool = False) -> None:
    """Arrow from p0 to p1; `progress` (0..1) draws it on; the head appears when the shaft is complete."""
    progress = min(1.0, max(0.0, progress))
    if progress <= 0:
        return
    x0, y0 = p0
    x1, y1 = p1
    ex, ey = x0 + (x1 - x0) * progress, y0 + (y1 - y0) * progress
    ang = math.atan2(y1 - y0, x1 - x0)
    pad = int(head + width + 2)

    def paint(d, ox, oy):
        s = lambda x, y: ((x - ox) * SS, (y - oy) * SS)
        if dashed:
            length = math.hypot(ex - x0, ey - y0)
            n = int(length // 14)
            for i in range(n + 1):
                a = i * 14
                b = min(length, a + 8)
                ux, uy = math.cos(ang), math.sin(ang)
                d.line([s(x0 + ux * a, y0 + uy * a), s(x0 + ux * b, y0 + uy * b)], fill=colour, width=int(width * SS))
        else:
            d.line([s(x0, y0), s(ex, ey)], fill=colour, width=int(width * SS))
        if progress >= 0.999:
            hx = [(x1, y1), (x1 - head * math.cos(ang - 0.45), y1 - head * math.sin(ang - 0.45)),
                  (x1 - head * math.cos(ang + 0.45), y1 - head * math.sin(ang + 0.45))]
            d.polygon([s(*p) for p in hx], fill=colour)

    _local(img, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), pad, paint)


def draw_bracket(img: Image.Image, box, colour: Colour, width: float = 3, arm: float = 22, progress: float = 1.0) -> None:
    """Four corner brackets around box (x0, y0, x1, y1); progress grows the arms."""
    progress = min(1.0, max(0.0, progress))
    if progress <= 0:
        return
    x0, y0, x1, y1 = box
    a = arm * progress

    def paint(d, ox, oy):
        s = lambda x, y: ((x - ox) * SS, (y - oy) * SS)
        for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            d.line([s(cx + sx * a, cy), s(cx, cy), s(cx, cy + sy * a)], fill=colour, width=int(width * SS), joint="curve")

    _local(img, box, int(width) + 3, paint)


def draw_circle_marker(img: Image.Image, centre, r: float, colour: Colour, width: float = 3, fill: Optional[Colour] = None) -> None:
    cx, cy = centre

    def paint(d, ox, oy):
        bb = [(cx - r - ox) * SS, (cy - r - oy) * SS, (cx + r - ox) * SS, (cy + r - oy) * SS]
        if fill:
            d.ellipse(bb, fill=fill)
        d.ellipse(bb, outline=colour, width=max(1, int(width * SS)))

    _local(img, (cx - r, cy - r, cx + r, cy + r), int(width) + 3, paint)


def draw_pin(img: Image.Image, tip, colour: Colour, size: float = 30, ring: Optional[Colour] = (10, 12, 16, 255)) -> None:
    """Location pin whose point sits on `tip` (x, y)."""
    tx, ty = tip
    r = size * 0.36
    cy = ty - size * 0.64

    def paint(d, ox, oy):
        s = lambda x, y: ((x - ox) * SS, (y - oy) * SS)
        d.polygon([s(tx, ty), s(tx - r * 0.86, cy + r * 0.5), s(tx + r * 0.86, cy + r * 0.5)], fill=colour)
        d.ellipse([(tx - r - ox) * SS, (cy - r - oy) * SS, (tx + r - ox) * SS, (cy + r - oy) * SS], fill=colour)
        if ring:
            q = r * 0.42
            d.ellipse([(tx - q - ox) * SS, (cy - q - oy) * SS, (tx + q - ox) * SS, (cy + q - oy) * SS], fill=ring)

    _local(img, (tx - r, cy - r, tx + r, ty), 3, paint)


# ---------------------------------------------------------------- flags: trivial stripe flags only; no emblems --------------------------

# code -> (orientation, stripe colours, optional weights)
_FLAGS: Dict[str, Tuple[str, Sequence[Tuple[int, int, int]], Optional[Sequence[int]]]] = {
    "UA": ("h", [(0, 91, 187), (255, 213, 0)], None),
    "RU": ("h", [(255, 255, 255), (0, 57, 166), (213, 43, 30)], None),
    "DE": ("h", [(0, 0, 0), (221, 0, 0), (255, 206, 0)], None),
    "NL": ("h", [(174, 28, 40), (255, 255, 255), (33, 70, 139)], None),
    "PL": ("h", [(255, 255, 255), (220, 20, 60)], None),
    "LT": ("h", [(253, 185, 19), (0, 106, 68), (193, 39, 45)], None),
    "LV": ("h", [(158, 48, 57), (255, 255, 255), (158, 48, 57)], [2, 1, 2]),
    "EE": ("h", [(0, 114, 206), (0, 0, 0), (255, 255, 255)], None),
    "HU": ("h", [(205, 42, 62), (255, 255, 255), (67, 111, 77)], None),
    "BG": ("h", [(255, 255, 255), (0, 150, 110), (214, 38, 18)], None),
    "FR": ("v", [(0, 85, 164), (255, 255, 255), (239, 65, 53)], None),
    "IT": ("v", [(0, 146, 70), (255, 255, 255), (206, 43, 55)], None),
    "RO": ("v", [(0, 43, 127), (252, 209, 22), (206, 17, 38)], None),
}


def draw_flag(code: str, size: int = 64) -> Optional[Image.Image]:
    """Badge of a plain stripe flag, `size` wide (3:2). None for every code that is not a trivial stripe flag (no emblems are drawn)."""
    spec = _FLAGS.get(str(code or "").strip().upper())
    if spec is None:
        return None
    orient, cols, weights = spec
    w = max(12, int(size))
    h = int(w * 2 / 3)
    big_w, big_h = w * SS, h * SS
    im = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    wts = list(weights or [1] * len(cols))
    total = sum(wts)
    pos = 0.0
    for col, wt in zip(cols, wts):
        span = (big_h if orient == "h" else big_w) * wt / total
        if orient == "h":
            d.rectangle([0, round(pos), big_w, round(pos + span)], fill=col + (255,))
        else:
            d.rectangle([round(pos), 0, round(pos + span), big_h], fill=col + (255,))
        pos += span
    d.rectangle([0, 0, big_w - 1, big_h - 1], outline=(10, 12, 16, 255), width=SS)
    return im.resize((w, h), Image.LANCZOS)
