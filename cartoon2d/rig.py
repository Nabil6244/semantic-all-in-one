"""Cut one full-body cartoon picture (white background) into a 2D cut-out rig.

python3 cartoon2d/rig.py cartoon2d/cast/<name>       (reads source.png + spec.json, writes parts/*.png + rig.json + debug.png)

spec.json (all points in source.png pixels):
  neck [x, y]            head pivot; the head part is everything above `neck_y` (plus a small overlap)
  head_box [x0,y0,x1,y1] where the head is (hair included) - limits the head cut
  arms: {"sl": {...}, "sr": {...}}   sl = screen-left (the character's right arm), sr = screen-right
      poly  [[x,y],...]  loose outline around the whole arm + hand; only its shoulder edge must be exact
      shoulder [x,y]     pivot of the upper arm
      elbow [x,y]        pivot of the forearm
      sleeve [x,y]       colour sample for the shoulder cap; elbow_skin [x,y] for the elbow cap
  mouth {"c": [x,y], "w": px, "h": px}   the drawn mouth (replaced while talking)
  eyes [[cx,cy,rx,ry], ...]               the eye openings (covered for blinks)
  skin [x,y]   cheek colour sample; line [x,y] outline colour sample
  feet [x,y]   ground point (centre between the shoes)
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def cutout(img, thresh=238):
    """White background -> alpha: flood from the border through near-white pixels, so white inside the character
    (eyes, socks, shoes) stays solid."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    h, w = a.shape[:2]
    white = (a.min(2) >= thresh) & (a.max(2) - a.min(2) < 18)
    bg = np.zeros((h, w), bool)
    seed = np.zeros((h, w), bool)
    seed[0, :] = seed[-1, :] = True
    seed[:, 0] = seed[:, -1] = True
    seed &= white
    bg |= seed
    # iterative flood fill on a numpy grid (fast enough for ~2k images: dilate within `white` until stable)
    while True:
        grown = bg.copy()
        grown[1:, :] |= bg[:-1, :]
        grown[:-1, :] |= bg[1:, :]
        grown[:, 1:] |= bg[:, :-1]
        grown[:, :-1] |= bg[:, 1:]
        grown &= white
        if (grown == bg).all():
            break
        bg = grown
    alpha = Image.fromarray(((~bg) * 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))   # trim the white halo, soft edge
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return out


def _box(x, r):
    """Box sum over a (2r+1)^2 window (edges clamped), numpy only."""
    p = np.pad(x, ((r + 1, r), (r + 1, r)) + ((0, 0),) * (x.ndim - 2), mode="edge")
    c = p.cumsum(0).cumsum(1)
    return c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]


def bleed(rgba):
    """Copy edge colours into transparent pixels so scaling/rotating never pulls white or black into the outline."""
    a = np.asarray(rgba).copy()
    m = (a[..., 3] > 8).astype(np.float64)
    acc = a[..., :3].astype(np.float64) * m[..., None]
    wsum = m.copy()
    for _ in range(4):
        acc, wsum = _box(acc, 2), _box(wsum, 2)
    fill = acc / np.maximum(wsum[..., None], 1e-9)
    hole = a[..., 3] <= 8
    a[..., :3][hole] = np.clip(fill[hole], 0, 255).astype(np.uint8)
    return Image.fromarray(a)


def poly_mask(size, pts):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in pts], fill=255)
    return np.asarray(m) > 127


def side_of(p, a, b):
    """>0 on one side of line a->b for each pixel grid point p (h,w,2)."""
    return (b[0] - a[0]) * (p[..., 1] - a[1]) - (b[1] - a[1]) * (p[..., 0] - a[0])


def crop_part(rgba, mask, pad=4):
    ys, xs = np.nonzero(mask)
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(rgba.width, xs.max() + pad + 1), min(rgba.height, ys.max() + pad + 1)
    a = np.asarray(rgba).copy()
    a[..., 3] = (a[..., 3] * mask).astype(np.uint8)
    part = Image.fromarray(a[y0:y1, x0:x1])
    return part, (int(x0), int(y0))


def width_at(mask, p, d):
    """Width of the mask across direction d (unit) at point p: walk both ways along the normal."""
    n = (-d[1], d[0])
    h, w = mask.shape
    tot = 0
    for sgn in (1, -1):
        k = 0
        while k < 400:
            x, y = int(round(p[0] + sgn * n[0] * k)), int(round(p[1] + sgn * n[1] * k))
            if not (0 <= x < w and 0 <= y < h) or not mask[y, x]:
                break
            k += 1
        tot += k
    return tot


def mid_at(mask, p, d):
    """Centre of the mask's cross-section through p, across direction d."""
    n = (-d[1], d[0])
    h, w = mask.shape
    ext = []
    for sgn in (1, -1):
        k = 0
        while k < 400:
            x, y = int(round(p[0] + sgn * n[0] * (k + 1))), int(round(p[1] + sgn * n[1] * (k + 1)))
            if not (0 <= x < w and 0 <= y < h) or not mask[y, x]:
                break
            k += 1
        ext.append(sgn * k)
    m = (ext[0] + ext[1]) / 2
    return [float(p[0] + n[0] * m), float(p[1] + n[1] * m)]


def sample(img, p, r=3):
    a = np.asarray(img.convert("RGB"))[int(p[1]) - r:int(p[1]) + r + 1, int(p[0]) - r:int(p[0]) + r + 1]
    return tuple(int(v) for v in np.median(a.reshape(-1, 3), 0))


def build(cast_dir):
    cast_dir = Path(cast_dir)
    spec = json.loads((cast_dir / "spec.json").read_text())
    src = Image.open(cast_dir / "source.png").convert("RGB")
    rgba = cutout(src)
    W, H = rgba.size
    alpha = np.asarray(rgba)[..., 3] > 40
    yy, xx = np.mgrid[0:H, 0:W]
    grid = np.stack([xx, yy], -1).astype(np.float32)
    parts_dir = cast_dir / "parts"
    parts_dir.mkdir(exist_ok=True)
    rig = {"size": [W, H], "feet": spec["feet"], "neck": spec["neck"], "parts": {}, "mouth": spec["mouth"], "eyes": spec["eyes"],
           "skin": sample(src, spec["skin"]), "line": spec.get("line_rgb") or sample(src, spec["line"], 1)}
    body = alpha.copy()
    for side, arm in spec["arms"].items():
        am = poly_mask((W, H), arm["poly"]) & alpha
        body &= ~am
        sh = arm["shoulder"]
        d = np.array(arm["elbow"], float) - np.array(sh, float)
        d /= np.linalg.norm(d)
        el = mid_at(am, arm["elbow"], d)                                # joints on the arm's centre line
        d2 = np.array(arm["wrist"], float) - np.array(el, float)
        d2 /= np.linalg.norm(d2)
        wr = mid_at(am, arm["wrist"], d2)
        se = arm["sleeve_end"]
        # the arm is drawn as smooth tubes (sleeve + skin) at render time; only the hand is cut from the picture
        along = (grid[..., 0] - wr[0]) * d2[0] + (grid[..., 1] - wr[1]) * d2[1]
        hand = am & (along > -4)
        p_, off = crop_part(rgba, hand)
        bleed(p_).save(parts_dir / f"hand_{side}.png")
        rig["parts"][f"hand_{side}"] = {"file": f"parts/hand_{side}.png", "offset": off, "pivot": wr}
        mid_up = [(se[0] + el[0]) / 2, (se[1] + el[1]) / 2]
        mid_fo = [el[0] + (wr[0] - el[0]) * 0.75, el[1] + (wr[1] - el[1]) * 0.75]
        mid_sl = [(sh[0] + se[0]) / 2, (sh[1] + se[1]) / 2]
        rig.setdefault("arms", {})[side] = {
            "S": [float(v) for v in sh], "E": el, "W": wr, "SE": [float(v) for v in se],
            "uw": width_at(am, mid_up, d), "fw": width_at(am, mid_fo, d2), "sw": width_at(am, mid_sl, d),
            "skin": sample(src, arm.get("elbow_skin", el)), "sleeve": sample(src, arm["sleeve"])}
    # head: above the neck line inside the head box, with a 14 px feathered overlap below it
    nx, ny = spec["neck"]
    hb = spec["head_box"]
    cut = spec.get("head_cut") or [[0, ny], [W, ny]]                 # polyline: the head is everything above it
    cx_, cy_ = zip(*sorted(cut))
    cut_y = np.interp(np.arange(W), cx_, cy_)[None, :]
    nw = spec.get("neck_w", 60)
    near_neck = np.abs(xx - nx) < nw
    above = yy < cut_y
    head_m = body & (above | (near_neck & (yy < cut_y + 14))) & (xx >= hb[0]) & (xx <= hb[2]) & (yy >= hb[1])
    body_wo_head = body & ~(head_m & above)
    hp, hoff = crop_part(rgba, head_m)
    ha = np.asarray(hp).copy()
    rows = np.arange(ha.shape[0])[:, None] + hoff[1]
    cols = np.arange(ha.shape[1])[None, :] + hoff[0]
    cy_part = np.interp(cols, cx_, cy_)
    fade = np.where(np.abs(cols - nx) < nw, np.clip((cy_part + 14 - rows) / 14.0, 0, 1), 1.0)   # soft edge over the neck stub only
    ha[..., 3] = (ha[..., 3] * fade).astype(np.uint8)
    bleed(Image.fromarray(ha)).save(parts_dir / "head.png")
    rig["parts"]["head"] = {"file": "parts/head.png", "offset": hoff, "pivot": [nx, ny]}
    # the body keeps a 4 px lip past each shoulder cut, so the body edge and the drawn sleeve overlap (no seam)
    lip = np.zeros_like(body_wo_head)
    for side, arm in spec["arms"].items():
        near = np.hypot(grid[..., 0] - arm["shoulder"][0], grid[..., 1] - arm["shoulder"][1]) < 120
        grown = np.asarray(Image.fromarray(body_wo_head.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(17))) > 127
        lip |= grown & alpha & near & ~body_wo_head
    body_wo_head = body_wo_head | lip
    # old sleeve outline bits inside the lip would show as dark ticks: paint them shirt colour
    arr = np.asarray(rgba).copy()
    lum = arr[..., :3].astype(np.int32).sum(-1) / 3
    for side, arm in spec["arms"].items():
        near = np.hypot(grid[..., 0] - arm["shoulder"][0], grid[..., 1] - arm["shoulder"][1]) < 120
        arr[lip & near & (lum < 120)] = sample(src, arm["sleeve"]) + (255,)
    rgba = Image.fromarray(arr)
    bp, boff = crop_part(rgba, body_wo_head)
    bleed(bp).save(parts_dir / "body.png")
    rig["parts"]["body"] = {"file": "parts/body.png", "offset": boff, "pivot": spec["feet"]}
    (cast_dir / "rig.json").write_text(json.dumps(rig, indent=1))
    # debug sheet: the cut lines and points on the picture
    dbg = src.copy()
    dd = ImageDraw.Draw(dbg)
    for side, arm in spec["arms"].items():
        dd.line([tuple(p) for p in arm["poly"]] + [tuple(arm["poly"][0])], fill=(255, 0, 255), width=3)
        for k in ("shoulder", "elbow", "wrist", "sleeve_end"):
            x, y = arm[k]
            dd.ellipse([x - 7, y - 7, x + 7, y + 7], outline=(0, 160, 255), width=3)
    dd.line([tuple(p) for p in sorted(cut)], fill=(0, 200, 0), width=3)
    mc = spec["mouth"]
    dd.rectangle([mc["c"][0] - mc["w"] / 2, mc["c"][1] - mc["h"] / 2, mc["c"][0] + mc["w"] / 2, mc["c"][1] + mc["h"] / 2], outline=(255, 0, 0), width=2)
    for cx, cy, rx, ry in spec["eyes"]:
        dd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=(255, 120, 0), width=2)
    dbg.save(cast_dir / "debug.png")
    print("RIG", cast_dir.name, {k: v["offset"] for k, v in rig["parts"].items()})


if __name__ == "__main__":
    build(sys.argv[1])
