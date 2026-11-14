"""The ocean sets (docs/ocean/PATTERNS.md section 3). Each one is a full-frame RGBA picture that is never still: god rays sway,
specks drift and kelp bends, so a long stretch on one set still moves.

    draw(name, t, args=None, w=W, h=H) -> RGBA w x h

Sets (args in brackets, all optional):
    open_water     the home stage: surface-lit gradient, rays, drifting specks
    surface        grey sky, a dark island / coast on the horizon, the water line, water below   [horizon 0..1, island bool]
    seafloor       shallow side view: water, a white foam line, sand with pebbles                 [sand_y 0..1]
    kelp           open water with swaying kelp stalks rising from the bottom                     [count]
    abyss          near-black deep with a purple glow and slow falling marine snow
    depth_column   darkening water with a depth ruler and labelled marks                          [marks [[m, label]], max_m]
    split_columns  two water columns side by side with a title over each                          [left/right {label, color}]
    dark           near-black cold water: what is there is seen only where the diver's torch points (ocean/stage.py)
    ice_hole       under sea ice: a dark ceiling with one bright square hole and its light shaft     [hole_x 0..1]
    savanna        land stories: dusk sky, low sun glow, acacia silhouettes, dry grass ground (animals stand on it)
    savanna_night  the same plain at night: deep blue sky, moon, stars, dark grass
    burrow         cross-section of the ground: a strip of grass on top, earth layers and a tunnel below
An unknown name draws open_water: a set never fails and never goes flat.
Static parts are drawn once per (set, args, size) and cached; moving parts are quantised to PHASES steps per cycle and cached,
so a frame is a couple of pastes plus a few dozen specks.
"""

from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from . import look as L

W, H = L.W, L.H
SETS = ("open_water", "surface", "seafloor", "kelp", "abyss", "depth_column", "split_columns", "dark", "ice_hole", "savanna",
        "savanna_night", "burrow", "plain")
LAND_SETS = ("savanna", "savanna_night", "burrow")
GROUND_Y = 0.80                    # the land sets' ground line (fraction of the height): animals stand on it
PHASES = 32
RAY_CYCLE_S = 14.0
KELP_CYCLE_S = 6.0
_RAY_SETS = ("open_water", "surface", "seafloor", "kelp", "depth_column")


# ------------------------------------------------------------------------------------------------------------------ helpers

def _vgrad(w: int, h: int, stops: Sequence[Tuple[float, Tuple[int, ...]]]) -> Image.Image:
    """Vertical gradient through (position 0..1, colour) stops."""
    col = Image.new("RGBA", (1, h))
    px = col.load()
    for y in range(h):
        f = y / max(1, h - 1)
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if a <= f <= b:
                k = 0.0 if b == a else (f - a) / (b - a)
                px[0, y] = tuple(int(round(ca[i] + (cb[i] - ca[i]) * k)) for i in range(3)) + (255,)
                break
        else:
            px[0, y] = tuple(stops[-1][1][:3]) + (255,)
    return col.resize((w, h), Image.NEAREST)


def _water(w: int, h: int, top: float = 0.0) -> Image.Image:
    return _vgrad(w, h, [(0.0, L.WATER_TOP), (top + (1 - top) * 0.45, L.WATER_MID), (1.0, L.WATER_DEEP)])


def _vignette(img: Image.Image, strength: int = 120) -> Image.Image:
    w, h = img.size
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).ellipse((-w * 0.15, -h * 0.25, w * 1.15, h * 1.2), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(w * 0.08)).point(lambda v: (255 - v) * strength // 255)
    out = img.copy()
    out.paste((0, 0, 0, 255), (0, 0), m)
    return out


def _font(role: str, size: int):
    return L.font(role, size)


def _args(args: Optional[Dict[str, Any]]) -> str:
    return json.dumps(args or {}, sort_keys=True, default=str)


# ------------------------------------------------------------------------------------------------------------------ static bases

def _island_poly(w: int, horizon: int, seed: int = 7) -> List[Tuple[float, float]]:
    rnd = random.Random(seed)
    x0, x1 = w * 0.08, w * 0.62
    pts = [(x0, horizon)]
    n = 14
    peak = w * 0.055
    for i in range(1, n):
        x = x0 + (x1 - x0) * i / n
        bump = math.sin(math.pi * i / n) ** 0.7
        pts.append((x, horizon - peak * bump * (0.65 + 0.5 * rnd.random())))
    pts.append((x1, horizon))
    return pts


def _base_surface(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    hy = int(h * float(a.get("horizon", 0.34)))
    img = _water(w, h)
    sky = _vgrad(w, hy, [(0.0, L.SKY_TOP), (1.0, L.SKY_LOW)])
    img.paste(sky, (0, 0))
    d = ImageDraw.Draw(img)
    if a.get("island", True):
        d.polygon(_island_poly(w, hy), fill=L.ISLAND)
    under = _vgrad(w, h - hy, [(0.0, (60, 116, 140, 255)), (0.4, L.WATER_MID), (1.0, L.WATER_DEEP)])
    img.paste(under, (0, hy))
    d.rectangle((0, hy - 1, w, hy + max(2, int(3 * L.scale()))), fill=(226, 236, 240, 255))
    return img


def _base_seafloor(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    sy = h * float(a.get("sand_y", 0.62))
    img = _water(w, h)
    d = ImageDraw.Draw(img)
    amp, wl = h * 0.018, w / 7.0
    edge = [(x, sy + amp * math.sin(2 * math.pi * x / wl)) for x in range(0, w + 8, 8)]
    sand = _vgrad(w, h, [(0.0, L.SAND_TOP), (1.0, L.SAND_LOW)])
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(edge + [(w, h), (0, h)], fill=255)
    img.paste(sand, (0, 0), mask)
    foam = max(3, int(6 * L.scale()))
    d.line(edge, fill=(244, 246, 246, 255), width=foam)
    d.line([(x, y - foam * 1.6) for x, y in edge], fill=(190, 224, 232, 140), width=max(1, foam // 2))
    rnd = random.Random(11)
    for _ in range(26):
        x, y = rnd.uniform(0, w), rnd.uniform(sy + h * 0.06, h * 0.98)
        r = rnd.uniform(1.5, 4.0) * L.scale()
        d.ellipse((x - r * 1.4, y - r, x + r * 1.4, y + r), fill=(150, 116, 76, 255))
    return img


def _base_abyss(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    img = _vgrad(w, h, [(0.0, L.ABYSS_TOP), (1.0, L.ABYSS_DEEP)])
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((w * 0.2, h * 0.15, w * 0.8, h * 0.95), fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.12)).point(lambda v: v * 90 // 255)
    img.paste(L.ABYSS_TINT, (0, 0), glow)
    return img


def _base_depth_column(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    img = _vgrad(w, h, [(0.0, L.WATER_TOP), (0.5, L.WATER_MID), (1.0, L.ABYSS_DEEP)])
    sc = L.scale()
    d = ImageDraw.Draw(img)
    marks = a.get("marks") or [[0, "surface"], [200, ""], [500, "500 m"], [1000, "1,000 m"]]
    max_m = float(a.get("max_m") or max([float(m[0]) for m in marks] + [1.0]) * 1.1)
    x = w * float(a.get("ruler_x", 0.3))
    top, bot = h * 0.06, h * 0.96
    d.line((x, top, x, bot), fill=(220, 230, 236, 200), width=max(1, int(2 * sc)))
    f = _font("body", 18)
    for m in marks:
        y = top + (bot - top) * min(1.0, float(m[0]) / max_m)
        d.line((x - 10 * sc, y, x + 10 * sc, y), fill=(230, 236, 240, 230), width=max(1, int(2 * sc)))
        label = str(m[1] if len(m) > 1 else "")
        if label:
            tw = d.textlength(label, font=f)
            d.text((x - 18 * sc - tw, y - f.size * 0.6), label, font=f, fill=L.SOFT)
    return img


def _base_split(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    img = _vgrad(w, h, [(0.0, (10, 24, 36, 255)), (1.0, L.WATER_DEEP)])
    sc = L.scale()
    d = ImageDraw.Draw(img)
    f = _font("title", 26)
    sides = [a.get("left") or {"label": ""}, a.get("right") or {"label": ""}]
    cw, top, bot = w * 0.3, h * 0.2, h * 0.9
    for i, side in enumerate(sides):
        cx = w * (0.29 if i == 0 else 0.71)
        x0, x1 = cx - cw / 2, cx + cw / 2
        c = tuple(side.get("color") or L.WATER_TOP)
        col = _vgrad(int(cw), int(bot - top), [(0.0, c), (0.35, L.WATER_MID), (1.0, L.WATER_DEEP)])
        m = Image.new("L", col.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, col.width - 1, col.height - 1), radius=int(10 * sc), fill=255)
        img.paste(col, (int(x0), int(top)), m)
        lab = str(side.get("label", "")).upper()
        if lab:
            tw = d.textlength(lab, font=f)
            d.text((cx - tw / 2, top - f.size * 1.6), lab, font=f, fill=L.WHITE)
        _ = x1
    return img


def _base_dark(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    return _vgrad(w, h, [(0.0, (12, 22, 30, 255)), (0.5, (6, 12, 18, 255)), (1.0, (2, 4, 8, 255))])


def _base_ice_hole(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    img = _vgrad(w, h, [(0.0, (16, 30, 40, 255)), (0.45, (7, 14, 20, 255)), (1.0, (2, 4, 8, 255))])
    sc = L.scale()
    ice = int(h * 0.075)
    d = ImageDraw.Draw(img)
    rnd = random.Random(4)
    edge = [(x, ice + rnd.uniform(-4, 6) * sc) for x in range(0, w + 16, 16)]
    d.polygon([(0, 0), (w, 0)] + edge[::-1], fill=(150, 170, 182, 255))
    d.line(edge, fill=(196, 214, 222, 255), width=max(2, int(3 * sc)))
    hx = w * float(a.get("hole_x", 0.5))
    hw = w * 0.07
    shaft = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shaft).polygon([(hx - hw / 2, ice), (hx + hw / 2, ice), (hx + hw * 1.1, h), (hx - hw * 1.1, h)], fill=200)
    shaft = shaft.filter(ImageFilter.GaussianBlur(w * 0.02))
    from PIL import ImageChops
    shaft = ImageChops.multiply(shaft, Image.linear_gradient("L").resize((w, h)).point(lambda v: 255 - int(v * 0.85)))
    img.paste((214, 236, 246, 255), (0, 0), shaft)
    d = ImageDraw.Draw(img)
    d.rectangle((hx - hw / 2, 0, hx + hw / 2, ice + 2 * sc), fill=(250, 252, 255, 255))
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((hx - hw * 1.6, -ice, hx + hw * 1.6, ice * 2.6), fill=255)
    img.paste((240, 248, 255, 255), (0, 0), glow.filter(ImageFilter.GaussianBlur(w * 0.02)).point(lambda v: v * 150 // 255))
    return img


def _acacia(d: ImageDraw.ImageDraw, x: float, gy: float, s: float, col) -> None:
    d.line((x, gy, x + 4 * s, gy - 60 * s), fill=col, width=max(2, int(5 * s)))
    d.line((x + 4 * s, gy - 60 * s, x - 22 * s, gy - 84 * s), fill=col, width=max(2, int(3 * s)))
    d.line((x + 4 * s, gy - 60 * s, x + 30 * s, gy - 88 * s), fill=col, width=max(2, int(3 * s)))
    d.ellipse((x - 70 * s, gy - 104 * s, x + 80 * s, gy - 78 * s), fill=col)


def _base_savanna(w: int, h: int, a: Dict[str, Any], night: bool = False) -> Image.Image:
    sc = L.scale()
    gy = int(h * GROUND_Y)
    if night:
        img = _vgrad(w, h, [(0.0, (6, 10, 24, 255)), (GROUND_Y, (22, 30, 52, 255)), (1.0, (6, 8, 12, 255))])
    else:
        img = _vgrad(w, h, [(0.0, (40, 36, 48, 255)), (0.45, (150, 92, 58, 255)), (GROUND_Y, (226, 150, 82, 255)),
                            (1.0, (30, 22, 16, 255))])
    d = ImageDraw.Draw(img)
    rnd = random.Random(9)
    if night:
        for _ in range(140):
            x, y = rnd.uniform(0, w), rnd.uniform(0, gy * 0.8)
            r = rnd.uniform(0.6, 1.8) * sc
            d.ellipse((x - r, y - r, x + r, y + r), fill=(230, 236, 250, rnd.randint(90, 220)))
        mx, my, mr = w * 0.78, h * 0.18, 34 * sc
        glow = Image.new("L", (w, h), 0)
        ImageDraw.Draw(glow).ellipse((mx - mr * 3, my - mr * 3, mx + mr * 3, my + mr * 3), fill=90)
        img.paste((180, 196, 230, 255), (0, 0), glow.filter(ImageFilter.GaussianBlur(w * 0.03)))
        d = ImageDraw.Draw(img)
        d.ellipse((mx - mr, my - mr, mx + mr, my + mr), fill=(236, 238, 226, 255))
    else:
        sx, sy, sr = w * 0.68, gy - 30 * sc, 70 * sc
        glow = Image.new("L", (w, h), 0)
        ImageDraw.Draw(glow).ellipse((sx - sr * 4, sy - sr * 2.5, sx + sr * 4, sy + sr * 2.5), fill=150)
        img.paste((255, 196, 120, 255), (0, 0), glow.filter(ImageFilter.GaussianBlur(w * 0.05)))
        d = ImageDraw.Draw(img)
        d.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(255, 226, 170, 255))
    far = (24, 22, 30, 255) if night else (70, 42, 34, 255)
    hills = [(x, gy - 18 * sc - 22 * sc * math.sin(x / w * 5.0 + 1.3) ** 2) for x in range(0, w + 20, 20)]
    d.polygon(hills + [(w, gy), (0, gy)], fill=far)
    for x, s_ in ((w * 0.12, 0.9), (w * 0.4, 0.6), (w * 0.9, 1.1), (w * 0.57, 0.45)):
        _acacia(d, x, gy - 6 * sc, s_ * sc, (14, 12, 16, 255) if night else (40, 24, 20, 255))
    ground = _vgrad(w, h - gy, [(0.0, (34, 34, 30, 255) if night else (150, 104, 56, 255)),
                                (1.0, (8, 8, 8, 255) if night else (54, 34, 20, 255))])
    img.paste(ground, (0, gy))
    d = ImageDraw.Draw(img)
    for _ in range(420):                                     # dry grass tufts along the ground line
        x = rnd.uniform(0, w)
        y = gy + rnd.uniform(-2, h - gy) ** 1.0 * rnd.random() * 0.5
        l = rnd.uniform(6, 18) * sc
        c = (52, 50, 42, 255) if night else (rnd.randint(170, 210), rnd.randint(120, 150), rnd.randint(60, 80), 255)
        d.line((x, y, x + rnd.uniform(-4, 4) * sc, y - l), fill=c, width=max(1, int(sc)))
    return img


def _base_savanna_night(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    return _base_savanna(w, h, a, night=True)


def _base_burrow(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    sc = L.scale()
    top = int(h * 0.24)
    img = _vgrad(w, h, [(0.0, (60, 46, 52, 255)), (0.2, (170, 104, 64, 255)), (0.24, (110, 74, 44, 255)),
                        (0.6, (70, 46, 28, 255)), (1.0, (30, 20, 12, 255))])
    d = ImageDraw.Draw(img)
    rnd = random.Random(12)
    for i in range(5):                                       # earth layers
        y = top + (h - top) * (0.15 + i * 0.18)
        pts = [(x, y + 8 * sc * math.sin(x / w * 7 + i)) for x in range(0, w + 20, 20)]
        d.line(pts, fill=(52, 34, 20, 255), width=max(2, int(3 * sc)))
    for _ in range(90):
        x, y, r = rnd.uniform(0, w), rnd.uniform(top + 10, h), rnd.uniform(2, 7) * sc
        d.ellipse((x - r, y - r * 0.7, x + r, y + r * 0.7), fill=(96, 70, 48, 255))
    tunnel = [(w * 0.08, top), (w * 0.2, h * 0.5), (w * 0.45, h * 0.66), (w * 0.75, h * 0.7), (w * 0.88, h * 0.62)]
    d.line(tunnel, fill=(26, 16, 10, 255), width=int(70 * sc), joint="curve")
    d.ellipse((w * 0.7, h * 0.56, w * 0.95, h * 0.82), fill=(26, 16, 10, 255))
    for _ in range(160):
        x = rnd.uniform(0, w)
        d.line((x, top, x + rnd.uniform(-3, 3) * sc, top - rnd.uniform(6, 16) * sc), fill=(196, 150, 80, 255), width=max(1, int(sc)))
    return img


def _base_plain(w: int, h: int, a: Dict[str, Any]) -> Image.Image:
    """The graphics' backdrop in beat mode: a calm dark gradient, nothing moving behind the numbers."""
    return _vgrad(w, h, [(0.0, (16, 26, 36, 255)), (0.6, (9, 15, 22, 255)), (1.0, (4, 7, 11, 255))])


_BASES = {"plain": _base_plain, "savanna": _base_savanna, "savanna_night": _base_savanna_night, "burrow": _base_burrow, "dark": _base_dark, "ice_hole": _base_ice_hole, "surface": _base_surface, "seafloor": _base_seafloor, "abyss": _base_abyss,
          "depth_column": _base_depth_column, "split_columns": _base_split}


@lru_cache(maxsize=24)
def _base(name: str, akey: str, w: int, h: int) -> Image.Image:
    a = json.loads(akey)
    fn = _BASES.get(name)
    img = fn(w, h, a) if fn else _water(w, h)
    return _vignette(img, 190 if name in ("abyss", "dark", "ice_hole", "savanna_night") else 165)      # heavy edge darkening: the documentary look


# ------------------------------------------------------------------------------------------------------------------ moving parts

def _phase(t: float, cycle: float) -> int:
    return int((t % cycle) / cycle * PHASES) % PHASES


@lru_cache(maxsize=PHASES * 2)
def _rays(w: int, h: int, ph: int, depth: float) -> Image.Image:
    """Soft wedges of light from the surface, swaying; depth = how far down they reach (0..1)."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    a = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(a)
    ang = 2 * math.pi * ph / PHASES
    for i, (x, wd, al) in enumerate(((0.18, 0.05, 70), (0.34, 0.035, 50), (0.52, 0.06, 64), (0.7, 0.04, 46), (0.86, 0.05, 56))):
        sway = math.sin(ang + i * 1.7) * w * 0.025
        xt = w * x + sway
        xb = xt + w * 0.12 + sway * 2.5
        d.polygon([(xt - w * wd * 0.4, 0), (xt + w * wd * 0.4, 0), (xb + w * wd * 1.6, h * depth), (xb - w * wd * 1.6, h * depth)],
                  fill=int(al * (0.8 + 0.2 * math.sin(ang * 2 + i))))
    a = a.filter(ImageFilter.GaussianBlur(w * 0.018))
    fade = Image.linear_gradient("L").resize((w, h)).point(lambda v: 255 - v)
    from PIL import ImageChops
    a = ImageChops.multiply(a, fade)
    layer.paste(L.RAY + (255,), (0, 0), a)
    return layer


@lru_cache(maxsize=PHASES)
def _kelp(w: int, h: int, ph: int, count: int) -> Image.Image:
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = random.Random(5)
    sc = L.scale()
    ang = 2 * math.pi * ph / PHASES
    for i in range(count):
        x0 = w * (0.04 + 0.92 * (i + rnd.uniform(-0.25, 0.25)) / max(1, count - 1))
        tall = h * rnd.uniform(0.55, 0.95)
        far = rnd.random() < 0.45
        col = L.KELP_DARK if far else L.KELP
        pts = []
        steps = 18
        for s in range(steps + 1):
            k = s / steps
            bend = math.sin(ang + i * 0.9 + k * 2.2) * w * 0.018 * k
            pts.append((x0 + bend, h - tall * k))
        d.line(pts, fill=col, width=max(2, int((3 if far else 4) * sc)))
        for s in range(2, steps, 2):
            x, y = pts[s]
            side = 1 if s % 4 == 0 else -1
            lw, lh = 22 * sc * (0.8 if far else 1.0), 8 * sc
            d.ellipse((x + side * 2 * sc - (lw if side < 0 else 0), y - lh / 2, x + side * 2 * sc + (lw if side > 0 else 0), y + lh / 2),
                      fill=col)
    return layer


def _specks(img: Image.Image, t: float, name: str, floor: float = 1.0) -> None:
    """Small particles: rising slowly in lit water, falling (marine snow) in the abyss; none below `floor` (the sand)."""
    w, h = img.size
    sc = L.scale()
    d = ImageDraw.Draw(img)
    rnd = random.Random(3)
    n = 70 if name == "abyss" else 46
    fall = name == "abyss"
    for _ in range(n):
        x0, y0 = rnd.uniform(0, w), rnd.uniform(0, h)
        sp = rnd.uniform(6, 18) * sc
        r = rnd.uniform(0.8, 2.4) * sc
        al = rnd.randint(40, 120)
        y = (y0 + (sp if fall else -sp) * t) % h
        x = x0 + math.sin(t * 0.4 + x0) * 6 * sc
        if y > h * floor:
            continue
        d.ellipse((x - r, y - r, x + r, y + r), fill=L.SPECK + (al,))


# ------------------------------------------------------------------------------------------------------------------ public

def draw(name: str, t: float, args: Optional[Dict[str, Any]] = None, w: int = W, h: int = H) -> Image.Image:
    name = name if name in SETS else "open_water"
    a = args or {}
    img = _base(name, _args(a), int(w), int(h)).copy()
    if name in _RAY_SETS:
        depth = 0.75 if name != "seafloor" else 0.6
        rays = _rays(int(w), int(h), _phase(t, RAY_CYCLE_S), depth)
        if name == "surface":
            hy = int(h * float(a.get("horizon", 0.34)))
            img.alpha_composite(rays.crop((0, 0, w, h - hy)), (0, hy))
        else:
            img.alpha_composite(rays)
    if name == "kelp":
        img.alpha_composite(_kelp(int(w), int(h), _phase(t, KELP_CYCLE_S), int(a.get("count", 9))))
    if name not in ("split_columns", "burrow", "savanna", "savanna_night", "plain"):
        _specks(img, t, name, float(a.get("sand_y", 0.62)) - 0.03 if name == "seafloor" else 1.0)
    return img
