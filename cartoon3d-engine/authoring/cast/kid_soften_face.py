"""Friendlier kid skin: red eyelid rims and red nose taken back to clean skin, cheek redness softened to a light blush.
Positions are on the 2048 CC head diffuse (shown as 1024 coordinates). Run: python3 cast/kid_soften_face.py <in> <out>
"""
import sys

import numpy as np
from PIL import Image

src, dst = sys.argv[1:3]
img = Image.open(src).convert("RGB")
a = np.asarray(img).astype(np.float32) / 255.0
H, W, _ = a.shape
k = W / 1024.0
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
LUM = np.array([0.299, 0.587, 0.114], np.float32)


def ellipse(cx, cy, rx, ry, soft=0.5):
    d = np.sqrt(((xx - cx * k) / (rx * k)) ** 2 + ((yy - cy * k) / (ry * k)) ** 2)
    return np.clip((1 - d) / soft, 0, 1)


skin = a[int(300 * k) - 8:int(300 * k) + 8, int(330 * k) - 8:int(330 * k) + 8].reshape(-1, 3).mean(0)   # clean temple skin
skin_l = float(skin @ LUM)
lum = (a @ LUM)[..., None]
clean = np.clip(skin * (0.35 + 0.65 * lum / skin_l), 0, 1)     # skin colour, keeping a little of the local light/dark
out = a.copy()
for cx, cy, rx, ry, s in ((425, 356, 62, 34, 0.85), (592, 356, 62, 34, 0.85),      # eyelids
                          (510, 412, 42, 42, 0.7),                                  # nose
                          (432, 432, 55, 45, 0.45), (594, 432, 55, 45, 0.45),      # cheeks: keep a light blush
                          (512, 482, 58, 20, 0.8)):                                # pale patch above the upper lip
    m = (ellipse(cx, cy, rx, ry) * s)[..., None]
    out = out * (1 - m) + clean * m
Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(dst, quality=95)
print("saved", dst)
