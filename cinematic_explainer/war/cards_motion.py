"""War Documentary motion graphics: full-frame animated cards for the stretches that have no clip (the owner, 2026-11-07: "we can use
graphics instead of that [the empty backdrop] ... add new graphics too, graphics animations"). Same contract as cards_kit: fn(t, dur, p) ->
RGBA W x H, a pure function of t and params; MOTION_CARDS maps layer kind -> function and registry.all_cards() imports it lazily.

Nothing here states a fact: every word on screen comes from the narration (the direction pass picks it), and drawn motifs (radar blips)
carry an ILLUSTRATIVE chip. Each card is opaque: it replaces the plain backdrop, never sits on top of a clip.

kit_kinetic   text*  key [words to highlight]  seed 0
              The narration's phrase built word by word in big type on a drifting grid, key words on a red block, a bar wiping under it.
Every card here takes over=True on a scene with footage: the plate becomes a see-through dark layer and the clip plays under it.
kit_dossier   title*  body ""  mark [words to highlight]  seed 0
              A paper file slides in on a dark desk; the title is typed, the body sentence follows, a highlighter strikes the key words.
kit_radar     label*  sub ""  seed 0
              A radar scope sweeps (rings, crosshair, fading beam, blips lit as the beam passes) beside the narration's words. ILLUSTRATIVE.
kit_keywords  items* [2-4 short phrases]  title ""  seed 0
              Numbered bars (01, 02 ...) slide in one after another, each with an accent block, under an optional hook title.

Cinematic set (2026-11-07, the owner: "richer graphics that make it more cinematic"): letterbox bars close in, dust drifts through a
light beam, the frame flickers like projected film.
kit_title     text*  sub ""  seed 0
              A chapter/title card: the title tracks in from wide letter spacing while a light sweep crosses it, a red rule opens under it.
kit_datecard  date*  sub ""  seed 0
              The date slams in large with a film-burn glow, a rule draws, the narration's line types underneath.
kit_quote     quote*  speaker ""  seed 0
              Full-frame quotation: a big red quote mark, the words light up one after another, the speaker's name slides in under a bar.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .. import look as L
from . import motion as M
from . import tokens as T
from .cards_kit import INK, KRED, PAPER, YELLOW, _blit, _ease_back, _hook_element, _memo, _out_alpha, _place, _rotated_cache, _shadowed, _sw, _wrap

W, H = T.W, T.H
NAVY = (12, 16, 24, 255)
GRID = (60, 78, 104)
CREAM = (250, 248, 244, 255)
GREEN = (88, 230, 150)


def _k(t: float, start: float, length: float) -> float:
    return max(0.0, min(1.0, (t - start) / max(1e-6, length)))


# ------------------------------------------------------------------------------------------------ plates ------------------------------

def _grid_tile(seed: int) -> Image.Image:
    """A dark plate twice the frame size with a fine grid, a few brighter major lines and soft light pools; cropped with a slow drift."""
    rnd = random.Random(seed)
    big = Image.new("RGBA", (W * 2, H * 2), NAVY)
    d = ImageDraw.Draw(big)
    step = 48
    for x in range(0, W * 2, step):
        d.line([(x, 0), (x, H * 2)], fill=GRID + ((80 if x % (step * 4) == 0 else 34),), width=1)
    for y in range(0, H * 2, step):
        d.line([(0, y), (W * 2, y)], fill=GRID + ((80 if y % (step * 4) == 0 else 34),), width=1)
    glow = Image.new("RGBA", (W // 2, H // 2), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for _ in range(5):
        x, y, r = rnd.uniform(0, W / 2), rnd.uniform(0, H / 2), rnd.uniform(60, 160)
        g.ellipse([x - r, y - r, x + r, y + r], fill=(48, 70, 110, 60))
    big.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)).resize((W * 2, H * 2), Image.BICUBIC))
    return big


def _vignette() -> Image.Image:
    vg = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(v * 0.8))
    shade = Image.new("RGBA", (W, H), (4, 6, 10, 255))
    shade.putalpha(vg)
    return shade


def _band() -> Image.Image:
    im = Image.new("RGBA", (W // 3, H), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([W // 12, 0, W // 4, H], fill=(120, 150, 200, 26))
    return im.filter(ImageFilter.GaussianBlur(50))


def _plate(t: float, seed: int) -> Image.Image:
    tile = _memo("mgrid" + str(seed), lambda: _grid_tile(seed))
    ang = (seed % 7) * 0.9
    ox = int((W / 2) + math.cos(ang) * t * 18) % W
    oy = int((H / 2) + math.sin(ang) * t * 12) % H
    img = tile.crop((ox, oy, ox + W, oy + H))
    band = _memo("mband", _band)
    sweep = int(((t * 0.18 + seed * 0.13) % 1.4 - 0.2) * W)          # a soft light band drifting across
    x0, x1 = max(0, sweep), min(W, sweep + band.width)
    if x1 > x0:
        img.alpha_composite(band.crop((x0 - sweep, 0, x1 - sweep, H)), (x0, 0))
    img.alpha_composite(_memo("mvig", _vignette))
    return img


def _scrim(alpha: int = 150) -> Image.Image:
    """Over footage (p['over']): a see-through dark layer with a heavier vignette, so the clip keeps playing under the words."""
    def build() -> Image.Image:
        im = Image.new("RGBA", (W, H), (6, 8, 12, alpha))
        vg = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(v * 0.55))
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        shade.putalpha(vg)
        im.alpha_composite(shade)
        return im
    return _memo("mscrim" + str(alpha), build).copy()


def _bg(t: float, seed: int, p: dict) -> Image.Image:
    return _scrim() if (p or {}).get("over") else _plate(t, seed)


def _chip(img: Image.Image, text: str) -> None:
    f = T.font("bold", 15)
    d = ImageDraw.Draw(img)
    tw = int(_sw(text, f, 0.08))
    x, y = W - T.MARGIN_X - tw - 20, H - 54
    d.rounded_rectangle([x, y, x + tw + 20, y + 28], radius=4, fill=(18, 22, 30, 210), outline=(150, 160, 176, 200), width=1)
    L.spaced(d, (x + 10, y + 5), text, f, (196, 206, 220, 255), 0.08)


# ------------------------------------------------------------------------------------------------ kinetic type ------------------------

def _layout_words(words: Sequence[str], f, max_w: int) -> List[List[int]]:
    lines: List[List[int]] = [[]]
    cur = 0.0
    sp = _sw(" ", f, 0.03)
    for i, w in enumerate(words):
        ww = _sw(w, f, 0.03)
        if lines[-1] and cur + sp + ww > max_w:
            lines.append([])
            cur = 0.0
        cur += (sp if lines[-1] else 0) + ww
        lines[-1].append(i)
    return lines


def kit_kinetic(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    words = [w for w in str(p.get("text") or "").upper().split() if w][:12]
    if not words:
        return None
    key = {str(k).upper().strip(".,;:!?") for k in (p.get("key") or [])}
    seed = int(p.get("seed", 0) or 0)
    img = _bg(t, seed, p)
    d = ImageDraw.Draw(img)
    size = 104 if len(words) <= 4 else 88 if len(words) <= 7 else 70
    f = T.font("display", size)
    lines = _layout_words(words, f, int(W * 0.78))
    while len(lines) > 3 and size > 44:
        size -= 8
        f = T.font("display", size)
        lines = _layout_words(words, f, int(W * 0.78))
    lh = int(size * 1.16)
    step = min(0.28, max(0.12, (max(dur, 2.0) * 0.55) / len(words)))
    y = int(H * 0.5 - lh * len(lines) / 2)
    sp = _sw(" ", f, 0.03)
    last_end = 0.0
    for ln in lines:
        lw = sum(_sw(words[i], f, 0.03) for i in ln) + sp * (len(ln) - 1)
        x = (W - lw) / 2
        for i in ln:
            w = words[i]
            ww = _sw(w, f, 0.03)
            a0 = 0.2 + i * step
            k = _k(t, a0, 0.32)
            last_end = a0 + 0.32
            if k > 0:
                lift = (1 - M.ease_out(k)) * 34
                is_key = w.strip(".,;:!?") in key
                if is_key:
                    kb = M.ease_out(_k(t, a0 + 0.1, 0.25))
                    d.rectangle([x - 10, y + 6, x - 10 + (ww + 20) * kb, y + lh - 6], fill=KRED)
                col = CREAM if not is_key else (255, 255, 255, 255)
                L.spaced(d, (int(x), int(y + lift)), w, f, col[:3] + (int(255 * min(1.0, k * 1.6)),), 0.03)
            x += ww + sp
        y += lh
    kb = M.ease_out(_k(t, last_end, 0.5))
    if kb > 0:
        bw = int(W * 0.22 * kb)
        d.rectangle([(W - bw) // 2, y + 10, (W + bw) // 2, y + 18], fill=YELLOW)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


# ------------------------------------------------------------------------------------------------ dossier -----------------------------

def _desk(seed: int) -> Image.Image:
    rnd = random.Random(seed + 11)
    im = Image.new("RGBA", (W // 4, H // 4), (26, 22, 20, 255))
    d = ImageDraw.Draw(im)
    for _ in range(40):
        y = rnd.uniform(0, H / 4)
        d.line([(0, y), (W / 4, y + rnd.uniform(-3, 3))], fill=(40 + rnd.randint(0, 16), 32 + rnd.randint(0, 10), 26, 120), width=1)
    im = im.filter(ImageFilter.GaussianBlur(1.2)).resize((W, H), Image.BICUBIC)
    im.alpha_composite(_memo("mvig", _vignette))
    return im


def _paper(w: int, h: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    im = Image.new("RGBA", (w, h), PAPER)
    d = ImageDraw.Draw(im)
    for _ in range(260):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        c = rnd.randint(214, 236)
        d.point((x, y), fill=(c, c - 6, c - 16, 255))
    d.rectangle([0, 0, w - 1, h - 1], outline=(200, 192, 176, 255), width=2)
    d.rectangle([w - 120, 0, w - 1, 34], fill=(230, 222, 204, 255))      # folder tab strip
    return im


DOSSIER_TYPED = 0.6


def kit_dossier(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    title = str(p.get("title") or "").strip().upper()
    if not title:
        return None
    body = str(p.get("body") or "").strip()
    marks = [str(m).lower() for m in (p.get("mark") or []) if str(m).strip()]
    seed = int(p.get("seed", 0) or 0)
    img = _scrim(120) if p.get("over") else _memo("mdesk" + str(seed), lambda: _desk(seed)).copy()
    pw = int(W * 0.62)
    ft, fb = T.font("display", 52), T.font("bold", 30)
    tl = _wrap(title, ft, pw - 100, 0.04, 2)
    n_lines = len(_wrap(body, fb, pw - 100, 0.01, 6)) if body else 0
    ph = max(int(H * 0.40), 70 + 60 * len(tl) + 34 + 42 * n_lines + 60)
    sheet = _memo("mpaper" + str(seed) + "x" + str(ph), lambda: _paper(pw, ph, seed)).copy()
    d = ImageDraw.Draw(sheet)
    n_title = sum(len(x) for x in tl)
    n_body0 = sum(len(x) for x in _wrap(body, fb, pw - 100, 0.01, 6)) if body else 0
    d_title, d_body = max(0.6, min(1.4, n_title * 0.045)), (max(0.8, min(2.2, n_body0 * 0.02)) if body else 0.0)
    # all typing done by DOSSIER_TYPED of the card's time, so the whole text is read before it fades (render 048: a 4.4 s card was
    # still typing 'creates another opportun' a moment before it went)
    sc = min(1.0, (DOSSIER_TYPED * dur) / (0.45 + d_title + 0.2 + d_body)) if dur > 0 else 1.0
    d_title, d_body = d_title * sc, d_body * sc
    typed = n_title                          # the card enters with its title on it (render 050: a blank paper for the first half second)
    d_title = 0.0
    y, left = 70, typed
    for ln in tl:
        part = ln[:max(0, left)]
        left -= len(ln)
        if part:
            L.spaced(d, (50, y), part, ft, INK, 0.04)
        y += 60
    d.rectangle([50, y + 4, pw - 50, y + 7], fill=KRED)
    y += 30
    t_body = 0.15
    if body:
        bl = _wrap(body, fb, pw - 100, 0.01, 6)
        n_body = sum(len(x) for x in bl)
        shown = int(n_body * _k(t, t_body, d_body))
        left = shown
        for ln in bl:
            part = ln[:max(0, left)]
            left -= len(ln)
            if part:
                low = ln.lower()
                for m in marks:                  # highlighter over the key words once they are typed
                    at = low.find(m)
                    if 0 <= at and at + len(m) <= len(part):
                        x0 = 50 + _sw(ln[:at], fb, 0.01)
                        k = M.ease_out(_k(t, t_body + min(1.4, d_body), 0.4))
                        if k > 0:
                            d.rectangle([x0 - 4, y + 2, x0 - 4 + (_sw(ln[at:at + len(m)], fb, 0.01) + 8) * k, y + 36], fill=(255, 222, 60, 255))
                L.spaced(d, (50, y), part, fb, (40, 38, 36, 255), 0.01)
            y += 42
    k = M.ease_out(_k(t, 0.0, 0.5))
    x, y = (W - pw) // 2, int((H - ph) / 2 + (1 - k) * H * 0.6)
    shadow = _memo("mdshadow" + str(pw) + "x" + str(ph), lambda: _shadowed(Image.new("RGBA", (pw, ph), (0, 0, 0, 255)), 14, (0, 12), 150))
    _blit(img, shadow, x - (shadow.width - pw) // 2, y - (shadow.height - ph) // 2 + 6)
    _blit(img, sheet, x, y)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


# ------------------------------------------------------------------------------------------------ radar -------------------------------

def _scope(r: int) -> Image.Image:
    im = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=(6, 22, 16, 235), outline=GREEN + (200,), width=3)
    for k in (0.25, 0.5, 0.75):
        rr = r * k
        d.ellipse([r - rr, r - rr, r + rr, r + rr], outline=GREEN + (70,), width=1)
    d.line([(r, 8), (r, 2 * r - 8)], fill=GREEN + (60,), width=1)
    d.line([(8, r), (2 * r - 8, r)], fill=GREEN + (60,), width=1)
    for a in range(0, 360, 10):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        l0 = r - (14 if a % 30 == 0 else 7)
        d.line([(r + ca * l0, r + sa * l0), (r + ca * (r - 3), r + sa * (r - 3))], fill=GREEN + (150,), width=1)
    return im


def kit_radar(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    label = str(p.get("label") or "").strip()
    if not label:
        return None
    seed = int(p.get("seed", 0) or 0)
    img = _bg(t, seed, p)
    r = int(H * 0.36)
    cx, cy = int(W * 0.31), int(H * 0.52)
    k_in = M.ease_out(_k(t, 0.0, 0.5))
    scope = _memo("mscope" + str(r), lambda: _scope(r)).copy()
    d = ImageDraw.Draw(scope)
    ang = (t * 140.0 + seed * 37) % 360.0                                # degrees per second
    for i in range(28):                                                  # the fading beam trail
        a = math.radians(ang - i * 1.6)
        al = int(150 * (1 - i / 28) ** 2)
        d.line([(r, r), (r + math.cos(a) * (r - 4), r + math.sin(a) * (r - 4))], fill=GREEN + (al,), width=4)
    rnd = random.Random(seed)
    for _ in range(6):                                                   # blips light up as the beam passes, then fade
        ba, bd = rnd.uniform(0, 360), rnd.uniform(0.2, 0.85) * r
        since = (ang - ba) % 360.0
        if t * 140.0 < since:
            continue
        glow = max(0.0, 1 - since / 300.0)
        if glow > 0:
            x, y = r + math.cos(math.radians(ba)) * bd, r + math.sin(math.radians(ba)) * bd
            s = 5 + 4 * glow
            d.ellipse([x - s, y - s, x + s, y + s], fill=(170, 255, 200, int(255 * glow)))
    _place(img, scope, cx, cy, 0.0, 0.8 + 0.2 * k_in, k_in)
    el = _memo("mradlab" + label, lambda: _shadowed(_rotated_cache("mrl" + label, _hook_element(label, 40, int(W * 0.36)), -2.0), 5, (0, 4), 110))
    kl = M.ease_out(_k(t, 0.5, 0.45))
    if kl > 0:
        part = el.crop((0, 0, max(1, int(el.width * kl)), el.height))
        _blit(img, part, int(W * 0.57), int(H * 0.40))
    sub = str(p.get("sub") or "").strip().upper()
    if sub and t > 1.0:
        f = T.font("bold", 24)
        dd = ImageDraw.Draw(img)
        for i, ln in enumerate(_wrap(sub, f, int(W * 0.38), 0.05, 2)):
            L.spaced(dd, (int(W * 0.565), int(H * 0.40) + el.height + 18 + i * 32), ln, f, (210, 230, 220, int(255 * _k(t, 1.0, 0.4))), 0.05)
    _chip(img, "ILLUSTRATIVE")
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


# ------------------------------------------------------------------------------------------------ keywords ----------------------------

def kit_keywords(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    items = [str(i).strip().upper() for i in (p.get("items") or []) if str(i).strip()][:4]
    if len(items) < 2:
        return None
    seed = int(p.get("seed", 0) or 0)
    img = _bg(t, seed, p)
    d = ImageDraw.Draw(img)
    fn, fi = T.font("display", 40), T.font("display", 46)
    bh, gap = 78, 22
    y0 = int(H * 0.56 - (len(items) * (bh + gap) - gap) / 2)
    title = str(p.get("title") or "").strip()
    if title:
        el = _memo("mkwt" + title, lambda: _shadowed(_rotated_cache("mkt" + title, _hook_element(title, 34, int(W * 0.6)), -2.0), 5, (0, 4), 110))
        kt = M.ease_out(_k(t, 0.1, 0.4))
        _blit(img, el.crop((0, 0, max(1, int(el.width * kt)), el.height)), (W - el.width) // 2, max(40, y0 - el.height - 40))
    widest = max(_sw(_wrap(it, fi, int(W * 0.62), 0.04, 1)[0], fi, 0.04) for it in items) + 196
    x0 = int((W - widest) / 2)
    for i, it in enumerate(items):
        k = M.ease_out(_k(t, 0.45 + i * 0.4, 0.45))
        if k <= 0:
            continue
        y = y0 + i * (bh + gap)
        text = _wrap(it, fi, int(W * 0.62), 0.04, 1)[0]
        bw = int((_sw(text, fi, 0.04) + 190) * k)
        d.rectangle([x0, y, x0 + bw, y + bh], fill=(18, 24, 34, 236))
        d.rectangle([x0, y, x0 + int(96 * k), y + bh], fill=KRED if i == 0 else (40, 52, 72, 255))
        if k > 0.5:
            a = int(255 * min(1.0, (k - 0.5) * 2))
            L.spaced(d, (x0 + 22, y + 16), f"{i + 1:02d}", fn, (255, 255, 255, a), 0.04)
            L.spaced(d, (x0 + 124, y + 12), text, fi, CREAM[:3] + (a,), 0.04)
        d.rectangle([x0 + bw, y, x0 + bw + 6, y + bh], fill=YELLOW)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)



# ------------------------------------------------------------------------------------------------ cinematic set -----------------------

def _cine_plate(t: float, seed: int, warm: bool = False, over: bool = False) -> Image.Image:
    """A near-black plate with a soft light beam from above, slow dust in the beam and a faint projector flicker. Over footage: the clip
    plays darkened under the same dust, flicker and letterbox."""
    base = _scrim(135) if over else _memo("mcine" + str(seed) + str(warm), lambda: _beam_plate(seed, warm)).copy()
    d = ImageDraw.Draw(base)
    rnd = random.Random(seed * 7 + 3)
    for i in range(46):                                                  # dust: each mote drifts on its own slow path
        x0, y0, sp, sz = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(6, 22), rnd.uniform(0.8, 1.9)
        x = (x0 + t * sp * rnd.uniform(-1, 1)) % W
        y = (y0 - t * sp * 0.6) % H
        a = int(22 + 48 * (0.5 + 0.5 * math.sin(t * rnd.uniform(0.8, 2.2) + i)))
        d.ellipse([x - sz, y - sz, x + sz, y + sz], fill=(230, 220, 200, a))
    flick = 0.035 * math.sin(t * 23.0 + seed) + 0.02 * math.sin(t * 7.3)
    if flick > 0:
        base.alpha_composite(Image.new("RGBA", (W, H), (255, 240, 220, int(255 * flick))))
    return base


def _beam_plate(seed: int, warm: bool) -> Image.Image:
    im = Image.new("RGBA", (W // 4, H // 4), (8, 9, 12, 255))
    d = ImageDraw.Draw(im)
    cx = W / 8 + (seed % 5 - 2) * 12
    col = (120, 90, 60, 70) if warm else (90, 110, 140, 64)
    d.polygon([(cx - 18, 0), (cx + 18, 0), (cx + 120, H / 4), (cx - 120, H / 4)], fill=col)
    im = im.filter(ImageFilter.GaussianBlur(14)).resize((W, H), Image.BICUBIC)
    im.alpha_composite(_memo("mvig", _vignette))
    return im


def _letterbox(img: Image.Image, t: float, dur: float) -> None:
    """Bars close in over the first 0.6 s (and open again in the last 0.4 s): the frame turns 2.39:1 for the card."""
    k = M.ease_out(_k(t, 0.0, 0.6)) * (1.0 - M.ease_out(_k(t, max(0.0, dur - 0.4), 0.4)) if dur > 1.0 else 1.0)
    bh = int(H * 0.12 * k)
    if bh > 0:
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, bh], fill=(0, 0, 0, 255))
        d.rectangle([0, H - bh, W, H], fill=(0, 0, 0, 255))


def _sweep(el: Image.Image, t: float, start: float, length: float) -> Image.Image:
    """A soft light band crossing the element (only where it is drawn)."""
    k = _k(t, start, length)
    if k <= 0 or k >= 1:
        return el
    band = Image.new("L", el.size, 0)
    bd = ImageDraw.Draw(band)
    x = int(-el.width * 0.3 + k * el.width * 1.6)
    bd.polygon([(x, 0), (x + 90, 0), (x + 30, el.height), (x - 60, el.height)], fill=150)
    band = band.filter(ImageFilter.GaussianBlur(14))
    glow = Image.new("RGBA", el.size, (255, 246, 226, 0))
    glow.putalpha(ImageChops.multiply(band, el.getchannel("A")))
    out = el.copy()
    out.alpha_composite(glow)
    return out


def _text_img(text: str, f, fill, sp: float) -> Image.Image:
    w = int(_sw(text, f, sp)) + 8
    im = Image.new("RGBA", (max(1, w), int(f.size * 1.3)), (0, 0, 0, 0))
    L.spaced(ImageDraw.Draw(im), (4, 0), text, f, fill, sp)
    return im


def kit_title(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    text = str(p.get("text") or "").strip().upper()
    if not text:
        return None
    seed = int(p.get("seed", 0) or 0)
    img = _cine_plate(t, seed, over=bool(p.get("over")))
    size = 92 if len(text) <= 18 else 74 if len(text) <= 30 else 58
    f = T.font("display", size)
    lines = _wrap(text, f, int(W * 0.8), 0.06, 2)
    kt = M.ease_out(_k(t, 0.35, 1.1))
    sp = 0.06 + 0.5 * (1 - kt)                                           # tracking in: wide letter spacing closes up
    y = int(H * 0.46 - len(lines) * size * 0.6)
    for i, ln in enumerate(lines):
        el = _text_img(ln, f, CREAM, sp)
        el = _sweep(el, t, 1.2 + 0.15 * i, 1.0)
        a = int(255 * min(1.0, kt * 1.4))
        el.putalpha(el.getchannel("A").point(lambda v, a=a: v * a // 255))
        _blit(img, el, (W - el.width) // 2, y)
        y += int(size * 1.12)
    d = ImageDraw.Draw(img)
    kr = M.ease_out(_k(t, 0.9, 0.6))
    if kr > 0:
        rw = int(W * 0.18 * kr)
        d.rectangle([(W - rw) // 2, y + 10, (W + rw) // 2, y + 14], fill=KRED)
    sub = str(p.get("sub") or "").strip().upper()
    if sub:
        fs = T.font("bold", 24)
        ks = _k(t, 1.3, 0.5)
        if ks > 0:
            ln = _wrap(sub, fs, int(W * 0.7), 0.12, 1)[0]
            L.spaced(d, (int((W - _sw(ln, fs, 0.12)) / 2), y + 34), ln, fs, (210, 204, 190, int(255 * ks)), 0.12)
    _letterbox(img, t, dur)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


def kit_datecard(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    date = str(p.get("date") or "").strip().upper()
    if not date:
        return None
    seed = int(p.get("seed", 0) or 0)
    img = _cine_plate(t, seed, warm=True, over=bool(p.get("over")))
    burn = _memo("mburn", _burn)
    kb = _k(t, 0.15, 0.9)
    if 0 < kb < 1:                                                       # a warm film-burn glow sweeps through as the date lands
        glow = burn.copy()
        glow.putalpha(glow.getchannel("A").point(lambda v: int(v * math.sin(math.pi * kb))))
        _blit(img, glow, int(-W * 0.3 + kb * W * 0.6), 0)
    size = 120 if len(date) <= 10 else 96 if len(date) <= 16 else 74
    f = T.font("display", size)
    ks = _k(t, 0.25, 0.35)
    if ks > 0:
        el = _text_img(date, f, YELLOW, 0.04)
        sc = 1.18 - 0.18 * M.ease_out(ks)                                 # slams in from slightly larger
        _place(img, el, W / 2, H * 0.44, 0.0, sc, min(1.0, ks * 2))
    d = ImageDraw.Draw(img)
    kr = M.ease_out(_k(t, 0.7, 0.5))
    if kr > 0:
        rw = int(W * 0.34 * kr)
        d.rectangle([(W - rw) // 2, int(H * 0.44 + size * 0.62), (W + rw) // 2, int(H * 0.44 + size * 0.62) + 3], fill=CREAM)
    sub = str(p.get("sub") or "").strip().upper()
    if sub:
        fs = T.font("bold", 26)
        ln = _wrap(sub, fs, int(W * 0.7), 0.1, 1)[0]
        n = int(len(ln) * _k(t, 1.0, max(0.6, len(ln) * 0.035)))
        if n:
            L.spaced(d, (int((W - _sw(ln, fs, 0.1)) / 2), int(H * 0.44 + size * 0.62) + 22), ln[:n], fs, (230, 224, 210, 255), 0.1)
    _letterbox(img, t, dur)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


def _burn() -> Image.Image:
    im = Image.new("RGBA", (W // 4, H // 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([W / 12, -H / 10, W / 6, H / 4], fill=(255, 150, 60, 110))      # well inside: the blur never meets an edge
    return im.filter(ImageFilter.GaussianBlur(26)).resize((W, H), Image.BICUBIC)


def kit_quote(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    quote = str(p.get("quote") or "").strip().strip('"').strip("\u201c\u201d")
    if not quote:
        return None
    seed = int(p.get("seed", 0) or 0)
    img = _cine_plate(t, seed, over=bool(p.get("over")))
    d = ImageDraw.Draw(img)
    fq = T.font("serif", 52 if len(quote) <= 90 else 42)
    mark = T.font("serif", 200)
    km = M.ease_out(_k(t, 0.2, 0.5))
    lines = _wrap(quote, fq, int(W * 0.72), 0.0, 4)
    words_total = sum(len(ln.split()) for ln in lines)
    step = min(0.32, max(0.08, (max(dur, 3.0) * 0.6) / max(1, words_total)))
    y, wi = int(H * 0.5 - (len(lines) * fq.size * 1.3 + 40) / 2), 0
    sp = _sw(" ", fq, 0.0)
    if km > 0:
        L.spaced(d, (int(W * 0.1), y - 150 - int(20 * (1 - km))), "\u201c", mark, KRED[:3] + (int(255 * km),), 0.0)
    for ln in lines:
        x = W * 0.16
        for w in ln.split():
            k = _k(t, 0.6 + wi * step, 0.35)
            col = (250, 246, 236, int(70 + 185 * k))                      # words wait dimmed, then light up as they are reached
            L.spaced(d, (int(x), y), w, fq, col, 0.0)
            x += _sw(w, fq, 0.0) + sp
            wi += 1
        y += int(fq.size * 1.3)
    who = str(p.get("speaker") or "").strip().upper()
    if who:
        kw = M.ease_out(_k(t, 0.6 + words_total * step * 0.5, 0.5))
        if kw > 0:
            d.rectangle([int(W * 0.16), y + 18, int(W * 0.16) + int(60 * kw), y + 22], fill=KRED)
            L.spaced(d, (int(W * 0.16) + int(80 * kw) - 10, y + 6), who, T.font("bold", 26), (230, 224, 210, int(255 * kw)), 0.1)
    _letterbox(img, t, dur)
    return L.fade(img, _out_alpha(t, dur) if dur > 0 else 1.0)


def kit_field(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """A text-free opaque backing for a card that has no footage under it (a figure, a stamp, a panel intro): the near-black beam plate with drifting
    dust, a light band crossing slowly and faint rings widening from a drifting centre. It never reads as the grey grid plate and states nothing."""
    p = p or {}
    seed = int(p.get("seed") or 0)
    img = _cine_plate(t, seed, warm=bool(seed % 2))
    sweep = int(((t * 0.14 + seed * 0.11) % 1.5 - 0.25) * W)
    band = _memo("mband", _band)
    x0, x1 = max(0, sweep), min(W, sweep + band.width)
    if x1 > x0:
        img.alpha_composite(band.crop((x0 - sweep, 0, x1 - sweep, H)), (x0, 0))
    rings = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(rings)
    cx = W * (0.68 + 0.05 * math.sin(t * 0.21 + seed))
    cy = H * (0.5 + 0.06 * math.cos(t * 0.17 + seed))
    for i in range(5):
        k = ((t * 0.09 + i / 5.0) % 1.0)
        r = 90 + k * 620
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(110, 150, 210, int(46 * (1.0 - k))), width=2)
    img.alpha_composite(rings)
    return Image.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 255)), img)      # the vignette edge is see-through in the plates: settle it on black


MOTION_CARDS = {"kit_field": kit_field, "kit_kinetic": kit_kinetic, "kit_dossier": kit_dossier, "kit_radar": kit_radar, "kit_keywords": kit_keywords,
                "kit_title": kit_title, "kit_datecard": kit_datecard, "kit_quote": kit_quote}
