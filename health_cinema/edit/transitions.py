"""Small transition library. Each transition maps (outgoing frame A, incoming frame B, progress p in 0..1) to a frame and is a pure function of those,
so any frame is reproducible. They are used sparingly and chosen by the editorial director from what the two shots are (see director.py)."""
from __future__ import annotations
import functools, math
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple
import numpy as np
from PIL import Image, ImageChops

from . import motion as M

NAMES = ("cut", "dissolve", "wipe", "bar_wipe", "push", "zoom_through", "iris", "drift_dissolve")

@dataclass(frozen=True)
class Transition:
    name: str = "cut"; frames: int = 0; direction: str = "l2r"; point: Tuple[float, float] = (0.5, 0.5); accent: Tuple[int, int, int] = (255, 96, 80); why: str = ""
    def as_json(self): return {"name": self.name, "frames": self.frames, "direction": self.direction, "point": list(self.point), "why": self.why}

@functools.lru_cache(maxsize=8)
def _grid(W: int, H: int):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32); return x / W, y / H

def _mask(a: np.ndarray) -> Image.Image: return Image.fromarray(np.clip(a * 255.0 + 0.5, 0, 255).astype(np.uint8), "L")

def _zoomed(im: Image.Image, z: float, cx: float = 0.5, cy: float = 0.5) -> Image.Image:
    if abs(z - 1) < 1e-4: return im
    w, h = im.width / z, im.height / z; x0 = min(max(cx * im.width - w / 2, 0), im.width - w) if z >= 1 else cx * im.width - w / 2
    y0 = min(max(cy * im.height - h / 2, 0), im.height - h) if z >= 1 else cy * im.height - h / 2
    return im.transform(im.size, Image.EXTENT, (x0, y0, x0 + w, y0 + h), Image.BICUBIC)

def apply(tr: Transition, A: Image.Image, B: Image.Image, p: float) -> Image.Image:
    """p is the raw 0..1 position inside the transition window."""
    W, H = A.size
    if tr.name == "cut" or tr.frames <= 0: return B if p >= 0.5 else A
    if tr.name == "dissolve":
        return Image.blend(A, B, M.in_out_sine(p))
    if tr.name == "drift_dissolve":      # the camera keeps moving through the join: A creeps in, B settles out
        e = M.in_out_sine(p); return Image.blend(_zoomed(A, 1 + 0.05 * e), _zoomed(B, 1.05 - 0.05 * e), e)
    if tr.name in ("wipe", "bar_wipe"):
        e = M.in_out_cubic(p); X, Y = _grid(W, H); soft = 0.10
        coord = {"l2r": X, "r2l": 1 - X, "t2b": Y * (H / W), "b2t": (1 - Y) * (H / W)}[tr.direction]
        span = (H / W) if tr.direction in ("t2b", "b2t") else 1.0
        edge = -soft + (span + 2 * soft) * e; m = np.clip((edge - coord) / soft + 0.5, 0, 1)
        out = Image.composite(B, A, _mask(m))
        if tr.name == "bar_wipe":     # a luminous accent bar rides the edge: graphic bridge between two shots
            d = np.abs(coord - edge); core = np.exp(-(d / 0.006) ** 2); halo = np.exp(-(d / 0.05) ** 2) * 0.35
            lum = np.clip(core + halo, 0, 1) * math.sin(math.pi * min(1.0, max(0.0, e))) ** 0.5
            col = Image.new("RGB", A.size, tuple(min(255, int(c * 0.55 + 140)) for c in tr.accent)); out = Image.composite(col, out, _mask(lum))
        return out
    if tr.name == "push":
        e = M.in_out_cubic(p); dx = int(W * e)
        sgn = 1 if tr.direction == "l2r" else -1; canvas = A.copy()
        canvas.paste(A, (int(sgn * dx * 0.55), 0)); canvas.paste(B, (int(-sgn * W + sgn * dx), 0))
        return canvas
    if tr.name == "zoom_through":
        e = M.in_out_cubic(p); a = _zoomed(A, 1 + 0.55 * e, *tr.point); b = _zoomed(B, 1.30 - 0.30 * e, 0.5, 0.5)
        out = Image.blend(a, b, M.smooth((p - 0.25) / 0.5)); fl = 0.10 * math.sin(math.pi * p) ** 2
        return ImageChops.add(out, Image.new("RGB", out.size, (int(255 * fl),) * 3)) if fl > 0.004 else out
    if tr.name == "iris":
        e = M.in_out_cubic(p); X, Y = _grid(W, H); cx, cy = tr.point; asp = W / H
        d = np.sqrt(((X - cx) * asp) ** 2 + (Y - cy) ** 2); rmax = math.hypot(max(cx, 1 - cx) * asp, max(cy, 1 - cy)) * 1.02; r = e * rmax; soft = 0.035
        m = np.clip((r - d) / soft + 0.5, 0, 1); out = Image.composite(B, A, _mask(m))
        ring = np.exp(-((d - r) / 0.004) ** 2) * math.sin(math.pi * e) * 0.8
        return Image.composite(Image.new("RGB", A.size, (235, 245, 255)), out, _mask(ring)) if ring.max() > 0.02 else out
    raise KeyError(tr.name)
