"""Story / retention pieces drawn by render.py (docs/cartoon2d/STORY_BIBLE.md).

countdown(frame, t, t0, t1)               3-2-1 ring under the "Your turn!" badge
draw_find(frame, f, t, sx, sy, h)         a hidden object in the place; after "found" it pops, glows and sparkles
collection(frame, got, total, pics)       the found objects collected in a bar at the top right ("3 / 10")
map_card(stops, k, q, bobo_head)          the treasure map: stops done (stars), Bobo walking from stop k-1 to k
end_screen(frame, q, text)                the last 20 s: the show shrinks to the left, room on the right for YouTube's boxes
make_blocks(out_dir, letters)             wooden alphabet blocks as props (block_a.png ...), drawn, no art needed
"""
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import fx

from fonts import FONT  # noqa: E402  (Arial Rounded on the Mac, a shipped font elsewhere)
LINE = (70, 45, 30)
BLOCK_COLS = [(255, 90, 90), (255, 165, 40), (250, 205, 40), (80, 190, 100), (60, 150, 240), (170, 100, 230), (255, 120, 190)]


def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


@lru_cache(maxsize=8)
def _font(size):
    return ImageFont.truetype(FONT, size)


# ------------------------------------------------------------------ your-turn countdown
def countdown(frame, t, t0, t1, cx, cy, r=58):
    q = (t - t0) / max(t1 - t0, 0.3)
    if not 0 <= q <= 1:
        return
    n = max(1, math.ceil(3 * (1 - q)))
    d = ImageDraw.Draw(frame)
    pop = 1 + 0.18 * max(0.0, 1 - ((3 * q) % 1) / 0.25)        # each number pops in
    rr = r * pop
    d.ellipse([cx - rr - 6, cy - rr - 6, cx + rr + 6, cy + rr + 6], fill=(255, 255, 255, 255))
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(60, 150, 240, 255))
    d.arc([cx - rr - 3, cy - rr - 3, cx + rr + 3, cy + rr + 3], -90, -90 + 360 * (1 - q), fill=(255, 214, 40, 255), width=10)
    d.text((cx, cy + 2), str(n), font=_font(int(76 * pop)), fill=(255, 255, 255, 255), anchor="mm", stroke_width=4,
           stroke_fill=(30, 80, 160, 255))


# ------------------------------------------------------------------ can you find it?
def draw_find(frame, pic, t, t_found, sx, sy, h, peek=None, mound=None):
    """pic = RGBA sticker; (sx, sy) = screen position of its bottom centre; h = its height on screen.
    peek = 0..1: until found only that top share shows (buried in sand, sunk in balls) over a little mound of the
    colour mound (RGB); once found it pops up whole."""
    big = 1.0
    if t_found is not None and t >= t_found:
        a = t - t_found
        big = 1 + 0.6 * math.sin(math.pi * min(a / 0.5, 1)) + 0.25 * _smooth(a / 0.5)   # pop up, settle a bit bigger
        if a < 2.2:                                                                    # a glow ring that pulses out
            rr = h * (0.7 + 0.5 * (a % 0.7) / 0.7)
            al = int(200 * (1 - (a % 0.7) / 0.7) * (1 - a / 2.2))
            ImageDraw.Draw(frame).ellipse([sx - rr, sy - h * 0.55 - rr, sx + rr, sy - h * 0.55 + rr], outline=(255, 235, 90, al),
                                          width=max(3, int(h * 0.06)))
            fx.sparkles(frame, (sx - h * 0.7, sy - h * 1.6, sx + h * 0.7, sy), t, 17)
    else:                                                                              # hidden: just a tiny wobble
        big = 1 + 0.03 * math.sin(t * 2.3)
    hh = max(4, int(h * big))
    ww = max(4, int(pic.width * hh / pic.height))
    im = pic.resize((ww, hh), Image.BICUBIC)
    hidden = t_found is None or t < t_found
    if peek and hidden:
        show = max(1, int(hh * peek))
        frame.alpha_composite(im.crop((0, 0, ww, show)), (int(sx - ww / 2), int(sy - show)))
        if mound:
            mw, mh = ww * 0.55, hh * 0.09                 # a low mound just over the cut, the head stays clear
            ImageDraw.Draw(frame).ellipse([sx - mw, sy - mh * 0.6, sx + mw, sy + mh * 1.4], fill=tuple(mound) + (255,),
                                          outline=(70, 45, 30, 255), width=max(2, int(h * 0.03)))
        return
    frame.alpha_composite(im, (int(sx - ww / 2), int(sy - hh)))


def collection(frame, got, total, pics):
    """got = [pic images found so far]; drawn as a bar of slots at the top right."""
    if total <= 0:
        return
    W = frame.width
    s = 62
    pad = 10
    bw = total * (s + 6) + 2 * pad + 6
    x0, y0 = W - bw - 34, 28
    bar = Image.new("RGBA", (bw, s + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(bar)
    d.rounded_rectangle([0, 0, bw - 1, s + 2 * pad - 1], radius=26, fill=(255, 255, 255, 215), outline=(255, 190, 60, 255), width=4)
    for i in range(total):
        x = pad + 3 + i * (s + 6)
        if i < len(got):
            p = got[i]
            hh = s - 6
            ww = int(p.width * hh / p.height)
            if ww > s - 4:
                ww, hh = s - 4, int(p.height * (s - 4) / p.width)
            bar.alpha_composite(p.resize((max(1, ww), max(1, hh)), Image.BICUBIC), (x + (s - ww) // 2, pad + (s - hh) // 2))
        else:
            d.rounded_rectangle([x + 6, pad + 6, x + s - 6, pad + s - 6], radius=12, outline=(200, 190, 170, 255), width=3)
            d.text((x + s / 2, pad + s / 2), "?", font=_font(30), fill=(200, 190, 170, 255), anchor="mm")
    frame.alpha_composite(bar, (x0, y0))


# ------------------------------------------------------------------ the treasure map
def _stop_points(n, W, H):
    """A winding path of n stops across the card: two rows, snake shape."""
    pts = []
    rows = 2 if n > 5 else 1
    per = math.ceil(n / rows)
    for i in range(n):
        r, c = divmod(i, per)
        if r % 2:
            c = per - 1 - c
        x = W * (0.13 + 0.74 * (c / max(per - 1, 1)))
        y = H * ((0.42 if rows == 2 else 0.58) + 0.3 * r) + 28 * math.sin(i * 1.7)
        pts.append((x, y))
    return pts


@lru_cache(maxsize=24)
def _map_base(stops, k, title):
    W, H = 1600, 860
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([14, 20, W - 2, H - 2], radius=60, fill=(0, 0, 0, 80))
    d.rounded_rectangle([0, 0, W - 16, H - 22], radius=60, fill=(250, 232, 188, 255), outline=(160, 110, 60, 255), width=10)
    for i in range(14):                                     # paper speckles
        x, y = (i * 397) % (W - 120) + 60, (i * 233) % (H - 160) + 70
        d.ellipse([x, y, x + 18, y + 12], fill=(238, 214, 160, 255))
    d.text((W / 2 - 8, 70), title, font=_font(64), fill=(200, 80, 50, 255), anchor="mm", stroke_width=5, stroke_fill=(255, 250, 235, 255))
    pts = _stop_points(len(stops), W - 16, H - 22)
    for a, b in zip(pts, pts[1:]):                          # dashed path
        n = int(math.hypot(b[0] - a[0], b[1] - a[1]) / 26)
        for j in range(n):
            if j % 2 == 0:
                q0, q1 = j / n, (j + 1) / n
                d.line([(a[0] + (b[0] - a[0]) * q0, a[1] + (b[1] - a[1]) * q0), (a[0] + (b[0] - a[0]) * q1, a[1] + (b[1] - a[1]) * q1)],
                       fill=(160, 110, 60, 255), width=9)
    for i, ((x, y), lab) in enumerate(zip(pts, stops)):
        done, cur = i < k, i == k
        col = BLOCK_COLS[i % len(BLOCK_COLS)] if (done or cur) else (205, 195, 175)
        r = 54 if cur else 46
        d.ellipse([x - r - 6, y - r - 6, x + r + 6, y + r + 6], fill=(255, 255, 255, 255))
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (255,), outline=LINE + (255,), width=5)
        d.text((x, y + 2), lab, font=_font(52 if cur else 44), fill=(255, 255, 255, 255), anchor="mm", stroke_width=4,
               stroke_fill=LINE + (255,))
        if done:
            fx._star(d, x + r * 0.75, y - r * 0.75, 22, (255, 215, 40, 255))
    lx, ly = pts[-1]                                        # an X marks the end
    d.line([(lx + 60, ly - 30), (lx + 110, ly + 20)], fill=(220, 40, 40, 255), width=12)
    d.line([(lx + 110, ly - 30), (lx + 60, ly + 20)], fill=(220, 40, 40, 255), width=12)
    return im, tuple(pts)


def map_card(stops, k, a, bobo_head, title="Bobo's map!"):
    """a = seconds since the map opened. Returns the card (RGBA) with Bobo walking to stop k."""
    base, pts = _map_base(tuple(stops), k, title)
    im = base.copy()
    q = _smooth((a - 0.35) / 1.4)
    p0 = pts[max(k - 1, 0)]
    p1 = pts[min(k, len(pts) - 1)]
    x = p0[0] + (p1[0] - p0[0]) * q
    y = p0[1] + (p1[1] - p0[1]) * q - 70 - abs(math.sin(q * math.pi * 3)) * 26 * (q < 1)
    hh = 130
    ww = int(bobo_head.width * hh / bobo_head.height)
    im.alpha_composite(bobo_head.resize((ww, hh), Image.BICUBIC), (int(x - ww / 2), int(y - hh / 2)))
    return im


# ------------------------------------------------------------------ end screen
def end_screen(frame, q, text="Watch next!"):
    """The episode frame shrinks into the left, a bright panel on the right leaves room for YouTube's end-screen boxes."""
    W, H = frame.size
    s = 1 - 0.42 * _smooth(q)
    if s >= 0.999:
        return frame
    bg = Image.new("RGBA", (W, H), (255, 214, 90, 255))
    d = ImageDraw.Draw(bg)
    for i in range(0, W + H, 90):                              # sunny stripes
        d.polygon([(i, 0), (i + 45, 0), (i + 45 - H, H), (i - H, H)], fill=(255, 200, 70, 255))
    w, h = int(W * s), int(H * s)
    x, y = int(60 * _smooth(q)), int((H - h) / 2)
    small = frame.resize((w, h), Image.BICUBIC)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(40 * _smooth(q)) + 1, fill=255)
    d.rounded_rectangle([x - 10, y - 10, x + w + 10, y + h + 10], radius=50, fill=(255, 255, 255, 255))
    bg.paste(small, (x, y), m)
    if q > 0.4:
        a = int(255 * _smooth((q - 0.4) / 0.6))
        d.text((x + w + (W - x - w) / 2, int(H * 0.13)), text, font=_font(72), fill=(220, 60, 60, a), anchor="mm", stroke_width=6,
               stroke_fill=(255, 255, 255, a))
    return bg


# ------------------------------------------------------------------ baby signs
def sign_badge(frame, sign, q, hand=None):
    """Bottom-left badge naming the sign being made ("Sign: more"), with a waving open hand."""
    if q <= 0.02:
        return
    f = _font(64)
    text = sign.replace("_", " ").upper()
    w = int(f.getlength(text)) + 230
    im = Image.new("RGBA", (w, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 12, w - 2, 148], radius=60, fill=(0, 0, 0, 60))
    d.rounded_rectangle([0, 0, w - 10, 136], radius=60, fill=(255, 255, 255, 245), outline=(120, 90, 220, 255), width=7)
    d.text((132, 34), "SIGN", font=_font(30), fill=(120, 90, 220, 255), anchor="lm")
    d.text((132, 88), text, font=f, fill=(90, 60, 200, 255), anchor="lm")
    if hand is not None:
        hh = 104
        hw = int(hand.width * hh / hand.height)
        im.alpha_composite(hand.resize((hw, hh), Image.BICUBIC), (int(66 - hw / 2), 16))
    s = 0.6 + 0.4 * q
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)
    im.putalpha(im.getchannel("A").point(lambda v: int(v * q)))
    frame.alpha_composite(im, (48, frame.height - im.height - 54))


# ------------------------------------------------------------------ alphabet blocks
def make_blocks(out_dir, letters):
    from pathlib import Path
    out = Path(out_dir)
    for i, L in enumerate(letters):
        S = 600
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        col = BLOCK_COLS[i % len(BLOCK_COLS)]
        dark = tuple(int(c * 0.72) for c in col)
        top = tuple(min(255, int(c * 1.15) + 20) for c in col)
        f, o = 90, 18
        d.polygon([(70, 150), (150, 70), (560, 70), (480, 150)], fill=top + (255,), outline=LINE + (255,), width=o)
        d.polygon([(480, 150), (560, 70), (560, 480), (480, 560)], fill=dark + (255,), outline=LINE + (255,), width=o)
        d.rounded_rectangle([70, 150, 480, 560], radius=30, fill=col + (255,), outline=LINE + (255,), width=o)
        d.rounded_rectangle([110, 190, 440, 520], radius=24, fill=(255, 250, 235, 255))
        d.text((275, 360), L, font=_font(260), fill=col + (255,), anchor="mm", stroke_width=10, stroke_fill=LINE + (255,))
        flat = Image.new("RGB", im.size, (255, 255, 255))         # props load as white-background stickers
        flat.paste(im, (0, 0), im)
        flat.save(out / f"block_{L.lower()}.png")
