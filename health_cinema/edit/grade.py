"""Cinematic colour: per-look matrix + tone curve, exposure normalisation from a measured luma, vignette and a deterministic grain.
All operations run in Pillow's C paths (matrix convert, point LUT, ImageChops), so a graded 1080p frame costs a few milliseconds."""
from __future__ import annotations
import functools, random
from typing import Dict, Tuple
from PIL import Image, ImageChops, ImageStat

from . import gfx

LOOKS: Dict[str, dict] = {
    "neutral":      dict(contrast=1.04, sat=1.00, temp=0.00, lift=0.000, vig=0.22, blue_shadows=0.00),
    "warm_memory":  dict(contrast=1.06, sat=0.96, temp=0.07, lift=0.010, vig=0.30, blue_shadows=0.00),
    "cool_clinical": dict(contrast=1.06, sat=0.88, temp=-0.06, lift=0.006, vig=0.26, blue_shadows=0.03),
    "tense":        dict(contrast=1.14, sat=0.68, temp=-0.03, lift=-0.010, vig=0.40, blue_shadows=0.02),
    "hopeful":      dict(contrast=1.03, sat=1.05, temp=0.035, lift=0.014, vig=0.20, blue_shadows=0.00),
}
TARGET_LUMA = 0.40       # mean luma (0..1) every footage shot is normalised toward, within [0.75x, 1.45x] gain, so cuts do not jump in exposure

def measure_luma(im: Image.Image) -> float:
    return ImageStat.Stat(im.convert("L").resize((96, 54))).mean[0] / 255.0

def exposure_gain(mean_luma: float) -> float:
    return min(1.45, max(0.75, TARGET_LUMA / max(0.04, mean_luma)))

@functools.lru_cache(maxsize=64)
def _matrix_lut(look: str, gain: float, boost: float):
    p = LOOKS[look]; s = p["sat"]; r, g, b = 0.299, 0.587, 0.114; gn = gain * boost
    rows = []
    for ci, (cw) in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
        row = [(1 - s) * (r, g, b)[j] + (s if j == ci else 0) for j in range(3)]
        mult = gn * (1 + p["temp"] if ci == 0 else 1 - p["temp"] if ci == 2 else 1.0)
        rows += [x * mult for x in row] + [0.0]
    c = p["contrast"]; lut = []
    for ch in range(3):
        sh = p["blue_shadows"] * (1 if ch == 2 else -0.5 if ch == 0 else 0)
        for i in range(256):
            x = i / 255.0; y = 0.5 + (x - 0.5) * c; y = y + p["lift"] * (1 - x) ** 2 + sh * (1 - x) ** 3
            lut.append(int(max(0, min(255, round(y * 255)))))
    return tuple(rows), lut

def apply(im: Image.Image, look: str = "neutral", gain: float = 1.0, boost: float = 1.0) -> Image.Image:
    """Colour-matrix (exposure, saturation, temperature) then tone curve, then vignette. `boost` lets a shot lift/lower exposure over time (e.g. a push to light)."""
    rows, lut = _matrix_lut(look, round(gain, 3), round(boost, 3))
    out = im.convert("RGB", rows).point(lut); return gfx.vignette(out, LOOKS[look]["vig"])

@functools.lru_cache(maxsize=4)
def _grain_pool(W: int, H: int, n: int = 8):
    import numpy as np
    rng = np.random.default_rng(1234); pool = []
    for _ in range(n):
        small = np.clip(rng.normal(128, 8, (H // 2, W // 2)), 0, 255).astype(np.uint8)
        g = Image.fromarray(small, "L").resize((W, H), Image.BILINEAR); pool.append(Image.merge("RGB", (g, g, g)))
    return pool

def grain(im: Image.Image, frame_index: int, amount: float = 1.0) -> Image.Image:
    """Fine monochrome grain, deterministic by frame index (pool of 8 patterns)."""
    g = _grain_pool(im.width, im.height)[frame_index % 8]
    if amount < 1.0: g = Image.blend(Image.new("RGB", g.size, (128, 128, 128)), g, amount)
    return ImageChops.add(im, g, 1.0, -128)
