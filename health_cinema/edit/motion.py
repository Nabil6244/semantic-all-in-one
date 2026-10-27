"""Easing, keyframe tracks and camera paths. Everything is a pure function of time, so a frame depends only on (shot spec, t)."""
from __future__ import annotations
import math
from typing import Callable, List, Sequence, Tuple

def clamp01(x: float) -> float: return 0.0 if x < 0 else 1.0 if x > 1 else x
def linear(x): return clamp01(x)
def smooth(x): x = clamp01(x); return x * x * (3 - 2 * x)
def smoother(x): x = clamp01(x); return x * x * x * (x * (6 * x - 15) + 10)
def in_cubic(x): x = clamp01(x); return x ** 3
def out_cubic(x): x = clamp01(x); return 1 - (1 - x) ** 3
def in_out_cubic(x): x = clamp01(x); return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2
def out_expo(x): x = clamp01(x); return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)
def out_back(x, s=1.3): x = clamp01(x) - 1; return 1 + (s + 1) * x ** 3 + s * x ** 2
def in_out_sine(x): return -(math.cos(math.pi * clamp01(x)) - 1) / 2
EASE = {"linear": linear, "smooth": smooth, "smoother": smoother, "in_cubic": in_cubic, "out_cubic": out_cubic, "in_out_cubic": in_out_cubic,
        "out_expo": out_expo, "out_back": out_back, "in_out_sine": in_out_sine}

def lerp(a, b, k): return a + (b - a) * k

def window(t: float, a: float, b: float, ease: Callable = smooth) -> float:
    """Progress of t through [a, b], eased, clamped to 0..1."""
    return ease((t - a) / max(1e-9, b - a))

def fade_inout(t: float, t0: float, t1: float, fin: float = 0.3, fout: float = 0.3) -> float:
    """Opacity of an element alive on [t0, t1] with eased fades in and out."""
    if t < t0 or t > t1: return 0.0
    return min(smooth((t - t0) / max(1e-9, fin)), smooth((t1 - t) / max(1e-9, fout)))

class Track:
    """Keyframes [(t, value)] with a per-segment ease; values may be numbers or tuples of numbers."""
    def __init__(self, keys: Sequence[Tuple[float, object]], ease: Callable = smooth):
        self.keys = sorted(keys, key=lambda k: k[0]); self.ease = ease
    def __call__(self, t: float):
        ks = self.keys
        if t <= ks[0][0]: return ks[0][1]
        for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
            if t <= t1:
                k = self.ease((t - t0) / max(1e-9, t1 - t0))
                return tuple(lerp(a, b, k) for a, b in zip(v0, v1)) if isinstance(v0, tuple) else lerp(v0, v1, k)
        return ks[-1][1]

# ---- camera ------------------------------------------------------------------------------------------------------------------------
# A camera is (zoom >= 1, cx, cy): the crop shows 1/zoom of the source around the centre (cx, cy in 0..1 of the source), clamped inside the source.
MOVES = ("push_in", "pull_back", "pan_left", "pan_right", "tilt_up", "tilt_down", "drift", "hold")

def camera_path(move: str, dur: float, amount: float = 0.12, focus: Tuple[float, float] = (0.5, 0.5), handle: float = 0.5, seed: int = 0) -> Callable[[float], Tuple[float, float, float]]:
    """Path over [-handle, dur + handle] so the motion carries through a transition instead of stopping at the cut. Ease is in-out (controlled
    acceleration and deceleration); a tiny deterministic sway keeps a held frame alive without looking handheld."""
    total = dur + 2 * handle; fx, fy = focus
    def sway(t):
        return (0.0016 * math.sin(2 * math.pi * (t / 7.3) + seed), 0.0012 * math.sin(2 * math.pi * (t / 9.1) + 1.7 * seed))
    def path(t: float):
        u = in_out_sine((t + handle) / total); sx, sy = sway(t)
        if move == "push_in": z = 1.0 + amount * u; cx, cy = lerp(0.5, fx, u * 0.9), lerp(0.5, fy, u * 0.9)
        elif move == "pull_back": z = 1.0 + amount * (1 - u); cx, cy = lerp(fx, 0.5, u * 0.9), lerp(fy, 0.5, u * 0.9)
        elif move in ("pan_left", "pan_right"):
            z = 1.0 + amount; d = amount / (2 * (1 + amount)) * 0.9; sgn = -1 if move == "pan_left" else 1
            cx, cy = 0.5 - sgn * d + sgn * 2 * d * u, fy
        elif move in ("tilt_up", "tilt_down"):
            z = 1.0 + amount; d = amount / (2 * (1 + amount)) * 0.9; sgn = -1 if move == "tilt_up" else 1
            cx, cy = fx, 0.5 - sgn * d + sgn * 2 * d * u
        elif move == "drift": z = 1.0 + amount * 0.6; cx, cy = 0.5 + 0.02 * math.sin(2 * math.pi * u * 0.5 + seed), 0.5 + 0.015 * math.cos(2 * math.pi * u * 0.5 + seed)
        else: z, cx, cy = 1.0 + amount * 0.0, 0.5, 0.5
        return z, cx + sx, cy + sy
    return path

def crop_extent(src_w: int, src_h: int, z: float, cx: float, cy: float) -> Tuple[float, float, float, float]:
    w, h = src_w / z, src_h / z
    x0 = min(max(cx * src_w - w / 2, 0), src_w - w); y0 = min(max(cy * src_h - h / 2, 0), src_h - h)
    return (x0, y0, x0 + w, y0 + h)
