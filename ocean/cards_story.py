"""Sentence scenes for Ocean Predators: each one draws what ONE narration line says (ocean/relations.py reads it), the way
the reference channel follows its narration line by line. Same contract as ocean/cards.py: a stage kind "ocean_<name>",
drawn in 1280 x 720 units, args["_k"] 0..1 animates it.

Full-frame scenes
    stomach       {predator, prey:[keys], labels:[text]}          the predator with an x-ray window: what it had eaten
    above_below   {top, bottom, surface: ice|land|surface}        cross-section: one on the ice / shore, one in the water
    map_pin       {place, lat, lon, line}                         dark map of the region, a pin and the place's name
    icon_grid     {animal, count, lit, title, sub}                45 shark icons, a third of them lit
    ghost_size    {animal, real_m, claim_m, real_label, claim_label}  measured animal + dashed outline of the claimed one
    hud_bars      {title, rows:[[label, value, text]], colors}    speed / air-use bars on a dark grid panel
    polaroid      {photo, animal, caption}                        a real photo (Visuals tab) in a tilted print, handwritten line
    year_anchor   {year, event, line}                             "1776" / THE UNITED STATES DECLARES INDEPENDENCE
    anatomy       {animal, part, label}                           close-up on one body part with a ring and a label
    era           {title, ago, order, prev}                       time dial spins to the era, then its title
    scoreboard    {rules, survives, dies}                         the end tally of a "survive every era" film
Corner cards (the animals stay)
    latin_name    {latin, means}                                  "Somniosus microcephalus" + "small head"
    temp_tag      {text}                                          thermometer + "-1.5 °C"
    question      {}                                              a big "?" over the animal
    verdict       {verdict: rules|survives|dies}                  crown / tick / skull stamp
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import look as L
from .cards import F, PANEL, _animal, _canvas, _centre, _ease, _fit, _k, _paste_c, _tw, _wrap

GRID_BG = (8, 16, 24, 255)
GRID_LINE = (24, 40, 52, 255)
BLUE_BAR = (120, 196, 230, 255)
YELLOW_BAR = (240, 216, 120, 255)
GREEN_BAR = (110, 210, 140, 255)
RED_BAR = (232, 96, 84, 255)
XRAY = (150, 230, 240, 255)
HAND_FONT = Path(__file__).resolve().parent.parent / "explainer" / "assets" / "fonts" / "Kalam-Bold.ttf"


def _hand(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(HAND_FONT), int(size))
    except OSError:
        return F("bold", size)


def _dark_bg(grid: bool = False) -> Image.Image:
    im = Image.new("RGBA", (1280, 720), GRID_BG)
    d = ImageDraw.Draw(im)
    for y in range(720):
        k = y / 719
        d.line((0, y, 1280, y), fill=(int(12 - 6 * k), int(26 - 14 * k), int(36 - 20 * k), 255))
    if grid:
        for x in range(0, 1281, 64):
            d.line((x, 0, x, 720), fill=GRID_LINE, width=1)
        for y in range(0, 721, 64):
            d.line((0, y, 1280, y), fill=GRID_LINE, width=1)
    vig = Image.new("L", (1280, 720), 0)
    ImageDraw.Draw(vig).ellipse((-160, -120, 1440, 840), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(110))
    return Image.composite(im, Image.new("RGBA", (1280, 720), (2, 4, 8, 255)), vig)


def _fit_w(sp: Image.Image, w: float, h: float) -> Image.Image:
    s = min(w / max(1, sp.width), h / max(1, sp.height))
    return sp.resize((max(1, int(sp.width * s)), max(1, int(sp.height * s))), Image.LANCZOS)


def _pale(sp: Image.Image, col=XRAY, alpha: float = 0.9) -> Image.Image:
    """The animal as a pale x-ray shape with a brighter outline."""
    a = sp.getchannel("A")
    out = Image.new("RGBA", sp.size, col[:3] + (0,))
    out.putalpha(a.point(lambda v: int(v * alpha * 0.45)))
    edge = ImageChops.subtract(a, a.filter(ImageFilter.MinFilter(5)))
    line = Image.new("RGBA", sp.size, col[:3] + (0,))
    line.putalpha(edge)
    out.alpha_composite(line)
    return out


def _name(key: str) -> str:
    return str(key or "").replace("_", " ").upper()


# ------------------------------------------------------------------------------------------------------------------ scenes

def stomach(a: Dict[str, Any]) -> Image.Image:
    k = _ease(_k(a))
    im = _dark_bg()
    pred = _animal(str(a.get("predator", "great_white")), 1040)
    px, py = 640 - pred.width // 2, 330 - pred.height // 2
    im.alpha_composite(pred, (px, py))
    prey = [p for p in (a.get("prey") or []) if p][:4]
    if not prey or k <= 0.02:
        return im
    cx, cy = px + pred.width * 0.52, py + pred.height * 0.58
    rx, ry = pred.width * 0.24 * k, max(40.0, pred.height * 0.30) * k
    win = Image.new("L", im.size, 0)
    ImageDraw.Draw(win).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    inner = Image.new("RGBA", im.size, (10, 34, 44, 255))
    slot = (2 * rx) / max(1, len(prey))
    for i, name in enumerate(prey):
        sp = _fit_w(_animal(name, 360), slot * 0.9, ry * 1.5)
        _paste_c(inner, _pale(sp), cx - rx + slot * (i + 0.5), cy)
    im = Image.composite(inner, im, win)
    d = ImageDraw.Draw(im)
    d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=XRAY, width=3)
    if k > 0.7:
        labels = list(a.get("labels") or [_name(p) for p in prey])
        _centre(d, 640, min(660, cy + ry + 30), "  ·  ".join(str(x).upper() for x in labels[:4]), F("bold", 28), L.WHITE)
    return im


def above_below(a: Dict[str, Any]) -> Image.Image:
    k = _ease(_k(a))
    surf = str(a.get("surface", "ice"))
    im = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    line_y = 300
    for y in range(line_y):
        c = (int(34 + 30 * y / line_y), int(44 + 34 * y / line_y), int(58 + 30 * y / line_y), 255)
        d.line((0, y, 1280, y), fill=c)
    for y in range(line_y, 720):
        k2 = (y - line_y) / (720 - line_y)
        d.line((0, y, 1280, y), fill=(int(14 - 10 * k2), int(40 - 32 * k2), int(56 - 44 * k2), 255))
    slab = {"ice": ((228, 238, 244, 255), (176, 200, 214, 255)), "land": ((150, 128, 96, 255), (104, 86, 64, 255))}.get(
        surf, ((40, 70, 90, 255), (30, 56, 74, 255)))
    if surf in ("ice", "land"):
        d.polygon([(0, line_y - 34), (760, line_y - 40), (800, line_y + 26), (0, line_y + 30)], fill=slab[0])
        d.polygon([(0, line_y + 4), (800, line_y + 4), (800, line_y + 26), (0, line_y + 30)], fill=slab[1])
    d.line((0, line_y, 1280, line_y), fill=(200, 222, 232, 200), width=2)
    top = a.get("top")
    if top:
        sp = _fit_w(_animal(str(top), 420), 420, 230)
        im.alpha_composite(sp, (int(380 - sp.width / 2), int(line_y - 36 - sp.height + 10)))
    bot = a.get("bottom")
    if bot:
        sp = _fit_w(_animal(str(bot), 380, face="left"), 380, 200)
        y = 520 - 30 * (1 - k)
        _paste_c(im, sp, 820, y)
        if a.get("sleep"):
            fz = F("heavy", 34)
            for i, ch in enumerate("zZz"):
                d.text((900 + i * 26, y - 140 - i * 30 + 10 * math.sin(k * 6 + i)), ch, font=fz, fill=(220, 236, 244, 200))
    return im


@lru_cache(maxsize=16)
def _map_base(lat: float, lon: float, span: float) -> Image.Image:
    from cinematic_explainer.war import geo_data as G
    import numpy as np
    w, h = 1280, 720
    im = Image.new("RGBA", (w, h), (14, 40, 56, 255))
    d = ImageDraw.Draw(im)
    lon0, lon1 = lon - span / 2, lon + span / 2
    ym_c = G.merc(lat)
    ym_span = math.radians(span) * h / w
    def xy(lons, yms):
        return np.stack([(lons - lon0) / (lon1 - lon0) * w, (ym_c + ym_span / 2 - yms) / ym_span * h], axis=1)
    for f in G.countries():
        b = f.bbox
        if b[2] < lon0 - 5 or b[0] > lon1 + 5:
            continue
        for ring, holes in f.polys:
            if ring.bbox[2] < lon0 - 5 or ring.bbox[0] > lon1 + 5:
                continue
            pts = [tuple(p) for p in xy(ring.lon, ring.ym)]
            if len(pts) >= 3:
                d.polygon(pts, fill=(176, 186, 180, 255), outline=(220, 228, 224, 255))
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse((-180, -140, w + 180, h + 140), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(120))
    return Image.composite(im, Image.new("RGBA", (w, h), (4, 12, 18, 255)), vig)


def map_pin(a: Dict[str, Any]) -> Image.Image:
    k = _ease(_k(a))
    lat, lon = float(a.get("lat", 0.0)), float(a.get("lon", 0.0))
    span = float(a.get("span", 40.0 if abs(lat) < 60 else 70.0))
    try:
        im = _map_base(round(lat, 2), round(lon, 2), span).copy()
    except Exception:  # noqa: BLE001 - no map data: dark water and the name
        im = _dark_bg(grid=True)
    d = ImageDraw.Draw(im)
    x, y = 640, 360
    n_dots = min(60, int(a.get("dots") or 0))           # a cluster of red dots: the attacks / sightings around the place
    if n_dots:
        import random as _rnd
        rg = _rnd.Random(str(a.get("place", "")))
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for i in range(int(n_dots * min(1.0, k * 1.4))):
            dx, dy = rg.gauss(0, 120), rg.gauss(0, 80)
            rr = rg.uniform(7, 14)
            ld.ellipse((x + dx - rr, y + dy - rr, x + dx + rr, y + dy + rr), fill=(226, 60, 60, 150))
        im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(2)))
        if a.get("count_label") and k > 0.5:
            _centre(d, 640, 90, str(a["count_label"]).upper(), F("heavy", 64), L.WHITE)
    r = 10 + 40 * (1 - k)
    d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, int(255 * k)), width=3)
    d.ellipse((x - 8, y - 8, x + 8, y + 8), fill=L.RED)
    f = F("bold", 26)
    name = str(a.get("place", "")).upper()
    if k > 0.3:
        d.rounded_rectangle((x + 24, y - 24, x + 48 + _tw(d, name, f), y + 20), radius=6, fill=(8, 14, 20, 220))
        d.text((x + 36, y - 18), name, font=f, fill=L.WHITE)
    if a.get("line") and k > 0.6:
        _centre(d, 640, 640, str(a["line"]).upper(), F("regular", 22), L.SOFT)
    return im


def icon_grid(a: Dict[str, Any]) -> Image.Image:
    k = _ease(_k(a))
    n_real = max(1, int(a.get("count", 20)))
    n = min(60, n_real)
    lit = max(0, min(n, int(round(float(a.get("lit", 0)) * n / n_real)) if a.get("lit") is not None else 0))
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    cols = min(n, max(5, int(math.ceil(math.sqrt(n * 2.6)))))
    rows = math.ceil(n / cols)
    cw = min(150, 1100 / cols)
    ch = min(90, 440 / rows)
    icon = _fit_w(_animal(str(a.get("animal", "great_white")), 300, flat=bool(a.get("flat_art"))), cw * 0.86, ch * 0.8)
    grey = icon.copy()
    grey.putalpha(icon.getchannel("A").point(lambda v: int(v * 0.35)))
    x0 = 640 - cols * cw / 2 + cw / 2
    y0 = 380 - rows * ch / 2 + ch / 2
    shown = int(round(n * min(1.0, k * 1.6)))
    lit_now = int(round(lit * max(0.0, (k - 0.55) / 0.45)))
    for i in range(shown):
        r_, c_ = divmod(i, cols)
        _paste_c(im, icon if i < lit_now else grey, x0 + c_ * cw, y0 + r_ * ch)
    _centre(d, 640, 60, str(a.get("title", f"{n_real}")).upper(), F("heavy", 40), L.WHITE)
    if a.get("sub") and k > 0.6:
        _centre(d, 640, 112, str(a["sub"]).upper(), F("bold", 24), L.ORANGE)
    return im


def _dashed_outline(sp: Image.Image, col=(232, 236, 240), dash: int = 14) -> Image.Image:
    al = sp.getchannel("A").point(lambda v: 255 if v > 60 else 0)
    edge = ImageChops.subtract(al.filter(ImageFilter.MaxFilter(5)), al)
    stripes = Image.new("L", sp.size, 0)
    ds = ImageDraw.Draw(stripes)
    for x in range(-sp.height, sp.width, dash * 2):
        ds.polygon([(x, 0), (x + dash, 0), (x + dash + sp.height, sp.height), (x + sp.height, sp.height)], fill=255)
    out = Image.new("RGBA", sp.size, col + (0,))
    out.putalpha(ImageChops.multiply(edge, stripes))
    return out


def ghost_size(a: Dict[str, Any]) -> Image.Image:
    k = _ease(_k(a))
    real, claim = max(0.3, float(a.get("real_m", 5.5))), max(0.3, float(a.get("claim_m", 7.0)))
    big = max(real, claim)
    ppm = 1000 / big
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    name = str(a.get("animal", "great_white"))
    ghost = _animal(name, int(claim * ppm))
    _paste_c(im, _dashed_outline(ghost), 640, 300)
    if k > 0.4:
        sp = _animal(name, int(real * ppm))
        im.alpha_composite(sp, (int(640 - ghost.width / 2), int(300 - sp.height / 2 + (ghost.height - sp.height) * 0.15)))
    fb = F("bold", 26)
    y = 300 + ghost.height / 2 + 40
    x0 = 640 - ghost.width / 2
    for i, (length, text, col) in enumerate(((real * ppm, a.get("real_label") or f"MEASURED · {real:g} M", YELLOW_BAR),
                                             (claim * ppm, a.get("claim_label") or f"CLAIMED · {claim:g} M ?", (200, 206, 210, 255)))):
        if i == 0 and k <= 0.4:
            continue
        yy = y + i * 54
        L_ = length * (k if i == 1 else min(1.0, (k - 0.4) / 0.6))
        if i == 1:
            for xx in range(int(x0), int(x0 + L_), 18):
                d.line((xx, yy, min(x0 + L_, xx + 10), yy), fill=col, width=3)
        else:
            d.line((x0, yy, x0 + L_, yy), fill=col, width=3)
        tw = _tw(d, str(text).upper(), fb)
        tx = x0 + L_ + 16 if x0 + L_ + 16 + tw < 1250 else x0 + L_ - tw
        d.text((tx, yy - 40 if tx < x0 + L_ else yy - 16), str(text).upper(), font=fb, fill=col)
    return im


def hud_bars(a: Dict[str, Any]) -> Image.Image:
    k = _ease(_k(a))
    rows = list(a.get("rows") or [])[:4]
    cols = [tuple(c) for c in (a.get("colors") or [BLUE_BAR, YELLOW_BAR, (180, 190, 200, 255), (180, 190, 200, 255)])]
    im = _dark_bg(grid=True)
    d = ImageDraw.Draw(im)
    _centre(d, 640, 150, str(a.get("title", "")).upper(), F("heavy", 40), L.WHITE)
    d.line((560, 204, 720, 204), fill=(120, 140, 152, 255), width=2)
    vmax = max([float(r[1]) for r in rows] + [1e-6])
    fl = F("bold", 24)
    lab_w = max([_tw(d, str(r[0]).upper(), fl) for r in rows] + [100])
    x_bar = 640 - 260 + 20
    x_lab = x_bar - 30 - lab_w
    for i, r in enumerate(rows):
        y = 290 + i * 90
        d.text((x_lab, y + 6), str(r[0]).upper(), font=fl, fill=L.SOFT)
        w = max(8.0, 560 * float(r[1]) / vmax * k)
        c = cols[i % len(cols)]
        d.rectangle((x_bar, y, x_bar + w, y + 40), fill=c[:3] + (230,), outline=c[:3] + (255,), width=2)
        if k > 0.5:                                       # the value shows while the bar is still growing
            d.text((x_bar + w + 18, y + 6), str(r[2] if len(r) > 2 else r[1]).upper(), font=F("heavy", 26), fill=L.WHITE)
    return im


def polaroid(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(640, 700)
    d.rectangle((20, 20, 620, 680), fill=(244, 242, 236, 255))
    box = (52, 52, 588, 512)
    photo = None
    p = a.get("photo")
    if p and Path(str(p)).is_file():
        try:
            src = Image.open(str(p)).convert("RGBA")
            bw, bh = box[2] - box[0], box[3] - box[1]
            s = max(bw / src.width, bh / src.height)
            src = src.resize((int(src.width * s) + 1, int(src.height * s) + 1), Image.LANCZOS)
            photo = src.crop(((src.width - bw) // 2, (src.height - bh) // 2, (src.width - bw) // 2 + bw, (src.height - bh) // 2 + bh))
        except Exception:  # noqa: BLE001
            photo = None
    if photo is None:                                     # no real photo yet: the painted animal in murky water
        bw, bh = box[2] - box[0], box[3] - box[1]
        photo = Image.new("RGBA", (bw, bh), (30, 60, 72, 255))
        pd = ImageDraw.Draw(photo)
        for y in range(bh):
            pd.line((0, y, bw, y), fill=(int(40 - 26 * y / bh), int(76 - 50 * y / bh), int(88 - 56 * y / bh), 255))
        _paste_c(photo, _fit_w(_animal(str(a.get("animal", "great_white")), 500), bw * 0.9, bh * 0.75), bw / 2, bh / 2)
    from PIL import ImageEnhance
    photo = ImageEnhance.Color(photo).enhance(0.75)
    im.alpha_composite(photo, box[:2])
    cap = str(a.get("caption", ""))
    if cap:
        f = _hand(44)
        lines = _wrap(d, cap, f, 540)[:2]
        for i, ln in enumerate(lines):
            _centre(d, 320, 548 + i * 54 - (20 if len(lines) > 1 else 0), ln, f, (30, 30, 34, 255))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((30, 34, 630, 694), fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    sh.alpha_composite(im)
    return sh.rotate(float(a.get("tilt", -4.0)), expand=True, resample=Image.BICUBIC)


def year_anchor(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    year = str(a.get("year", ""))
    shown = year[: max(1, int(round(len(year) * min(1.0, k * 2.5))))] if a.get("_k") is not None else year
    _centre(d, 640, 230, shown, F("heavy", 150), L.WHITE)
    if k > 0.4:
        _centre(d, 640, 420, str(a.get("event", "")).upper(), _fit(d, str(a.get("event", "")).upper(), "bold", 28, 1000), L.SOFT)
    if a.get("line") and k > 0.7:
        _centre(d, 640, 480, str(a["line"]).upper(), F("heavy", 30), L.ORANGE)
    return im


PART_AT = {  # where a body part sits on a side view facing right (fraction of width, height)
    "eye": (0.86, 0.46), "mouth": (0.92, 0.60), "nose": (0.97, 0.48), "gills": (0.76, 0.52), "fin": (0.55, 0.12),
    "tail": (0.07, 0.40), "liver": (0.58, 0.60), "skin": (0.42, 0.45), "brain": (0.84, 0.36), "heart": (0.72, 0.64),
    "sense": (0.95, 0.52), "claw": (0.80, 0.92),
}


PART_AT_LAND = {  # a standing four-legged animal facing right: the head is high at the front
    "eye": (0.86, 0.24), "mouth": (0.93, 0.40), "nose": (0.97, 0.32), "gills": (0.80, 0.42), "fin": (0.5, 0.12),
    "tail": (0.04, 0.40), "liver": (0.55, 0.50), "skin": (0.52, 0.38), "brain": (0.85, 0.18), "heart": (0.68, 0.52),
    "sense": (0.96, 0.32), "claw": (0.78, 0.96),
}
PART_AT_SNAKE = {"eye": (0.9, 0.12), "mouth": (0.93, 0.16), "nose": (0.95, 0.12), "skin": (0.5, 0.75), "sense": (0.95, 0.14),
                 "tail": (0.05, 0.85), "heart": (0.5, 0.7), "liver": (0.5, 0.75), "brain": (0.9, 0.1), "claw": (0.5, 0.75)}


def anatomy(a: Dict[str, Any]) -> Image.Image:
    k = _ease(_k(a))
    part = str(a.get("part", "eye"))
    from . import species as _SPX
    fam = _SPX.family(str(a.get("animal", "")))
    land = fam in ("land", "bear", "bird")
    snake = str(a.get("animal", "")) in ("cobra", "puff_adder", "black_mamba")
    table = PART_AT_SNAKE if snake else PART_AT_LAND if land else PART_AT
    fx, fy = table.get(part, (0.5, 0.5))
    zoom = 1.0 + 1.1 * k if part not in ("tail", "fin", "skin") else 1.0 + 0.4 * k
    im = _dark_bg()
    sp = _animal(str(a.get("animal", "great_white")), int(900 * zoom), jaw=part == "mouth" and k > 0.5 and not land,
                 flat=bool(a.get("flat_art")))
    px = 640 - fx * sp.width * k - 0.5 * sp.width * (1 - k)          # glide the part to the centre while zooming
    py = 380 - fy * sp.height * k - 0.5 * sp.height * (1 - k)
    im.alpha_composite(sp, (int(px), int(py)))
    cx, cy = px + fx * sp.width, py + fy * sp.height
    d = ImageDraw.Draw(im)
    if k > 0.5:
        q = (k - 0.5) / 0.5
        if part == "sense":                                           # the electric field: rings spreading from the snout
            for i in range(4):
                r = 60 + i * 70 * q
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(140, 210, 240, int(200 * (1 - i / 4))), width=3)
        else:
            r = 90 + 10 * math.sin(q * 6)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=L.ORANGE, width=4)
            lx, ly = cx - 300, cy - 190
            d.line((cx - r * 0.7, cy - r * 0.7, lx + 200, ly + 20, lx, ly + 20), fill=L.ORANGE, width=3)
        label = str(a.get("label") or part).upper()
        f = F("heavy", 30)
        d.text((max(30, cx - 300), max(30, cy - 240)), label, font=f, fill=L.WHITE)
    return im


def _dial(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, ang: float, alpha: int = 255) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(70, 80, 90, alpha), outline=(150, 160, 168, alpha), width=6)
    d.ellipse((cx - r * 0.88, cy - r * 0.88, cx + r * 0.88, cy + r * 0.88), outline=(110, 120, 130, alpha), width=2)
    for i in range(60):
        a = 2 * math.pi * i / 60
        r0 = r * (0.78 if i % 5 == 0 else 0.83)
        d.line((cx + math.cos(a) * r0, cy + math.sin(a) * r0, cx + math.cos(a) * r * 0.87, cy + math.sin(a) * r * 0.87),
               fill=(200, 206, 210, alpha), width=3 if i % 5 == 0 else 1)
    hx, hy = cx + math.cos(ang) * r * 0.72, cy + math.sin(ang) * r * 0.72
    d.line((cx, cy, hx, hy), fill=(240, 240, 236, alpha), width=6)
    d.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill=(80, 150, 220, alpha))


def era(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    o1 = float(a.get("order", 0.5))
    o0 = float(a.get("prev", 1.0))
    spin = _ease(min(1.0, k / 0.5))
    turns = 1.0 if o1 < o0 else 0.0                                # going back in time: the hand winds backwards
    ang = -math.pi / 2 + 2 * math.pi * (o0 + (o1 - o0 - turns) * spin)
    if k < 0.62:
        _dial(d, 640, 360, 220, ang)
        return im
    q = _ease((k - 0.62) / 0.38)
    _dial(d, 640, 360 - 120 * q, 220 * (1 - 0.65 * q), ang, int(255 * (1 - 0.6 * q)))
    if a.get("ago"):
        _centre(d, 640, 360, str(a["ago"]).upper(), F("bold", 26), (190, 200, 206, int(255 * q)))
    if a.get("title"):
        _centre(d, 640, 400, str(a["title"]).upper(), F("heavy", 64), (246, 248, 250, int(255 * q)))
    return im


def _crown(d, cx, cy, s, col):
    d.polygon([(cx - s, cy + s * 0.6), (cx - s, cy - s * 0.4), (cx - s * 0.5, cy), (cx, cy - s * 0.7), (cx + s * 0.5, cy),
               (cx + s, cy - s * 0.4), (cx + s, cy + s * 0.6)], fill=col)


def _tick(d, cx, cy, s, col):
    d.ellipse((cx - s, cy - s, cx + s, cy + s), fill=col)
    d.line((cx - s * 0.45, cy, cx - s * 0.1, cy + s * 0.38, cx + s * 0.5, cy - s * 0.35), fill=(10, 20, 24, 255), width=max(3, int(s * 0.22)))


def _skull(d, cx, cy, s, col):
    d.ellipse((cx - s * 0.8, cy - s, cx + s * 0.8, cy + s * 0.45), fill=col)
    d.rectangle((cx - s * 0.45, cy + s * 0.2, cx + s * 0.45, cy + s * 0.8), fill=col)
    for ex in (-0.33, 0.33):
        d.ellipse((cx + ex * s - s * 0.22, cy - s * 0.35, cx + ex * s + s * 0.22, cy + s * 0.08), fill=(10, 12, 16, 255))


ICONS = {"rules": (_crown, (246, 196, 60, 255)), "survives": (_tick, (110, 210, 150, 255)), "dies": (_skull, (230, 230, 230, 255))}
WORDS = {"rules": "RULES", "survives": "SURVIVES", "dies": "DIES"}


def scoreboard(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    for i, key in enumerate(("rules", "survives", "dies")):
        if k < i * 0.25:
            continue
        cx = 400 + i * 240
        fn, col = ICONS[key]
        fn(d, cx, 290, 34, col)
        _centre(d, cx, 340, str(int(a.get(key, 0))), F("heavy", 60), L.WHITE)
        _centre(d, cx, 420, WORDS[key], F("bold", 22), (170, 180, 186, 255))
    return im


# ------------------------------------------------------------------------------------------------------------------ corner cards

def latin_name(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(900, 130)
    f = F("serif", 46)
    _centre(d, 450, 4, str(a.get("latin", "")), f, L.WHITE)
    if a.get("means"):
        _centre(d, 450, 72, "“" + str(a["means"]) + "”", _hand(36), L.ORANGE)
    return im


def temp_tag(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(300, 110)
    d.rounded_rectangle((20, 14, 40, 76), radius=10, outline=L.WHITE, width=3)
    d.ellipse((12, 64, 48, 100), outline=L.WHITE, width=3)
    d.ellipse((19, 71, 41, 93), fill=(120, 196, 230, 255))
    d.rectangle((27, 46, 33, 76), fill=(120, 196, 230, 255))
    d.text((66, 24), str(a.get("text", "")), font=F("heavy", 50), fill=L.WHITE)
    return im


def question(a: Dict[str, Any]) -> Image.Image:
    im, d = _canvas(160, 200)
    f = F("heavy", 150)
    d.text((80, 100), "?", font=f, fill=(246, 214, 90, 255), anchor="mm")
    glow = im.filter(ImageFilter.GaussianBlur(10))
    return Image.alpha_composite(glow, im)


def verdict(a: Dict[str, Any]) -> Image.Image:
    v = str(a.get("verdict", "survives"))
    im, d = _canvas(360, 110)
    d.rounded_rectangle((4, 4, 356, 106), radius=16, fill=PANEL)
    fn, col = ICONS.get(v, ICONS["survives"])
    fn(d, 60, 56, 30, col)
    d.text((110, 30), WORDS.get(v, v.upper()), font=F("heavy", 40), fill=col)
    return im


# ------------------------------------------------------------------ ApexMorph cards (docs/ocean/PATTERNS.md, land video #7)

def title_banner(a: Dict[str, Any]) -> Image.Image:
    """"THE TSAVO LIONS" on a slanted orange bar, "Kenya, 1898" under it; the animal small above (glowing eyes in the dark
    when no animal is given). args: title, sub, animal."""
    k = _ease(_k(a))
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    if a.get("animal"):
        sp = _fit_w(_animal(str(a["animal"]), 420, flat=bool(a.get("flat_art"))), 360, 170)
        sp.putalpha(sp.getchannel("A").point(lambda v: int(v * min(1.0, k * 1.5))))
        _paste_c(im, sp, 640, 205)
    else:
        for x in (612, 668):
            r = 7 * min(1.0, k * 2)
            d.ellipse((x - r, 200 - r, x + r, 200 + r), fill=(236, 230, 120, 255))
    title = str(a.get("title", "")).upper()
    f = _fit(d, title, "heavy", 58, 760)
    tw = _tw(d, title, f)
    bw = (tw + 120) * min(1.0, k * 1.6)
    if bw > 4:
        bar = Image.new("RGBA", (int(bw) + 40, 130), (0, 0, 0, 0))
        ImageDraw.Draw(bar).polygon([(20, 22), (int(bw) + 40, 0), (int(bw) + 20, 108), (0, 130)], fill=(232, 112, 56, 255))
        im.alpha_composite(bar, (int(640 - (bw + 40) / 2), 300))
    if k > 0.45:
        _centre(d, 640, 365 - f.size * 0.62, title, f, (20, 20, 22, 255))
    if a.get("sub") and k > 0.7:
        _centre(d, 640, 455, str(a["sub"]), F("regular", 24), L.SOFT)
    return im


def checklist(a: Dict[str, Any]) -> Image.Image:
    """"TRIED: x soldiers x traps x poison" and an "ALL FAILED" stamp, or "SURVIVED: v gunfire"; the items tick in one by
    one. args: title, items [[text, ok]], stamp."""
    k = _ease(_k(a))
    items = [list(x) for x in (a.get("items") or [])][:6]
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    fi, ft = F("bold", 30), F("heavy", 36)
    w = max([_tw(d, str(x[0]), fi) for x in items] + [_tw(d, str(a.get("title", "")).upper(), ft)]) + 140
    h = 90 + 58 * len(items)
    x0, y0 = 640 - w / 2 - 120, 360 - h / 2
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=10, fill=(22, 30, 38, 235))
    d.text((x0 + 34, y0 + 26), str(a.get("title", "")).upper(), font=ft, fill=L.WHITE)
    shown = int(len(items) * min(1.0, k * 1.35) + 0.999) if items else 0
    for i, (text, ok) in enumerate(items[:shown]):
        y = y0 + 90 + i * 58
        cx, cy = x0 + 50, y + 18
        if ok:
            d.line((cx - 12, cy, cx - 3, cy + 10, cx + 14, cy - 12), fill=(110, 210, 140, 255), width=5)
        else:
            d.line((cx - 11, cy - 11, cx + 11, cy + 11), fill=L.RED, width=5)
            d.line((cx - 11, cy + 11, cx + 11, cy - 11), fill=L.RED, width=5)
        d.text((x0 + 86, y), str(text), font=fi, fill=(214, 220, 226, 255))
    if a.get("stamp") and k > 0.85:
        st = str(a["stamp"]).upper()
        fs = F("heavy", 44)
        sw = int(_tw(d, st, fs) + 40)
        stamp = Image.new("RGBA", (sw + 10, 86), (0, 0, 0, 0))
        sd = ImageDraw.Draw(stamp)
        sd.rectangle((4, 4, sw + 4, 80), outline=L.RED, width=5)
        sd.text((24, 14), st, font=fs, fill=L.RED)
        stamp = stamp.rotate(8, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(stamp, (int(x0 + w + 30), int(y0 + h / 2 - stamp.height / 2)))
    return im


def statement(a: Dict[str, Any]) -> Image.Image:
    """A short line in big heavy letters, the last word red ("FOUR HUNDRED.", "ONE KILL."). args: text."""
    k = _ease(_k(a))
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    words = str(a.get("text", "")).upper().split()
    if not words:
        return im
    head, last = " ".join(words[:-1]), words[-1]
    f = _fit(d, " ".join(words), "heavy", 96, 1100)
    wh = _tw(d, head + " ", f) if head else 0
    wl = _tw(d, last, f)
    x = 640 - (wh + wl) / 2
    y = 360 - f.size * 0.6 + 30 * (1 - min(1.0, k * 2))
    col = lambda c: c[:3] + (int(255 * min(1.0, k * 2)),)
    if head:
        d.text((x, y), head, font=f, fill=col(L.WHITE))
    d.text((x + wh, y), last, font=f, fill=col(L.RED))
    return im


def labels(a: Dict[str, Any]) -> Image.Image:
    """The whole animal from the side with thin pointer lines to its named parts ("MASSIVE SHOULDERS", "NO MANE").
    args: animal, labels [text, ...] (a label naming a body part points at it)."""
    from . import relations as REL
    from . import species as _SPX
    k = _ease(_k(a))
    im = _dark_bg()
    d = ImageDraw.Draw(im)
    name = str(a.get("animal", "great_white"))
    land = _SPX.family(name) in ("land", "bear", "bird")
    snake = name in ("cobra", "puff_adder", "black_mamba")
    table = PART_AT_SNAKE if snake else PART_AT_LAND if land else PART_AT
    sp = _fit_w(_animal(name, 760, flat=bool(a.get("flat_art"))), 640, 360)
    ax, ay = 640 - sp.width / 2, 430 - sp.height / 2
    im.alpha_composite(sp, (int(ax), int(ay)))
    spots = [(0.35, 0.2), (0.8, 0.2), (0.15, 0.55), (0.6, 0.75)]
    labs = [str(x) for x in (a.get("labels") or [])][:4]
    placed: List[Tuple[bool, bool]] = []
    for i, lab in enumerate(labs):
        q = max(0.0, min(1.0, k * (len(labs) + 1) - i - 0.6))
        if q <= 0:
            continue
        part = next((n for rx, n in REL._PARTS if rx.search(lab)), None)
        fx, fy = table.get(part, spots[i % len(spots)]) if part else spots[i % len(spots)]
        px, py = ax + fx * sp.width, ay + fy * sp.height
        right, low = fx >= 0.5, fy >= 0.6                 # the label sits on its part's side, so lines never cross the body
        used = sum(1 for j in range(i) if placed[j] == (right, low))
        placed.append((right, low))
        tx = 1060 if right else 220
        ty = (600 + used * 46) if low else (120 + used * 46)
        f = F("bold", 26)
        t = lab.upper()
        tw = _tw(d, t, f)
        d.line((px, py, px + (tx - px) * q, py + (ty + 34 - py) * q), fill=(200, 206, 212, int(255 * q)), width=2)
        d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=L.WHITE)
        if q > 0.8:
            d.text((tx - tw / 2, ty), t, font=f, fill=L.WHITE)
    return im


KINDS = {
    "title_banner": title_banner, "checklist": checklist, "statement": statement, "labels": labels,
    "stomach": stomach, "above_below": above_below, "map_pin": map_pin, "icon_grid": icon_grid, "ghost_size": ghost_size,
    "hud_bars": hud_bars, "polaroid": polaroid, "year_anchor": year_anchor, "anatomy": anatomy, "era": era,
    "scoreboard": scoreboard, "latin_name": latin_name, "temp_tag": temp_tag, "question": question, "verdict": verdict,
}
FULL = {"title_banner", "checklist", "statement", "labels", "stomach", "above_below", "map_pin", "icon_grid", "ghost_size", "hud_bars", "polaroid", "year_anchor", "anatomy",
        "era", "scoreboard"}
ANIMATED = ("title_banner", "checklist", "statement", "labels", "stomach", "above_below", "map_pin", "icon_grid", "ghost_size", "hud_bars", "year_anchor", "anatomy", "era",
            "scoreboard")
