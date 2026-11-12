"""Aviation style cards, part 1: the blue article card, the window collage and the 'Source:' tag (docs/aviation/PLAN.md N3, N4).

Same contract as the War cards: fn(t, dur, params) -> RGBA 1280x720 or None, a pure function of t and params (files named in params
are read). Text comes from the narration / CSV (outlet, headline, date, fact, name); pictures are files the user or the providers
supplied. Nothing is downloaded or invented here, and nothing is drawn when the needed input is missing.

  lay_article   image (path) or video + at (one frame of a clip), outlet, headline, date, fact, name, role.
                A rounded browser window (three dots in its top bar) slides up onto the moving blue backdrop; the picture keeps
                pushing in. Under it: outlet, headline, date (right-aligned) - or a fact strip (red square + one line).
                A name + role sits inside the window, bottom-left, over a soft shade. Without a picture the window holds a
                plain white page with the outlet and headline typeset (never a mock-up of the outlet's site).
  lay_collage   images (2-4 paths), brand (optional faint wordmark behind the windows; only the user's own channel name).
                Windows pop in one at a time.
  tag_source    source. Small 'Source: X' top-right over a borrowed clip; transparent elsewhere.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from cinematic_explainer.war import motion as M
from cinematic_explainer.war import tokens as T
from cinematic_explainer.war.graphics_lib import _load, _still, _wrap_px
from cinematic_explainer import look as L

W, H = T.W, T.H
BLUE_DARK = (6, 18, 120)
BLUE_LIGHT = (20, 52, 214)
RED = (226, 32, 40, 255)
WHITE = (255, 255, 255, 255)
WIN_W, WIN_H = int(W * 0.47), int(H * 0.42)
WIN_X, WIN_Y = int(W * 0.47 - WIN_W / 2), int(H * 0.12)
BAR_H = 26
RADIUS = 18
_CACHE: Dict[str, Image.Image] = {}


# ---------------------------------------------------------------------------------------------------------------- backdrop

def _base() -> Image.Image:
    if "base" not in _CACHE:
        # diagonal light from the lower right: rotate a gradient bigger than the frame and keep its middle (no empty corners)
        side = int(math.hypot(W, H)) + 4
        g = Image.linear_gradient("L").resize((side, side), Image.BICUBIC).rotate(-35, resample=Image.BICUBIC)
        g = g.crop(((side - W) // 2, (side - H) // 2, (side - W) // 2 + W, (side - H) // 2 + H))
        img = Image.composite(Image.new("RGB", (W, H), BLUE_LIGHT), Image.new("RGB", (W, H), BLUE_DARK), g).convert("RGBA")
        dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dots)
        for y in range(16, H, 34):
            for x in range(16, W, 34):
                dd.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(255, 255, 255, 34))
        img.alpha_composite(dots)
        _CACHE["base"] = img
    return _CACHE["base"]


def _bands() -> Image.Image:
    """Soft diagonal light bands, twice the frame wide so they can drift sideways forever."""
    if "bands" not in _CACHE:
        q = 4                                  # drawn at quarter size and blurred there: soft sweeps, no hard edges, cheap
        b = Image.new("RGBA", (W * 2 // q, H // q), (0, 0, 0, 0))
        d = ImageDraw.Draw(b)
        for x0, wd, a in ((80, 300, 30), (620, 160, 20), (1180, 360, 26), (1900, 200, 22)):
            for k in (0, W):
                d.polygon([((x0 + k) / q, H / q), ((x0 + wd + k) / q, H / q), ((x0 + wd + k + 420) / q, 0), ((x0 + k + 420) / q, 0)],
                          fill=(120, 170, 255, a))
        b = b.filter(ImageFilter.GaussianBlur(28))
        _CACHE["bands"] = b.resize((W * 2, H), Image.BICUBIC)
    return _CACHE["bands"]


def backdrop(t: float) -> Image.Image:
    img = _base().copy()
    off = int(t * 22) % W                     # the light keeps moving: the card is never a still frame
    img.alpha_composite(_bands().crop((off, 0, off + W, H)))
    return img


# ---------------------------------------------------------------------------------------------------------------- window

def _rounded_mask(size: Tuple[int, int], r: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=255)
    return m


def _cover(src: Image.Image, w: int, h: int, zoom: float) -> Image.Image:
    s = max(w / src.width, h / src.height) * zoom
    im = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _plain_page(w: int, h: int, outlet: str, headline: str) -> Image.Image:
    page = Image.new("RGB", (w, h), (250, 250, 248))
    d = ImageDraw.Draw(page)
    y = 26
    if outlet:
        L.spaced(d, (28, y), outlet.upper(), T.font("bold", 15), (120, 124, 132), 0.12)
        y += 34
    fh = T.font("serif", 30)
    for ln in _wrap_px(d, headline, fh, w - 56)[:4]:
        d.text((28, y), ln, font=fh, fill=(18, 20, 26))
        y += 40
    return page


def _window(content: Image.Image, w: int, h: int) -> Image.Image:
    """Browser window: light top bar with three dots, the content below, rounded corners, a thin light frame."""
    win = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    body = Image.new("RGBA", (w, h), (236, 240, 250, 255))
    body.paste(content.convert("RGBA"), (0, BAR_H))
    d = ImageDraw.Draw(body)
    for i, col in enumerate(((240, 70, 70), (250, 190, 40), (60, 200, 90))):
        cx = 18 + i * 16
        d.ellipse([cx - 5, BAR_H // 2 - 5, cx + 5, BAR_H // 2 + 5], fill=col)
    win.paste(body, (0, 0), _rounded_mask((w, h), RADIUS))
    ImageDraw.Draw(win).rounded_rectangle([0, 0, w - 1, h - 1], RADIUS, outline=(255, 255, 255, 150), width=2)
    return win


def _shadowed(win: Image.Image) -> Tuple[Image.Image, int]:
    pad = 40
    out = Image.new("RGBA", (win.width + pad * 2, win.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", win.size, (0, 0, 20, 0))
    sh.putalpha(win.getchannel("A").point(lambda v: int(v * 0.55)))
    out.alpha_composite(sh, (pad, pad + 14))
    out = out.filter(ImageFilter.GaussianBlur(16))
    out.alpha_composite(win, (pad, pad))
    return out, pad


def _picture(p: dict) -> Optional[Image.Image]:
    im = _load(p.get("image"))
    if im is None and p.get("video"):
        im = _still(str(p["video"]), float(p.get("at", 1.0)))
    return im


def _name_tag(win: Image.Image, name: str, role: str) -> None:
    w, h = win.size
    shade = Image.new("RGBA", (w, 90), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for i in range(90):
        sd.line([(0, i), (w, i)], fill=(0, 0, 0, int(150 * i / 90)))
    mask = win.getchannel("A").crop((0, h - 90, w, h))
    region = win.crop((0, h - 90, w, h))
    region.alpha_composite(shade)
    region.putalpha(mask)
    win.paste(region, (0, h - 90))
    d = ImageDraw.Draw(win)
    x, y = 22, h - 58
    d.rectangle([x, y + 4, x + 12, y + 16], fill=RED)
    d.text((x + 20, y), name, font=T.font("bold", 19), fill=WHITE)
    if role:
        d.text((x + 20, y + 24), role, font=T.font("regular", 12), fill=(230, 232, 238, 255))


def lay_article(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    pic = _picture(p)
    outlet = str(p.get("outlet") or "").strip()
    headline = str(p.get("headline") or "").strip()
    fact = str(p.get("fact") or "").strip()
    if pic is None and not headline:
        return None
    img = backdrop(t)
    ch = WIN_H - BAR_H
    if pic is not None:
        zoom = 1.0 + 0.10 * M.ease_in_out(M.clamp01(t / max(dur, 0.1)))   # slow push-in for the whole card
        content = _cover(pic, WIN_W, ch, zoom)
    else:
        content = _plain_page(WIN_W, ch, outlet, headline)
    win = _window(content, WIN_W, WIN_H)
    if p.get("name"):
        _name_tag(win, str(p["name"]), str(p.get("role") or ""))
    k = M.ease_out(M.ramp(t, 0.0, 0.6))
    s = 0.92 + 0.08 * k
    sw = win.resize((max(1, int(WIN_W * s)), max(1, int(WIN_H * s))), Image.LANCZOS)
    sw, pad = _shadowed(sw)
    x = int(WIN_X + (WIN_W - WIN_W * s) / 2) - pad
    y = int(WIN_Y + 40 * (1 - k) + (WIN_H - WIN_H * s) / 2) - pad
    img.alpha_composite(L.fade(_place(sw, x, y), k))
    # the text block under the window
    kt = M.ease_out(M.ramp(t, 0.35, 0.5))
    txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(txt)
    tx, ty = WIN_X + 10, WIN_Y + WIN_H + 26
    if fact:
        d.rectangle([tx, ty, tx + 34, ty + 34], fill=RED)
        d.polygon([(tx + 9, ty + 26), (tx + 17, ty + 8), (tx + 25, ty + 26)], fill=WHITE)   # a small up-arrow mark
        fy = ty + 2
        for ln in _wrap_px(d, fact, T.font("bold", 23), WIN_W - 60)[:2]:
            d.text((tx + 48, fy), ln, font=T.font("bold", 23), fill=WHITE)
            fy += 28
    elif pic is not None and (outlet or headline):
        if outlet:
            d.text((tx, ty), outlet, font=T.font("bold", 19), fill=WHITE)
            ty += 28
        fh = T.font("bold", 24)
        for ln in _wrap_px(d, headline, fh, WIN_W - 20)[:2]:
            d.text((tx, ty), ln, font=fh, fill=WHITE)
            ty += 29
    date = str(p.get("date") or "").strip()
    if date:
        fd = T.font("regular", 13)
        dw = d.textlength(date, font=fd)
        d.text((WIN_X + WIN_W - 10 - dw, ty + 6), date, font=fd, fill=(220, 226, 245, 255))
    img.alpha_composite(L.fade(txt, kt))
    return img


def _place(layer: Image.Image, x: int, y: int) -> Image.Image:
    full = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    full.alpha_composite(layer, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
    return full


# ---------------------------------------------------------------------------------------------------------------- collage

_SLOTS = {2: ((0.06, 0.20, 0.42), (0.52, 0.30, 0.42)),
          3: ((0.04, 0.16, 0.36), (0.56, 0.12, 0.36), (0.30, 0.54, 0.36)),
          4: ((0.03, 0.10, 0.34), (0.55, 0.10, 0.34), (0.03, 0.55, 0.34), (0.55, 0.55, 0.34))}
_COLLAGE_STEP = 0.6


def windows_shown(t: float, n: int) -> int:
    return sum(1 for i in range(n) if t >= 0.2 + i * _COLLAGE_STEP)


def lay_collage(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    pics = [im for im in (_load(x) for x in (p.get("images") or [])[:4]) if im is not None]
    if len(pics) < 2:
        return None
    img = backdrop(t)
    brand = str(p.get("brand") or "").strip()
    if brand:
        wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        f = T.font("display", 120)
        wd = ImageDraw.Draw(wm)
        tw = wd.textlength(brand, font=f)
        wd.text(((W - tw) / 2, H * 0.40), brand, font=f, fill=(150, 190, 255, 60))
        img.alpha_composite(wm)
    for i, (pic, (fx, fy, fw)) in enumerate(zip(pics, _SLOTS[len(pics)])):
        start = 0.2 + i * _COLLAGE_STEP
        if t < start:
            continue
        k = M.ease_out(M.ramp(t, start, 0.45))
        w = int(W * fw)
        h = int(w * 0.62)
        zoom = 1.0 + 0.06 * M.clamp01((t - start) / max(dur, 0.1))
        win = _window(_cover(pic, w, h - BAR_H, zoom), w, h)
        s = 0.85 + 0.15 * k
        win = win.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
        win, pad = _shadowed(win)
        x = int(W * fx + (w - w * s) / 2) - pad
        y = int(H * fy + (h - h * s) / 2) - pad
        img.alpha_composite(L.fade(_place(win, x, y), k))
    return img


# ---------------------------------------------------------------------------------------------------------------- source tag

def source_text(source: Any) -> str:
    s = str(source or "").strip()
    if not s:
        return ""
    return s if s.lower().startswith("source:") else f"Source: {s}"


def tag_source(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    text = source_text((p or {}).get("source"))
    if not text:
        return None
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f = T.font("bold", 14)
    tw = d.textlength(text, font=f)
    x, y = W - 18 - tw, 14
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((x + 1, y + 1), text, font=f, fill=(0, 0, 0, 170))
    lay.alpha_composite(sh.filter(ImageFilter.GaussianBlur(1.5)))
    d.text((x, y), text, font=f, fill=WHITE)
    return L.fade(lay, M.ease_out(M.ramp(t, 0.0, 0.25)))
