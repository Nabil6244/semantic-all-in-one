#!/usr/bin/env python3
"""Make the small placeholder pictures, sticker and clip used by samples/rich-media-kenya.json.

They are synthetic (gradients, shapes and a test pattern) so no third-party photo ships with the repo.
Real projects point `media` at their own photos, PNG stickers and clips.
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "samples" / "media"
OUT.mkdir(parents=True, exist_ok=True)
FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Montserrat-VF.ttf"


def font(px):
    try:
        f = ImageFont.truetype(str(FONT), px)
        f.set_variation_by_axes([800])
        return f
    except Exception:
        return ImageFont.load_default()


def photo(name, top, bottom, label, size=(840, 600)):
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(size[1]):
        t = y / (size[1] - 1)
        for x in range(size[0]):
            px[x, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t + 14 * ((x // 70 + y // 70) % 2)) for i in range(3))
    d = ImageDraw.Draw(im)
    d.ellipse([size[0] * 0.62, size[1] * 0.12, size[0] * 0.82, size[1] * 0.12 + size[0] * 0.2], fill=(255, 236, 170))
    d.polygon([(0, size[1]), (size[0] * 0.3, size[1] * 0.55), (size[0] * 0.55, size[1])], fill=tuple(int(c * 0.55) for c in bottom))
    d.text((24, size[1] - 70), label, fill=(255, 255, 255), font=font(40))
    im.save(OUT / name, quality=88)


photo("highlands.jpg", (120, 190, 235), (60, 140, 70), "PLACEHOLDER 1")
photo("city.jpg", (150, 190, 225), (90, 100, 110), "PLACEHOLDER 2")
photo("lake.jpg", (230, 160, 110), (40, 110, 150), "PLACEHOLDER 3")
photo("desert.jpg", (235, 190, 130), (190, 120, 60), "PLACEHOLDER 4")
photo("coast.jpg", (140, 200, 240), (30, 120, 170), "PLACEHOLDER 5")
photo("market.jpg", (200, 170, 120), (120, 80, 50), "PLACEHOLDER 6")

# a sticker: PNG with transparency, a little "mountain on a plinth" so the plinth acts as its own base
st = Image.new("RGBA", (500, 700), (0, 0, 0, 0))
d = ImageDraw.Draw(st)
d.ellipse([40, 560, 460, 680], fill=(236, 240, 245, 255), outline=(180, 190, 200, 255), width=6)
d.polygon([(90, 600), (250, 150), (410, 600)], fill=(150, 98, 60, 255))
d.polygon([(250, 150), (200, 300), (250, 270), (300, 300)], fill=(250, 250, 250, 255))
d.ellipse([310, 90, 390, 170], fill=(255, 214, 90, 255))
st.save(OUT / "sticker.png")

# a 3 s clip (test pattern) for the full-screen interlude and a video card
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=3", "-pix_fmt", "yuv420p", str(OUT / "clip.mp4")], check=True)
print("wrote", sorted(p.name for p in OUT.iterdir()))
