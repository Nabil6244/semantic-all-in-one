"""Numbers made physical (docs/aviation/MASTER_PLAN.md S18): the business graphics of gfx_air restyled as stage stickers.
The airline's own aircraft stickers fill a fleet grid, cash is a pile of sticker bills, seats are a sticker cabin, bars have white
die-cut edges. Every kind is registered on the stage (aviation.stage auto-imports this module) and ANIMATED: add it with
st.add(kind, at, args, anim=seconds); the stage hands the sprite its progress as args['_k'] (0..1) in 24 cached steps.

    sticker_fleet        count, label, airline, type     aircraft stickers fill a grid one by one, yellow count badge counts up;
                                                         above 40 icons one sticker stands for N aircraft ("= N aircraft" key)
    cash_pile            value, currency, label          sticker bills stacking (number of stacks ~ log10 of the value), figure counting
    sticker_cabin        now, before, label              top view of sticker seats filling to the load factor, last year's figure beside
    sticker_change       before, after, currency, label  two die-cut bars growing, red / green change tag (gfx_air.change_tag)
    sticker_big_number   value, unit, sign, label, icon, airline, type   aircraft sticker + one big counting number
    gfx_frame            fn, params, dur                 ANY gfx_air.lay_* graphic as a sticker card: fn = "lay_runway" etc.

    SKIN                 {"gfx_air.lay_fleet": "sticker_fleet", ...}   all 12 gfx_air layers -> a sticker kind (gfx_frame for the rest)
    add_graphic(st, at, layer_name, params, dur=4.0, pos=(640, 390), **kw) -> id
                         the planner's one call: the same params it would hand gfx_air, now as a sticker element of the stage
    skin_kind(layer_name) -> kind                                                           (gfx_frame when there is no own skin)
    fleet_layout(count) -> (icons, per)      shown_count(count, k) -> int      cabin_filled(now, k) -> seats      (what a frame shows)

gfx_frame: gfx_air draws full frames with their own backdrop. It renders the function at time k*dur. A frame whose pixels are
mostly opaque (a backdrop) is cropped by a 3 % margin (the vignette edge), scaled to a 960 x 540 card. A transparent overlay
(lay_crew) is cropped to its content box plus padding and laid on a dark card, so its white text stays readable. Either way the card
gets rounded corners, then a white die-cut edge and shadow, like every sticker. A graphic with nothing to show (None) draws the
stage's placeholder card, never a crash.
Positions are in 1280 x 720 stage units; sizes here are in the same units (the stage scales them to the frame).
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from cinematic_explainer.war import motion as M

from . import gfx_air as A
from . import stage as G
from . import style as S

CARD_W, CARD_H = 960, 540
STAGE_POS = (640.0, 390.0)
ICON_CAP = 40                       # more aircraft than this: one sticker stands for several
ANIM_S = 2.4                        # how long the specific kinds take to build up


# ---------------------------------------------------------------------------------------------------------------- helpers

def _k(a: Dict[str, Any]) -> float:
    return M.clamp01(float(a.get("_k", 1.0)))


def _prog(k: float, start: float = 0.0, length: float = 0.85) -> float:
    return M.ease_out(M.ramp(k, start, length))


def _die(img: Image.Image, edge: int = 6) -> Image.Image:
    from . import stickers
    return stickers.die_cut(img, edge)


def _text_img(text: str, role: str, size: int, fill, stroke: int = 0, stroke_fill=None) -> Image.Image:
    f = S.font(role, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text or " ", font=f, stroke_width=stroke)
    w, h = box[2] - box[0] + 8, box[3] - box[1] + 8
    im = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - box[0], 4 - box[1]), text or " ", font=f, fill=fill, stroke_width=stroke,
                            stroke_fill=stroke_fill or S.INK)
    return im


def _sticker_text(text: str, role: str, size: int, fill=S.YELLOW, edge: int = 6) -> Image.Image:
    return _die(_text_img(text, role, size, fill, stroke=max(2, size // 22), stroke_fill=S.INK), edge)


def _fixed_width_text(text: str, final: str, role: str, size: int, fill, edge: int = 6) -> Image.Image:
    """Text sticker centred on a canvas as wide as the FINAL text, so a counting figure never shifts the layout."""
    cur = _sticker_text(text, role, size, fill, edge)
    ref = _sticker_text(final, role, size, fill, edge)
    out = Image.new("RGBA", (max(cur.width, ref.width), ref.height), (0, 0, 0, 0))
    out.alpha_composite(cur, ((out.width - cur.width) // 2, (out.height - cur.height) // 2))
    return out


def _paste_c(canvas: Image.Image, im: Image.Image, cx: float, cy: float) -> None:
    canvas.alpha_composite(im, (int(round(cx - im.width / 2)), int(round(cy - im.height / 2))))


def _pop(im: Image.Image, f: float) -> Image.Image:
    """Back-out scale pop of a sticker as it lands (f 0..1)."""
    s = max(0.05, G._back_out(f))
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BILINEAR) if s < 0.995 or s > 1.005 else im


def _pill(text: str, fill, ink, size: int = 40, pad: Tuple[int, int] = (22, 10), edge: int = 5) -> Image.Image:
    f = S.font("badge", size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0] + pad[0] * 2, box[3] - box[1] + pad[1] * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=min(h // 2, 22), fill=fill)
    d.text((pad[0] - box[0], pad[1] - box[1]), text, font=f, fill=ink)
    return _die(im, edge)


def _card(w: int, h: int, fill=S.YELLOW, radius: int = 26) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=fill)
    return im


@lru_cache(maxsize=96)
def _aircraft_sticker(type_id: str, airline: str, width: int, edge: int) -> Image.Image:
    from . import stickers
    return stickers.die_cut(stickers.aircraft(type_id, airline, width), edge)


@lru_cache(maxsize=32)
def _prop_sticker(name: str, size: int, edge: int) -> Image.Image:
    from . import stickers
    return stickers.die_cut(stickers.prop(name, size), edge)


# ---------------------------------------------------------------------------------------------------------------- fleet

def fleet_layout(count: int) -> Tuple[int, int]:
    """(icons, per): up to ICON_CAP stickers, one per aircraft; above it each sticker stands for `per` aircraft (a round number)."""
    n = max(0, int(count))
    if n <= ICON_CAP:
        return n, 1
    raw = n / ICON_CAP
    per = next((p for p in (2, 5, 10, 20, 25, 50, 100, 200, 500, 1000) if p >= raw), int(math.ceil(raw)))
    return int(math.ceil(n / per)), per


def shown_count(count: int, k: float) -> int:
    """The figure on the badge at progress k: counts up, exact at the end."""
    if k >= 0.999:
        return int(count)
    return int(round(count * _prog(k)))


def _grid(icons: int, area_w: int, area_h: int) -> Tuple[int, int]:
    """(cols, aircraft width) giving the biggest stickers that fit icons into the area (sticker is about 0.42 x as tall as wide)."""
    best = (1, 40)
    for cols in range(1, 13):
        rows = math.ceil(icons / cols)
        aw = min(area_w / cols - 30, (area_h / rows - 30) / 0.42)
        if aw > best[1]:
            best = (cols, int(aw))
    return best


def sticker_fleet(a: Dict[str, Any]) -> Image.Image:
    n = int(a.get("count") or 0)
    k = _k(a)
    icons, per = fleet_layout(n)
    cw, chh = 1120, 540
    canvas = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    gx0, gw = 360, 760
    cols, aw = _grid(max(1, icons), gw, chh)
    sprite = _aircraft_sticker(str(a.get("type") or ""), str(a.get("airline") or ""), aw, 4)
    rows = math.ceil(max(1, icons) / cols)
    px, py = gw / cols, chh / rows
    prog = _prog(k)
    shown = icons if k >= 0.999 else int(icons * prog)
    for i in range(shown):
        r, c = divmod(i, cols)
        cx, cy = gx0 + (c + 0.5) * px, (r + 0.5) * py
        im = sprite
        if i == shown - 1 and k < 0.999:
            im = _pop(sprite, 0.6)
        _paste_c(canvas, im, cx, cy)
    # the count badge: yellow card, ink figure
    final = f"{n:,}"
    fig = _fixed_width_text(f"{shown_count(n, k):,}", final, "badge", 110, S.INK, edge=0)
    lab = _text_img(str(a.get("label") or "AIRCRAFT").upper(), "body", 30, S.INK)
    bw = max(fig.width, lab.width) + 60
    badge = _card(bw, fig.height + lab.height + 44, S.YELLOW)
    badge.alpha_composite(fig, ((bw - fig.width) // 2, 14))
    badge.alpha_composite(lab, ((bw - lab.width) // 2, 14 + fig.height + 6))
    badge = _die(badge, 7)
    _paste_c(canvas, badge, 170, chh / 2 - (28 if per > 1 else 0))
    if per > 1:
        key_ac = _aircraft_sticker(str(a.get("type") or ""), str(a.get("airline") or ""), 90, 3)
        key_t = _text_img(f"= {per} aircraft", "body", 28, S.WHITE)
        row = Image.new("RGBA", (key_ac.width + key_t.width + 14, max(key_ac.height, key_t.height)), (0, 0, 0, 0))
        row.alpha_composite(key_ac, (0, (row.height - key_ac.height) // 2))
        row.alpha_composite(key_t, (key_ac.width + 14, (row.height - key_t.height) // 2))
        _paste_c(canvas, row, 170, chh / 2 + badge.height / 2 + 30)
    return canvas


# ---------------------------------------------------------------------------------------------------------------- cash

def cash_stacks(value: float) -> int:
    """How many stacks a figure earns: grows with its order of magnitude (thousands 1, millions ~4, billions ~7)."""
    v = abs(float(value or 0))
    return int(min(9, max(1, math.floor(math.log10(max(v, 1.0))) - 2)))


def cash_pile(a: Dict[str, Any]) -> Image.Image:
    v = float(a.get("value") or 0)
    k = _k(a)
    cur = str(a.get("currency") or "USD")
    cw, chh = 1120, 540
    canvas = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    ns = cash_stacks(v)
    sz = 150 if ns <= 5 else 124
    bill = _prop_sticker("cash", sz, 4)
    step = int(bill.height * 0.30)                  # each bill rests partly over the one below
    levels = [1 + min(3, int(round(2.5 * math.sin(math.pi * (j + 0.5) / ns)))) for j in range(ns)]   # a heap: tall in the middle
    total = sum(levels)
    placed = int(total * _prog(k, 0.0, 0.9)) if k < 0.999 else total
    gap = min(bill.width * 0.95, 980 / ns)
    x0 = cw / 2 - gap * (ns - 1) / 2
    base_y = chh - bill.height / 2 - 6
    order: List[Tuple[int, int]] = [(lv, j) for lv in range(max(levels)) for j in range(ns) if lv < levels[j]]
    for idx, (lv, j) in enumerate(order[:placed]):
        im = bill
        if idx == placed - 1 and k < 0.999:
            im = _pop(bill, 0.6)
        wob = ((j * 7 + lv * 5) % 5 - 2) * 3
        _paste_c(canvas, im, x0 + j * gap + wob, base_y - lv * step)
    # figure and label above the heap
    kk = _prog(k, 0.0, 0.85)
    shown = v * (1.0 if k >= 0.999 else kk)
    final = A.money(v, cur)
    txt = A.money(shown, cur) if shown else A.money(0, cur)
    fig = _fixed_width_text(txt, final, "badge", 120, S.YELLOW)
    _paste_c(canvas, fig, cw / 2, 70)
    if a.get("label"):
        lab = _sticker_text(str(a["label"]).upper(), "body", 34, S.WHITE, edge=5)
        _paste_c(canvas, lab, cw / 2, 170)
    return canvas


# ---------------------------------------------------------------------------------------------------------------- cabin

CABIN_ROWS, CABIN_LAYOUT = 20, (3, 4, 3)
CABIN_SEATS = CABIN_ROWS * sum(CABIN_LAYOUT)


def cabin_filled(now: float, k: float) -> int:
    """Seats taken at progress k (exactly the load factor at the end)."""
    pct = float(now) * (1.0 if k >= 0.999 else _prog(k))
    return A.seats_filled(pct, CABIN_SEATS)


@lru_cache(maxsize=1)
def _cabin_base() -> Image.Image:
    w, h = 1040, 340
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=150, fill=S.WHITE)
    d.rounded_rectangle((9, 9, w - 10, h - 10), radius=142, fill=S.NAVY)
    return _die(im, 6)


def _seat_layer(filled: int, latest: bool) -> Image.Image:
    ss = 2
    w, h = 960, 320
    lay = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    cw_, sw, sh_, pitch = 44, 32, 22, 25
    i = 0
    for r in range(CABIN_ROWS):
        y = 14.0
        x = 56 + r * cw_
        for b, block in enumerate(CABIN_LAYOUT):
            for _ in range(block):
                full = i < filled
                hot = latest and full and i == filled - 1
                fill = S.WHITE if hot else (S.YELLOW if full else (62, 72, 112, 255))
                out = S.INK if full else (96, 108, 156, 255)
                d.rounded_rectangle((x * ss, y * ss, (x + sw) * ss, (y + sh_) * ss), radius=7 * ss, fill=fill, outline=out, width=2 * ss)
                if full:
                    d.ellipse(((x + sw - 14) * ss, (y + sh_ / 2 - 5) * ss, (x + sw - 4) * ss, (y + sh_ / 2 + 5) * ss), fill=S.INK)
                i += 1
                y += pitch
            y += 16
    return lay.resize((w, h), Image.LANCZOS)


def sticker_cabin(a: Dict[str, Any]) -> Image.Image:
    now = float(a.get("now") or 0)
    k = _k(a)
    cw, chh = 1120, 540
    canvas = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    base = _cabin_base()
    cx, cy = cw / 2, chh - base.height / 2 - 4
    _paste_c(canvas, base, cx, cy)
    n = cabin_filled(now, k)
    seats = _seat_layer(n, k < 0.999)
    canvas.alpha_composite(seats, (int(cx - seats.width / 2 + 10), int(cy - seats.height / 2)))
    shown = now * (1.0 if k >= 0.999 else _prog(k))
    fig = _fixed_width_text(f"{shown:.0f}%", f"{now:.0f}%", "badge", 118, S.YELLOW)
    canvas.alpha_composite(fig, (30, 4))
    lab = _sticker_text(str(a.get("label") or "SEATS FILLED").upper(), "body", 34, S.WHITE, edge=5)
    canvas.alpha_composite(lab, (fig.width + 60, 40))
    if a.get("before") is not None and k > 0.55:
        pill = _pill(f"{float(a['before']):g}% a year earlier", S.WHITE, S.INK, 32)
        canvas.alpha_composite(_pop(pill, M.clamp01((k - 0.55) / 0.2)), (fig.width + 60, 100))
    return canvas


# ---------------------------------------------------------------------------------------------------------------- change

def sticker_change(a: Dict[str, Any]) -> Image.Image:
    if a.get("before") is None or a.get("after") is None:
        raise ValueError("sticker_change needs before and after")
    b0, b1 = float(a["before"]), float(a["after"])
    cur = str(a.get("currency") or "")
    k = _k(a)
    cw, chh = 1000, 560
    canvas = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    top = max(abs(b0), abs(b1)) or 1.0
    base_y, max_h, bw = 470, 330, 190
    after_col = S.RED if b1 < b0 else S.GREEN
    for i, (v, lab, col) in enumerate(((b0, str(a.get("before_label") or "BEFORE"), (214, 220, 236, 255)),
                                       (b1, str(a.get("after_label") or "NOW"), after_col))):
        f = _prog(k, 0.55 * i, 0.55) if k < 0.999 else 1.0
        h = int(max_h * abs(v) / top * f)
        x = 190 + i * 330
        if h >= 6:
            bar = Image.new("RGBA", (bw, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(bar)
            d.rounded_rectangle((0, 0, bw - 1, h - 1), radius=min(18, h // 2), fill=col)
            d.rounded_rectangle((0, 0, bw - 1, h - 1), radius=min(18, h // 2), outline=S.INK, width=3)
            sb = _die(bar, 6)
            canvas.alpha_composite(sb, (x + bw // 2 - sb.width // 2, base_y - h - (sb.height - h) // 2))
            val = A.money(v * f, cur) if cur else A._num(v * f, 1 if abs(v) < 100 else 0)
            fin = A.money(v, cur) if cur else A._num(v, 1 if abs(v) < 100 else 0)
            t = _fixed_width_text(val, fin, "badge", 52, S.WHITE, edge=4)
            canvas.alpha_composite(t, (x + bw // 2 - t.width // 2, base_y - h - t.height - 14 - 8))
        ln = _text_img(lab.upper(), "body", 26, S.WHITE)
        canvas.alpha_composite(ln, (x + bw // 2 - ln.width // 2, base_y + 26))
    tag = A.change_tag(b0, b1)
    if tag and k > 0.62:
        pill = _pill(tag, after_col, S.WHITE, 70, (28, 12), 6)
        pill = _pop(pill, M.clamp01((k - 0.62) / 0.22))
        _paste_c(canvas, pill, 790, 150)
    if a.get("label"):
        lab = _sticker_text(str(a["label"]).upper(), "body", 38, S.YELLOW, edge=5)
        canvas.alpha_composite(lab, (14, 10))
    return canvas


# ---------------------------------------------------------------------------------------------------------------- big number

def big_number_text(v: float, unit: str, sign: str, k: float) -> str:
    kk = 1.0 if k >= 0.999 else _prog(k, 0.0, 0.7)
    if unit in ("USD", "EUR", "GBP"):
        return sign + A.money(v * kk, unit)
    return f"{sign}{v * kk:,.{1 if v < 10 and v != int(v) else 0}f}{unit}"


def sticker_big_number(a: Dict[str, Any]) -> Image.Image:
    if a.get("value") is None:
        raise ValueError("sticker_big_number needs a value")
    v = float(a["value"])
    unit, sign = str(a.get("unit") or ""), str(a.get("sign") or "")
    k = _k(a)
    cw, chh = 1100, 540
    canvas = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
    col = S.GREEN if sign == "+" else (S.RED if sign == "-" else S.YELLOW)
    fig = _fixed_width_text(big_number_text(v, unit, sign, k), big_number_text(v, unit, sign, 1.0), "badge", 190, col, edge=8)
    _paste_c(canvas, fig, cw / 2, 120)
    ac = _aircraft_sticker(str(a.get("type") or ""), str(a.get("airline") or ""), 520, 8)
    slide = (1 - M.ease_out(M.ramp(k, 0.0, 0.6))) * 360
    y = 345
    _paste_c(canvas, ac, cw / 2 - 40 + slide, y)
    if str(a.get("icon")) == "freighter":
        box = _prop_sticker("cargo", 130, 5)
        _paste_c(canvas, box, cw / 2 + 330 + slide * 0.4, y + 70)
    if a.get("label"):
        lab = _sticker_text(str(a["label"]).upper(), "body", 38, S.WHITE, edge=5)
        _paste_c(canvas, lab, cw / 2, chh - 36)
    return canvas


# ---------------------------------------------------------------------------------------------------------------- generic frame

def _frame_card(fr: Image.Image) -> Image.Image:
    """Crop a gfx_air frame to a sticker card (see the module docstring)."""
    fr = fr.convert("RGBA")
    a = fr.getchannel("A")
    opaque = sum(a.resize((64, 36)).point(lambda v: 255 if v > 200 else 0).histogram()[255:]) / (64 * 36)
    if opaque > 0.9:
        mx, my = int(fr.width * 0.03), int(fr.height * 0.03)
        card = fr.crop((mx, my, fr.width - mx, fr.height - my)).resize((CARD_W, CARD_H), Image.LANCZOS)
    else:
        bb = a.point(lambda v: 255 if v > 16 else 0).getbbox() or (0, 0, fr.width, fr.height)
        pad = 36
        bb = (max(0, bb[0] - pad), max(0, bb[1] - pad), min(fr.width, bb[2] + pad), min(fr.height, bb[3] + pad))
        crop = fr.crop(bb)
        sc = min(CARD_W / crop.width, CARD_H / crop.height, 1.6)
        crop = crop.resize((max(1, int(crop.width * sc)), max(1, int(crop.height * sc))), Image.LANCZOS)
        card = Image.new("RGBA", crop.size, (20, 26, 44, 255))
        card.alpha_composite(crop)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius=34, fill=255)
    out = Image.new("RGBA", card.size, (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    return _die(out, 9)


def gfx_frame(a: Dict[str, Any]) -> Image.Image:
    name = str(a.get("fn") or "")
    if not name.startswith("lay_") or not hasattr(A, name):
        raise KeyError(name)
    dur = max(0.5, float(a.get("dur") or 4.0))
    fr = getattr(A, name)(_k(a) * dur, dur, dict(a.get("params") or {}))
    if fr is None:
        raise ValueError(f"{name}: nothing to show")
    return _frame_card(fr)


# ---------------------------------------------------------------------------------------------------------------- skin + planner call

SKIN: Dict[str, str] = {
    "gfx_air.lay_fleet": "sticker_fleet",
    "gfx_air.lay_seats": "sticker_cabin",
    "gfx_air.lay_change": "sticker_change",
    "gfx_air.lay_big_number": "sticker_big_number",
    "gfx_air.lay_network": "gfx_frame",
    "gfx_air.lay_timeline": "gfx_frame",
    "gfx_air.lay_crew": "gfx_frame",
    "gfx_air.lay_gauge": "gfx_frame",
    "gfx_air.lay_runway": "gfx_frame",
    "gfx_air.lay_approach": "gfx_frame",
    "gfx_air.lay_descent": "gfx_frame",
    "gfx_air.lay_title": "gfx_frame",
}
# cash_pile has no gfx_air twin: the planner calls it directly for a money figure that is not a before / after pair.


def skin_kind(layer_name: str) -> str:
    n = str(layer_name or "")
    if not n.startswith("gfx_air."):
        n = "gfx_air." + n
    return SKIN.get(n, "gfx_frame")


def add_graphic(st: G.Stage, at: float, layer_name: str, params: Optional[Dict[str, Any]], dur: float = 4.0, *,
                pos: Tuple[float, float] = STAGE_POS, enter: str = "pop", **kw: Any) -> str:
    """Add the sticker skin of a gfx_air graphic ('gfx_air.lay_fleet' or 'lay_fleet') to the stage; returns the element id."""
    kind = skin_kind(layer_name)
    p = dict(params or {})
    if kind == "gfx_frame":
        short = str(layer_name).split(".")[-1]
        args = {"fn": short, "params": p, "dur": float(dur), "_flat": True}
        anim = float(dur)
    else:
        args = dict(p)
        args["_flat"] = True
        anim = min(float(dur), ANIM_S)
    return st.add(kind, at, args, pos=pos, enter=enter, edge=False, float_=False, anim=anim, **kw)


G.register("sticker_fleet", sticker_fleet)
G.register("cash_pile", cash_pile)
G.register("sticker_cabin", sticker_cabin)
G.register("sticker_change", sticker_change)
G.register("sticker_big_number", sticker_big_number)
G.register("gfx_frame", gfx_frame)
