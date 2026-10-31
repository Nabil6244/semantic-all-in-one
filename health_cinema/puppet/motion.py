"""Continuous, CALM motion for a single still (the 'never static' layer of Normal-style videos).

    render_motion(still_path, out_path, duration, fps=30, size=(1920, 1080), seed=0, params=None, cancel=None, progress=None) -> out_path

One mp4 (libx264 crf 17 yuv420p, no audio, exactly round(duration*fps) frames). The artwork is NEVER bent: every frame is one RIGID affine of the still (Pillow transform),
so engraved lines stay straight and sharp. Edges can never show (zoom margin covers pan + rotation + jitter).
  * camera: push-in / pull-out / lateral drift / diagonal picked by seed, eased but never stopping, slow drift and a rotation <= 0.4 deg (per seed); the clip ends mid-move so it can be cut.
  * stop-motion paper jitter: the whole frame translates +-jitter_px (default 1.0, 0 disables) at 8-12 fps (classic cut-out feel, rigid).
  * film grain, light flicker, vignette, drifting dust and a slow drifting light pool (effects.Post, none of them move the picture).
  * living details, detected conservatively (if unsure nothing is done): a red dot pulses / a red dashed route gets a travelling glow (colour only, no geometry);
    a clean foreground cut-out piece (scene.py occluder) slides a few px as a RIGID paper layer over an inpainted plate, with a soft shadow on the plate (no bending).
params: intensity 'low'|'medium'|'high' or a number (default 'medium'), mode ('push_in','pull_out','drift_l','drift_r','diag_in','diag_out'), living (bool, default True),
        jitter_px (default 1.0), boil_fps (8..12), layers (bool, default True), legacy (bool: the old mesh boil/parallax/billow/sway, for A/B only).
warp_energy(video_or_frames) measures how much of the motion is NOT a rigid camera move (should be ~0).
The cache key covers the still's pixels, duration, fps, size, seed, params, VERSION and puppet/*.py."""
from __future__ import annotations
import hashlib, json, math, os, shutil, subprocess, tempfile, threading
from collections import deque
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

from . import effects, scene

VERSION = "2"
_HERE = Path(__file__).resolve().parent
CACHE_DIR = scene.ROOT / "out" / "puppet_cache" / "motion"
INTENSITY = {"low": .55, "medium": 1.0, "high": 1.5}
MODES = ("push_in", "pull_out", "drift_l", "drift_r", "diag_in", "diag_out")

class MotionError(RuntimeError): pass
class Cancelled(MotionError): pass

# ---------------------------------------------------------------- small helpers
def _ffmpeg() -> str:
    try:
        from .. import assets
        p = assets.ffmpeg_path()
        if p: return p
    except Exception: pass
    return shutil.which("ffmpeg") or "ffmpeg"

def _code_hash() -> str:
    h = hashlib.sha256(VERSION.encode())
    for f in sorted(_HERE.glob("*.py")): h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()[:16]

def _file_hash(path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for c in iter(lambda: fh.read(1 << 20), b""): h.update(c)
    except OSError as e:
        raise MotionError(f"cannot read still {path}: {e}") from e
    return h.hexdigest()[:20]

def _intensity(v) -> float:
    if isinstance(v, str):
        if v not in INTENSITY: raise MotionError(f"intensity must be one of {sorted(INTENSITY)} or a number, got {v!r}")
        return INTENSITY[v]
    try: return float(np.clip(float(v), 0.0, 2.0))
    except (TypeError, ValueError): raise MotionError(f"bad intensity {v!r}")

def _label(mask: np.ndarray):
    """4-connected components of a small boolean mask -> list of (area, x0, y0, x1, y1, cx, cy, ys, xs)."""
    h, w = mask.shape; seen = np.zeros_like(mask, bool); out = []
    for y, x in np.argwhere(mask):
        if seen[y, x]: continue
        q = deque([(y, x)]); seen[y, x] = True; pts = []
        while q:
            p, r = q.popleft(); pts.append((p, r))
            for dp, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                pp, rr = p + dp, r + dr
                if 0 <= pp < h and 0 <= rr < w and mask[pp, rr] and not seen[pp, rr]:
                    seen[pp, rr] = True; q.append((pp, rr))
        a = np.array(pts); ys, xs = a[:, 0], a[:, 1]
        out.append((len(pts), int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()), float(xs.mean()), float(ys.mean()), ys, xs))
    return out

def _small(img: Image.Image, w: int) -> np.ndarray:
    return np.asarray(img.resize((w, max(1, round(img.height * w / img.width))), Image.BILINEAR), dtype=np.float32)

def _blur(a: np.ndarray, r: float) -> np.ndarray:
    k = max(1, int(round(r)))
    return scene._box(scene._box(a.astype(np.float32), k), k)

def _to_grid(a: np.ndarray, shape) -> np.ndarray:
    return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize((shape[1], shape[0]), Image.BILINEAR))

# ---------------------------------------------------------------- detection (conservative: returns None / [] when unsure)
def detect_red(rgb: Image.Image):
    """Saturated red marks: {'dots': [(x, y, r)], 'route': [(x, y)...] or None} in fractions of the frame. Sepia/engraved paper is never this red."""
    a = _small(rgb, 960); H, W = a.shape[:2]; r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > 155) & (r - g > 105) & (r - b > 95) & (g < 85)   # pure marker red; rust, brick and ribbons stay below this
    n = int(red.sum())
    if n < 20 or n > .012 * H * W: return None
    comps = [c for c in _label(red) if c[0] >= 2]
    if not comps or len(comps) > 150: return None
    dots, small = [], []
    for ar, x0, y0, x1, y1, cx, cy, _, _ in comps:
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if ar > .004 * H * W: continue
        if ar >= 30 and max(bw, bh) <= 1.7 * min(bw, bh) and ar >= .55 * bw * bh: dots.append((cx / W, cy / H, math.sqrt(ar / math.pi) / W))
        else: small.append((cx / W, cy / H, ar))
    route = None
    if len(small) >= 8:
        P = np.array([(x * W, y * H) for x, y, _ in small]); c = P - P.mean(0)
        axis = np.linalg.svd(c, full_matrices=False)[2][0]; order = [int(np.argmin(c @ axis))]; left = set(range(len(P))) - set(order)
        steps = []
        while left:
            last = P[order[-1]]; j = min(left, key=lambda i: float(np.hypot(*(P[i] - last)))); steps.append(float(np.hypot(*(P[j] - last)))); order.append(j); left.discard(j)
        med = float(np.median(steps))
        keep = len(order)
        for i, s in enumerate(steps):
            if s > 3.2 * med + 2: keep = i + 1; break
        if keep >= 8 and sum(steps[:keep - 1]) > .12 * W: route = [(P[i][0] / W, P[i][1] / H) for i in order[:keep]]
    if not dots and not route: return None
    if route and dots:   # the head runs toward the dot that sits nearest an end of the chain
        d0 = min(math.hypot(route[0][0] - x, route[0][1] - y) for x, y, _ in dots); d1 = min(math.hypot(route[-1][0] - x, route[-1][1] - y) for x, y, _ in dots)
        if d0 < d1: route = route[::-1]
    return {"dots": dots[:3], "route": route}

def detect_smoke(rgb: Image.Image):
    """Soft vertex-free blobs: list of (cx, cy, rx, ry) fractions for bright, calm regions in the upper part of the picture that are bordered by darker detail."""
    a = _small(rgb, 160); H, W = a.shape[:2]; lum = a.mean(2)
    gy, gx = np.gradient(_blur(lum, 1)); tex = _blur(np.hypot(gx, gy), 2.5)
    up = np.zeros((H, W), bool); up[: int(H * .6)] = True
    pic = _blur((lum < 205).astype(np.float32), 3) > .25            # inside the printed picture, not the page margin
    lo = np.percentile(lum[up & pic], 62) if (up & pic).sum() > 200 else 255
    cand = up & pic & (_blur(lum, 2.5) > max(lo, 150)) & (tex < np.percentile(tex[up & pic], 38) if (up & pic).sum() > 200 else False)
    out = []
    for ar, x0, y0, x1, y1, cx, cy, _, _ in sorted(_label(cand), key=lambda c: -c[0])[:2]:
        if not (.012 * H * W <= ar <= .22 * H * W): continue
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if bw > .6 * W or ar < .4 * bw * bh: continue
        # must be a blob in front of detail, not an empty margin: darker textured ring around it
        ring = lum[max(y0 - 4, 0):y1 + 5, max(x0 - 4, 0):x1 + 5]
        if ring.size and ring.std() < 14: continue
        out.append((cx / W, cy / H, bw / W / 2, bh / H / 2))
    return out

def detect(path) -> dict:
    """Debug view of what the still triggers: {'red': ..., 'smoke': [...], 'sway': n_pieces}."""
    sc = scene.analyse(path); fit = sc.fit((480, 270))
    return {"red": detect_red(fit.rgb), "smoke": detect_smoke(fit.rgb), "sway": len(_label(np.asarray(fit.occ.resize((96, 54))) > 100))}

# ---------------------------------------------------------------- the rig
def _glow(r: int) -> np.ndarray:
    y, x = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32); d = np.hypot(x, y) / r
    return np.clip(1 - d, 0, 1) ** 2

class _LegacyRig:
    """OLD motion (mesh boil, pseudo-depth parallax, smoke billow, sway) kept only for A/B comparison: params legacy=True. All per-clip state; frame(k) -> uint8 RGB array. coords(k) exposes the unclipped mesh source coordinates (used by the tests)."""
    def __init__(self, still, size, fps, duration, seed, params):
        p = dict(params or {}); self.out = tuple(int(v) for v in size); ws = float(np.clip(p.get("warp_scale", .75), .4, 1.0))
        self.size = self.out if ws >= .99 else (max(2, round(self.out[0] * ws) // 2 * 2), max(2, round(self.out[1] * ws) // 2 * 2))   # the mesh warp runs at this size
        W, H = self.size; self.fps = fps; self.T = max(duration, 1e-3)
        self.I = _intensity(p.get("intensity", "medium")); I = self.I; self.sc = sc = W / 1920.0
        rng = np.random.default_rng(seed * 7919 + 17); self.rng = rng
        try: self.scene = scene.analyse(still)
        except scene.SceneError as e: raise MotionError(str(e)) from e
        self.fit = fit = self.scene.fit(self.size); self.img = fit.rgb
        bf = float(np.clip(p.get("boil_fps", rng.uniform(8, 12)), 8, 12))
        self.warper = effects.Warper(self.size, boil_px=2.0 * I, boil_fps=bf, seed=seed + 3, cell=24, calm=False)
        self.post = effects.Post(self.out, seed=seed + 5, grain=3.5 + 1.2 * I, flicker=.008 + .006 * I, vignette=.16, dust=int(round(34 * I)), calm=False)
        self.vig0 = self.post.vig.copy(); self.depth = fit.depth
        self.living = bool(p.get("living", True)) and I > 0
        self._setup_extras(fit)
        self._setup_camera(p.get("mode"), rng)
        self.lphase = rng.uniform(0, 6.28, 4); self._k = -1

    # -- camera
    def _setup_camera(self, mode, rng):
        W, H = self.size; sc, I, T = self.sc, self.I, self.T
        if mode is None: mode = MODES[int(rng.choice(len(MODES), p=[.24, .14, .18, .18, .16, .10]))]
        if mode not in MODES: raise MotionError(f"unknown mode {mode!r}; use one of {MODES}")
        self.mode = mode
        self.par_max = 26 * sc * I                                     # depth parallax range across the depth map (px)
        self.sway_max = (7 * sc * I if (self.living and self.sway) else 0.0) + (6 * sc * I if (self.living and self.smoke is not None) else 0.0)
        boil = 3.0 * 2.0 * I * sc
        self.Rx = boil + self.par_max * .5 + self.sway_max + 4 * sc; self.Ry = boil + self.par_max * .3 + self.sway_max + 4 * sc
        dz = float(np.clip(.02 + .016 * T, .03, .15)) * (.5 + .5 * I)
        z_lo = 1.09 + .04 * (I > 1)
        z0, z1 = {"push_in": (z_lo, z_lo + dz), "pull_out": (z_lo + dz, z_lo), "diag_in": (z_lo, z_lo + dz * .8), "diag_out": (z_lo + dz * .8, z_lo)}.get(mode, (z_lo + .03, z_lo + .03 + dz * .35))
        self.z0, self.z1 = z0, z1; zmin = min(z0, z1)
        availx = max((1 - 1 / zmin) * W / 2 - self.Rx, 0.0); availy = max((1 - 1 / zmin) * H / 2 - self.Ry, 0.0)
        sgn = float(rng.choice([-1.0, 1.0]))
        spd = {"drift_l": 36, "drift_r": 36, "diag_in": 26, "diag_out": 26, "push_in": 16, "pull_out": 16}[mode] * sc * I
        ax = min(availx * .92, .5 * spd * T); ay = min(availy * .92, .5 * spd * T * .55)
        dx = {"drift_l": -1.0, "drift_r": 1.0}.get(mode, sgn * (.7 if mode.startswith("diag") else .6)); dy = {"diag_in": -sgn * .8, "diag_out": sgn * .8}.get(mode, float(rng.choice([-1, 1])) * .3)
        self.px0, self.px1 = -dx * ax, dx * ax; self.py0, self.py1 = -dy * ay, dy * ay
        self.par_dir = (1.0 if dx >= 0 else -1.0)
        self.ph = rng.uniform(0, 6.28)

    def _u(self, t):
        """Eased progress in 0..1 whose speed varies between ~.6x and ~1.4x but never reaches 0."""
        v = t / self.T + .04 * math.sin(2 * math.pi * 1.3 * t / self.T + self.ph)
        return (v + .04) / 1.08

    def cam(self, t):
        u = self._u(t); lerp = lambda a, b: a + (b - a) * u
        z = lerp(self.z0, self.z1); px, py = lerp(self.px0, self.px1), lerp(self.py0, self.py1)
        par = self.par_max * (self.par_dir * (2 * u - 1) * .7 + .3 * math.sin(t * .9 + self.ph))
        return z, px, py, par, par * .35 * math.sin(t * .6 + self.ph * 2)

    # -- living details
    def _setup_extras(self, fit):
        W, H = self.size; wp = self.warper; ny1, nx1 = wp.vx.shape
        self.red = None; self.smoke = None; self.sway = []
        self.sx_phase = np.sin(wp.vx / W * 9.0) * 3 + wp.vy / H * 7.0
        if not self.living: return
        r = detect_red(fit.rgb)
        if r:
            self.red = r; self.glow_big = _glow(max(6, int(round(34 * self.sc))))
            self.glow_small = _glow(max(4, int(round(16 * self.sc))))
        sm = detect_smoke(fit.rgb)
        if sm:
            m = np.zeros((fit.rgb.height // 4, fit.rgb.width // 4), np.float32); Hm, Wm = m.shape
            yy, xx = np.mgrid[0:Hm, 0:Wm].astype(np.float32)
            for cx, cy, rx, ry in sm:
                m = np.maximum(m, np.clip(1 - np.hypot((xx / Wm - cx) / max(rx * 1.15, .02), (yy / Hm - cy) / max(ry * 1.15, .02)), 0, 1))
            self.smoke = _to_grid(_blur(m, 2.0), (ny1, nx1)).clip(0, 1) ** .8
        occ = np.asarray(fit.occ, dtype=np.float32) / 255.0
        if occ.max() > .5:
            ov = _to_grid(_blur(occ[::4, ::4], 1.5), (ny1, nx1)); comps = _label(ov > .5)
            for ar, x0, y0, x1, y1, *_ in comps:
                if ar < 12: continue
                yy = np.arange(ny1, dtype=np.float32)[:, None]
                w = np.clip((y1 + 1 - yy) / max(y1 - y0 + 1, 1), 0, 1) ** 1.4 * np.ones((1, nx1), np.float32)
                xs = np.zeros((ny1, nx1), np.float32); xs[y0:y1 + 1, x0:x1 + 1] = 1
                self.sway.append(ov * w * xs * (ov > .1))
        self.sway_phase = self.rng.uniform(0, 6.28, max(1, len(self.sway)))

    def extras(self, t):
        sc, I = self.sc, self.I; wp = self.warper; ex = np.zeros(wp.vx.shape, np.float32); ey = np.zeros_like(ex)
        if not self.living: return ex, ey
        if self.smoke is not None:
            ph = self.sx_phase; s = 6 * sc * I
            ex += self.smoke * s * np.sin(2 * math.pi * .21 * t + ph); ey += self.smoke * s * .7 * np.sin(2 * math.pi * .16 * t + ph * 1.7 + 1.0) - self.smoke * s * .25
        for i, w in enumerate(self.sway):
            f = self.sway_phase[i]; ex += w * 7 * sc * I * (.75 * math.sin(2 * math.pi * .42 * t + f) + .25 * math.sin(2 * math.pi * 1.1 * t + 2 * f))
        return ex, ey

    def coords(self, k, clip=True):
        W, H = self.size; cx, cy = W / 2, H / 2; wp = self.warper; t = k / self.fps
        z, px, py, par, parv = self.cam(t)
        sx = cx + (wp.vx - cx) / z + px; sy = cy + (wp.vy - cy) / z + py
        dv = wp.depth_at_vertices(self.depth)
        sx = sx + (dv - .5) * par; sy = sy + (dv - .5) * parv
        bx, by = wp._boil(t); ex, ey = self.extras(t)
        sx = sx + bx + ex; sy = sy + by + ey
        if clip: sx, sy = np.clip(sx, 0, W - 1.01), np.clip(sy, 0, H - 1.01)
        return sx, sy

    def _marks(self, t):
        """Image with the red-mark glow added (or the plain fitted still); positions are in still space so the mesh carries them with the camera."""
        if not self.red: return self.img
        W, H = self.size; a = np.array(self.img, dtype=np.uint8); I = self.I
        def blit(g, x, y, k, col):
            r = g.shape[0] // 2; x0, y0 = int(round(x)) - r, int(round(y)) - r
            xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + g.shape[1], W), min(y0 + g.shape[0], H)
            if xb <= xa or yb <= ya: return
            add = g[ya - y0:yb - y0, xa - x0:xb - x0, None] * (k * np.array(col, np.float32))
            reg = a[ya:yb, xa:xb]; reg[...] = np.minimum(reg.astype(np.float32) + add, 255).astype(np.uint8)
        for x, y, rr in self.red["dots"]:
            pulse = .5 + .5 * math.sin(2 * math.pi * .85 * t); g = self.glow_big
            blit(g, x * W, y * H, (.35 + .65 * pulse) * .75 * min(I, 1.4), (255, 90, 60))
        route = self.red["route"]
        if route:
            P = np.array([(x * W, y * H) for x, y in route]); seg = np.hypot(*np.diff(P, axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)]); L = float(cum[-1])
            head = ((t / max(2.2, L / (W * .22))) % 1.0) * (L * 1.15) - .08 * L
            for i, (x, y) in enumerate(P):
                k = math.exp(-((cum[i] - head) / (.09 * L + 1)) ** 2)
                if k > .05: blit(self.glow_small, x, y, k * .85 * min(I, 1.4), (255, 80, 50))
            if 0 <= head <= L:
                j = int(np.searchsorted(cum, head, side="right")) - 1; j = min(max(j, 0), len(P) - 2); f = (head - cum[j]) / max(seg[j], 1e-6)
                hx, hy = P[j] + (P[j + 1] - P[j]) * f; blit(self.glow_big, hx, hy, .9 * min(I, 1.4), (255, 150, 90))
        return Image.fromarray(a)

    def frame(self, k):
        t = k / self.fps; W, H = self.out
        sx, sy = self.coords(k)
        out = self.warper.warp(self._marks(t), sx, sy)
        if self.size != self.out: out = out.resize(self.out, Image.BICUBIC)
        # slow drifting light pool folded into the vignette multiplier
        ph = self.lphase; gy, gx = np.mgrid[0:27, 0:48].astype(np.float32)
        lx = 24 + 16 * math.sin(t * .31 + ph[0]); ly = 13 + 7 * math.sin(t * .23 + ph[1])
        L = 1 + .055 * self.I * np.exp(-(((gx - lx) / 15) ** 2 + ((gy - ly) / 9) ** 2)) - .02 * self.I
        self.post.vig = self.vig0 * _to_grid(L, (H, W))[..., None]
        return np.ascontiguousarray(self.post.apply(out, t, k))

# ---------------------------------------------------------------- the calm rig (default): rigid affine camera + rigid paper layer + colour-only life
def _edge_ok(lum, m, comp_mask):
    """True when the outline of the piece sits on a real tonal edge (inside vs outside differ) for most of its length."""
    cm = comp_mask.astype(np.float32); out = 1 - cm
    inner = scene._box(lum * cm, 2) / np.maximum(scene._box(cm, 2), 1e-3); outer = scene._box(lum * out, 2) / np.maximum(scene._box(out, 2), 1e-3)
    er = comp_mask.copy(); er[1:] &= comp_mask[:-1]; er[:-1] &= comp_mask[1:]; er[:, 1:] &= comp_mask[:, :-1]; er[:, :-1] &= comp_mask[:, 1:]
    bd = comp_mask & ~er
    if bd.sum() < 8: return False
    return float((np.abs(inner - outer)[bd] > 12).mean()) >= .5

def _inpaint(rgb: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Fill `hole` (bool, full size) from the surrounding plate with a multi-scale normalised blur (working at 1/4 size); returns float32 full-size fill."""
    H, W = hole.shape; q = 4; h4, w4 = H // q, W // q
    im = np.asarray(Image.fromarray(rgb).resize((w4, h4), Image.BILINEAR), dtype=np.float32)
    known = (~(np.asarray(Image.fromarray((hole * 255).astype(np.uint8)).resize((w4, h4), Image.BILINEAR)) > 0)).astype(np.float32)
    cur = im * known[..., None]; kn = known.copy()
    for r in (2, 4, 8, 16, 32, 64):
        if kn.min() > .99: break
        num = np.stack([scene._box(cur[..., c], r) for c in range(3)], -1); den = scene._box(kn, r)
        est = num / np.maximum(den, 1e-4)[..., None]; new = (kn < .5) & (den > .03)
        cur = np.where(new[..., None], est, cur); kn = np.where(new, 1.0, kn)
    cur = np.where((kn < .5)[..., None], im.mean((0, 1)), cur)
    return np.asarray(Image.fromarray(cur.clip(0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), dtype=np.float32)

class _CalmRig:
    """Per-clip state; frame(k) -> uint8 RGB. Every frame = ONE rigid affine of the still (+ optionally one rigid cut-out layer). cam(t) and coords(k) keep the old shapes."""
    def __init__(self, still, size, fps, duration, seed, params):
        p = dict(params or {}); self.out = tuple(int(v) for v in size); ws = float(np.clip(p.get("warp_scale", 1.0), .4, 1.0))
        self.size = self.out if ws >= .99 else (max(2, round(self.out[0] * ws) // 2 * 2), max(2, round(self.out[1] * ws) // 2 * 2))
        W, H = self.size; self.fps = fps; self.T = max(duration, 1e-3)
        self.I = _intensity(p.get("intensity", "medium")); I = self.I; self.sc = sc = W / 1920.0
        rng = np.random.default_rng(seed * 7919 + 17); self.rng = rng
        try: self.scene = scene.analyse(still)
        except scene.SceneError as e: raise MotionError(str(e)) from e
        self.fit = fit = self.scene.fit(self.size); self.img = fit.rgb; self.depth = fit.depth
        bf = float(np.clip(p.get("boil_fps", rng.uniform(8, 12)), 8, 12))
        jp = float(np.clip(p.get("jitter_px", 1.0), 0.0, 3.0)); self.jitter_px = jp
        self.warper = effects.Warper(self.size, boil_px=2.0, boil_fps=bf, seed=seed + 3, cell=64, calm=True, jitter_px=jp)
        self.post = effects.Post(self.out, seed=seed + 5, grain=3.5 + 1.2 * I, flicker=.008 + .006 * I, vignette=.16, dust=int(round(34 * I)))
        self.vig0 = self.post.vig.copy()
        self.living = bool(p.get("living", True)) and I > 0
        self.red = None; self.layer = None
        if self.living:
            r = detect_red(fit.rgb)
            if r:
                self.red = r; self.glow_big = _glow(max(6, int(round(34 * sc)))); self.glow_small = _glow(max(4, int(round(16 * sc))))
        self.fg_amp = 5.0 * sc * I if (self.living and bool(p.get("layers", True))) else 0.0
        self._setup_camera(p.get("mode"), rng)
        if self.fg_amp > 0: self._setup_layer(fit)
        self._fit_zoom()
        self.lphase = rng.uniform(0, 6.28, 4); self._k = -1

    # -- camera
    def _setup_camera(self, mode, rng):
        W, H = self.size; sc, I, T = self.sc, self.I, self.T
        if mode is None: mode = MODES[int(rng.choice(len(MODES), p=[.24, .14, .18, .18, .16, .10]))]
        if mode not in MODES: raise MotionError(f"unknown mode {mode!r}; use one of {MODES}")
        self.mode = mode
        dz = float(np.clip(.02 + .016 * T, .03, .15)) * (.5 + .5 * I)
        z_lo = 1.05 + .02 * (I > 1)
        z0, z1 = {"push_in": (z_lo, z_lo + dz), "pull_out": (z_lo + dz, z_lo), "diag_in": (z_lo, z_lo + dz * .8), "diag_out": (z_lo + dz * .8, z_lo)}.get(mode, (z_lo + .03, z_lo + .03 + dz * .35))
        self.z0, self.z1 = z0, z1; zmin = min(z0, z1)
        sgn = float(rng.choice([-1.0, 1.0]))
        spd = {"drift_l": 36, "drift_r": 36, "diag_in": 26, "diag_out": 26, "push_in": 16, "pull_out": 16}[mode] * sc * I
        availx = max((1 - 1 / zmin) * W / 2 - 4 * self.fg_amp - 10 * sc, 0.0); availy = max((1 - 1 / zmin) * H / 2 - 4 * self.fg_amp - 10 * sc, 0.0)
        ax = min(availx * .9, .5 * spd * T); ay = min(availy * .9, .5 * spd * T * .55)
        dx = {"drift_l": -1.0, "drift_r": 1.0}.get(mode, sgn * (.7 if mode.startswith("diag") else .6)); dy = {"diag_in": -sgn * .8, "diag_out": sgn * .8}.get(mode, float(rng.choice([-1, 1])) * .3)
        self.px0, self.px1 = -dx * ax, dx * ax; self.py0, self.py1 = -dy * ay, dy * ay
        self.ph = rng.uniform(0, 6.28); self.ph2 = rng.uniform(0, 6.28); self.fg_dir = (float(rng.choice([-1, 1])), float(rng.choice([-1, 1])) * .4)
        self.rot_amp = float(rng.uniform(.15, .4)) * (1 if rng.random() < .5 else -1) * min(1.0, .5 + .5 * I)    # degrees, <= 0.4
        self.drift_amp = 3.0 * sc * I

    def _u(self, t):
        """Eased progress in 0..1 whose speed varies between ~.6x and ~1.4x but never reaches 0."""
        v = t / self.T + .04 * math.sin(2 * math.pi * 1.3 * t / self.T + self.ph)
        return (v + .04) / 1.08

    def rot(self, t):
        """Rotation in degrees (|r| <= 0.4): slow lean from -rot_amp to +rot_amp over the clip plus nothing else."""
        return self.rot_amp * (2 * self._u(t) - 1)

    def cam(self, t):
        """(zoom, px, py, 0, 0): source = centre + (screen - centre)/zoom + (px, py), same convention as the legacy rig (links use it for continuity)."""
        u = self._u(t); lerp = lambda a, b: a + (b - a) * u
        d = self.drift_amp
        return lerp(self.z0, self.z1), lerp(self.px0, self.px1) + d * math.sin(.45 * t + self.ph), lerp(self.py0, self.py1) + d * .7 * math.cos(.33 * t + self.ph2), 0.0, 0.0

    def _fg_off(self, t):
        """Screen offset (px) of the cut-out layer relative to the plate: a rigid slide of a few px, continuous, never stops."""
        u = self._u(t); a = self.fg_amp
        return a * (self.fg_dir[0] * (2 * u - 1) * .8 + .35 * math.sin(.8 * t + self.ph)), a * self.fg_dir[1] * ((2 * u - 1) * .8 + .35 * math.cos(.6 * t + self.ph2))

    def affine(self, t, off=(0.0, 0.0), jitter=True):
        """Pillow AFFINE coefficients (a, b, c, d, e, f): source = (a x + b y + c, d x + e y + f) for output pixel (x, y)."""
        W, H = self.size; cx, cy = W / 2, H / 2; z, px, py, _, _ = self.cam(t); th = math.radians(self.rot(t))
        jx, jy = self.warper.jitter(t) if (jitter and self.jitter_px > 0) else (0.0, 0.0)
        co, si = math.cos(th) / z, math.sin(th) / z
        a, b, d, e = co, -si, si, co
        c = cx + px + jx - (a * (cx + off[0]) + b * (cy + off[1])); f = cy + py + jy - (d * (cx + off[0]) + e * (cy + off[1]))
        return a, b, c, d, e, f

    def _fit_zoom(self):
        """Raise z0/z1 if rotation + pan + jitter + layer slide could ever expose the border (checked at the 4 corners over the whole clip)."""
        W, H = self.size
        for t in np.linspace(0, self.T, 48):
            for off in ((0, 0), tuple(self._fg_off(t))):
                a, b, c, d, e, f = self.affine(t, off, jitter=False)
                mj = self.jitter_px * self.sc + 1.5
                for x, y in ((0, 0), (W, 0), (0, H), (W, H)):
                    sx, sy = a * x + b * y + c, d * x + e * y + f
                    # overshoot beyond [mj, W - mj]: grow zoom proportionally (corner distance from centre)
                    ox = max(mj - sx, sx - (W - mj), 0); oy = max(mj - sy, sy - (H - mj), 0)
                    if ox or oy:
                        self._bump = max(getattr(self, "_bump", 0.0), max(ox / (W / 2), oy / (H / 2)) * 1.06)
        b = getattr(self, "_bump", 0.0)
        if b > 0: self.z0 += b; self.z1 += b

    def coords(self, k, clip=True):
        """Source coordinates at the 64 px mesh vertices (rigid, so a plane): used by the tests to check borders."""
        t = k / self.fps; a, b, c, d, e, f = self.affine(t); wp = self.warper
        sx = a * wp.vx + b * wp.vy + c; sy = d * wp.vx + e * wp.vy + f
        if clip: sx, sy = np.clip(sx, 0, self.size[0] - 1.01), np.clip(sy, 0, self.size[1] - 1.01)
        return sx, sy

    # -- rigid cut-out layer
    def _setup_layer(self, fit):
        occ = np.asarray(fit.occ)
        if occ.max() < 200: return
        W, H = self.size; q = 4; small = occ[::q, ::q] > 110; lum_full = np.asarray(fit.rgb.convert("L"), dtype=np.float32); lum = lum_full[::q, ::q]
        sh, sw = small.shape; picked = []
        for ar, x0, y0, x1, y1, cx, cy, ys, xs in sorted(_label(small), key=lambda c: -c[0]):
            fr = ar / (sh * sw); bw, bh = x1 - x0 + 1, y1 - y0 + 1
            if not (.004 <= fr <= .20) or ar < .3 * bw * bh: continue
            cm = np.zeros_like(small); cm[ys, xs] = True
            er = cm.copy(); er[1:] &= cm[:-1]; er[:-1] &= cm[1:]; er[:, 1:] &= cm[:, :-1]; er[:, :-1] &= cm[:, 1:]
            per = int((cm & ~er).sum())
            if per * per > 110 * ar or not _edge_ok(lum, small, cm): continue
            picked.append(cm)
            if len(picked) >= 3: break
        if not picked: return
        reg = np.zeros_like(small)
        for cm in picked: reg |= cm
        d = reg.copy(); d[1:] |= reg[:-1]; d[:-1] |= reg[1:]; d[:, 1:] |= reg[:, :-1]; d[:, :-1] |= reg[:, 1:]
        up = np.asarray(Image.fromarray((d * 255).astype(np.uint8)).resize((W, H), Image.NEAREST)) > 0
        alpha = (occ.astype(np.float32) / 255.0) * up
        if alpha.sum() < 200: return
        if self.red:   # glow lives on the plate; do not hide it under a piece
            pts = [(x, y) for x, y, _ in self.red["dots"]] + list(self.red["route"] or [])
            if any(alpha[min(max(int(y * H), 0), H - 1), min(max(int(x * W), 0), W - 1)] > .05 for x, y in pts): return
        sc = self.sc; rgb = np.asarray(fit.rgb)
        hole = np.asarray(Image.fromarray((alpha > .02).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * max(2, int(round(3 * sc))) + 1))) > 0
        if hole.mean() > .25: return
        fill = _inpaint(rgb, hole)
        soft = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(max(1.0, 1.5 * sc))), dtype=np.float32)[..., None] / 255.0
        self.fg_src = fit.rgb
        self.img = Image.fromarray((rgb * (1 - soft) + fill * soft).clip(0, 255).astype(np.uint8))      # the plate with the pieces inpainted away
        a8 = Image.fromarray((alpha * 255).clip(0, 255).astype(np.uint8)); self.fg_alpha = a8
        self.fg_shadow = a8.filter(ImageFilter.GaussianBlur(max(2.0, 7 * sc))).point(lambda v: int(v * .34 * min(self.I, 1.3)))
        ys, xs = np.nonzero(alpha > .02); pad = int(round(26 * sc))
        self.fg_box = (max(int(xs.min()) - pad, 0), max(int(ys.min()) - pad, 0), min(int(xs.max()) + pad, W), min(int(ys.max()) + pad, H))
        self.sh_off = (4.0 * sc, 6.0 * sc); self.layer = True

    def _marks(self, t):
        if not self.red: return self.img
        W, H = self.size; a = np.array(self.img, dtype=np.uint8); I = self.I
        def blit(g, x, y, k, col):
            r = g.shape[0] // 2; x0, y0 = int(round(x)) - r, int(round(y)) - r
            xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + g.shape[1], W), min(y0 + g.shape[0], H)
            if xb <= xa or yb <= ya: return
            add = g[ya - y0:yb - y0, xa - x0:xb - x0, None] * (k * np.array(col, np.float32))
            reg = a[ya:yb, xa:xb]; reg[...] = np.minimum(reg.astype(np.float32) + add, 255).astype(np.uint8)
        for x, y, rr in self.red["dots"]:
            pulse = .5 + .5 * math.sin(2 * math.pi * .85 * t)
            blit(self.glow_big, x * W, y * H, (.35 + .65 * pulse) * .75 * min(I, 1.4), (255, 90, 60))
        route = self.red["route"]
        if route:
            P = np.array([(x * W, y * H) for x, y in route]); seg = np.hypot(*np.diff(P, axis=0).T); cum = np.concatenate([[0], np.cumsum(seg)]); L = float(cum[-1])
            head = ((t / max(2.2, L / (W * .22))) % 1.0) * (L * 1.15) - .08 * L
            for i, (x, y) in enumerate(P):
                k = math.exp(-((cum[i] - head) / (.09 * L + 1)) ** 2)
                if k > .05: blit(self.glow_small, x, y, k * .85 * min(I, 1.4), (255, 80, 50))
            if 0 <= head <= L:
                j = int(np.searchsorted(cum, head, side="right")) - 1; j = min(max(j, 0), len(P) - 2); f = (head - cum[j]) / max(seg[j], 1e-6)
                hx, hy = P[j] + (P[j + 1] - P[j]) * f; blit(self.glow_big, hx, hy, .9 * min(I, 1.4), (255, 150, 90))
        return Image.fromarray(a)

    @staticmethod
    def _region_coefs(co, x0, y0):
        a, b, c, d, e, f = co
        return a, b, c + a * x0 + b * y0, d, e, f + d * x0 + e * y0

    def frame(self, k):
        t = k / self.fps; W, H = self.size
        out = self._marks(t).transform(self.size, Image.Transform.AFFINE, self.affine(t), Image.BILINEAR)   # bilinear: 3x faster than bicubic, same rigid geometry
        if self.layer:
            x0, y0, x1, y1 = self.fg_box; wh = (x1 - x0, y1 - y0); fo = self._fg_off(t)
            # box follows the still-space bbox through the same camera (rigid) -> screen box, padded by the slide
            A = np.array(self.affine(t) + (0, 0, 1), dtype=np.float64).reshape(3, 3); Ai = np.linalg.inv(A)   # source -> screen
            cs = np.array([(x0, y0, 1), (x1, y0, 1), (x0, y1, 1), (x1, y1, 1)], float) @ Ai.T
            m = int(abs(fo[0]) + abs(fo[1])) + 14
            bx0, by0 = max(int(cs[:, 0].min()) - m, 0), max(int(cs[:, 1].min()) - m, 0); bx1, by1 = min(int(cs[:, 0].max()) + m, W), min(int(cs[:, 1].max()) + m, H)
            if bx1 > bx0 and by1 > by0:
                sz = (bx1 - bx0, by1 - by0)
                osh = (fo[0] + self.sh_off[0], fo[1] + self.sh_off[1])
                sh = self.fg_shadow.transform(sz, Image.Transform.AFFINE, self._region_coefs(self.affine(t, osh), bx0, by0), Image.BILINEAR)
                out.paste((0, 0, 0), (bx0, by0, bx1, by1), sh)
                co = self._region_coefs(self.affine(t, fo), bx0, by0)
                out.paste(self.fg_src.transform(sz, Image.Transform.AFFINE, co, Image.BICUBIC), (bx0, by0), self.fg_alpha.transform(sz, Image.Transform.AFFINE, co, Image.BILINEAR))
        if self.size != self.out: out = out.resize(self.out, Image.BICUBIC)
        # slow drifting light pool folded into the vignette multiplier (colour only)
        ph = self.lphase; Wo, Ho = self.out; gy, gx = np.mgrid[0:27, 0:48].astype(np.float32)
        lx = 24 + 16 * math.sin(t * .31 + ph[0]); ly = 13 + 7 * math.sin(t * .23 + ph[1])
        L = 1 + .055 * self.I * np.exp(-(((gx - lx) / 15) ** 2 + ((gy - ly) / 9) ** 2)) - .02 * self.I
        self.post.vig = self.vig0 * _to_grid(L, (Ho, Wo))[..., None]
        return np.ascontiguousarray(self.post.apply(out, t, k))

def _Rig(still, size, fps, duration, seed, params):
    """Factory kept under the old name: calm rig by default, params legacy=True gives the old warping rig (A/B comparison only)."""
    if (params or {}).get("legacy"): return _LegacyRig(still, size, fps, duration, seed, params)
    if (params or {}).get("parallax", True):       # real-depth layered parallax (rigid layers) when the picture has depth structure; else the plain calm camera
        try:
            from . import layers
            rig = layers.build(still, size, fps, duration, seed, params)
            if rig is not None: return rig
        except Exception:
            pass
    return _CalmRig(still, size, fps, duration, seed, params)

# ---------------------------------------------------------------- warp energy: how much of the motion is NOT a rigid camera move
def _frames_of(src, max_w=960):
    if isinstance(src, (str, os.PathLike)):
        probe = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(src), "-vf", f"scale={max_w}:-2,format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, timeout=900)
        if probe.returncode != 0: raise MotionError(f"cannot decode {src}: {probe.stderr.decode('utf8', 'replace')[-300:]}")
        info = subprocess.run([_ffmpeg(), "-i", str(src)], capture_output=True, timeout=900).stderr.decode("utf8", "replace")
        import re
        m = re.search(r"Stream.*Video.* (\d{2,5})x(\d{2,5})", info); ow, oh = int(m.group(1)), int(m.group(2))
        w = max_w; h = int(round(oh * max_w / ow / 2)) * 2
        a = np.frombuffer(probe.stdout, np.uint8); n = a.size // (w * h)
        return a[: n * w * h].reshape(n, h, w).astype(np.float32), ow / w
    arr = [np.asarray(f) for f in src]
    out = []; ow = arr[0].shape[1]
    for f in arr:
        im = Image.fromarray(f).convert("L"); w = min(max_w, im.width); out.append(np.asarray(im.resize((w, max(2, round(im.height * w / im.width))), Image.BILINEAR), dtype=np.float32))
    return np.stack(out), ow / out[0].shape[1]

def _pc_shift(a, b):
    """Sub-pixel translation of patch b relative to a (phase correlation, parabolic peak): returns (dx, dy) such that b(x) = a(x - d)."""
    win = np.hanning(a.shape[0])[:, None] * np.hanning(a.shape[1])[None, :]
    A = np.fft.rfft2((a - a.mean()) * win); B = np.fft.rfft2((b - b.mean()) * win)
    R = A.conj() * B; R /= np.abs(R) + 1e-6
    c = np.fft.irfft2(R, s=a.shape); iy, ix = np.unravel_index(int(np.argmax(c)), c.shape); h, w = c.shape
    def sub(m, p, z):
        l, r = c[iy, (ix - 1) % w] if z == 0 else c[(iy - 1) % h, ix], c[iy, (ix + 1) % w] if z == 0 else c[(iy + 1) % h, ix]
        den = l - 2 * m + r; return 0.0 if abs(den) < 1e-9 else 0.5 * (l - r) / den
    dx = ix + sub(c[iy, ix], ix, 0); dy = iy + sub(c[iy, ix], iy, 1)
    if dx > w / 2: dx -= w
    if dy > h / 2: dy -= h
    return dx, dy

def warp_energy(video_or_frames, patch=96, max_pairs=40, step=1):
    """Non-rigid motion between consecutive frames. Per pair: translation of a grid of textured patches (phase correlation on slightly blurred gray frames),
    a global similarity transform (translate + zoom + rotate) fitted by least squares, and the RMS of what is left over. All numbers in px at the SOURCE frame size
    (so 1080p px for a 1080p video). Returns {'resid_px': mean RMS residual, 'rigid_px': mean RMS of the fitted rigid displacement, 'resid_max': worst pair,
    'pairs': n, 'ratio': resid/rigid}. A pure camera move + whole-frame jitter gives resid ~ 0; water-like ripple, shear parallax or sway gives resid of the same order as the motion."""
    fr, scl = _frames_of(video_or_frames)
    if len(fr) < 2: raise MotionError("need at least 2 frames")
    H, W = fr.shape[1:]; ps = patch
    ys = list(range(8, H - ps - 8 + 1, ps)); xs = list(range(8, W - ps - 8 + 1, ps))
    pairs = list(range(0, len(fr) - step, step)); stride = max(1, len(pairs) // max_pairs); pairs = pairs[::stride]
    res, rig, worst = [], [], 0.0
    for i in pairs:
        a_full, b_full = _box2(fr[i]), _box2(fr[i + step]); P, D = [], []
        for y in ys:
            for x in xs:
                pa, pb = a_full[y:y + ps, x:x + ps], b_full[y:y + ps, x:x + ps]
                if np.hypot(*np.gradient(pa)).mean() < 1.2: continue    # blank paper: no texture to follow
                dx, dy = _pc_shift(pa, pb); P.append((x + ps / 2 - W / 2, y + ps / 2 - H / 2)); D.append((dx, dy))
        if len(P) < 6: continue
        P = np.array(P); D = np.array(D)
        # d = t + s*p + r*perp(p): solve for (tx, ty, s, r) over x and y components together
        n = len(P); Amat = np.zeros((2 * n, 4)); Amat[0::2, 0] = 1; Amat[1::2, 1] = 1; Amat[0::2, 2] = P[:, 0]; Amat[1::2, 2] = P[:, 1]; Amat[0::2, 3] = -P[:, 1]; Amat[1::2, 3] = P[:, 0]
        bvec = D.reshape(-1); sol, *_ = np.linalg.lstsq(Amat, bvec, rcond=None); fit = Amat @ sol
        r = bvec - fit; rm = float(np.sqrt((r ** 2).sum() / n)) * scl; rg = float(np.sqrt((fit ** 2).sum() / n)) * scl
        res.append(rm); rig.append(rg); worst = max(worst, rm)
    if not res: raise MotionError("no textured patches to measure")
    R, G = float(np.mean(res)), float(np.mean(rig))
    return {"resid_px": R, "rigid_px": G, "resid_max": worst, "pairs": len(res), "ratio": R / max(G, 1e-6)}

def _box2(a):
    return scene._box(a, 1)

# ---------------------------------------------------------------- ffmpeg sink (own copy so this module stands alone)
class _Sink:
    def __init__(self, size, fps, path):
        self.err = tempfile.TemporaryFile()
        cmd = [_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-", "-an",
               "-c:v", "libx264", "-crf", "17", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-f", "mp4", path]
        try: self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self.err)
        except OSError as e:
            self.err.close(); raise MotionError(f"cannot start ffmpeg: {e}") from e
    def _msg(self):
        try: self.err.seek(0); return self.err.read().decode("utf8", "replace").strip()[-600:]
        except Exception: return ""
    def write(self, b):
        try: self.p.stdin.write(b)
        except (BrokenPipeError, OSError) as e: raise MotionError(f"ffmpeg stopped early: {self._msg()}") from e
    def close(self):
        try:
            if self.p.stdin and not self.p.stdin.closed: self.p.stdin.close()
        except OSError: pass
        rc = self.p.wait(timeout=7200); msg = self._msg(); self.err.close()
        if rc != 0: raise MotionError(f"ffmpeg failed ({rc}): {msg}")
    def abort(self):
        try: self.p.kill()
        except Exception: pass
        try:
            if self.p.stdin: self.p.stdin.close()
        except Exception: pass
        try: self.p.wait(timeout=5)
        except Exception: pass
        try: self.err.close()
        except Exception: pass

def _key(still, duration, fps, size, seed, params) -> str:
    blob = json.dumps(dict(v=VERSION, code=_code_hash(), still=_file_hash(still), d=round(float(duration), 4), fps=fps, size=list(size), seed=seed, p=params or {}), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]

# ---------------------------------------------------------------- public
def render_motion(still_path, out_path, duration, fps=30, size=(1920, 1080), seed=0, params=None, cancel=None, progress=None):
    """Render the moving version of one still to out_path (mp4). Cached; safe to call from several threads/processes."""
    size = (int(size[0]) // 2 * 2, int(size[1]) // 2 * 2); params = dict(params or {}); cancel = cancel or params.pop("cancel", None); progress = progress or params.pop("progress", None)
    if not (duration and duration > 0): raise MotionError(f"duration must be > 0, got {duration!r}")
    if fps <= 0: raise MotionError(f"fps must be > 0, got {fps!r}")
    if not os.path.isfile(str(still_path)): raise MotionError(f"still not found: {still_path}")
    _intensity(params.get("intensity", "medium"))
    n = max(1, int(round(duration * fps))); out_path = str(out_path); out_dir = os.path.dirname(os.path.abspath(out_path)); os.makedirs(out_dir, exist_ok=True)
    key = _key(still_path, duration, fps, size, seed, params); CACHE_DIR.mkdir(parents=True, exist_ok=True); cached = CACHE_DIR / f"{key}.mp4"
    with _key_lock(key):   # one thread renders a key; the others wait and copy it (Windows cannot replace a file being copied)
        _render_cached(still_path, cached, n, size, fps, duration, seed, params, cancel, progress)
    fd, tmp2 = tempfile.mkstemp(dir=out_dir, suffix=".part"); os.close(fd)
    try: shutil.copyfile(cached, tmp2); os.replace(tmp2, out_path)
    except BaseException:
        try: os.unlink(tmp2)
        except OSError: pass
        raise
    return out_path


_KEY_LOCKS: dict = {}
_KEY_LOCKS_GUARD = threading.Lock()


def _key_lock(key):
    with _KEY_LOCKS_GUARD:
        return _KEY_LOCKS.setdefault(key, threading.Lock())


def _render_cached(still_path, cached, n, size, fps, duration, seed, params, cancel, progress):
    if not cached.exists() or cached.stat().st_size == 0:
        if cancel and cancel(): raise Cancelled("motion render cancelled")
        rig = _Rig(still_path, size, fps, duration, seed, params)
        fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".part.mp4"); os.close(fd)
        sink = _Sink(size, fps, tmp)
        try:
            for i in range(n):
                if cancel and cancel(): raise Cancelled("motion render cancelled")
                sink.write(rig.frame(i).tobytes())
                if progress: progress((i + 1) / n)
            sink.close()
            try: os.replace(tmp, cached)
            except PermissionError:   # Windows: another process rendered the same key and is reading it; theirs is identical
                if not (cached.exists() and cached.stat().st_size > 0): raise
                os.unlink(tmp)
        except BaseException:
            sink.abort()
            try: os.unlink(tmp)
            except OSError: pass
            raise
