"""Story-mode stage pieces, set 2 (docs/aviation/MASTER_PLAN.md S9-S11, S13-S17). Registered as stage sprite kinds
(the stage auto-imports this module), so they float, glide and leave like every other sticker. Positions are 1280 x 720 units.
Words and numbers come only from the args (the narration / catalog); nothing is invented, no face is ever drawn.

    portrait       args {name, role, quote?, image?}               round b/w portrait (or a neutral silhouette), name, role, bubble
    fleet_card *   args {count, type, airline, title?, label?}      'The Fleet of X', aircraft sticker, yellow '3x Boeing 707' badge pops
    icon_stat *    args {value, unit?, label, icon}                 yellow line icon + one figure counting up; icon: chart plane globe
                                                                    people cash route seat fuel
    handwriting *  args {text, strike?, rewrite?}                   name written by a pen on a white card, struck in red, rewritten below
    flight_title * args {flight, from, to}                          'SQ 108' between two airport dots (catalog ids), dashed line draws
    photo_card *   args {image, title, subtitle?, credit}           photo card, title band top-left, 'Credits: X', slow Ken Burns
    big_type       args {text, highlight?: [words], arrows?: [[x, y]], origin?: [x, y]}   bold white type, key words yellow, hand-drawn
                                                                    arrows to stage points (arrows draw with _k; origin = where the
                                                                    sprite sits on the stage, default centre)
    paper *        args {image, headline_box?, highlight_box?, source?}   page shot as a tilted torn-edge paper, highlight swept yellow
    (* animated: add with anim=seconds, the sprite reads args['_k'] 0..1; without _k it draws the finished state)

    add_portrait / add_fleet_card / add_icon_stat / add_handwriting / add_flight_title / add_photo_card / add_big_type / add_paper
        (stage, at, ...) -> element id; each picks a sensible position, scale and anim length (all overridable).

Handwriting font: Chalkboard SE (assets/fonts/ChalkboardSE.ttc, regular face); falls back to the style serif.
"""

from __future__ import annotations

import math
import os
import random
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from . import catalog as C
from . import stage as G
from . import style as S

_HERE = os.path.dirname(os.path.abspath(__file__))
_HAND_PATH = os.path.join(os.path.dirname(_HERE), "assets", "fonts", "ChalkboardSE.ttc")
DARK = (14, 15, 20, 255)
PANEL = (28, 31, 40, 255)


# ------------------------------------------------------------------------------------------------------------------ helpers

def _k(a: Dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(a.get("_k", 1.0))))
    except (TypeError, ValueError):
        return 1.0


def _ease_out(k: float) -> float:
    return 1 - (1 - max(0.0, min(1.0, k))) ** 3


def _seg(k: float, a: float, b: float) -> float:
    """Progress of k inside the window a..b, 0..1."""
    return 0.0 if b <= a else max(0.0, min(1.0, (k - a) / (b - a)))


def _back(k: float) -> float:
    k = max(0.0, min(1.0, k))
    return 1 + 2.9 * (k - 1) ** 3 + 1.9 * (k - 1) ** 2


@lru_cache(maxsize=64)
def _hand_font(size: int):
    try:
        return ImageFont.truetype(_HAND_PATH, int(size), index=1)
    except (OSError, ValueError):
        try:
            return ImageFont.truetype(_HAND_PATH, int(size))
        except (OSError, ValueError):
            return S.font("hand", size)


def _wrap(text: str, font, maxw: float) -> List[str]:
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines, cur = [], ""
    for wd in str(text).split():
        t = (cur + " " + wd).strip()
        if probe.textlength(t, font=font) > maxw and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


def _tw(font, text: str) -> float:
    return ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(text, font=font)


def _tracked(d: ImageDraw.ImageDraw, x: float, y: float, text: str, font, fill, track: float) -> float:
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + track
    return x


def _tracked_w(font, text: str, track: float) -> float:
    return sum(_tw(font, ch) + track for ch in text) - track if text else 0.0


@lru_cache(maxsize=32)
def _load(path: str, mtime: float) -> Optional[Image.Image]:
    try:
        with Image.open(path) as im:
            im.load()
            return im.convert("RGB")
    except Exception:
        return None


def _image(path: Any) -> Optional[Image.Image]:
    p = str(path or "")
    if not p or not os.path.isfile(p):
        return None
    try:
        return _load(p, os.path.getmtime(p))
    except OSError:
        return None


def _ss(w: int, h: int, ss: int = 3) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _down(im: Image.Image, ss: int = 3) -> Image.Image:
    return im.resize((im.width // ss, im.height // ss), Image.LANCZOS)


def _round_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


def _fit_cover(im: Image.Image, w: int, h: int, zoom: float = 1.0, pan: Tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    sc = max(w / im.width, h / im.height) * zoom
    nw, nh = max(w, int(im.width * sc)), max(h, int(im.height * sc))
    r = im.resize((nw, nh), Image.BILINEAR)
    x0 = int((nw - w) * pan[0])
    y0 = int((nh - h) * pan[1])
    return r.crop((x0, y0, x0 + w, y0 + h))


# ------------------------------------------------------------------------------------------------------------------ S9 portrait

def _silhouette(size: int) -> Image.Image:
    ss = 3
    im = Image.new("RGBA", (size * ss, size * ss), (58, 62, 74, 255))
    d = ImageDraw.Draw(im)
    s = size * ss
    d.ellipse((s * 0.34, s * 0.20, s * 0.66, s * 0.54), fill=(150, 154, 164, 255))
    d.ellipse((s * 0.14, s * 0.62, s * 0.86, s * 1.30), fill=(150, 154, 164, 255))
    return _down(im, ss)


def portrait(a: Dict[str, Any]) -> Image.Image:
    name, role = str(a.get("name", "")).strip(), str(a.get("role", "")).strip()
    quote = str(a.get("quote") or "").strip()
    D = 270
    src = _image(a.get("image"))
    if src is not None:
        face = ImageOps.grayscale(ImageOps.fit(src, (D, D), Image.LANCZOS, centering=(0.5, 0.35))).convert("RGBA")
        face = ImageOps.autocontrast(face.convert("L"), cutoff=1).convert("RGBA")
    else:
        face = _silhouette(D)
    ss = 3
    m = Image.new("L", (D * ss, D * ss), 0)
    ImageDraw.Draw(m).ellipse((0, 0, D * ss - 1, D * ss - 1), fill=255)
    m = m.resize((D, D), Image.LANCZOS)
    disc = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    disc.paste(face, (0, 0), m)
    ring = 8
    fn, fr = S.font("title", 40), S.font("body", 30)
    bw = 520 if quote else 0
    tw_ = max(_tw(fn, name), _tw(fr, role), D + 2 * ring)
    left_w = int(min(tw_, 420)) + 16
    W_ = left_w + (30 + bw if quote else 0)
    name_lines = _wrap(name, fn, left_w) if name else []
    role_lines = _wrap(role, fr, left_w) if role else []
    H_ = D + 2 * ring + 14 + len(name_lines) * int(fn.size * 1.15) + len(role_lines) * int(fr.size * 1.3) + 10
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = left_w // 2
    d.ellipse((cx - D // 2 - ring, 0, cx + D // 2 + ring, D + 2 * ring), fill=S.WHITE)
    im.alpha_composite(disc, (cx - D // 2, ring))
    y = D + 2 * ring + 14
    for ln in name_lines:
        d.text((cx - _tw(fn, ln) / 2, y), ln, font=fn, fill=S.WHITE)
        y += int(fn.size * 1.15)
    for ln in role_lines:
        d.text((cx - _tw(fr, ln) / 2, y), ln, font=fr, fill=S.YELLOW)
        y += int(fr.size * 1.3)
    if quote:
        try:
            from . import stickers
            b = stickers.bubble(quote, bw, (), "left")
        except Exception:
            b = Image.new("RGBA", (bw, 160), S.WHITE)
        if b.height > H_ - 20:
            b = b.resize((int(b.width * (H_ - 20) / b.height), H_ - 20), Image.LANCZOS)
        im.alpha_composite(b, (left_w + 30, max(0, (D + 2 * ring - b.height) // 2 + 10)))
    return im


# ------------------------------------------------------------------------------------------------------------------ S10 fleet card

def _type_name(type_id: str) -> str:
    e = C.get_aircraft(str(type_id)) or {}
    return str(e.get("name") or type_id)


def _airline_name(airline: str) -> str:
    e = C.get_airline(str(airline)) or {}
    return str(e.get("name") or airline)


def fleet_card(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    title = str(a.get("title") or f"The Fleet of {_airline_name(a.get('airline', ''))}").strip()
    label = str(a.get("label") or f"{a.get('count', '')}x {_type_name(a.get('type', ''))}").strip()
    W_, H_ = 920, 470
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ft = S.font("title", 56)
    size = 56
    while _tw(ft, title) > W_ - 20 and size > 30:
        size -= 4
        ft = S.font("title", size)
    d.text(((W_ - _tw(ft, title)) / 2, 0), title, font=ft, fill=S.WHITE)
    try:
        from . import stickers
        plane = stickers.die_cut(stickers.aircraft(str(a.get("type", "")), str(a.get("airline", "")), 720), S.EDGE)
    except Exception:
        plane = Image.new("RGBA", (720, 280), (0, 0, 0, 0))
    plane.thumbnail((W_ - 40, 330), Image.LANCZOS)
    im.alpha_composite(plane, ((W_ - plane.width) // 2, 80))
    fb = S.font("title", 46)
    bw, bh = int(_tw(fb, label)) + 56, 78
    badge = Image.new("RGBA", (bw + 8, bh + 8), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle((4, 4, bw + 3, bh + 3), radius=22, fill=S.YELLOW, outline=S.WHITE, width=4)
    bd.text((4 + bw / 2, 4 + bh / 2), label, font=fb, fill=S.INK, anchor="mm")
    sc = _back(_seg(k, 0.12, 0.55))
    if sc > 0.02:
        badge = badge.resize((max(1, int(badge.width * sc)), max(1, int(badge.height * sc))), Image.LANCZOS)
        cx, cy = W_ // 2 + 150, H_ - 62
        im.alpha_composite(badge, (int(cx - badge.width / 2), int(cy - badge.height / 2)))
    return im


# ------------------------------------------------------------------------------------------------------------------ S11 icon stat

def _line(d, pts, w, col=S.YELLOW):
    d.line(pts, fill=col, width=w, joint="curve")
    r = w / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=col)


def _icon(kind: str, size: int = 200) -> Image.Image:
    ss = 3
    im, d = _ss(size, size, ss)
    s = size * ss
    u = s / 100.0
    w = int(6 * u)
    Y = S.YELLOW

    def P(*pts):
        return [(x * u, y * u) for x, y in pts]

    if kind == "chart":
        _line(d, P((12, 10), (12, 88), (92, 88)), w)
        _line(d, P((24, 70), (44, 48), (58, 60), (86, 24)), w)
        _line(d, P((70, 24), (86, 24), (86, 40)), w)
    elif kind == "plane":
        pts = P((50, 6), (57, 30), (94, 56), (94, 66), (58, 56), (56, 80), (70, 90), (70, 95), (50, 90), (30, 95), (30, 90),
                (44, 80), (42, 56), (6, 66), (6, 56), (43, 30))
        d.line(pts + [pts[0]], fill=Y, width=w, joint="curve")
    elif kind == "globe":
        d.ellipse([x * u for x in (10, 10, 90, 90)], outline=Y, width=w)
        d.ellipse([x * u for x in (32, 10, 68, 90)], outline=Y, width=w)
        _line(d, P((10, 50), (90, 50)), w)
        _line(d, P((18, 30), (82, 30)), int(w * .7))
        _line(d, P((18, 70), (82, 70)), int(w * .7))
    elif kind == "people":
        for cx, hy, r in ((34, 30, 13), (68, 36, 10)):
            d.ellipse([(cx - r) * u, (hy - r) * u, (cx + r) * u, (hy + r) * u], outline=Y, width=w)
        d.arc([x * u for x in (8, 54, 60, 112)], 180, 360, fill=Y, width=w)
        d.arc([x * u for x in (52, 58, 90, 104)], 180, 360, fill=Y, width=w)
    elif kind == "cash":
        d.rounded_rectangle([x * u for x in (6, 24, 94, 76)], radius=int(8 * u), outline=Y, width=w)
        d.ellipse([x * u for x in (36, 36, 64, 64)], outline=Y, width=w)
        for cx, cy in ((19, 37), (81, 63)):
            d.ellipse([(cx - 3) * u, (cy - 3) * u, (cx + 3) * u, (cy + 3) * u], fill=Y)
    elif kind == "route":
        d.ellipse([x * u for x in (6, 62, 26, 82)], outline=Y, width=w)
        d.ellipse([x * u for x in (74, 18, 94, 38)], outline=Y, width=w)
        pts = [(math.pow(1 - t, 2) * 16 + 2 * (1 - t) * t * 30 + t * t * 84, math.pow(1 - t, 2) * 62 + 2 * (1 - t) * t * 0 + t * t * 38)
               for t in [i / 24 for i in range(25)]]
        for i in range(0, 24, 3):
            d.line([(x * u, y * u) for x, y in pts[i:i + 2]], fill=Y, width=w)
    elif kind == "seat":
        _line(d, P((30, 10), (36, 52)), int(w * 1.5))
        _line(d, P((36, 52), (74, 56), (78, 70)), w)
        _line(d, P((36, 52), (30, 70), (78, 70)), w)
        _line(d, P((54, 70), (54, 90)), w)
        _line(d, P((36, 90), (72, 90)), w)
    elif kind == "fuel":
        d.rounded_rectangle([x * u for x in (14, 14, 60, 90)], radius=int(6 * u), outline=Y, width=w)
        d.rectangle([x * u for x in (24, 24, 50, 44)], outline=Y, width=int(w * .8))
        _line(d, P((60, 40), (76, 40), (82, 52), (82, 78)), w)
        _line(d, P((6, 90), (68, 90)), w)
    else:
        d.rounded_rectangle([x * u for x in (10, 10, 90, 90)], radius=int(12 * u), outline=Y, width=w)
    return _down(im, ss)


_COUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def counted(value: str, k: float) -> str:
    """The value with its number scaled by k (0 -> 0, 1 -> the value exactly). 'S$100' at 0.5 -> 'S$50'. No number: unchanged."""
    v = str(value)
    m = _COUNT_RE.search(v)
    if not m or k >= 1.0:
        return v
    raw = m.group(1)
    dec = len(raw.split(".")[1]) if "." in raw else 0
    num = float(raw.replace(",", ""))
    cur = num * max(0.0, k)
    txt = f"{cur:,.{dec}f}" if "," in raw else f"{cur:.{dec}f}"
    return v[:m.start()] + txt + v[m.end():]


def icon_stat(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    value, unit, label = str(a.get("value", "")), str(a.get("unit") or "").strip(), str(a.get("label", "")).strip()
    ico = _icon(str(a.get("icon", "")), 210)
    fv = S.font("title", 112)
    size = 112
    full = f"{value} {unit}".strip()
    while _tw(fv, full) > 720 and size > 48:
        size -= 6
        fv = S.font("title", size)
    fl = S.font("body", 44)
    lab_lines = _wrap(label, fl, 760)
    textw = int(max(_tw(fv, full), *(_tw(fl, ln) for ln in lab_lines)))
    W_ = 210 + 40 + textw + 10
    H_ = max(230, int(fv.size * 1.2) + len(lab_lines) * int(fl.size * 1.25) + 20)
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    im.alpha_composite(ico, (0, (H_ - 210) // 2))
    d = ImageDraw.Draw(im)
    shown = counted(value, _ease_out(_seg(k, 0.0, 0.8)))
    ty = (H_ - (int(fv.size * 1.2) + len(lab_lines) * int(fl.size * 1.25))) // 2
    x = 250
    d.text((x, ty), shown, font=fv, fill=S.WHITE)
    if unit:
        d.text((x + _tw(fv, value) + _tw(fv, " "), ty), unit, font=fv, fill=S.YELLOW)
    y = ty + int(fv.size * 1.2)
    ap = _seg(k, 0.15, 0.5)
    for ln in lab_lines:
        col = S.WHITE[:3] + (int(255 * ap),)
        d.text((x, y), ln, font=fl, fill=col)
        y += int(fl.size * 1.25)
    return im


# ------------------------------------------------------------------------------------------------------------------ S13 handwriting

def _sweep_reveal(layer: Image.Image, p: float, tip: Tuple[int, int, int, int]) -> Tuple[Image.Image, Optional[Tuple[float, float]]]:
    """Keep the left `p` of the layer's content box (a slanted front, like a pen moving), return the layer and the pen position."""
    x0, y0, x1, y1 = tip
    if p <= 0:
        return Image.new("RGBA", layer.size, (0, 0, 0, 0)), None
    front = x0 + (x1 - x0) * p
    m = Image.new("L", layer.size, 0)
    slant = (y1 - y0) * 0.18
    ImageDraw.Draw(m).polygon([(0, 0), (front + slant, 0), (front - slant, layer.height), (0, layer.height)], fill=255)
    out = layer.copy()
    out.putalpha(ImageChops.multiply(layer.getchannel("A"), m))
    return out, (front, (y0 + y1) / 2)


def handwriting(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    text, rewrite = str(a.get("text", "")), str(a.get("rewrite") or "")
    strike = bool(a.get("strike"))
    size = 104
    f = _hand_font(size)
    while _tw(f, text) > 900 and size > 40:
        size -= 6
        f = _hand_font(size)
    rsize = size
    fr = _hand_font(rsize)
    while rewrite and _tw(fr, rewrite) > 900 and rsize > 40:
        rsize -= 6
        fr = _hand_font(rsize)
    pad = 54
    lh1 = int(size * 1.35)
    lh2 = int(rsize * 1.35) if rewrite else 0
    W_ = int(max(_tw(f, text), _tw(fr, rewrite) if rewrite else 0)) + pad * 2
    W_ = max(W_, 420)
    H_ = pad * 2 + lh1 + lh2 + (14 if rewrite else 0)
    card = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((0, 0, W_ - 1, H_ - 1), radius=26, fill=S.WHITE)
    # phases of the whole sequence
    if strike and rewrite:
        w_a, w_b, s_b = (0.0, 0.42), (0.42, 0.56), 1.0
    elif strike:
        w_a, w_b, s_b = (0.0, 0.7), (0.7, 1.0), 1.0
    elif rewrite:
        w_a, w_b, s_b = (0.0, 0.5), (0.5, 0.5), 1.0
    else:
        w_a, w_b, s_b = (0.0, 1.0), (1.0, 1.0), 1.0
    pen = None
    ink = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(ink)
    tx = (W_ - _tw(f, text)) / 2
    d.text((tx, pad), text, font=f, fill=S.INK)
    box = (int(tx) - 6, pad, int(tx + _tw(f, text)) + 6, pad + lh1)
    vis, pen1 = _sweep_reveal(ink, _seg(k, *w_a), box)
    card.alpha_composite(vis)
    pen = pen1 if 0 < _seg(k, *w_a) < 1 else None
    if strike:
        sp = _seg(k, *w_b)
        if sp > 0:
            sd = ImageDraw.Draw(card)
            x_a, x_b = tx - 14, tx + _tw(f, text) + 14
            y_a, y_b = pad + lh1 * 0.60, pad + lh1 * 0.52
            xe = x_a + (x_b - x_a) * sp
            ye = y_a + (y_b - y_a) * sp
            sd.line([(x_a, y_a), (xe, ye)], fill=S.RED, width=9)
            sd.ellipse((x_a - 4, y_a - 4, x_a + 4, y_a + 4), fill=S.RED)
            sd.ellipse((xe - 4, ye - 4, xe + 4, ye + 4), fill=S.RED)
            if sp < 1:
                pen = (xe, ye)
    if rewrite:
        rp = _seg(k, (w_b[1] if strike else w_a[1]), 1.0)
        ink2 = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        rx = (W_ - _tw(fr, rewrite)) / 2
        ry = pad + lh1 + 14
        ImageDraw.Draw(ink2).text((rx, ry), rewrite, font=fr, fill=S.NAVY)
        vis2, pen2 = _sweep_reveal(ink2, rp, (int(rx) - 6, ry, int(rx + _tw(fr, rewrite)) + 6, ry + lh2))
        card.alpha_composite(vis2)
        if 0 < rp < 1:
            pen = pen2
    if pen:
        pd = ImageDraw.Draw(card)
        px, py = pen
        pd.polygon([(px, py), (px + 34, py - 40), (px + 46, py - 30), (px + 12, py + 6)], fill=(60, 64, 78, 255))
        pd.ellipse((px - 4, py - 4, px + 4, py + 4), fill=S.INK)
    return card


# ------------------------------------------------------------------------------------------------------------------ S14 flight title

def _airport(i: Any) -> Tuple[str, str]:
    e = C.get_airport(str(i)) or {}
    return str(e.get("id") or i).upper() if (e.get("id") or i) else "", str(e.get("city") or e.get("name") or "")


def flight_title(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    flight = str(a.get("flight", "")).strip()
    (c1, n1), (c2, n2) = _airport(a.get("from")), _airport(a.get("to"))
    W_, H_ = 1040, 360
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ff = S.font("title", 118)
    size = 118
    while _tracked_w(ff, flight, 22) > W_ - 20 and size > 50:
        size -= 6
        ff = S.font("title", size)
    _tracked(d, (W_ - _tracked_w(ff, flight, 22)) / 2, 0, flight, ff, S.WHITE, 22)
    y = 212
    xa, xb = 120, W_ - 120
    dp = _seg(k, 0.0, 0.2)
    r = 15 * _back(dp) if dp > 0 else 0
    if r > 0.5:
        d.ellipse((xa - r, y - r, xa + r, y + r), fill=S.YELLOW, outline=S.WHITE, width=4)
    lp = _seg(k, 0.15, 0.8)
    xe = xa + (xb - xa) * lp
    x = xa + 34
    while x < xe - 2:
        d.line((x, y, min(x + 22, xe), y), fill=S.WHITE, width=6)
        x += 38
    if lp > 0.02:
        px = xe
        d.polygon([(px + 10, y), (px - 12, y - 11), (px - 7, y), (px - 12, y + 11)], fill=S.YELLOW) if lp < 1 else None
    ep = _seg(k, 0.75, 0.95)
    r2 = 15 * _back(ep) if ep > 0 else 0
    if r2 > 0.5:
        d.ellipse((xb - r2, y - r2, xb + r2, y + r2), fill=S.YELLOW, outline=S.WHITE, width=4)
    fc, fn = S.font("title", 54), S.font("body", 32)
    for cx, code, city, vis in ((xa, c1, n1, _seg(k, 0.05, 0.3)), (xb, c2, n2, _seg(k, 0.8, 1.0))):
        if vis <= 0:
            continue
        al = int(255 * vis)
        d.text((cx - _tw(fc, code) / 2, y + 30), code, font=fc, fill=S.YELLOW[:3] + (al,))
        cs = city
        while _tw(fn, cs) > 300 and len(cs) > 3:
            cs = cs[:-2]
        d.text((cx - _tw(fn, cs) / 2, y + 100), cs if cs == city else cs + "…", font=fn, fill=S.WHITE[:3] + (al,))
    return im


# ------------------------------------------------------------------------------------------------------------------ S15 photo card

def photo_card(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    W_, H_ = 980, 560
    src = _image(a.get("image"))
    if src is not None:
        body = _fit_cover(src, W_, H_, 1.0 + 0.10 * k, (0.35 + 0.3 * k, 0.5))
    else:
        body = Image.new("RGB", (W_, H_), PANEL[:3])
        gd = ImageDraw.Draw(body)
        for i in range(H_):
            gd.line((0, i, W_, i), fill=(34 + i // 24, 37 + i // 24, 48 + i // 20))
    card = body.convert("RGBA")
    d = ImageDraw.Draw(card, "RGBA")
    title, sub = str(a.get("title", "")).strip(), str(a.get("subtitle") or "").strip()
    ft, fs = S.font("title", 44), S.font("body", 28)
    tl = _wrap(title, ft, W_ * 0.6)
    sl = _wrap(sub, fs, W_ * 0.6) if sub else []
    bw = int(max([_tw(ft, ln) for ln in tl] + [_tw(fs, ln) for ln in sl] + [60])) + 56
    bh = 24 + len(tl) * int(ft.size * 1.2) + (len(sl) * int(fs.size * 1.3) + 6 if sl else 0) + 16
    if title or sub:
        d.rounded_rectangle((-30, 26, bw, 26 + bh), radius=18, fill=(10, 11, 15, 225))
        y = 26 + 16
        for ln in tl:
            d.text((28, y), ln, font=ft, fill=S.WHITE)
            y += int(ft.size * 1.2)
        for ln in sl:
            d.text((28, y + 6), ln, font=fs, fill=S.YELLOW)
            y += int(fs.size * 1.3)
    credit = str(a.get("credit") or "").strip()
    if credit:
        fc = S.font("body", 24)
        t = f"Credits: {credit}"
        while _tw(fc, t) > W_ - 80 and len(t) > 12:
            t = t[:-2]
        cw = int(_tw(fc, t)) + 36
        d.rounded_rectangle((20, H_ - 62, 20 + cw, H_ - 20), radius=12, fill=(10, 11, 15, 210))
        d.text((38, H_ - 55), t, font=fc, fill=S.WHITE)
    out = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    out.paste(card, (0, 0), _round_mask((W_, H_), 24))
    return out


# ------------------------------------------------------------------------------------------------------------------ S16 big type

def _arrow(d: ImageDraw.ImageDraw, p0, p1, prog: float, rnd: random.Random, w: int = 9) -> None:
    if prog <= 0:
        return
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / dist, dx / dist
    bend = rnd.choice((-1, 1)) * dist * 0.16
    cx, cy = (x0 + x1) / 2 + nx * bend, (y0 + y1) / 2 + ny * bend
    steps = 36
    pts = []
    for i in range(int(steps * min(1.0, prog)) + 1):
        t = i / steps
        pts.append(((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1 + math.sin(t * 9) * 2.2,
                    (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1 + math.cos(t * 7) * 2.2))
    if len(pts) > 1:
        d.line(pts, fill=S.YELLOW, width=w, joint="curve")
    if prog >= 0.98:
        ex, ey = pts[-1]
        px, py = pts[-4]
        ang = math.atan2(ey - py, ex - px)
        for da in (2.55, -2.55):
            d.line((ex, ey, ex + 34 * math.cos(ang + da), ey + 34 * math.sin(ang + da)), fill=S.YELLOW, width=w)


def big_type(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    text = str(a.get("text", "")).strip()
    hl = {str(h).lower().strip(".,!?;:\"'()") for h in (a.get("highlight") or [])}
    arrows = [tuple(p) for p in (a.get("arrows") or []) if isinstance(p, (list, tuple)) and len(p) == 2]
    size = 96
    f = S.font("title", size)
    maxw = 1000
    lines = _wrap(text, f, maxw)
    while len(lines) > 3 and size > 52:
        size -= 6
        f = S.font("title", size)
        lines = _wrap(text, f, maxw)
    lh = int(size * 1.18)
    bw = int(max([_tw(f, ln) for ln in lines] + [10]))
    bh = lh * len(lines)
    ox, oy = (a.get("origin") or [640, 360])[:2]
    if arrows:
        W_, H_ = 1280, 720
        left, top = ox - bw / 2, oy - bh / 2
    else:
        W_, H_ = bw + 40, bh + 30
        left, top = 20, 10
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    space = _tw(f, " ")
    y = top
    for ln in lines:
        x = left + (bw - _tw(f, ln)) / 2
        for wd in ln.split():
            col = S.YELLOW if wd.lower().strip(".,!?;:\"'()") in hl else S.WHITE
            d.text((x, y), wd, font=f, fill=col)
            x += _tw(f, wd) + space
        y += lh
    rnd = random.Random(7)
    n = len(arrows)
    for i, (tx, ty) in enumerate(arrows):
        # start from the text-block edge nearest the target
        sx = min(max(tx, left + 30), left + bw - 30)
        sy = top + bh + 14 if ty > top + bh / 2 else top - 14
        if left - 10 < tx < left + bw + 10 and top - 10 < ty < top + bh + 10:
            continue
        a0, a1 = 0.1 + 0.6 * i / max(1, n), 0.4 + 0.6 * (i + 1) / max(1, n)
        # stop the head short of the target so it points at the sticker rather than covering it
        dist = math.hypot(tx - sx, ty - sy) or 1
        ex, ey = tx - (tx - sx) / dist * 18, ty - (ty - sy) / dist * 18
        _arrow(d, (sx, sy), (ex, ey), _seg(k, a0, min(1.0, a1)), rnd)
    return im


# ------------------------------------------------------------------------------------------------------------------ S17 paper

def paper(a: Dict[str, Any]) -> Image.Image:
    k = _k(a)
    src = _image(a.get("image"))
    PW = 600
    margin = 14
    if src is not None:
        sc = (PW - 2 * margin) / src.width
        page = src.resize((PW - 2 * margin, max(60, int(src.height * sc))), Image.LANCZOS)
        page = page.crop((0, 0, page.width, min(page.height, 560)))
    else:
        sc = 1.0
        page = Image.new("RGB", (PW - 2 * margin, 360), (246, 244, 238))
        pd = ImageDraw.Draw(page)
        for yy in range(40, 360, 34):
            pd.line((20, yy, page.width - 20, yy), fill=(222, 220, 212), width=2)
    ph = page.height + 2 * margin + 26
    sheet = Image.new("RGBA", (PW, ph), S.WHITE)
    sheet.paste(page.convert("RGBA"), (margin, margin))

    def box(b):
        try:
            x, y, w, h = [float(v) for v in b]
        except (TypeError, ValueError):
            return None
        if w <= 0 or h <= 0:
            return None
        return [margin + x * sc, margin + y * sc, margin + (x + w) * sc, margin + (y + h) * sc]

    marks = []
    for key in ("headline_box", "highlight_box"):
        b = box(a.get(key)) if src is not None else None
        if b:
            marks.append(b)
    marks = marks[:2]
    for i, b in enumerate(marks):
        p = _ease_out(_seg(k, 0.1 + 0.4 * i / max(1, len(marks)), 0.55 + 0.4 * (i + 1) / max(1, len(marks))))
        if p <= 0:
            continue
        x0, y0, x1, y1 = b
        x0 = max(0, x0 - 6)
        x1 = min(PW, x1 + 6)
        y1 = min(ph - 20, y1 + 4)
        if y0 >= ph:
            continue
        xe = x0 + (x1 - x0) * p
        region = sheet.crop((int(x0), int(y0), max(int(x0) + 1, int(xe)), int(y1))).convert("RGB")
        tint = Image.new("RGB", region.size, S.YELLOW[:3])
        sheet.paste(ImageChops.multiply(region, tint).convert("RGBA"), (int(x0), int(y0)))
    # torn bottom edge
    rnd = random.Random(11)
    mask = Image.new("L", (PW, ph), 0)
    md = ImageDraw.Draw(mask)
    edge = [(0, 0), (PW, 0)]
    y = ph - 14
    xs = list(range(PW, -1, -14))
    for x in xs:
        edge.append((x, y + rnd.randint(-9, 9)))
    md.polygon(edge, fill=255)
    paper_im = Image.new("RGBA", (PW, ph), (0, 0, 0, 0))
    paper_im.paste(sheet, (0, 0), mask)
    # source tag, drawn on the paper's lower left (before the tilt)
    srcs = str(a.get("source") or "").strip()
    if srcs:
        ft = S.font("body", 22)
        t = f"Source: {srcs}"
        while _tw(ft, t) > PW - 70 and len(t) > 10:
            t = t[:-2]
        tw = int(_tw(ft, t)) + 28
        td = ImageDraw.Draw(paper_im)
        td.rounded_rectangle((16, ph - 52, 16 + tw, ph - 14), radius=10, fill=S.YELLOW)
        td.text((30, ph - 46), t, font=ft, fill=S.INK)
    # tilt about the centre
    tilt = paper_im.rotate(2.0, resample=Image.BICUBIC, expand=True)
    return tilt


for _kind, _fn in (("portrait", portrait), ("fleet_card", fleet_card), ("icon_stat", icon_stat), ("handwriting", handwriting),
                   ("flight_title", flight_title), ("photo_card", photo_card), ("big_type", big_type), ("paper", paper)):
    G.register(_kind, _fn)


# ------------------------------------------------------------------------------------------------------------------ builders

def add_portrait(st: G.Stage, at: float, name: str, role: str, quote: str = "", image: str = "",
                 pos: Tuple[float, float] = (640, 370), scale: float = 0.85) -> str:
    return st.add("portrait", at, {"name": name, "role": role, "quote": quote, "image": image}, pos=pos, scale=scale, edge=False)


def add_fleet_card(st: G.Stage, at: float, count: Any, type_id: str, airline: str, title: str = "",
                   pos: Tuple[float, float] = (640, 380), scale: float = 0.95, anim: float = 1.6) -> str:
    a = {"count": count, "type": type_id, "airline": airline}
    if title:
        a["title"] = title
    return st.add("fleet_card", at, a, pos=pos, scale=scale, edge=False, anim=anim)


def add_icon_stat(st: G.Stage, at: float, value: str, label: str, icon: str, unit: str = "",
                  pos: Tuple[float, float] = (640, 370), scale: float = 1.0, anim: float = 1.8) -> str:
    return st.add("icon_stat", at, {"value": value, "unit": unit, "label": label, "icon": icon}, pos=pos, scale=scale, edge=False,
                  anim=anim)


def add_handwriting(st: G.Stage, at: float, text: str, strike: bool = False, rewrite: str = "",
                    pos: Tuple[float, float] = (640, 360), scale: float = 0.95, anim: Optional[float] = None) -> str:
    if anim is None:
        anim = 1.4 + 0.07 * len(text) + (1.0 + 0.07 * len(rewrite) if rewrite else 0.0) + (0.5 if strike else 0.0)
    a: Dict[str, Any] = {"text": text, "strike": bool(strike)}
    if rewrite:
        a["rewrite"] = rewrite
    return st.add("handwriting", at, a, pos=pos, scale=scale, edge=False, anim=anim)


def add_flight_title(st: G.Stage, at: float, flight: str, origin: str, dest: str,
                     pos: Tuple[float, float] = (640, 340), scale: float = 1.0, anim: float = 1.6) -> str:
    return st.add("flight_title", at, {"flight": flight, "from": origin, "to": dest}, pos=pos, scale=scale, edge=False, anim=anim)


def add_photo_card(st: G.Stage, at: float, image: str, title: str, credit: str, subtitle: str = "",
                   pos: Tuple[float, float] = (640, 370), scale: float = 0.9, anim: float = 6.0) -> str:
    a = {"image": image, "title": title, "credit": credit}
    if subtitle:
        a["subtitle"] = subtitle
    return st.add("photo_card", at, a, pos=pos, scale=scale, edge=False, float_=False, anim=anim)


def add_big_type(st: G.Stage, at: float, text: str, highlight: Sequence[str] = (), arrows: Sequence[Sequence[float]] = (),
                 pos: Tuple[float, float] = (640, 150), scale: float = 1.0, anim: float = 1.4) -> str:
    a: Dict[str, Any] = {"text": text, "highlight": list(highlight)}
    if arrows:
        a["arrows"] = [list(p) for p in arrows]
        a["origin"] = [pos[0], pos[1]]
        # an arrows sprite covers the whole stage, so it sits at the stage centre and the text is drawn at `origin`
        return st.add("big_type", at, a, pos=(640, 360), scale=1.0, edge=False, float_=False, anim=anim)
    return st.add("big_type", at, a, pos=pos, scale=scale, edge=False, anim=anim)


def add_paper(st: G.Stage, at: float, image: str, headline_box: Optional[Sequence[float]] = None,
              highlight_box: Optional[Sequence[float]] = None, source: str = "",
              pos: Tuple[float, float] = (640, 370), scale: float = 1.05, anim: float = 1.6) -> str:
    a: Dict[str, Any] = {"image": image, "source": source}
    if headline_box:
        a["headline_box"] = list(headline_box)
    if highlight_box:
        a["highlight_box"] = list(highlight_box)
    return st.add("paper", at, a, pos=pos, scale=scale, edge=False, anim=anim)
