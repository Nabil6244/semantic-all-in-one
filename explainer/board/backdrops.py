"""Board backgrounds (schema-free, a clip-level choice). "grey" is the reference's flat board (#C0C0C0) and is what every earlier clip used; the others are light textures that keep the dark
ink and the role colours readable. Each image is drawn once per size from a fixed seed (no randomness, no clock) and cached."""

from __future__ import annotations

from functools import lru_cache
from typing import Tuple

import numpy as np
from PIL import Image

STYLES = ("grey", "paper", "grid", "warm")
GREY = (192, 192, 192)


def _vignette(h: int, w: int, strength: float) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2) / 1.4142
    return 1.0 - strength * np.clip(d, 0, 1) ** 2.2


@lru_cache(maxsize=8)
def _build(name: str, w: int, h: int) -> bytes:
    rs = np.random.RandomState({"paper": 11, "grid": 12, "warm": 13}.get(name, 0))
    if name == "paper":                 # warm off-white paper: fine grain, a few soft fibres, darker edges
        base = np.empty((h, w, 3), np.float32)
        base[:] = (231, 225, 212)
        grain = rs.normal(0, 2.2, (h, w, 1)).astype(np.float32)
        low = np.kron(rs.normal(0, 2.6, (h // 24 + 1, w // 24 + 1, 1)), np.ones((24, 24, 1)))[:h, :w].astype(np.float32)
        img = (base + grain + low) * _vignette(h, w, 0.10)[..., None]
    elif name == "grid":                # a light blue-grey notebook page with a faint 60 px grid
        base = np.empty((h, w, 3), np.float32)
        base[:] = (221, 229, 236)
        img = base + rs.normal(0, 1.2, (h, w, 1)).astype(np.float32)
        img[::60, :, :] -= np.array([14, 10, 8], np.float32)
        img[:, ::60, :] -= np.array([14, 10, 8], np.float32)
        img *= _vignette(h, w, 0.06)[..., None]
    elif name == "warm":                # a soft vertical gradient from cream to sand
        t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        top, bot = np.array([244, 237, 222], np.float32), np.array([222, 208, 188], np.float32)
        img = (top * (1 - t) + bot * t) * np.ones((1, w, 1), np.float32) + rs.normal(0, 1.0, (h, w, 1)).astype(np.float32)
        img *= _vignette(h, w, 0.07)[..., None]
    else:
        raise ValueError(f"unknown background {name!r} (use {', '.join(STYLES)})")
    return np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes()


def image(name: str, size: Tuple[int, int]) -> Image.Image:
    """The background as an RGB image of `size` (a fresh copy: callers draw on it)."""
    if name not in STYLES:
        raise ValueError(f"unknown background {name!r} (use {', '.join(STYLES)})")
    w, h = int(size[0]), int(size[1])
    if name == "grey":
        return Image.new("RGB", (w, h), GREY)
    return Image.frombytes("RGB", (w, h), _build(name, w, h))
