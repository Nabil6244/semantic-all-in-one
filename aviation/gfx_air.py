"""Aviation graphics for the business side of a story (the Plane Curious blue look): numbers shown as aviation pictures, not as text.
Same contract as the other cards: fn(t, dur, params) -> RGBA 1280x720 or None (nothing to show -> nothing drawn). Full frame.

  lay_fleet       count, label            top-view airliner icons filling a grid (one icon per aircraft up to 100, then one per few)
  lay_network     hub, count, label       arcs from the hub to the catalog's airports on the dark satellite map, the count beside
  lay_seats       now, before, label      a cabin seat map filling to the load factor, last year's figure beside it
  lay_change      before, after, currency, label   then -> now bars growing, a red / green change tag
  lay_big_number  value, unit, sign, label, icon   one big counting number with an aircraft (or freighter) drawing
  lay_timeline    from_year, to_year, label        an airliner flying along a line of years, the year counting with it
Every value comes from the narration (aviation.router) or the CSV; the planner decides which line gets which graphic.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M
from cinematic_explainer.war import tokens as T
from cinematic_explainer import look as L

from . import basemap as B
from . import catalog as C
from . import cards as K
from . import flightmap as F

W, H = T.W, T.H
WHITE = (250, 250, 252, 255)
GOLD = (242, 184, 64, 255)
RED = (236, 72, 72, 255)
GREEN = (80, 200, 130, 255)
DIM = (150, 170, 230, 255)


def _label(d: ImageDraw.ImageDraw, x: float, y: float, text: str, size: int = 15, col=GOLD) -> None:
    L.spaced(d, (x, y), text.upper(), T.font("bold", size), col, 0.16)


def _num(v: float, decimals: int = 0) -> str:
    return f"{v:,.{decimals}f}"


def _airliner(d: ImageDraw.ImageDraw, x: float, y: float, size: float, angle: float, fill=WHITE) -> None:
    pts = [(x + size * (px * math.cos(angle) - py * math.sin(angle)), y + size * (px * math.sin(angle) + py * math.cos(angle)))
           for px, py in F._AIRLINER]
    d.polygon(pts, fill=fill)


def _fade_in(t: float) -> float:
    return M.ease_out(M.ramp(t, 0.0, 0.4))


# ---------------------------------------------------------------------------------------------------------------- fleet

def fleet_icons(count: int) -> int:
    return int(min(max(0, count), 100))


def lay_fleet(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    n = int((p or {}).get("count") or 0)
    if n <= 0:
        return None
    img = K.backdrop(t)
    d = ImageDraw.Draw(img)
    icons = fleet_icons(n)
    cols = 20 if icons > 40 else 10
    rows_ = math.ceil(icons / cols)
    cell = min(44, 760 / cols)
    gx, gy = 470, max(120, (H - rows_ * cell) / 2)
    shown = int(icons * M.ease_out(M.ramp(t, 0.3, 1.8)))
    for i in range(shown):
        r_, c_ = divmod(i, cols)
        _airliner(d, gx + c_ * cell + cell / 2, gy + r_ * cell + cell / 2, cell * 0.8, -math.pi / 2,
                  fill=GOLD if i == shown - 1 and shown < icons else WHITE)
    k = M.ease_out(M.ramp(t, 0.3, 1.8))
    d.text((80, 250), _num(n * k), font=T.font("display", 120), fill=WHITE)
    _label(d, 84, 390, str(p.get("label") or "AIRCRAFT"), 20)
    if n > icons:
        _label(d, 84, 430, f"each icon = {n / icons:.1f} aircraft", 12, DIM)
    return L.fade(img, _fade_in(t))


# ---------------------------------------------------------------------------------------------------------------- network

def _destinations(hub: dict, limit_km: float = 7500.0) -> List[dict]:
    out = []
    for a in C.all_airports():
        if a["id"] == hub["id"]:
            continue
        km = F.haversine_km((hub["lat"], hub["lon"]), (a["lat"], a["lon"]))
        if 300 < km < limit_km:
            out.append((km, a))
    return [a for _, a in sorted(out, key=lambda x: x[0])]


def lay_network(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    hub = C.get_airport(str(p.get("hub") or "").upper())
    if not hub:
        return None
    dests = _destinations(hub)
    if not dests:
        return None
    pts = [(hub["lat"], hub["lon"])] + [(a["lat"], a["lon"]) for a in dests]
    bb = B.fit_bbox(pts, pad=0.08)
    k = M.ease_in_out(M.clamp01(t / max(dur, 0.1)))
    view = B.scale_bbox(bb, 1.0 - 0.04 * k)
    base = B.relief(B.scale_bbox(bb, 1.1), (int(W * 1.1), int(H * 1.1)), p.get("fetch_tile"), p.get("cache"))
    bx0, by0, bx1, by1 = B.bbox_merc(B.scale_bbox(bb, 1.1))
    vx0, vy0, vx1, vy1 = B.bbox_merc(view)
    bw, bh = base.size
    box = ((vx0 - bx0) / (bx1 - bx0) * bw, (vy0 - by0) / (by1 - by0) * bh, (vx1 - bx0) / (bx1 - bx0) * bw, (vy1 - by0) / (by1 - by0) * bh)
    img = base.transform((W, H), Image.EXTENT, box, Image.BILINEAR).convert("RGBA")
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    hx, hy = B.to_px(view, hub["lat"], hub["lon"], W, H)
    for i, a in enumerate(dests):
        st = 0.3 + 2.2 * i / max(1, len(dests))
        f = M.ease_out(M.ramp(t, st, 0.7))
        if f <= 0:
            continue
        ax, ay = B.to_px(view, a["lat"], a["lon"], W, H)
        curve = F.leg_curve((hx, hy), (ax, ay), bend=0.08 if i % 2 else -0.08, n=24)
        part = F._poly_partial(curve, f)
        if len(part) > 1:
            d.line(part, fill=(242, 184, 64, 170), width=2)
        if f >= 1.0:
            d.ellipse([ax - 3, ay - 3, ax + 3, ay + 3], fill=WHITE)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([hx - 26, hy - 26, hx + 26, hy + 26], fill=(242, 184, 64, 160))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    img.alpha_composite(over)
    d = ImageDraw.Draw(img)
    d.ellipse([hx - 7, hy - 7, hx + 7, hy + 7], fill=GOLD, outline=WHITE, width=2)
    d.text((hx + 14, hy - 12), hub["city"].upper(), font=T.font("bold", 22), fill=WHITE)
    n = int(p.get("count") or len(dests))
    kc = M.ease_out(M.ramp(t, 0.3, 2.2))
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle([50, 50, 400, 210], 14, fill=(8, 14, 40, 200))
    pd.text((76, 62), _num(n * kc) + ("+" if p.get("plus", True) else ""), font=T.font("display", 90), fill=WHITE)
    _label(pd, 80, 168, str(p.get("label") or "DESTINATIONS"), 18)
    img.alpha_composite(panel)
    ImageDraw.Draw(img).text((14, H - 18), B.CREDIT, font=T.font("regular", 10), fill=(150, 154, 164, 160))
    return L.fade(img, _fade_in(t))


# ---------------------------------------------------------------------------------------------------------------- seats

def seats_filled(pct: float, total: int) -> int:
    return int(round(total * max(0.0, min(100.0, pct)) / 100.0))


def lay_seats(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    if p.get("now") is None:
        return None
    now = float(p["now"])
    img = K.backdrop(t)
    d = ImageDraw.Draw(img)
    rows_, layout = 20, (3, 4, 3)                 # a widebody's 3-4-3 economy, seen from above
    total = rows_ * sum(layout)
    x0, y0, cw = 330, 250, 42
    # the fuselage
    d.rounded_rectangle([x0 - 60, y0 - 40, x0 + rows_ * cw + 60, y0 + 12 * 22 + 40], 120, fill=(230, 234, 244, 40), outline=(230, 234, 244, 120), width=2)
    fill_to = seats_filled(now * M.ease_out(M.ramp(t, 0.3, 1.8)), total)
    i = 0
    for r_ in range(rows_):
        y = y0
        for b, block in enumerate(layout):
            for s_ in range(block):
                full = i < fill_to
                d.rounded_rectangle([x0 + r_ * cw, y, x0 + r_ * cw + cw - 10, y + 18], 4,
                                    fill=GOLD if full else (90, 110, 190, 255))
                i += 1
                y += 22
            y += 18                               # an aisle
    k = M.ease_out(M.ramp(t, 0.3, 1.8))
    d.text((80, 70), f"{now * k:.0f}%", font=T.font("display", 110), fill=WHITE)
    _label(d, 330, 120, str(p.get("label") or "SEATS FILLED"), 20)
    if p.get("before") is not None:
        _label(d, 330, 150, f"{float(p['before']):g}% a year earlier", 15, DIM)
    return L.fade(img, _fade_in(t))


# ---------------------------------------------------------------------------------------------------------------- change

def money(v: float, cur: str = "USD") -> str:
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(cur or "", "")
    if abs(v) >= 1e9:
        return f"{sym}{v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"{sym}{v / 1e6:.1f}M"
    return f"{sym}{v:,.0f}"


def change_tag(before: float, after: float) -> str:
    if not before:
        return ""
    pct = (after - before) / abs(before) * 100.0
    return f"{'+' if pct > 0 else '-'}{abs(pct):.0f}%"


def lay_change(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    if p.get("before") is None or p.get("after") is None:
        return None
    a, b = float(p["before"]), float(p["after"])
    cur = str(p.get("currency") or "")
    img = K.backdrop(t)
    d = ImageDraw.Draw(img)
    top = max(abs(a), abs(b)) or 1.0
    base_y, max_h, bw = 600, 380, 170
    for i, (v, lab, col) in enumerate(((a, str(p.get("before_label") or "BEFORE"), (200, 208, 230, 255)),
                                       (b, str(p.get("after_label") or "NOW"), RED if b < a else GREEN))):
        k = M.ease_out(M.ramp(t, 0.3 + 0.6 * i, 0.9))
        h = max_h * abs(v) / top * k
        x = 430 + i * 300
        d.rounded_rectangle([x, base_y - h, x + bw, base_y], 10, fill=col)
        if k > 0.05:
            txt = money(v * k, cur) if cur else _num(v * k, 1 if abs(v) < 100 else 0)
            tw = d.textlength(txt, font=T.font("display", 48))
            d.text((x + bw / 2 - tw / 2, base_y - h - 60), txt, font=T.font("display", 48), fill=WHITE)
        lw = L.spaced_width(d, lab.upper(), T.font("bold", 15), 0.16)
        _label(d, x + bw / 2 - lw / 2, base_y + 16, lab, 15, DIM)
    tag = change_tag(a, b)
    kt = M.ease_out(M.ramp(t, 1.6, 0.4))
    if tag and kt > 0:
        pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        f = T.font("display", 54)
        tw = pd.textlength(tag, font=f)
        pd.rounded_rectangle([960, 220, 960 + tw + 40, 300], 12, fill=RED if b < a else GREEN)
        pd.text((980, 228), tag, font=f, fill=WHITE)
        img.alpha_composite(L.fade(pill, kt))
    _label(d, 80, 90, str(p.get("label") or ""), 26)
    return L.fade(img, _fade_in(t))


# ---------------------------------------------------------------------------------------------------------------- big number

def lay_big_number(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    if p.get("value") is None:
        return None
    v = float(p["value"])
    img = K.backdrop(t)
    d = ImageDraw.Draw(img)
    k = M.ease_out(M.ramp(t, 0.3, 1.2))
    unit, sign = str(p.get("unit") or ""), str(p.get("sign") or "")
    if unit in ("USD", "EUR", "GBP"):
        txt = sign + money(v * k, unit)
    else:
        txt = f"{sign}{v * k:,.{1 if v < 10 and v != int(v) else 0}f}{unit}"
    d.text((90, 210), txt, font=T.font("display", 170), fill=GOLD if sign == "+" else (RED if sign == "-" else WHITE))
    _label(d, 96, 420, str(p.get("label") or ""), 26, WHITE)
    # the aircraft drawing glides in from the right
    kx = M.ease_out(M.ramp(t, 0.2, 1.4))
    from .gfx import _side_plane
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _side_plane(ImageDraw.Draw(lay), 1300 - 330 * kx, 330, 2.4, tail=tuple(p.get("tail") or (120, 130, 150, 255)))
    if str(p.get("icon")) == "freighter":
        ld = ImageDraw.Draw(lay)
        for j in range(4):                              # cargo pallets under the freighter
            x = 1300 - 330 * kx - 120 + j * 62
            ld.rounded_rectangle([x, 410, x + 52, 452], 4, fill=(200, 160, 90, 255), outline=(120, 90, 50, 255), width=2)
    img.alpha_composite(lay)
    return L.fade(img, _fade_in(t))


# ---------------------------------------------------------------------------------------------------------------- timeline

def lay_timeline(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    if not p.get("from_year") or not p.get("to_year"):
        return None
    y0, y1 = int(p["from_year"]), int(p["to_year"])
    if y1 <= y0:
        return None
    img = K.backdrop(t)
    d = ImageDraw.Draw(img)
    x0, x1, ly = 120, 1160, 420
    d.line([(x0, ly), (x1, ly)], fill=(200, 210, 240, 200), width=3)
    step = 5 if y1 - y0 <= 50 else 10
    for yr in range((y0 // step + 1) * step, y1 + 1, step):
        x = x0 + (x1 - x0) * (yr - y0) / (y1 - y0)
        d.line([(x, ly - 10), (x, ly + 10)], fill=(200, 210, 240, 200), width=2)
        d.text((x - 20, ly + 18), str(yr), font=T.font("bold", 16), fill=DIM)
    for yr, col in ((y0, GOLD), (y1, WHITE)):
        x = x0 + (x1 - x0) * (yr - y0) / (y1 - y0)
        d.ellipse([x - 9, ly - 9, x + 9, ly + 9], fill=col)
        d.text((x - 34, ly + 44), str(yr), font=T.font("display", 40), fill=col)
    k = M.ease_in_out(M.ramp(t, 0.4, max(1.0, dur * 0.7)))
    x = x0 + (x1 - x0) * k
    d.line([(x0, ly), (x, ly)], fill=GOLD, width=5)
    _airliner(d, x, ly - 46, 64, 0.0)
    d.text((x - 46, ly - 140), str(int(round(y0 + (y1 - y0) * k))), font=T.font("display", 56), fill=WHITE)
    _label(d, 120, 110, str(p.get("label") or ""), 26)
    return L.fade(img, _fade_in(t))


# ================================================================================================================ borrowed from the Green Dot
# Aviation reference (Eastern 855): crew card, instrument gauge, runway diagram, approach side view, descent graphic, title card.

TEAL = (60, 220, 190, 255)
ORANGE = (240, 150, 50, 255)
NAVY = ((6, 10, 48), (14, 26, 90))


def _navy() -> Image.Image:
    g = Image.linear_gradient("L").resize((W, H))
    return Image.composite(Image.new("RGB", (W, H), NAVY[1]), Image.new("RGB", (W, H), NAVY[0]), g).convert("RGBA")


def tail_of(airline_id: str) -> Tuple[int, int, int, int]:
    a = C.get_airline(airline_id or "")
    for h in (a or {}).get("colors") or []:
        h = h.lstrip("#")
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if min(rgb) < 200:                                    # the livery's first real colour (white is every airliner)
            return rgb + (255,)
    return (120, 130, 150, 255)


def _silhouette(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
    d.rectangle([x, y, x + w, y + h], fill=(40, 46, 60, 255))
    d.ellipse([x + w * 0.3, y + h * 0.18, x + w * 0.7, y + h * 0.55], fill=(150, 156, 170, 255))
    d.pieslice([x + w * 0.12, y + h * 0.55, x + w * 0.88, y + h * 1.25], 180, 360, fill=(150, 156, 170, 255))


def lay_crew(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Overlay: portrait (the user's photo, else a silhouette) in a bracket frame, name / role, age, total hours, an 'on type' pill."""
    p = p or {}
    if not (p.get("hours") or p.get("age") or p.get("name")):
        return None
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    k = M.ease_out(M.ramp(t, 0.0, 0.5))
    x0, y0 = int(60 - 40 * (1 - k)), 440
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle([0, y0 - 40, 760, H], fill=(0, 0, 0, 110))
    lay.alpha_composite(shade.filter(ImageFilter.GaussianBlur(30)))
    photo = None
    if p.get("photo"):
        try:
            photo = Image.open(p["photo"]).convert("RGB").resize((110, 136))
        except Exception:  # noqa: BLE001
            photo = None
    if photo is not None:
        lay.paste(photo.convert("L").convert("RGBA"), (x0, y0))
    else:
        _silhouette(d, x0, y0, 110, 136)
    for (ax, ay, bx, by) in ((x0 - 8, y0 - 8, x0 + 18, y0 - 8), (x0 - 8, y0 - 8, x0 - 8, y0 + 18), (x0 + 118, y0 + 144, x0 + 92, y0 + 144),
                             (x0 + 118, y0 + 144, x0 + 118, y0 + 118)):
        d.line([(ax, ay), (bx, by)], fill=WHITE, width=2)
    tx = x0 + 140
    role = str(p.get("role") or "").upper()
    name = str(p.get("name") or "").upper()
    head = (name or role) + (f" ({int(p['age'])})" if p.get("age") else "")
    d.text((tx, y0 + 2), head, font=T.font("bold", 26), fill=WHITE)
    if name and role:
        _label(d, tx, y0 + 36, role, 12, DIM)
    if p.get("hours"):
        kh = M.ease_out(M.ramp(t, 0.4, 1.0))
        d.text((tx, y0 + 62), f"{int(p['hours']) * kh:,.0f} HRS", font=T.font("display", 40), fill=WHITE)
        _label(d, tx, y0 + 108, "total experience", 11, DIM)
    if p.get("on_type"):
        kp = M.ease_out(M.ramp(t, 1.2, 0.4))
        if kp > 0:
            px = tx + 230
            txt = f"{int(p['on_type']):,} HRS"
            d.rounded_rectangle([px, y0 + 64, px + d.textlength(txt, font=T.font("bold", 24)) + 24, y0 + 100], 6, outline=TEAL, width=2)
            d.text((px + 12, y0 + 68), txt, font=T.font("bold", 24), fill=TEAL)
            _label(d, px, y0 + 108, str(p.get("on_type_label") or "on type"), 11, DIM)
    return L.fade(lay, k)


def needle_angle(v: float, lo: float, hi: float) -> float:
    """Degrees (0 = 3 o'clock, clockwise) for a 270-degree dial that starts at the lower left."""
    return 135.0 + 270.0 * (max(lo, min(hi, v)) - lo) / max(1e-6, hi - lo)


def lay_gauge(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Full frame: one round instrument, its needle swinging to the value; the bottom 20 % of the scale red."""
    p = p or {}
    if p.get("value") is None:
        return None
    v, hi = float(p["value"]), float(p.get("max") or max(1.0, float(p["value"]) * 2))
    img = Image.new("RGBA", (W, H), (22, 24, 28, 255))
    vg = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vg).ellipse([140, -120, 1140, 840], fill=255)
    img = Image.composite(Image.new("RGBA", (W, H), (52, 56, 64, 255)), img, vg.filter(ImageFilter.GaussianBlur(160)))
    d = ImageDraw.Draw(img)
    cx, cy, r = 640, 370, 250
    d.ellipse([cx - r - 18, cy - r - 18, cx + r + 18, cy + r + 18], fill=(70, 74, 82, 255))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(12, 13, 16, 255))
    d.arc([cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14], 135, 135 + 270 * 0.2, fill=(220, 50, 50, 255), width=14)
    for i in range(11):
        a = math.radians(135 + 27 * i)
        d.line([(cx + (r - 40) * math.cos(a), cy + (r - 40) * math.sin(a)), (cx + (r - 14) * math.cos(a), cy + (r - 14) * math.sin(a))],
               fill=WHITE, width=4)
        lab = f"{hi * i / 10 / (1000 if hi >= 10000 else 1):.0f}"
        tw = d.textlength(lab, font=T.font("bold", 22))
        d.text((cx + (r - 70) * math.cos(a) - tw / 2, cy + (r - 70) * math.sin(a) - 12), lab, font=T.font("bold", 22), fill=WHITE)
    k = M.ease_in_out(M.ramp(t, 0.3, 1.6))
    start = float(p.get("from") if p.get("from") is not None else hi)
    a = math.radians(needle_angle(start + (v - start) * k, 0.0, hi))
    d.line([(cx, cy), (cx + (r - 50) * math.cos(a), cy + (r - 50) * math.sin(a))], fill=(245, 150, 60, 255), width=8)
    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(80, 84, 92, 255))
    unit = str(p.get("unit") or "")
    readout = f"{start + (v - start) * k:,.0f} {unit}".strip()
    tw = d.textlength(readout, font=T.font("display", 46))
    d.rounded_rectangle([cx - tw / 2 - 14, cy + 90, cx + tw / 2 + 14, cy + 150], 6, fill=(0, 0, 0, 255), outline=(90, 94, 100, 255))
    d.text((cx - tw / 2, cy + 94), readout, font=T.font("display", 46), fill=(245, 150, 60, 255))
    _label(d, cx - L.spaced_width(d, str(p.get("label") or "").upper(), T.font("bold", 18), 0.16) / 2, cy - 110, str(p.get("label") or ""), 18, WHITE)
    return L.fade(img, _fade_in(t))


def runway_ends(rwy: str) -> Tuple[str, str]:
    m = re.match(r"(\d{1,2})([LRC]?)", str(rwy).upper())
    if not m:
        return str(rwy), ""
    n = int(m.group(1))
    other = (n + 18) % 36 or 36
    side = {"L": "R", "R": "L"}.get(m.group(2), m.group(2))
    return f"{n:02d}{m.group(2)}", f"{other:02d}{side}"


def lay_runway(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Full frame: the runway drawn to its heading with both ends' numbers, its length in a box, the approach track coming in."""
    p = p or {}
    if not p.get("runway"):
        return None
    end_a, end_b = runway_ends(str(p["runway"]))
    hd = math.radians(int(re.match(r"\d+", end_a).group(0)) * 10 - 90)        # screen angle of the landing direction
    img = Image.new("RGBA", (W, H), (20, 22, 26, 255))
    d = ImageDraw.Draw(img)
    for gx in range(0, W, 64):
        d.line([(gx, 0), (gx, H)], fill=(30, 33, 38, 255))
    for gy in range(0, H, 64):
        d.line([(0, gy), (W, gy)], fill=(30, 33, 38, 255))
    ux, uy = math.cos(hd), math.sin(hd)
    half, wd = 220, 24
    cx, cy = 640 + ux * 150, 370 + uy * 150                 # pushed toward the far end: the approach side has room in the frame
    nx, ny = -uy, ux
    k = M.ease_out(M.ramp(t, 0.2, 0.8))
    poly = [(cx - ux * half * k + nx * wd, cy - uy * half * k + ny * wd), (cx + ux * half * k + nx * wd, cy + uy * half * k + ny * wd),
            (cx + ux * half * k - nx * wd, cy + uy * half * k - ny * wd), (cx - ux * half * k - nx * wd, cy - uy * half * k - ny * wd)]
    d.polygon([(x, y) for x, y in poly], fill=(70, 74, 80, 255), outline=(200, 204, 214, 255))
    for i in range(-8, 9, 2):
        a0, a1 = i / 10 * half * k, (i + 1) / 10 * half * k
        d.line([(cx + ux * a0, cy + uy * a0), (cx + ux * a1, cy + uy * a1)], fill=WHITE, width=3)
    if k > 0.9:
        for lab, sgn in ((end_a, -1), (end_b, 1)):
            x, y = cx + sgn * ux * (half + 40), cy + sgn * uy * (half + 40)
            tw = d.textlength(lab, font=T.font("display", 36))
            d.text((x - tw / 2, y - 22), lab, font=T.font("display", 36), fill=WHITE)
    # the approach: a teal track from far out to the threshold of the landing end, the aircraft on it
    ka = M.ease_in_out(M.ramp(t, 0.8, max(1.5, dur * 0.55)))
    sx, sy = cx - ux * half, cy - uy * half
    room = min(260.0, *[v for v in ((W - 40 - sx) / ux if ux > 0 else (sx - 40) / -ux if ux < 0 else 1e9,
                                    (H - 40 - sy) / uy if uy > 0 else (sy - 40) / -uy if uy < 0 else 1e9) if v > 0] or [260.0])
    fx, fy = sx - ux * room, sy - uy * room                  # the approach starts inside the frame, so it is seen
    hx, hy = fx + (sx - fx) * ka, fy + (sy - fy) * ka
    d.line([(fx, fy), (hx, hy)], fill=TEAL, width=4)
    _airliner(d, hx, hy, 46, hd)
    if p.get("length_m"):
        txt = f"RWY {end_a} = {int(p['length_m']):,}M"
        kb = M.ease_out(M.ramp(t, 1.0, 0.4))
        box = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        tw = bd.textlength(txt, font=T.font("bold", 28))
        bd.rounded_rectangle([60, 60, 60 + tw + 32, 110], 8, fill=(240, 240, 244, 230))      # top-left: never over the runway
        bd.text((76, 68), txt, font=T.font("bold", 28), fill=(20, 22, 26, 255))
        img.alpha_composite(L.fade(box, kb))
    ap = C.get_airport(str(p.get("airport") or ""))
    if ap:
        d.ellipse([60, 646, 74, 660], fill=TEAL)
        d.text((84, 640), ap["name"], font=T.font("bold", 20), fill=WHITE)
    return L.fade(img, _fade_in(t))


def lay_approach(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Full frame, side view: the green glide-slope wedge to the runway, the aircraft coming down it, coloured height lines."""
    p = p or {}
    if p.get("from_ft") is None:
        return None
    a_ft, b_ft = float(p["from_ft"]), float(p.get("to_ft") or 0.0)
    top = max(a_ft, b_ft, *[float(x) for x in p.get("lines") or [0]]) * 1.25 or 1.0
    img = _navy()
    d = ImageDraw.Draw(img)
    gy, gx = 640, 1150                                       # the ground line and the touchdown point
    y_of = lambda ft: gy - (gy - 90) * ft / top
    wedge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(wedge).polygon([(gx, gy), (80, y_of(top * 0.92)), (80, y_of(top * 0.72))], fill=(40, 200, 120, 90))
    img.alpha_composite(wedge)
    d.line([(60, gy), (W - 60, gy)], fill=(220, 224, 236, 255), width=3)
    for ft, col in zip(sorted(p.get("lines") or [], reverse=True), (ORANGE, (60, 220, 120, 255), WHITE)):
        y = y_of(float(ft))
        for x in range(80, W - 80, 24):
            d.line([(x, y), (x + 12, y)], fill=col, width=2)
        d.text((W - 220, y - 28), f"{int(ft):,}FT", font=T.font("bold", 22), fill=col)
    k = M.ease_in_out(M.ramp(t, 0.3, max(1.5, dur * 0.8)))
    ft_now = a_ft + (b_ft - a_ft) * k
    y = y_of(ft_now)
    x = 200 + (gx - 380) * k                                 # left to right, down the glide slope
    from .gfx import _side_plane
    _side_plane(d, x, y, 1.0, tail=tuple(p.get("tail") or (120, 130, 150, 255)))
    d.text((80, 90), f"{ft_now:,.0f} FT", font=T.font("display", 54), fill=WHITE)
    _label(d, 84, 156, str(p.get("label") or "approach"), 16, DIM)
    return L.fade(img, _fade_in(t))


def lay_descent(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Full frame: a dashed descent line on navy, the aircraft sliding down it, speed and vertical speed counting."""
    p = p or {}
    if p.get("fpm") is None:
        return None
    img = _navy()
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 120, 160, 1160, 600
    for i in range(0, 40):
        if i % 2:
            continue
        a, b = i / 40, (i + 1) / 40
        d.line([(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a), (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b)], fill=(90, 140, 230, 255), width=3)
    k = M.ease_in_out(M.ramp(t, 0.3, max(1.5, dur * 0.8)))
    from .gfx import _side_plane
    _side_plane(d, x0 + (x1 - x0) * k, y0 + (y1 - y0) * k - 10, 1.1, tail=tuple(p.get("tail") or (120, 130, 150, 255)))
    kc = M.ease_out(M.ramp(t, 0.3, 1.2))
    if p.get("speed_kt"):
        d.text((x0, y1 + 40), f"{float(p['speed_kt']) * kc:,.0f} KTS", font=T.font("display", 48), fill=WHITE)
    fpm = float(p["fpm"])
    d.text((x1 - 300, y1 + 40), f"{'-' if fpm < 0 else '+'}{abs(fpm) * kc:,.0f} FPM", font=T.font("display", 48),
           fill=RED if fpm < 0 else GREEN)
    return L.fade(img, _fade_in(t))


def lay_title(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Full frame: the airline and flight in big retro type over a bright sky (the reference's opening title)."""
    p = p or {}
    title = str(p.get("title") or "").strip().upper()
    if not title:
        return None
    g = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), (150, 200, 240)), Image.new("RGB", (W, H), (40, 110, 190)), g).convert("RGBA")
    clouds = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(clouds)
    import random as _r
    rng = _r.Random(855)
    for _ in range(26):
        x, y, r = rng.uniform(-100, W + 100) + t * 18, rng.uniform(380, 760), rng.uniform(60, 160)
        cd.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6], fill=(255, 255, 255, 140))
    img.alpha_composite(clouds.filter(ImageFilter.GaussianBlur(24)))
    k = M.ease_out(M.ramp(t, 0.2, 0.8))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    words = title.split()
    lines = [" ".join(words[:max(1, len(words) - 1)]), words[-1]] if len(words) > 1 else [title]
    y = 190
    for i, ln in enumerate(lines):
        f = T.font("display", 130 if i == 0 else 110)
        tw = d.textlength(ln, font=f)
        x = (W - tw) / 2
        d.text((x + 6, y + 6), ln, font=f, fill=(40, 30, 80, 200))
        d.text((x, y), ln, font=f, fill=(250, 140, 40, 255), stroke_width=4, stroke_fill=(255, 220, 120, 255))
        y += 140
    sub = str(p.get("sub") or "").upper()
    if sub:
        sw = L.spaced_width(d, sub, T.font("bold", 22), 0.3)
        L.spaced(d, ((W - sw) / 2, y + 20), sub, T.font("bold", 22), WHITE, 0.3)
    s = 1.12 - 0.12 * k
    lay = lay.resize((int(W * s), int(H * s)), Image.LANCZOS).crop((int((W * s - W) / 2), int((H * s - H) / 2),
                                                                     int((W * s - W) / 2) + W, int((H * s - H) / 2) + H))
    img.alpha_composite(L.fade(lay, k))
    return L.fade(img, _fade_in(t))
