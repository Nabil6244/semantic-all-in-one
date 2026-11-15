"""Friendly face texture for the adult lead: dark smoky eyeshadow painted out to soft skin, a little natural lid warmth kept,
bold lipstick softened to a warm rose. Positions are on the 2048 CC head diffuse (Std_Skin_Head_Diffuse).
Run: python3 cast/soften_face.py <in.png> <out.png>
"""
import sys

import numpy as np
from PIL import Image, ImageFilter

src, dst = sys.argv[1:3]
img = Image.open(src).convert("RGB")
a = np.asarray(img).astype(np.float32) / 255.0
H, W, _ = a.shape
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
k = W / 1024.0


def ellipse(cx, cy, rx, ry, soft=0.35):
    d = np.sqrt(((xx - cx * k) / (rx * k)) ** 2 + ((yy - cy * k) / (ry * k)) ** 2)
    return np.clip((1 - d) / soft, 0, 1)


# skin tone to paint with: blurred copy of the face, sampled from just below each eye (cheek) and shifted up
blur = np.asarray(img.filter(ImageFilter.GaussianBlur(18 * k))).astype(np.float32) / 255.0
lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
out = a.copy()
for cx in (422, 603):
    cy = 362
    m = ellipse(cx, cy, 82, 52)
    skin = blur[int((cy + 62) * k), int(cx * k)]
    skin_l = float(skin @ np.array([0.299, 0.587, 0.114]))
    dark = np.clip(np.abs(skin_l - lum) / (0.55 * skin_l), 0, 1)    # how far from skin (dark shadow or pale highlight)
    w = (m * np.clip(dark * 1.4, 0, 1))[..., None]
    lid = skin * np.array([0.97, 0.93, 0.92], np.float32)            # a touch of natural warmth on the lid
    out = out * (1 - w) + lid * w

# lips: from bold magenta to a soft warm rose
m = ellipse(512, 522, 70, 40, 0.5)[..., None]
lum2 = (out @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
rose_c = np.array([0.86, 0.47, 0.46], np.float32)
rose = rose_c * (lum2 / float(rose_c @ np.array([0.299, 0.587, 0.114])))
out = out * (1 - m * 0.75) + np.clip(rose, 0, 1) * (m * 0.75)
Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(dst)
print("saved", dst)
