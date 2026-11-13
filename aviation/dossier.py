"""Dossier cards (docs/aviation/J11_REFERENCE_STUDY.md J4): the analysis skin - a graphite backdrop with a faint grid, a title
top-left with a short orange rule over it and a grey source line under it, one idea per card. A third skin for numbers,
comparisons and quotes, next to the blue news skin (gfx_air) and the sticker skin (gfx_sticker); nothing old is replaced.
Contract: fn(t, dur, params) -> RGBA W x H (full frame) or None when there is nothing to show. Every card animates.

    lay_share    title, sub, parts [{label, pct, side}], big?            one long bar split by side, big % on the right
    lay_range    title, sub, lo, hi, unit, note?, ticks?                 a bar between two values, ticks, a red note
    lay_icons    title, sub, count, label, per?                          aircraft icons filling rows, big counting number
    lay_markers  title, sub, start, end, markers [{year, label, side}], stops [{from, to, label}]   axis + markers + stopped lines
    lay_options  title, sub, options [{title, sub, side}]                cards side by side, coloured left rule
    lay_quotes   title, sub, quotes [{text, who, side}]                  stacked quote cards (two claims that disagree)
    lay_flow     title, sub, left, right, items [str]                    two columns, arrows running between the rows
    lay_family   title, sub, members [{name, sub, type, airline}]        variant cards added one by one with silhouettes
Sides: 'a' orange, 'b' light blue, 'warn' red, anything else grey - the same colours in every card of a film (colour = side).
Every word and number comes from the params (the narration, the CSV or the catalog); nothing is invented here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M

from . import style as S

W, H = S.W, S.H
BG = (20, 21, 24, 255)
GRID = (27, 28, 32, 255)       # a faint grid: a shade just above the graphite, drawn opaque (never a see-through white)
ORANGE = (242, 168, 44, 255)
BLUE = (120, 172, 232, 255)
RED = (226, 70, 58, 255)
GREY = (150, 154, 162, 255)
PANEL = (32, 34, 39, 235)
SIDES = {"a": ORANGE, "b": BLUE, "warn": RED}


def side(s: Any) -> tuple:
    return SIDES.get(str(s or "").lower(), GREY)


@lru_cache(maxsize=2)
def _backdrop(w: int, h: int) -> Image.Image:
    im = Image.new("RGBA", (w, h), BG)
    d = ImageDraw.Draw(im)
    step = int(48 * S.scale())
    for x in range(0, w, step):
        d.line((x, 0, x, h), fill=GRID)
    for y in range(0, h, step):
        d.line((0, y, w, y), fill=GRID)
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((-w * 0.2, -h * 0.4, w * 0.9, h * 0.9), fill=60)
    im.paste((40, 42, 48, 255), (0, 0), glow.filter(ImageFilter.GaussianBlur(w * 0.1)))
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).rectangle((0, 0, w, h), fill=0)
    return im


def _frame(t: float, p: Dict[str, Any]) -> Image.Image:
    """Backdrop + the title system; the title slides in first, the card's content after."""
    im = _backdrop(W, H).copy()
    d = ImageDraw.Draw(im)
    sc = S.scale()
    k = M.ease_out(M.ramp(t, 0.0, 0.45))
    x, y = int(64 * sc), int(58 * sc)
    d.rectangle((x, y, x + int(36 * sc * k), y + int(4 * sc)), fill=ORANGE)
    title = str(p.get("title") or "").upper()
    if title:
        f = S.font("title", 30)
        d.text((x, y + int(16 * sc)), title, font=f, fill=(245, 245, 245, int(255 * k)))
    sub = str(p.get("sub") or "").upper()
    if sub:
        fs = S.font("body", 14)
        d.text((x, y + int(56 * sc)), sub, font=fs, fill=GREY[:3] + (int(220 * k),))
    return im


def _k(t: float, start: float, length: float = 0.8) -> float:
    return M.ease_out(M.ramp(t, start, length))


def _text(d, xy, text, size, fill=S.WHITE, role="body"):
    d.text(xy, str(text), font=S.font(role, size), fill=fill)


def _silhouette(typ: str, width: int, fill=(205, 210, 218, 255)) -> Image.Image:
    from . import stickers as SK
    im = SK.aircraft(typ or "narrow", "", int(width))
    a = im.getchannel("A")
    out = Image.new("RGBA", im.size, fill)
    out.putalpha(a)
    return out


# ---------------------------------------------------------------------------------------------------------------- cards

def lay_share(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    parts = [x for x in (p.get("parts") or []) if float(x.get("pct") or 0) > 0]
    if not parts:
        return None
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    x0, x1, y = int(120 * sc), int(1160 * sc), int(330 * sc)
    bh = int(34 * sc)
    k = _k(t, 0.5, 1.2)
    total = sum(float(x["pct"]) for x in parts) or 1.0
    d.rectangle((x0, y, x1, y + bh), fill=(48, 50, 56, 255))
    cx, lx = x0, x0
    for i, x in enumerate(parts):
        full = (x1 - x0) * float(x["pct"]) / max(100.0, total)
        w = full * k
        d.rectangle((cx, y, cx + w, y + bh), fill=side(x.get("side") or ("a" if i == 0 else "b")))
        _text(d, (lx + 4, y - int(30 * sc)), str(x.get("label") or "").upper(), 15, GREY)   # each label over its own part
        cx += w
        lx += full
    big = str(p.get("big") or f"{parts[0]['pct']:g} %")
    if k > 0.6:
        _text(d, (x1 - int(150 * sc), y - int(80 * sc)), big, 46, side(parts[0].get("side") or "a"), "title")
    sil = _silhouette(p.get("type") or "wide", int(300 * sc))     # always the aircraft under the bar (J-11 J4a), the line's type if named
    im.alpha_composite(_fade(sil, _k(t, 0.3, 0.8)), (int(W / 2 - sil.width / 2), y + int(90 * sc)))
    return im


def lay_range(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    lo, hi = p.get("lo"), p.get("hi")
    if lo is None or hi is None:
        return None
    lo, hi = float(lo), float(hi)
    unit = str(p.get("unit") or "")
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    a0, a1, y = int(140 * sc), int(1140 * sc), int(380 * sc)
    span = max(1e-9, hi - lo)
    pad = span * 0.6
    vmin, vmax = lo - pad, hi + pad
    X = lambda v: a0 + (v - vmin) / (vmax - vmin) * (a1 - a0)
    d.line((a0, y, a1, y), fill=(70, 72, 80, 255), width=2)
    for i in range(6):
        v = vmin + i * (vmax - vmin) / 5
        d.line((X(v), y - 6, X(v), y + 6), fill=(90, 92, 100, 255), width=2)
        _text(d, (X(v) - 22, y + 16), f"{unit}{v:,.1f}", 12, GREY)
    k = _k(t, 0.5, 1.2)
    d.rounded_rectangle((X(lo), y - 7, X(lo) + (X(hi) - X(lo)) * k, y + 7), radius=7, fill=ORANGE)
    _text(d, (X(lo) - 30, y - 60), f"{unit}{lo:g}{p.get('suffix', '')}", 30, ORANGE, "title")
    if k > 0.95:
        _text(d, (X(hi) - 30, y - 60), f"{unit}{hi:g}{p.get('suffix', '')}", 30, ORANGE, "title")
    if p.get("note") and t > 1.6:
        d.rectangle((a0, y + 80, a0 + 4, y + 104), fill=RED)
        _text(d, (a0 + 14, y + 82), str(p["note"]).upper(), 15, S.WHITE)
    return im


def _icon(d, x: float, y: float, s: float, fill) -> None:
    """A small top-view aircraft: fuselage, swept wings, tailplane."""
    d.polygon([(x, y - s), (x + s * 0.12, y - s * 0.3), (x + s * 0.9, y + s * 0.2), (x + s * 0.9, y + s * 0.35), (x + s * 0.12, y + s * 0.15),
               (x + s * 0.1, y + s * 0.7), (x + s * 0.4, y + s * 0.95), (x + s * 0.4, y + s * 1.05), (x, y + s * 0.9), (x - s * 0.4, y + s * 1.05),
               (x - s * 0.4, y + s * 0.95), (x - s * 0.1, y + s * 0.7), (x - s * 0.12, y + s * 0.15), (x - s * 0.9, y + s * 0.35),
               (x - s * 0.9, y + s * 0.2), (x - s * 0.12, y - s * 0.3)], fill=fill)


def icons_shown(count: int, per: int, k: float) -> int:
    return int(round(min(count, 200) / max(1, per) * M.clamp01(k)))


def lay_icons(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    count = int(p.get("count") or 0)
    if count <= 0:
        return None
    per = int(p.get("per") or (1 if count <= 120 else (5 if count <= 600 else 10)))
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    n_icons = max(1, count // per)
    cols = min(20, n_icons)
    rows = (n_icons + cols - 1) // cols
    s = int(min(18, 300 / max(1, rows), 760 / (cols * 2.6)) * sc)     # the grid ends left of the big number (x 1000)
    gx, gy = int(110 * sc), int(250 * sc)
    k = _k(t, 0.4, 1.8)
    shown = icons_shown(count, per, k)
    col = side(p.get("side") or "a")
    for i in range(n_icons):
        r, c = divmod(i, cols)
        _icon(d, gx + c * s * 2.6, gy + r * s * 2.6, s, col if i < shown else (60, 62, 68, 255))
    num = int(round(count * k))
    _text(d, (int(1000 * sc), int(300 * sc)), f"{'~' if p.get('approx') else ''}{num:,}", 64, ORANGE, "title")
    if p.get("label"):
        _text(d, (int(1000 * sc), int(390 * sc)), str(p["label"]).upper(), 15, S.WHITE)
    if per > 1 and k > 0.9:
        _text(d, (gx, gy + rows * s * 2.6 + 20), f"ONE ICON = {per} AIRCRAFT", 13, GREY)
    return im


def lay_markers(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    start, end = p.get("start"), p.get("end")
    if not start or not end:
        return None
    start, end = int(start), int(end)
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    a0, a1, y = int(110 * sc), int(1170 * sc), int(560 * sc)
    X = lambda yr: a0 + (float(yr) - start) / max(1, end - start) * (a1 - a0)
    ka = _k(t, 0.3, 0.8)
    d.line((a0, y, a0 + (a1 - a0) * ka, y), fill=(80, 82, 90, 255), width=2)
    step = max(1, (end - start) // 6)
    for yr in range(start, end + 1, step):
        _text(d, (X(yr) - 16, y + 14), yr, 12, GREY)
    for i, st in enumerate(p.get("stops") or []):
        kk = _k(t, 0.8 + i * 0.6, 1.0)
        yy = y - int((150 + 70 * i) * sc)
        xa, xb = X(st["from"]), X(st["to"])
        col = side(st.get("side") or ("a" if i == 0 else "b"))
        d.line((xa, yy, xa + (xb - xa) * kk, yy), fill=col, width=4)
        _text(d, (xa, yy - 26), str(st.get("label") or "").upper(), 13, S.WHITE)
        if kk >= 1 and st.get("stopped"):
            d.line((xb - 8, yy - 8, xb + 8, yy + 8), fill=RED, width=4)
            d.line((xb - 8, yy + 8, xb + 8, yy - 8), fill=RED, width=4)
    for i, m in enumerate(p.get("markers") or []):
        km = _k(t, 0.9 + i * 0.5, 0.5)
        if km <= 0:
            continue
        x = X(m["year"])
        top = y - int((120 + 60 * (i % 3)) * sc)
        col = side(m.get("side"))
        d.line((x, y, x, y - (y - top) * km), fill=col, width=2)
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=col)
        if km > 0.8:
            lab = str(m.get("label") or m["year"]).upper()
            f = S.font("body", 13)
            tw = d.textlength(lab, font=f)
            d.rectangle((x - 4, top - 30, x + tw + 14, top - 6), fill=PANEL)
            d.text((x + 5, top - 26), lab, font=f, fill=S.WHITE)
    return im


def lay_options(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    opts = list(p.get("options") or [])[:3]
    if not opts:
        return None
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    n = len(opts)
    cw = int(min(470, 1060 / n - 24) * sc)
    x = int(W / 2 - (n * cw + (n - 1) * 30 * sc) / 2)
    y, ch = int(250 * sc), int(270 * sc)
    for i, o in enumerate(opts):
        k = _k(t, 0.4 + 0.45 * i, 0.6)
        if k <= 0:
            continue
        yy = y + int(30 * (1 - k))
        col = side(o.get("side") or ("b" if i == 0 else "a"))
        d.rectangle((x, yy, x + cw, yy + ch), fill=PANEL)
        d.rectangle((x, yy, x + 5, yy + ch), fill=col)
        _text(d, (x + 26, yy + 24), str(o.get("title") or "").upper(), 26, col, "title")
        _text(d, (x + 26, yy + 66), str(o.get("sub") or "").upper(), 13, GREY)
        sil = _silhouette(o.get("type") or "narrow", int(cw * 0.6))      # every option card shows its aircraft (J-11 J4e)
        im.alpha_composite(_fade(sil, k), (int(x + cw / 2 - sil.width / 2), int(yy + ch - sil.height - 30 * sc)))
        x += cw + int(30 * sc)
    return im


def lay_quotes(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    qs = [q for q in (p.get("quotes") or []) if q.get("text")][:2]
    if not qs:
        return None
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    one = len(qs) == 1
    f = S.font("title", 44 if one else 28)        # a single quote is the card: big, centred (it sat small at the top)
    y = int((270 if one else 230) * sc)
    for i, q in enumerate(qs):
        k = _k(t, 0.4 + 1.2 * i, 0.6)
        if k <= 0:
            continue
        x = int((150 if one else 110 + 330 * i) * sc)
        boxw = int((980 if one else 700) * sc)
        words, lines, cur = str(q["text"]).upper().split(), [], ""
        for w in words:
            tt = (cur + " " + w).strip()
            if d.textlength(tt, font=f) > boxw - 100 * sc and cur:
                lines.append(cur)
                cur = w
            else:
                cur = tt
        lines.append(cur)
        lines = lines[:3]
        bh = len(lines) * int(f.size * 1.2) + int(70 * sc)
        col = side(q.get("side") or ("warn" if i else "a"))
        d.rectangle((x, y, x + boxw, y + bh), fill=PANEL)
        d.rectangle((x, y, x + 5, y + bh), fill=col)
        _text(d, (x + 22, y + 6), "“", 46, col, "title")
        yy = y + int(26 * sc)
        for ln in lines:
            d.text((x + int(58 * sc), yy), ln, font=f, fill=S.WHITE)
            yy += int(f.size * 1.2)
        if q.get("who"):
            _text(d, (x + int(58 * sc), yy + 8), str(q["who"]).upper(), 13, GREY)
        y += bh + int(40 * sc)
    return im


def lay_flow(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    items = list(p.get("items") or [])[:5]
    if not items:
        return None
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    lx, rx, y0 = int(260 * sc), int(820 * sc), int(250 * sc)
    _text(d, (lx + int(180 * sc), y0 - int(40 * sc)), str(p.get("left") or "").upper(), 18, BLUE, "title")
    _text(d, (rx, y0 - int(40 * sc)), str(p.get("right") or "").upper(), 18, ORANGE, "title")
    for i, it in enumerate(items):
        y = y0 + i * int(64 * sc)
        k = _k(t, 0.5 + 0.35 * i, 0.5)
        if k <= 0:
            continue
        d.rectangle((lx - int(150 * sc), y, lx - int(146 * sc), y + int(26 * sc)), fill=S.WHITE)
        _text(d, (lx - int(136 * sc), y + 3), str(it).upper(), 14, S.WHITE)
        phase = (t * 0.9 + i * 0.17) % 1.0                         # arrows keep running left -> right
        for j in range(5):
            ax = lx + int(200 * sc) + ((j + phase) / 5.0) * (rx - lx - int(240 * sc))
            d.line((ax, y + 13, ax + 18, y + 13), fill=BLUE, width=2)
            d.polygon([(ax + 18, y + 7), (ax + 28, y + 13), (ax + 18, y + 19)], fill=BLUE)
    return im


def lay_family(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    mem = list(p.get("members") or [])[:4]
    if not mem:
        return None
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    cw, ch = int(520 * sc), int(170 * sc)
    for i, m in enumerate(mem):
        k = _k(t, 0.4 + 0.6 * i, 0.5)
        if k <= 0:
            continue
        r, c = divmod(i, 2)
        x, y = int((110 + c * 560) * sc), int((210 + r * 200) * sc) + int(20 * (1 - k))
        col = side(m.get("side") or ("a" if c == 0 else "b"))
        d.rectangle((x, y, x + cw, y + ch), fill=PANEL)
        d.rectangle((x, y, x + 4, y + ch), fill=col)
        _text(d, (x + 20, y + 16), str(m.get("name") or "").upper(), 24, col, "title")
        _text(d, (x + 20, y + 52), str(m.get("sub") or "").upper(), 12, GREY)
        sil = _silhouette(m.get("type") or "narrow", int(cw * 0.42))     # every variant card shows its aircraft (J-11 J4i)
        im.alpha_composite(_fade(sil, k), (x + cw - sil.width - 20, y + ch - sil.height - 16))
    return im


CREAM = (238, 232, 218, 255)
INK = (26, 26, 28, 255)


def lay_newspaper(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    """The press said ... (J4g): a cream paper card with the outlet, the date and the headline TYPESET (never a fake page); the
    words after `split` (if given) turn red as the second line. A small note under it when the CSV gives one."""
    head = str(p.get("headline") or "").strip()
    if not head:
        return None
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    k = _k(t, 0.3, 0.6)
    x, y, w, h = int(330 * sc), int(220 * sc) + int(30 * (1 - k)), int(620 * sc), int(300 * sc)
    card = Image.new("RGBA", (w, h), CREAM)
    cd = ImageDraw.Draw(card)
    cd.text((26, 22), str(p.get("outlet") or "").upper(), font=S.font("serif", 30), fill=INK)
    cd.line((26, 66, w - 26, 66), fill=(120, 112, 100, 255), width=2)
    cd.text((26, 76), str(p.get("date") or "").upper(), font=S.font("body", 13), fill=(110, 104, 96, 255))
    kh = _k(t, 0.9, 0.6)
    if kh > 0:
        f = S.font("title", 38)
        split = str(p.get("split") or "")
        parts = [head.split(split, 1)[0].strip(), split + head.split(split, 1)[1]] if split and split in head else [head]
        yy = 118
        for i, part in enumerate(parts):
            words, line = part.upper().split(), ""
            for wd in words:
                tt = (line + " " + wd).strip()
                if cd.textlength(tt, font=f) > w - 52 and line:
                    cd.text((26, yy), line, font=f, fill=INK if i == 0 else RED)
                    yy += int(f.size * 1.1)
                    line = wd
                else:
                    line = tt
            if line:
                cd.text((26, yy), line, font=f, fill=INK if i == 0 else RED)
                yy += int(f.size * 1.1)
    sh = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((20, 26, w + 20, h + 26), fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), (x - 20, y - 20))
    card.putalpha(card.getchannel("A").point(lambda v: int(v * k)))
    im.alpha_composite(card, (x, y))
    if p.get("note") and t > 1.6:
        d.rectangle((x, y + h + 26, x + 4, y + h + 50), fill=ORANGE)
        _text(d, (x + 14, y + h + 28), str(p["note"]).upper(), 14, S.WHITE)
    return im


def lay_reveal(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    """What it became (J4j): the first type's picture on the left, a grey silhouette with '?' on the right; then an arrow and the
    second type slides in where the '?' was. Types / airlines from the line; the pictures are the Flow stickers when made."""
    a, b = p.get("from") or {}, p.get("to") or {}
    if not a.get("type") or not b.get("type"):
        return None
    from . import sticker_flow as SF
    from . import stickers as SK
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    w = int(470 * sc)
    left = SK.die_cut(SF.aircraft_image(a["type"], a.get("airline", ""), w), 6)
    k0 = _k(t, 0.3, 0.6)
    if k0 > 0:
        im.alpha_composite(_fade(left, k0), (int(90 * sc), int(300 * sc)))
        _text(d, (int(100 * sc), int(300 * sc) + left.height + 10), str(a.get("label") or "").upper(), 16, side(a.get("side") or "b"))
    k1 = _k(t, 1.0, 0.8)
    rx, ry = int(720 * sc), int(300 * sc)
    if k1 < 1:
        sil = _silhouette(b["type"], w, fill=(70, 72, 80, 255))
        im.alpha_composite(sil, (rx, ry))
        _text(d, (rx + sil.width // 2 - 14, ry + sil.height // 2 - 40), "?", 64, (150, 152, 160, 255), "title")
    if k1 > 0:
        d.line((int(600 * sc), int(380 * sc), int(600 * sc) + int(80 * sc * k1), int(380 * sc)), fill=S.WHITE, width=3)
        right = SK.die_cut(SF.aircraft_image(b["type"], b.get("airline", ""), w), 6)
        im.alpha_composite(_fade(right, k1), (rx + int(60 * (1 - k1)), ry))
        if k1 > 0.8:
            _text(d, (rx + 10, ry + right.height + 10), str(b.get("label") or "").upper(), 16, side(b.get("side") or "a"))
    return im


def _fade(im: Image.Image, k: float) -> Image.Image:
    if k >= 0.999:
        return im
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * k)))
    return out


import re as _re

# where each part sits on a side view, nose to the right, as fractions of the picture (x, y) - the Flow stickers and the code kit
# both draw a plain side view, so one table serves every type
PARTS = (("cockpit", r"\bcockpit\b|\bflight deck\b|\bcanopy\b", (0.93, 0.40)),
         ("engines", r"\bengines?\b|\bturbofans?\b|\bnacelles?\b", (0.58, 0.72)),
         ("wings", r"\bwings?\b|\bwingspan\b|\bwinglets?\b", (0.50, 0.62)),
         ("tail", r"\btail\b|\bfin\b|\brudder\b|\bstabiliser\b|\bstabilizer\b", (0.08, 0.22)),
         ("landing gear", r"\blanding gear\b|\bundercarriage\b|\bwheels\b", (0.62, 0.92)),
         ("fuel tanks", r"\bfuel tanks?\b|\btanks?\b", (0.47, 0.60)),
         ("cabin", r"\bcabin\b|\bseats?\b|\bwindows?\b", (0.66, 0.42)),
         ("doors", r"\bdoors?\b", (0.84, 0.50)),
         ("fuselage", r"\bfuselage\b|\bbody\b|\bstretched\b|\blonger\b", (0.40, 0.45)))
_LENGTH = _re.compile(r"(\d+(?:\.\d+)?)\s*(?:m|metres|meters)\s+long|\blength of\s+(\d+(?:\.\d+)?)\s*(?:m|metres|meters)", _re.I)


def parts_in(text: str) -> List[str]:
    return [name for name, rx, _ in PARTS if _re.search(rx, str(text or ""), _re.I)]


@lru_cache(maxsize=2)
def _hangar(w: int, h: int) -> Image.Image:
    """A bright studio hangar (J-11 study J3): pale walls, a few arch ribs, a light floor with a soft reflection band."""
    im = Image.new("RGBA", (w, h), (226, 229, 234, 255))
    d = ImageDraw.Draw(im)
    for y in range(h):
        g = int(236 - 26 * (y / h))
        d.line((0, y, w, y), fill=(g, g + 2, g + 6, 255))
    for i in range(6):
        x = int(w * (0.08 + i * 0.17))
        d.arc((x - w * 0.5, -h * 0.3, x + w * 0.5, h * 1.1), 200, 340, fill=(205, 208, 214, 255), width=3)
    d.rectangle((0, int(h * 0.74), w, h), fill=(214, 217, 222, 255))
    d.line((0, int(h * 0.74), w, int(h * 0.74)), fill=(196, 199, 206, 255), width=2)
    return im


def lay_callouts(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    """Part callouts on the line's aircraft: the plane large (its Flow sticker when made) in the bright hangar or on the dark
    card, a label with a thin leader line for each part the line names, one after another, and a dimension line when the line
    states a length."""
    parts = [x for x in (p.get("parts") or []) if any(x == n for n, _, _ in PARTS)][:4]
    if not parts or not p.get("type"):
        return None
    from . import sticker_flow as SF
    sc = S.scale()
    light = p.get("look", "hangar") == "hangar"
    im = _hangar(W, H).copy() if light else _backdrop(W, H).copy()
    d = ImageDraw.Draw(im)
    ink = (24, 26, 30, 255) if light else S.WHITE
    k = _k(t, 0.0, 0.45)
    title = str(p.get("title") or "").upper()
    if title:
        d.rectangle((int(64 * sc), int(58 * sc), int(64 * sc) + int(36 * sc * k), int(62 * sc)), fill=ORANGE)
        d.text((int(64 * sc), int(74 * sc)), title, font=S.font("title", 30), fill=ink[:3] + (int(255 * k),))
    pw = int(820 * sc)
    plane = SF.aircraft_image(p["type"], p.get("airline", ""), pw)
    drift = int(18 * sc * M.clamp01(t / max(1.0, dur)))           # a slow camera drift over the model
    px, py = int(W / 2 - plane.width / 2) - drift, int(H * 0.56 - plane.height / 2)
    if light:
        sh = Image.new("RGBA", (plane.width, plane.height // 4), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse((plane.width * 0.1, 0, plane.width * 0.9, sh.height), fill=(0, 0, 0, 70))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)), (px, int(H * 0.74) - sh.height // 2))
    im.alpha_composite(_fade(plane, _k(t, 0.15, 0.6)), (px, py))
    # labels in spread slots (left to right in the order the parts sit), alternating above / below the plane: never stacked
    order = sorted(parts, key=lambda n: next(xy for m, _, xy in PARTS if m == n)[0])
    n = len(order)
    for i, name in enumerate(order):
        kk = _k(t, 0.8 + 0.55 * i, 0.5)
        if kk <= 0:
            continue
        fx, fy = next(xy for m, _, xy in PARTS if m == name)
        ax, ay = px + plane.width * fx, py + plane.height * fy
        up = i % 2 == 0
        lx = px + plane.width * (0.12 + 0.76 * (i + 0.5) / n)
        ly = (py - int(52 * sc)) if up else (py + plane.height + int(48 * sc))
        d.ellipse((ax - 5, ay - 5, ax + 5, ay + 5), fill=ORANGE)
        d.line((ax, ay, ax + (lx - ax) * kk, ay + (ly - ay) * kk), fill=ink, width=2)
        if kk > 0.8:
            f = S.font("body", 15)
            lab = name.upper()
            tw = d.textlength(lab, font=f)
            bx = lx - (tw + 24) / 2
            d.rectangle((bx, ly - 14, bx + tw + 24, ly + 14), fill=(24, 26, 30, 230))
            d.rectangle((bx, ly - 14, bx + 4, ly + 14), fill=ORANGE)
            d.text((bx + 13, ly - 9), lab, font=f, fill=S.WHITE)
    if p.get("length_m") and t > 0.8:
        kd = _k(t, 0.8, 0.8)
        y = py - int(110 * sc)                                  # above the plane and its upper labels
        x0, x1 = px + plane.width * 0.02, px + plane.width * 0.98
        d.line((x0, y, x0 + (x1 - x0) * kd, y), fill=ORANGE, width=2)
        d.line((x0, y - 8, x0, y + 8), fill=ORANGE, width=2)
        if kd >= 1:
            d.line((x1, y - 8, x1, y + 8), fill=ORANGE, width=2)
            lab = f"~{p['length_m']:g} M"
            f = S.font("title", 22)
            d.text(((x0 + x1) / 2 - d.textlength(lab, font=f) / 2, y - 32), lab, font=f, fill=ink)
    return im


def lay_figure(t: float, dur: float, p: Dict[str, Any]) -> Optional[Image.Image]:
    """One figure that matters (J4): a big counting value, its word under it, and a change chip ('+40 % ON A YEAR EARLIER') in
    red or green when the line states the change."""
    val = p.get("value")
    if val is None:
        return None
    im = _frame(t, p)
    d = ImageDraw.Draw(im)
    sc = S.scale()
    k = _k(t, 0.4, 1.2)
    unit, suf = str(p.get("unit") or ""), str(p.get("suffix") or "")
    shown = float(val) * k
    dec = 1 if abs(float(val)) < 100 and float(val) != int(float(val)) else 0
    txt = f"{unit}{shown:,.{dec}f}{suf}"
    col = RED if p.get("bad") else ORANGE
    f = S.font("title", 96)
    d.text((int(110 * sc), int(250 * sc)), txt, font=f, fill=col)
    if p.get("label"):
        _text(d, (int(116 * sc), int(250 * sc) + int(f.size * 1.15)), str(p["label"]).upper(), 18, S.WHITE)
    if p.get("delta") and t > 1.4:
        kd = _k(t, 1.4, 0.4)
        lab = str(p["delta"]).upper()
        fd = S.font("body", 18)
        tw = d.textlength(lab, font=fd)
        x, y = int(116 * sc), int(250 * sc) + int(f.size * 1.15) + int(48 * sc)
        dc = RED if p.get("delta_bad") else (80, 200, 130, 255)
        d.rectangle((x, y, x + (tw + 30) * kd, y + 36), fill=(32, 34, 39, 235))
        d.rectangle((x, y, x + 5, y + 36), fill=dc)
        if kd > 0.9:
            d.text((x + 16, y + 7), lab, font=fd, fill=S.WHITE)
    return im


CARDS = {"dossier.lay_share": lay_share, "dossier.lay_range": lay_range, "dossier.lay_icons": lay_icons,
         "dossier.lay_markers": lay_markers, "dossier.lay_options": lay_options, "dossier.lay_quotes": lay_quotes,
         "dossier.lay_flow": lay_flow, "dossier.lay_family": lay_family, "dossier.lay_newspaper": lay_newspaper,
         "dossier.lay_reveal": lay_reveal, "dossier.lay_callouts": lay_callouts, "dossier.lay_figure": lay_figure}


# ---------------------------------------------------------------------------------------------------------------- picking

import re as _re

_QUOTE = _re.compile(r"[\"“]([^\"”]{12,140})[\"”]")
_SAID = _re.compile(r"\b([A-Z][\w\-]+(?:\s+[A-Z][\w\-]+){0,3})\s+(?:said|says|called|described|told|wrote|added)\b")
_RANGE_WORDS = _re.compile(r"\bbetween\b|\bestimat\w*|\bup to\b|\bsomewhere\b|\branging\b|\bfrom\b.*\bto\b", _re.I)
_SHARE_WORDS = _re.compile(r"\bpercent of\b|\bper cent of\b|%\s+of\b|\bshare\b|\bmade in\b|\bbuilt in\b|\blocal\w*\b|\bimport\w*|\bstake\b|\bof the\b|\bowned\b|\bsupplied\b", _re.I)
_LABELS = (("price", "THE PRICE"), ("cost", "THE COST"), ("profit", "PROFIT"), ("loss", "LOSS"), ("revenue", "REVENUE"),
           ("stake", "THE STAKE"), ("share", "THE SHARE"), ("order", "THE ORDER"), ("deal", "THE DEAL"), ("fleet", "THE FLEET"),
           ("passenger", "PASSENGERS"), ("import", "IMPORTS"))


def _title(c: Any, text: str, fallback: str) -> str:
    low = text.lower()
    lab = next((L for w, L in _LABELS if w in low), fallback)
    al = c.airlines[0]["name"] if getattr(c, "airlines", None) else ""
    return f"{al}: {lab}" if al and lab not in (al.upper(),) else lab


def pick(c: Any, r: Optional[Dict[str, Any]] = None) -> Optional[tuple]:
    """(layer, params) of the dossier card the line's own words and numbers call for, or None. Only what the line states:
    two money values with range words -> range bar; a percentage with share words -> share bar; an aircraft count -> icon grid;
    a quoted sentence -> quote card; two or more years -> marker timeline."""
    text = str(getattr(c, "text", "") or "")
    v = getattr(c, "values", {}) or {}
    years = [int(y) for y in v.get("years") or []]
    sub = (f"{min(years)}" if years else "")
    acs = [a for a in getattr(c, "aircraft", [])]
    if len({a["id"] for a in acs}) >= 2 and _re.search(r"\binto\b|\bbecame\b|\bturned\b|\bdeveloped\b|\bevolved\b|\breplaced by\b", text, _re.I):
        from . import sides as SD
        al = getattr(c, "airlines", [])
        aid = al[0]["id"] if al else ""
        return "dossier.lay_reveal", {"title": "What it became", "sub": sub,
                                      "from": {"type": acs[0]["id"], "airline": aid, "label": acs[0]["name"], "side": "b"},
                                      "to": {"type": acs[1]["id"], "airline": aid, "label": acs[1]["name"], "side": "a"}}
    pts = parts_in(text)
    if pts and acs:
        al = getattr(c, "airlines", [])
        m = _LENGTH.search(text)
        ln = float(m.group(1) or m.group(2)) if m else None
        return "dossier.lay_callouts", {"title": acs[0]["name"], "type": acs[0]["id"], "airline": al[0]["id"] if al else "",
                                        "parts": pts, "length_m": ln, "look": "hangar"}
    q = _QUOTE.search(text)
    if q:
        who = (r or {}).get("person") or (_SAID.search(text).group(1) if _SAID.search(text) else "")
        return "dossier.lay_quotes", {"title": "On the record", "sub": sub, "quotes": [{"text": q.group(1).strip(), "who": who, "side": "a"}]}
    money = v.get("money") or []
    unit_of = lambda cur: {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "SGD": "S$"}.get(cur, "")

    def _scaled(x: float):
        return (round(x / 1e9, 3), " BN") if x >= 1e9 else ((round(x / 1e6, 1), " M") if x >= 1e6 else (x, ""))
    # 'N are in Europe, N in Africa ...': the split of a whole, as a share bar of several parts
    split = _re.findall(r"(\d+)\s+(?:are|were)?\s*in\s+((?:South and Central |North |South |Central |Southern |Northern )?"
                        r"(?:Europe|America|Africa|Asia|the Middle East|Oceania|Brazil|the United States))", text)
    if len(split) >= 3:
        tot = sum(int(n) for n, _ in split)
        sides_ = ["a", "b", "warn", "grey"]
        return "dossier.lay_share", {"title": _title(c, text, "WHERE IT FLIES"), "sub": sub, "big": str(tot),
                                     "parts": [{"label": f"{reg} {n}", "pct": 100.0 * int(n) / tot, "side": sides_[min(i, 3)]}
                                               for i, (n, reg) in enumerate(split)]}
    # 'X for 44.9 percent of Y': a stake bought for a price - the share bar with the price as the big figure
    pcts0 = v.get("percent") or []
    if money and pcts0 and _re.search(r"\bfor\s+[\d.]+\s*(?:%|percent|per cent)\s+of\b", text, _re.I):
        val, suf = _scaled(float(money[0][1]))
        p0 = float(pcts0[0])
        buyer = getattr(c, "airlines", [])
        return "dossier.lay_share", {"title": _title(c, text, "THE STAKE"), "sub": sub, "big": f"{unit_of(money[0][0])}{val:g}{suf}",
                                     "parts": [{"label": f"{buyer[0]['name'] if buyer else 'BUYER'} {p0:g} %", "pct": p0, "side": "a"},
                                               {"label": "", "pct": 100 - p0, "side": "b"}]}
    if len(money) >= 2 and _RANGE_WORDS.search(text) and not v.get("changes"):
        cur = money[0][0]
        vals = sorted(float(m[1]) for m in money[:2])
        unit = {"USD": "$", "EUR": "€", "GBP": "£", "SGD": "S$"}.get(cur, "")
        div, suf = (1e9, " BN") if vals[1] >= 1e9 else ((1e6, " M") if vals[1] >= 1e6 else (1.0, ""))
        return "dossier.lay_range", {"title": _title(c, text, "THE ESTIMATES"), "sub": sub, "lo": round(vals[0] / div, 2),
                                     "hi": round(vals[1] / div, 2), "unit": unit, "suffix": suf}
    pcts = v.get("percent") or []
    if pcts and _SHARE_WORDS.search(text) and 0 < float(pcts[0]) < 100:
        p = float(pcts[0])
        from . import sides as SD
        m = _re.search(r"\b(?:made|built|produced|supplied|owned)\s+(?:in|by)\s+([A-Z][\w\-]*(?:\s+[A-Z][\w\-]*)?)", text)
        who = m.group(1) if m else ""
        sa = SD.side_of(who) or "a"                            # the named side keeps its film colour
        sb = "b" if sa == "a" else "a"
        return "dossier.lay_share", {"title": _title(c, text, "THE SHARE"), "sub": sub,
                                     "parts": [{"label": (m.group(0) if m else ""), "pct": p, "side": sa},
                                               {"label": "", "pct": 100 - p, "side": sb}], "big": f"{p:g} %"}
    if len(money) == 1 and not v.get("changes"):
        lowt = text.lower()
        bad = bool(_re.search(r"\blost\b|\bloss\b|\bdebt\b|\bfell\b|\bdown\b|\bcost\b", lowt))
        m = _re.search(r"([\d.]+)\s*(?:%|percent|per cent)\s+(more|less|higher|lower|up|down)(?:\s+than)?\s+(a year earlier|the year before|last year)?", text, _re.I)
        if m or _re.search(r"\blost\b|\bprofit\b|\brevenue\b|\bcharge\b", lowt):
            val, suf = _scaled(float(money[0][1]))
            delta = f"{'+' if m and m.group(2).lower() in ('more', 'higher', 'up') else '-'}{m.group(1)} % {(m.group(3) or '').strip()}".strip() if m else ""
            lab = next((L for w, L in _LABELS if w in lowt), "LOSS" if "lost" in lowt else "")
            return "dossier.lay_figure", {"title": _title(c, text, lab or "THE FIGURE"), "sub": sub, "value": val, "unit": unit_of(money[0][0]),
                                          "suffix": suf, "label": lab, "bad": bad, "delta": delta, "delta_bad": bad}
    counts = dict((n, x) for x, n in (v.get("counts") or []))
    n_ac = next((counts[w] for w in ("aircraft", "jets", "planes", "airliners", "fighters") if counts.get(w)), 0)
    if n_ac >= 5:
        return "dossier.lay_icons", {"title": _title(c, text, "THE FLEET"), "sub": sub, "count": int(n_ac), "label": "aircraft",
                                     "approx": bool(_re.search(r"\babout\b|\baround\b|\bnearly\b|\balmost\b|\bsome\b", text, _re.I))}
    if len(set(years)) >= 2:
        ys = sorted(set(years))
        from . import sides as SD
        line_side = next((SD.side_of(x["id"]) for x in getattr(c, "airlines", []) if SD.side_of(x["id"])), "")
        return "dossier.lay_markers", {"title": "The dates", "sub": "", "start": ys[0] - 1, "end": ys[-1] + 1,
                                       "markers": [{"year": y, "label": str(y), "side": line_side or ("a" if i % 2 == 0 else "b")}
                                                   for i, y in enumerate(ys)]}
    return None


def from_csv(graphic: str, c: Any, r: Dict[str, Any]) -> Optional[tuple]:
    """A dossier card the CSV asks for by name, filled from the row's `split` column (entries separated by '|', 'label: text'):
       markers  'Nov 2025: three bidders | Apr 2026: IAG out | Oct 2026: Lufthansa chosen'   (years read from each entry)
       options  'Air France-KLM: its only hub in southern Europe | Lufthansa: leading South Atlantic carrier'
       family   'Lufthansa | Swiss | Austrian | ITA Airways | TAP Air Portugal'                (airlines from the catalog)
       quotes   'Reuters: the main attraction of the airline'
       dossier  the line's own card (pick), whatever the rotation says
    Every word is the CSV's (from the script); nothing is invented here."""
    from . import catalog as C
    g = str(graphic or "").strip().lower()
    parts = [x.strip() for x in str((r or {}).get("split") or "").split("|") if x.strip()]
    title = str((r or {}).get("title") or "").strip()
    if g == "dossier":
        return pick(c, r)
    if g == "markers" and parts:
        ms = []
        for i, x in enumerate(parts):
            y = _re.search(r"(19|20)\d\d", x)
            if y:
                ms.append({"year": int(y.group(0)), "label": x, "side": "warn" if i == len(parts) - 1 else ("a" if i % 2 == 0 else "b")})
        if len(ms) >= 2:
            ys = [m["year"] for m in ms]
            return "dossier.lay_markers", {"title": title or "The timeline", "start": min(ys) - 1, "end": max(ys) + 1, "markers": ms}
    if g == "options" and parts:
        opts = []
        for i, x in enumerate(parts[:3]):
            name, _, rest = x.partition(":")
            hit = C.find_airlines(name)
            typ = ""
            opts.append({"title": name.strip(), "sub": rest.strip(), "side": "a" if i == 0 else "b", "type": typ})
        return "dossier.lay_options", {"title": title or "The offers", "options": opts}
    if g == "family" and parts:
        mem = []
        for i, x in enumerate(parts[:4]):
            hit = [m.entry for m in C.find_airlines(x) if m.entry]
            al = hit[0] if hit else {}
            mem.append({"name": al.get("name") or x, "sub": (f"since {al['founded']}" if al.get("founded") else ""),
                        "airline": al.get("id", ""), "side": "a" if i == len(parts[:4]) - 1 else "b"})
        return "dossier.lay_family", {"title": title or "The group", "members": mem}
    if g == "quotes" and parts:
        qs = []
        for i, x in enumerate(parts[:2]):
            who, _, words = x.partition(":")
            qs.append({"text": words.strip() or who.strip(), "who": who.strip() if words else "", "side": "a" if i == 0 else "warn"})
        return "dossier.lay_quotes", {"title": title or "On the record", "quotes": qs}
    return None
