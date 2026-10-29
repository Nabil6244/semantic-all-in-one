"""Layered RIGID parallax for one still: the picture is cut into FAR / MID / NEAR layers by a real depth map (puppet/depth.py); every layer is a flat paper cut-out that
moves as ONE affine (translate + zoom), at its own speed, over the layer behind it. Nothing is ever bent, so engraved lines stay straight (no water look).
The gaps that open up behind a near layer show an inpainted plate. Pictures with no usable depth structure return None from build() and the caller keeps the plain camera move.

    rig = build(still_path, size, fps, duration, seed, params)  -> LayerRig | None
    rig.frame(k) -> uint8 RGB array;  render_parallax(still, out, duration, ...) -> out (mp4, cached)
params: amount (parallax strength, default 1.0), mode ('lateral' | 'push'; default by seed), jitter_px (default 1.0)."""
from __future__ import annotations
import hashlib, json, math, os, shutil, tempfile
import numpy as np
from PIL import Image, ImageFilter

from . import depth as _depth, effects, scene
from . import motion as _m

VERSION = "1"
T1, T2 = 0.38, 0.66            # depth thresholds far|mid|near (depth is normalised 0..1, 1 = near)
FACT = (0.45, 1.0, 1.75)       # layer speed factors far, mid, near
ZBASE = (1.06, 1.085, 1.115)

def _mask_img(m: np.ndarray, erode: int = 2, feather: float = 1.1) -> Image.Image:
    im = Image.fromarray((m * 255).astype(np.uint8))
    if erode > 0: im = im.filter(ImageFilter.MinFilter(2 * erode + 1))
    return im.filter(ImageFilter.GaussianBlur(feather))

def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    """Dilate by r px. Done at 1/4 size with a box blur (PIL's MaxFilter is O(r^2) per pixel: minutes at r = 70)."""
    if r <= 0: return m
    H, W = m.shape; q = 4; sm = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((W // q, H // q), Image.BILINEAR), np.float32) / 255.0
    b = scene._box(scene._box((sm > .3).astype(np.float32), max(1, r // q)), max(1, r // q // 2)) > .02
    return np.asarray(Image.fromarray(b.astype(np.uint8) * 255).resize((W, H), Image.BILINEAR)) > 100

class LayerRig:
    def __init__(self, fit_rgb: Image.Image, d: np.ndarray, size, fps, duration, seed, params):
        p = dict(params or {}); self.size = tuple(size); W, H = self.size; self.fps = fps; self.T = max(duration, 1e-3); sc = W / 1920.0; self.sc = sc
        rng = np.random.default_rng(seed * 7919 + 31)
        amt = float(np.clip(p.get("amount", 1.0), 0.2, 2.0)); self.amt = amt
        db = scene._box(scene._box(d, 3), 3); near = db > T2; mid = (db > T1) & ~near
        rgb = np.asarray(fit_rgb, np.uint8)
        # holes: what each nearer layer can uncover
        R = max(4, int(round(6 * sc))); near_d = _dilate(near, R); mn_d = _dilate(near | mid, R)   # a layer can only uncover its own footprint (+ a halo margin), which it covers at rest
        far_fill = _m._inpaint(rgb, mn_d); far = np.where(mn_d[..., None], far_fill, rgb.astype(np.float32)).clip(0, 255).astype(np.uint8)
        mid_fill = _m._inpaint(rgb, near_d); midrgb = np.where(near_d[..., None], mid_fill, rgb.astype(np.float32)).clip(0, 255).astype(np.uint8)
        self.layers = [(Image.fromarray(far), None),
                       (Image.fromarray(midrgb), _mask_img(mid | near_d)),
                       (fit_rgb, _mask_img(near))]
        mode = p.get("mode")
        if mode is not None and mode not in _m.MODES + ("lateral", "push"): raise _m.MotionError(f"unknown mode {mode!r}; use one of {_m.MODES}")
        self.mode = "push" if mode in ("push_in", "pull_out", "diag_in", "diag_out", "push") else "lateral" if mode else ("lateral" if rng.random() < .65 else "push")
        self.sign = float(rng.choice([-1.0, 1.0])); self.ysign = float(rng.choice([-1.0, 1.0])) * .25
        self.ph = rng.uniform(0, 6.28)
        self.jit = effects.Warper(self.size, boil_fps=float(np.clip(p.get("boil_fps", rng.uniform(8, 12)), 8, 12)), seed=seed + 3, calm=True, jitter_px=float(np.clip(p.get("jitter_px", 1.0), 0, 3)))
        self.post = effects.Post(self.size, seed=seed + 5, grain=4.0, flicker=.010, vignette=.16, dust=26)
        self.vig0 = self.post.vig.copy(); self.lphase = rng.uniform(0, 6.28, 4)
        self._boxes = {}
        self.A = 40 * sc * amt                                # near-layer travel is FACT[2] * A

    def _u(self, t):
        v = t / self.T + .04 * math.sin(2 * math.pi * 1.3 * t / self.T + self.ph)
        return min(max((v + .04) / 1.08, 0.0), 1.0)

    def affine(self, i, t, jitter=True):
        W, H = self.size; cx, cy = W / 2, H / 2; u = self._u(t); f = FACT[i]
        dz = (.035 + .012 * min(self.T, 6)) * f * (self.amt * .7) if self.mode == "push" else 0.0
        z = ZBASE[i] + dz * u
        px = (self.sign * self.A * f * (2 * u - 1)) * (0.45 if self.mode == "push" else 1.0)
        py = self.ysign * self.A * f * (2 * u - 1) * .6
        jx, jy = self.jit.jitter(t) if jitter else (0.0, 0.0)
        return 1 / z, 0.0, cx - cx / z + px + jx, 0.0, 1 / z, cy - cy / z + py + jy

    def cam(self, t):
        """(zoom, px, py, 0, 0) of the MID layer: same shape as motion's rigs, used by links to make clips meet."""
        co = self.affine(1, t, jitter=False); return 1 / co[0], co[2] - self.size[0] / 2 * (1 - co[0]), co[5] - self.size[1] / 2 * (1 - co[4]), 0.0, 0.0

    def _box(self, i):
        """Screen box the layer can ever touch (its alpha bbox grown by the largest zoom/pan it makes): only this region is transformed each frame."""
        if i in self._boxes: return self._boxes[i]
        a = self.layers[i][1]; W, H = self.size
        bb = a.point(lambda v: 255 if v > 3 else 0).getbbox() if a is not None else (0, 0, W, H)
        if bb is None: bb = (0, 0, 0, 0)
        g = int(self.A * FACT[i] * 1.3 + 0.2 * max(W, H) * (self.amt * .7) * FACT[i] * .15 + 24 * self.sc)
        z = ZBASE[i] + (.035 + .012 * min(self.T, 6)) * FACT[i] * self.amt * .7
        cx, cy = W / 2, H / 2
        x0 = int(max(0, (bb[0] - cx) * z + cx - g)); y0 = int(max(0, (bb[1] - cy) * z + cy - g)); x1 = int(min(W, (bb[2] - cx) * z + cx + g)); y1 = int(min(H, (bb[3] - cy) * z + cy + g))
        self._boxes[i] = (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None
        return self._boxes[i]

    def frame(self, k):
        t = k / self.fps; out = None
        for i, (rgb, a) in enumerate(self.layers):
            co = self.affine(i, t)
            if a is None:
                out = rgb.transform(self.size, Image.Transform.AFFINE, co, Image.BILINEAR); continue
            bx = self._box(i)
            if bx is None: continue
            x0, y0, x1, y1 = bx; sz = (x1 - x0, y1 - y0); a_, b_, c_, d_, e_, f_ = co
            rc = (a_, b_, c_ + a_ * x0 + b_ * y0, d_, e_, f_ + d_ * x0 + e_ * y0)
            tr = rgb.transform(sz, Image.Transform.AFFINE, rc, Image.BILINEAR)
            out.paste(tr, (x0, y0), a.transform(sz, Image.Transform.AFFINE, rc, Image.BILINEAR))
        ph = self.lphase; Wo, Ho = self.size; gy, gx = np.mgrid[0:27, 0:48].astype(np.float32)
        lx = 24 + 16 * math.sin(t * .31 + ph[0]); ly = 13 + 7 * math.sin(t * .23 + ph[1])
        L = 1 + .055 * np.exp(-(((gx - lx) / 15) ** 2 + ((gy - ly) / 9) ** 2)) - .02
        self.post.vig = self.vig0 * _m._to_grid(L, (Ho, Wo))[..., None]
        return np.ascontiguousarray(self.post.apply(out, t, k))

def usable(d: np.ndarray) -> bool:
    db = d[::4, ::4]; near = (db > T2).mean(); far = (db <= T1).mean()
    return 0.04 <= near <= 0.55 and far >= 0.08 and float(db.std()) >= 0.14

def build(still, size=(1920, 1080), fps=30, duration=4.0, seed=0, params=None):
    if not _depth.available(): return None
    try: sc = scene.analyse(still)
    except scene.SceneError: return None
    fit = sc.fit(tuple(size)); full = _depth.depth_map(still)
    d = np.asarray(Image.fromarray(full, "F").resize(tuple(size), Image.BILINEAR), np.float32)
    # the still is cover-fitted to `size`: crop the depth the same way (fit() already letterboxes by cover; reuse its geometry via a same-size resize of the source)
    src = Image.open(still).convert("RGB")
    if src.size != tuple(size):
        s = max(size[0] / src.width, size[1] / src.height); w2, h2 = round(src.width * s), round(src.height * s)
        x0, y0 = (w2 - size[0]) // 2, (h2 - size[1]) // 2
        d = np.asarray(Image.fromarray(full, "F").resize((w2, h2), Image.BILINEAR), np.float32)[y0:y0 + size[1], x0:x0 + size[0]]
        rgb = src.resize((w2, h2), Image.LANCZOS).crop((x0, y0, x0 + size[0], y0 + size[1]))
    else:
        rgb = src
    if not usable(d): return None
    return LayerRig(rgb, d, size, fps, duration, seed, params)

def render_parallax(still, out_path, duration, fps=30, size=(1920, 1080), seed=0, params=None, cancel=None):
    rig = build(still, size, fps, duration, seed, params)
    if rig is None: return None
    n = max(1, int(round(duration * fps))); fd, tmp = tempfile.mkstemp(suffix=".part.mp4", dir=os.path.dirname(os.path.abspath(out_path)) or "."); os.close(fd)
    sink = _m._Sink(size, fps, tmp)
    try:
        for i in range(n):
            if cancel and cancel(): raise _m.Cancelled("cancelled")
            sink.write(rig.frame(i).tobytes())
        sink.close(); os.replace(tmp, out_path)
    except BaseException:
        sink.abort()
        try: os.unlink(tmp)
        except OSError: pass
        raise
    return out_path
