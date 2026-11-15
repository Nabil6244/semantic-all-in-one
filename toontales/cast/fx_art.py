"""Toon Tales reaction sprites (PIL, made once outside Blender): sweat, anger, burst, sparkle, speed, question, stars.

Run: python3 toontales/cast/fx_art.py <out dir>     (build_story calls it when this file changes)
Ink and colours match the faces: dark-brown outline, flat fills, transparent background, 512 px squares.
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

INK = (40, 26, 20, 255)
S = 512


def _canvas():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def sweat():
    im = _canvas()
    d = ImageDraw.Draw(im)
    for cx, cy, r in ((300, 230, 62), (200, 340, 44)):
        pts = [(cx, cy - r * 2.0)] + [(cx + r * math.cos(a), cy + r * math.sin(a))
                                       for a in [math.radians(x) for x in range(-20, 201, 10)]]
        d.polygon(pts, fill=(150, 210, 255, 255), outline=INK, width=14)
        d.ellipse([cx - r * 0.45, cy - r * 0.2, cx - r * 0.1, cy + r * 0.25], fill=(255, 255, 255, 230))
    return im


def anger():
    im = _canvas()
    d = ImageDraw.Draw(im)
    c = (230, 40, 40, 255)
    for ang in (45, 135, 225, 315):  # four bent ticks: the cartoon vein mark
        a = math.radians(ang)
        x0, y0 = S / 2 + math.cos(a) * 70, S / 2 + math.sin(a) * 70
        x1, y1 = S / 2 + math.cos(a) * 190, S / 2 + math.sin(a) * 190
        bend = (x0 + math.cos(a + 1.2) * 60, y0 + math.sin(a + 1.2) * 60)
        d.line([(x0, y0), bend, (x1, y1)], fill=INK, width=58, joint="curve")
        d.line([(x0, y0), bend, (x1, y1)], fill=c, width=34, joint="curve")
    return im


def burst():
    im = _canvas()
    d = ImageDraw.Draw(im)
    for k in range(12):
        a = 2 * math.pi * k / 12
        r0, r1 = 150, 240 if k % 2 == 0 else 205
        p = [(S / 2 + math.cos(a) * r0, S / 2 + math.sin(a) * r0), (S / 2 + math.cos(a) * r1, S / 2 + math.sin(a) * r1)]
        d.line(p, fill=INK, width=26)
        d.line(p, fill=(255, 230, 80, 255), width=12)
    return im


def sparkle():
    im = _canvas()
    d = ImageDraw.Draw(im)
    for cx, cy, r in ((150, 150, 90), (370, 220, 70), (230, 380, 55)):
        pts = []
        for k in range(8):
            a = math.pi / 4 * k - math.pi / 2
            rr = r if k % 2 == 0 else r * 0.32
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        d.polygon(pts, fill=(255, 220, 60, 255), outline=INK, width=10)
    return im


def speed():
    im = _canvas()
    d = ImageDraw.Draw(im)
    for k, (y, x0) in enumerate(((120, 80), (200, 30), (280, 110), (360, 50), (430, 140))):
        d.line([(x0, y), (S - 40, y)], fill=(255, 255, 255, 235), width=18 if k % 2 else 26)
        d.line([(x0, y), (S - 40, y)], fill=INK, width=4)
    return im


def question():
    im = _canvas()
    d = ImageDraw.Draw(im)
    d.arc([140, 60, 370, 290], 180, 60, fill=INK, width=70)
    d.arc([140, 60, 370, 290], 180, 60, fill=(255, 255, 255, 255), width=40)
    d.line([(300, 270), (256, 330), (256, 360)], fill=INK, width=70)
    d.line([(300, 270), (256, 330), (256, 360)], fill=(255, 255, 255, 255), width=40)
    d.ellipse([216, 400, 296, 480], fill=(255, 255, 255, 255), outline=INK, width=14)
    return im


def stars():
    im = _canvas()
    d = ImageDraw.Draw(im)
    for k in range(4):
        a = 2 * math.pi * k / 4
        cx, cy, r = S / 2 + math.cos(a) * 170, S / 2 + math.sin(a) * 70, 52
        pts = [(cx + math.cos(math.pi / 2.5 * j - math.pi / 2) * (r if j % 2 == 0 else r * 0.45),
                cy + math.sin(math.pi / 2.5 * j - math.pi / 2) * (r if j % 2 == 0 else r * 0.45)) for j in range(10)]
        d.polygon([pts[(j * 1) % 10] for j in range(10)], fill=(255, 230, 80, 255), outline=INK, width=8)
    return im


SPRITES = {"sweat": sweat, "anger": anger, "burst": burst, "sparkle": sparkle, "speed": speed,
           "question": question, "stars": stars}


def build(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in SPRITES.items():
        fn().save(out / f"{name}.png")


if __name__ == "__main__":
    build(sys.argv[1])
