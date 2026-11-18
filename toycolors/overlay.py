"""2D overlay layer for Toy Vehicles Colours: big outlined titles, coloured numbers and comic burst lines.
Each function returns a transparent RGBA PIL image the size of the frame; composite it over a rendered frame.

    from toycolors import overlay as O
    O.title("5 RED BALLS", (230, 20, 15)).save("title.png")
    O.number(3, (250, 200, 10)).save("three.png")
    O.burst((250, 210, 20), center=(960, 600)).save("burst.png")
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from toycolors.paths import font as _font_path

FONT = _font_path()
W, H = 1920, 1080


def _font(size):
    return ImageFont.truetype(FONT, size)


def _lighter(c, k=0.45):
    return tuple(int(v + (255 - v) * k) for v in c)


def _darker(c, k=0.45):
    return tuple(int(v * (1 - k)) for v in c)


def _chunky_text(text, colour, size, pos, size_wh=(W, H), anchor="mm"):
    """Cartoon title text: drop shadow, dark outer outline, white outline, colour fill with a light top shine."""
    img = Image.new("RGBA", size_wh, (0, 0, 0, 0))
    f = _font(size)
    s = max(4, size // 14)
    # shadow
    sh = Image.new("RGBA", size_wh, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pos[0] + s, pos[1] + s * 1.3), text, font=f, anchor=anchor, fill=(0, 0, 0, 150),
                            stroke_width=s * 3, stroke_fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(s * 0.8)))
    d = ImageDraw.Draw(img)
    d.text(pos, text, font=f, anchor=anchor, fill=_darker(colour, 0.7) + (255,), stroke_width=s * 3,
           stroke_fill=_darker(colour, 0.7) + (255,))
    d.text(pos, text, font=f, anchor=anchor, fill=(255, 255, 255, 255), stroke_width=s * 2,
           stroke_fill=(255, 255, 255, 255))
    # fill with a vertical gradient: light shine on top, full colour below
    mask = Image.new("L", size_wh, 0)
    ImageDraw.Draw(mask).text(pos, text, font=f, anchor=anchor, fill=255)
    box = mask.getbbox()
    grad = Image.new("RGBA", size_wh, colour + (255,))
    if box:
        gd = ImageDraw.Draw(grad)
        top, bot = box[1], box[3]
        for y in range(top, bot + 1):
            k = (y - top) / max(1, bot - top)
            c = _lighter(colour, 0.5 * max(0.0, 0.55 - k) / 0.55) if k < 0.55 else _darker(colour, 0.18 * (k - 0.55) / 0.45)
            gd.line([(box[0], y), (box[2], y)], fill=c + (255,))
    img.paste(grad, (0, 0), mask)
    return img


def title(text, colour, y=110, size=110):
    """Big outlined title across the top of the frame, in the verse colour."""
    return _chunky_text(text.upper(), tuple(colour), size, (W // 2, y))


def number(n, colour, pos=(260, 430), size=380):
    """Huge counting number in the colour, at the side of the frame."""
    return _chunky_text(str(n), tuple(colour), size, pos)


def burst(colour, center=(W // 2, H // 2), r0=170, r1=330, seed=1):
    """Comic impact burst: jagged colour spikes with white speed strokes, like a cartoon 'pop'."""
    rng = random.Random(seed)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = center
    n = 16
    for i in range(n):
        a = 2 * math.pi * (i + rng.uniform(-0.2, 0.2)) / n
        ra, rb = r0 * rng.uniform(0.9, 1.1), r1 * rng.uniform(0.75, 1.15)
        w = rng.uniform(0.06, 0.1)
        pts = [(cx + math.cos(a - w) * ra, cy + math.sin(a - w) * ra), (cx + math.cos(a) * rb, cy + math.sin(a) * rb),
               (cx + math.cos(a + w) * ra, cy + math.sin(a + w) * ra)]
        d.polygon(pts, fill=tuple(colour) + (255,), outline=_darker(tuple(colour), 0.5) + (255,))
    for i in range(10):                                   # white curved speed strokes between spikes
        a = 2 * math.pi * (i + 0.5) / 10 + rng.uniform(-0.1, 0.1)
        r = rng.uniform(r0 * 1.05, r1 * 0.9)
        bb = [cx - r, cy - r, cx + r, cy + r]
        d.arc(bb, math.degrees(a) - 8, math.degrees(a) + 8, fill=(255, 255, 255, 255), width=7)
    return img


def compose(frame_path, layers, out_path):
    base = Image.open(frame_path).convert("RGBA")
    for L in layers:
        base.alpha_composite(L.resize(base.size, Image.LANCZOS) if L.size != base.size else L)
    base.convert("RGB").save(out_path, quality=95)
