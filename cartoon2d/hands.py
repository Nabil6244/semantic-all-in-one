"""Hand shapes (thumbs up, fist, pointing, open palm) for the cut-out cast, made once from Flow pictures.

Pictures: cartoon2d/art/hands/{human,bear}_{thumb,fist,point,open}.png  (a RIGHT hand, fingers up, wrist at the bottom).
rig.py calls add(cast_dir, rig, spec, src): each shape is cut out (stray motion lines dropped), recoloured to the
character's own skin / fur, sized to its hand and mirrored for the other side -> parts/hs_<shape>_<side>.png, and
rig["hand_shapes"][shape][side] = {file, wrist: [x, y] (bottom centre), w}.
"""
from pathlib import Path

import numpy as np
from PIL import Image

ART = Path(__file__).resolve().parent / "art" / "hands"
SHAPES = ("thumb", "fist", "point", "open")


def biggest(mask):
    """Keep the largest connected blob (the hand), drop the little motion lines around it."""
    from collections import deque
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    best, best_n, cur = 0, 0, 0
    ys, xs = np.nonzero(mask[::3, ::3])
    small = mask[::3, ::3]
    lab = np.zeros(small.shape, np.int32)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]:
            continue
        cur += 1
        q, n = deque([(y0, x0)]), 0
        lab[y0, x0] = cur
        while q:
            y, x = q.popleft(); n += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < small.shape[0] and 0 <= xx < small.shape[1] and small[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = cur; q.append((yy, xx))
        if n > best_n:
            best, best_n = cur, n
    keep = np.kron(lab == best, np.ones((3, 3), bool))[:h, :w]
    from PIL import ImageFilter
    keep = np.asarray(Image.fromarray(keep.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(7))) > 127
    return mask & keep


def add(cast_dir, rig, spec, cutout, bleed):
    kind = "bear" if spec.get("paw") else "human"
    if not all((ART / f"{kind}_{s}.png").exists() for s in SHAPES):
        return
    parts = Path(cast_dir) / "parts"
    rig["hand_shapes"] = {}
    for s in SHAPES:
        im = cutout(Image.open(ART / f"{kind}_{s}.png").convert("RGB"))
        a = np.asarray(im).copy()
        m = biggest(a[..., 3] > 40)
        a[..., 3] = (a[..., 3] * m).astype(np.uint8)
        ys, xs = np.nonzero(m)
        a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        rgb = a[..., :3].astype(float)
        lum = rgb.mean(-1)
        skin_px = (a[..., 3] > 200) & (lum > 120)
        out = {}
        for side in ("sl", "sr"):
            tgt = np.array(rig["arms"][side]["skin"], float)
            src = np.median(rgb[skin_px], 0)
            b = a.copy()
            k = np.clip(rgb * (tgt / np.maximum(src, 1))[None, None, :], 0, 255)
            b[..., :3] = np.where(skin_px[..., None], k, rgb).astype(np.uint8)          # skin / fur matched, outline kept
            img = Image.fromarray(b)
            hp = Image.open(parts / f"hand_{side}.png")
            want_w = max(hp.width * 1.2, rig["arms"][side]["fw"] * 1.6)
            f = want_w / img.width
            img = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))), Image.LANCZOS)
            if side == "sl":                                                           # the thumb toward the body
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            fn = f"parts/hs_{s}_{side}.png"
            bleed(img).save(Path(cast_dir) / fn)
            al = np.asarray(img)[..., 3] > 128                     # wrist = middle of the lowest band of the hand
            band = al[int(al.shape[0] * 0.93):]
            xs_ = np.nonzero(band.any(0))[0]
            wx = float(xs_.mean()) if len(xs_) else img.width / 2
            out[side] = {"file": fn, "wrist": [wx, img.height * 0.97], "w": img.width}
        rig["hand_shapes"][s] = out
