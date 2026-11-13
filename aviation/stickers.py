"""Code-drawn stickers for the sticker-story look: the fallback for every Flow sticker. PIL only, no network, deterministic.
Every function returns an RGBA image with a transparent background (a fresh copy on each call, so callers may paint on it; the drawing
itself is cached with functools.lru_cache). Drawn at 2-3x and downsampled, so edges are smooth.

  die_cut(img, edge=10, shadow=True)       thick white outline following the alpha, soft drop shadow down-right, canvas padded
                                           by die_cut_pad(edge) px on every side so nothing clips (not cached: takes an image)
  sticker(img, edge=10)                    = die_cut(img, edge)
  aircraft(type_id, airline_id="", width=640)   side view, nose right, in the airline's livery (tail colour, cheatline); cropped
                                           to the drawing. Families: narrow wide jumbo regional turboprop old_jet propliner
  aircraft_family(type_id)                 catalog id / free text -> family name (unknown -> "narrow")
  livery(airline_id)                       {"tail": rgb, "accent": rgb, "main": rgb} from the catalog (neutral blue/gold if unknown)
  tail_mark(airline_id, size=160)          tail-fin shape in the livery colours with a small drawn emblem (never a real logo)
  flag(country, width=240)                 ISO-2 (any case) -> geometric flag, 3:2, rounded corners; unknown -> grey with the letters
  hand_flag(country, width=260, side="left")  cartoon hand/arm holding the flag on a short pole (side = which edge the arm enters)
  bubble(text, width=520, bold=(), tail="left")  white speech bubble, wrapped dark text, `bold` words on a yellow highlight;
                                           tail = left | right | none
  prop(kind, size=220)                     ticket timetable cash coins cargo globe building contract chart plane_icon route_icon
                                           crown handshake scissors (unknown kind -> rounded square with the word)
  FLAGS                                    the ISO-2 codes with a drawn flag
"""

from __future__ import annotations

import functools
import math
import zlib
from typing import Callable, Dict, List, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from cinematic_explainer.war import tokens as T

from . import catalog as C

W, H = T.W, T.H
INK = (28, 28, 36, 255)
WHITE = (255, 255, 255, 255)
YELLOW = (255, 208, 56, 255)


def _cached(maxsize: int = 256):
    def deco(fn):
        inner = functools.lru_cache(maxsize=maxsize)(fn)

        @functools.wraps(fn)
        def wrap(*a, **k):
            return inner(*a, **k).copy()

        wrap.cache_info = inner.cache_info
        wrap.cache_clear = inner.cache_clear
        return wrap
    return deco


def _rgb(hexs: str) -> Tuple[int, int, int]:
    h = hexs.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rgba(c, a: int = 255):
    return (int(c[0]), int(c[1]), int(c[2]), a)


def _canvas(w: int, h: int) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _down(im: Image.Image, ss: int) -> Image.Image:
    return im.resize((max(1, im.width // ss), max(1, im.height // ss)), Image.LANCZOS)


def _trim(im: Image.Image, pad: int = 2) -> Image.Image:
    bb = im.getchannel("A").point(lambda v: 255 if v > 6 else 0).getbbox()
    if not bb:
        return im
    x0, y0, x1, y1 = bb
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)
    return im.crop((x0, y0, x1, y1))


def _star(d, cx, cy, R, fill, n=5, inner=0.382, rot=-90.0):
    pts = []
    for i in range(n * 2):
        r = R if i % 2 == 0 else R * inner
        a = math.radians(rot + i * 180.0 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=fill)


def _rot(pts, cx, cy, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


# =================================================================================================================== die cut

def die_cut_pad(edge: int = 10) -> int:
    """Pixels die_cut adds on every side of the input."""
    edge = int(edge)
    off = max(3, int(edge * 0.6))
    blur = max(2, int(edge * 0.5))
    return edge + off + blur * 2 + 2


def die_cut(img: Image.Image, edge: int = 10, shadow: bool = True) -> Image.Image:
    img = img.convert("RGBA")
    edge = max(0, int(edge))
    pad = die_cut_pad(edge)
    w, h = img.width + 2 * pad, img.height + 2 * pad
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    base.paste(img, (pad, pad))
    a = base.getchannel("A").point(lambda v: 255 if v > 8 else 0)
    rim = a
    if edge > 0:
        for rad, n in ((edge, 28), (edge * 0.75, 20), (edge * 0.5, 14), (edge * 0.25, 8)):
            for i in range(n):
                ang = 2 * math.pi * i / n
                dx, dy = int(round(rad * math.cos(ang))), int(round(rad * math.sin(ang)))
                sh = ImageChops.offset(a, dx, dy)
                rim = ImageChops.lighter(rim, sh)
        rim = rim.filter(ImageFilter.GaussianBlur(0.7)).point(lambda v: 255 if v > 110 else int(v * 255 / 110) if v > 40 else 0)
        rim = ImageChops.lighter(rim, a)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        off = max(3, int(edge * 0.6))
        blur = max(2, int(edge * 0.5))
        sh = ImageChops.offset(rim, off, off).filter(ImageFilter.GaussianBlur(blur))
        sh = sh.point(lambda v: int(v * 0.5))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        layer.putalpha(sh)
        out = Image.alpha_composite(out, layer)
    white = Image.new("RGBA", (w, h), WHITE)
    white.putalpha(rim)
    out = Image.alpha_composite(out, white)
    return Image.alpha_composite(out, base)


def sticker(img: Image.Image, edge: int = 10) -> Image.Image:
    return die_cut(img, edge)


# ================================================================================================================== liveries

def _near_white(c) -> bool:
    return min(c) > 215


def livery(airline_id: str = "") -> Dict[str, Tuple[int, int, int]]:
    cols: List[Tuple[int, int, int]] = []
    e = C.get_airline(airline_id) if airline_id else None
    if e:
        for h in e.get("colors", []):
            try:
                cols.append(_rgb(h))
            except (ValueError, IndexError):
                pass
    solid = [c for c in cols if not _near_white(c)]
    if not solid:
        tail = (80, 90, 110) if cols else (43, 90, 170)
        main = cols[0] if cols else tail
        accent = (240, 180, 50) if not cols else _mix(tail, (255, 255, 255), 0.35)
        return {"tail": tail, "accent": accent, "main": main}
    tail = solid[0]
    accent = next((c for c in solid[1:] if c != tail), None)
    if accent is None:
        accent = _mix(tail, (0, 0, 0), 0.35)
    return {"tail": tail, "accent": accent, "main": cols[0]}


# =================================================================================================================== aircraft

_FAMILY_IDS = {
    "dc3": "propliner", "dc4": "propliner", "dc6": "propliner", "dc7": "propliner", "c47": "propliner", "constellation": "propliner",
    "l049": "propliner", "l1049": "propliner", "l749": "propliner", "propliner": "propliner", "stratocruiser": "propliner",
    "b707": "old_jet", "boeing707": "old_jet", "707": "old_jet", "dc8": "old_jet", "comet": "old_jet", "decomet": "old_jet",
    "b720": "old_jet", "vc10": "old_jet", "convair880": "old_jet", "old_jet": "old_jet",
    "atr": "turboprop", "atr72": "turboprop", "atr42": "turboprop", "dash8": "turboprop", "q400": "turboprop", "dhc8": "turboprop",
    "dash7": "turboprop", "saab340": "turboprop", "turboprop": "turboprop", "f50": "turboprop", "an24": "turboprop",
    "e_jet": "regional", "ejet": "regional", "crj": "regional", "erj": "regional", "e175": "regional", "e190": "regional",
    "e195": "regional", "regional": "regional",
    "narrow": "narrow", "wide": "wide", "jumbo": "jumbo",
}
_FAMILIES = ("narrow", "wide", "jumbo", "regional", "turboprop", "old_jet", "propliner")


def aircraft_family(type_id: str) -> str:
    t = "".join(ch for ch in str(type_id or "").lower().replace("-", "").replace(" ", "") if ch.isalnum() or ch == "_")
    if t in _FAMILY_IDS:
        return _FAMILY_IDS[t]
    e = C.get_aircraft(str(type_id or "").lower().strip())
    if e:
        body = e.get("body", "narrow")
        if body in ("narrow", "wide", "jumbo", "regional"):
            return body
        return "narrow"
    for key, fam in (("a380", "jumbo"), ("747", "jumbo"), ("a330", "wide"), ("a340", "wide"), ("a350", "wide"), ("777", "wide"),
                     ("787", "wide"), ("767", "wide"), ("a300", "wide"), ("md11", "wide"), ("dc10", "wide"), ("l1011", "wide"),
                     ("atr", "turboprop"), ("dash8", "turboprop"), ("q400", "turboprop"), ("dhc", "turboprop"),
                     ("crj", "regional"), ("erj", "regional"), ("ejet", "regional"), ("dc3", "propliner"), ("dc8", "old_jet"),
                     ("707", "old_jet")):
        if key in t:
            return fam
    return "narrow"


# per-family drawing parameters (units: fractions of the sticker width; y grows downward; nose points right)
_FAM = {
    "narrow":    dict(r=.052, nose=.10, tail=.24, fin=.115, eng=.030, wing_y=.55, sweep=.16, down=.075, chord=.15, win=.0215),
    "wide":      dict(r=.062, nose=.11, tail=.26, fin=.140, eng=.040, wing_y=.55, sweep=.20, down=.090, chord=.18, win=.0225),
    "jumbo":     dict(r=.066, nose=.12, tail=.26, fin=.145, eng=.036, wing_y=.55, sweep=.20, down=.095, chord=.18, win=.0230),
    "regional":  dict(r=.048, nose=.09, tail=.24, fin=.105, eng=.026, wing_y=.55, sweep=.09, down=.060, chord=.13, win=.0205),
    "turboprop": dict(r=.048, nose=.07, tail=.25, fin=.120, eng=.024, wing_y=-.62, sweep=.04, down=.030, chord=.11, win=.0205),
    "old_jet":   dict(r=.040, nose=.11, tail=.26, fin=.125, eng=.022, wing_y=.55, sweep=.22, down=.105, chord=.12, win=.0200),
    "propliner": dict(r=.048, nose=.12, tail=.27, fin=.105, eng=.024, wing_y=.55, sweep=.07, down=.050, chord=.17, win=.0215),
}
_BODY_LIGHT = (246, 248, 252)
_METAL = (206, 212, 222)
_METAL_DK = (150, 158, 172)
_WINDOW = (34, 46, 70)


def _fuselage_pts(fam: str, p: dict, yc: float, hump: float, hump_len: float, tip_raise: float = 0.0):
    r, nl, tl = p["r"], p["nose"], p["tail"]
    x0, x1 = 0.045, 0.965
    ytip = yc + 0.15 * r
    top, bot = [], []
    n = 90
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        t, b = yc - r, yc + r
        if x < x0 + tl:
            u = (x - x0) / tl
            t = yc - r * (0.45 + 0.55 * u ** 0.6)
            b = yc + r * (-0.35 + 1.35 * u ** 0.8)
            if fam == "propliner":
                t = yc - r * (0.30 + 0.70 * u ** 0.55)
        if x > x1 - nl:
            v = (x - (x1 - nl)) / nl
            expo = 3.0 if fam in ("propliner", "turboprop") else 2.0
            s = max(0.0, 1 - v ** expo) ** (1.0 / expo)
            t = ytip - (ytip - (yc - r)) * s
            b = ytip + ((yc + r) - ytip) * s
        if hump > 0:
            hs = x1 - nl - hump_len - 0.02
            he = x1 - nl + 0.02
            if hs < x < he:
                u = (x - hs) / (he - hs)
                bump = math.sin(math.pi * u ** 0.75) ** 0.7
                t -= hump * bump
        top.append((x, t))
        bot.append((x, b))
    return top, list(reversed(bot))


def _poly(d, pts, U, fill, outline=None, width=0):
    pp = [(x * U, y * U) for x, y in pts]
    if outline is not None and width:
        d.polygon(pp, fill=fill, outline=outline, width=int(width))
    else:
        d.polygon(pp, fill=fill)


def _ell(d, cx, cy, rx, ry, U, fill, outline=None, width=0):
    box = [(cx - rx) * U, (cy - ry) * U, (cx + rx) * U, (cy + ry) * U]
    if outline is not None and width:
        d.ellipse(box, fill=fill, outline=outline, width=int(width))
    else:
        d.ellipse(box, fill=fill)


def _engine(im, d, U, cx, cy, ry, length, shade, front_col=(60, 68, 84), prop=None):
    """podded jet engine, nose right."""
    body = _mix(_METAL, (0, 0, 0), shade)
    rx = length / 2
    d.rounded_rectangle([(cx - rx) * U, (cy - ry) * U, (cx + rx) * U, (cy + ry) * U], radius=ry * U * 0.95, fill=_rgba(body),
                        outline=_rgba(_mix(body, (0, 0, 0), 0.25)), width=max(1, int(U * 0.0015)))
    hl = _mix(body, (255, 255, 255), 0.55)
    d.rounded_rectangle([(cx - rx * 0.8) * U, (cy - ry * 0.85) * U, (cx + rx * 0.55) * U, (cy - ry * 0.35) * U], radius=ry * U * 0.3,
                        fill=_rgba(hl, 150))
    # intake
    _ell(d, cx + rx - ry * 0.18, cy, ry * 0.42, ry * 0.92, U, _rgba(_mix(body, (0, 0, 0), 0.15)))
    _ell(d, cx + rx - ry * 0.16, cy, ry * 0.30, ry * 0.74, U, _rgba(front_col))
    _ell(d, cx + rx - ry * 0.12, cy, ry * 0.10, ry * 0.22, U, _rgba((190, 196, 208)))


def _draw_propeller(d, U, cx, cy, rad, blades=3, phase=0.0):
    """prop seen from the side: a faint disc + blade shapes."""
    d.ellipse([(cx - rad * 0.10) * U, (cy - rad) * U, (cx + rad * 0.10) * U, (cy + rad) * U], fill=(90, 96, 110, 55))
    for i in range(blades):
        a = phase + 2 * math.pi * i / blades
        ty = math.sin(a) * rad
        y0 = cy
        d.polygon([(cx * U, (y0 - 0.004) * U), ((cx + 0.004) * U, (y0 + 0.004) * U), ((cx + 0.002) * U, (cy + ty) * U)], fill=(40, 44, 54, 255))
    d.ellipse([(cx - 0.006) * U, (cy - 0.009) * U, (cx + 0.012) * U, (cy + 0.009) * U], fill=(200, 60, 50, 255))


def _wing(d, U, fam, p, yc, shade, xr=0.60, dy=0.0, dx=0.0):
    r = p["r"]
    yw = yc + p["wing_y"] * r + dy
    ch, sw, dn = p["chord"], p["sweep"], p["down"]
    col = _mix(_METAL, (0, 0, 0), shade)
    thick = 0.012 if fam in ("old_jet", "regional", "propliner") else 0.015
    if p["wing_y"] < 0:   # high wing: a thin flat wing sitting on the body, drawn down-and-back
        pts = [(xr + dx, yw), (xr - ch + dx, yw), (xr - ch - sw + dx, yw + dn), (xr - sw + dx, yw + dn)]
    else:
        pts = [(xr + dx, yw), (xr - ch + dx, yw), (xr - ch - sw + dx, yw + dn + thick), (xr - sw + dx, yw + dn + thick)]
    _poly(d, pts, U, _rgba(col), _rgba(_mix(col, (0, 0, 0), 0.25)), max(1, int(U * 0.0018)))
    # tip winglet for jets
    if fam in ("narrow", "wide", "jumbo") and p["wing_y"] > 0:
        tx, ty = xr - ch - sw + dx, yw + dn + thick
        _poly(d, [(tx + 0.012, ty), (tx + 0.002, ty), (tx - 0.004, ty - 0.035), (tx + 0.006, ty - 0.035)], U, _rgba(_mix(col, (0, 0, 0), 0.1)))
    return yw, pts


def _draw_aircraft(fam: str, tail_c, accent_c, main_c, width: int, big_hump: bool = False, dc3_gear: bool = False) -> Image.Image:
    ss = 3
    U = width * ss
    p = _FAM[fam]
    yc = 0.27
    r = p["r"]
    cw, ch = int(U * 1.04), int(U * 0.50)
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ox = 0.0
    hump = 0.0
    hump_len = 0.0
    if fam == "jumbo":
        hump = 0.030
        hump_len = 0.42 if big_hump else 0.15
    top, bot = _fuselage_pts(fam, p, yc, hump, hump_len)
    body_pts = top + bot
    tail_rgba, acc_rgba = _rgba(tail_c), _rgba(accent_c)
    edge = max(1, int(U * 0.0018))
    x0, tl, nl = 0.045, p["tail"], p["nose"]
    x1 = 0.965

    # --- far-side engines / props peeking behind the body (drawn first)
    if fam == "old_jet" or fam == "jumbo":
        for dx_, dy_ in ((0.045, -0.008), (-0.03, -0.012)):
            _engine(im, d, U, 0.57 + dx_ - 0.02, yc + r * 0.95 + dy_ + 0.002, p["eng"] * 0.9, 0.078, 0.42)
    # far stabiliser (above the tail, behind the fin)
    stab_y = yc - r * 0.15
    if fam in ("turboprop",) or fam == "regional":
        pass
    else:
        _poly(d, [(x0 + 0.23, stab_y - 0.03), (x0 + 0.13, stab_y - 0.03), (x0 + 0.045, stab_y - 0.075), (x0 + 0.10, stab_y - 0.075)], U,
              _rgba(_mix(_METAL, (0, 0, 0), 0.35)), None)

    # --- rear-mounted engines on the fuselage (regional)
    if fam == "regional":
        ex, ey = x0 + 0.205, yc - r * 0.15
        d.rounded_rectangle([(ex - 0.012) * U, (ey + 0.01) * U, (ex + 0.02) * U, (ey + 0.04) * U], radius=int(U * 0.004), fill=_rgba(_METAL_DK))
        _engine(im, d, U, ex - 0.005, ey + 0.045, p["eng"], 0.085, 0.0)

    # --- fuselage with livery
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).polygon([(x * U, y * U) for x, y in body_pts], fill=255)
    liv = Image.new("RGBA", (cw, ch), _rgba(_BODY_LIGHT))
    ld = ImageDraw.Draw(liv)
    # belly grey
    ld.rectangle([0, (yc + r * 0.50) * U, cw, ch], fill=_rgba(_mix(_BODY_LIGHT, (60, 70, 95), 0.22)))
    # cheatline band, rising at the tail
    by = yc + r * 0.18
    band = [(0.0, by - 0.012), (x1 + 0.01, by - 0.012), (x1 + 0.01, by + r * 0.20), (0.0, by + r * 0.20)]
    _poly(ld, band, U, acc_rgba)
    rise = [(x0, by - 0.012), (x0 + tl * 1.05, by - 0.012), (x0 + tl * 0.55, by - 0.012 - r * 0.2), (x0, by - 0.012 - r * 0.9)]
    _poly(ld, rise, U, acc_rgba)
    # tail section in the tail colour
    ld.rectangle([0, 0, (x0 + tl * 0.42) * U, ch], fill=tail_rgba)
    # nose radome tip a touch darker
    ld.rectangle([(x1 - 0.028) * U, 0, cw, ch], fill=_rgba(_mix(_BODY_LIGHT, (80, 90, 110), 0.18)))
    # shading
    grad = Image.linear_gradient("L").resize((cw, int(2 * r * U)))
    shade = Image.new("L", (cw, ch), 0)
    shade.paste(grad.point(lambda v: int(v * 0.30)), (0, int((yc - r) * U)))
    dark = Image.new("RGBA", (cw, ch), (10, 18, 50, 255))
    dark.putalpha(shade)
    liv = Image.alpha_composite(liv, dark)
    hi = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))
    ImageDraw.Draw(hi).rounded_rectangle([(x0 + tl * 0.8) * U, (yc - r * 0.92) * U, (x1 - nl * 0.9) * U, (yc - r * 0.70) * U],
                                          radius=int(r * U * 0.2), fill=(255, 255, 255, 90))
    liv = Image.alpha_composite(liv, hi)
    fus = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    fus.paste(liv, (0, 0), mask)
    im.alpha_composite(fus)
    d = ImageDraw.Draw(im)
    d.polygon([(x * U, y * U) for x, y in body_pts], outline=_rgba(_mix(_BODY_LIGHT, (40, 50, 80), 0.45)), width=edge)

    # --- vertical fin (tail colour + accent stripe)
    fh = p["fin"]
    ytb = yc - r * 0.55
    if fam == "propliner":
        fin = [(x0 + 0.24, ytb + 0.015), (x0 + 0.115, ytb - fh * 0.95), (x0 + 0.075, ytb - fh), (x0 + 0.035, ytb - fh * 0.80),
               (x0 + 0.005, yc - r * 0.35), (x0 + 0.01, ytb + 0.02)]
    else:
        fin = [(x0 + 0.245, ytb + 0.012), (x0 + 0.125, ytb - fh), (x0 + 0.065, ytb - fh), (x0 + 0.012, ytb - fh * 0.12),
               (x0 + 0.0, ytb + 0.02)]
    fl = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fl)
    _poly(fd, fin, U, tail_rgba)
    # accent chevron stripe across the fin
    sx = x0 + 0.10
    _poly(fd, [(sx + 0.04, ytb - fh * 0.20), (sx + 0.095, ytb - fh * 0.20), (sx + 0.05, ytb - fh * 0.60), (sx - 0.005, ytb - fh * 0.60)], U, acc_rgba)
    fm = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(fm).polygon([(x * U, y * U) for x, y in fin], fill=255)
    fin_img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    fin_img.paste(fl, (0, 0), fm)
    im.alpha_composite(fin_img)
    d = ImageDraw.Draw(im)
    d.polygon([(x * U, y * U) for x, y in fin], outline=_rgba(_mix(tail_c, (0, 0, 0), 0.35)), width=edge)
    if fam in ("turboprop", "regional"):
        # T-tail stabiliser on top of the fin
        sy = ytb - fh
        d.rounded_rectangle([(x0 + 0.015) * U, (sy - 0.006) * U, (x0 + 0.13) * U, (sy + 0.013) * U], radius=int(U * 0.006),
                            fill=_rgba(_mix(_METAL, (0, 0, 0), 0.05)), outline=_rgba(_METAL_DK), width=edge)
    else:
        _poly(d, [(x0 + 0.215, yc - r * 0.05), (x0 + 0.135, yc - r * 0.05), (x0 + 0.045, yc + r * 0.20 + 0.02), (x0 + 0.105, yc + r * 0.20 + 0.02)], U,
              _rgba(_mix(_METAL, (0, 0, 0), 0.08)), _rgba(_METAL_DK), edge)

    # --- near wing, pylon, engines
    xr = 0.62 if fam != "propliner" else 0.60
    if fam in ("narrow", "wide", "jumbo", "regional", "old_jet", "propliner"):
        yw, wpts = _wing(d, U, fam, p, yc, 0.0, xr)
    else:
        yw, wpts = _wing(d, U, fam, p, yc, 0.0, xr)
    er = p["eng"]
    if fam in ("narrow", "wide"):
        ex = xr - 0.035
        ey = yc + r * 0.95 + er * 0.35
        d.rounded_rectangle([(ex - 0.02) * U, (yw + 0.002) * U, (ex + 0.015) * U, (ey) * U], radius=int(U * 0.003), fill=_rgba(_METAL_DK))
        _engine(im, d, U, ex, ey, er, 0.095 if fam == "narrow" else 0.115, 0.0)
    elif fam in ("old_jet", "jumbo"):
        for ex, ey in ((xr - 0.10, yc + r * 0.95 + er * 1.45 + 0.012), (xr - 0.015, yc + r * 0.95 + er * 0.45)):
            d.rounded_rectangle([(ex - 0.018) * U, (yw + 0.002) * U, (ex + 0.012) * U, ey * U], radius=int(U * 0.003), fill=_rgba(_METAL_DK))
            _engine(im, d, U, ex, ey, er, 0.092 if fam == "old_jet" else 0.10, 0.0)
    elif fam == "turboprop":
        ex, ey = xr - 0.02, yw + 0.040
        d.rounded_rectangle([(ex - 0.06) * U, (ey - 0.020) * U, (ex + 0.075) * U, (ey + 0.020) * U], radius=int(U * 0.016),
                            fill=_rgba(_METAL), outline=_rgba(_METAL_DK), width=edge)
        d.rounded_rectangle([(ex - 0.055) * U, (ey - 0.017) * U, (ex + 0.04) * U, (ey - 0.004) * U], radius=int(U * 0.006), fill=(255, 255, 255, 120))
        _draw_propeller(d, U, ex + 0.078, ey, 0.082, 4, 0.5)
    elif fam == "propliner":
        for ex, ey, dxx in ((xr - 0.035, yw + 0.001, 0.0), (xr + 0.0 - 0.115, yw + 0.036, 0.0)):
            d.rounded_rectangle([(ex - 0.045) * U, (ey - 0.020) * U, (ex + 0.055) * U, (ey + 0.022) * U], radius=int(U * 0.014),
                                fill=_rgba(_mix(_METAL, (0, 0, 0), 0.04)), outline=_rgba(_METAL_DK), width=edge)
            d.ellipse([(ex + 0.050) * U, (ey - 0.019) * U, (ex + 0.064) * U, (ey + 0.021) * U], fill=_rgba(_METAL_DK))
            _draw_propeller(d, U, ex + 0.066, ey, 0.075, 3, 0.3 + ex)

    # --- windows, doors, cockpit
    wy = yc - r * 0.42
    wh = 0.0135 * (r / 0.046) ** 0.5
    ww = 0.0095
    xs = x0 + tl + 0.03
    xe = x1 - nl - 0.045
    sp = p["win"]
    x = xs
    skip = [(x1 - nl - 0.115, x1 - nl - 0.085)] if fam != "turboprop" else [(x1 - nl - 0.10, x1 - nl - 0.07)]
    while x < xe:
        if not any(a <= x <= b for a, b in skip):
            d.rounded_rectangle([x * U, (wy - wh / 2) * U, (x + ww) * U, (wy + wh / 2) * U], radius=int(ww * U * 0.45), fill=_rgba(_WINDOW))
        x += sp
    if fam == "jumbo":   # upper deck windows on the hump
        x = x1 - nl - (0.42 if big_hump else 0.15) + 0.02
        uy = yc - r - hump * 0.62
        while x < x1 - nl - 0.01:
            d.rounded_rectangle([x * U, (uy - 0.005) * U, (x + 0.008) * U, (uy + 0.007) * U], radius=int(U * 0.003), fill=_rgba(_WINDOW))
            x += 0.0195
    for a, b in skip:   # door outline
        d.rounded_rectangle([a * U, (wy - 0.021) * U, b * U + 0.0 * U, (yc + r * 0.48) * U], radius=int(U * 0.004), outline=_rgba(_mix(_BODY_LIGHT, (40, 50, 80), 0.5)), width=edge)
    # cockpit windows
    cx_ = x1 - nl * 0.62
    cy_ = yc - r * 0.60
    cock = [(cx_ - 0.004, cy_ - 0.003), (cx_ + 0.030, cy_ - 0.003), (cx_ + 0.044, cy_ + 0.014), (cx_ + 0.010, cy_ + 0.014)]
    if fam in ("propliner", "turboprop"):
        cock = [(cx_ - 0.004, cy_ - 0.004), (cx_ + 0.022, cy_ - 0.004), (cx_ + 0.034, cy_ + 0.016), (cx_ + 0.004, cy_ + 0.016)]
    _poly(d, cock, U, _rgba(_WINDOW))
    _poly(d, [(cock[0][0] + 0.004, cock[0][1] + 0.002), (cock[0][0] + 0.010, cock[0][1] + 0.002), (cock[3][0] + 0.003, cock[3][1] - 0.002), (cock[3][0] - 0.001, cock[3][1] - 0.002)],
          U, (255, 255, 255, 70))

    if dc3_gear:
        # tail wheel, main wheel (tail-dragger)
        d.ellipse([(x0 + 0.03) * U, (yc + r * 0.1 + 0.008) * U, (x0 + 0.05) * U, (yc + r * 0.1 + 0.028) * U], fill=INK)
        d.line([((x0 + 0.04) * U, (yc + r * 0.1) * U), ((x0 + 0.04) * U, (yc + r * 0.1 + 0.015) * U)], fill=INK, width=max(2, edge * 2))
        mx = xr - 0.07
        d.line([(mx * U, (yw + 0.02) * U), (mx * U, (yc + r + 0.065) * U)], fill=_rgba(_METAL_DK), width=max(2, edge * 3))
        d.ellipse([(mx - 0.020) * U, (yc + r + 0.045) * U, (mx + 0.020) * U, (yc + r + 0.085) * U], fill=INK)
        d.ellipse([(mx - 0.008) * U, (yc + r + 0.057) * U, (mx + 0.008) * U, (yc + r + 0.073) * U], fill=_rgba(_METAL))
    out = _down(im, ss)
    if dc3_gear:
        out = out.rotate(7, resample=Image.BICUBIC, expand=True)
    return _trim(out)


@_cached(128)
def _aircraft(fam: str, tail: tuple, accent: tuple, main: tuple, width: int, hump: bool, gear: bool) -> Image.Image:
    return _draw_aircraft(fam, tail, accent, main, width, hump, gear)


def aircraft(type_id: str, airline_id: str = "", width: int = 640) -> Image.Image:
    """Side view sticker body, nose right, cropped to the drawing (about `width` px wide, ~0.4 x that tall)."""
    fam = aircraft_family(type_id)
    t = "".join(ch for ch in str(type_id or "").lower() if ch.isalnum())
    lv = livery(airline_id)
    return _aircraft(fam, lv["tail"], lv["accent"], lv["main"], int(width), "a380" in t, t in ("dc3", "c47", "dc3dakota"))


# =================================================================================================================== tail mark

@_cached(128)
def _tail_mark(airline_id: str, size: int) -> Image.Image:
    lv = livery(airline_id)
    tail_c, acc = lv["tail"], lv["accent"]
    ss = 3
    S = size * ss
    im, d = _canvas(S, S)
    # swept fin on a short body stub
    fin = [(0.20, 0.86), (0.66, 0.06), (0.92, 0.06), (0.86, 0.86)]
    d.polygon([(x * S, y * S) for x, y in fin], fill=_rgba(tail_c))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon([(x * S, y * S) for x, y in fin], fill=255)
    art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ad = ImageDraw.Draw(art)
    kind = zlib.crc32(airline_id.encode("utf8")) % 4
    if kind == 0:     # ring
        ad.ellipse([0.40 * S, 0.30 * S, 0.80 * S, 0.70 * S], fill=_rgba(accent_or_white(acc)))
        ad.ellipse([0.48 * S, 0.38 * S, 0.72 * S, 0.62 * S], fill=_rgba(tail_c))
    elif kind == 1:   # diagonal stripes
        for i in range(3):
            ad.polygon([((0.10 + i * 0.17) * S, 0.90 * S), ((0.22 + i * 0.17) * S, 0.90 * S), ((0.62 + i * 0.17) * S, 0.0), ((0.50 + i * 0.17) * S, 0.0)],
                       fill=_rgba(acc if i % 2 == 0 else (250, 250, 252)))
    elif kind == 2:   # chevron
        ad.polygon([(0.2 * S, 0.60 * S), (0.55 * S, 0.30 * S), (0.95 * S, 0.30 * S), (0.60 * S, 0.60 * S)], fill=_rgba(acc))
        ad.polygon([(0.2 * S, 0.78 * S), (0.50 * S, 0.50 * S), (0.95 * S, 0.50 * S), (0.60 * S, 0.80 * S)], fill=(250, 250, 252, 255))
    else:             # star
        _star(ad, 0.60 * S, 0.48 * S, 0.24 * S, (250, 250, 252, 255), 5)
        ad.ellipse([0.54 * S, 0.42 * S, 0.66 * S, 0.54 * S], fill=_rgba(acc))
    art.putalpha(ImageChops.multiply(art.getchannel('A'), mask))
    im.alpha_composite(art)
    d = ImageDraw.Draw(im)
    d.polygon([(x * S, y * S) for x, y in fin], outline=_rgba(_mix(tail_c, (0, 0, 0), 0.4)), width=ss * 2)
    # body stub (white fuselage section)
    d.rounded_rectangle([0.04 * S, 0.80 * S, 0.98 * S, 0.96 * S], radius=int(0.05 * S), fill=_rgba(_BODY_LIGHT), outline=_rgba(_mix(_BODY_LIGHT, (40, 50, 80), 0.45)), width=ss * 2)
    d.rectangle([0.04 * S, 0.88 * S, 0.98 * S, 0.915 * S], fill=_rgba(acc))
    return _down(im, ss)


def accent_or_white(c):
    return c


def tail_mark(airline_id: str, size: int = 160) -> Image.Image:
    return _tail_mark(str(airline_id or ""), int(size))


# ====================================================================================================================== flags

def _hs(d, w, h, cols, wts=None):
    wts = wts or [1] * len(cols)
    tot = float(sum(wts))
    y = 0.0
    for c, k in zip(cols, wts):
        d.rectangle([0, y * h / tot, w, (y + k) * h / tot + 1], fill=c)
        y += k


def _vs(d, w, h, cols, wts=None):
    wts = wts or [1] * len(cols)
    tot = float(sum(wts))
    x = 0.0
    for c, k in zip(cols, wts):
        d.rectangle([x * w / tot, 0, (x + k) * w / tot + 1, h], fill=c)
        x += k


def _crescent(d, cx, cy, R, fg, bg, shift=0.32, inner=0.80):
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=fg)
    d.ellipse([cx - R + R * shift * 2, cy - R * inner, cx - R + R * shift * 2 + 2 * R * inner, cy + R * inner], fill=bg)


def _union_jack(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h), (1, 33, 105))
    d = ImageDraw.Draw(im)
    wt = (255, 255, 255)
    rd = (200, 16, 46)
    d.line([0, 0, w, h], fill=wt, width=int(h * 0.20))
    d.line([0, h, w, 0], fill=wt, width=int(h * 0.20))
    d.line([0, 0, w, h], fill=rd, width=int(h * 0.07))
    d.line([0, h, w, 0], fill=rd, width=int(h * 0.07))
    d.rectangle([0, h * 0.5 - h * 0.17, w, h * 0.5 + h * 0.17], fill=wt)
    d.rectangle([w * 0.5 - h * 0.17, 0, w * 0.5 + h * 0.17, h], fill=wt)
    d.rectangle([0, h * 0.5 - h * 0.10, w, h * 0.5 + h * 0.10], fill=rd)
    d.rectangle([w * 0.5 - h * 0.10, 0, w * 0.5 + h * 0.10, h], fill=rd)
    return im


RED = (206, 17, 38)
WH = (255, 255, 255)
BLU = (0, 40, 104)
GRN = (0, 122, 61)
YEL = (252, 209, 22)
BLK = (20, 20, 20)


def _f_sg(d, im, w, h):
    _hs(d, w, h, [(237, 41, 57), WH])
    _crescent(d, w * 0.19, h * 0.25, h * 0.17, WH, (237, 41, 57))
    for i in range(5):
        a = math.radians(-90 + i * 72)
        _star(d, w * 0.31 + h * 0.13 * math.cos(a), h * 0.25 + h * 0.13 * math.sin(a), h * 0.034, WH)


def _f_my(d, im, w, h):
    for i in range(14):
        d.rectangle([0, i * h / 14, w, (i + 1) * h / 14 + 1], fill=(204, 0, 1) if i % 2 == 0 else WH)
    d.rectangle([0, 0, w * 0.5, h * 8 / 14], fill=(1, 0, 102))
    _crescent(d, w * 0.19, h * 0.28, h * 0.19, YEL, (1, 0, 102))
    _star(d, w * 0.32, h * 0.28, h * 0.12, YEL, 14, 0.5)


def _f_gb(d, im, w, h):
    im.paste(_union_jack(w, h), (0, 0))


def _f_fr(d, im, w, h): _vs(d, w, h, [(0, 85, 164), WH, (239, 65, 53)])
def _f_nl(d, im, w, h): _hs(d, w, h, [(174, 28, 40), WH, (33, 70, 139)])
def _f_de(d, im, w, h): _hs(d, w, h, [BLK, (221, 0, 0), (255, 206, 0)])
def _f_it(d, im, w, h): _vs(d, w, h, [(0, 146, 70), WH, (206, 43, 55)])
def _f_ie(d, im, w, h): _vs(d, w, h, [(22, 155, 98), WH, (255, 136, 62)])
def _f_be(d, im, w, h): _vs(d, w, h, [BLK, (253, 218, 36), (239, 51, 64)])
def _f_at(d, im, w, h): _hs(d, w, h, [(237, 41, 57), WH, (237, 41, 57)])
def _f_pl(d, im, w, h): _hs(d, w, h, [WH, (220, 20, 60)])
def _f_ru(d, im, w, h): _hs(d, w, h, [WH, (0, 57, 166), (213, 43, 30)])
def _f_id(d, im, w, h): _hs(d, w, h, [(206, 17, 38), WH])
def _f_es(d, im, w, h): _hs(d, w, h, [(170, 21, 27), (241, 191, 0), (170, 21, 27)], [1, 2, 1])
def _f_th(d, im, w, h): _hs(d, w, h, [(165, 25, 49), WH, (45, 42, 74), WH, (165, 25, 49)], [1, 1, 2, 1, 1])
def _f_mx(d, im, w, h):
    _vs(d, w, h, [(0, 104, 71), WH, (206, 17, 38)])
    d.ellipse([w * 0.43, h * 0.36, w * 0.57, h * 0.64], fill=(150, 100, 50))
    d.ellipse([w * 0.455, h * 0.40, w * 0.545, h * 0.60], fill=(0, 104, 71))
def _f_ar(d, im, w, h):
    _hs(d, w, h, [(116, 172, 223), WH, (116, 172, 223)])
    d.ellipse([w * 0.44, h * 0.38, w * 0.56, h * 0.62], fill=(246, 180, 14))
    d.ellipse([w * 0.47, h * 0.43, w * 0.53, h * 0.57], fill=(255, 215, 90))
def _f_eg(d, im, w, h):
    _hs(d, w, h, [(206, 17, 38), WH, BLK])
    d.polygon([(w * 0.5, h * 0.36), (w * 0.56, h * 0.50), (w * 0.5, h * 0.64), (w * 0.44, h * 0.50)], fill=(193, 148, 30))
def _f_jp(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=WH)
    d.ellipse([w * 0.5 - h * 0.30, h * 0.5 - h * 0.30, w * 0.5 + h * 0.30, h * 0.5 + h * 0.30], fill=(188, 0, 45))
def _f_cn(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(222, 41, 16))
    _star(d, w * 0.17, h * 0.27, h * 0.17, YEL)
    for cx, cy in ((0.34, 0.12), (0.40, 0.22), (0.40, 0.35), (0.34, 0.45)):
        _star(d, w * cx, h * cy, h * 0.055, YEL)
def _f_hk(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(222, 41, 16))
    cx, cy = w * 0.5, h * 0.5
    for i in range(5):
        a = math.radians(-90 + i * 72)
        px, py = cx + h * 0.15 * math.cos(a), cy + h * 0.15 * math.sin(a)
        d.ellipse([px - h * 0.10, py - h * 0.10, px + h * 0.10, py + h * 0.10], fill=WH)
    d.ellipse([cx - h * 0.04, cy - h * 0.04, cx + h * 0.04, cy + h * 0.04], fill=(222, 41, 16))
def _f_kr(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=WH)
    cx, cy, R = w * 0.5, h * 0.5, h * 0.25
    d.pieslice([cx - R, cy - R, cx + R, cy + R], 180, 360, fill=(205, 46, 58))
    d.pieslice([cx - R, cy - R, cx + R, cy + R], 0, 180, fill=(0, 71, 160))
    d.ellipse([cx - R / 2, cy - R, cx + R / 2, cy], fill=(205, 46, 58))
    d.ellipse([cx - R / 2, cy, cx + R / 2, cy + R], fill=(0, 71, 160))
    for sx, sy, ang in ((-1, -1, 0.6), (1, -1, -0.6), (-1, 1, -0.6), (1, 1, 0.6)):
        bx, by = cx + sx * w * 0.30, cy + sy * h * 0.29
        for k in (-1, 0, 1):
            pts = [(bx - h * 0.09, by + k * h * 0.045 - h * 0.012), (bx + h * 0.09, by + k * h * 0.045 - h * 0.012),
                   (bx + h * 0.09, by + k * h * 0.045 + h * 0.012), (bx - h * 0.09, by + k * h * 0.045 + h * 0.012)]
            d.polygon(_rot(pts, bx, by, ang if sx * sy > 0 else -ang), fill=BLK)
def _f_ae(d, im, w, h):
    _hs(d, w, h, [(0, 115, 47), WH, BLK])
    d.rectangle([0, 0, w * 0.25, h], fill=(255, 0, 0))
def _f_qa(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(138, 21, 56))
    n = 9
    pts = [(0, 0), (w * 0.30, 0)]
    for i in range(n):
        y0 = h * i / n
        pts += [(w * 0.38, y0 + h / n * 0.5), (w * 0.30, y0 + h / n)]
    pts += [(0, h)]
    d.polygon(pts, fill=WH)
def _f_au(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(0, 0, 139))
    im.paste(_union_jack(int(w * 0.5), int(h * 0.5)), (0, 0))
    _star(d, w * 0.25, h * 0.75, h * 0.14, WH, 7, 0.45)
    for cx, cy, r in ((0.75, 0.22, 0.05), (0.62, 0.45, 0.05), (0.88, 0.45, 0.05), (0.75, 0.82, 0.05), (0.82, 0.58, 0.035)):
        _star(d, w * cx, h * cy, h * r, WH, 7 if r > .04 else 5, 0.45)
def _f_nz(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(0, 36, 125))
    im.paste(_union_jack(int(w * 0.5), int(h * 0.5)), (0, 0))
    for cx, cy in ((0.78, 0.25), (0.65, 0.50), (0.91, 0.50), (0.78, 0.82)):
        _star(d, w * cx, h * cy, h * 0.085, WH)
        _star(d, w * cx, h * cy, h * 0.06, (204, 20, 43))
def _f_us(d, im, w, h):
    for i in range(13):
        d.rectangle([0, i * h / 13, w, (i + 1) * h / 13 + 1], fill=(178, 34, 52) if i % 2 == 0 else WH)
    d.rectangle([0, 0, w * 0.42, h * 7 / 13], fill=(60, 59, 110))
    for r in range(5):
        for c in range(6 if r % 2 == 0 else 5):
            x = w * (0.035 + c * 0.07 + (0.035 if r % 2 else 0))
            y = h * (0.05 + r * 0.095)
            d.ellipse([x - h * 0.015, y - h * 0.015, x + h * 0.015, y + h * 0.015], fill=WH)
def _f_in(d, im, w, h):
    _hs(d, w, h, [(255, 153, 51), WH, (19, 136, 8)])
    cx, cy, R = w * 0.5, h * 0.5, h * 0.13
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(0, 0, 128), width=max(2, int(h * 0.012)))
    for i in range(12):
        a = math.radians(i * 30)
        d.line([cx, cy, cx + R * math.cos(a), cy + R * math.sin(a)], fill=(0, 0, 128), width=max(1, int(h * 0.006)))
def _f_ph(d, im, w, h):
    _hs(d, w, h, [(0, 56, 168), (206, 17, 38)])
    d.polygon([(0, 0), (w * 0.5, h * 0.5), (0, h)], fill=WH)
    d.ellipse([w * 0.06, h * 0.40, w * 0.06 + h * 0.20, h * 0.60], fill=YEL)
    for cx, cy in ((0.03, 0.08), (0.03, 0.92), (0.40, 0.5)):
        _star(d, w * cx + h * 0.04, h * cy, h * 0.04, YEL)
def _f_vn(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(218, 37, 29))
    _star(d, w * 0.5, h * 0.52, h * 0.30, YEL)
def _f_tr(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(227, 10, 23))
    _crescent(d, w * 0.38, h * 0.5, h * 0.25, WH, (227, 10, 23), 0.28, 0.80)
    _star(d, w * 0.56, h * 0.5, h * 0.09, WH)
def _f_pt(d, im, w, h):
    _vs(d, w, h, [(0, 102, 0), (255, 0, 0)], [2, 3])
    cx = w * 0.4
    d.ellipse([cx - h * 0.19, h * 0.31, cx + h * 0.19, h * 0.69], fill=YEL)
    d.ellipse([cx - h * 0.12, h * 0.38, cx + h * 0.12, h * 0.62], fill=(200, 30, 40))
    d.rectangle([cx - h * 0.06, h * 0.43, cx + h * 0.06, h * 0.57], fill=WH)
def _f_ch(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(218, 41, 28))
    d.rectangle([w * 0.5 - h * 0.09, h * 0.2, w * 0.5 + h * 0.09, h * 0.8], fill=WH)
    d.rectangle([w * 0.5 - h * 0.30, h * 0.41, w * 0.5 + h * 0.30, h * 0.59], fill=WH)
def _f_dk(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(198, 12, 48))
    d.rectangle([w * 0.28, 0, w * 0.28 + h * 0.13, h], fill=WH)
    d.rectangle([0, h * 0.435, w, h * 0.565], fill=WH)
def _f_se(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(0, 106, 167))
    d.rectangle([w * 0.28, 0, w * 0.28 + h * 0.13, h], fill=(254, 204, 0))
    d.rectangle([0, h * 0.435, w, h * 0.565], fill=(254, 204, 0))
def _f_no(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(186, 12, 47))
    d.rectangle([w * 0.27, 0, w * 0.27 + h * 0.21, h], fill=WH)
    d.rectangle([0, h * 0.395, w, h * 0.605], fill=WH)
    d.rectangle([w * 0.27 + h * 0.05, 0, w * 0.27 + h * 0.16, h], fill=(0, 32, 91))
    d.rectangle([0, h * 0.445, w, h * 0.555], fill=(0, 32, 91))
def _f_fi(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=WH)
    d.rectangle([w * 0.28, 0, w * 0.28 + h * 0.15, h], fill=(0, 53, 128))
    d.rectangle([0, h * 0.425, w, h * 0.575], fill=(0, 53, 128))
def _f_ca(d, im, w, h):
    _vs(d, w, h, [(216, 6, 33), WH, (216, 6, 33)], [1, 2, 1])
    half = [(0, -1), (0.17, -0.6), (0.4, -0.72), (0.33, -0.18), (0.62, -0.33), (0.55, -0.08), (0.92, 0.04), (0.47, 0.38), (0.52, 0.58), (0.1, 0.5), (0.08, 0.95)]
    pts = half + [(-x, y) for x, y in reversed(half)]
    S = h * 0.38
    d.polygon([(w * 0.5 + x * S, h * 0.5 + y * S) for x, y in pts], fill=(216, 6, 33))
def _f_br(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(0, 156, 59))
    d.polygon([(w * 0.5, h * 0.10), (w * 0.90, h * 0.5), (w * 0.5, h * 0.90), (w * 0.10, h * 0.5)], fill=(255, 223, 0))
    R = h * 0.24
    d.ellipse([w * 0.5 - R, h * 0.5 - R, w * 0.5 + R, h * 0.5 + R], fill=(0, 39, 118))
    d.arc([w * 0.5 - R * 0.95, h * 0.5 - R * 0.5, w * 0.5 + R * 0.95, h * 0.5 + R * 1.4], 200, 340, fill=WH, width=max(2, int(h * 0.035)))
def _f_za(d, im, w, h):
    _hs(d, w, h, [(224, 60, 49), (0, 20, 137)])
    for col, wd in ((WH, 0.22), ((0, 122, 77), 0.13)):
        k = int(h * wd)
        d.line([0, 0, w * 0.42, h * 0.5], fill=col, width=k)
        d.line([0, h, w * 0.42, h * 0.5], fill=col, width=k)
        d.line([w * 0.40, h * 0.5, w, h * 0.5], fill=col, width=k)
    d.polygon([(0, h * 0.14), (0, h * 0.86), (w * 0.34, h * 0.5)], fill=(255, 184, 28))
    d.polygon([(0, h * 0.22), (0, h * 0.78), (w * 0.26, h * 0.5)], fill=BLK)
def _f_sa(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(0, 106, 57))
    for i, (a, b) in enumerate(((0.22, 0.78), (0.30, 0.70), (0.26, 0.74))):
        d.rounded_rectangle([w * a, h * (0.30 + i * 0.075), w * b, h * (0.34 + i * 0.075)], radius=3, fill=WH)
    d.rounded_rectangle([w * 0.22, h * 0.68, w * 0.78, h * 0.72], radius=3, fill=WH)
    d.polygon([(w * 0.78, h * 0.66), (w * 0.84, h * 0.70), (w * 0.78, h * 0.74)], fill=WH)
def _f_pk(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(1, 65, 28))
    d.rectangle([0, 0, w * 0.25, h], fill=WH)
    _crescent(d, w * 0.62, h * 0.5, h * 0.28, WH, (1, 65, 28), 0.30, 0.80)
    _star(d, w * 0.72, h * 0.34, h * 0.09, WH)
def _f_lk(d, im, w, h):
    d.rectangle([0, 0, w, h], fill=(255, 190, 0))
    d.rectangle([w * 0.04, h * 0.06, w * 0.12, h * 0.94], fill=(0, 112, 74))
    d.rectangle([w * 0.12, h * 0.06, w * 0.20, h * 0.94], fill=(255, 114, 0))
    d.rectangle([w * 0.24, h * 0.06, w * 0.96, h * 0.94], fill=(141, 21, 58))
    d.rectangle([w * 0.25, h * 0.09, w * 0.95, h * 0.91], outline=(255, 190, 0), width=max(2, int(h * 0.02)))
    d.ellipse([w * 0.50, h * 0.32, w * 0.70, h * 0.60], fill=(255, 190, 0))
    d.polygon([(w * 0.44, h * 0.66), (w * 0.60, h * 0.55), (w * 0.76, h * 0.66)], fill=(255, 190, 0))


_FLAG_FNS: Dict[str, Callable] = {
    "SG": _f_sg, "MY": _f_my, "GB": _f_gb, "FR": _f_fr, "NL": _f_nl, "DE": _f_de, "US": _f_us, "IN": _f_in, "AE": _f_ae, "QA": _f_qa,
    "AU": _f_au, "JP": _f_jp, "CN": _f_cn, "HK": _f_hk, "KR": _f_kr, "TH": _f_th, "ID": _f_id, "PH": _f_ph, "VN": _f_vn, "TR": _f_tr,
    "IT": _f_it, "ES": _f_es, "PT": _f_pt, "IE": _f_ie, "CH": _f_ch, "AT": _f_at, "BE": _f_be, "DK": _f_dk, "SE": _f_se, "NO": _f_no,
    "FI": _f_fi, "PL": _f_pl, "RU": _f_ru, "CA": _f_ca, "BR": _f_br, "MX": _f_mx, "AR": _f_ar, "ZA": _f_za, "EG": _f_eg, "SA": _f_sa,
    "NZ": _f_nz, "PK": _f_pk, "LK": _f_lk,
}
FLAGS = tuple(sorted(_FLAG_FNS))


@_cached(128)
def _flag(code: str, width: int) -> Image.Image:
    ss = 2
    w = width * ss
    h = int(round(w * 2 / 3))
    im = Image.new("RGB", (w, h), (120, 125, 135))
    d = ImageDraw.Draw(im)
    fn = _FLAG_FNS.get(code)
    if fn:
        fn(d, im, w, h)
    else:
        d.rectangle([0, 0, w, h], fill=(120, 125, 135))
        f = T.font("heavy", int(h * 0.36))
        txt = (code or "?")[:3]
        bb = d.textbbox((0, 0), txt, font=f)
        d.text(((w - (bb[2] - bb[0])) / 2 - bb[0], (h - (bb[3] - bb[1])) / 2 - bb[1]), txt, font=f, fill=(245, 245, 248))
    rgba = im.convert("RGBA")
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(h * 0.06), fill=255)
    rgba.putalpha(m)
    ImageDraw.Draw(rgba).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(h * 0.06), outline=(0, 0, 0, 70), width=ss)
    return _down(rgba, ss)


def flag(country: str, width: int = 240) -> Image.Image:
    return _flag(str(country or "").strip().upper(), int(width))


# ================================================================================================================== hand flag

@_cached(64)
def _hand_flag(code: str, width: int, side: str) -> Image.Image:
    ss = 2
    S = width * ss
    fl = flag(code, int(width * 0.64)).resize((int(width * 0.64) * ss, int(round(width * 0.64 * 2 / 3)) * ss), Image.LANCZOS)
    Hh = int(S * 1.05)
    im, d = _canvas(S, Hh)
    px = int(S * 0.34)
    top = int(S * 0.04)
    bottom = int(S * 0.94)
    # pole
    d.rounded_rectangle([px - S * 0.012, top, px + S * 0.012, bottom], radius=int(S * 0.012), fill=(150, 104, 60, 255), outline=INK, width=ss * 2)
    d.ellipse([px - S * 0.025, top - S * 0.02, px + S * 0.025, top + S * 0.03], fill=YELLOW, outline=INK, width=ss * 2)
    # arm coming from the lower left to the pole, sleeve + hand
    skin, skin_dk, sleeve = (240, 190, 150, 255), (205, 150, 112, 255), (60, 90, 160, 255)
    hy = int(S * 0.74)
    arm = [(0, int(S * 1.04)), (0, int(S * 0.90)), (px - S * 0.03, hy + S * 0.02), (px - S * 0.03, hy + S * 0.15)]
    d.polygon(arm, fill=skin, outline=INK)
    d.line([(0, int(S * 1.04)), (px - S * 0.03, hy + S * 0.15)], fill=INK, width=ss * 2)
    d.line([(0, int(S * 0.90)), (px - S * 0.03, hy + S * 0.02)], fill=INK, width=ss * 2)
    cuff = [(0, int(S * 1.04)), (0, int(S * 0.90)), (S * 0.09, int(S * 0.90) + S * 0.045), (S * 0.09, int(S * 1.04) - S * 0.025)]
    d.polygon(cuff, fill=sleeve, outline=INK)
    d.polygon([(0, int(S * 1.04)), (0, int(S * 0.90)), (S * 0.04, int(S * 0.90) + S * 0.02), (S * 0.04, int(S * 1.04) - S * 0.01)], fill=sleeve)
    # fist around the pole: fingers stacked
    fx0, fx1 = px - S * 0.075, px + S * 0.06
    for i in range(4):
        y = hy - S * 0.005 + i * S * 0.040
        d.rounded_rectangle([fx0, y, fx1, y + S * 0.042], radius=int(S * 0.02), fill=skin, outline=INK, width=ss * 2)
    d.rounded_rectangle([fx0 - S * 0.02, hy + S * 0.01, px - S * 0.02, hy + S * 0.20], radius=int(S * 0.03), fill=skin_dk, outline=INK, width=ss * 2)
    d.ellipse([px - S * 0.005, hy - S * 0.045, px + S * 0.06, hy + S * 0.04], fill=skin, outline=INK, width=ss * 2)  # thumb
    if side == "right":
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    fw, fh = fl.size
    cloth = Image.new("RGBA", (fw, fh + int(S * 0.04)), (0, 0, 0, 0))
    for x in range(fw):
        k = x if side == "left" else fw - 1 - x
        dy = int(math.sin(k / fw * math.pi * 2) * S * 0.012)
        cloth.paste(fl.crop((x, 0, x + 1, fh)), (x, int(S * 0.02) + dy))
    cx0 = px + int(S * 0.012) if side == "left" else S - px - int(S * 0.012) - fw
    im.alpha_composite(cloth, (cx0, top + int(S * 0.02)))
    return _down(im, ss)


def hand_flag(country: str, width: int = 260, side: str = "left") -> Image.Image:
    """Arm enters from `side` (left: fist on the left, flag to the right; right: mirrored arm, the flag itself is never mirrored)."""
    return _hand_flag(str(country or "").strip().upper(), int(width), "right" if side == "right" else "left")


# ====================================================================================================================== bubble

@_cached(128)
def _bubble(text: str, width: int, bold: tuple, tail: str) -> Image.Image:
    ss = 2
    Wd = width * ss
    pad = int(Wd * 0.06)
    fs = max(14, int(Wd * 0.066))
    f_reg, f_bold = T.font("bold", fs), T.font("heavy", fs)
    boldset = {b.lower().strip(".,!?;:\"'()") for b in bold}
    words = str(text).split()
    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    space = probe.textlength(" ", font=f_reg)
    maxw = Wd - 2 * pad
    lines: List[List[Tuple[str, bool, float]]] = [[]]
    cur = 0.0
    for wd in words:
        isb = wd.lower().strip(".,!?;:\"'()") in boldset
        wl = probe.textlength(wd, font=f_bold if isb else f_reg)
        if lines[-1] and cur + space + wl > maxw:
            lines.append([])
            cur = 0.0
        cur += (space if lines[-1] else 0) + wl
        lines[-1].append((wd, isb, wl))
    lh = int(fs * 1.38)
    Hb = pad * 2 + lh * len(lines) - int(fs * 0.2)
    tail_h = int(Wd * 0.11) if tail in ("left", "right") else 0
    im, d = _canvas(Wd, Hb + tail_h)
    rad = int(min(Hb * 0.35, Wd * 0.09))
    d.rounded_rectangle([0, 0, Wd - 1, Hb - 1], radius=rad, fill=WHITE)
    if tail == "left":
        d.polygon([(Wd * 0.10, Hb - 4), (Wd * 0.24, Hb - 4), (Wd * 0.07, Hb + tail_h)], fill=WHITE)
    elif tail == "right":
        d.polygon([(Wd * 0.90, Hb - 4), (Wd * 0.76, Hb - 4), (Wd * 0.93, Hb + tail_h)], fill=WHITE)
    y = pad
    for ln in lines:
        x = pad
        for wd, isb, wl in ln:
            if isb:
                d.rounded_rectangle([x - fs * 0.15, y - fs * 0.02, x + wl + fs * 0.15, y + fs * 1.22], radius=int(fs * 0.25), fill=YELLOW)
                d.text((x, y), wd, font=f_bold, fill=INK)
            else:
                d.text((x, y), wd, font=f_reg, fill=(34, 38, 52, 255))
            x += wl + space
        y += lh
    return _down(im, ss)


def bubble(text: str, width: int = 520, bold: Sequence[str] = (), tail: str = "left") -> Image.Image:
    tail = tail if tail in ("left", "right", "none") else "left"
    if isinstance(bold, str):
        bold = (bold,)
    return _bubble(str(text), int(width), tuple(str(b) for b in bold), tail)


# ======================================================================================================================== props

_GREEN = (64, 168, 96, 255)
_GREEN_DK = (38, 118, 66, 255)
_BLUE = (66, 134, 232, 255)
_RED = (226, 70, 62, 255)
_PAPER = (250, 247, 238, 255)
_ORANGE = (244, 144, 44, 255)
_GREY = (150, 158, 172, 255)


def _o(ss):  # outline width
    return max(2, int(ss * 2))


def _prop_ticket(d, S, ss):
    pts = _rot([(S * 0.10, S * 0.28), (S * 0.90, S * 0.28), (S * 0.90, S * 0.72), (S * 0.10, S * 0.72)], S / 2, S / 2, math.radians(-8))
    d.polygon(pts, fill=_PAPER, outline=INK, width=_o(ss))
    c1 = _rot([(S * 0.10, S * 0.28), (S * 0.10, S * 0.72)], S / 2, S / 2, math.radians(-8))
    stripe = _rot([(S * 0.10, S * 0.28), (S * 0.90, S * 0.28), (S * 0.90, S * 0.40), (S * 0.10, S * 0.40)], S / 2, S / 2, math.radians(-8))
    d.polygon(stripe, fill=_BLUE, outline=INK, width=_o(ss))
    perf = _rot([(S * 0.68, S * 0.28), (S * 0.68, S * 0.72)], S / 2, S / 2, math.radians(-8))
    d.line(perf, fill=INK, width=_o(ss), joint="curve")
    for k in range(4):
        r1 = _rot([(S * 0.18, S * (0.48 + k * 0.05)), (S * (0.52 - k * 0.04), S * (0.48 + k * 0.05))], S / 2, S / 2, math.radians(-8))
        d.line(r1, fill=_GREY, width=ss * 3)
    for sx, sy in ((0.10, 0.28), (0.10, 0.72), (0.90, 0.28), (0.90, 0.72)):
        (cx, cy), = _rot([(S * sx, S * sy)], S / 2, S / 2, math.radians(-8))
        d.ellipse([cx - S * 0.03, cy - S * 0.03, cx + S * 0.03, cy + S * 0.03], fill=(0, 0, 0, 0))
    _plane_glyph(d, S * 0.80, S * 0.57, S * 0.075, _BLUE, -8)


def _plane_glyph(d, cx, cy, s, fill, deg=0.0, outline=None, ss=2):
    """top-view airliner pointing up, centred; s = half length."""
    base = [(0, -1.0), (0.10, -0.80), (0.12, -0.25), (0.95, 0.20), (0.95, 0.34), (0.12, 0.18), (0.10, 0.62), (0.38, 0.84),
            (0.38, 0.95), (0.0, 0.88), (-0.38, 0.95), (-0.38, 0.84), (-0.10, 0.62), (-0.12, 0.18), (-0.95, 0.34), (-0.95, 0.20),
            (-0.12, -0.25), (-0.10, -0.80)]
    pts = _rot([(cx + x * s, cy + y * s) for x, y in base], cx, cy, math.radians(deg))
    d.polygon(pts, fill=fill, outline=outline, width=_o(ss) if outline else 0)


def _prop_timetable(d, S, ss):
    d.rounded_rectangle([S * 0.10, S * 0.14, S * 0.90, S * 0.86], radius=int(S * 0.05), fill=(34, 40, 56, 255), outline=INK, width=_o(ss))
    d.rounded_rectangle([S * 0.10, S * 0.14, S * 0.90, S * 0.30], radius=int(S * 0.05), fill=YELLOW, outline=INK, width=_o(ss))
    d.rectangle([S * 0.10, S * 0.24, S * 0.90, S * 0.30], fill=YELLOW)
    d.line([S * 0.10, S * 0.30, S * 0.90, S * 0.30], fill=INK, width=_o(ss))
    for i in range(4):
        y = S * (0.38 + i * 0.12)
        d.rounded_rectangle([S * 0.16, y, S * 0.34, y + S * 0.07], radius=3, fill=(245, 245, 250, 255))
        d.rounded_rectangle([S * 0.38, y, S * 0.66, y + S * 0.07], radius=3, fill=(200, 205, 220, 255))
        d.rounded_rectangle([S * 0.70, y, S * 0.84, y + S * 0.07], radius=3, fill=_GREEN if i % 2 == 0 else _ORANGE)
    d.rounded_rectangle([S * 0.16, S * 0.18, S * 0.50, S * 0.26], radius=3, fill=INK)


def _prop_cash(d, S, ss):
    for k, (dx, dy, ang) in enumerate(((0.0, 0.18, -5), (0.02, 0.06, 3), (-0.02, -0.06, -2))):
        cx, cy = S * (0.5 + dx), S * (0.5 + dy)
        pts = _rot([(S * 0.14 + S * dx, S * 0.30 + S * dy), (S * 0.86 + S * dx, S * 0.30 + S * dy), (S * 0.86 + S * dx, S * 0.62 + S * dy), (S * 0.14 + S * dx, S * 0.62 + S * dy)], cx, cy, math.radians(ang))
        d.polygon(pts, fill=(112, 190, 124, 255) if k != 2 else (136, 208, 146, 255), outline=INK, width=_o(ss))
    cx, cy = S * 0.48, S * 0.44
    d.ellipse([cx - S * 0.12, cy - S * 0.12, cx + S * 0.12, cy + S * 0.12], fill=(166, 224, 172, 255), outline=INK, width=_o(ss))
    f = T.font("heavy", int(S * 0.15))
    d.text((cx, cy), "$", font=f, fill=_GREEN_DK, anchor="mm")
    d.rectangle([S * 0.40, S * 0.72, S * 0.60, S * 0.80], fill=(0, 0, 0, 0))
    band = [(S * 0.44, S * 0.18), (S * 0.56, S * 0.18), (S * 0.56, S * 0.76), (S * 0.44, S * 0.76)]
    d.polygon(band, fill=YELLOW, outline=INK, width=_o(ss))


def _prop_coins(d, S, ss):
    def stack(cx, base_y, n, rx):
        ry = rx * 0.38
        h = S * 0.075
        for i in range(n):
            y = base_y - i * h
            d.rectangle([cx - rx, y - h, cx + rx, y], fill=(226, 168, 36, 255))
            d.ellipse([cx - rx, y - ry, cx + rx, y + ry], fill=(226, 168, 36, 255), outline=INK, width=_o(ss))
            d.line([cx - rx, y - h, cx - rx, y], fill=INK, width=_o(ss))
            d.line([cx + rx, y - h, cx + rx, y], fill=INK, width=_o(ss))
        y = base_y - n * h
        d.ellipse([cx - rx, y - ry, cx + rx, y + ry], fill=YELLOW, outline=INK, width=_o(ss))
        d.ellipse([cx - rx * 0.6, y - ry * 0.6, cx + rx * 0.6, y + ry * 0.6], outline=(214, 150, 20, 255), width=ss * 2)
    stack(S * 0.30, S * 0.82, 4, S * 0.17)
    stack(S * 0.68, S * 0.86, 6, S * 0.17)
    stack(S * 0.49, S * 0.92, 2, S * 0.15)


def _prop_cargo(d, S, ss):
    d.rectangle([S * 0.06, S * 0.70, S * 0.94, S * 0.80], fill=(176, 130, 78, 255), outline=INK, width=_o(ss))
    for x in (0.12, 0.45, 0.78):
        d.rectangle([S * x, S * 0.80, S * (x + 0.10), S * 0.88], fill=(150, 108, 62, 255), outline=INK, width=_o(ss))
    d.rectangle([S * 0.10, S * 0.26, S * 0.90, S * 0.70], fill=_RED, outline=INK, width=_o(ss))
    for i in range(7):
        x = S * (0.15 + i * 0.105)
        d.rectangle([x, S * 0.29, x + S * 0.04, S * 0.67], fill=(190, 52, 46, 255))
    d.rectangle([S * 0.10, S * 0.26, S * 0.90, S * 0.30], fill=(150, 40, 36, 255), outline=INK, width=_o(ss))
    d.rectangle([S * 0.10, S * 0.66, S * 0.90, S * 0.70], fill=(150, 40, 36, 255), outline=INK, width=_o(ss))
    d.rectangle([S * 0.84, S * 0.30, S * 0.90, S * 0.66], fill=(150, 40, 36, 255), outline=INK, width=_o(ss))


def _prop_globe(d, S, ss):
    cx = cy = S / 2
    R = S * 0.38
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(70, 150, 230, 255))
    cont = Image.new("RGBA", (int(S), int(S)), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cont)
    cd.polygon([(S * .30, S * .30), (S * .44, S * .26), (S * .50, S * .36), (S * .42, S * .50), (S * .34, S * .56), (S * .26, S * .46)], fill=_GREEN)
    cd.polygon([(S * .55, S * .34), (S * .70, S * .30), (S * .76, S * .46), (S * .66, S * .56), (S * .58, S * .72), (S * .52, S * .54)], fill=_GREEN)
    cd.polygon([(S * .66, S * .66), (S * .74, S * .62), (S * .76, S * .70), (S * .68, S * .74)], fill=_GREEN)
    m = Image.new("L", (int(S), int(S)), 0)
    ImageDraw.Draw(m).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
    d._image.paste(cont, (0, 0), ImageChops.multiply(m, cont.getchannel("A")))
    for k in (-0.5, 0.0, 0.5):
        d.ellipse([cx - R * abs(1 - abs(k)) - 1, cy - R, cx + R * abs(1 - abs(k)) + 1, cy + R], outline=(255, 255, 255, 90), width=ss)
    d.line([cx - R, cy, cx + R, cy], fill=(255, 255, 255, 90), width=ss)
    d.ellipse([cx - R * 0.55, cy - R * 0.6, cx - R * 0.15, cy - R * 0.3], fill=(255, 255, 255, 60))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=INK, width=_o(ss) + 1)
    d.arc([cx - R * 1.15, cy - R * 0.45, cx + R * 1.15, cy + R * 0.45], 200, 340, fill=INK, width=_o(ss))
    d.polygon([(S * .50, S * .20), (S * .53, S * .26), (S * .47, S * .26)], fill=(0, 0, 0, 0))
    d.rounded_rectangle([cx - R * 0.45, cy + R * 1.04, cx + R * 0.45, cy + R * 1.18], radius=int(S * 0.02), fill=(90, 96, 112, 255), outline=INK, width=_o(ss))
    d.line([cx, cy + R, cx, cy + R * 1.05], fill=INK, width=_o(ss))


def _prop_building(d, S, ss):
    d.rectangle([S * 0.22, S * 0.14, S * 0.78, S * 0.88], fill=(128, 142, 168, 255), outline=INK, width=_o(ss))
    d.rectangle([S * 0.12, S * 0.40, S * 0.30, S * 0.88], fill=(150, 162, 186, 255), outline=INK, width=_o(ss))
    d.rectangle([S * 0.70, S * 0.34, S * 0.88, S * 0.88], fill=(150, 162, 186, 255), outline=INK, width=_o(ss))
    for r in range(8):
        for c in range(4):
            x = S * (0.27 + c * 0.12)
            y = S * (0.19 + r * 0.082)
            d.rectangle([x, y, x + S * 0.075, y + S * 0.05], fill=YELLOW if (r + c) % 3 == 0 else (206, 226, 250, 255))
    d.rectangle([S * 0.44, S * 0.80, S * 0.56, S * 0.88], fill=(60, 66, 86, 255), outline=INK, width=_o(ss))
    d.line([S * 0.50, S * 0.14, S * 0.50, S * 0.04], fill=INK, width=_o(ss))
    d.polygon([(S * 0.50, S * 0.04), (S * 0.64, S * 0.08), (S * 0.50, S * 0.12)], fill=_RED, outline=INK)


def _prop_contract(d, S, ss):
    pts = _rot([(S * 0.22, S * 0.10), (S * 0.78, S * 0.10), (S * 0.78, S * 0.90), (S * 0.22, S * 0.90)], S / 2, S / 2, math.radians(4))
    d.polygon(pts, fill=_PAPER, outline=INK, width=_o(ss))
    for i in range(6):
        ln = _rot([(S * 0.30, S * (0.22 + i * 0.075)), (S * (0.70 if i < 5 else 0.55), S * (0.22 + i * 0.075))], S / 2, S / 2, math.radians(4))
        d.line(ln, fill=_GREY, width=ss * 3)
    ln = _rot([(S * 0.30, S * 0.78), (S * 0.62, S * 0.78)], S / 2, S / 2, math.radians(4))
    d.line(ln, fill=INK, width=_o(ss))
    sig = [(S * 0.32, S * 0.74), (S * 0.38, S * 0.66), (S * 0.42, S * 0.76), (S * 0.47, S * 0.68), (S * 0.52, S * 0.76), (S * 0.58, S * 0.70)]
    d.line(_rot(sig, S / 2, S / 2, math.radians(4)), fill=(30, 70, 190, 255), width=ss * 3, joint="curve")
    (sx, sy), = _rot([(S * 0.68, S * 0.72)], S / 2, S / 2, math.radians(4))
    d.ellipse([sx - S * 0.07, sy - S * 0.07, sx + S * 0.07, sy + S * 0.07], fill=_RED, outline=INK, width=_o(ss))
    _star(d, sx, sy, S * 0.045, (255, 220, 200, 255))


def _prop_chart(d, S, ss):
    d.rounded_rectangle([S * 0.08, S * 0.12, S * 0.92, S * 0.88], radius=int(S * 0.06), fill=_PAPER, outline=INK, width=_o(ss))
    for i in range(4):
        y = S * (0.28 + i * 0.15)
        d.line([S * 0.16, y, S * 0.84, y], fill=(205, 210, 222, 255), width=ss * 2)
    pts = [(S * 0.16, S * 0.74), (S * 0.32, S * 0.62), (S * 0.46, S * 0.68), (S * 0.62, S * 0.46), (S * 0.80, S * 0.28)]
    d.line(pts, fill=_GREEN_DK, width=ss * 7, joint="curve")
    d.line(pts, fill=_GREEN, width=ss * 4, joint="curve")
    for x, y in pts:
        d.ellipse([x - S * 0.02, y - S * 0.02, x + S * 0.02, y + S * 0.02], fill=WHITE, outline=INK, width=ss)
    d.polygon([(S * 0.86, S * 0.20), (S * 0.86, S * 0.36), (S * 0.72, S * 0.28)], fill=_GREEN, outline=INK, width=ss * 2)


def _prop_plane_icon(d, S, ss):
    d.ellipse([S * 0.08, S * 0.08, S * 0.92, S * 0.92], fill=YELLOW, outline=INK, width=_o(ss))
    _plane_glyph(d, S * 0.5, S * 0.5, S * 0.30, INK, 45, None, ss)


def _prop_route_icon(d, S, ss):
    a, b = (S * 0.16, S * 0.74), (S * 0.84, S * 0.74)
    d.arc([S * 0.138, S * 0.411, S * 0.862, S * 1.411], 200, 340, fill=INK, width=ss * 7)
    for t in range(13):
        ang = math.radians(200 + 140 * t / 12)
        x = S * 0.5 + S * 0.362 * math.cos(ang)
        y = S * 0.911 + S * 0.5 * math.sin(ang)
        d.ellipse([x - S * 0.012, y - S * 0.012, x + S * 0.012, y + S * 0.012], fill=WHITE)
    for p_, col in ((a, _BLUE), (b, _RED)):
        d.ellipse([p_[0] - S * 0.09, p_[1] - S * 0.09, p_[0] + S * 0.09, p_[1] + S * 0.09], fill=col, outline=INK, width=_o(ss))
        d.ellipse([p_[0] - S * 0.03, p_[1] - S * 0.03, p_[0] + S * 0.03, p_[1] + S * 0.03], fill=WHITE)
    _plane_glyph(d, S * 0.5, S * 0.30, S * 0.13, YELLOW, 90, INK, ss)


def _prop_crown(d, S, ss):
    pts = [(S * .14, S * .74), (S * .10, S * .30), (S * .30, S * .50), (S * .50, S * .20), (S * .70, S * .50), (S * .90, S * .30), (S * .86, S * .74)]
    d.polygon(pts, fill=(246, 190, 40, 255), outline=INK, width=_o(ss))
    d.rectangle([S * .14, S * .74, S * .86, S * .84], fill=(226, 160, 24, 255), outline=INK, width=_o(ss))
    for x, y, c in ((.10, .30, _RED), (.50, .20, _BLUE), (.90, .30, _RED)):
        d.ellipse([S * x - S * .05, S * y - S * .05, S * x + S * .05, S * y + S * .05], fill=c, outline=INK, width=ss * 2)
    for x in (.30, .50, .70):
        d.ellipse([S * x - S * .03, S * .775, S * x + S * .03, S * .835], fill=(180, 240, 255, 255), outline=INK, width=ss)


def _prop_handshake(d, S, ss):
    d.polygon([(0, S * .26), (S * .24, S * .22), (S * .24, S * .76), (0, S * .72)], fill=(58, 86, 160, 255), outline=INK, width=_o(ss))
    d.polygon([(S, S * .26), (S * .76, S * .22), (S * .76, S * .76), (S, S * .72)], fill=(44, 50, 70, 255), outline=INK, width=_o(ss))
    skin, skin2 = (240, 192, 152, 255), (214, 160, 120, 255)
    d.polygon([(S * .22, S * .30), (S * .55, S * .28), (S * .70, S * .44), (S * .62, S * .62), (S * .22, S * .70)], fill=skin, outline=INK, width=_o(ss))
    d.polygon([(S * .78, S * .30), (S * .55, S * .28), (S * .40, S * .46), (S * .50, S * .66), (S * .78, S * .70)], fill=skin2, outline=INK, width=_o(ss))
    for i in range(4):
        x = S * (0.42 + i * 0.075)
        d.rounded_rectangle([x, S * (0.48 + (i % 2) * 0.01), x + S * 0.075, S * 0.70], radius=int(S * 0.03), fill=skin, outline=INK, width=_o(ss))
    d.rounded_rectangle([S * .30, S * .26, S * .58, S * .38], radius=int(S * .05), fill=skin2, outline=INK, width=_o(ss))
    d.rectangle([S * .20, S * .26, S * .26, S * .72], fill=WHITE, outline=INK, width=_o(ss))
    d.rectangle([S * .74, S * .26, S * .80, S * .72], fill=WHITE, outline=INK, width=_o(ss))


def _prop_scissors(d, S, ss):
    cx, cy = S * 0.5, S * 0.5
    for ang, col in ((-35, _GREY), (35, (190, 198, 212, 255))):
        blade = [(S * 0.46, S * 0.50), (S * 0.96, S * 0.45), (S * 0.96, S * 0.52)]
        d.polygon(_rot(blade, cx, cy, math.radians(ang)), fill=col, outline=INK, width=_o(ss))
    for ang in (-35, 35):
        (hx, hy), = _rot([(S * 0.16, S * 0.50)], cx, cy, math.radians(ang))
        d.ellipse([hx - S * 0.12, hy - S * 0.12 + (S * 0.0), hx + S * 0.12, hy + S * 0.12], outline=INK, width=ss * 9)
        d.ellipse([hx - S * 0.12, hy - S * 0.12, hx + S * 0.12, hy + S * 0.12], outline=_RED, width=ss * 5)
    d.ellipse([cx - S * 0.04, cy - S * 0.04, cx + S * 0.04, cy + S * 0.04], fill=(90, 96, 112, 255), outline=INK, width=_o(ss))


_PROPS: Dict[str, Callable] = {
    "ticket": _prop_ticket, "timetable": _prop_timetable, "cash": _prop_cash, "coins": _prop_coins, "cargo": _prop_cargo,
    "globe": _prop_globe, "building": _prop_building, "contract": _prop_contract, "chart": _prop_chart,
    "plane_icon": _prop_plane_icon, "route_icon": _prop_route_icon, "crown": _prop_crown, "handshake": _prop_handshake,
    "scissors": _prop_scissors,
}
PROP_KINDS = tuple(_PROPS)


@_cached(128)
def _prop(kind: str, size: int) -> Image.Image:
    ss = 3
    S = size * ss
    im, d = _canvas(S, S)
    fn = _PROPS.get(kind)
    if fn:
        fn(d, S, ss)
    else:
        d.rounded_rectangle([S * 0.1, S * 0.1, S * 0.9, S * 0.9], radius=int(S * 0.12), fill=(236, 238, 244, 255), outline=INK, width=_o(ss))
        txt = (kind or "?")[:12]
        fs = int(S * 0.2)
        f = T.font("heavy", fs)
        while d.textlength(txt, font=f) > S * 0.74 and fs > 8:
            fs -= 4
            f = T.font("heavy", fs)
        d.text((S / 2, S / 2), txt, font=f, fill=INK, anchor="mm")
    return _down(im, ss)


def prop(kind: str, size: int = 220) -> Image.Image:
    return _prop(str(kind or "").strip().lower(), int(size))
