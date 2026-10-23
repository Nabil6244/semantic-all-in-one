"""Drawing of the Milestone 1 cue kinds (header, card, icon, chip, arrow) onto a board frame. Anti-aliased sprites are built at 2x or 3x and reduced,
then cached by their parameters, so a frame depends only on the item and the time. Pure Pillow."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import List, Tuple

from PIL import Image, ImageDraw

from . import icons as I
from . import layout as L
from . import theme as T

TH = T.THEME
POP_IN_S = 0.25


def overshoot(k: float) -> float:
    k = max(0.0, min(1.0, k))
    s = 1.5
    return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2


def scale_at(age: float) -> float:
    return 0.4 + 0.6 * overshoot(age / POP_IN_S)


def _text_block(d: ImageDraw.ImageDraw, lines: List[str], px: int, box: Tuple[int, int, int, int], align: str) -> None:
    f = T.font("body", px)
    asc, desc = f.getmetrics()
    lh = asc + desc
    y = box[1] + ((box[3] - box[1]) - lh * len(lines)) / 2
    tr = px * TH.tracking_em
    for ln in lines:
        if align == "center":
            T.draw_tracked(d, ((box[0] + box[2]) / 2, y), ln, f, TH.ink, tr, anchor="m")
        else:
            T.draw_tracked(d, (box[0], y), ln, f, TH.ink, tr)
        y += lh


@lru_cache(maxsize=64)
def card_sprite(w: int, h: int, lines: Tuple[str, ...], px: int, asset: str, role: str) -> Image.Image:
    ss = 2
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=26 * ss, fill=TH.paper, outline=TH.outline, width=TH.outline_px * ss)
    # a thin role-coloured tab along the top edge ties the card to the video's colour language
    d.rounded_rectangle([34 * ss, 0, 34 * ss + 84 * ss, 12 * ss], radius=6 * ss, fill=TH.roles.get(role, TH.roles["blue"]), outline=TH.outline, width=3 * ss)
    sp = big.resize((w, h), Image.LANCZOS)
    d2 = ImageDraw.Draw(sp)
    box = [L.CARD_PAD, 24, w - L.CARD_PAD, h - L.CARD_PAD]
    if asset:
        ic = I.icon_sprite(asset, role, L.CARD_ICON_PX)
        sp.paste(ic, (L.CARD_PAD, (h - L.CARD_ICON_PX) // 2 + 6), ic)
        box[0] += L.CARD_ICON_PX + L.CARD_ICON_GAP
    if lines:
        _text_block(d2, list(lines), px, tuple(box), "center" if not asset else "left")
    return sp


@lru_cache(maxsize=64)
def chip_sprite(text: str, px: int, w: int, h: int) -> Image.Image:
    ss = 3
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=(h * ss) // 2, fill=TH.chip_fill)
    sp = big.resize((w, h), Image.LANCZOS)
    ImageDraw.Draw(sp).text((w / 2, h / 2), text, font=T.font("chip", px), fill=TH.chip_text, anchor="mm")
    return sp


def chip_size(text: str, px: int = TH.chip_px) -> Tuple[int, int]:
    f = T.font("chip", px)
    asc, desc = f.getmetrics()
    return int(f.getlength(text) + px * 1.2), int(asc + desc + px * 0.6)


def paste_scaled(im: Image.Image, sprite: Image.Image, rect: L.Rect, s: float) -> None:
    """Paste `sprite` centred in `rect`, scaled by s (1.0 = its own size)."""
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    if abs(s - 1.0) > 1e-3:
        sw, sh = max(2, int(sprite.width * s)), max(2, int(sprite.height * s))
        sprite = sprite.resize((sw, sh), Image.LANCZOS)
    im.paste(sprite, (int(round(cx - sprite.width / 2)), int(round(cy - sprite.height / 2))), sprite)


def draw_header(im: Image.Image, it, age: float) -> None:
    d = ImageDraw.Draw(im)
    f = T.font("body", it.px)
    tr = it.px * TH.tracking_em
    n = min(len(it.text), int(age * it.cps) + 1)
    shown = T.body_text(TH, it.text)[:n]
    x0, y0 = it.rect[0], it.rect[1]
    T.draw_tracked(d, (x0, y0), shown, f, TH.ink, tr)
    asc, desc = f.getmetrics()
    wid = T.tracked_width(f, shown, tr)
    d.rounded_rectangle([x0, y0 + asc + desc + 4, x0 + max(8, wid), y0 + asc + desc + 11], radius=3, fill=TH.roles.get(it.role, TH.roles["blue"]), outline=TH.outline, width=2)


def draw_card(im: Image.Image, it, age: float) -> None:
    sp = card_sprite(it.rect[2] - it.rect[0], it.rect[3] - it.rect[1], tuple(it.lines), it.px, it.asset, it.role)
    paste_scaled(im, sp, it.rect, scale_at(age))


def draw_icon(im: Image.Image, it, age: float) -> None:
    s = scale_at(age)
    cx = (it.rect[0] + it.rect[2]) // 2
    top = it.rect[1] + 10
    ic = I.icon_sprite(it.asset, it.role, 180)
    if abs(s - 1.0) > 1e-3:
        ic = ic.resize((max(2, int(180 * s)), max(2, int(180 * s))), Image.LANCZOS)
    cy = top + 90
    im.paste(ic, (cx - ic.width // 2, int(cy - ic.height / 2)), ic)
    if it.lines and age >= POP_IN_S:
        d = ImageDraw.Draw(im)
        _text_block(d, it.lines, it.px, (it.rect[0], top + 200, it.rect[2], it.rect[3] - 10), "center")


def draw_chip(im: Image.Image, it, age: float) -> None:
    w, h = it.rect[2] - it.rect[0], it.rect[3] - it.rect[1]
    paste_scaled(im, chip_sprite(it.text, it.px, w, h), it.rect, scale_at(age))


@lru_cache(maxsize=256)
def arrow_sprite(p0: Tuple[float, float], p1: Tuple[float, float], cur_len: int, role: str, width: int = 9) -> Tuple[Image.Image, Tuple[int, int]]:
    """RGBA sprite of the arrow grown to `cur_len` px, and the top-left corner where to paste it."""
    ss = 3
    L0 = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    ux, uy = (p1[0] - p0[0]) / L0, (p1[1] - p0[1]) / L0
    tip = (p0[0] + ux * cur_len, p0[1] + uy * cur_len)
    pad = 40
    x0, y0 = int(min(p0[0], tip[0]) - pad), int(min(p0[1], tip[1]) - pad)
    x1, y1 = int(max(p0[0], tip[0]) + pad), int(max(p0[1], tip[1]) + pad)
    w, h = x1 - x0, y1 - y0
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    col = TH.ink if role == "ink" else TH.roles.get(role, TH.roles["blue"])
    P = lambda p: ((p[0] - x0) * ss, (p[1] - y0) * ss)
    has_head = cur_len >= 30
    hl = L.HEAD_LEN * width / 9
    base = (tip[0] - ux * hl, tip[1] - uy * hl) if has_head else tip
    nx, ny = -uy, ux
    for wd, fill, grow in ((width + 7, TH.outline, 3), (width, col, 0)):
        d.line([P(p0), P(base)], fill=fill, width=int(wd * ss))
        for q in (p0, base):
            r = wd * ss / 2
            cx, cy = P(q)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
        if has_head:
            hw = (20 + grow) * width / 9
            ext = grow * 1.4
            tri = [P((tip[0] + ux * ext, tip[1] + uy * ext)), P((base[0] + nx * hw, base[1] + ny * hw)), P((base[0] - nx * hw, base[1] - ny * hw))]
            d.polygon(tri, fill=fill)
    return big.resize((w, h), Image.LANCZOS), (x0, y0)


def draw_visual(im: Image.Image, it, age: float, frame_no: int = 0) -> None:
    """Reference-style elements (schema v1.3): a typed line, or a sprite that scales in like a card."""
    from . import styles as ST

    if it.style == "line":
        ST.draw_line(im, it, age, frame_no)
        return
    if it.style in ST.CARTOON_STYLES:                                    # schema v1.4: prebuilt art, no drawing here
        sp = ST.cartoon_sprite(it.style, it.vparams or {})
        if it.style == "set":
            im.paste(sp.convert("RGB"), (0, 0))
            return
        from ..narrator.timeline import BOB, BOB_PERIOD
        dy = BOB[(frame_no - it.first_frame) % BOB_PERIOD] if it.style == "figure" else 0       # the same integer bob table as the narrator: deterministic, no rounding ties
        paste_scaled(im, sp, (it.rect[0], it.rect[1] + dy, it.rect[2], it.rect[3] + dy), scale_at(age))
        return
    inner = it.word_boxes[0] if it.word_boxes else (0, 0)
    sp = ST.sprite(it.style, it.text, it.role, it.asset, it.rect[2] - it.rect[0], it.rect[3] - it.rect[1], it.px, tuple(it.lines), tuple(inner))
    paste_scaled(im, sp, it.rect, scale_at(age))


def draw_arrow(im: Image.Image, it, age: float) -> None:
    total = math.hypot(it.end[0] - it.pos[0], it.end[1] - it.pos[1])
    k = min(1.0, max(0.0, age / max(0.05, it.grow_s)))
    ease = 1 - (1 - k) ** 3
    cur = max(6, int(round(total * ease)))
    sp, xy = arrow_sprite((round(it.pos[0], 1), round(it.pos[1], 1)), (round(it.end[0], 1), round(it.end[1], 1)), cur, it.role, it.px or 9)
    im.paste(sp, xy, sp)


CAPTION_HIGHLIGHT_FRAMES = 6


def caption_char_x(it, i: int) -> float:
    f = T.font("body", it.px)
    tr = it.px * TH.tracking_em
    return it.pos[0] + sum(f.getlength(c) for c in it.lines[0][:i]) + tr * i


def draw_caption(im: Image.Image, it, age: float, frame_no: int) -> None:
    """Words mode: word k is drawn from clip frame it.reveal_frames[k]; the newest word is in the role colour for CAPTION_HIGHLIGHT_FRAMES frames.
    Typed mode (rung 3): characters appear at it.cps, like a header."""
    d = ImageDraw.Draw(im)
    f = T.font("body", it.px)
    tr = it.px * TH.tracking_em
    text = it.lines[0]
    y = it.pos[1]
    if it.rung == 3:
        n = min(len(text), int(age * it.cps) + 1)
        T.draw_tracked(d, (it.pos[0], y), text[:n], f, TH.ink, tr)
        return
    words = text.split(" ")
    newest = max([k for k, fr in enumerate(it.reveal_frames) if fr <= frame_no] or [-1])
    off = 0
    for k, w in enumerate(words):
        x = caption_char_x(it, off)
        if it.reveal_frames[k] <= frame_no:
            hot = k == newest and frame_no - it.reveal_frames[k] < CAPTION_HIGHLIGHT_FRAMES
            T.draw_tracked(d, (x, y), w, f, TH.roles.get(it.role, TH.roles["blue"]) if hot else TH.ink, tr)
        off += len(w) + 1
