"""Calm studio backdrops for the baby speech channel: a soft pastel wall, a light floor and a few gentle shapes at the
sides (the middle stays clear for the host's face, hands and the word picture).

python3 cartoon2d/baby_sets.py      -> cartoon2d/art/bg/baby_<name>.png (peach, mint, lavender, sky, lemon)
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "art" / "bg"
W, H = 1376, 768
SETS = {  # wall top, wall bottom, floor, shape colours
    "peach": ((255, 214, 196), (255, 232, 214), (255, 243, 232), [(255, 170, 150), (255, 200, 120), (250, 150, 180)]),
    "mint": ((190, 238, 218), (214, 246, 232), (238, 252, 244), [(120, 210, 170), (150, 200, 240), (250, 210, 120)]),
    "lavender": ((222, 208, 250), (236, 226, 252), (246, 240, 254), [(180, 150, 240), (250, 170, 210), (150, 200, 250)]),
    "sky": ((188, 226, 252), (214, 238, 254), (236, 247, 255), [(120, 180, 245), (255, 210, 110), (160, 220, 180)]),
    "lemon": ((255, 240, 180), (255, 246, 206), (255, 251, 232), [(250, 200, 80), (255, 160, 140), (140, 210, 160)]),
}
LINE = (120, 100, 90)


def _cloud(d, x, y, s, col):
    for dx, dy, r in ((0, 0, 1), (-0.9, 0.25, 0.7), (0.9, 0.25, 0.72), (0.45, -0.35, 0.75), (-0.45, -0.3, 0.68)):
        d.ellipse([x + dx * s - r * s, y + dy * s - r * s, x + dx * s + r * s, y + dy * s + r * s], fill=col)


def _star(d, x, y, r, col):
    pts = []
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.48
        pts.append((x + rr * math.cos(a), y - rr * math.sin(a)))
    d.polygon(pts, fill=col)


def make(name, top, bottom, floor, cols):
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    fy = int(H * 0.8)
    for y in range(fy):                                  # wall: soft vertical gradient
        q = y / fy
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * q) for a, b in zip(top, bottom)))
    d.rectangle([0, fy, W, H], fill=floor)               # floor and a soft skirting line
    d.rectangle([0, fy - 6, W, fy + 2], fill=tuple(max(0, c - 18) for c in bottom))
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    rnd = random.Random(name)
    for side in (0, 1):                                  # shapes only at the sides, faded
        for k in range(4):
            x = (rnd.uniform(0.04, 0.2) if side == 0 else rnd.uniform(0.8, 0.96)) * W
            y = rnd.uniform(0.1, 0.62) * H
            col = cols[(k + side) % len(cols)] + (120,)
            kind = (k + side) % 3
            if kind == 0:
                _cloud(dd, x, y, rnd.uniform(30, 46), (255, 255, 255, 170))
            elif kind == 1:
                _star(dd, x, y, rnd.uniform(26, 40), col)
            else:
                r = rnd.uniform(22, 36)
                dd.ellipse([x - r, y - r, x + r, y + r], fill=col)
    im.paste(deco.filter(ImageFilter.GaussianBlur(1.2)), (0, 0), deco.filter(ImageFilter.GaussianBlur(1.2)))
    im.save(OUT / f"baby_{name}.png")


if __name__ == "__main__":
    for n, v in SETS.items():
        make(n, *v)
        print("SET", OUT / f"baby_{n}.png")
