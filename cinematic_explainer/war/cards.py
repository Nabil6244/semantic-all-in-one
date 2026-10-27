"""War Documentary cards. Every card is fn(t, dur, params) -> RGBA (1280x720) or None, a pure function of t and params.

    equipment_card  stat_compare  stat_number  figure_card  institution_card  timeline  split_compare  evidence_card
    status_chip  source_label  shot_headline  flag

Rules built into every card: factual cards carry a status chip (an unknown or missing status is drawn as UNVERIFIED); equipment whose model is
not confirmed shows only its generic class; a missing image or file never raises; content stays inside tokens.SAFE and above the chip stack
(chips and the shot headline live below that line, so they never overlap a card). Type is sized for a phone at 720p: body text is at least
20 px, source lines at least 15 px, key figures 40-220 px.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from PIL import ImageFilter, Image, ImageChops, ImageDraw

from .. import look as L
from . import icons as I
from . import motion as M
from . import tokens as T

W, H = T.W, T.H
CHIP_H = 30
STACK_Y = T.LOWER_ZONE_Y - 18 - CHIP_H                 # top of the first (lowest) chip; chips stack upward from here
CARD_BOTTOM = STACK_Y - (CHIP_H + 6) - 4               # cards end here, above a stack of two chips
_IMG_CACHE: Dict[tuple, Image.Image] = {}


# ------------------------------------------------------------------------------------------------ helpers -------------------------

def _canvas() -> Image.Image:
    return L.blank()


def _finish(img: Image.Image, t: float, dur: float, lift: int = 14) -> Image.Image:
    """Slide up a few pixels while fading in (0.3 s), fade out over the last 0.2 s."""
    k = M.ease_out(t / T.IN_S) if T.IN_S > 0 else 1.0
    dy = int(round(lift * (1 - k)))
    if dy:
        img = ImageChops.offset(img, 0, dy)
    return L.fade(img, M.card_alpha(t, dur))


def _spaced(d, xy, text, f, fill, sp=0.08):
    return L.spaced(d, xy, text, f, fill, sp)


def _sw(d, text, f, sp=0.08) -> float:
    return L.spaced_width(d, text, f, sp)


def _wrap(d, text: str, f, width: int) -> List[str]:
    lines: List[str] = []
    cur = ""
    for w in str(text).split():
        trial = (cur + " " + w).strip()
        if cur and d.textlength(trial, font=f) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _fit(d, text: str, f, width: int, ellipsis: str = "…") -> str:
    text = str(text)
    if d.textlength(text, font=f) <= width:
        return text
    while text and d.textlength(text + ellipsis, font=f) > width:
        text = text[:-1]
    return text.rstrip() + ellipsis


def _panel(d, box, fill=T.PANEL, line=T.PANEL_LINE, r=6):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=line, width=1)


def _load(path, w: int, h: int, cover: bool = True) -> Optional[Image.Image]:
    """RGB image fitted to w x h (cover crop), cached by file identity; None when the file is absent or unreadable."""
    if not path:
        return None
    try:
        p = str(path)
        if not os.path.isfile(p):
            return None
        st = os.stat(p)
        key = (p, st.st_mtime_ns, st.st_size, w, h, cover)
        hit = _IMG_CACHE.get(key)
        if hit is not None:
            return hit
        im = Image.open(p).convert("RGB")
        sc = max(w / im.width, h / im.height) if cover else min(w / im.width, h / im.height)
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
        if cover:
            x0, y0 = (im.width - w) // 2, (im.height - h) // 2
            im = im.crop((x0, y0, x0 + w, y0 + h))
        if len(_IMG_CACHE) > 24:
            _IMG_CACHE.clear()
        _IMG_CACHE[key] = im
        return im
    except Exception:
        return None


def _chip(img: Image.Image, xy: Tuple[int, int], status: str, text: Optional[str] = None, align: str = "left") -> Tuple[int, int, int, int]:
    """Status chip (colour dot + spaced caps, 16 px) drawn at xy; returns its box. `align` right: xy is the top-right corner."""
    d = ImageDraw.Draw(img)
    st = status if status in T.STATUSES else "unverified"
    label = (text or T.STATUS_LABEL[st]).upper()
    f = T.font("bold", 16)
    w = int(_sw(d, label, f, 0.1)) + 46
    x, y = xy
    if align == "right":
        x -= w
    box = (x, y, x + w, y + CHIP_H)
    d.rounded_rectangle(box, radius=4, fill=(10, 12, 16, 238), outline=T.STATUS_COLOUR[st], width=1)
    d.ellipse([x + 11, y + 10, x + 21, y + 20], fill=T.STATUS_COLOUR[st])
    _spaced(d, (x + 32, y + 5), label, f, T.CREAM, 0.1)
    return box


def _placeholder_bg(size: Tuple[int, int]) -> Image.Image:
    w, h = size
    im = Image.new("RGBA", size, (24, 32, 44, 255))
    d = ImageDraw.Draw(im)
    for i in range(0, h, 4):
        shade = 22 + int(14 * i / max(1, h))
        d.line([(0, i), (w, i)], fill=(shade, shade + 8, shade + 20, 255))
    return im


def _source_line(d, x: int, y: int, text: str, width: int, extra: str = "") -> None:
    f = T.font("regular", 16)
    s = f"Source: {text}" if text else "Source: not stated"
    if extra:
        s += f"  ·  {extra}"
    d.text((x, y), _fit(d, s, f, width), font=f, fill=T.CREAM_DIM)


# ------------------------------------------------------------------------------------------------ equipment ----------------------------

def _equipment_specs(p: dict) -> list:
    identified = str(p.get("confidence") or "uncertain").lower() in ("confirmed", "stated")
    return [s for s in (list(p.get("specs") or [])[:4] if identified else []) if isinstance(s, dict)]


def _equipment_layout(p: dict) -> dict:
    """Panel geometry: sized to its content; the picture takes the height that is left (taller when there are fewer spec rows)."""
    n = len(_equipment_specs(p))
    x0, y0, pw = T.MARGIN_X, 44, 450
    fixed = 16 + 12 + 56 + 6 + 30 + ((12 + 34 * n) if n else 0) + 8 + 22 + 14
    ih = max(148, min(300, CARD_BOTTOM - y0 - fixed - 2))
    return {"x0": x0, "y0": y0, "pw": pw, "iw": pw - 32, "ih": ih, "ph": fixed + ih, "ix0": x0 + 16, "iy0": y0 + 16}


def equipment_card(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    img = _canvas()
    d = ImageDraw.Draw(img)
    conf = str(p.get("confidence") or "uncertain").lower()
    identified = conf in ("confirmed", "stated")
    icon_id = I.class_id(p.get("icon"))
    status = T.status_of(p)
    specs = _equipment_specs(p)
    g = _equipment_layout(p)
    x0, y0, pw, iw, ih, ph = g["x0"], g["y0"], g["pw"], g["iw"], g["ih"], g["ph"]
    _panel(d, (x0, y0, x0 + pw, y0 + ph))
    ix0, iy0 = g["ix0"], g["iy0"]
    photo = _load(p.get("image"), iw, ih)
    if photo is not None:
        img.paste(photo, (ix0, iy0))
        fallback = False
    else:
        img.paste(_placeholder_bg((iw, ih)), (ix0, iy0))
        isz = min(ih - 6, iw - 40)
        img.alpha_composite(I.draw_icon(icon_id, isz, T.CREAM_DIM), (ix0 + (iw - isz) // 2, iy0 + (ih - isz) // 2))
        fallback = True
    d = ImageDraw.Draw(img)
    _chip(img, (ix0 + iw - 10, iy0 + 10), status, align="right")
    if fallback:
        _chip(img, (ix0 + 10, iy0 + ih - CHIP_H - 10), "illustrative", "ILLUSTRATIVE SILHOUETTE")
    elif p.get("image_credit"):     # a licensed photograph carries its credit on the picture
        fc = T.font("regular", 14)
        ctext = _fit(d, str(p["image_credit"]), fc, iw - 16)
        d.rectangle([ix0, iy0 + ih - 22, ix0 + int(d.textlength(ctext, font=fc)) + 16, iy0 + ih], fill=(10, 12, 16, 235))
        d.text((ix0 + 8, iy0 + ih - 20), ctext, font=fc, fill=T.CREAM)
    # callouts: fixed screen-space leader lines, only on a real photo of a confirmed or stated identification
    if photo is not None and identified:
        fl = T.font("bold", 16)
        for i, c in enumerate((p.get("callouts") or [])[:3]):
            if not isinstance(c, dict):
                continue
            k = M.draw_fraction(t, T.IN_S + 0.35 + i * 0.3, T.DRAW_S)
            if k <= 0:
                continue
            px = ix0 + int(min(1.0, max(0.0, float(c.get("x", 0.5)))) * iw)
            py = iy0 + int(min(1.0, max(0.0, float(c.get("y", 0.5)))) * ih)
            lx = min(ix0 + iw - 150, max(ix0 + 8, px + 36))
            ly = max(iy0 + 8, min(iy0 + ih - 40, py - 44))
            I.draw_circle_marker(img, (px, py), 8, T.AMBER, 2)
            end = (px + (lx - px) * k, py + (ly + 14 - py) * k)
            d.line([(px, py), end], fill=T.AMBER, width=2)
            la = M.ramp(t, T.IN_S + 0.35 + i * 0.3 + T.DRAW_S, 0.25)
            if la > 0:
                lab = str(c.get("label", "")).upper()
                tw = int(_sw(d, lab, fl, 0.08)) + 16
                tag = L.blank()
                td = ImageDraw.Draw(tag)
                td.rectangle([lx, ly, lx + tw, ly + 28], fill=(10, 12, 16, 232), outline=T.AMBER)
                _spaced(td, (lx + 8, ly + 5), lab, fl, T.CREAM, 0.08)
                img.alpha_composite(L.fade(tag, la))
                d = ImageDraw.Draw(img)
    ny = iy0 + ih + 12
    name = str(p.get("name") or "") if identified else I.CLASS_LABEL[icon_id]
    fn = T.font("display", 46)
    nw = int(min(iw, _sw(d, name.upper(), fn, 0.04) + 32))
    d.rectangle([ix0, ny, ix0 + nw, ny + 56], fill=T.RED)
    _spaced(d, (ix0 + 16, ny + 4), _fit(d, name.upper(), fn, iw - 32), fn, T.CREAM, 0.04)
    role = str(p.get("role") or "") if identified else "MODEL NOT CONFIRMED"
    operator = str(p.get("operator") or "") if identified else ""
    line = " · ".join(s for s in (role, operator) if s)
    fr = T.font("bold", 22)
    d.text((ix0, ny + 62), _fit(d, line, fr, iw), font=fr, fill=T.CREAM_DIM)
    sy = ny + 62 + 30 + 12
    fl, fv = T.font("bold", 18), T.font("bold", 26)
    for i, s in enumerate(specs):
        k = M.ramp(t, T.IN_S + 0.2 + i * T.ROW_S, T.ROW_S)
        if k <= 0:
            continue
        row = L.blank()
        rd = ImageDraw.Draw(row)
        ry = sy + i * 34
        rd.line([(ix0, ry + 32), (ix0 + iw, ry + 32)], fill=(60, 70, 86, 255), width=1)
        _spaced(rd, (ix0, ry + 7), str(s.get("label", "")).upper(), fl, T.GREY, 0.1)
        val = str(s.get("value", ""))
        rd.text((ix0 + iw - rd.textlength(val, font=fv), ry + 2), val, font=fv, fill=T.CREAM)
        img.alpha_composite(L.fade(row, k))
    d = ImageDraw.Draw(img)
    _source_line(d, ix0, y0 + ph - 14 - 22, str(p.get("source") or ""), iw, f"ID: {conf.replace('_', ' ')}")
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ statistics ------------------------

_BAR_COLOUR = {"red": T.RED, "yellow": T.AMBER, "blue": T.BLUE, "cream": T.CREAM}


def _claim_text(p: dict) -> Optional[str]:
    status = T.status_of(p)
    who = str(p.get("claimant") or "").strip()
    if who:
        return ("CLAIMED BY " if status in ("disputed", "unverified") else "REPORTED BY ") + who.upper()
    if status == "disputed":
        return "CLAIMED FIGURES"
    if status == "attributed":
        return "REPORTED FIGURES"
    return None


def _fmt(v) -> str:
    try:
        f = float(v)
        return f"{int(f):,}" if f == int(f) else f"{f:,.1f}"
    except (TypeError, ValueError):
        return str(v)


def stat_compare(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Each item enters as one unit: label, bar track, bar and value together. The bar grows from the zero axis; its value rides at the bar end."""
    items = [i for i in (p.get("items") or []) if isinstance(i, dict)][:6]
    if not items:
        return None
    img = _canvas()
    d = ImageDraw.Draw(img)
    status = T.status_of(p)
    x0 = T.MARGIN_X
    d.text((x0, 50), str(p.get("title", "")).upper(), font=T.font("display", 56), fill=T.CREAM)
    cy = 120
    claim = _claim_text(p)
    box = _chip(img, (x0, cy), status, claim)
    if p.get("as_of"):
        d = ImageDraw.Draw(img)
        d.text((box[2] + 16, cy + 4), f"AS OF {str(p['as_of']).upper()}", font=T.font("bold", 20), fill=T.CREAM_DIM)
    vals = [max(0.0, float(i.get("value") or 0)) for i in items]
    vmax = max(vals) or 1.0
    top, bottom = 172, CARD_BOTTOM
    n = len(items)
    pitch = min(96, (bottom - top) / n)
    bar_h = int(max(28, min(42, pitch - 46)))
    bar_x = x0 + 4
    maxw = 580                                              # the longest bar plus its value fills the left 60 % of the frame
    unit = str(p.get("unit") or "")
    fl, fv = T.font("display", 30), T.font("display", 46)
    for k_i, (it, v) in enumerate(zip(items, vals)):
        y = int(top + k_i * pitch)
        start = T.IN_S + k_i * 0.3
        a = M.ramp(t, start, 0.25)
        if a <= 0:
            continue                                        # nothing of this item before it enters: never a label without its bar
        layer = L.blank()
        ld = ImageDraw.Draw(layer)
        _spaced(ld, (bar_x, y), str(it.get("label", "")).upper(), fl, T.CREAM_DIM, 0.08)
        by = y + 36
        ld.rectangle([bar_x, by, bar_x + maxw, by + bar_h], fill=(34, 42, 54, 255))        # the track, full length, drawn with the label
        ld.line([(bar_x - 2, by - 4), (bar_x - 2, by + bar_h + 4)], fill=T.PANEL_LINE, width=2)   # the zero axis
        k = M.draw_fraction(t, start, 0.8)
        bw = int(maxw * v / vmax * k)
        if bw > 0:
            ld.rectangle([bar_x, by, bar_x + bw, by + bar_h], fill=_BAR_COLOUR.get(str(it.get("colour")), T.CREAM))
        shown = str(it.get("shown") if it.get("shown") is not None else _fmt(it.get("value")))
        txt = shown + (f" {unit}" if unit and not shown.endswith(unit) else "")
        ld.text((bar_x + bw + 14, by + bar_h / 2 - 25), txt, font=fv, fill=T.CREAM)
        img.alpha_composite(L.fade(layer, a))
        d = ImageDraw.Draw(img)
    return _finish(img, t, dur)


def stat_number(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    img = _canvas()
    d = ImageDraw.Draw(img)
    try:
        value = int(p["value"])
    except (KeyError, TypeError, ValueError):
        return None
    status = T.status_of(p)
    col = {"yellow": T.AMBER, "blue": T.BLUE, "cream": T.CREAM}.get(str(p.get("colour")), T.RED)
    prefix, suffix = str(p.get("prefix") or ""), str(p.get("suffix") or "")
    x, y = T.MARGIN_X, int(H * 0.26)
    size = 230
    full = f"{prefix}{value:,}{suffix}"
    while size > 100 and d.textlength(full, font=T.font("display", size)) > 560:
        size -= 10
    fy = T.font("display", size)
    shown = M.count_value(t, 0.15, value)
    if shown:
        d.text((x, y), f"{prefix}{shown:,}{suffix}", font=fy, fill=col)
    wfull = int(d.textlength(full, font=fy))
    la = M.ramp(t, 0.15 + T.COUNT_S, 0.2)
    if la > 0:
        lab = L.blank()
        ld = ImageDraw.Draw(lab)
        fl = T.font("display", 58)
        lx = x + wfull + 34
        lines = _wrap(ld, str(p.get("label", "")).upper(), fl, W - lx - T.MARGIN_X)[:3]
        for i, line in enumerate(lines):
            ld.text((lx, y + 56 + i * 60), line, font=fl, fill=T.CREAM)
        if p.get("sub"):
            ld.text((lx, y + 56 + 60 * len(lines) + 8), _fit(ld, str(p["sub"]), T.font("bold", 24), W - lx - T.MARGIN_X),
                    font=T.font("bold", 24), fill=T.CREAM_DIM)
        img.alpha_composite(L.fade(lab, la))
    ry = y + int(size * 1.0) + 8
    rk = M.draw_fraction(t, 0.15 + T.COUNT_S + 0.1, T.DRAW_S)
    d = ImageDraw.Draw(img)
    d.rectangle([x, ry, x + int(760 * rk), ry + 3], fill=T.RED)
    ca = M.ramp(t, 0.15 + T.COUNT_S + 0.4, 0.3)
    if ca > 0:
        row = L.blank()
        claim = _claim_text(p)
        box = _chip(row, (x, ry + 22), status, claim)
        if p.get("as_of"):
            ImageDraw.Draw(row).text((box[2] + 16, ry + 26), f"AS OF {str(p['as_of']).upper()}", font=T.font("bold", 20), fill=T.CREAM_DIM)
        img.alpha_composite(L.fade(row, ca))
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ people ---------------------------------

def _circle(src: Image.Image, size: int) -> Image.Image:
    face = src.convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(face, (0, 0), mask)
    return out


def figure_card(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    img = _canvas()
    d = ImageDraw.Draw(img)
    status = T.status_of(p) if p.get("status") else "attributed"
    name = str(p.get("name") or "").strip()
    if not name:
        return None
    role = str(p.get("role") or "")
    cx, top = T.MARGIN_X + 150, 70
    portrait = _load(p.get("image"), 260, 260)
    fn, fr = T.font("display", 42), T.font("bold", 20)
    if portrait is not None:
        k = M.ease_out(t / T.IN_S)
        size = int(256 * (0.94 + 0.06 * k))
        ring = Image.new("RGBA", (size + 12, size + 12), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([0, 0, size + 11, size + 11], fill=T.CREAM)
        img.alpha_composite(ring, (cx - size // 2 - 6, top + 134 - size // 2 - 6))
        img.alpha_composite(_circle(portrait, size), (cx - size // 2, top + 134 - size // 2))
        py = top + 134 + size // 2 + 16
        for fs in (42, 38, 34, 30, 27):           # a long name shrinks before it is ever cut
            fn_try = T.font("display", fs) if fs != 42 else fn
            if _sw(d, name.upper(), fn_try, 0.04) + 34 <= 420:
                fn = fn_try
                break
        nw = int(min(420, _sw(d, name.upper(), fn, 0.04) + 34))
        d.rectangle([cx - nw // 2, py, cx + nw // 2, py + 50], fill=T.RED)
        _spaced(d, (cx - nw // 2 + 17, py + 3), _fit(d, name.upper(), fn, nw - 34), fn, T.CREAM, 0.04)
        for i, line in enumerate(_wrap(d, role, fr, 300)[:2]):
            d.text((cx - d.textlength(line, font=fr) / 2, py + 58 + i * 26), line, font=fr, fill=T.CREAM_DIM)
        text_x = T.MARGIN_X + 350
    else:
        # no portrait: a neutral name plate (never a monogram or a stand-in face)
        pw = 340
        py = top + 40
        nlines = _wrap(d, name.upper(), fn, pw - 44)[:3]
        rlines = _wrap(d, role, fr, pw - 44)[:3]
        ph = 24 + len(nlines) * 48 + 14 + len(rlines) * 26 + 20
        _panel(d, (T.MARGIN_X, py, T.MARGIN_X + pw, py + ph))
        d.rectangle([T.MARGIN_X, py, T.MARGIN_X + 6, py + ph], fill=T.BLUE)
        for i, line in enumerate(nlines):
            d.text((T.MARGIN_X + 24, py + 20 + i * 48), line, font=fn, fill=T.CREAM)
        for i, line in enumerate(rlines):
            d.text((T.MARGIN_X + 24, py + 20 + len(nlines) * 48 + 14 + i * 26), line, font=fr, fill=T.CREAM_DIM)
        text_x = T.MARGIN_X + pw + 50
    statement = str(p.get("statement") or "").strip()
    if statement:
        fs = T.font("bold", 34)
        words = list(p.get("words") or statement.split())
        times = list(p.get("times") or [])
        if len(times) < len(words):
            t0, t1 = 0.6, max(1.2, dur - 1.4)
            times = [t0 + (t1 - t0) * i / max(1, len(words)) for i in range(len(words))]
        width = W - text_x - T.MARGIN_X
        d.text((text_x - 4, 100), "“", font=T.font("serif", 100), fill=T.RED)
        lines: List[List[int]] = [[]]
        for i, w in enumerate(words):
            trial = " ".join(words[j] for j in lines[-1] + [i])
            if lines[-1] and d.textlength(trial, font=fs) > width:
                lines.append([i])
            else:
                lines[-1].append(i)
        y = 196
        for line in lines[:5]:
            x = text_x
            for i in line:
                kk = M.ramp(t, times[i], L.WORD_S)
                d.text((x, y), words[i], font=fs, fill=L.lerp_color(T.GREY, T.CREAM, kk))
                x += d.textlength(words[i] + " ", font=fs)
            y += 46
        d.rectangle([text_x, y + 10, text_x + 44, y + 13], fill=T.RED)
        who = " · ".join(s for s in (name.upper(), str(p.get("statement_date") or ""), str(p.get("venue") or "")) if s)
        fa = T.font("bold", 20)
        d.text((text_x, y + 26), _fit(d, who, fa, width), font=fa, fill=T.CREAM_DIM)
        _chip(img, (text_x, 62), status)
        d = ImageDraw.Draw(img)
        _source_line(d, text_x, min(CARD_BOTTOM - 22, y + 62), str(p.get("source") or ""), width)
    else:
        _chip(img, (T.MARGIN_X, 62), status)
    return _finish(img, t, dur)


def institution_card(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    name = str(p.get("name") or "").strip()
    if not name:
        return None
    img = _canvas()
    d = ImageDraw.Draw(img)
    status = T.status_of(p) if p.get("status") else "attributed"
    x0, y0, pw, ph = T.MARGIN_X, 170, 820, 250
    _panel(d, (x0, y0, x0 + pw, y0 + ph))
    d.rectangle([x0, y0, x0 + 6, y0 + ph], fill=T.BLUE)
    emb = _load(p.get("emblem"), 150, 150, cover=False)
    box = (x0 + 34, y0 + 50, x0 + 184, y0 + 200)
    if emb is not None:
        img.paste(emb, (box[0] + (150 - emb.width) // 2, box[1] + (150 - emb.height) // 2))
    else:
        img.alpha_composite(I.draw_icon("institution", 140, T.CREAM_DIM), (box[0] + 5, box[1] + 5))
    d = ImageDraw.Draw(img)
    fn = T.font("display", 54)
    tx = x0 + 216
    nl = _wrap(d, name.upper(), fn, pw - 250)[:2]
    for i, line in enumerate(nl):
        d.text((tx, y0 + 30 + i * 58), line, font=fn, fill=T.CREAM)
    if p.get("subtitle"):
        fs = T.font("bold", 24)
        for i, line in enumerate(_wrap(d, str(p["subtitle"]), fs, pw - 250)[:2]):
            d.text((tx, y0 + 40 + len(nl) * 58 + i * 30), line, font=fs, fill=T.CREAM_DIM)
    _chip(img, (tx, y0 + ph - 48), status)
    d = ImageDraw.Draw(img)
    _source_line(d, x0, y0 + ph + 14, str(p.get("source") or ""), pw)
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ timeline -------------------------------

def _scrim(img: Image.Image, box, alpha: int = 205, radius: int = 22, feather: int = 26) -> None:
    """A soft dark panel behind a card's own text, so the text reads on bright footage while the rest of the scene stays as bright as it was."""
    x0, y0, x1, y1 = [int(v) for v in box]
    pad = feather * 2
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, w - pad, h - pad], radius=radius, fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(feather / 2))
    layer = Image.new("RGBA", (w, h), (8, 12, 20, 255))
    layer.putalpha(mask)
    img.alpha_composite(layer, (max(0, x0 - pad), max(0, y0 - pad)), (max(0, pad - x0), max(0, pad - y0)))


def timeline(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    events = [e for e in (p.get("events") or []) if isinstance(e, dict)][:6]
    if not events:
        return None
    img = _canvas()
    _scrim(img, (T.MARGIN_X - 24, 36, W - T.MARGIN_X + 24, 290 + (232 if p.get("source") else 176)))   # readable on bright footage, nothing else dimmed
    d = ImageDraw.Draw(img)
    n = len(events)
    times = list(p.get("times") or [])
    if len(times) < n:
        times = [0.7 + i * 0.9 for i in range(n)]
    d.text((T.MARGIN_X, 56), str(p.get("title", "")).upper(), font=T.font("display", 56), fill=T.CREAM)
    ly = 290
    bw = 220
    if n > 1:
        step0 = (W - 2 * T.MARGIN_X - bw - 12) / (n - 1)
        bw = int(max(110, min(220, step0 - 16)))
    x0, x1 = T.MARGIN_X + bw // 2 + 6, W - T.MARGIN_X - bw // 2 - 6
    k = M.draw_fraction(t, 0.15, 1.0 + 0.25 * n)
    d.line([(x0, ly), (x0 + (x1 - x0) * k, ly)], fill=T.PANEL_LINE, width=4)
    step = (x1 - x0) / max(1, n - 1) if n > 1 else 0
    fd, fl, fs = T.font("display", 44), T.font("bold", 22), T.font("bold", 16)
    for i, ev in enumerate(events):
        cx = int(x0 + step * i) if n > 1 else (x0 + x1) // 2
        st = str(ev.get("status") or "attributed").lower()
        colour = T.STATUS_COLOUR.get(st, T.GREY)
        pk = M.ramp(t, times[i], 0.25)
        if pk <= 0:
            continue
        r = 11 * M.ease_out(pk)
        layer = L.blank()
        I.draw_circle_marker(layer, (cx, ly), r + 4, colour, 2, fill=T.CHARCOAL)
        if r > 2.5:   # a dot smaller than the ring offset has no inside to draw (PIL rejects an inverted box)
            ImageDraw.Draw(layer).ellipse([cx - r + 2, ly - r + 2, cx + r - 2, ly + r - 2], fill=colour)
        la = M.ramp(t, times[i] + 0.1, T.IN_S)
        text = L.blank()
        td = ImageDraw.Draw(text)
        date = str(ev.get("date", "")).upper()
        td.text((cx - td.textlength(date, font=fd) / 2, ly - 72), date, font=fd, fill=T.AMBER)
        lines = _wrap(td, str(ev.get("label", "")), fl, bw)[:4]
        for j, line in enumerate(lines):
            td.text((cx - td.textlength(line, font=fl) / 2, ly + 28 + j * 28), line, font=fl, fill=T.CREAM)
        if st in ("disputed", "unverified", "illustrative"):
            tag = T.STATUS_LABEL[st]
            td.text((cx - td.textlength(tag, font=fs) / 2, ly + 34 + len(lines) * 28), tag, font=fs, fill=T.STATUS_COLOUR[st])
        img.alpha_composite(layer)
        img.alpha_composite(L.fade(text, la))
    d = ImageDraw.Draw(img)
    if p.get("source"):
        _source_line(d, T.MARGIN_X, ly + 200, str(p["source"]), 760)
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ comparison -------------------------------

def split_compare(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    left, right = p.get("left"), p.get("right")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    img = _canvas()
    status = T.status_of(p)
    pw, ph = 556, 400
    y0 = 70
    xs = (T.MARGIN_X, W - T.MARGIN_X - pw)
    for n, (side, x) in enumerate(zip((left, right), xs)):
        k = M.ease_out(M.ramp(t, 0.1 + n * 0.15, 0.4))
        pane = L.blank()
        pd = ImageDraw.Draw(pane)
        _panel(pd, (x, y0, x + pw, y0 + ph))
        photo = _load(side.get("image"), pw - 24, 270)
        if photo is not None:
            pane.paste(photo, (x + 12, y0 + 12))
        else:
            pane.paste(_placeholder_bg((pw - 24, 270)), (x + 12, y0 + 12))
            pane.alpha_composite(I.draw_icon(I.class_id(side.get("icon")), 210, T.CREAM_DIM), (x + (pw - 210) // 2, y0 + 12 + 30))
            _chip(pane, (x + 22, y0 + 12 + 270 - CHIP_H - 10), "illustrative", "ILLUSTRATIVE SILHOUETTE")
        pd = ImageDraw.Draw(pane)
        ft = T.font("display", 56)
        pd.text((x + 18, y0 + 286), _fit(pd, str(side.get("label", "")).upper(), ft, pw - 36), font=ft, fill=T.CREAM)
        if side.get("sub"):
            fs = T.font("bold", 22)
            pd.text((x + 18, y0 + 352), _fit(pd, str(side["sub"]), fs, pw - 36), font=fs, fill=T.CREAM_DIM)
        shift = int((-1 if n == 0 else 1) * 30 * (1 - k))
        pane = ImageChops.offset(pane, shift, 0)
        img.alpha_composite(L.fade(pane, k))
    d = ImageDraw.Draw(img)
    cy = y0 + ph + 18
    chip = str(p.get("chip") or "").upper()
    if chip:
        f = T.font("bold", 18)
        w = int(_sw(d, chip, f, 0.12)) + 32
        ca = M.ramp(t, 0.6, 0.3)
        c = L.blank()
        cd = ImageDraw.Draw(c)
        cd.rounded_rectangle([(W - w) // 2, cy, (W + w) // 2, cy + CHIP_H], radius=4, fill=T.RED)
        _spaced(cd, ((W - w) // 2 + 16, cy + 4), chip, f, T.CREAM, 0.12)
        img.alpha_composite(L.fade(c, ca))
    _chip(img, (T.MARGIN_X, cy), status)
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ evidence & chips ---------------------

def evidence_card(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Paper source card (words darken as spoken, the highlighter follows) with the war status chip and a kind tag."""
    words = list(p.get("words") or [])
    times = list(p.get("times") or [])
    if not words or len(times) < len(words):
        return None
    img = _canvas()
    d = ImageDraw.Draw(img)
    kind = str(p.get("kind") or "statement").lower()
    status = T.status_of(p) if p.get("status") else ("unverified" if kind == "claim" else "attributed")
    fh, fo, fc = T.font("serif", 38), T.font("serif", 30), T.font("bold", 16)
    cw, pad = 920, 38
    lines: List[List[int]] = [[]]
    for i, w in enumerate(words):
        trial = " ".join(words[j] for j in lines[-1] + [i])
        if lines[-1] and d.textlength(trial, font=fh) > cw - 2 * pad:
            lines.append([i])
        else:
            lines[-1].append(i)
    lines = lines[:6]
    lh = 54
    ch = 82 + lh * len(lines) + 26
    x0, y0 = (W - cw) // 2, max(120, int(H * 0.50) - ch // 2)
    d.rectangle([x0, y0, x0 + cw, y0 + ch], fill=L.PAPER)
    d.rectangle([x0, y0, x0 + cw, y0 + 6], fill=T.RED)
    d.text((x0 + pad, y0 + 22), str(p.get("outlet", "")), font=fo, fill=L.INK)
    date = str(p.get("date", "")).upper()
    dw = int(_sw(d, date, fc, 0.1)) + 22
    d.rectangle([x0 + cw - pad - dw, y0 + 26, x0 + cw - pad, y0 + 54], fill=(28, 28, 32, 255))
    _spaced(d, (x0 + cw - pad - dw + 11, y0 + 31), date, fc, T.CREAM, 0.1)
    mark = p.get("mark")
    y = y0 + 80
    for line in lines:
        x = x0 + pad
        bx0: Optional[int] = None
        bx1 = 0
        for i in line:
            k = L.ramp(t, times[i], L.WORD_S)
            if mark and mark[0] <= i <= mark[1] and k > 0:
                if bx0 is None:
                    bx0 = int(x) - 3
                bx1 = int(x + d.textlength(words[i], font=fh) * k) + 3
            x += d.textlength(words[i] + " ", font=fh)
        if bx0 is not None:
            d.rectangle([bx0, y + 10, bx1, y + lh - 8], fill=(255, 213, 0, 235))
        x = x0 + pad
        for i in line:
            k = L.ramp(t, times[i], L.WORD_S)
            d.text((x, y), words[i], font=fh, fill=L.lerp_color(L.GHOST, L.INK, k))
            x += d.textlength(words[i] + " ", font=fh)
        y += lh
    text = {"claim": "CLAIM · " + T.STATUS_LABEL[status], "report": "REPORT · " + T.STATUS_LABEL[status]}.get(kind)
    _chip(img, (x0, y0 - CHIP_H - 12), status, text)
    return _finish(img, t, dur, lift=16)


def status_chip(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Bottom-left chip(s) above the lower zone. p: status, text (override), chips (optional extra [{status, text}] stacked upward)."""
    img = _canvas()
    chips = [{"status": p.get("status"), "text": p.get("text")}] + [c for c in (p.get("chips") or []) if isinstance(c, dict)]
    y = STACK_Y
    for c in chips[:3]:
        _chip(img, (T.MARGIN_X, y), str(c.get("status") or "unverified").lower(), c.get("text"))
        y -= CHIP_H + 6
    return L.fade(img, min(M.ramp(t, 0.0, 0.2), 1 - M.ramp(t, dur - 0.2, 0.2)))


def source_label(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    text = str(p.get("text") or "").strip()
    if not text:
        return None
    img = _canvas()
    d = ImageDraw.Draw(img)
    f = T.font("regular", 17)
    s = _fit(d, text if text.lower().startswith("source") else f"Source: {text}", f, 620)
    w = int(d.textlength(s, font=f)) + 26
    x1 = W - T.MARGIN_X
    d.rounded_rectangle([x1 - w, STACK_Y, x1, STACK_Y + CHIP_H], radius=4, fill=(10, 12, 16, 226))
    d.text((x1 - w + 13, STACK_Y + 4), s, font=f, fill=T.CREAM_DIM)
    return L.fade(img, min(M.ramp(t, 0.0, 0.2), 1 - M.ramp(t, dur - 0.2, 0.2)))


def shot_headline(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    text = str(p.get("text") or "").strip()
    if not text:
        return None
    img = _canvas()
    d = ImageDraw.Draw(img)
    fh, fd = T.font("display", 38), T.font("bold", 16)
    date = str(p.get("date_line") or "").strip().upper()
    shown = M.typed(text.upper(), t, 0.1, 0.5) or text.upper()[:1]
    full_w = int(_sw(d, text.upper(), fh, 0.04))
    w = min(W - 2 * T.MARGIN_X - 12, max(full_w, int(_sw(d, date, fd, 0.12)) if date else 0) + 48)
    h = 72 if date else 52
    x, y = T.MARGIN_X, T.SAFE[3] - h - 2                  # anchored to the bottom safe margin, below the chip stack
    d.rectangle([x, y, x + w, y + h], fill=(10, 12, 16, 240))
    d.rectangle([x, y, x + 6, y + h], fill=T.AMBER)
    ty = y + 5
    if date:
        _spaced(d, (x + 22, y + 7), _fit(d, date, fd, w - 34), fd, T.AMBER, 0.12)
        ty = y + 26
    _spaced(d, (x + 22, ty), shown, fh, T.CREAM, 0.04)
    return L.fade(img, M.card_alpha(t, dur))


def flag(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Small flag badge top-left with its code; a code that is not a trivial stripe flag gets a neutral plate with the letters only."""
    code = str(p.get("code") or "").strip().upper()
    if not code:
        return None
    img = _canvas()
    d = ImageDraw.Draw(img)
    f = I.draw_flag(code, 84)
    x, y = T.MARGIN_X, T.MARGIN_Y
    if f is not None:
        img.alpha_composite(f, (x, y))
        w, h = f.size
    else:
        w, h = 84, 56
        d.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=(30, 38, 50, 255), outline=T.PANEL_LINE)
        fc = T.font("display", 34)
        d.text((x + (w - d.textlength(code[:3], font=fc)) / 2, y + 8), code[:3], font=fc, fill=T.CREAM)
    if p.get("label"):
        d.text((x + w + 14, y + 8), str(p["label"]).upper(), font=T.font("display", 40), fill=T.CREAM)
    return _finish(img, t, dur, lift=8)


WAR_CARDS = {
    "equipment_card": equipment_card, "stat_compare": stat_compare, "stat_number": stat_number, "figure_card": figure_card,
    "institution_card": institution_card, "timeline": timeline, "split_compare": split_compare, "evidence_card": evidence_card,
    "status_chip": status_chip, "source_label": source_label, "shot_headline": shot_headline, "flag": flag,
}
