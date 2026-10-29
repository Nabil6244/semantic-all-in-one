"""travel -- a continuous camera TRAVEL through a collage world (the "first prototype" look).

Pictures are glued side by side with torn-paper seams (cream torn edge + soft shadow).  The camera dwells on a picture while the narration
describes it, then travels on to the next one so that the new picture is centred exactly when its words start.  A flat ink silhouette
walker stays at a fixed screen position while the world scrolls rigidly under it.  Everything moves RIGIDLY: only affine camera moves
(translate + a hair of scale), +-1 px frame jitter, grain, vignette, flicker, dust.  No mesh warps, no dissolves, no cuts.

    strip = build_strip(stills, size=(1920, 1080), seam_style='torn', overlap_px=40)       # -> Strip (lazy: loads 2-3 pictures at a time)
    sched = plan_schedule(starts, ends, travel_s=1.1, dwell_drift=0.012, ease='smooth', direction='right')
    render_travel(stills, sched, out_path, fps=30, size=(1920, 1080), walker='silhouette', seed=0, cancel=None, progress=None) -> out_path
    render_travel_slices(stills_by_scene, scene_windows, out_dir, margin=0.5, ...) -> {scene_no: mp4}

The frame at time t is a pure function of (inputs, t): frames can be skipped, rendered in any order, and the result is deterministic.
Cancelling (cancel() -> True) raises TravelCancelled and leaves no partial file (temp file, then os.replace).
Python3 + numpy + Pillow + ffmpeg only.
"""
from __future__ import annotations

import hashlib
import math
import os
import pickle
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

try:
    _CODE_HASH = hashlib.sha1(open(__file__, "rb").read()).hexdigest()[:10]
except Exception:  # pragma: no cover
    _CODE_HASH = "x"
VERSION = "travel-1." + _CODE_HASH

CREAM = (244, 236, 218)
INK = (36, 27, 21)
_DIRS = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}
_ENTER_SIDE = {"right": "left", "left": "right", "down": "top", "up": "bottom"}    # the side of the NEW picture that faces the old one


class TravelCancelled(RuntimeError):
    """Raised when cancel() returned True; no partial output is left behind."""


# ================================================================================ ease / schedule
def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


_EASE_TABLES: Dict[str, np.ndarray] = {}


def _ease_table(kind: str) -> np.ndarray:
    """Position profile 0..1 on 2049 samples; velocity is continuous and zero at both ends, constant in the middle for 'smooth'."""
    if kind in _EASE_TABLES:
        return _EASE_TABLES[kind]
    n = 2048
    u = np.linspace(0, 1, n + 1)
    if kind == "smooth":          # velocity: smoothstep ramp (30 %), plateau, smoothstep ramp (30 %)
        r = 0.30
        v = np.minimum(_smoothstep(u / r), _smoothstep((1 - u) / r))
    elif kind == "linear":        # trapezoid velocity
        r = 0.22
        v = np.minimum(np.clip(u / r, 0, 1), np.clip((1 - u) / r, 0, 1))
    elif kind == "sine":
        v = np.sin(np.pi * u)
    else:
        raise ValueError("ease must be 'smooth', 'linear' or 'sine'")
    p = np.concatenate([[0.0], np.cumsum((v[1:] + v[:-1]) * 0.5)])
    p /= p[-1]
    _EASE_TABLES[kind] = p
    return p


def ease_pos(kind: str, u):
    t = _ease_table(kind)
    return np.interp(np.clip(u, 0, 1), np.linspace(0, 1, len(t)), t)


@dataclass
class Schedule:
    starts: List[float]
    ends: List[float]
    travels: List[Tuple[float, float]]          # travels[k] = (t0, t1): camera moves from picture k to k+1 (t1 = start of k+1 unless `lead` given)
    dirs: List[str]                             # dirs[k]    = direction of travel k
    ease: str = "smooth"
    dwell_drift: float = 0.012                  # drift amplitude, fraction of frame width
    dwell_mode: str = "drift"                   # 'drift' | 'push' | 'still'
    breathe: float = 0.012                      # scale breathing amplitude (<= 0.02)
    seed: int = 0

    @property
    def n(self) -> int:
        return len(self.starts)

    @property
    def total(self) -> float:
        return float(self.ends[-1])

    def arrival(self, k: int) -> float:
        return 0.0 if k == 0 else self.travels[k - 1][1]

    def departure(self, k: int) -> float:
        return self.total if k >= self.n - 1 else self.travels[k][0]

    def locate(self, t: float):
        """-> (k, travelling, u): picture index k (the picture we are on / leaving), u = 0..1 progress of the travel k -> k+1."""
        k = 0
        lo, hi = 0, len(self.travels)
        while lo < hi:                       # first travel whose end is > t
            mid = (lo + hi) // 2
            if self.travels[mid][1] <= t:
                lo = mid + 1
            else:
                hi = mid
        k = lo
        if k >= len(self.travels):
            return self.n - 1, False, 0.0
        t0, t1 = self.travels[k]
        if t >= t0:
            return k, True, (t - t0) / max(t1 - t0, 1e-9)
        return k, False, 0.0

    def state(self, t: float) -> dict:
        """Camera state: k, travelling, u, f (eased 0..1 travel fraction), dir, dx, dy (fractions of frame WIDTH, drift), scale."""
        k, trav, u = self.locate(t)
        f = float(ease_pos(self.ease, u)) if trav else 0.0
        dx = dy = 0.0
        sc = 1.0
        if self.dwell_mode != "still":
            a, d = self.arrival(k), self.departure(k)
            tau = t - a
            if trav:
                tau = d - a
            span = max(d - a, 1e-6)
            uu = min(max(tau / span, 0.0), 1.0)
            env = math.sin(math.pi * uu) ** 2
            rs = (self.seed * 7919 + k * 104729) % 1000 / 1000.0
            ph1, ph2, ph3 = rs * 6.283, (rs * 3.7) % 1 * 6.283, (rs * 5.3) % 1 * 6.283
            if self.dwell_mode == "push":
                dx = self.dwell_drift * env * (1 if k % 2 == 0 else -1)
                dy = 0.0
                sc = 1.0 + min(0.02, self.breathe * 1.6) * env
            else:
                dx = self.dwell_drift * env * math.sin(2 * math.pi * tau / 8.5 + ph1)
                dy = self.dwell_drift * 0.6 * env * math.sin(2 * math.pi * tau / 6.3 + ph2)
                sc = 1.0 + min(0.02, self.breathe) * env * math.sin(2 * math.pi * tau / 9.7 + ph3)
        dirv = self.dirs[k] if k < len(self.dirs) else (self.dirs[-1] if self.dirs else "right")
        return dict(k=k, travelling=trav, u=u, f=f, dir=dirv, dx=dx, dy=dy, scale=sc)


def plan_schedule(starts: Sequence[float], ends: Sequence[float], *, travel_s: float = 1.1, dwell_drift: float = 0.012, ease: str = "smooth",
                  dwell_mode: str = "drift", direction: str = "right", chapters: Optional[Sequence] = None, vertical: Optional[str] = None,
                  vertical_every: int = 0, dirs: Optional[Sequence[str]] = None, lead: Optional[float] = None, min_dwell: float = 0.3,
                  breathe: float = 0.012, seed: int = 0) -> Schedule:
    """Camera plan.  starts[i]/ends[i] = the narration window of picture i (picture 0 starts at 0).

    Travel k -> k+1 ENDS at starts[k+1] (the new picture is centred exactly when its first words start) and lasts travel_s, shortened when the
    gap between two starts is short.  lead=0.25 switches to 'the travel STARTS at boundary - lead' (it then ends at start + travel_s - lead).
    direction: 'right' | 'left' | 'alternate_by_chapter' (flips when chapters[i] changes; chapters = per-picture ids).  vertical='up'|'down' with
    vertical_every=N makes every Nth transition a vertical one for variety.  dirs overrides everything (one direction per transition).
    The camera position and velocity are continuous (velocity is zero at both ends of every travel and the dwell drift is zero-velocity at its ends).
    """
    n = len(starts)
    if n < 1:
        raise ValueError("need at least one picture")
    if len(ends) != n:
        raise ValueError("starts and ends must have the same length")
    starts = [float(s) for s in starts]
    starts[0] = min(starts[0], 0.0) if starts[0] > 0 else starts[0]
    ends = [float(e) for e in ends]
    if dirs is not None:
        dl = list(dirs)
        if len(dl) < n - 1:
            raise ValueError("dirs too short")
        dl = dl[:max(n - 1, 0)]
    else:
        dl = []
        cur = "right" if direction in ("right", "alternate_by_chapter") else "left"
        for k in range(max(n - 1, 0)):
            if direction == "alternate_by_chapter" and chapters is not None and k >= 1 and chapters[k + 1] != chapters[k]:
                cur = "left" if cur == "right" else "right"
            d = cur
            if vertical and vertical_every and (k + 1) % vertical_every == 0:
                d = vertical
            dl.append(d)
    for d in dl:
        if d not in _DIRS:
            raise ValueError("bad direction %r" % (d,))
    tr: List[Tuple[float, float]] = []
    prev_end = 0.0
    for k in range(n - 1):
        b = starts[k + 1]
        gap = b - (starts[k])
        T = min(float(travel_s), max(0.35, gap * 0.7))
        t1 = b if lead is None else b - lead + T
        t0 = t1 - T
        t0 = max(t0, prev_end + 0.05) if k > 0 else max(t0, 0.0)
        if t1 <= t0 + 0.05:
            t1 = t0 + 0.05
        tr.append((t0, t1))
        prev_end = t1
    ends = list(ends)
    ends[-1] = max(ends[-1], tr[-1][1] + 0.5 if tr else ends[-1])
    return Schedule(starts, ends, tr, dl, ease=ease, dwell_drift=dwell_drift, dwell_mode=dwell_mode, breathe=breathe, seed=seed)


# ================================================================================ strip / geometry
def _as_image(src) -> Image.Image:
    if isinstance(src, Image.Image):
        return src.convert("RGB")
    if isinstance(src, np.ndarray):
        return Image.fromarray(src.astype(np.uint8)).convert("RGB")
    with Image.open(str(src)) as im:
        return im.convert("RGB")


def _cover_crop(im: Image.Image, pw: int, ph: int) -> Image.Image:
    s = max(pw / im.width, ph / im.height)
    nw, nh = max(pw, int(math.ceil(im.width * s))), max(ph, int(math.ceil(im.height * s)))
    im = im.resize((nw, nh), Image.LANCZOS)
    l, t = (nw - pw) // 2, (nh - ph) // 2
    return im.crop((l, t, l + pw, t + ph))


def _profile(rng, n, amp, knots_every, smooth=0):
    m = max(2, n // knots_every + 2)
    kn = rng.standard_normal(m)
    p = np.interp(np.arange(n), np.linspace(0, n - 1, m), kn)
    if smooth:
        k = np.ones(smooth) / smooth
        p = np.convolve(np.pad(p, smooth, mode="edge"), k, mode="same")[smooth:-smooth]
    return p * amp


def _torn_canonical(arr: np.ndarray, seed: int, k: float, style: str, tear0: float, sh_pad: int) -> np.ndarray:
    """arr (h, w, 3) uint8, entering edge at the LEFT.  -> RGBA (h, w + sh_pad, 4): the picture torn at its left edge, cream paper edge, shadow
    (a soft black alpha band outside the tear).  Canvas column c <-> picture column c - sh_pad."""
    h, w, _ = arr.shape
    rng = np.random.default_rng(seed)
    if style == "torn":
        j = _profile(rng, h, 13 * k, 60, 31) + _profile(rng, h, 5 * k, 15) + _profile(rng, h, 1.3 * k, 3)
        j = np.clip(j, -(tear0 - 6 * k), tear0 - 6 * k)
        bw = 14 * k * (0.72 + 0.55 * _smoothstep(0.5 + 0.5 * _profile(rng, h, 1.0, 40, 9)))
    else:                                       # 'clean': straight cut, paper edge, shadow
        j = np.zeros(h)
        bw = np.full(h, 10 * k)
    t = tear0 + j                                # tear column (picture coords) per row
    band_cols = int(tear0 + 22 * k + 14 * k * 1.4 + 6)
    nb = band_cols + sh_pad
    cols = (np.arange(nb) - sh_pad)[None, :].astype(np.float32)
    d = cols - t[:, None].astype(np.float32)             # >= 0 inside the paper
    inside = d >= 0
    cov = np.clip(d + 0.5, 0, 1)
    src = arr[:, :band_cols, :].astype(np.float32)
    src = np.concatenate([np.repeat(src[:, :1, :], sh_pad, axis=1), src], axis=1) if sh_pad else src
    noise = rng.standard_normal((h, nb, 1)).astype(np.float32) * 4.0
    cream = np.array(CREAM, np.float32)[None, None, :] + noise
    m = np.clip((bw[:, None].astype(np.float32) - d) / 1.2, 0, 1)[..., None] * inside[..., None]
    rgb = src * (1 - m) + cream * m
    sd = np.maximum(-d, 0)
    sa = 0.46 * np.clip(1 - sd / (38 * k), 0, 1) ** 1.6
    alpha = np.where(inside, cov, sa) * 255.0
    rgb = np.where(inside[..., None], rgb, cream * 0.0 + np.array([14, 10, 6], np.float32))
    band = np.concatenate([np.clip(rgb, 0, 255), alpha[..., None]], axis=2).astype(np.uint8)
    rest = np.concatenate([arr[:, band_cols:, :], np.full((h, w - band_cols, 1), 255, np.uint8)], axis=2)
    out = np.concatenate([band, rest], axis=1)
    return out


class Strip:
    """The collage world.  Holds the picture sources and the geometry; decodes only the pictures that are visible (small LRU)."""

    def __init__(self, stills, size=(1920, 1080), seam_style="torn", overlap_px: Optional[int] = None, seed: int = 0, zoom: Optional[Tuple[float, float]] = None,
                 dirs: Optional[Sequence[str]] = None):
        self.stills = list(stills)
        self.W, self.H = int(size[0]), int(size[1])
        self.k = self.W / 1920.0
        self.seam_style = seam_style
        self.seed = int(seed)
        self.lap = float(overlap_px if overlap_px is not None else 40) * self.k          # how far the old picture extends past the seam
        self.tear0 = 30.0 * self.k                                                       # tear centre inside the new picture
        self.sh_pad = int(math.ceil(46 * self.k))
        self._zoom = zoom
        self.dirs: List[str] = list(dirs) if dirs is not None else ["right"] * max(len(self.stills) - 1, 0)
        self._plain: Dict[int, Image.Image] = {}
        self._torn: Dict[Tuple[int, str], Image.Image] = {}
        self._order: List = []
        self._layout()

    # ---- geometry
    def _layout(self):
        vert = any(d in ("up", "down") for d in self.dirs)
        zx, zy = self._zoom if self._zoom else (1.16, 1.27 if vert else 1.16)
        self.Pw, self.Ph = int(round(self.W * zx)), int(round(self.H * zy))
        c = [(0.0, 0.0)]
        for d in self.dirs:
            dx, dy = _DIRS[d]
            x, y = c[-1]
            c.append((x + dx * (self.Pw - self.lap - self.tear0), y + dy * (self.Ph - self.lap - self.tear0)))
        while len(c) < len(self.stills):
            c.append(c[-1])
        self.centres = c[:max(len(self.stills), 1)]
        # how far the camera may drift/scale from a centre before an edge or a seam shows (pixels)
        shadow = 38 * self.k
        jit = 22 * self.k
        self.margin_x = self.Pw / 2 - self.lap - jit - shadow - self.W / 2
        self.margin_y = self.Ph / 2 - self.lap - jit - shadow - self.H / 2 if vert else self.Ph / 2 - self.H / 2

    def set_dirs(self, dirs):
        self.dirs = list(dirs)
        self._plain.clear(); self._torn.clear(); self._order.clear()
        self._layout()

    def origin(self, i: int) -> Tuple[float, float]:
        cx, cy = self.centres[i]
        return cx - self.Pw / 2, cy - self.Ph / 2

    # ---- pictures
    def _touch(self, key):
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)
        while len(self._order) > 7:
            old = self._order.pop(0)
            if old[0] == "p":
                self._plain.pop(old[1], None)
            else:
                self._torn.pop(old[1:], None)

    def plain(self, i: int) -> Image.Image:
        if i not in self._plain:
            self._plain[i] = _cover_crop(_as_image(self.stills[i]), self.Pw, self.Ph)
        self._touch(("p", i))
        return self._plain[i]

    def torn(self, i: int, direction: str):
        """RGBA picture torn on the side facing the previous picture.  -> (image, (canvas_offset_x, canvas_offset_y)) relative to the plain panel."""
        side = _ENTER_SIDE[direction]
        key = (i, side)
        if key not in self._torn:
            arr = np.asarray(self.plain(i))
            sd = self.seed * 1009 + i * 31
            args = (sd, self.k, self.seam_style, self.tear0, self.sh_pad)
            if side == "left":
                out = _torn_canonical(arr, *args)
            elif side == "right":
                out = _torn_canonical(arr[:, ::-1], *args)[:, ::-1]
            elif side == "top":
                out = _torn_canonical(arr.transpose(1, 0, 2), *args).transpose(1, 0, 2)
            else:
                out = _torn_canonical(arr.transpose(1, 0, 2)[:, ::-1], *args)[:, ::-1].transpose(1, 0, 2)
            self._torn[key] = Image.fromarray(np.ascontiguousarray(out), "RGBA")
        self._touch(("t",) + key)
        off = {"left": (-self.sh_pad, 0), "right": (0, 0), "top": (0, -self.sh_pad), "bottom": (0, 0)}[side]
        return self._torn[key], off

    # ---- compositing
    @staticmethod
    def _xf(img: Image.Image, size, cam, scale, ox, oy, resample):
        s = 1.0 / scale
        W, H = size
        c = cam[0] - W / 2.0 * s - ox
        f = cam[1] - H / 2.0 * s - oy
        return img.transform(size, Image.AFFINE, (s, 0, c, 0, s, f), resample)

    def view(self, cam: Tuple[float, float], scale: float, a: int, b: Optional[int] = None, direction: str = "right", resample=Image.BICUBIC) -> Image.Image:
        """The frame seen from world position cam (centre) at the given scale.  b is the picture being travelled to (torn over a)."""
        size = (self.W, self.H)
        ox, oy = self.origin(a)
        base = self._xf(self.plain(a), size, cam, scale, ox, oy, resample)
        if b is not None:
            timg, off = self.torn(b, direction)
            bx, by = self.origin(b)
            top = self._xf(timg, size, cam, scale, bx + off[0], by + off[1], resample)
            base.paste(top, (0, 0), top)
        return base


def build_strip(stills, size=(1920, 1080), seam_style="torn", overlap_px: Optional[int] = None, seed: int = 0, dirs=None, zoom=None) -> Strip:
    """Strip of pictures joined by torn seams.  seam_style 'torn' | 'clean'.  overlap_px = how far the previous picture extends under the seam (default 40)."""
    if seam_style not in ("torn", "clean"):
        raise ValueError("seam_style must be 'torn' or 'clean'")
    return Strip(stills, size, seam_style, overlap_px, seed, zoom, dirs)


def camera_xy(strip: Strip, sched: Schedule, t: float, jitter=(0, 0)) -> Tuple[float, float, float]:
    """World camera centre (px) and scale at time t (before the +-1 px frame jitter)."""
    st = sched.state(t)
    k = st["k"]
    cx, cy = strip.centres[k]
    if st["travelling"]:
        nx, ny = strip.centres[k + 1]
        cx += (nx - cx) * st["f"]
        cy += (ny - cy) * st["f"]
    ax = min(abs(st["dx"] * strip.W), max(strip.margin_x - 4, 0)) * (1 if st["dx"] >= 0 else -1)
    ay = min(abs(st["dy"] * strip.W), max(strip.margin_y - 4, 0)) * (1 if st["dy"] >= 0 else -1)
    return cx + ax + jitter[0], cy + ay + jitter[1], st["scale"]


# ================================================================================ walker
def _flatten_sprite(sprite: Image.Image, k: float):
    """Rigged colour sprite -> flat ink silhouette + white cut-out outline.  -> RGBA, pad (pixels added on every side)."""
    a = np.asarray(sprite)
    al = a[..., 3]
    lum = a[..., :3].astype(np.float32).mean(-1)
    body = (al > 128).astype(np.uint8) * 255      # the whole sprite is one solid shape: no pale parts may punch holes into the ink
    m = Image.fromarray(body, "L").filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    r = max(2, int(round(5.5 * k)))
    pad = r + 4
    m = ImageOps.expand(m, pad, 0)
    outl = m.filter(ImageFilter.MaxFilter(2 * r + 1)).filter(ImageFilter.GaussianBlur(0.8))
    ink = m.filter(ImageFilter.GaussianBlur(0.6))
    ones = Image.new("RGBA", m.size, CREAM + (255,))
    ones.putalpha(outl)
    inkimg = Image.new("RGBA", m.size, INK + (255,))
    inkimg.putalpha(ink)
    return Image.alpha_composite(ones, inkimg), pad



# ================================================================================ ink man: a slim flat silhouette drawn directly (two real legs, foot-locked)
def _smooth(x):
    x = min(1.0, max(0.0, x)); return x * x * (3 - 2 * x)

def _ik(hx, hy, ax, ay, l1, l2):
    """2-bone leg from hip (hx,hy) to ankle (ax,ay), knee bends FORWARD (+x). y is up. -> knee (x,y), ankle actually reached."""
    dx, dy = ax - hx, ay - hy; d = math.hypot(dx, dy); d = max(1e-6, d)
    if d > (l1 + l2) * 0.999:
        sc = (l1 + l2) * 0.999 / d; dx, dy = dx * sc, dy * sc; d = (l1 + l2) * 0.999
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d); h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    ux, uy = dx / d, dy / d
    kx, ky = hx + ux * a - uy * h, hy + uy * a + ux * h          # perpendicular pointing forward/up for a leg pointing down
    return (kx, ky), (hx + dx, hy + dy)

class InkMan:
    """Side view, facing right.  All lengths in units of the man's height h.  pose(action, phase, stride) -> (RGBA sprite, anchor=(x of the hip line, y of the ground))."""
    L1 = L2 = 0.28
    STRIDE = 0.70                    # one full walk cycle moves the world this many body heights
    STANCE = 0.62                    # fraction of a cycle a foot is on the ground
    DUR = {"stand_idle": 3.2, "look_around": 2.4}
    SS = 3

    def __init__(self, h_px: int):
        self.h = int(h_px)

    def _canvas(self):
        S = self.SS; h = self.h * S
        W, H = int(1.5 * h), int(1.1 * h)
        return W, H, (W // 2, int(1.04 * h))

    def pose(self, action: str, phase: float, stride: float = 1.0):
        from PIL import ImageDraw
        S = self.SS; h = self.h * S; W, H, (ax0, gy) = self._canvas()
        im = Image.new("L", (W, H), 0); d = ImageDraw.Draw(im)
        X = lambda x: ax0 + x * h
        Y = lambda y: gy - y * h
        L1, L2 = self.L1, self.L2; walking = action in ("walk", "run")
        feet = []
        if walking:
            Sx = self.STRIDE * stride; st = self.STANCE; lift = 0.07
            for off in (0.0, 0.5):
                q = (phase + off) % 1.0
                if q < st:
                    fx, fy = 0.5 * st * Sx - q * Sx, 0.0
                else:
                    sw = (q - st) / (1 - st); e = _smooth(sw)
                    fx = -0.5 * st * Sx + st * Sx * e; fy = lift * math.sin(math.pi * sw) ** 0.8
                feet.append([fx, fy, q < st])
            reach = (L1 + L2) * 0.985
            hip_y = min(math.sqrt(max(reach ** 2 - f[0] ** 2, 1e-4)) + f[1] * 0.0 for f in feet if f[2]) if any(f[2] for f in feet) else reach
            hip_y = min(hip_y, reach)
            lean = 0.05; arm_sw = 0.42 * min(1.3, stride); bounce = 0.0
        else:
            br = math.sin(2 * math.pi * phase)
            feet = [[-0.045, 0.0, True], [0.05, 0.0, True]]; hip_y = (L1 + L2) * 0.985 - 0.012 + 0.004 * br
            lean = 0.0; arm_sw = 0.0
        sh_y = hip_y + 0.27; sh_x = lean * 0.27
        def cap(p0, p1, w, fill=255):
            d.line([(X(p0[0]), Y(p0[1])), (X(p1[0]), Y(p1[1]))], fill=fill, width=max(1, int(w * h)))
            for p in (p0, p1):
                r = w * h / 2; d.ellipse([X(p[0]) - r, Y(p[1]) - r, X(p[0]) + r, Y(p[1]) + r], fill=fill)
        # back leg first, then body
        order = sorted(range(2), key=lambda i: feet[i][0])        # the foot further forward is drawn last
        for i in order:
            fx, fy, onground = feet[i]
            kn, an = _ik(0.0, hip_y, fx, fy + 0.025, L1, L2)
            cap((0.0, hip_y), kn, 0.092); cap(kn, an, 0.07)
            # shoe: toe points forward
            sy0 = max(an[1] - 0.025, 0.0)
            d.polygon([(X(an[0] - 0.04), Y(sy0 + 0.05)), (X(an[0] + 0.03), Y(sy0 + 0.05)), (X(an[0] + 0.115), Y(sy0 + 0.012)), (X(an[0] + 0.115), Y(sy0 - 0.0 if onground else sy0)), (X(an[0] - 0.045), Y(sy0))], fill=255)
        # arms (behind coat): swing opposite to the legs
        ang = [math.sin(2 * math.pi * phase) * arm_sw, -math.sin(2 * math.pi * phase) * arm_sw]
        sw = math.sin(2 * math.pi * phase) if walking else 0.0
        hem = hip_y - 0.20 + (0.0)
        coat = [(sh_x - 0.075, sh_y), (sh_x + 0.07, sh_y), (0.105 + 0.012 * sw, hem), (-0.115 - 0.012 * sw, hem - 0.01)]
        coat_poly = [(X(x), Y(y)) for x, y in coat]
        for a in ang[:1]:
            e = (sh_x + math.sin(a) * 0.16, sh_y - 0.02 - math.cos(a) * 0.16); w = (e[0] + math.sin(a + 0.35) * 0.15, e[1] - math.cos(a + 0.35) * 0.15)
            cap((sh_x, sh_y - 0.02), e, 0.062); cap(e, w, 0.055)
        d.polygon(coat_poly, fill=255)
        # satchel hanging at the hip
        if walking or True:
            d.rounded_rectangle([X(-0.035 - 0.02 * sw * 0), Y(hip_y - 0.02), X(0.095), Y(hip_y - 0.15)], radius=int(0.02 * h), fill=255)
        a = ang[1]
        e = (sh_x + math.sin(a) * 0.16, sh_y - 0.02 - math.cos(a) * 0.16); w = (e[0] + math.sin(a + 0.35) * 0.15, e[1] - math.cos(a + 0.35) * 0.15)
        cap((sh_x, sh_y - 0.02), e, 0.062); cap(e, w, 0.055)
        # neck, head, hat (head dips a hair with each step)
        hb = 0.006 * math.sin(4 * math.pi * phase) if walking else 0.0
        hx, hy = sh_x + 0.012 + (0.01 * math.sin(2 * math.pi * phase / 1.0) if action == "look_around" else 0.0), sh_y + 0.095 + hb
        cap((sh_x, sh_y), (hx, hy - 0.03), 0.055)
        r = 0.07 * h; d.ellipse([X(hx) - r, Y(hy) - r, X(hx) + r, Y(hy) + r], fill=255)
        d.ellipse([X(hx - 0.095), Y(hy + 0.07), X(hx + 0.105), Y(hy + 0.032)], fill=255)          # hat brim
        d.rounded_rectangle([X(hx - 0.045), Y(hy + 0.12), X(hx + 0.05), Y(hy + 0.04)], radius=int(0.02 * h), fill=255)   # crown
        im = im.resize((W // S, H // S), Image.LANCZOS)
        rgba = Image.new("RGBA", im.size, INK + (255,)); rgba.putalpha(im)
        return rgba, (ax0 // S, gy // S)

    def duration(self, action):
        return self.DUR.get(action, 1.0)


class Walker:
    """Flat ink silhouette walker.  Sprites come from health_cinema.puppet.render_character_frame, flattened and cached (memory + disk)."""

    GAIT_STEPS = 48
    IDLE_FPS = 12

    def __init__(self, size, character="ink_man", height=0.50, x=0.33, ground_y: Union[float, Sequence[float]] = 0.88, enabled: Optional[Sequence[bool]] = None,
                 cache_dir: Optional[str] = None, cadence_max: float = 2.8):
        self.W, self.H = size
        self.k = self.W / 1920.0
        self.character = character
        self.xf = float(x)
        self.height = float(height)
        self.ground_y = ground_y
        self.enabled = enabled
        self.cadence_max = cadence_max
        self.cache_dir = cache_dir or os.path.join(tempfile.gettempdir(), "travel_sprites")
        self._mem: Dict[tuple, tuple] = {}
        self.ink = InkMan(int(round(self.height * self.H))) if character == "ink_man" else None
        if self.ink:
            class _P:   # the same three calls the procedural cast offers
                @staticmethod
                def action_duration(a): return InkMan.DUR.get(a, 1.0)
            self._p = _P; self.scale = 1.0
            self.stride_walk = self.stride_run = InkMan.STRIDE * self.height * self.H
        else:
            from health_cinema import puppet as _p
            self._p = _p
            ref = 583.0
            self.scale = self.height * self.H / ref
            self.stride_walk = _p.stride_length(character, "walk", self.scale)
            self.stride_run = _p.stride_length(character, "run", self.scale)
        self._shadow = None

    def g(self, i: int) -> float:
        if isinstance(self.ground_y, (int, float)):
            return float(self.ground_y)
        return float(self.ground_y[min(i, len(self.ground_y) - 1)])

    def on(self, i: int) -> bool:
        return True if self.enabled is None else bool(self.enabled[min(i, len(self.enabled) - 1)])

    # sprite cache
    def sprite(self, action: str, idx: int, nq: int, sl: float = 1.0):
        sl = round(min(1.6, max(0.5, sl)) / 0.05) * 0.05 if action in ("walk", "run") else 1.0
        key = (VERSION, self.character, action, idx, nq, round(self.scale, 4), round(self.k, 3), round(sl, 2))
        if key in self._mem:
            return self._mem[key]
        path = os.path.join(self.cache_dir, hashlib.sha1(repr(key).encode()).hexdigest()[:20] + ".pkl")
        val = None
        try:
            with open(path, "rb") as fh:
                im, anchor = pickle.load(fh)
            val = (Image.frombytes("RGBA", im[0], im[1]), anchor)
        except Exception:
            val = None
        if val is None and self.ink:
            ph = idx / float(nq) if action in ("walk", "run") else idx / float(nq)
            spr, anc = self.ink.pose(action, ph, sl)
            flat, pad = _flatten_sprite(spr, self.k)
            val = (flat, (anc[0] + pad, anc[1] + pad))
        elif val is None:
            if action in ("walk", "run"):
                spr, anc = self._p.render_character_frame(self.character, action, 0.0, self.scale, "right", ground_phase=idx / float(nq))
            else:
                dur = self._p.action_duration(action)
                spr, anc = self._p.render_character_frame(self.character, action, dur * idx / float(nq), self.scale, "right")
            flat, pad = _flatten_sprite(spr, self.k)
            val = (flat, (anc[0] + pad, anc[1] + pad))
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                tmp = path + ".tmp%d" % os.getpid()
                with open(tmp, "wb") as fh:
                    pickle.dump(((val[0].size, val[0].tobytes()), val[1]), fh, protocol=4)
                os.replace(tmp, path)
            except Exception:
                pass
        self._mem[key] = val
        return val

    def shadow(self):
        if self._shadow is None:
            w, h = int(self.height * self.H * 0.55), int(self.height * self.H * 0.07)
            m = Image.new("L", (w + 60, h + 60), 0)
            from PIL import ImageDraw
            ImageDraw.Draw(m).ellipse([30, 30, 30 + w, 30 + h], fill=120)
            m = m.filter(ImageFilter.GaussianBlur(8 * self.k))
            im = Image.new("RGBA", m.size, (30, 20, 10, 255))
            im.putalpha(m)
            self._shadow = im
        return self._shadow

    # gait plan for one travel: pick walk/run and a whole number of half cycles so both ends land on a passing pose
    def gait_plan(self, D: float, T: float, peak_ratio: float = 1.35):
        if self.ink:
            cad_cap = self.cadence_max * T / peak_ratio * 2.0
            n = int(max(2, min(round(D / self.stride_walk * 2.0), max(2, int(cad_cap)))))
            return ("walk", n, (D / (n / 2.0)) / self.stride_walk)
        cad_cap = self.cadence_max * T / peak_ratio * 2.0             # max half cycles
        best = None
        for action, stride in (("walk", self.stride_walk), ("run", self.stride_run)):
            nat = D / stride * 2.0
            n = max(2, int(round(nat)))
            if n <= cad_cap or action == "run":
                n = int(max(2, min(n, max(2, int(cad_cap)))))
                slip = (D / (n / 2.0)) / stride
                best = (action, n, slip)
                if slip <= 1.12:
                    break
        return best

    def phase_at(self, plan, f: float) -> float:
        """Gait phase (cycles) for eased travel fraction f; ground velocity == phase velocity * stride_eff (feet locked) by construction."""
        return 0.25 + f * plan[1] / 2.0


# ================================================================================ effects
class _FX:
    def __init__(self, size, seed, grain=3.5, vignette=0.14, flicker=0.010, dust=40, jitter=1, grain_variants=6):
        W, H = size
        self.W, self.H, self.seed = W, H, seed
        self.flicker, self.jitter = flicker, jitter
        rng = np.random.default_rng(seed + 11)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
        v = np.clip(1 - vignette * r2, 0, 1) * 255
        self.vig = Image.fromarray(np.repeat(v[..., None], 3, 2).astype(np.uint8), "RGB") if vignette else None
        self.grain = []
        if grain:
            for _ in range(grain_variants):
                g = np.clip(128 + rng.standard_normal((H + 8, W + 8)) * grain, 0, 255).astype(np.uint8)
                self.grain.append(Image.fromarray(np.repeat(g[..., None], 3, 2), "RGB"))
        self.nd = dust
        self.dx, self.dy = rng.uniform(0, W, dust), rng.uniform(0, H, dust)
        self.dv = rng.uniform(8, 40, dust)
        self.dr = rng.uniform(1.2, 3.5, dust) * (W / 1920.0)
        self.dph = rng.uniform(0, 6.28, dust)

    def jit(self, fi: int, fps: float) -> Tuple[int, int]:
        if not self.jitter:
            return 0, 0
        s = int(fi * 10.0 / fps)
        r = np.random.default_rng(self.seed * 100003 + s)
        return int(r.integers(-self.jitter, self.jitter + 1)), int(r.integers(-self.jitter, self.jitter + 1))

    def apply(self, img: Image.Image, t: float, fi: int, fps: float) -> np.ndarray:
        if self.vig is not None:
            img = ImageChops.multiply(img, self.vig)
        if self.grain:
            r = np.random.default_rng(self.seed * 7 + int(fi * 12.0 / fps))
            g = self.grain[int(r.integers(0, len(self.grain)))]
            ox, oy = int(r.integers(0, 9)), int(r.integers(0, 9))
            img = ImageChops.add(img, g.crop((ox, oy, ox + self.W, oy + self.H)), 1.0, -128)
        if self.flicker:
            gain = 1 + self.flicker * math.sin(t * 23.0) * 0.6 + self.flicker * 0.4 * math.sin(t * 7.1 + 1)
            lut = [min(255, int(i * gain + 0.5)) for i in range(256)] * 3
            img = img.point(lut)
        a = np.array(img)
        for k in range(self.nd):
            x = int((self.dx[k] + self.dv[k] * t * 0.6 + 12 * math.sin(t * 1.3 + self.dph[k])) % self.W)
            y = int((self.dy[k] - self.dv[k] * t) % self.H)
            r = int(self.dr[k])
            ys, xs = slice(max(y - r, 0), y + r + 1), slice(max(x - r, 0), x + r + 1)
            a[ys, xs] = (a[ys, xs] // 2 + 125)
        return a


# ================================================================================ renderer
class TravelRenderer:
    def __init__(self, strip: Strip, sched: Schedule, walker: Optional[Walker] = None, seed: int = 0, fps: float = 30.0, fx: Optional[dict] = None,
                 motion_blur: float = 0.0, resample=Image.BICUBIC):
        if strip.dirs != sched.dirs:
            strip.set_dirs(sched.dirs)
        self.strip, self.sched, self.walker, self.fps = strip, sched, walker, float(fps)
        self.seed = seed
        self.fx = _FX((strip.W, strip.H), seed, **(fx or {}))
        self.motion_blur = motion_blur
        self.resample = resample
        self._wplan: Dict[int, tuple] = {}

    # ---- camera
    def cam(self, t: float, fi: Optional[int] = None):
        j = self.fx.jit(fi, self.fps) if fi is not None else (0, 0)
        return camera_xy(self.strip, self.sched, t, j)

    def _base(self, t: float, fi: int) -> Image.Image:
        st = self.sched.state(t)
        cx, cy, sc = self.cam(t, fi)
        k = st["k"]
        if st["travelling"]:
            return self.strip.view((cx, cy), sc, k, k + 1, st["dir"], self.resample)
        return self.strip.view((cx, cy), sc, k, None, st["dir"], self.resample)

    def _speed_px(self, t: float) -> float:
        a = camera_xy(self.strip, self.sched, t)
        b = camera_xy(self.strip, self.sched, t - 1.0 / self.fps)
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # ---- walker
    def _plan(self, k: int):
        if k not in self._wplan:
            Pd = self.strip.Pw - self.strip.lap - self.strip.tear0
            T = self.sched.travels[k][1] - self.sched.travels[k][0]
            self._wplan[k] = self.walker.gait_plan(Pd, T)
        return self._wplan[k]

    def walker_state(self, t: float) -> Optional[dict]:
        """-> dict(alpha, facing, x_world_off, ground, parts=[(action, idx, nq, weight)]) or None."""
        w = self.walker
        if w is None:
            return None
        st = self.sched.state(t)
        k, trav, u = st["k"], st["travelling"], st["u"]
        dirs = self.sched.dirs
        d_here = dirs[k] if k < len(dirs) else (dirs[-1] if dirs else "right")
        horiz = d_here in ("left", "right")
        if not trav:
            d_dwell = d_here if k < len(dirs) else (dirs[k - 1] if k > 0 and dirs else "right")
            if d_dwell in ("up", "down"):
                d_dwell = dirs[k - 1] if k > 0 and dirs[k - 1] in ("left", "right") else "right"
            alpha = 1.0 if w.on(k) else 0.0
            facing = d_dwell
            ground = w.g(k)
            arrival = self.sched.arrival(k)
            parts = self._idle_parts(t, k, arrival)
            return dict(alpha=alpha, facing=facing, ground=ground, parts=parts, k=k)
        d_next = dirs[k + 1] if k + 1 < len(dirs) else d_here
        if d_next in ("up", "down"):
            d_next = d_here
        # fade rules: leaving/entering a disabled picture, vertical travel or a direction change hide the walker mid-travel
        hide = (not horiz) or (d_next != d_here and d_here in ("left", "right"))
        on_a, on_b = w.on(k), w.on(k + 1)
        fo = _smoothstep(u / 0.3)
        fi_ = _smoothstep((u - 0.7) / 0.3)
        if hide:
            alpha = (1 - fo if on_a else 0.0) if u < 0.5 else (fi_ if on_b else 0.0)
        else:
            alpha = (1.0 - fo) if (on_a and not on_b) else (fi_ if (on_b and not on_a) else (1.0 if on_a else 0.0))
        facing = d_here if (not hide or u < 0.5) else d_next
        if not horiz:
            facing = "right"
        # ground y across the seam
        c0, c1 = self.strip.centres[k], self.strip.centres[k + 1]
        g0, g1 = w.g(k), w.g(k + 1)
        if horiz:
            sgn = 1 if d_here == "right" else -1
            S = c0[0] + sgn * (self.strip.Pw / 2 - self.strip.lap)
            wx = c0[0] + (c1[0] - c0[0]) * st["f"] + ((1.0 - w.xf) if sgn < 0 else w.xf) * self.strip.W - self.strip.W / 2
            ww = float(_smoothstep(sgn * (wx - S) / (90 * self.strip.k) + 0.5))
        else:
            ww = float(_smoothstep(u))
        ground = g0 + (g1 - g0) * ww
        parts = []
        if horiz:
            plan = self._plan(k)
            action, n, slip = plan
            nq = w.GAIT_STEPS
            ph = w.phase_at(plan, st["f"]) % 1.0
            idx = int(round(ph * nq)) % nq
            T = self.sched.travels[k][1] - self.sched.travels[k][0]
            tau = u * T
            wk = float(min(_smoothstep(tau / 0.22), _smoothstep((T - tau) / 0.22)))
            if wk < 1.0:
                for p in self._idle_parts(t, k, self.sched.arrival(k) if tau < T / 2 else self.sched.travels[k][1]):
                    parts.append((p[0], p[1], p[2], p[3] * (1 - wk)))
            parts.append((action, idx, nq, wk))
        return dict(alpha=max(0.0, min(1.0, alpha)), facing=facing, ground=ground, parts=parts, k=k)

    def _idle_parts(self, t: float, k: int, arrival: float):
        w = self.walker
        tau = max(0.0, t - arrival)
        nq = int(round(w._p.action_duration("stand_idle") * w.IDLE_FPS))
        dur_i = w._p.action_duration("stand_idle")
        idx = int(round((tau % dur_i) / dur_i * nq)) % nq
        parts = [("stand_idle", idx, nq, 1.0)]
        dwell = self.sched.departure(k) - arrival
        if dwell >= 4.4 and k % 1 == 0:
            la = 0.9 + (k * 0.37) % 0.6
            dur = w._p.action_duration("look_around")
            lt = tau - la
            if 0 <= lt < dur:
                nql = int(round(dur * w.IDLE_FPS))
                fade = float(min(_smoothstep(lt / 0.2), _smoothstep((dur - lt) / 0.2)))
                parts = [("stand_idle", idx, nq, 1.0 - fade), ("look_around", int(round(lt / dur * nql)) % nql, nql, fade)]
        return parts

    def _draw_walker(self, img: Image.Image, t: float, fi: int):
        ws = self.walker_state(t)
        if ws is None or ws["alpha"] <= 0.003:
            return
        w = self.walker
        st = self.sched.state(t)
        cx, cy, sc = self.cam(t, fi)
        k = st["k"]
        nominal_x, nominal_y = self.strip.centres[k]
        if st["travelling"]:
            nx, ny = self.strip.centres[k + 1]
            nominal_x += (nx - nominal_x) * st["f"]
            nominal_y += (ny - nominal_y) * st["f"]
        face_left = ws["facing"] == "left"
        xf = (1.0 - w.xf) if face_left else w.xf
        wx = nominal_x + (xf - 0.5) * self.strip.W
        wy = nominal_y + (ws["ground"] - 0.5) * self.strip.H
        sx = self.strip.W / 2 + (wx - cx) * sc
        sy = self.strip.H / 2 + (wy - cy) * sc
        sh = w.shadow()
        sa = sh.copy()
        if ws["alpha"] < 1:
            a = sa.getchannel("A").point(lambda v: int(v * ws["alpha"]))
            sa.putalpha(a)
        img.paste(sa, (int(round(sx - sa.width / 2)), int(round(sy - sa.height / 2))), sa)
        for action, idx, nq, wt in ws["parts"]:
            if wt <= 0.004:
                continue
            spr, anc = w.sprite(action, idx, nq, self._plan(ws["k"])[2] if action in ("walk", "run") else 1.0)
            if face_left:
                spr = ImageOps.mirror(spr)
                anc = (spr.width - anc[0], anc[1])
            g = wt * ws["alpha"]
            layer = spr
            if g < 0.999:
                layer = spr.copy()
                layer.putalpha(spr.getchannel("A").point(lambda v, g=g: int(v * g)))
            img.paste(layer, (int(round(sx - anc[0])), int(round(sy - anc[1]))), layer)

    # ---- one frame
    def frame(self, fi: int) -> np.ndarray:
        t = fi / self.fps
        sp = self._speed_px(t) if self.motion_blur else 0.0
        if sp > 6.0:
            n = int(min(10, math.ceil(sp * self.motion_blur / 5.0) + 1))
            acc = None
            for j in range(n):
                tj = t + (j / (n - 1) - 0.5) * self.motion_blur / self.fps
                tj = min(max(tj, 0.0), self.sched.total)
                im = self._base(tj, fi)
                acc = im if acc is None else Image.blend(acc, im, 1.0 / (j + 1))
            img = acc
        else:
            img = self._base(t, fi)
        self._draw_walker(img, t, fi)
        return self.fx.apply(img, t, fi, self.fps)


# ================================================================================ encode / render
def _ffmpeg(path: str, size, fps: float, crf: int = 17, preset: str = "veryfast"):
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % size, "-r", repr(float(fps)), "-i", "-",
                             "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-f", "mp4", path],
                            stdin=subprocess.PIPE)


def _make_walker(walker, size, walker_opts, n):
    if not walker:
        return None
    o = dict(walker_opts or {})
    if "enabled" in o and o["enabled"] is not None and len(o["enabled"]) < n:
        o["enabled"] = list(o["enabled"]) + [o["enabled"][-1]] * (n - len(o["enabled"]))
    return Walker(size, **o)


def _run(rend: TravelRenderer, outs: List[Tuple[str, int, int]], size, fps, crf, cancel, progress, preset="veryfast"):
    """outs = [(tmp_path, first_frame, last_frame_exclusive)].  Frames are rendered once and piped to every encoder whose window contains them."""
    procs = {}
    todo = sorted(set(f for _, a, b in outs for f in range(a, b)))
    try:
        for i, (p, a, b) in enumerate(outs):
            procs[i] = _ffmpeg(p, size, fps, crf, preset)
        for n, fi in enumerate(todo):
            if cancel is not None and cancel():
                raise TravelCancelled("cancelled")
            data = rend.frame(fi).tobytes()
            for i, (p, a, b) in enumerate(outs):
                if a <= fi < b:
                    procs[i].stdin.write(data)
            if progress is not None and n % 5 == 0:
                progress(n / max(len(todo), 1))
        for pr in procs.values():
            pr.stdin.close()
        for pr in procs.values():
            if pr.wait() != 0:
                raise RuntimeError("ffmpeg failed")
        if progress is not None:
            progress(1.0)
    except BaseException:
        for pr in procs.values():
            try:
                pr.stdin.close()
            except Exception:
                pass
            try:
                pr.kill(); pr.wait()
            except Exception:
                pass
        for p, _, _ in outs:
            try:
                os.remove(p)
            except OSError:
                pass
        raise


def _key(stills, sched: Schedule, size, fps, walker, walker_opts, seed, extra=()) -> str:
    h = hashlib.sha1()
    for s in stills:
        if isinstance(s, (str, os.PathLike)):
            try:
                st = os.stat(s)
                h.update(("%s|%d|%d" % (os.fspath(s), st.st_size, int(st.st_mtime))).encode())
            except OSError:
                h.update(os.fspath(s).encode())
        elif isinstance(s, Image.Image):
            h.update(s.tobytes()[:4096] + repr(s.size).encode())
        else:
            h.update(np.asarray(s).tobytes()[:4096])
    h.update(repr((sched.starts, sched.ends, sched.travels, sched.dirs, sched.ease, sched.dwell_drift, sched.dwell_mode, sched.breathe, sched.seed,
                   tuple(size), fps, walker, sorted((walker_opts or {}).items(), key=lambda kv: kv[0]), seed, extra, VERSION)).encode())
    return h.hexdigest()[:16]


def _frames(sched: Schedule, fps: float) -> int:
    return int(math.ceil(sched.total * fps - 1e-6))


def render_travel(stills, schedule: Schedule, out_path: str, fps: float = 30, size=(1920, 1080), walker: Optional[str] = "silhouette", seed: int = 0,
                  cancel: Optional[Callable[[], bool]] = None, progress: Optional[Callable[[float], None]] = None, walker_opts: Optional[dict] = None,
                  seam_style: str = "torn", fx: Optional[dict] = None, crf: int = 17, motion_blur: float = 0.0, use_cache: bool = True) -> str:
    """One continuous mp4 of the whole travel.  Returns out_path.  Raises TravelCancelled (no partial file) when cancel() says so."""
    out_path = os.fspath(out_path)
    stills = list(stills)
    if len(stills) != schedule.n:
        raise ValueError("%d stills for %d scheduled pictures" % (len(stills), schedule.n))
    key = _key(stills, schedule, size, fps, walker, walker_opts, seed, (seam_style, fx and sorted(fx.items()), crf, motion_blur))
    marker = out_path + ".key"
    if use_cache and os.path.exists(out_path) and os.path.exists(marker):
        try:
            if open(marker).read() == key:
                return out_path
        except OSError:
            pass
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    strip = build_strip(stills, size, seam_style, seed=seed, dirs=schedule.dirs)
    rend = TravelRenderer(strip, schedule, _make_walker(walker, size, walker_opts, len(stills)), seed, fps, fx, motion_blur)
    tmp = out_path + ".part.mp4"
    _run(rend, [(tmp, 0, _frames(schedule, fps))], tuple(size), fps, crf, cancel, progress)
    os.replace(tmp, out_path)
    with open(marker, "w") as fh:
        fh.write(key)
    return out_path


def render_travel_slices(stills_by_scene: Dict, scene_windows: Dict, out_dir: str, margin: float = 0.5, fps: float = 30, size=(1920, 1080),
                         walker: Optional[str] = "silhouette", seed: int = 0, cancel=None, progress=None, walker_opts: Optional[dict] = None,
                         schedule: Optional[Schedule] = None, seam_style: str = "torn", fx: Optional[dict] = None, crf: int = 17,
                         motion_blur: float = 0.0, use_cache: bool = True, **plan_kw) -> Dict:
    """The travel rendered once, cut into per-scene mp4 slices (scene window +- margin, whole frames).  -> {scene_no: mp4 path}.

    stills_by_scene {scene_no: still}, scene_windows {scene_no: (start, end)}; scenes are ordered by start.  A slice covers frames
    [floor((start - margin) * fps), ceil((end + margin) * fps)) clipped to the film, so with margin=0 the slices tile the film exactly.
    The scene's first frame is at index round(start*fps) - first_frame of the slice (see <out_dir>/travel_<key>.json).  Cached by inputs + code hash.
    """
    import json
    scenes = sorted(scene_windows, key=lambda s: scene_windows[s][0])
    stills = [stills_by_scene[s] for s in scenes]
    starts = [float(scene_windows[s][0]) for s in scenes]
    ends = [float(scene_windows[s][1]) for s in scenes]
    sched = schedule or plan_schedule(starts, ends, **plan_kw)
    total = _frames(sched, fps)
    key = _key(stills, sched, size, fps, walker, walker_opts, seed, (seam_style, fx and sorted(fx.items()), crf, motion_blur))
    os.makedirs(out_dir, exist_ok=True)
    wins, paths = {}, {}
    for s, (a, b) in zip(scenes, [scene_windows[x] for x in scenes]):
        f0 = max(0, int(math.floor((a - margin) * fps + 1e-6)))
        f1 = min(total, int(math.ceil((b + margin) * fps - 1e-6)))
        if f1 <= f0:
            f1 = min(total, f0 + 1)
        wins[s] = (f0, f1)
        paths[s] = os.path.join(out_dir, "travel_%s_%s_%d_%d.mp4" % (key, str(s), f0, f1))
    todo = [s for s in scenes if not (use_cache and os.path.exists(paths[s]) and os.path.getsize(paths[s]) > 0)]
    if todo:
        strip = build_strip(stills, size, seam_style, seed=seed, dirs=sched.dirs)
        rend = TravelRenderer(strip, sched, _make_walker(walker, size, walker_opts, len(stills)), seed, fps, fx, motion_blur)
        outs = [(paths[s] + ".part.mp4", wins[s][0], wins[s][1]) for s in todo]
        _run(rend, outs, tuple(size), fps, crf, cancel, progress)
        for s, (p, _, _) in zip(todo, outs):
            os.replace(p, paths[s])
    meta = dict(key=key, fps=fps, frames=total, scenes={str(s): dict(path=paths[s], first_frame=wins[s][0], end_frame=wins[s][1],
                                                                 scene_start_in_slice=round(scene_windows[s][0] * fps) - wins[s][0]) for s in scenes})
    with open(os.path.join(out_dir, "travel_%s.json" % key), "w") as fh:
        json.dump(meta, fh, indent=1)
    return {s: paths[s] for s in scenes}
