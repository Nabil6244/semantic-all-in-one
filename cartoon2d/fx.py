"""Stage B effects for the cartoon2d renderer.

follow(img, hx, hy, top=True)   follow-through: the top of a head (hair, ears, bows) or the hem of a body lags behind the
                                motion. Returns (padded image, pad) - place it at offset (-pad, -pad).
dust(frame, x, y, age, s)       a puff of dust where feet land
sparkles(frame, box, t, seed)   twinkling stars around a happy character
screen_fx(frame, kind, age, dur, seed)   full-screen confetti / bubbles / leaves / hearts / stars (line field "fx")
transition(a, b, q, kind)       place change: iris / star / push / page
"""
import math
import random
from functools import lru_cache

import numpy as np

from PIL import Image, ImageDraw, ImageFilter

LINE = (70, 45, 30)
PAD = 0.06
BANDS = 10
PALETTE = [(255, 90, 90), (255, 165, 40), (255, 215, 50), (60, 190, 100), (60, 150, 240), (170, 100, 230), (255, 120, 190)]
TRANSITIONS = ("iris", "star", "push", "page")


# ------------------------------------------------------------------ follow-through
def _padded(img, m):
    out = Image.new("RGBA", (img.width + 2 * m, img.height + 2 * m), (0, 0, 0, 0))
    out.paste(img, (m, m))
    return out


def follow(img, hx, hy, top=True):
    """Shift the top 55 % (top=True) or the bottom 30 % (hem) of img by up to (hx, hy) px, fading to 0 at the joint."""
    m = int(max(img.width, img.height) * PAD)
    src = _padded(img, m)
    W, H = src.size
    h = img.height
    mesh = []
    for i in range(BANDS):
        y0, y1 = round(H * i / BANDS), round(H * (i + 1) / BANDS)

        def f(y):
            v = (y - m) / h
            w = max(0.0, 1 - v / 0.55) if top else max(0.0, (v - 0.7) / 0.3)
            return min(w, 1.0) ** 1.6
        f0, f1 = f(y0), f(y1)
        mesh.append(((0, y0, W, y1), (-hx * f0, y0 - hy * f0, -hx * f1, y1 - hy * f1, W - hx * f1, y1 - hy * f1, W - hx * f0, y0 - hy * f0)))
    return src.transform((W, H), Image.MESH, mesh, Image.BICUBIC), m


# ------------------------------------------------------------------ little drawn effects
def _star(d, x, y, r, col, rot=0.0, inner=0.45):
    pts = []
    for i in range(10):
        a = rot + math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * inner
        pts.append((x + rr * math.cos(a), y - rr * math.sin(a)))
    d.polygon(pts, fill=col, outline=LINE + (col[3],), width=max(1, int(r * 0.14)))


def _heart(d, x, y, r, col):
    d.ellipse([x - r, y - r * 0.7, x, y + r * 0.2], fill=col)
    d.ellipse([x, y - r * 0.7, x + r, y + r * 0.2], fill=col)
    d.polygon([(x - r * 0.97, y - r * 0.1), (x + r * 0.97, y - r * 0.1), (x, y + r)], fill=col)


def dust(frame, x, y, age, s):
    """age 0..1 over the puff's life; s = character height on screen."""
    if not 0 <= age < 1:
        return
    d = ImageDraw.Draw(frame)
    a = int(150 * (1 - age) ** 1.5)
    for i, (dx, dy, r) in enumerate(((-1, 0, 1), (1, 0, 1), (-0.6, -0.3, 0.8), (0.6, -0.3, 0.8), (-1.4, 0.1, 0.6), (1.4, 0.1, 0.6))):
        spread = 0.12 + 0.22 * math.sqrt(age)
        rr = s * (0.03 + 0.045 * age) * r
        cx, cy = x + dx * s * spread, y + dy * s * 0.08 * (1 + age) - s * 0.01
        d.ellipse([cx - rr, cy - rr * 0.8, cx + rr, cy + rr * 0.8], fill=(250, 244, 230, a))


def sparkles(frame, box, t, seed):
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(frame)
    rnd = random.Random(seed)
    for i in range(7):
        ph = rnd.uniform(0, 6.28)
        sp = rnd.uniform(1.8, 3.0)
        a = max(0.0, math.sin(t * sp + ph))
        if a < 0.15:
            continue
        u, v = rnd.random(), rnd.uniform(0.0, 0.7)
        x = x0 - 0.15 * (x1 - x0) + u * 1.3 * (x1 - x0)
        y = y0 + v * (y1 - y0)
        r = (x1 - x0) * 0.045 * a + 4
        _star(d, x, y, r, (255, 225, 60, int(255 * a)), rot=t * 1.5 + ph)


def screen_fx(frame, kind, age, dur, seed):
    """Full-screen effects. age = seconds since start, dur = how long new pieces keep coming."""
    W, H = frame.size
    d = ImageDraw.Draw(frame)
    rnd = random.Random(seed)
    n = {"confetti": 70, "bubbles": 26, "leaves": 22, "hearts": 18, "stars": 24}.get(kind, 0)
    for i in range(n):
        born = rnd.uniform(0, max(dur - 0.5, 0.2)) if kind != "confetti" else rnd.uniform(0, 0.25)
        life = {"confetti": 3.2, "bubbles": 4.0, "leaves": 5.0, "hearts": 3.0, "stars": 2.4}[kind]
        x0 = rnd.uniform(0.03, 0.97) * W
        col = PALETTE[rnd.randrange(len(PALETTE))]
        ph = rnd.uniform(0, 6.28)
        q = (age - born) / life
        if not 0 <= q < 1:
            continue
        fade = min(1.0, (1 - q) / 0.2)
        if kind == "confetti":                        # a burst from the top that flutters down
            x = x0 + 60 * math.sin(age * 3 + ph)
            y = -40 + q * (H + 80) * (0.6 + 0.4 * rnd.random())
            w, h = 16, 9 + 7 * abs(math.sin(age * 8 + ph))
            ang = age * 4 + ph
            c, s = math.cos(ang), math.sin(ang)
            pts = [(x + c * dx - s * dy, y + s * dx + c * dy) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            d.polygon(pts, fill=col + (int(255 * fade),))
        elif kind == "bubbles":                       # float up, wobble, pop at the end
            r = 18 + 22 * rnd.random()
            x = x0 + 30 * math.sin(age * 1.6 + ph)
            y = H + r - q * (H * 0.9)
            a = int(200 * fade)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(190, 230, 255, int(a * 0.35)), outline=(255, 255, 255, a), width=3)
            d.ellipse([x - r * 0.55, y - r * 0.6, x - r * 0.2, y - r * 0.25], fill=(255, 255, 255, a))
        elif kind == "leaves":                        # drift down, swinging side to side
            x = x0 + 90 * math.sin(age * 1.2 + ph)
            y = -30 + q * (H + 60)
            col = ((240, 150, 40), (220, 90, 40), (250, 200, 50), (120, 180, 60))[i % 4]
            ang = 0.8 * math.sin(age * 1.2 + ph)
            r = 16
            c, s = math.cos(ang), math.sin(ang)
            pts = [(x + c * dx - s * dy, y + s * dx + c * dy) for dx, dy in ((0, -r), (r * 0.55, 0), (0, r), (-r * 0.55, 0))]
            d.polygon(pts, fill=col + (int(255 * fade),), outline=LINE + (int(200 * fade),))
        elif kind == "hearts":
            x = x0 + 40 * math.sin(age * 2 + ph)
            y = H * 0.9 - q * H * 0.7
            _heart(d, x, y, 22 + 10 * math.sin(age * 5 + ph), (255, 90, 130, int(240 * fade)))
        elif kind == "stars":
            x = x0
            y = rnd.uniform(0.05, 0.6) * H
            a = math.sin(math.pi * q)
            _star(d, x, y, 10 + 22 * a, (255, 225, 60, int(255 * a)), rot=age * 2 + ph)


# ------------------------------------------------------------------ motion blur
def _box1d(a, r, axis):
    """Box average of width 2r+1 along one axis (edges clamped)."""
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float32)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def motion_blur(layer, bx, by):
    """Blur a transparent layer along x by bx px and along y by by px (shutter smear of a fast move). In place."""
    bb = layer.getbbox()
    if not bb:
        return layer
    rx, ry = int(bx / 2), int(by / 2)
    x0, y0 = max(0, bb[0] - rx - 2), max(0, bb[1] - ry - 2)
    x1, y1 = min(layer.width, bb[2] + rx + 2), min(layer.height, bb[3] + ry + 2)
    cr = layer.crop((x0, y0, x1, y1))
    pm = cr.mode == "RGBA"
    a = np.asarray(cr.convert("RGBa") if pm else cr, np.float32)
    a = _box1d(_box1d(a, rx, 1), ry, 0)
    out = Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBa" if pm else cr.mode)
    layer.paste(out.convert("RGBA") if pm else out, (x0, y0))
    return layer


# ------------------------------------------------------------------ transitions between places
@lru_cache(maxsize=8)
def _star_mask_base(n=512):
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)
    pts = []
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        rr = n / 2 if i % 2 == 0 else n / 2 * 0.48
        pts.append((n / 2 + rr * math.cos(a), n / 2 - rr * math.sin(a)))
    d.polygon(pts, fill=255)
    return m


def transition(a, b, q, kind):
    """a = old place frame, b = new place frame (RGBA, same size); q 0..1 eased progress. Returns the mixed frame."""
    W, H = a.size
    if kind == "push":                                # the new place pushes the old one off to the left
        x = int(W * q)
        out = Image.new("RGBA", (W, H))
        out.paste(a, (-x, 0))
        out.paste(b, (W - x, 0))
        return motion_blur(out, 60 * math.sin(math.pi * q), 0)     # a whip: smeared while it moves fastest
    if kind == "page":                                # a diagonal page sweep with a soft shadow on its edge
        m = Image.new("L", (W, H), 0)
        x = -0.3 * W + q * 1.6 * W
        ImageDraw.Draw(m).polygon([(-10, -10), (x + 0.15 * W, -10), (x - 0.15 * W, H + 10), (-10, H + 10)], fill=255)
        sh = m.filter(ImageFilter.GaussianBlur(28)).point(lambda v: int(v * 0.35))
        a = a.copy()
        a.paste(Image.new("RGBA", (W, H), (40, 20, 40, 255)), (0, 0), sh)
        a.paste(b, (0, 0), m)
        return a
    big = math.hypot(W, H)
    m = Image.new("L", (W, H), 0)
    if kind == "star":
        s = max(2, int(q * big * 2.2))
        st = _star_mask_base().resize((s, s), Image.BILINEAR)
        m.paste(st, (W // 2 - s // 2, H // 2 - s // 2))
    else:                                             # iris (circle)
        r = q * big / 2 + 2
        ImageDraw.Draw(m).ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], fill=255)
    a = a.copy()
    a.paste(b, (0, 0), m)
    return a
