"""War Documentary composition layouts: full-frame, split, inset and diagram patterns that occupy the frame on purpose.

Every kind is fn(t, dur, params) -> RGBA 1280x720 (a pure function of t and params, same contract as cards.py / cards_kit.py) meant to sit over
dimmed or blurred footage or the atmosphere plate. Shared design language: tokens.py colours, fonts and status chips, motion.py easing, the
kit's chip / stamp elements and the stickers library. 64 px safe margins, condensed caps for names and numbers, one accent per layout.
A missing image or empty list never raises: each portrait / photo has a designed typographic or silhouette alternative that reads as a
deliberate composition (never a blank, never a stand-in face).

Params (* = needed; everything else optional; unknown keys ignored)
  lay_figure_hero    name*, role, image (path), status (default attributed), kicker ("KEY FIGURE"), side (right|left), country,
                     statement, words, times (per-word reveal times, seconds from card start), statement_date, venue, source, credit
                     Sequence: portrait fades in and pushes slowly -> tag -> name wipes -> rule draws -> role -> statement words.
                     No image: typographic hero (large name) beside a labelled dossier panel (COUNTRY / ROLE / STATUS).
  lay_figure_pair    people* = [{name*, role, image, country, credit}] (2), label ("MEETS" / "VS" ...), status, kicker
  lay_equipment_hero name, role, operator, image (path), image_credit, icon (class id), confidence (confirmed|stated|else generic),
                     specs [{label, value}] (up to 4, shown only when confidence is confirmed/stated), status, source
                     Split screen: large photo (or large silhouette + ILLUSTRATIVE SILHOUETTE chip) left, name and spec rows right.
  lay_equipment_compare items* = [equipment dict as above] (2): photos side by side, then aligned spec rows with the label between.
  lay_stat_split     value*, label, sub, prefix, suffix, colour (yellow|red|cream|blue), text (explanation), panel_title,
                     rows [{label, value, shown, colour}] (supporting bars from the zero axis), status, claimant, as_of
  lay_timeline       items* = [{date*, text}] (2-6), title, times (per-node seconds from card start), status
  lay_claim          claim*, claimant, date, highlight (phrase inside claim), status (claimed|unverified|disputed|...), source, note,
                     confirmed [str], claimed [str]
  lay_inset          caption, caption_sub, notes [{title, sub, variant: dark|red|blue|paper}] (up to 4), inset {image, label, credit},
                     side (right|left) for the notes. A lower-third, a note stack and a framed inset over the footage.
  lay_logistics      nodes* = [{label*, sub, icon (sticker name), value, value_label}] (2-4), links [label per arrow], title
                     Generic labels only; always carries an ILLUSTRATIVE DIAGRAM chip.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .. import look as L
from . import cards as C
from . import cards_kit as K
from . import icons as I
from . import motion as M
from . import stickers as S
from . import tokens as T

W, H = T.W, T.H
MX = 64                      # safe margin
PAD = 8                      # transparent padding round every text element (soft shadow)
_D = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
_CACHE: Dict[Any, Any] = {}
_PHOTOS: Dict[Any, Image.Image] = {}


# ------------------------------------------------------------------------------------------------ helpers -------------------------

def _memo(key: Any, build: Callable[[], Any]) -> Any:
    v = _CACHE.get(key)
    if v is None:
        if len(_CACHE) > 260:
            _CACHE.clear()
        v = _CACHE[key] = build()
    return v


def _fid(f) -> Tuple[str, int]:
    return (str(getattr(f, "path", "")), int(getattr(f, "size", 0)))


def _jk(p: dict, *names: str) -> str:
    return json.dumps({n: (p or {}).get(n) for n in names}, sort_keys=True, default=str)


def _canvas() -> Image.Image:
    return L.blank()


def _tw(text: str, f, sp: float = 0.0) -> float:
    return L.spaced_width(_D, text, f, sp) if sp else _D.textlength(text, font=f)


def _draw(d, xy, s: str, f, fill, sp: float = 0.0) -> None:
    if sp:
        L.spaced(d, xy, s, f, fill, sp)
    else:
        d.text(xy, s, font=f, fill=fill)


def _wrap(text: str, f, width: int, sp: float = 0.0, max_lines: int = 3) -> List[str]:
    lines: List[str] = []
    cur = ""
    for w in str(text).split():
        trial = (cur + " " + w).strip()
        if cur and _tw(trial, f, sp) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and _tw(last + "…", f, sp) > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _fit_lines(text: str, kind: str, sizes: Tuple[int, ...], width: int, max_lines: int, sp: float = 0.0):
    """Largest font from `sizes` whose wrapped text fits `max_lines` lines inside `width` (the smallest is used otherwise, truncated)."""
    for s in sizes:
        f = T.font(kind, s)
        lines = _wrap(text, f, width, sp, max_lines + 1)
        if len(lines) <= max_lines and all(_tw(x, f, sp) <= width for x in lines):
            return f, lines
    f = T.font(kind, sizes[-1])
    return f, _wrap(text, f, width, sp, max_lines)


def _text_el(lines: List[str], f, fill, sp: float = 0.0, lh: Optional[int] = None, shadow: bool = True, align: str = "left") -> Image.Image:
    """Lines of text with a soft drop shadow on a padded transparent element (draw at x - PAD, y - PAD). Cached."""
    key = ("t", tuple(lines), _fid(f), tuple(fill), sp, lh, shadow, align)

    def build():
        step = lh or int(f.size * 1.12)
        w = max([int(_tw(s, f, sp)) for s in lines] + [1]) + 2
        h = step * len(lines) + int(f.size * 0.35)
        im = Image.new("RGBA", (w + 2 * PAD, h + 2 * PAD), (0, 0, 0, 0))
        def x_of(s: str) -> float:
            return PAD + ((w - _tw(s, f, sp)) / 2 if align == "center" else 0)

        if shadow:
            sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(sh)
            for i, s in enumerate(lines):
                _draw(sd, (x_of(s) + 1, PAD + 3 + i * step), s, f, (0, 0, 0, 175), sp)
            im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
        d = ImageDraw.Draw(im)
        for i, s in enumerate(lines):
            _draw(d, (x_of(s), PAD + i * step), s, f, fill, sp)
        return im

    return _memo(key, build)


def _wipe_img(im: Image.Image, k: float) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rectangle([0, 0, int(im.width * k), im.height], fill=255)
    out = im.copy()
    out.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
    return out


def _put(canvas: Image.Image, im: Optional[Image.Image], x: float, y: float, a: float = 1.0, dx: float = 0.0, dy: float = 0.0, wipe: float = 1.0) -> None:
    if im is None or a <= 0.0 or wipe <= 0.0:
        return
    if wipe < 1.0:
        im = _wipe_img(im, wipe)
    if a < 1.0:
        im = L.fade(im, a)
    K._blit(canvas, im, int(round(x + dx)), int(round(y + dy)))


def _fade_in(t: float, start: float, length: float = 0.3) -> float:
    return M.ramp(t, start, length)


def _slide(t: float, start: float, dist: float = 22.0, length: float = 0.4) -> float:
    return dist * (1.0 - M.ease_out(M.ramp(t, start, length)))


def _finish(img: Image.Image, t: float, dur: float) -> Image.Image:
    return L.fade(img, min(M.ramp(t, 0.0, 0.15), 1.0 - M.ramp(t, dur - T.OUT_S, T.OUT_S)))


def _photo(path: Any) -> Optional[Image.Image]:
    """RGB photo from disk, cached by file identity; None when absent or unreadable."""
    if not path:
        return None
    try:
        p = str(path)
        if not os.path.isfile(p):
            return None
        st = os.stat(p)
        key = (p, st.st_mtime_ns, st.st_size)
        hit = _PHOTOS.get(key)
        if hit is None:
            if len(_PHOTOS) > 16:
                _PHOTOS.clear()
            hit = _PHOTOS[key] = Image.open(p).convert("RGB")
        return hit
    except Exception:
        return None


def _cover(src: Image.Image, w: int, h: int, zoom: float = 1.0, ax: float = 0.5, ay: float = 0.5) -> Image.Image:
    """src scaled to cover w x h (times `zoom`, a slow push) and cropped with the anchor (ax, ay) kept steady."""
    sc = max(w / src.width, h / src.height) * max(1.0, zoom)
    nw, nh = max(w, int(src.width * sc)), max(h, int(src.height * sc))
    im = src.resize((nw, nh), Image.BICUBIC)
    x0 = int((nw - w) * ax)
    y0 = int((nh - h) * ay)
    return im.crop((x0, y0, x0 + w, y0 + h))


def _grad(w: int, h: int, horizontal: bool, a0: int, a1: int, rgb=(6, 8, 12)) -> Image.Image:
    """Alpha gradient plate: a0 at the left (horizontal) or top edge, a1 at the right or bottom edge."""
    def build():
        g = Image.linear_gradient("L")                       # 0 at the top, 255 at the bottom
        if horizontal:
            g = g.rotate(90, expand=True)                     # 0 at the left, 255 at the right
        g = g.resize((w, h))
        lut = [int(a0 + (a1 - a0) * v / 255.0) for v in range(256)]
        im = Image.new("RGBA", (w, h), rgb + (0,))
        im.putalpha(g.point(lut))
        return im

    return _memo(("grad", w, h, horizontal, a0, a1, rgb), build)


def _glass(w: int, h: int, accent=None, alpha: int = 208) -> Image.Image:
    def build():
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=6, fill=(10, 14, 20, alpha), outline=T.PANEL_LINE, width=1)
        if accent:
            d.rectangle([0, 0, 4, h - 1], fill=accent)
        return K._shadowed(im, 6, (0, 4), 110)

    return _memo(("glass", w, h, accent, alpha), build)


def _chip_el(status: str, text: Optional[str] = None) -> Image.Image:
    def build():
        c = Image.new("RGBA", (560, C.CHIP_H + 2), (0, 0, 0, 0))
        box = C._chip(c, (0, 0), status, text)
        return c.crop((0, 0, box[2] + 1, C.CHIP_H + 1))

    return _memo(("chip", status, text), build)


def _tag_el(text: str, fill=T.RED, ink=T.CREAM, size: int = 17) -> Image.Image:
    def build():
        f = T.font("bold", size)
        w = int(_tw(text.upper(), f, 0.12)) + 24
        im = Image.new("RGBA", (w, size + 14), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, w - 1, size + 13], fill=fill)
        L.spaced(d, (12, 6), text.upper(), f, ink, 0.12)
        return im

    return _memo(("tag", text, fill, ink, size), build)


def _rule(w: int, h: int = 4, colour=T.RED, k: float = 1.0) -> Optional[Image.Image]:
    if k <= 0:
        return None
    im = Image.new("RGBA", (max(1, int(w * min(1.0, k))), h), colour)
    return im


def _count_text(value: Any, t: float, start: float, length: float = 0.75) -> Tuple[str, str]:
    """(shown, final): the number counted up to its final text; unparseable values appear as they are."""
    pre, num, suf, commas, dec = K._parse_value(value)
    if num is None:
        return str(value), str(value)

    def fmt(x: float) -> str:
        s = f"{x:,.{dec}f}" if commas else f"{x:.{dec}f}"
        return f"{pre}{s}{suf}"

    k = M.ease_out(M.ramp(t, start, length))
    final = fmt(num)
    if k >= 1.0:
        return final, final
    cur = num * k
    return fmt(round(cur) if dec == 0 else cur), final


def _initial_state(p: dict) -> dict:
    return p if isinstance(p, dict) else {}


# ------------------------------------------------------------------------------------------------ figures ------------------------

PW = 440                      # hero portrait box (about 61 % of the frame height)


def _feather_mask(w: int, h: int, side: str) -> Image.Image:
    """255 inside, fading to 0 on the edge facing the text (`side`: left|right is the fading edge) and along the bottom."""
    def build():
        fx, fy = max(1, int(w * 0.34)), max(1, int(h * 0.30))
        row = Image.new("L", (w, 1), 255)
        rp = row.load()
        for x in range(w):
            k = min(1.0, (x if side == "left" else w - 1 - x) / fx)
            rp[x, 0] = int(255 * k * k * (3 - 2 * k))
        col = Image.new("L", (1, h), 255)
        cp = col.load()
        for y in range(h):
            k = min(1.0, (h - 1 - y) / fy)
            cp[0, y] = int(255 * k * k * (3 - 2 * k))
        return ImageChops.multiply(row.resize((w, h), Image.NEAREST), col.resize((w, h), Image.NEAREST))

    return _memo(("fmask", w, h, side), build)


def _glow(w: int, h: int, rgb=(64, 112, 170), alpha: int = 70) -> Image.Image:
    def build():
        g = Image.radial_gradient("L").resize((w, h)).point(lambda v: 255 - v)
        im = Image.new("RGBA", (w, h), rgb + (0,))
        im.putalpha(g.point(lambda v: int(v * alpha / 255)))
        return im

    return _memo(("glow", w, h, rgb, alpha), build)


def _portrait_el(src: Image.Image, w: int, h: int, zoom: float, fade_side: str) -> Image.Image:
    im = _cover(src, w, h, zoom, 0.5, 0.0).convert("RGBA")       # portraits are stored top-anchored: the face stays put while it pushes
    im.putalpha(_feather_mask(w, h, fade_side))
    return im


def _stack_height(blocks: List[int]) -> int:
    return sum(blocks)


def _dossier(w: int, h: int, rows: List[Tuple[str, str]], accent) -> Image.Image:
    """A designed information panel used when there is no verified portrait: labelled rows on a hatched navy block. Never a face."""
    def build():
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, w - 1, h - 1], fill=(12, 20, 34, 232))
        for x in range(-h, w, 22):
            d.line([(x, h), (x + h, 0)], fill=(255, 255, 255, 12), width=1)
        d.rectangle([0, 0, 6, h - 1], fill=accent)
        d.rectangle([0, 0, w - 1, h - 1], outline=T.PANEL_LINE, width=1)
        fl = T.font("bold", 17)
        y = 30
        for label, value in rows:
            L.spaced(d, (32, y), label.upper(), fl, T.GREY, 0.14)
            y += 28
            fv, vl = _fit_lines(value.upper(), "display", (44, 38, 32, 28), w - 64, 2, 0.03)
            for ln in vl:
                L.spaced(d, (32, y), ln, fv, T.CREAM, 0.03)
                y += int(fv.size * 1.05)
            d.line([(32, y + 6), (w - 32, y + 6)], fill=(70, 82, 100, 255), width=1)
            y += 26
        return K._shadowed(im, 8, (0, 6), 120)

    return _memo(("dossier", w, h, tuple(rows), accent), build)


def lay_figure_hero(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    name = str(p.get("name") or "").strip()
    if not name:
        return None
    role = str(p.get("role") or "").strip()
    side = "left" if str(p.get("side") or "right").lower() == "left" else "right"
    status = T.status_of(p) if p.get("status") else "attributed"
    src = _photo(p.get("image"))
    statement = str(p.get("statement") or "").strip()
    img = _canvas()
    py = 140
    if side == "right":
        px, tx, tw = W - MX - PW, MX, W - MX - PW - MX - 60
    else:
        px, tx, tw = MX, MX + PW + 60, W - MX - PW - MX - 60
    # a quiet scrim behind the text column keeps it readable on bright footage
    sc_w = tx + tw + 160 if side == "right" else W - tx + 80
    scrim = _grad(sc_w, H, True, 190, 0) if side == "right" else _grad(sc_w, H, True, 0, 190)
    _put(img, scrim, 0 if side == "right" else W - sc_w, 0, _fade_in(t, 0.0, 0.4) * 0.9)
    # portrait (or the dossier panel)
    k_in = M.ease_out(M.ramp(t, 0.0, 0.5))
    if src is not None:
        _put(img, _glow(PW + 360, PW + 260), px - 180, py - 110, k_in)
        zoom = 1.0 + 0.045 * (t / dur if dur > 0 else 1.0)
        el = _portrait_el(src, PW, PW, zoom, "left" if side == "right" else "right")
        _put(img, el, px, py, k_in, dx=(28 if side == "right" else -28) * (1 - k_in))
        if p.get("credit"):
            cf = T.font("regular", 14)
            cl = _text_el([str(p["credit"])[:96]], cf, T.CREAM_DIM, shadow=True)
            _put(img, cl, (px + PW - cl.width + 2 * PAD) if side == "right" else px - PAD, py + PW + 2 - PAD, _fade_in(t, 0.6))
    else:
        rows = [(k, v) for k, v in (("Country", str(p.get("country") or "")), ("Role", role), ("Status", T.STATUS_LABEL[status])) if v]
        dos = _dossier(PW, PW, rows, T.BLUE)
        _put(img, dos, px - 24, py - 24, k_in, dx=(28 if side == "right" else -28) * (1 - k_in))
    # text column: kicker, name, rule, role, statement
    f_name, n_lines = _fit_lines(name.upper(), "display", (112, 98, 86, 76, 66, 58), tw, 2, 0.03)
    n_el = _text_el(n_lines, f_name, T.CREAM, 0.03, int(f_name.size * 0.98))
    role_f = T.font("bold", 26)
    r_lines = _wrap(role, role_f, tw, 0.0, 2) if role else []
    r_el = _text_el(r_lines, role_f, T.CREAM_DIM, 0.0, 34) if r_lines else None
    st_f = T.font("serif_regular", 31)
    words = list(p.get("words") or statement.split()) if statement else []
    lines_idx: List[List[int]] = [[]]
    for i, w in enumerate(words):
        trial = " ".join(words[j] for j in lines_idx[-1] + [i])
        if lines_idx[-1] and _tw(trial, st_f) > tw - 8:
            lines_idx.append([i])
        else:
            lines_idx[-1].append(i)
    lines_idx = lines_idx[:5] if words else []
    st_h = (len(lines_idx) * 44 + 44) if lines_idx else 0
    n_h = len(n_lines) * int(f_name.size * 0.98) + 14
    total = 34 + 14 + n_h + 18 + (len(r_lines) * 34 + 14 if r_lines else 0) + st_h
    y = int(max(92, min(py + PW / 2 - total / 2, H - 100 - total)))
    # kicker + status chip
    kick = str(p.get("kicker") or "").strip()
    a = _fade_in(t, 0.25)
    x = tx
    if kick:
        tg = _tag_el(kick)
        _put(img, tg, x, y, a, dx=_slide(t, 0.25, -18))
        x += tg.width + 10
    _put(img, _chip_el(status), x, y + (0 if not kick else 3), a, dx=_slide(t, 0.25, -18))
    y += 34 + 14
    _put(img, n_el, tx - PAD, y - PAD, 1.0, wipe=M.ease_out(M.ramp(t, 0.35, 0.4)))
    y += n_h
    rule = _rule(min(tw, 220), 4, T.RED, M.draw_fraction(t, 0.7, 0.5))
    _put(img, rule, tx, y - 6)
    y += 18
    if r_el is not None:
        _put(img, r_el, tx - PAD, y - PAD, _fade_in(t, 0.85), dy=_slide(t, 0.85, 10))
        y += len(r_lines) * 34 + 14
    if lines_idx:
        times = list(p.get("times") or [])
        if len(times) < len(words):
            t0, t1 = 1.3, max(1.8, dur - 1.2)
            times = [t0 + (t1 - t0) * i / max(1, len(words)) for i in range(len(words))]
        qa = _fade_in(t, 1.2)
        d = ImageDraw.Draw(img)
        if qa > 0:
            q = _text_el(["“"], T.font("serif", 90), T.RED, shadow=False)
            _put(img, q, tx - PAD - 6, y - 26, qa)
        sy = y + 30
        for line in lines_idx:
            xx = tx + 4
            for i in line:
                kk = M.ramp(t, times[i], L.WORD_S)
                if kk > 0:
                    c = L.lerp_color(T.GREY, T.CREAM, kk)
                    d.text((xx + 1, sy + 2), words[i], font=st_f, fill=(0, 0, 0, int(150 * kk)))
                    d.text((xx, sy), words[i], font=st_f, fill=c[:3] + (int(255 * min(1.0, kk * 2.5)),))
                xx += d.textlength(words[i] + " ", font=st_f)
            sy += 44
        who = " · ".join(s for s in (name.upper(), str(p.get("statement_date") or ""), str(p.get("venue") or "")) if s)
        if who:
            wl = _text_el([_fit_text(who, T.font("bold", 18), tw)], T.font("bold", 18), T.CREAM_DIM, 0.0, 24)
            _put(img, wl, tx - PAD, sy - PAD + 2, _fade_in(t, 1.3))
    return _finish(img, t, dur)


def _fit_text(s: str, f, width: int) -> str:
    s = str(s)
    if _tw(s, f) <= width:
        return s
    while s and _tw(s + "…", f) > width:
        s = s[:-1]
    return s.rstrip() + "…"


def lay_figure_pair(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    people = [q for q in (p.get("people") or []) if isinstance(q, dict) and str(q.get("name") or "").strip()][:2]
    if len(people) < 2:
        return None
    status = T.status_of(p) if p.get("status") else "attributed"
    img = _canvas()
    colw, ph_, gap = 520, 372, 56
    xs = [MX, W - MX - colw]
    py = 100
    _put(img, _grad(W, 330, False, 0, 190), 0, H - 330, _fade_in(t, 0.0, 0.4) * 0.9)
    kick = str(p.get("kicker") or "").strip()
    if kick:
        _put(img, _tag_el(kick), xs[0], 56, _fade_in(t, 0.1))
    for i, q in enumerate(people):
        start = 0.1 + 0.25 * i
        k_in = M.ease_out(M.ramp(t, start, 0.5))
        sx = (-1 if i == 0 else 1) * 26 * (1 - k_in)
        cx = xs[i] + colw // 2
        src = _photo(q.get("image"))
        if src is not None:
            w_ = 400
            zoom = 1.0 + 0.04 * (t / dur if dur > 0 else 1.0)
            _put(img, _glow(w_ + 280, ph_ + 220), cx - (w_ + 280) // 2, py - 90, k_in)
            el = _portrait_el(src, w_, ph_, zoom, "left" if i else "right")
            _put(img, el, cx - w_ // 2, py, k_in, dx=sx)
            if q.get("credit"):
                cl = _text_el([_fit_text(str(q["credit"]), T.font("regular", 13), colw)], T.font("regular", 13), T.CREAM_DIM)
                _put(img, cl, cx - cl.width // 2, py + ph_ + 2 - PAD, _fade_in(t, 0.7))
            ny = py + ph_ + 22
        else:
            rows = [("Country", str(q.get("country") or "Not stated")), ("Role", str(q.get("role") or "Not stated"))]
            _put(img, _dossier(400, ph_ - 30, rows, T.BLUE), cx - 200 - 24, py + 10 - 24, k_in, dx=sx)
            ny = py + ph_ + 22
        f_name, n_lines = _fit_lines(str(q["name"]).upper(), "display", (58, 50, 44, 38), colw - 20, 2, 0.03)
        n_el = _text_el(n_lines, f_name, T.CREAM, 0.03, int(f_name.size * 0.98), True, "center")
        _put(img, n_el, cx - n_el.width // 2, ny - PAD, 1.0, wipe=M.ease_out(M.ramp(t, start + 0.4, 0.35)))
        ry = ny + len(n_lines) * int(f_name.size * 0.98) + 8
        role = str(q.get("role") or "")
        if role:
            rf = T.font("bold", 21)
            rl = _text_el(_wrap(role, rf, colw - 20, 0.0, 2), rf, T.CREAM_DIM, 0.0, 28, True, "center")
            _put(img, rl, cx - rl.width // 2, ry - PAD, _fade_in(t, start + 0.65), dy=_slide(t, start + 0.65, 8))
    label = str(p.get("label") or "").strip()
    if label:
        a = M.ease_out(M.ramp(t, 0.75, 0.3))
        f = T.font("display", 32)
        w = int(_tw(label.upper(), f, 0.08)) + 44
        pill = Image.new("RGBA", (w, 48), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        pd.rounded_rectangle([0, 0, w - 1, 47], radius=24, fill=T.RED)
        L.spaced(pd, (22, 5), label.upper(), f, T.CREAM, 0.08)
        _put(img, K._shadowed(pill, 5, (0, 3), 130), W // 2 - w // 2 - 15, py + ph_ // 2 - 39, a, dy=0)
    _put(img, _chip_el(status), W // 2 - _chip_el(status).width // 2, H - 70, _fade_in(t, 0.9))
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ equipment --------------------------

def _eq_state(p: dict) -> dict:
    conf = str(p.get("confidence") or "uncertain").lower()
    identified = conf in ("confirmed", "stated")
    icon = I.class_id(p.get("icon"))
    name = str(p.get("name") or "").strip() if identified else I.CLASS_LABEL[icon]
    role = str(p.get("role") or "") if identified else "MODEL NOT CONFIRMED"
    specs = [s for s in (list(p.get("specs") or [])[:4] if identified else []) if isinstance(s, dict)]
    return {"conf": conf, "identified": identified, "icon": icon, "name": name or I.CLASS_LABEL[icon], "role": role, "specs": specs,
            "operator": str(p.get("operator") or "") if identified else "", "status": T.status_of(p)}


def _eq_picture(p: dict, st: dict, w: int, h: int, zoom: float) -> Tuple[Image.Image, bool]:
    """(RGBA picture w x h, is_photo). A designed silhouette plate when there is no photo."""
    src = _photo(p.get("image"))
    if src is not None:
        return _cover(src, w, h, zoom, 0.5, 0.5).convert("RGBA"), True

    def build():
        im = C._placeholder_bg((w, h)).convert("RGBA")
        d = ImageDraw.Draw(im)
        for x in range(0, w, 40):
            d.line([(x, 0), (x, h)], fill=(255, 255, 255, 10), width=1)
        for y in range(0, h, 40):
            d.line([(0, y), (w, y)], fill=(255, 255, 255, 10), width=1)
        isz = min(h - 70, w - 80)
        im.alpha_composite(I.draw_icon(st["icon"], isz, T.CREAM_DIM), ((w - isz) // 2, (h - isz) // 2 - 6))
        return im

    return _memo(("eqsil", w, h, st["icon"]), build).copy(), False


def _eq_credit(img: Image.Image, p: dict, x: int, y: int, w: int, a: float) -> None:
    c = str(p.get("image_credit") or "").strip()
    if not c:
        return
    f = T.font("regular", 14)
    el = _text_el([_fit_text(c, f, w - 20)], f, T.CREAM, shadow=False)
    bar = Image.new("RGBA", (w, 28), (10, 12, 16, 235))
    bar.alpha_composite(el, (10 - PAD, 6 - PAD))
    _put(img, bar, x, y, a)


def lay_equipment_hero(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    st = _eq_state(p)
    img = _canvas()
    pw_, ph_ = 704, 408
    px, py = MX, 116
    cx0, cw = px + pw_ + 36, W - MX - (px + pw_ + 36)
    k_in = M.ease_out(M.ramp(t, 0.0, 0.45))
    zoom = 1.0 + 0.05 * (t / dur if dur > 0 else 1.0)
    pic, is_photo = _eq_picture(p, st, pw_, ph_, zoom)
    frame = pic.copy()
    d = ImageDraw.Draw(frame)
    d.rectangle([0, 0, pw_ - 1, ph_ - 1], outline=(236, 230, 214, 120), width=2)
    frame.alpha_composite(_grad(pw_, 120, False, 0, 150), (0, ph_ - 120))
    _put(img, K._shadowed(frame, 8, (0, 6), 130), px - 24, py - 24, k_in, dx=-30 * (1 - k_in))
    _put(img, _chip_el(st["status"]), px + pw_ - _chip_el(st["status"]).width - 12, py + 12, _fade_in(t, 0.4))
    if not is_photo:
        _put(img, _chip_el("illustrative", "ILLUSTRATIVE SILHOUETTE"), px + 12, py + ph_ - C.CHIP_H - 12, _fade_in(t, 0.4))
    else:
        _eq_credit(img, p, px, py + ph_, pw_, _fade_in(t, 0.5))
    # side panel
    rows = list(st["specs"])
    if not rows:                                 # the catalogue lists no figures for this system: show what it does record, never a guessed spec
        rows = [r for r in ({"label": "CLASS", "value": I.CLASS_LABEL[st["icon"]].title()},
                            {"label": "COUNTRY", "value": str(st["operator"] or "")},
                            {"label": "SPECS", "value": "Not listed"}) if r["value"]]
    _put(img, _glass(cw, ph_ + 28, T.RED), cx0 - 18, py - 18, _fade_in(t, 0.15), dx=24 * (1 - M.ease_out(M.ramp(t, 0.15, 0.4))))
    ix = cx0 + 22
    iw = cw - 40
    y = py + 20
    cls = I.CLASS_LABEL[st["icon"]].upper()
    _put(img, _text_el([cls], T.font("bold", 16), T.AMBER, 0.14, shadow=False), ix - PAD, y - PAD, _fade_in(t, 0.3))
    y += 28
    f_name, n_lines = _fit_lines(st["name"].upper(), "display", (66, 58, 50, 44), iw, 2, 0.03)
    n_el = _text_el(n_lines, f_name, T.CREAM, 0.03, int(f_name.size * 0.98))
    _put(img, n_el, ix - PAD, y - PAD, 1.0, wipe=M.ease_out(M.ramp(t, 0.35, 0.35)))
    y += len(n_lines) * int(f_name.size * 0.98) + 8
    _put(img, _rule(80, 4, T.RED, M.draw_fraction(t, 0.65, 0.4)), ix, y)
    y += 16
    rf = T.font("bold", 21)
    line = " · ".join(s for s in (st["role"], st["operator"]) if s)
    r_lines = _wrap(line, rf, iw, 0.0, 3)
    _put(img, _text_el(r_lines, rf, T.CREAM_DIM, 0.0, 28), ix - PAD, y - PAD, _fade_in(t, 0.8), dy=_slide(t, 0.8, 8))
    y += len(r_lines) * 28 + 14
    fl, fv = T.font("bold", 16), T.font("display", 36)
    for i, s in enumerate(rows):
        a = M.ramp(t, 1.0 + i * 0.3, 0.3)
        if a <= 0:
            continue
        row = Image.new("RGBA", (iw, 54), (0, 0, 0, 0))
        rd = ImageDraw.Draw(row)
        lab = str(s.get("label", "")).upper()
        L.spaced(rd, (0, 8), lab, fl, T.GREY, 0.12)
        avail = iw - int(_tw(lab, fl, 0.12)) - 18
        fvv = fv
        for sz in (36, 30, 26, 22):
            fvv = T.font("display", sz)
            if _tw(str(s.get("value", "")), fvv) <= avail:
                break
        val = _fit_text(str(s.get("value", "")), fvv, avail)
        rd.text((iw - rd.textlength(val, font=fvv), 4 if fvv.size >= 36 else 10 - (fvv.size - 22) // 4), val, font=fvv, fill=T.CREAM)
        rd.line([(0, 52), (iw, 52)], fill=(70, 82, 100, 255), width=1)
        _put(img, row, ix, y + i * 54, a, dx=14 * (1 - M.ease_out(a)))
    if p.get("source") or st["identified"]:
        sf = T.font("regular", 14)
        s_txt = f"Source: {p.get('source') or 'not stated'}"
        if _tw(s_txt + f"  ·  ID: {st['conf']}", sf) <= pw_:
            s_txt += f"  ·  ID: {st['conf'].replace('_', ' ')}"
        _put(img, _text_el([_fit_text(s_txt, sf, pw_)], sf, T.CREAM_DIM, shadow=True), px - PAD, py + ph_ + 36 - PAD, _fade_in(t, 0.6))
    return _finish(img, t, dur)


def lay_equipment_compare(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    items = [q for q in (p.get("items") or []) if isinstance(q, dict)][:2]
    if len(items) < 2:
        return None
    states = [_eq_state(q) for q in items]
    img = _canvas()
    cw, ph_, gap = 540, 262, 56
    xs = [MX, W - MX - cw]
    py = 96
    zoom = 1.0 + 0.04 * (t / dur if dur > 0 else 1.0)
    _put(img, _grad(W, 330, False, 0, 150), 0, H - 330, _fade_in(t, 0.0, 0.4) * 0.8)
    for i, (q, st) in enumerate(zip(items, states)):
        k_in = M.ease_out(M.ramp(t, 0.05 + 0.2 * i, 0.45))
        pic, is_photo = _eq_picture(q, st, cw, ph_, zoom)
        ImageDraw.Draw(pic).rectangle([0, 0, cw - 1, ph_ - 1], outline=(236, 230, 214, 110), width=2)
        pic.alpha_composite(_grad(cw, 80, False, 0, 140), (0, ph_ - 80))
        _put(img, K._shadowed(pic, 7, (0, 5), 130), xs[i] - 21, py - 21, k_in, dx=(-1 if i == 0 else 1) * 26 * (1 - k_in))
        if not is_photo:
            _put(img, _chip_el("illustrative", "ILLUSTRATIVE SILHOUETTE"), xs[i] + 10, py + ph_ - C.CHIP_H - 10, _fade_in(t, 0.4))
        else:
            _eq_credit(img, q, xs[i], py + ph_, cw, _fade_in(t, 0.5))
        f_name, n_lines = _fit_lines(st["name"].upper(), "display", (56, 48, 42), cw, 1, 0.03)
        n_el = _text_el(n_lines, f_name, T.CREAM, 0.03)
        _put(img, n_el, xs[i] - PAD, py + ph_ + 40 - PAD, 1.0, wipe=M.ease_out(M.ramp(t, 0.4 + 0.15 * i, 0.35)))
        rf = T.font("bold", 20)
        line = " · ".join(s for s in (st["role"], st["operator"]) if s)
        _put(img, _text_el([_fit_text(line, rf, cw)], rf, T.CREAM_DIM, shadow=True), xs[i] - PAD, py + ph_ + 40 + 56 - PAD, _fade_in(t, 0.7))
    # connector disc between the pictures
    a = M.ease_out(M.ramp(t, 0.5, 0.3))
    disc = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)
    dd.ellipse([0, 0, 71, 71], fill=T.RED, outline=T.CREAM, width=3)
    f = T.font("display", 36)
    dd.text((36 - dd.textlength("VS", font=f) / 2, 14), "VS", font=f, fill=T.CREAM)
    _put(img, K._shadowed(disc, 5, (0, 3), 130), W // 2 - 36 - 15, py + ph_ // 2 - 36 - 15, a)
    # aligned spec rows: values under each side, the label centred between them
    n = max(len(states[0]["specs"]), len(states[1]["specs"]))
    base = py + ph_ + 40 + 56 + 38
    fl, fv = T.font("bold", 16), T.font("display", 40)
    for r in range(min(n, 3)):
        a = M.ramp(t, 1.0 + r * 0.3, 0.3)
        if a <= 0:
            continue
        row = Image.new("RGBA", (W - 2 * MX, 56), (0, 0, 0, 0))
        rd = ImageDraw.Draw(row)
        rd.line([(0, 54), (W - 2 * MX, 54)], fill=(70, 82, 100, 255), width=1)
        label = ""
        for i, st in enumerate(states):
            if r < len(st["specs"]):
                s = st["specs"][r]
                label = label or str(s.get("label", ""))
                fvc = fv
                for sz in (40, 34, 28, 24):
                    fvc = T.font("display", sz)
                    if _tw(str(s.get("value", "")), fvc) <= cw - 150:
                        break
                v = _fit_text(str(s.get("value", "")), fvc, cw - 150)
                cx = (cw // 2) if i == 0 else (W - 2 * MX - cw // 2)
                rd.text((cx - rd.textlength(v, font=fvc) / 2, 6 + (40 - fvc.size) // 3), v, font=fvc, fill=T.CREAM)
        lw = _tw(label.upper(), fl, 0.12)
        rd.rectangle([(W - 2 * MX) / 2 - lw / 2 - 8, 2, (W - 2 * MX) / 2 + lw / 2 + 8, 28], fill=(10, 14, 20, 235))
        L.spaced(rd, ((W - 2 * MX) / 2 - lw / 2, 6), label.upper(), fl, T.GREY, 0.12)
        _put(img, row, MX, base + r * 58, a)
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ statistics -----------------------

_COL = {"yellow": K.YELLOW, "red": (236, 56, 56, 255), "cream": T.CREAM, "blue": (96, 150, 220, 255)}


def lay_stat_split(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    if p.get("value") in (None, ""):
        return None
    status = T.status_of(p) if p.get("status") else "attributed"
    col = _COL.get(str(p.get("colour") or "yellow"), K.YELLOW)
    rows = [r for r in (p.get("rows") or []) if isinstance(r, dict)][:4]
    text = str(p.get("text") or "").strip()
    has_panel = bool(text or rows)
    img = _canvas()
    lw = 640 if has_panel else 900
    _put(img, _grad(lw + 280, H, True, 165, 0), 0, 0, _fade_in(t, 0.0, 0.4) * 0.85)
    shown, final = _count_text(p["value"], t, 0.15)
    size = 250
    while size > 90 and _tw(final, T.font("display", size)) > lw:
        size -= 10
    f = T.font("display", size)
    y = 150 if has_panel else 170
    _put(img, _text_el([shown], f, col, 0.0, int(size * 0.95)), MX - PAD, y - PAD)
    y += int(size * 0.95) + 4
    label = str(p.get("label") or "").strip()
    if label:
        lf, lines = _fit_lines(label.upper(), "display", (60, 52, 46), lw, 2, 0.03)
        _put(img, _text_el(lines, lf, T.CREAM, 0.03, int(lf.size * 1.0)), MX - PAD, y - PAD, _fade_in(t, 0.55), dy=_slide(t, 0.55, 12))
        y += len(lines) * int(lf.size * 1.0) + 4
    if p.get("sub"):
        sf = T.font("bold", 24)
        _put(img, _text_el(_wrap(str(p["sub"]), sf, lw, 0.0, 2), sf, T.CREAM_DIM, 0.0, 32), MX - PAD, y - PAD, _fade_in(t, 0.75))
        y += 40 * min(2, len(_wrap(str(p["sub"]), sf, lw, 0.0, 2)))
    y += 12
    _put(img, _rule(min(lw, 520), 4, col, M.draw_fraction(t, 0.6, 0.5)), MX, y)
    claim = C._claim_text(p)
    a = _fade_in(t, 1.0)
    chip = _chip_el(status, claim)
    _put(img, chip, MX, y + 22, a)
    if p.get("as_of"):
        af = T.font("bold", 19)
        _put(img, _text_el([f"AS OF {str(p['as_of']).upper()}"], af, T.CREAM_DIM, shadow=False), MX + chip.width + 14 - PAD, y + 24 - PAD, a)
    if has_panel:
        px, pw_, py = 720, W - MX - 720, 128
        iw_est = pw_ - 52
        t_lines = len(_wrap(text, T.font("regular", 28), iw_est, 0.0, 6)) if text else 0
        ph_ = 26 + 34 + (t_lines * 38 + 20 if t_lines else 0) + len(rows) * 74 + 22
        k = M.ease_out(M.ramp(t, 0.5, 0.45))
        _put(img, _glass(pw_, ph_, col), px - 18, py - 18, k, dx=26 * (1 - k))
        ix, iw = px + 28, pw_ - 52
        yy = py + 26
        pt = str(p.get("panel_title") or "WHAT IT MEANS").upper()
        _put(img, _text_el([pt], T.font("bold", 16), T.GREY, 0.16, shadow=False), ix - PAD, yy - PAD, _fade_in(t, 0.8))
        yy += 34
        if text:
            tf = T.font("regular", 28)
            tl = _wrap(text, tf, iw, 0.0, 6)
            _put(img, _text_el(tl, tf, T.CREAM, 0.0, 38, False), ix - PAD, yy - PAD, _fade_in(t, 1.0), dy=_slide(t, 1.0, 10))
            yy += len(tl) * 38 + 20
        fl, fv = T.font("bold", 17), T.font("display", 34)
        vals = []
        for r in rows:
            try:
                vals.append(max(0.0, float(r.get("value") or 0)))
            except (TypeError, ValueError):
                vals.append(0.0)
        vmax = max(vals + [1e-9])
        for i, r in enumerate(rows):
            st0 = 1.3 + i * 0.3
            a2 = M.ramp(t, st0, 0.25)
            if a2 <= 0:
                continue
            lay = Image.new("RGBA", (iw, 68), (0, 0, 0, 0))
            ld = ImageDraw.Draw(lay)
            L.spaced(ld, (0, 0), str(r.get("label", "")).upper(), fl, T.CREAM_DIM, 0.1)
            ld.rectangle([0, 28, iw - 150, 52], fill=(34, 42, 54, 255))
            bw = int((iw - 150) * vals[i] / vmax * M.draw_fraction(t, st0, 0.7))
            if bw > 0:
                ld.rectangle([0, 28, bw, 52], fill=_COL.get(str(r.get("colour") or ""), col))
            sv = str(r.get("shown") if r.get("shown") is not None else C._fmt(r.get("value")))
            ld.text((iw - fv.getlength(sv), 20), sv, font=fv, fill=T.CREAM)
            _put(img, lay, ix, yy + i * 74, a2)
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ timeline ------------------------

def lay_timeline(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    items = [q for q in (p.get("items") or []) if isinstance(q, dict) and str(q.get("date") or "").strip()][:6]
    if len(items) < 2:
        return None
    n = len(items)
    status = T.status_of(p) if p.get("status") else "confirmed"
    img = _canvas()
    band = _memo(("tlband", 0), lambda: _band(W, 520))
    _put(img, band, 0, 130, _fade_in(t, 0.0, 0.4))
    title = str(p.get("title") or "").strip()
    if title:
        tf, tl = _fit_lines(title.upper(), "display", (60, 52, 44), W - 2 * MX - 200, 1, 0.03)
        _put(img, _text_el(tl, tf, T.CREAM, 0.03), MX - PAD, 74 - PAD, _fade_in(t, 0.1), dy=_slide(t, 0.1, 12))
    _put(img, _chip_el(status), W - MX - _chip_el(status).width, 84, _fade_in(t, 0.2))
    x0, x1 = 120, W - 120
    step = (x1 - x0) / (n - 1)
    ly = 392
    times = list(p.get("times") or [])
    if len(times) < n:
        span = max(1.0, dur - 1.6)
        times = [0.5 + span * i / max(1, n) for i in range(n)]
    d = ImageDraw.Draw(img)
    # the line draws to the latest node reached
    done = 0.0
    for i in range(n):
        a = M.ramp(t, times[i], 0.5)
        if a > 0:
            done = i + a
    xe = x0 + step * min(n - 1, done)
    d.line([(x0, ly), (x1, ly)], fill=(70, 82, 100, 150), width=3)
    d.line([(x0, ly), (xe, ly)], fill=T.RED, width=5)
    for i, it in enumerate(items):
        cx = x0 + step * i
        a = M.ease_out(M.ramp(t, times[i], 0.4))
        if a <= 0:
            continue
        r = 15 * (0.4 + 0.6 * a)
        d.ellipse([cx - r - 5, ly - r - 5, cx + r + 5, ly + r + 5], fill=(10, 14, 20, 255))
        d.ellipse([cx - r, ly - r, cx + r, ly + r], fill=T.RED, outline=T.CREAM, width=3)
        if i == max(0, int(done - 1e-6)) and t < dur - 0.4:
            sc, al = M.pulse(t, 1.4)
            rr = r * sc + 6
            d.ellipse([cx - rr, ly - rr, cx + rr, ly + rr], outline=T.RED[:3] + (int(150 * al),), width=2)
        colw = int(min(250, step - 24)) if n > 1 else 300
        df, dl = _fit_lines(str(it["date"]).upper(), "display", (104, 92, 80, 68, 56, 46), colw, 1, 0.02)
        del_ = _text_el(dl, df, K.YELLOW, 0.02)
        _put(img, del_, min(max(cx - del_.width // 2, MX - PAD), W - MX + PAD - del_.width), ly - 28 - int(df.size * 0.95) - PAD, a, dy=-12 * (1 - a))
        cap = str(it.get("text") or "").strip()
        if cap:
            cf = T.font("bold", 26)
            cl = _text_el(_wrap(cap, cf, colw, 0.0, 4), cf, T.CREAM, 0.0, 34, True, "center")
            _put(img, cl, min(max(cx - cl.width // 2, MX - PAD), W - MX + PAD - cl.width), ly + 38 - PAD, M.ramp(t, times[i] + 0.15, 0.3), dy=10 * (1 - a))
    return _finish(img, t, dur)


def _band(w: int, h: int) -> Image.Image:
    """A soft horizontal darkening band (transparent at its top and bottom edges) that carries a full-width diagram on bright footage."""
    col = Image.new("L", (1, h), 0)
    cp = col.load()
    for y in range(h):
        k = min(1.0, (1.0 - abs((y - h / 2) / (h / 2))) * 2.2)
        cp[0, y] = int(125 * k * k * (3 - 2 * k))
    im = Image.new("RGBA", (w, h), (6, 8, 12, 0))
    im.putalpha(col.resize((w, h), Image.NEAREST))
    return im


# ------------------------------------------------------------------------------------------------ claims -------------------------

_PAPER = (244, 239, 228, 255)
_INK = (22, 22, 26, 255)
_HL = (255, 214, 10, 255)


def lay_claim(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    claim = str(p.get("claim") or "").strip()
    if not claim:
        return None
    status = str(p.get("status") or "claimed").lower()
    status = status if status in ("claimed", "unverified", "disputed", "illustrative") else "claimed"
    img = _canvas()
    cx0, cw = MX, 616
    cf = T.font("serif", 36)
    lines = _wrap(claim, cf, cw - 72, 0.0, 6)
    head_h = 62
    ch = head_h + 36 + len(lines) * 50 + 40 + (46 if p.get("source") else 0)
    cy = max(96, int((H - ch) / 2) - 10)
    # paper card with a highlighter under the key phrase
    def build_card():
        im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, cw - 1, ch - 1], fill=_PAPER)
        d.rectangle([0, 0, cw - 1, 6], fill=T.RED)
        who = str(p.get("claimant") or "Claim").upper()
        hf = T.font("bold", 21)
        L.spaced(d, (36, 24), _fit_text(who, hf, cw - 220), hf, _INK, 0.06)
        if p.get("date"):
            df = T.font("bold", 16)
            dt = str(p["date"]).upper()
            w = int(_tw(dt, df, 0.1)) + 20
            d.rectangle([cw - 36 - w, 22, cw - 36, 46], fill=_INK)
            L.spaced(d, (cw - 36 - w + 10, 26), dt, df, _PAPER, 0.1)
        d.line([(36, head_h), (cw - 36, head_h)], fill=(190, 182, 166, 255), width=1)
        return K._shadowed(im, 10, (0, 8), 120)

    card = _memo(("claimcard", cw, ch, _jk(p, "claimant", "date")), build_card)
    k_in = M.ease_out(M.ramp(t, 0.0, 0.45))
    _put(img, card, cx0 - 30, cy - 30, k_in, dy=18 * (1 - k_in))
    # claim text with the highlighter sweep
    hl = str(p.get("highlight") or "").strip().lower()
    d = ImageDraw.Draw(img)
    y = cy + head_h + 28
    words_all = claim.split()
    hl_words = hl.split()
    hit: set = set()
    if hl_words:
        low = [w.strip(".,;:!?\"'“”").lower() for w in words_all]
        for i in range(len(low) - len(hl_words) + 1):
            if low[i:i + len(hl_words)] == [w.strip(".,;:!?\"'“”") for w in hl_words]:
                hit.update(range(i, i + len(hl_words)))
                break
    sweep = M.ease_out(M.ramp(t, 0.8, 0.7))
    a_txt = _fade_in(t, 0.25)
    wi = 0
    tx_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(tx_layer)
    boxes: List[Tuple[float, float, float, float]] = []
    for line in lines:
        x = cx0 + 36
        for w in line.split():
            ww = td.textlength(w, font=cf)
            if wi in hit:
                boxes.append((x - 4, y + 6, x + ww + 4, y + 44))
            td.text((x, y), w, font=cf, fill=_INK)
            x += td.textlength(w + " ", font=cf)
            wi += 1
        y += 50
    if boxes:                                   # one continuous sweep across the highlighted words, in reading order
        total = sum(b[2] - b[0] for b in boxes)
        run = total * sweep
        hl_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hd = ImageDraw.Draw(hl_layer)
        for b in boxes:
            wdt = b[2] - b[0]
            use = min(wdt, max(0.0, run))
            run -= wdt
            if use > 0:
                hd.rectangle([b[0], b[1], b[0] + use, b[3]], fill=_HL)
        img.alpha_composite(L.fade(hl_layer, a_txt))
    img.alpha_composite(L.fade(tx_layer, a_txt))
    if p.get("source"):
        sf = T.font("regular", 17)
        d = ImageDraw.Draw(img)
        d.text((cx0 + 36, cy + ch - 48), _fit_text(f"Source: {p['source']}", sf, cw - 72), font=sf, fill=(78, 74, 66, 255))
    # right column: stamp, then confirmed / claimed
    rx = cx0 + cw + 64
    rw = W - MX - rx
    stamp = K._stamp_element(K._STAMP_TXT[status], str(p.get("note") or ""), K._STAMP_COL[status], 50)
    stamp = K._rotated_cache("lclaimstamp" + status + str(p.get("note")), stamp, -5.0)
    ks = K._ease_back(M.clamp01((t - 1.0) / 0.26)) if t > 1.0 else 0.0
    if ks > 0:
        sc = 1.0 + 0.6 * (1.0 - ks)
        K._place(img, K._shadowed(stamp, 5, (0, 3), 120), rx + rw / 2, cy + 50, 0.0, sc, M.ramp(t, 1.0, 0.1))
    conf = [str(x) for x in (p.get("confirmed") or []) if str(x).strip()][:3]
    clm = [str(x) for x in (p.get("claimed") or []) if str(x).strip()][:3]
    yy = cy + 130
    for title, items, icon, colr, st0 in (("WHAT IS CONFIRMED", conf, "check", (84, 150, 112, 255), 1.5), ("WHAT IS CLAIMED", clm, "question", T.AMBER, 2.0)):
        if not items:
            continue
        bf = T.font("regular", 22)
        wrapped = [_wrap(s, bf, rw - 96, 0.0, 2) for s in items]
        hh = 58 + sum(len(wl) * 28 + 12 for wl in wrapped) + 14
        a = M.ramp(t, st0, 0.35)
        if a > 0:
            panel = _glass(rw, hh, colr).copy()
            pd = ImageDraw.Draw(panel)
            ox, oy = 12, 12                                            # _glass pads by its shadow blur * 3
            pad = 18
            panel.alpha_composite(S.draw_sticker(icon, 34, colr, colr), (pad + 18, pad + 12))
            L.spaced(pd, (pad + 62, pad + 18), title, T.font("bold", 17), colr, 0.12)
            ty = pad + 52
            for wl in wrapped:
                for ln in wl:
                    pd.text((pad + 24, ty), ln, font=bf, fill=T.CREAM)
                    ty += 28
                ty += 12
            _put(img, panel, rx - pad, yy - pad, a, dx=18 * (1 - M.ease_out(a)))
        yy += hh + 22
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ inset -------------------------

def lay_inset(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    caption = str(p.get("caption") or "").strip()
    notes = [n for n in (p.get("notes") or []) if isinstance(n, dict) and str(n.get("title") or "").strip()][:4]
    inset = p.get("inset") if isinstance(p.get("inset"), dict) else None
    if not (caption or notes or inset):
        return None
    side = "left" if str(p.get("side") or "right").lower() == "left" else "right"
    img = _canvas()
    _put(img, _grad(W, 230, False, 0, 175), 0, H - 230, _fade_in(t, 0.0, 0.4))           # lower scrim carries the caption on any footage
    if caption:
        f, lines = _fit_lines(caption.upper(), "display", (54, 48, 42, 38), 820, 2, 0.03)
        sub = str(p.get("caption_sub") or "").strip()
        lh = int(f.size * 1.0)
        bh = 22 + len(lines) * lh + (34 if sub else 0) + 8
        shown = M.ramp(t, 0.15, 0.5)
        if shown > 0:
            by = H - 64 - bh
            box_w = int(max(_tw(s, f, 0.03) for s in lines)) + 60
            if sub:
                box_w = max(box_w, int(_tw(sub, T.font("bold", 20))) + 60)
            box = Image.new("RGBA", (box_w, bh), (0, 0, 0, 0))
            bd = ImageDraw.Draw(box)
            bd.rectangle([0, 0, box_w - 1, bh - 1], fill=(10, 12, 16, 236))
            bd.rectangle([0, 0, 9, bh - 1], fill=K.YELLOW)
            for i, s in enumerate(lines):
                L.spaced(bd, (32, 12 + i * lh), s, f, T.CREAM, 0.03)
            if sub:
                bd.text((32, 14 + len(lines) * lh), sub, font=T.font("bold", 20), fill=T.CREAM_DIM)
            _put(img, K._shadowed(box, 6, (0, 4), 120), MX - 18, by - 18, 1.0, wipe=shown)
    if notes:
        nx = W - MX - 304 if side == "right" else MX
        y = 92
        for i, n in enumerate(notes):
            el = K._chip_element(str(n["title"]), str(n.get("sub") or ""), str(n.get("variant") or "dark"), 304)
            a = M.ease_out(M.ramp(t, 0.5 + i * 0.35, 0.4))
            _put(img, el, nx - 15, y - 15, a, dx=(40 if side == "right" else -40) * (1 - a))
            y += el.height - 30 + 12
    if inset:
        src = _photo(inset.get("image"))
        iw_, ih_ = 300, 200
        ix = MX if side == "right" else W - MX - iw_
        iy = 92
        a = M.ease_out(M.ramp(t, 0.35, 0.45))
        fr = Image.new("RGBA", (iw_ + 12, ih_ + 12 + (30 if inset.get("label") else 0)), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fr)
        fd.rectangle([0, 0, fr.width - 1, fr.height - 1], fill=T.CREAM)
        if src is not None:
            fr.alpha_composite(_cover(src, iw_, ih_, 1.0 + 0.04 * (t / dur if dur > 0 else 1), 0.5, 0.2).convert("RGBA"), (6, 6))
        else:
            fr.alpha_composite(C._placeholder_bg((iw_, ih_)).convert("RGBA"), (6, 6))
        if inset.get("label"):
            fd.text((10, ih_ + 14), _fit_text(str(inset["label"]).upper(), T.font("bold", 16), iw_ - 8), font=T.font("bold", 16), fill=_INK)
        el = K._shadowed(fr, 7, (0, 5), 130)
        _put(img, el, ix - 21, iy - 21, a, dy=14 * (1 - a))
        if inset.get("credit"):
            cf = T.font("regular", 13)
            cl = _text_el([_fit_text(str(inset["credit"]), cf, iw_ + 12)], cf, T.CREAM_DIM)
            _put(img, cl, ix - PAD, iy + fr.height + 4 - PAD, _fade_in(t, 0.7))
    return _finish(img, t, dur)


# ------------------------------------------------------------------------------------------------ logistics ----------------------

def lay_logistics(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = _initial_state(p)
    nodes = [n for n in (p.get("nodes") or []) if isinstance(n, dict) and str(n.get("label") or "").strip()][:4]
    if len(nodes) < 2:
        return None
    n = len(nodes)
    img = _canvas()
    _put(img, _memo(("tlband", 1), lambda: _band(W, 520)), 0, 130, _fade_in(t, 0.0, 0.4))
    title = str(p.get("title") or "").strip()
    if title:
        tf, tl = _fit_lines(title.upper(), "display", (58, 50, 44), W - 2 * MX, 1, 0.03)
        _put(img, _text_el(tl, tf, T.CREAM, 0.03), MX - PAD, 74 - PAD, _fade_in(t, 0.1), dy=_slide(t, 0.1, 12))
    gap = 92
    nw = int(min(270, (W - 2 * MX - (n - 1) * gap) / n))
    total = n * nw + (n - 1) * gap
    x0 = (W - total) // 2
    nh = 296
    ny = 196
    links = list(p.get("links") or [])
    d = ImageDraw.Draw(img)
    for i, nd in enumerate(nodes):
        st = 0.25 + 0.55 * i
        a = M.ease_out(M.ramp(t, st, 0.4))
        nx = x0 + i * (nw + gap)
        if a > 0:
            panel = _glass(nw, nh, T.AMBER).copy()
            pd = ImageDraw.Draw(panel)
            pad = 18
            icon = S.draw_sticker(str(nd.get("icon") or "question"), 104, T.CREAM, T.AMBER)
            panel.alpha_composite(icon, (pad + (nw - 104) // 2, pad + 22))
            lf, ll = _fit_lines(str(nd["label"]).upper(), "display", (40, 34, 30), nw - 28, 2, 0.03)
            yy = pad + 22 + 104 + 14
            for ln in ll:
                L.spaced(pd, (pad + (nw - _tw(ln, lf, 0.03)) / 2, yy), ln, lf, T.CREAM, 0.03)
                yy += int(lf.size * 1.0)
            if nd.get("sub"):
                sf = T.font("regular", 17)
                for ln in _wrap(str(nd["sub"]), sf, nw - 28, 0.0, 2):
                    pd.text((pad + (nw - pd.textlength(ln, font=sf)) / 2, yy + 4), ln, font=sf, fill=T.CREAM_DIM)
                    yy += 22
            _put(img, panel, nx - pad, ny - pad, a, dy=16 * (1 - a))
            if nd.get("value") not in (None, ""):
                vs, vf = _count_text(nd["value"], t, st + 0.4, 0.6)
                vfnt = T.font("display", 64)
                vel = _text_el([vs], vfnt, K.YELLOW, 0.0, 64)
                _put(img, vel, nx + nw // 2 - (vel.width - 2 * PAD) // 2 - PAD, ny + nh + 14 - PAD, M.ramp(t, st + 0.35, 0.3))
                if nd.get("value_label"):
                    vl = _text_el([_fit_text(str(nd["value_label"]).upper(), T.font("bold", 17), nw + gap - 10)], T.font("bold", 17), T.CREAM_DIM, 0.1, shadow=False)
                    _put(img, vl, nx + nw // 2 - (vl.width - 2 * PAD) // 2 - PAD, ny + nh + 84 - PAD, M.ramp(t, st + 0.5, 0.3))
        if i < n - 1:
            k = M.draw_fraction(t, st + 0.45, 0.45)
            ax0, ax1, ay = nx + nw + 14, nx + nw + gap - 14, ny + nh // 2 - 10
            if k > 0:
                xe = ax0 + (ax1 - ax0) * k
                d = ImageDraw.Draw(img)
                d.line([(ax0, ay), (xe, ay)], fill=T.AMBER, width=5)
                if k > 0.85:
                    d.polygon([(ax1, ay), (ax1 - 18, ay - 12), (ax1 - 18, ay + 12)], fill=T.AMBER)
                if i < len(links) and str(links[i]).strip():
                    lf2 = T.font("bold", 15)
                    ll = _text_el(_wrap(str(links[i]).upper(), lf2, gap + 40, 0.1, 2), lf2, T.CREAM_DIM, 0.1, 20, shadow=True)
                    _put(img, ll, (ax0 + ax1) / 2 - (ll.width - 2 * PAD) / 2 - PAD, ay - 14 - ll.height + 2 * PAD, M.ramp(t, st + 0.7, 0.3))
    _put(img, _chip_el("illustrative", "ILLUSTRATIVE DIAGRAM"), MX, H - 74, _fade_in(t, 0.6))
    return _finish(img, t, dur)


LAYOUT_CARDS: Dict[str, Callable] = {
    "lay_figure_hero": lay_figure_hero, "lay_figure_pair": lay_figure_pair, "lay_equipment_hero": lay_equipment_hero,
    "lay_equipment_compare": lay_equipment_compare, "lay_stat_split": lay_stat_split, "lay_timeline": lay_timeline,
    "lay_claim": lay_claim, "lay_inset": lay_inset, "lay_logistics": lay_logistics,
}
