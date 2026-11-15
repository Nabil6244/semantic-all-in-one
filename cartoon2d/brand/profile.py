"""Channel profile picture: Ms Molly head-and-shoulders on a sunny rainbow disc, 800x800 PNG (YouTube shows it as a circle).

python3 cartoon2d/brand/profile.py
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cartoon2d"))
import rig  # noqa: E402

S = 800
src = Image.open(ROOT / "cartoon2d/cast/molly/source.png").convert("RGB")
cut = rig.cutout(src)
bust = cut.crop((95, 25, 675, 605))                       # hair top to chest, the whole curly hair inside
for name, ring in (("profile_molly", True), ("profile_molly_plain", False)):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, S - 1, S - 1], fill=(255, 236, 160, 255))
    if ring:                                               # rainbow rings behind her, like the playroom mural
        cols = [(255, 99, 99), (255, 165, 60), (255, 222, 70), (110, 205, 110), (90, 160, 245), (170, 120, 230)]
        for i, c in enumerate(cols):
            r = S * 0.47 - i * 22
            d.arc([S / 2 - r, S * 0.62 - r, S / 2 + r, S * 0.62 + r], 180, 360, fill=c + (255,), width=22)
        d.ellipse([S * 0.16, S * 0.20, S * 0.33, S * 0.29], fill=(255, 255, 255, 255))     # two little clouds
        d.ellipse([S * 0.66, S * 0.15, S * 0.83, S * 0.24], fill=(255, 255, 255, 255))
    b = bust.resize((int(S * 0.86), int(S * 0.86)), Image.LANCZOS)
    sh = Image.new("RGBA", b.size, (0, 0, 0, 0))
    sh.putalpha(b.getchannel("A").point(lambda v: v * 0.25))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), (int(S * 0.07) + 8, int(S * 0.16) + 12))
    im.alpha_composite(b, (int(S * 0.07), int(S * 0.16)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, S - 1, S - 1], fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    d2 = ImageDraw.Draw(out)
    d2.ellipse([6, 6, S - 7, S - 7], outline=(255, 255, 255, 255), width=12)
    p = ROOT / "cartoon2d/brand" / f"{name}.png"
    out.save(p)
    print("PROFILE", p)
