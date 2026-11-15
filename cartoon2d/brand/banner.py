"""Channel banner: 2560x1440, the playroom with the whole cast; name + tagline inside YouTube's 1546x423 safe area.

python3 cartoon2d/brand/banner.py   -> cartoon2d/brand/banner.png (+ banner_safe_check.png with the safe areas outlined)
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cartoon2d"))
import rig  # noqa: E402

W, H = 2560, 1440
SAFE = (W // 2 - 773, H // 2 - 212, W // 2 + 773, H // 2 + 212)        # visible on every device
FONT = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
bg = Image.open(ROOT / "cartoon2d/art/bg/playland.png").convert("RGB").resize((W, H), Image.LANCZOS).convert("RGBA")
haze = Image.new("RGBA", (W, H), (255, 255, 255, 60))                     # a touch lighter so the cast and text pop
bg.alpha_composite(haze)
# cast: small enough that heads sit inside the safe band; feet may run below it (only TVs show them)
cast = [("molly", 1.00, 0.505), ("lily", 0.72, 0.592), ("ollie", 0.65, 0.655), ("bobo", 0.92, 0.735)]
band_h = SAFE[3] - SAFE[1]
for who, rel, xf in cast:
    src = Image.open(ROOT / f"cartoon2d/cast/{who}/source.png").convert("RGB")
    cut = rig.cutout(src)
    cut = cut.crop(cut.getbbox())
    h = int(band_h * 1.32 * rel)
    im = cut.resize((int(cut.width * h / cut.height), h), Image.LANCZOS)
    x = int(W * xf - im.width / 2)
    y = SAFE[1] + int(band_h * 0.05) + int(band_h * 1.32 * (1 - rel))
    sh = Image.new("RGBA", (im.width, 40), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([im.width * 0.15, 5, im.width * 0.85, 35], fill=(40, 20, 40, 90))
    bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (x, y + h - 22))
    bg.alpha_composite(im, (x, y))
# name + tagline on the left of the safe area, on a soft cloud-white panel
d = ImageDraw.Draw(bg)
px0, py0 = SAFE[0] + 10, SAFE[1] + 55
d.rounded_rectangle([px0 + 10, py0 + 16, px0 + 640, py0 + 330], radius=60, fill=(0, 0, 0, 60))
d.rounded_rectangle([px0, py0, px0 + 630, py0 + 314], radius=60, fill=(255, 250, 230, 245))
f1, f2 = ImageFont.truetype(FONT, 150), ImageFont.truetype(FONT, 50)
cols = [(255, 80, 80), (255, 160, 30), (60, 170, 90), (50, 140, 240), (160, 90, 230), (255, 110, 170), (250, 190, 20)]
x = px0 + 45
for i, ch in enumerate("Ms Molly"):
    if ch.strip():
        d.text((x, py0 + 120), ch, font=f1, fill=cols[i % len(cols)] + (255,), anchor="lm", stroke_width=8, stroke_fill=(255, 255, 255, 255))
    x += f1.getlength(ch)
d.text((px0 + 315, py0 + 245), "Learn, sing & play!", font=f2, fill=(90, 60, 50, 255), anchor="mm")
out = ROOT / "cartoon2d/brand/banner.png"
bg.convert("RGB").save(out)
chk = bg.copy()
cd = ImageDraw.Draw(chk)
cd.rectangle(SAFE, outline=(255, 0, 0, 255), width=6)                       # phones + all devices
cd.rectangle((W // 2 - 1177, H // 2 - 212, W // 2 + 1177, H // 2 + 212), outline=(0, 0, 255, 255), width=4)   # desktop max
chk.convert("RGB").resize((1280, 720)).save(ROOT / "cartoon2d/brand/banner_safe_check.png")
print("BANNER", out)
