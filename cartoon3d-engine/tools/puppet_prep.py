#!/usr/bin/env python3
"""Turn a character picture into a clean cut-out for a 2D puppet host.

Usage: puppet_prep.py PICTURE OUT.png
- Grid lines baked into the picture (a design tool's see-through guide grid: thin evenly spaced lines) are found from the
  plain background and inverted everywhere, across the character too, so the drawing under each line comes back.
- The background is the flat colour touching the picture's border: only that connected area becomes transparent,
  with a soft edge; anything inside the character keeps its colour.
- The cut-out is cropped to the character with a small margin. Prints a JSON report.
"""
import json
import sys

import numpy as np
from PIL import Image


def _lines(profile, bg_level, min_gap=60):
    """Indices of thin bands where a background-only profile departs from the background level."""
    dev = np.abs(profile - bg_level) > 3
    bands, i = [], 0
    while i < len(dev):
        if dev[i]:
            j = i
            while j + 1 < len(dev) and dev[j + 1]:
                j += 1
            if j - i <= 12:
                bands.append((i, j))
            i = j + 1
        else:
            i += 1
    # keep only bands that repeat at a steady spacing (a grid), not one-off marks
    if len(bands) < 3:
        return []
    centres = np.array([(a + b) / 2 for a, b in bands]); step = np.median(np.diff(centres))
    return [b for b, c in zip(bands, centres) if step >= min_gap and abs(((c - centres[0]) / step) - round((c - centres[0]) / step)) < 0.08]


def _band_refs(src, bands, pad=3):
    """For every row of every band: (row, the same row as it would be without the line, which pixels are trustworthy)."""
    n = src.shape[0]
    for a, b in bands:
        a, b = max(0, a - pad), min(n - 1, b + pad)
        lo, hi = src[max(0, a - 2)], src[min(n - 1, b + 2)]
        flat = np.abs(lo - hi).sum(-1) < 15
        if flat.sum() < 50:
            continue
        for k in range(a, b + 1):
            t = (k - a + 2) / (b - a + 4)
            yield k, lo * (1 - t) + hi * t, flat


def _line_colour(src, bands):
    """The grid's one colour: where a row crosses both dark and light drawing, line = (1 - a) * clean + a * colour."""
    found = []
    for k, ref, flat in _band_refs(src, bands):
        x, y = ref[flat].ravel(), src[k][flat].ravel()
        if x.std() < 25:
            continue
        slope, off = np.polyfit(x, y, 1)
        if 0.5 < slope < 0.93:
            found.append([np.polyfit(ref[flat, c], src[k][flat, c], 1) for c in range(3)])
    if not found:
        return None
    f = np.array(found)
    return np.median(f[:, :, 1] / np.maximum(1 - f[:, :, 0], 0.02), axis=0)


def _strengths(src, bands, colour):
    """How strong the line is on each row, per channel (0 away from a line)."""
    out = np.zeros((src.shape[0], 3))
    for k, ref, flat in _band_refs(src, bands):
        for c in range(3):
            d = colour[c] - ref[flat, c]; e = src[k][flat, c] - ref[flat, c]
            keep = np.ones(len(d), bool)
            for _ in range(3):                           # robust: a crossing line or a stray edge must not pull the fit
                a = (e[keep] * d[keep]).sum() / max(1.0, (d[keep] ** 2).sum())
                res = np.abs(e - a * d); keep = res < max(4.0, np.percentile(res, 80))
            out[k, c] = min(0.7, max(0.0, a))
    return out


def _unblend(img, cols, rows):
    """Take a see-through grid out by inverting it, so whatever it crosses (an eyelid, a lash) comes back untouched; a straight
    blend across each line would flatten the drawing under it. The grid was drawn once, so a crossing is undone once too."""
    turned = img.transpose(1, 0, 2)
    colour = _line_colour(img, rows)
    if colour is None:
        colour = _line_colour(turned, cols)
    if colour is None:
        return img
    a = np.maximum(_strengths(img, rows, colour)[:, None, :], _strengths(turned, cols, colour)[None, :, :])
    return np.clip((img - a * colour) / (1 - a), 0, 255)


def prep(src, dst):
    im = np.asarray(Image.open(src).convert("RGB")).astype(np.float64)
    h, w, _ = im.shape
    bg = np.median(np.concatenate([im[:8].reshape(-1, 3), im[-8:].reshape(-1, 3), im[:, :8].reshape(-1, 3), im[:, -8:].reshape(-1, 3)]), axis=0)
    # grid: columns from the top band, rows from the left band (both background-only in a centred portrait)
    gray = im.mean(2)
    cols = _lines(np.median(gray[: max(20, h // 12)], axis=0), bg.mean())
    rows = _lines(np.median(gray[:, : max(20, w // 12)], axis=1), bg.mean())
    im = _unblend(im, cols, rows)
    # background: near-bg colour connected to the border
    dist = np.sqrt(((im - bg) ** 2).sum(2))
    near = dist < 18
    from collections import deque
    seen = np.zeros_like(near); q = deque()
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x] and not seen[y, x]:
                seen[y, x] = True; q.append((y, x))
    for x in range(w):
        for y in (0, h - 1):
            if near[y, x] and not seen[y, x]:
                seen[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and near[yy, xx] and not seen[yy, xx]:
                seen[yy, xx] = True; q.append((yy, xx))
    # enclosed background (e.g. the gap inside an arm on the hip): flat near-bg areas not touching the border, at least 400 px
    rest = near & ~seen; lab = np.zeros(rest.shape, np.int32); n_lab = 0
    for y0, x0 in zip(*np.nonzero(rest)):
        if lab[y0, x0]:
            continue
        n_lab += 1; comp = [(y0, x0)]; lab[y0, x0] = n_lab; k = 0
        while k < len(comp):
            y, x = comp[k]; k += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and rest[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n_lab; comp.append((yy, xx))
        if len(comp) >= 400:
            ys_, xs_ = zip(*comp); seen[list(ys_), list(xs_)] = True
    alpha = np.where(seen, 0.0, 1.0)
    # soft edge: pixels next to the background blend by their distance from the background colour
    from PIL import ImageFilter
    edge = np.asarray(Image.fromarray((seen * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    ring = edge & ~seen
    a_ring = np.clip((dist - 6) / 40, 0, 1)
    alpha[ring] = np.minimum(alpha[ring], a_ring[ring])
    # un-mix the grey from soft edge pixels so no grey halo shows on new backgrounds
    a3 = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.where(alpha[..., None] < 1, (im - bg * (1 - a3)) / a3, im)
    rgba = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)
    # only the character: stray marks left along the grid must not stay or stretch the crop
    solid = alpha > 0.05; lab2 = np.zeros(solid.shape, np.int32); best, best_n = 0, 0
    for y0, x0 in zip(*np.nonzero(solid)):
        if lab2[y0, x0]:
            continue
        i_ = lab2.max() + 1; lab2[y0, x0] = i_; comp = [(y0, x0)]; k = 0
        while k < len(comp):
            y, x = comp[k]; k += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and solid[yy, xx] and not lab2[yy, xx]:
                    lab2[yy, xx] = i_; comp.append((yy, xx))
        if len(comp) > best_n:
            best, best_n = i_, len(comp)
    alpha[lab2 != best] = 0
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    ys, xs = np.nonzero(alpha > 0.05); m = 12
    box = (max(0, xs.min() - m), max(0, ys.min() - m), min(w, xs.max() + m + 1), min(h, ys.max() + m + 1))
    Image.fromarray(rgba).crop(box).save(dst)
    rep = {"size": [w, h], "enclosed_background_areas": int(n_lab), "background": [round(v) for v in bg], "grid_columns": len(cols), "grid_rows": len(rows), "crop": [int(v) for v in box], "out": dst}
    print(json.dumps(rep))
    return rep


if __name__ == "__main__":
    prep(sys.argv[1], sys.argv[2])
