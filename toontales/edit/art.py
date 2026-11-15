"""Toon Tales edit art (PIL): one-word captions and story overlays as transparent full-frame PNGs, cached.

caption(word, size, pop=False) -> PNG: bold white word, thick black outline, centred ~70% down the frame.
overlay({"type": "chalk"|"arrow"|"circle"|"stamp"|"label"|"cross", "text": ...}, size) -> PNG in the top half.
"""
import hashlib
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TT = Path(__file__).resolve().parents[1]
OUT = TT / "build" / "edit_art"
FONTS = Path("/System/Library/Fonts/Supplemental")
CAPTION_Y = 0.70
CHALK_Y = 0.085                    # chalk and stamps sit above the heads (they covered faces at 0.24-0.3)
STAMP_Y = 0.095
VERSION = "v4"
HOT = (255, 214, 40, 255)          # key words (numbers, money, names the plan marks) pop in yellow


def _font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


def _key(*parts):
    return hashlib.sha1("|".join(map(str, parts + (VERSION,))).encode()).hexdigest()[:14]


def clean_word(w):
    return w.strip().strip(",.;:!?\"“”()—–-…").replace("’", "'")


def caption(word, size, pop=False, hot=False):
    W, H = size
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"cap_{_key(word, W, H, pop, hot)}.png"
    if p.exists():
        return p
    s = W / 1080
    fs = int((128 if pop else 112) * s * (1.25 if hot else 1.0))
    f = _font("Arial Black.ttf", fs)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    text = clean_word(word)
    while d.textbbox((0, 0), text, font=f)[2] > W * 0.88 and fs > 40:
        fs -= 6
        f = _font("Arial Black.ttf", fs)
    cx, cy = W / 2, H * CAPTION_Y
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # soft drop shadow
    ImageDraw.Draw(sh).text((cx + 6 * s, cy + 9 * s), text, font=f, anchor="mm", fill=(0, 0, 0, 150),
                            stroke_width=int(14 * s), stroke_fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6 * s)))
    d.text((cx, cy), text, font=f, anchor="mm", fill=HOT if hot else (255, 255, 255, 255), stroke_width=int(13 * s),
           stroke_fill=(10, 8, 8, 255))
    if hot:
        im = im.rotate(-3, resample=Image.BICUBIC, center=(cx, cy))
    im.save(p)
    return p


def _wrap(d, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textbbox((0, 0), t, font=f)[2] > maxw and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + [cur] if cur else lines


def title(text, size):
    """Hook title card for the first ~1.7 s: big black words on a tilted yellow slab, top third."""
    W, H = size
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"title_{_key(text, W, H)}.png"
    if p.exists():
        return p
    s = W / 1080
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = _font("Arial Black.ttf", int(104 * s))
    lines = _wrap(d, text.upper(), f, W * 0.8)
    lh = int(122 * s)
    cy0 = H * 0.17 - (len(lines) - 1) * lh / 2
    widest = max(d.textbbox((0, 0), ln, font=f)[2] for ln in lines)
    pad = 40 * s
    d.rounded_rectangle([W / 2 - widest / 2 - pad, cy0 - lh / 2 - pad * 0.6, W / 2 + widest / 2 + pad,
                         cy0 + (len(lines) - 0.5) * lh + pad * 0.6], radius=int(26 * s), fill=HOT,
                        outline=(10, 8, 8, 255), width=int(10 * s))
    for i, ln in enumerate(lines):
        d.text((W / 2, cy0 + i * lh), ln, font=f, anchor="mm", fill=(14, 10, 8, 255))
    layer = layer.rotate(2.5, resample=Image.BICUBIC, center=(W / 2, H * 0.17))
    im.alpha_composite(layer)
    im.save(p)
    return p


def freeze_text(text, size):
    """Pattern-break card on a freeze frame: huge white word with a red outline, centre of the frame."""
    W, H = size
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"frz_{_key(text, W, H)}.png"
    if p.exists():
        return p
    s = W / 1080
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font("Impact.ttf", int(230 * s))
    d.text((W / 2, H * 0.42), text.upper(), font=f, anchor="mm", fill=(255, 255, 255, 255),
           stroke_width=int(16 * s), stroke_fill=(200, 24, 30, 255))
    im = im.rotate(-6, resample=Image.BICUBIC, center=(W / 2, H * 0.42))
    im.save(p)
    return p


def _chalk(d, xy, text, f, rnd, fill=(246, 246, 240, 255)):
    d.text(xy, text, font=f, anchor="mm", fill=fill)


def _roughen(im, rnd, amount=0.18):
    """Chalk texture: knock random specks out of the strokes."""
    px = im.load()
    W, H = im.size
    for _ in range(int(W * H * 0.004 * amount)):
        x, y = rnd.randrange(W), rnd.randrange(H)
        r, g, b, a = px[x, y]
        if a:
            px[x, y] = (r, g, b, int(a * rnd.uniform(0.0, 0.5)))
    return im


def _hand_line(d, pts, fill, w, rnd, jitter=3.0):
    pts = [(x + rnd.uniform(-jitter, jitter), y + rnd.uniform(-jitter, jitter)) for x, y in pts]
    d.line(pts, fill=fill, width=int(w), joint="curve")


def overlay(ov, size):
    W, H = size
    OUT.mkdir(parents=True, exist_ok=True)
    kind, text = ov.get("type"), str(ov.get("text", "")).strip()
    p = OUT / f"ov_{_key(kind, text, W, H)}.png"
    if p.exists():
        return p
    s = W / 1080
    rnd = random.Random(_key(kind, text))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == "chalk":
        f = _font("Chalkduster.ttf", int(120 * s))
        while d.textbbox((0, 0), text, font=f)[2] > W * 0.85 and f.size > 40:
            f = _font("Chalkduster.ttf", f.size - 8)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        _chalk(ImageDraw.Draw(layer), (W / 2, H * CHALK_Y), text, f, rnd)
        bb = layer.getbbox()
        if bb:  # chalk underline
            _hand_line(ImageDraw.Draw(layer), [(bb[0], bb[3] + 24 * s), ((bb[0] + bb[2]) / 2, bb[3] + 30 * s),
                                               (bb[2], bb[3] + 20 * s)], (246, 246, 240, 255), 10 * s, rnd)
        layer = layer.rotate(rnd.uniform(-5, 5), resample=Image.BICUBIC, center=(W / 2, H * CHALK_Y))
        # soft dark halo so white chalk reads on white heads and bright walls
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        halo.putalpha(layer.getchannel("A").filter(ImageFilter.MaxFilter(int(9 * s) | 1)).filter(ImageFilter.GaussianBlur(14 * s)))
        halo = Image.composite(Image.new("RGBA", (W, H), (20, 16, 14, 255)), halo, halo.getchannel("A").point(lambda v: min(255, v * 2)))
        halo.putalpha(halo.getchannel("A").point(lambda v: int(v * 0.75)))
        im.alpha_composite(halo)
        im.alpha_composite(_roughen(layer, rnd))
    elif kind == "arrow":
        col = (255, 214, 64, 255)
        x0, y0, x1, y1 = W * 0.72, H * 0.16, W * 0.56, H * 0.36
        pts = [(x0 + (x1 - x0) * t + math.sin(t * 3.1) * 30 * s, y0 + (y1 - y0) * t) for t in [i / 12 for i in range(13)]]
        _hand_line(d, pts, (20, 14, 10, 255), 30 * s, rnd, 0)
        _hand_line(d, pts, col, 18 * s, rnd, 0)
        ang = math.atan2(y1 - pts[-2][1], x1 - pts[-2][0])
        for a in (ang + 2.5, ang - 2.5):
            tip = [(x1, y1), (x1 + math.cos(a) * 70 * s, y1 + math.sin(a) * 70 * s)]
            d.line(tip, fill=(20, 14, 10, 255), width=int(30 * s))
            d.line(tip, fill=col, width=int(18 * s))
        if text:
            f = _font("Arial Black.ttf", int(84 * s))
            d.text((x0, y0 - 60 * s), text, font=f, anchor="mm", fill=col, stroke_width=int(9 * s),
                   stroke_fill=(20, 14, 10, 255))
    elif kind == "circle":
        cx, cy, rx, ry = W / 2, H * 0.42, W * 0.3, H * 0.12
        pts = [(cx + rx * math.cos(a) * rnd.uniform(0.97, 1.03), cy + ry * math.sin(a) * rnd.uniform(0.97, 1.03))
               for a in [i / 40 * 2.15 * math.pi for i in range(41)]]
        _hand_line(d, pts, (220, 40, 36, 255), 16 * s, rnd, 1)
        if text:
            f = _font("Arial Black.ttf", int(80 * s))
            d.text((cx, cy - ry - 70 * s), text, font=f, anchor="mm", fill=(255, 255, 255, 255),
                   stroke_width=int(9 * s), stroke_fill=(220, 40, 36, 255))
    elif kind == "stamp":
        f = _font("Impact.ttf", int(140 * s))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        bb = ld.textbbox((W / 2, H * STAMP_Y), text or "FAKE", font=f, anchor="mm")
        pad = 34 * s
        ld.rounded_rectangle([bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad], radius=int(20 * s),
                             outline=(206, 30, 36, 255), width=int(16 * s))
        ld.text((W / 2, H * STAMP_Y), text or "FAKE", font=f, anchor="mm", fill=(206, 30, 36, 255))
        layer = layer.rotate(rnd.uniform(-14, -8), resample=Image.BICUBIC, center=(W / 2, H * STAMP_Y))
        im.alpha_composite(_roughen(layer, rnd, 0.6))
    elif kind == "label":
        f = _font("Arial Black.ttf", int(88 * s))
        while d.textbbox((0, 0), text, font=f)[2] > W * 0.82 and f.size > 36:
            f = _font("Arial Black.ttf", f.size - 6)
        bb = d.textbbox((W / 2, H * 0.15), text, font=f, anchor="mm")
        pad = 30 * s
        d.rounded_rectangle([bb[0] - pad, bb[1] - pad * 0.8, bb[2] + pad, bb[3] + pad * 0.8], radius=int(22 * s),
                            fill=(24, 18, 16, 230), outline=(255, 206, 64, 255), width=int(6 * s))
        d.text((W / 2, H * 0.15), text, font=f, anchor="mm", fill=(255, 214, 64, 255))
    elif kind == "cross":
        c = (220, 40, 36, 235)
        for a, b in (((0.22, 0.2), (0.78, 0.5)), ((0.78, 0.2), (0.22, 0.5))):
            _hand_line(d, [(W * a[0], H * a[1]), (W * (a[0] + b[0]) / 2, H * (a[1] + b[1]) / 2), (W * b[0], H * b[1])],
                       c, 40 * s, rnd, 6)
        if text:
            f = _font("Arial Black.ttf", int(80 * s))
            d.text((W / 2, H * 0.14), text, font=f, anchor="mm", fill=(255, 255, 255, 255), stroke_width=int(9 * s),
                   stroke_fill=c)
    im.save(p)
    return p
