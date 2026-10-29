"""Fast frame effects for the puppet renderer: one PIL mesh warp carries camera + boil + depth parallax; a numpy pass adds grain, flicker, vignette, dust and the iris.

CALM (default): the artwork is never bent. Warper(calm=True) turns the 'boil' into a RIGID whole-frame stop-motion jitter (one +-1..1.5 px translate per tick, the same for
every mesh vertex) and the depth 'parallax' into one uniform rigid shift, so every mesh cell gets the same affine = a plain camera move. Old callers keep working unchanged;
calm=False restores the old mesh boil / pseudo-depth shear (used only by motion.py legacy=True for A/B comparison).

The warp uses Pillow's MESH transform (affine per cell, done in C) so a 1080p frame costs ~20 ms instead of a numpy bilinear gather; boil fields are tiny
grids shared by every frame of a tick."""
from __future__ import annotations
import math
import numpy as np
from PIL import Image

CELL = 32

def _grid(size, cell=CELL):
    W, H = size
    nx, ny = max(1, math.ceil(W / cell)), max(1, math.ceil(H / cell))
    xs = np.rint(np.linspace(0, W, nx + 1)).astype(np.int32); ys = np.rint(np.linspace(0, H, ny + 1)).astype(np.int32)
    return xs, ys

class Warper:
    """Builds source coordinates at mesh vertices and warps images. One instance per output size."""
    def __init__(self, size, boil_px: float = 2.2, boil_fps: float = 10.0, seed: int = 7, cell: int = CELL, calm: bool = True, jitter_px: float = None):
        self.calm = bool(calm); self.size = size; self.cell = cell; self.xs, self.ys = _grid(size, cell)
        self.vx, self.vy = np.meshgrid(self.xs.astype(np.float32), self.ys.astype(np.float32))
        self.boil_px = boil_px * size[0] / 1920.0; self.boil_fps = boil_fps; self.seed = seed; self._tick = None; self._noise = None
        self._depth_v = None; self._depth_id = None
        sc = size[0] / 1920.0
        # calm: rigid jitter amplitude in px (default: half the old boil, at most 1.5 px at 1080p); 0 disables
        self.jitter_px = float(jitter_px) * sc if jitter_px is not None else min(self.boil_px * .5, 1.5 * sc)

    def jitter(self, t: float):
        """(dx, dy) rigid translate for the tick containing t: changes at boil_fps, never repeats the same direction twice in a row."""
        k = int(t * self.boil_fps); r = np.random.default_rng(self.seed * 100003 + k)
        r0 = np.random.default_rng(self.seed * 100003 + k - 1)
        a0 = r0.uniform(0, 6.2832); a = a0 + math.pi * r.uniform(.55, 1.45)
        m = self.jitter_px * r.uniform(.6, 1.0)
        return m * math.cos(a), m * math.sin(a)

    def _boil(self, t: float):
        if self.calm:
            k = int(t * self.boil_fps)
            if k != self._tick:
                dx, dy = self.jitter(t) if self.jitter_px > 0 else (0.0, 0.0)
                self._noise = [np.full(self.vx.shape, dx, np.float32), np.full(self.vx.shape, dy, np.float32)]; self._tick = k
            return self._noise
        k = int(t * self.boil_fps)
        if k != self._tick:
            r = np.random.default_rng(self.seed * 100003 + k); ny, nx = self.vx.shape
            g = r.standard_normal((2, 14, 25)).astype(np.float32)
            self._noise = [np.asarray(Image.fromarray(g[c]).resize((nx, ny), Image.BICUBIC)) * self.boil_px for c in range(2)]
            self._tick = k
        return self._noise

    def depth_at_vertices(self, depth):
        if depth is None: return None
        if self.calm:   # one uniform value = the mean depth: parallax becomes a rigid shift, never a shear
            if self._depth_id is not id(depth):
                self._depth_v = np.full(self.vx.shape, float(depth.mean()), np.float32); self._depth_id = id(depth); self._depth_ref = depth
            return self._depth_v
        if self._depth_id is not id(depth):
            H, W = depth.shape; yy = np.clip(self.ys, 0, H - 1); xx = np.clip(self.xs, 0, W - 1)
            self._depth_v = depth[np.ix_(yy, xx)]; self._depth_id = id(depth); self._depth_ref = depth
        return self._depth_v

    def source(self, t: float, zoom: float = 1.0, pan=(0.0, 0.0), depth=None, par=(0.0, 0.0), boil: bool = True):
        """Source coordinates (ny+1, nx+1) for each mesh vertex: camera zoom about the centre + pan, depth parallax (near moves more) and boil."""
        W, H = self.size; cx, cy = W / 2, H / 2
        sx = cx + (self.vx - cx) / zoom + pan[0]; sy = cy + (self.vy - cy) / zoom + pan[1]
        dv = self.depth_at_vertices(depth)
        if dv is not None and (par[0] or par[1]):
            sx = sx + (dv - .5) * par[0]; sy = sy + (dv - .5) * par[1]
        if boil:
            bx, by = self._boil(t); sx = sx + bx; sy = sy + by
        return np.clip(sx, 0, W - 1.01), np.clip(sy, 0, H - 1.01)

    def warp(self, img: Image.Image, sx, sy, resample=Image.BILINEAR) -> Image.Image:
        xs, ys = self.xs, self.ys
        x0 = xs[None, :-1].repeat(len(ys) - 1, 0); x1 = xs[None, 1:].repeat(len(ys) - 1, 0)
        y0 = ys[:-1, None].repeat(len(xs) - 1, 1); y1 = ys[1:, None].repeat(len(xs) - 1, 1)
        bbox = np.stack([x0, y0, x1, y1], -1).reshape(-1, 4).tolist()
        quad = np.stack([sx[:-1, :-1], sy[:-1, :-1], sx[1:, :-1], sy[1:, :-1], sx[1:, 1:], sy[1:, 1:], sx[:-1, 1:], sy[:-1, 1:]], -1).reshape(-1, 8).tolist()
        return img.transform(self.size, Image.Transform.MESH, list(zip(map(tuple, bbox), map(tuple, quad))), resample)

class Post:
    """Grain, flicker, vignette, dust and iris on a uint8 RGB frame. Noise pools are made once per size."""
    def __init__(self, size, seed: int = 11, grain: float = 4.0, flicker: float = .012, vignette: float = .16, dust: int = 40, dust_fps: float = 12.0, calm: bool = True):
        self.calm = bool(calm)
        if calm: flicker = min(flicker, .014)
        W, H = size; self.size = size; self.grain = grain; self.flicker = flicker; self.dust_fps = dust_fps
        r = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.vig = (1 - vignette * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)).astype(np.float32)[..., None]
        self._yy, self._xx = yy[::4, ::4], xx[::4, ::4]
        self.pool = []
        for _ in range(6):
            g = r.standard_normal((H // 2, W // 2)).astype(np.float32) * grain
            self.pool.append(np.asarray(Image.fromarray(g).resize((W, H), Image.BILINEAR))[..., None])
        self.n = dust; sc = W / 1920.0
        self.dx = r.uniform(0, W, dust); self.dy = r.uniform(0, H, dust); self.dv = r.uniform(8, 40, dust) * sc
        self.dr = np.maximum(1, (r.uniform(1.2, 3.6, dust) * sc)).astype(int); self.dp = r.uniform(0, 6.28, dust); self.dal = r.uniform(.25, .6, dust)
        self.seed = seed

    def apply(self, img: Image.Image, t: float, k: int, dark: float = 0.0, dark_xy=(.5, .5), dust: bool = True, fade: float = 0.0) -> np.ndarray:
        W, H = self.size
        a = np.asarray(img).astype(np.float32)
        flick = 1 + self.flicker * math.sin(t * 23.0) * math.sin(t * 7.1 + 1.3)
        a *= self.vig * flick; a += self.pool[(k // 2 + self.seed) % 6][::-1 if (k // 2) % 2 else 1]
        if dark > 0.001:
            cx, cy = dark_xy[0] * W, dark_xy[1] * H
            rad = (1.0 - dark) * math.hypot(W, H) * .62 + 1
            d = np.hypot(self._xx - cx, self._yy - cy) / rad
            m = np.clip((d - .85) / .35, 0, 1) ** 1.2 if dark < .999 else np.ones_like(d)
            m = np.asarray(Image.fromarray(m.astype(np.float32)).resize((W, H), Image.BILINEAR))[..., None]
            a = a * (1 - m * (1 if dark > .02 else dark / .02))
        if fade > 0: a *= (1 - fade)
        np.clip(a, 0, 255, out=a); out = a.astype(np.uint8)
        if dust and self.n:
            kk = t if self.calm else int(t * self.dust_fps) / self.dust_fps   # calm: dust drifts smoothly
            for i in range(self.n):
                x = int((self.dx[i] + self.dv[i] * kk * .6 + 12 * math.sin(kk * 1.3 + self.dp[i])) % W); y = int((self.dy[i] - self.dv[i] * kk) % H); r = int(self.dr[i])
                reg = out[max(y - r, 0):y + r + 1, max(x - r, 0):x + r + 1]
                reg += (np.maximum(250 - reg.astype(np.float32), 0) * self.dal[i]).astype(np.uint8)
        return out
