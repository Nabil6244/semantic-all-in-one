"""Speech bubbles and stage spotlights (visual styles `bubble` and `spot`; opt-in through explainer/director/compose_dialogue.py). Same pattern as stamp/plate in sprites.py: `measure_*`
gives the box the layout reserves, `draw` paints it for the age since its cue frame. Everything is a pure function of (item, age) on the 30 fps grid; tables are fixed decimals, nothing is random.

bubble: the quote in a rounded white bubble (outline in ink, text in ink, the role colour only in the outline and a small tick), one or two lines, with a tail on the bottom edge pointing at the
speaker. The cue's rect includes the tail, so the layout's own collision check keeps the bubble off every figure. params: tx (tail root, px from the rect's left), lean (tail tip offset in px,
negative = leans left), shout (spiky burst body for a one-word cry), pv (entrance variant 0 pop, 1 bounce, 2 rise; always written by the director so the layout keeps the params).
spot: a soft cone of light from the top of the stage down onto a figure, blended on top (screen) with a pool of light on the floor; params w, h (the rect), power (0.3 to 1.0)."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..board import layout as LY
from ..board import theme as T
from . import presets as P

TH = T.THEME
VERSION = 1                       # carried in the cue's params by the director: a change to a table here changes that clip's cache key only
TAIL_H = 46
TAIL_W = 40
PAD_X, PAD_Y = 34, 20
BUBBLE_MAX_W = 700
BUBBLE_PX = (52, 46, 40, 36, 32)
SHOUT_PX = (84, 72, 60, 48)
SHOUT_PAD_X, SHOUT_PAD_Y = 52, 34
SPOT_W, SPOT_H = 560, 880
LIGHT = (255, 238, 196)

# (scale, alpha, dy) per frame; scaling is about the tail tip, so the bubble grows out of the speaker. The last row is the settled bubble.
POP = (
    ((0.45, 0.30, 0), (0.78, 0.70, 0), (1.12, 1.00, 0), (1.07, 1.00, 0), (0.97, 1.00, 0), (1.02, 1.00, 0), (1.00, 1.00, 0)),
    ((0.20, 0.30, 0), (0.60, 0.75, 0), (1.22, 1.00, 0), (1.10, 1.00, 0), (0.94, 1.00, 0), (1.03, 1.00, 0), (1.00, 1.00, 0)),
    ((1.00, 0.20, 26), (1.00, 0.55, 14), (1.00, 0.90, 6), (1.00, 1.00, 2), (1.00, 1.00, 0), (1.00, 1.00, 0), (1.00, 1.00, 0)),
)
POP_FRAMES = len(POP[0])
VARIANTS = len(POP)
SPOT_FADE_FRAMES = 9
BREATH = (0, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1)       # a slow integer triangle (period 12 frames) for the light's breathing


def pop_frame(age: float, variant: int = 0) -> Tuple[float, float, int]:
    """(scale, alpha, dy) of the bubble at `age`: pure table lookup."""
    return POP[variant % VARIANTS][min(P.frame_of(age), POP_FRAMES - 1)]


def spot_power(age: float, power: float = 0.8) -> float:
    f = P.frame_of(age)
    ramp = min(1.0, (f + 1) / SPOT_FADE_FRAMES)
    return round(power * ramp * (0.93 + 0.07 * BREATH[f % len(BREATH)] / 6.0), 3)


# ---------------------------------------------------------------- measure
def _fit(text: str, sizes, max_w: int, max_lines: int, pad_x: int):
    words = " ".join(str(text).split()).split(" ")
    if not words or not words[0]:
        return None
    for px in sizes:
        f = T.font("body", px)
        tr = px * TH.tracking_em
        lines = LY.wrap(words, f, max_w - 2 * pad_x, tr)
        if len(lines) <= max_lines and all(T.tracked_width(f, ln, tr) <= max_w - 2 * pad_x for ln in lines):
            if len(lines) == 2:                                  # balance the two lines: the narrowest width that still wraps into two (no one-word second line)
                lo, hi = 60, int(max_w - 2 * pad_x)
                while hi - lo > 6:
                    mid = (lo + hi) // 2
                    if len(LY.wrap(words, f, mid, tr)) <= 2:
                        hi = mid
                    else:
                        lo = mid
                lines = LY.wrap(words, f, hi, tr)
            return px, lines
    return None


def measure_bubble(text: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """{w, h, px, lines}: the box of the bubble including its tail, or None when the text does not fit in two lines (one line for a shout)."""
    shout = bool(params.get("shout"))
    px_cap = int(params.get("px", 0)) or 0
    sizes = tuple(p for p in (SHOUT_PX if shout else BUBBLE_PX) if not px_cap or p <= px_cap) or (SHOUT_PX if shout else BUBBLE_PX)[-1:]
    padx, pady = (SHOUT_PAD_X, SHOUT_PAD_Y) if shout else (PAD_X, PAD_Y)
    fit = _fit(text.upper() if shout else text, sizes, BUBBLE_MAX_W, 1 if shout else 2, padx)
    if fit is None:
        return None
    px, lines = fit
    f = T.font("body", px)
    asc, desc = f.getmetrics()
    tr = px * TH.tracking_em
    tw = int(max(T.tracked_width(f, ln, tr) for ln in lines))
    w = max(tw + 2 * padx, 2 * TAIL_W + 40)
    body_h = len(lines) * (asc + desc) + 2 * pady
    return {"w": w, "h": body_h + TAIL_H, "px": px, "lines": lines}


def measure_spot(text: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    w, h = int(params.get("w", SPOT_W)), int(params.get("h", SPOT_H))
    if w < 120 or h < 200:
        return None
    return {"w": w, "h": h, "px": 0, "lines": []}


# ---------------------------------------------------------------- sprites
def _burst(w: int, bh: int, ss: int):
    """Outline of a spiky cry body inside w x bh (px, before supersampling): 22 points alternating outer and inner radius, deterministic."""
    cx, cy = w / 2, bh / 2
    pts = []
    n = 22
    for k in range(n * 2):
        a = math.pi * k / n
        inner = k % 2 == 1
        rx, ry = (w / 2 - 2) * (0.86 if inner else 1.0), (bh / 2 - 2) * (0.78 if inner else 1.0)
        pts.append(((cx + rx * math.cos(a)) * ss, (cy + ry * math.sin(a)) * ss))
    return pts


@lru_cache(maxsize=64)
def bubble_sprite(lines: Tuple[str, ...], role: str, w: int, h: int, px: int, tx: int, lean: int, shout: bool) -> Image.Image:
    ss = 2
    bh = h - TAIL_H
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    col = TH.roles.get(role, TH.ink) if role and role != "ink" else TH.ink
    ink = TH.outline + (255,)
    tx = min(max(tx, TAIL_W // 2 + 20), w - TAIL_W // 2 - 20)
    tip = (min(max(tx + lean, 6), w - 6), h - 3)
    root = [(tx - TAIL_W // 2, bh - 6), (tx + TAIL_W // 2, bh - 6)]
    tail = [(root[0][0] * ss, root[0][1] * ss), (tip[0] * ss, tip[1] * ss), (root[1][0] * ss, root[1][1] * ss)]
    if shout:
        pts = _burst(w, bh, ss)
        d.polygon([(x + 5 * ss, y + 6 * ss) for x, y in pts], fill=(0, 0, 0, 60))
        d.polygon(tail, fill=(255, 255, 255, 255), outline=ink)
        d.polygon(pts, fill=(255, 250, 214, 255), outline=col + (255,))
        d.line(pts + [pts[0]], fill=col + (255,), width=5 * ss, joint="curve")
    else:
        d.rounded_rectangle([5 * ss, 6 * ss, w * ss - 1, bh * ss - 1], radius=26 * ss, fill=(0, 0, 0, 55))                               # soft drop shadow
        d.rounded_rectangle([0, 0, (w - 6) * ss, (bh - 4) * ss], radius=26 * ss, fill=(255, 255, 255, 255), outline=col + (255,), width=5 * ss)
        d.polygon(tail, fill=(255, 255, 255, 255))
        d.line([tail[0], tail[1], tail[2]], fill=col + (255,), width=5 * ss, joint="curve")
        d.line([((root[0][0] + 3) * ss, (bh - 6) * ss), ((root[1][0] - 3) * ss, (bh - 6) * ss)], fill=(255, 255, 255, 255), width=8 * ss)      # opens the outline where the tail joins
    sp = big.resize((w, h), Image.LANCZOS)
    d2 = ImageDraw.Draw(sp)
    f = T.font("body", px)
    asc, desc = f.getmetrics()
    lh = asc + desc
    tr = px * TH.tracking_em
    y = (bh - 4 - lh * len(lines)) / 2
    for ln in lines:
        T.draw_tracked(d2, ((w - 6) / 2, y), ln, f, TH.ink, tr, anchor="m")
        y += lh
    return sp


@lru_cache(maxsize=16)
def spot_light(w: int, h: int) -> Image.Image:
    """The light's mask (mode L, 0..255): a cone narrow at the top that widens down to a pool on the floor, soft edges, brightest near the floor pool and fading toward the lamp."""
    ss = 2
    m = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)
    top_w, pool_h = w * 0.26, h * 0.10
    cone = [((w - top_w) / 2 * ss, 0), ((w + top_w) / 2 * ss, 0), ((w - 14) * ss, (h - pool_h / 2) * ss), (14 * ss, (h - pool_h / 2) * ss)]
    d.polygon(cone, fill=110)
    d.ellipse([14 * ss, (h - pool_h) * ss, (w - 14) * ss, (h - 2) * ss], fill=170)
    m = m.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(6, w // 28)))
    grad = Image.linear_gradient("L").resize((w, h))                       # 0 at the top, 255 at the bottom
    grad = grad.point(lambda v: int(70 + 185 * v / 255))
    return ImageChops.multiply(m, grad)


# ---------------------------------------------------------------- draw
def draw_bubble(im: Image.Image, it, age: float) -> None:
    w, h = it.rect[2] - it.rect[0], it.rect[3] - it.rect[1]
    vp = it.vparams or {}
    shout = bool(vp.get("shout"))
    tx = int(vp.get("tx", w // 3))
    lean = int(vp.get("lean", 0))
    sp = bubble_sprite(tuple(it.lines), it.role, w, h, it.px, tx, lean, shout)
    scale, alpha, dy = pop_frame(age, int(vp.get("pv", 0)))
    tipx = min(max(tx + lean, 6), w - 6)
    if abs(scale - 1.0) > 1e-6:
        sp = sp.resize((max(2, round(w * scale)), max(2, round(h * scale))), Image.BICUBIC)
    if alpha < 0.999:
        sp = sp.copy()
        sp.putalpha(sp.getchannel("A").point(lambda v: int(v * alpha)))
    x = round(it.rect[0] + tipx - tipx * sp.width / w)
    y = round(it.rect[3] - 3 - (h - 3) * sp.height / h) + dy
    im.paste(sp, (min(max(x, 0), im.width - sp.width), min(max(y, 0), im.height - sp.height)), sp)       # the large approach frames stay whole inside the frame


def draw_spot(im: Image.Image, it, age: float) -> None:
    w, h = it.rect[2] - it.rect[0], it.rect[3] - it.rect[1]
    power = float((it.vparams or {}).get("power", 0.8))
    k = spot_power(age, power)
    mask = spot_light(w, h).point(lambda v: int(v * k))
    x0, y0 = it.rect[0], it.rect[1]
    box = (max(0, x0), max(0, y0), min(im.width, x0 + w), min(im.height, y0 + h))
    if box[2] <= box[0] or box[3] <= box[1]:
        return
    mask = mask.crop((box[0] - x0, box[1] - y0, box[2] - x0, box[3] - y0))
    region = im.crop(box)
    lit = ImageChops.screen(region, Image.new("RGB", region.size, LIGHT))
    im.paste(Image.composite(lit, region, mask), box[:2])


def draw(im: Image.Image, it, age: float) -> None:
    if it.style == "spot":
        draw_spot(im, it, age)
    else:
        draw_bubble(im, it, age)
