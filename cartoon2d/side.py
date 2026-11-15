"""Side view (profile) rig for walking and running: the upper body as one piece, and the legs cut at the hips so two copies
(near leg and a darker far leg) can swing in a walk cycle.

python3 cartoon2d/side.py <who> [hip_frac]   reads cast/<who>/side/source.png (facing right, white background)
                                             writes cast/<who>/side/{upper.png, leg.png, side.json, debug.png}
hip_frac = where the legs start, as a share of the figure height from the top of the head (defaults per character).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rig import cutout  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HIP = {"molly": 0.68, "lily": 0.74, "ollie": 0.80, "bobo": 0.76}
OVERLAP = 0.04


def build(who, hip_frac=None):
    d = ROOT / "cartoon2d" / "cast" / who / "side"
    rgba = cutout(Image.open(d / "source.png"))
    a = np.asarray(rgba.getchannel("A")) > 128
    ys, xs = np.nonzero(a)
    top, bot = int(ys.min()), int(ys.max())
    h = bot - top
    cut = int(top + h * (hip_frac or HIP.get(who, 0.7)))
    ov = int(h * OVERLAP)
    row = np.nonzero(a[cut])[0]
    hip = [float(row.mean()), float(cut)]
    feet_rows = a[bot - max(2, h // 30):bot + 1].any(0)
    fx = np.nonzero(feet_rows)[0]
    feet = [float(fx.mean()), float(bot)]
    W, H = rgba.size
    upper = rgba.copy()
    ua = np.asarray(upper.getchannel("A")).copy()
    ua[cut + 1:] = 0
    upper.putalpha(Image.fromarray(ua))
    leg = rgba.crop((0, cut - ov, W, H))
    upper.save(d / "upper.png")
    leg.save(d / "leg.png")
    info = {"size": [W, H], "top": top, "height": h, "hip": hip, "feet": feet, "leg_offset": [0, cut - ov],
            "leg_len": float(bot - cut)}
    (d / "side.json").write_text(json.dumps(info, indent=1) + "\n")
    dbg = Image.new("RGB", rgba.size, (200, 230, 255))
    dbg.paste(rgba, (0, 0), rgba)
    dr = ImageDraw.Draw(dbg)
    dr.line([(0, cut), (W, cut)], fill=(255, 0, 0), width=3)
    dr.ellipse([hip[0] - 8, hip[1] - 8, hip[0] + 8, hip[1] + 8], outline=(255, 0, 0), width=3)
    dr.ellipse([feet[0] - 8, feet[1] - 8, feet[0] + 8, feet[1] + 8], outline=(0, 0, 255), width=3)
    dbg.save(d / "debug.png")
    print("SIDE", who, info)


if __name__ == "__main__":
    build(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else None)
