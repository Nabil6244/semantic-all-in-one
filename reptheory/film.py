"""Carl Jung Theory's old-film finish, drawn in code (no assets): a fine moving grain, dust drifting through the light, a soft lamp flicker, and an ink-like
dissolve between chapters. Cheap per frame: the grain and the dissolve noise are made once per size, the dust is a handful of soft dots."""
from __future__ import annotations
import math
from typing import Dict

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

GRAIN_FRAMES, GRAIN_SIGMA = 6, 5.0
DUST_N = 22
_grain: Dict[tuple, list] = {}
_ink: Dict[tuple, np.ndarray] = {}
_grain_img: Dict[tuple, list] = {}


def _grains(w: int, h: int) -> list:
    if (w, h) not in _grain:
        rng = np.random.default_rng(23)
        _grain[(w, h)] = [rng.normal(0, GRAIN_SIGMA, (h, w, 1)).astype(np.float32) for _ in range(GRAIN_FRAMES)]
    return _grain[(w, h)]


def _grain_images(w: int, h: int) -> list:
    """The same grain as _grains, as (lighter, darker) RGB images: a pixel is either lifted or darkened, never both, so the two
    saturating adds in C give the float maths' result (within one level) at about a tenth of the cost (34 ms -> ~4 ms a 1080p frame)."""
    if (w, h) not in _grain_img:
        out = []
        for g in _grains(w, h):
            q = np.rint(g[..., 0]).astype(np.int16)
            up = Image.fromarray(np.clip(q, 0, 255).astype("uint8"), "L"); down = Image.fromarray(np.clip(-q, 0, 255).astype("uint8"), "L")
            out.append((Image.merge("RGB", (up, up, up)), Image.merge("RGB", (down, down, down))))
        _grain_img[(w, h)] = out
    return _grain_img[(w, h)]


def finish(img: Image.Image, frame: int, fps: int = 24) -> Image.Image:
    """Grain (a new pattern every other frame), a lamp flicker of about 1.5 %, and dust motes drifting up and across, each fading in and out."""
    w, h = img.size; t = frame / fps
    flick = 1.0 + 0.010 * math.sin(t * 7.1) + 0.006 * math.sin(t * 17.3 + 1.3)
    up, down = _grain_images(w, h)[(frame // 2) % GRAIN_FRAMES]      # a 23-min video is ~34,000 frames: the float version alone took 20 min of it
    out = ImageChops.subtract(ImageChops.add(img.convert("RGB").point([min(255, int(v * flick)) for v in range(256)] * 3), up), down)
    d = ImageDraw.Draw(out, "RGBA"); s = w / 1920
    for i in range(DUST_N):      # each mote: its own slow path, size and life; positions are pure functions of time (identical on every render)
        sp = 0.012 + 0.010 * ((i * 37) % 11) / 11; ph = (i * 0.618) % 1.0
        x = ((ph + t * sp * 0.6 + 0.04 * math.sin(t * 0.7 + i)) % 1.0) * w; y = ((1.0 - (ph * 1.7 + t * sp) % 1.0)) * h
        life = 0.5 + 0.5 * math.sin(t * (0.5 + 0.07 * i) + i * 2.1); r = (1.2 + (i % 4) * 0.7) * s
        if life > 0.15: d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 236, 200, int(70 * life)))
    return out


def _ink_noise(w: int, h: int) -> np.ndarray:
    if (w, h) not in _ink:
        rng = np.random.default_rng(5); small = Image.fromarray((rng.random((h // 24 + 1, w // 24 + 1)) * 255).astype("uint8"), "L")
        big = small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(18 * w / 1920))
        n = np.asarray(big, dtype=np.float32) / 255.0; _ink[(w, h)] = (n - n.min()) / max(1e-6, n.max() - n.min())
    return _ink[(w, h)]


def ink_dissolve(a: Image.Image, b: Image.Image, p: float) -> Image.Image:
    """From a to b like ink spreading through water: soft blotches of b grow until they fill the frame (p 0..1)."""
    p = min(1.0, max(0.0, p)); n = _ink_noise(*a.size)
    m = np.clip((p * 1.35 - n) / 0.35, 0.0, 1.0)
    return Image.composite(b.convert("RGB"), a.convert("RGB"), Image.fromarray((m * 255).astype("uint8"), "L"))


ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]


def roman(n: int) -> str:
    return ROMAN[n] if 0 < n < len(ROMAN) else str(n)
