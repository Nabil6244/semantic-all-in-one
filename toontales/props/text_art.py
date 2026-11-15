"""Artwork for Toon Tales text props (PIL, outside Blender): signs, boards, newspapers, labels, letters,
bottle labels and maps. One PNG per (type, text), cached by content, then mapped onto a plane in Blender.

Library: text_art.make("sign", "SURE THING MINE", out_dir) -> Path to PNG (and its aspect w/h)
"""
import hashlib
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = Path("/System/Library/Fonts/Supplemental")
STYLE = {  # type: (size px, background, ink, font file, max chars per line)
    "sign":      ((1200, 520), (168, 118, 72), (40, 24, 16), "Rockwell.ttc", 14),
    "board":     ((1100, 760), (40, 52, 46), (236, 236, 226), "Chalkduster.ttf", 12),
    "newspaper": ((900, 1180), (232, 224, 204), (30, 26, 24), "Georgia Bold.ttf", 16),
    "label":     ((700, 420), (214, 186, 140), (48, 32, 24), "AmericanTypewriter.ttc", 12),
    "letter":    ((820, 1060), (240, 230, 206), (40, 36, 60), "Bradley Hand Bold.ttf", 18),
    "bottle":    ((800, 560), (236, 222, 186), (120, 30, 30), "Copperplate.ttc", 12),
    "map":       ((1100, 820), (222, 202, 160), (90, 50, 30), "Chalkduster.ttf", 16),
}


def _font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


def _fit(d, lines, fname, box_w, box_h, start=220):
    size = start
    while size > 20:
        f = _font(fname, size)
        ws = [d.textbbox((0, 0), ln, font=f) for ln in lines]
        w = max(b[2] - b[0] for b in ws)
        h = sum(b[3] - b[1] for b in ws) + size * 0.25 * (len(lines) - 1)
        if w <= box_w and h <= box_h:
            return f, ws
        size -= 6
    return _font(fname, 20), [d.textbbox((0, 0), ln, font=_font(fname, 20)) for ln in lines]


def _center_text(d, text, fname, box, ink, wrap, start=220):
    x0, y0, x1, y1 = box
    lines = textwrap.wrap(text, wrap) or [""]
    f, ws = _fit(d, lines, fname, x1 - x0, y1 - y0, start)
    gap = f.size * 0.25
    total = sum(b[3] - b[1] for b in ws) + gap * (len(lines) - 1)
    y = y0 + (y1 - y0 - total) / 2
    for ln, b in zip(lines, ws):
        w = b[2] - b[0]
        d.text((x0 + (x1 - x0 - w) / 2 - b[0], y - b[1]), ln, font=f, fill=ink)
        y += (b[3] - b[1]) + gap


def _grain(im, rnd, col, n=90, alpha=60):
    d = ImageDraw.Draw(im, "RGBA")
    w, h = im.size
    for _ in range(n):
        y = rnd.uniform(0, h)
        d.line([(0, y), (w, y + rnd.uniform(-20, 20))], fill=col + (alpha,), width=rnd.randint(1, 4))


def make(kind, text, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{kind}|{text}|v3".encode()).hexdigest()[:12]
    p = out / f"{kind}_{key}.png"
    if p.exists():
        return p
    (w, h), bg, ink, fname, wrap = STYLE[kind]
    rnd = random.Random(key)
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    text = text.strip()
    if kind == "sign":
        _grain(im, rnd, (110, 72, 40))
        for y in (h * 0.34, h * 0.67):
            d.line([(0, y), (w, y)], fill=(120, 80, 46), width=6)
        _center_text(d, text.upper(), fname, (60, 50, w - 60, h - 50), ink, wrap)
        for x, y in ((40, 40), (w - 40, 40), (40, h - 40), (w - 40, h - 40)):
            d.ellipse([x - 12, y - 12, x + 12, y + 12], fill=(60, 50, 44))
    elif kind == "board":
        d.rectangle([0, 0, w, h], outline=(120, 82, 48), width=44)
        for _ in range(40):  # chalk smudges
            x, y = rnd.uniform(60, w - 60), rnd.uniform(60, h - 60)
            d.ellipse([x - 60, y - 14, x + 60, y + 14], fill=(54, 66, 60))
        _center_text(d, text, fname, (90, 90, w - 90, h - 90), ink, wrap)
    elif kind == "newspaper":
        mast = _font("Didot.ttc", 72)
        d.text((w / 2, 70), "THE DAILY NUGGET", font=mast, fill=ink, anchor="mt")
        d.line([(40, 190), (w - 40, 190)], fill=ink, width=6)
        d.line([(40, 204), (w - 40, 204)], fill=ink, width=2)
        _center_text(d, text.upper(), fname, (50, 230, w - 50, 620), ink, wrap, start=150)
        for col in range(2):  # body text lines
            x0 = 50 + col * (w - 100) / 2 + 10
            for i in range(14):
                y = 680 + i * 32
                d.line([(x0, y), (x0 + (w - 140) / 2 - rnd.uniform(0, 60), y)], fill=(120, 112, 100), width=8)
    elif kind == "label":
        d.ellipse([w * 0.06, h / 2 - 22, w * 0.06 + 44, h / 2 + 22], fill=(120, 96, 70))
        _center_text(d, text.upper(), fname, (110, 40, w - 40, h - 40), ink, wrap)
    elif kind == "letter":
        for i in range(18):
            d.line([(40, 120 + i * 52), (w - 40, 120 + i * 52)], fill=(200, 196, 214), width=2)
        _center_text(d, text, fname, (70, 80, w - 70, h - 120), ink, wrap, start=110)
    elif kind == "bottle":
        d.rectangle([24, 24, w - 24, h - 24], outline=ink, width=10)
        _center_text(d, text.upper(), fname, (70, 70, w - 70, h - 70), ink, wrap)
    elif kind == "map":
        pts = [(90 + i * (w - 180) / 5, rnd.uniform(300, h - 90)) for i in range(6)]
        for a, b in zip(pts, pts[1:]):  # dashed trail
            for k in range(0, 10, 2):
                d.line([(a[0] + (b[0] - a[0]) * k / 10, a[1] + (b[1] - a[1]) * k / 10),
                        (a[0] + (b[0] - a[0]) * (k + 1) / 10, a[1] + (b[1] - a[1]) * (k + 1) / 10)], fill=ink, width=8)
        x, y = pts[-1]
        d.line([(x - 40, y - 40), (x + 40, y + 40)], fill=(170, 30, 30), width=16)
        d.line([(x - 40, y + 40), (x + 40, y - 40)], fill=(170, 30, 30), width=16)
        _center_text(d, text, fname, (60, 40, w - 60, 200), ink, wrap, start=90)
    im = im.filter(ImageFilter.SMOOTH)
    im.save(p)
    return p
