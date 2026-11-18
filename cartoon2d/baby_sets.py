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
    "rose": ((255, 206, 216), (255, 226, 232), (255, 242, 246), [(250, 150, 170), (255, 200, 120), (170, 200, 250)]),
    "aqua": ((186, 236, 240), (212, 246, 248), (236, 252, 252), [(110, 200, 210), (255, 190, 120), (170, 220, 150)]),
    "apricot": ((255, 222, 180), (255, 236, 206), (255, 246, 230), [(250, 180, 110), (150, 200, 240), (240, 150, 170)]),
    "lilac": ((232, 214, 244), (242, 230, 250), (250, 244, 254), [(200, 160, 230), (255, 190, 200), (150, 210, 200)]),
    "cream": ((252, 240, 214), (254, 246, 230), (255, 251, 242), [(230, 190, 120), (170, 210, 160), (240, 160, 150)]),
    "pistachio": ((214, 238, 196), (230, 246, 218), (244, 252, 238), [(150, 210, 120), (255, 200, 130), (160, 190, 245)]),
    "coral": ((255, 200, 186), (255, 222, 212), (255, 240, 234), [(250, 140, 120), (255, 210, 110), (130, 200, 200)]),
    "periwinkle": ((206, 214, 252), (224, 230, 254), (242, 245, 255), [(140, 160, 240), (250, 190, 210), (170, 220, 170)]),
    "butter": ((255, 236, 170), (255, 244, 200), (255, 250, 228), [(245, 205, 90), (240, 150, 140), (150, 200, 230)]),
    "blush": ((250, 214, 226), (252, 230, 238), (254, 244, 248), [(240, 160, 190), (180, 160, 240), (250, 210, 130)]),
    "seafoam": ((196, 240, 226), (218, 248, 238), (240, 253, 248), [(110, 210, 180), (250, 180, 150), (160, 180, 245)]),
    "honeydew": ((226, 246, 200), (238, 250, 220), (248, 254, 240), [(170, 220, 120), (250, 170, 190), (140, 200, 240)]),
    "sand": ((246, 228, 200), (250, 238, 218), (253, 248, 238), [(230, 180, 130), (140, 200, 220), (240, 150, 160)]),
    "bluebell": ((200, 220, 250), (220, 234, 254), (240, 246, 255), [(130, 170, 240), (255, 200, 120), (240, 160, 200)]),
    "melon": ((255, 214, 200), (255, 230, 220), (255, 244, 238), [(250, 160, 140), (150, 210, 170), (180, 170, 245)]),
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
    # shapes only at the sides, faded, and low on the wall just above the floor (owner, 2026-11-17: stars, circles and clouds high on
    # the wall peeked out from behind the word picture and word cards in the face close-ups; the cards live in the upper wall)
    for side in (0, 1):
        for k in range(3):
            x = (rnd.uniform(0.03, 0.17) if side == 0 else rnd.uniform(0.83, 0.97)) * W
            y = rnd.uniform(0.55, 0.6) * H
            col = cols[(k + side) % len(cols)] + (120,)
            kind = (k + side) % 3
            if kind == 0:
                _cloud(dd, x, y, rnd.uniform(22, 32), (255, 255, 255, 170))
            elif kind == 1:
                _star(dd, x, y, rnd.uniform(20, 30), col)
            else:
                r = rnd.uniform(16, 26)
                dd.ellipse([x - r, y - r, x + r, y + r], fill=col)
    im.paste(deco.filter(ImageFilter.GaussianBlur(1.2)), (0, 0), deco.filter(ImageFilter.GaussianBlur(1.2)))
    im.save(OUT / f"baby_{name}.png")


if __name__ == "__main__":
    for n, v in SETS.items():
        make(n, *v)
        print("SET", OUT / f"baby_{n}.png")
