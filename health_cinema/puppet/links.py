"""Picture-to-picture LINK clips: a 1.0-1.6 s move that carries the eye from still A into still B (no characters needed).

    render_link(still_a, still_b, kind, out_path, duration=1.2, fps=30, size=(1920, 1080), seed=0, params=None, cancel=None, progress=None) -> out_path
    resolve_link(still_a, still_b, kind, params=None) -> dict   what render_link will really do (kind used, points found, match score)
    estimate_seconds(kind, duration, fps, size) -> float        rough render time on this class of machine

One mp4 (libx264 crf 17 yuv420p, no audio, exactly round(duration*fps) frames). Frame 0 is A framed like a moving shot, the last frame is B framed like a moving
shot, so a link placed between two motion clips has no jump at either end (both pictures are already drifting inside it). Everything is a mesh warp of the
real stills (effects.Warper, same boil/grain/vignette/dust as motion.py), so no kind can ever show an empty border. Deterministic for a seed; cached under
out/puppet_cache/links keyed by both stills' pixels, kind, duration, fps, size, seed, params, VERSION and every puppet/*.py file.

KINDS and best use
  torn_wipe      A is a sheet of paper that tears away sideways (cream torn edge, soft shadow on B, edge fraying and boiling); B sits underneath and drifts.
                 Best for: a new place / a new beat of the story, "turn the page" feel, passing from one scene to a different scene of the same chapter.
  push_through   The camera dives into a doorway / dark area / strong centre detail of A (motion blur, darkness bridge) and emerges from the matching spot of B.
                 Best for: going INTO something (a building, a body part, a hole, a cave, a screen) and arriving somewhere new; time or location jumps with a "through".
  match_cut      A and B share a dominant shape (blob / circle / vertical) or the horizon line; B is scaled and moved so the feature coincides, they cross-dissolve while
                 both drift, then B relaxes to its own framing. Falls back to dissolve_alive when nothing convincing is shared (resolve_link says so).
                 Best for: visual rhymes (moon -> lamp, wheel -> coin, tower -> tree), "this is like that" narration.
  whip           Fast sideways whip pan with directional motion blur and boil (dir 'l' or 'r').
                 Best for: energetic hand-offs, "meanwhile ...", lists, quick change of subject at the same level of importance.
  dissolve_alive A paper-like noisy dissolve (patches change at different moments, so it never looks like a uniform double exposure) while both pictures keep moving.
                 Best for: gentle continuation, same topic, time passing, anything that must not draw attention.

params (all optional): dir ('l'|'r', torn_wipe/whip, default by seed), point_a / point_b ((x, y) fractions: push_through target in A / emerge point in B),
  points (((ax, ay), (bx, by)) fractions: match_cut feature positions, skips detection), min_score (match_cut acceptance, default .38), zoom_max (push_through, default 4.6),
  dip (push_through dark bridge strength 0..1, default from how dark the target is), warp_scale (default .75, like motion.py), intensity ('low'|'medium'|'high'|number).
"""
from __future__ import annotations
import hashlib, json, math, os, shutil, tempfile
from collections import deque
from pathlib import Path
import numpy as np
from PIL import Image

from . import effects, scene
from .motion import MotionError, Cancelled, _Sink, _file_hash, _intensity, _to_grid

VERSION = "1"
_HERE = Path(__file__).resolve().parent
CACHE_DIR = scene.ROOT / "out" / "puppet_cache" / "links"
KINDS = ("torn_wipe", "push_through", "match_cut", "whip", "dissolve_alive")
# measured ms/frame at 1920x1080 with warp_scale .75 on the dev Mac (see docs/story/links.md); estimate_seconds scales by pixel count
MS_PER_FRAME_1080 = {"torn_wipe": 160, "push_through": 300, "match_cut": 250, "whip": 250, "dissolve_alive": 160}
ENCODE_MS_1080 = 25

class LinkError(MotionError): pass

# ------------------------------------------------------------------ small math
def _sm(u):
    u = min(max(float(u), 0.0), 1.0); return u * u * (3 - 2 * u)

def _eio(u):
    u = min(max(float(u), 0.0), 1.0); return 4 * u ** 3 if u < .5 else 1 - (-2 * u + 2) ** 3 / 2

def _lerp(a, b, t): return a + (b - a) * t

def _code_hash() -> str:
    h = hashlib.sha256(VERSION.encode())
    for f in sorted(_HERE.glob("*.py")): h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()[:16]

def _noise2d(rng, shape, cells, amp=1.0):
    """Smooth value noise in [-amp, amp]-ish with `cells` = (cy, cx) control points."""
    g = rng.standard_normal(cells).astype(np.float32)
    return np.asarray(Image.fromarray(g).resize((shape[1], shape[0]), Image.BICUBIC)) * amp

def _noise1d(rng, n, k, amp=1.0):
    return np.asarray(Image.fromarray(rng.standard_normal((1, k)).astype(np.float32)).resize((n, 1), Image.BICUBIC))[0] * amp

def _box_x(a: np.ndarray, L: int) -> np.ndarray:
    """Horizontal box blur of length L (odd) on an H x W x C float array, edge-padded."""
    if L <= 1: return a
    r = L // 2; p = np.pad(a, ((0, 0), (r + 1, r), (0, 0)), mode="reflect"); c = np.cumsum(p, axis=1, dtype=np.float32)
    return (c[:, L:] - c[:, :-L]) / L

# ------------------------------------------------------------------ feature finding (match cut)
def _small_gray(path, w=160):
    with Image.open(path) as im: im = im.convert("RGB"); h = max(1, round(im.height * w / im.width)); im = im.resize((w, h), Image.BILINEAR)
    a = np.asarray(im, dtype=np.float32); return a, a.mean(2)

def _blur(a, r): return scene._box(a.astype(np.float32), max(1, int(r)))

def find_features(path, n=3) -> list:
    """Up to n dominant blobs of a still, strongest first: dict(x, y, w, h, area, sign, strength, fill, aspect) in fractions of width/height; sign -1 = darker than surround."""
    a, lum = _small_gray(path); H, W = lum.shape
    mx, mn = a.max(2), a.min(2); cream = (lum > 205) & ((mx - mn) / (mx + 1) < .25)
    pic = _blur(cream.astype(np.float32), 2) < .5; ok = _blur(pic.astype(np.float32), 3) > .995       # inside the printed picture, away from the paper margin
    if ok.sum() < 200: return []
    resp = _blur(lum, 2) - _blur(lum, 8)
    sd = float(resp[ok].std()) + 1e-3; work = np.where(ok, resp, 0).astype(np.float32); out = []
    for _ in range(n + 2):
        iy, ix = np.unravel_index(int(np.argmax(np.abs(work))), work.shape); pk = float(work[iy, ix])
        if abs(pk) < 2.2 * sd: break
        sign = 1 if pk > 0 else -1; thr = .4 * abs(pk)
        seen = np.zeros((H, W), bool); q = deque([(iy, ix)]); seen[iy, ix] = True; pts = []
        while q:
            y, x = q.popleft(); pts.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and not seen[yy, xx] and ok[yy, xx] and sign * resp[yy, xx] > thr: seen[yy, xx] = True; q.append((yy, xx))
        P = np.array(pts); y0, y1, x0, x1 = P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max()
        for (y, x) in pts: work[max(y - 0, 0), x] = 0
        work[max(y0 - 4, 0):y1 + 5, max(x0 - 4, 0):x1 + 5] = 0                                         # suppress the neighbourhood so the next peak is a different object
        ar = len(pts) / (H * W); bw, bh = (x1 - x0 + 1), (y1 - y0 + 1)
        if not (.004 <= ar <= .35): continue
        out.append(dict(x=float((P[:, 1].mean() + .5) / W), y=float((P[:, 0].mean() + .5) / H), w=float(bw / W), h=float(bh / H), area=float(ar), sign=sign,
                        strength=float(abs(pk) / sd), fill=float(len(pts) / (bw * bh)), aspect=float(bw / bh)))
        if len(out) >= n: break
    return out

def _pair_score(fa: dict, fb: dict) -> float:
    if fa["sign"] != fb["sign"]: return 0.0
    ra, rb = math.sqrt(fa["w"] * fa["h"]), math.sqrt(fb["w"] * fb["h"]); rs = ra / rb
    if not (.4 <= rs <= 2.5): return 0.0
    asp = math.exp(-abs(math.log(fa["aspect"] / fb["aspect"])) * 1.0); fil = math.exp(-abs(fa["fill"] - fb["fill"]) * 2.0)
    siz = math.exp(-abs(math.log(rs)) * .45); dist = math.exp(-math.hypot(fa["x"] - fb["x"], (fa["y"] - fb["y"]) * .56) / .5)
    st = min(1.0, min(fa["strength"], fb["strength"]) / 4.0)
    return float(asp * fil * siz * dist * (.6 + .4 * st))

def plan_match(path_a, path_b, min_score=.38) -> dict:
    """Best shared feature of two stills -> dict(ok, kind 'blob'|'horizon'|None, a=(x,y), b=(x,y), scale (A size / B size), score). Never raises on plain pictures."""
    try:
        fa, fb = find_features(path_a), find_features(path_b); best = (0.0, None, None)
        for x in fa:
            for y in fb:
                s = _pair_score(x, y)
                if s > best[0]: best = (s, x, y)
        if best[1] is not None and best[0] >= min_score:
            x, y = best[1], best[2]
            return dict(ok=True, kind="blob", a=(x["x"], x["y"]), b=(y["x"], y["y"]), scale=float(np.clip(math.sqrt(x["w"] * x["h"]) / math.sqrt(y["w"] * y["h"]), .5, 2.0)), score=round(best[0], 3))
        sa, sb = scene.analyse(path_a), scene.analyse(path_b)
        if abs(sa.horizon - sb.horizon) <= .2 and abs(sa.horizon - sb.horizon) > .01:
            return dict(ok=True, kind="horizon", a=(.5, sa.horizon), b=(.5, sb.horizon), scale=1.0, score=round(max(best[0], .4), 3))
        return dict(ok=False, kind=None, a=(.5, .5), b=(.5, .5), scale=1.0, score=round(best[0], 3))
    except (scene.SceneError, OSError, ValueError):
        return dict(ok=False, kind=None, a=(.5, .5), b=(.5, .5), scale=1.0, score=0.0)

def _darkness(path, pt, r=.06) -> float:
    """0..1 how much darker than the picture's average the neighbourhood of pt (fractions) is."""
    a, lum = _small_gray(path, 96); H, W = lum.shape; x, y = int(pt[0] * W), int(pt[1] * H); rr = max(2, int(r * W))
    loc = lum[max(y - rr, 0):y + rr + 1, max(x - rr, 0):x + rr + 1]
    if loc.size == 0: return 0.0
    return float(np.clip((lum.mean() - loc.mean()) / max(lum.mean(), 1.0) * 2.2, 0, 1))

def _door_point(sc: scene.Scene, towards=None):
    if not sc.doors: return None
    ds = sorted(sc.doors, key=lambda d: abs(d[0] - towards) if towards is not None else 0)
    d = ds[0]; return (float(d[0]), float(max(.15, d[1] - d[3] * .5)))

def resolve_link(still_a, still_b, kind, params=None) -> dict:
    """What render_link will do: {'kind' (used), 'asked', 'fallback' (bool), plus kind specifics}. Cheap (no frames are rendered)."""
    p = dict(params or {})
    if kind not in KINDS: raise LinkError(f"unknown link kind {kind!r}; use one of {KINDS}")
    r = {"asked": kind, "kind": kind, "fallback": False}
    if kind == "push_through":
        sa, sb = scene.analyse(still_a), scene.analyse(still_b)
        pa = p.get("point_a"); src = "given"
        if pa is None:
            pa = _door_point(sa); src = "door"
            if pa is None:
                fs = [f for f in find_features(still_a, 2) if f["sign"] < 0]
                if fs: pa = (fs[0]["x"], fs[0]["y"]); src = "dark_blob"
                else: pa = (.5, .46); src = "centre"
        pb = p.get("point_b")
        if pb is None:
            pb = _door_point(sb, towards=pa[0]) or (float(pa[0]), float(pa[1]));
        r.update(point_a=tuple(pa), point_b=tuple(pb), source=src)
    elif kind == "match_cut":
        pts = p.get("points")
        if pts:
            r.update(ok=True, feature="given", a=tuple(pts[0]), b=tuple(pts[1]), scale=float(p.get("scale", 1.0)), score=1.0)
        else:
            m = plan_match(still_a, still_b, float(p.get("min_score", .38)))
            if m["ok"]: r.update(ok=True, feature=m["kind"], a=m["a"], b=m["b"], scale=m["scale"], score=m["score"])
            else: r.update(kind="dissolve_alive", fallback=True, score=m["score"], reason="no shared feature")
    return r

def estimate_seconds(kind, duration, fps=30, size=(1920, 1080)) -> float:
    n = max(1, int(round(duration * fps))); px = (size[0] * size[1]) / (1920 * 1080)
    return round(n * (MS_PER_FRAME_1080.get(kind, 150) + ENCODE_MS_1080) * px / 1000.0 + 1.0, 2)

# ------------------------------------------------------------------ rendering
class _Layer:
    """One still at the working size: fit, depth and a mesh warper. cam = (a source point px, s screen point px, zoom): source = a + (screen - s) / zoom."""
    def __init__(self, path, size, seed, boil):
        try: self.scene = scene.analyse(path)
        except scene.SceneError as e: raise LinkError(str(e)) from e
        self.fit = self.scene.fit(size); self.img = self.fit.rgb; self.depth = self.fit.depth; self.size = size
        self.wp = effects.Warper(size, boil_px=boil, boil_fps=10.0, seed=seed, cell=32)

    def feasible(self, a, s, z):
        """Move the screen anchor s the least needed so the sampled window stays inside the picture (no empty border at any zoom >= 1)."""
        W, H = self.size
        sx = min(max(s[0], W - (W - a[0]) * z), a[0] * z); sy = min(max(s[1], H - (H - a[1]) * z), a[1] * z)
        return (sx, sy)

    def render(self, a, s, z, t, par=(0.0, 0.0), keep=True) -> Image.Image:
        wp = self.wp
        if keep: s = self.feasible(a, s, z)
        sx = a[0] + (wp.vx - s[0]) / z; sy = a[1] + (wp.vy - s[1]) / z
        if par[0] or par[1]:
            dv = wp.depth_at_vertices(self.depth); sx = sx + (dv - .5) * par[0]; sy = sy + (dv - .5) * par[1]
        bx, by = wp._boil(t); sx = np.clip(sx + bx, 0, self.size[0] - 1.01); sy = np.clip(sy + by, 0, self.size[1] - 1.01)
        return wp.warp(self.img, sx, sy)

class _Rig:
    """frame(k) -> uint8 RGB at the output size."""
    def __init__(self, still_a, still_b, kind, size, fps, n, seed, params, info):
        p = dict(params or {}); self.p = p; self.kind = kind; self.n = n; self.fps = fps; self.out = size; self.info = info
        ws = float(np.clip(p.get("warp_scale", .75), .4, 1.0))
        self.size = size if ws >= .99 else (max(2, round(size[0] * ws) // 2 * 2), max(2, round(size[1] * ws) // 2 * 2))
        W, H = self.size; self.W, self.H = W, H; self.cx, self.cy = W / 2, H / 2; self.k = W / 1920.0
        I = self.I = _intensity(p.get("intensity", "medium")); self.rng = np.random.default_rng(seed * 7919 + 101)
        boil = 2.0 * I
        self.A = _Layer(still_a, self.size, seed + 3, boil); self.B = _Layer(still_b, self.size, seed + 4, boil)
        self.post = effects.Post(self.size, seed=seed + 5, grain=3.5 + 1.2 * I, flicker=.008 + .006 * I, vignette=.16, dust=int(round(26 * I)))
        r = self.rng; self.dir = p.get("dir") or ("l" if r.random() < .5 else "r")
        if self.dir not in ("l", "r"): raise LinkError(f"dir must be 'l' or 'r', got {self.dir!r}")
        self.ph = r.uniform(0, 6.28, 4)
        # natural framing: A keeps pushing in slowly, B settles out of a slightly larger zoom -> frame 0 / last frame look like motion-clip frames
        self.zA0, self.zA1 = 1.10, 1.145; self.zB0, self.zB1 = 1.145, 1.10
        self.pxA = r.uniform(-1, 1, 2) * 8 * self.k; self.pxB = r.uniform(-1, 1, 2) * 8 * self.k
        getattr(self, "_setup_" + kind)()

    # natural camera of A / B at link progress u. params cam_a / cam_b = [[z, fx, fy] at link start, [z, fx, fy] at link end] (fx, fy = camera offset as a fraction of the
    # frame, the same numbers a motion.py clip has at those moments) make the link start/end exactly where the neighbouring motion clips are.
    def nat(self, which, u):
        cam = self.p.get("cam_a" if which == "A" else "cam_b")
        if cam:
            (z0, fx0, fy0), (z1, fx1, fy1) = cam
            z = math.exp(_lerp(math.log(z0), math.log(z1), u)); d = (_lerp(fx0, fx1, u) * self.W, _lerp(fy0, fy1, u) * self.H)
            par = (22 * self.k * self.I * (u if which == "A" else u - 1.0), 4 * self.k * (u if which == "A" else u - 1.0))
            return (self.cx + d[0], self.cy + d[1]), (self.cx, self.cy), z, par
        if which == "A": z = _lerp(self.zA0, self.zA1, u); d = np.array([-14, -5]) * self.k * (u - .0) + self.pxA; par = (22 * self.k * self.I * u, 4 * self.k * u)
        else: z = _lerp(self.zB0, self.zB1, u); d = np.array([-14, -5]) * self.k * (u - 1.0) + self.pxB; par = (22 * self.k * self.I * (u - 1.0), 4 * self.k * (u - 1.0))
        return (self.cx + d[0], self.cy + d[1]), (self.cx, self.cy), z, par

    def img_a(self, u, t): a, s, z, par = self.nat("A", u); return self.A.render(a, s, z, t, par)
    def img_b(self, u, t): a, s, z, par = self.nat("B", u); return self.B.render(a, s, z, t, par)

    # ---------------- torn_wipe
    def _setup_torn_wipe(self):
        H, W, k, r = self.H, self.W, self.k, self.rng
        self.tear = [np.zeros(H, np.float32) + _noise1d(np.random.default_rng(int(r.integers(1 << 30)) + j), H, 9, 20 * k) + _noise1d(np.random.default_rng(j + 77), H, 40, 5 * k)
                     + _noise1d(np.random.default_rng(j + 991), H, 170, 1.8 * k) for j in range(4)]
        self.fray = _noise1d(r, H, 220, 1.0); self.edge_w = (8 + 3 * _noise1d(r, H, 30, 1.0)).clip(4, 14) * k
        self.fibre = _noise1d(r, H, 500, 1.0); self.xx = np.arange(W, dtype=np.float32)[None, :]; self.yy = np.arange(H, dtype=np.float32)[:, None]
        self.tilt = float(r.uniform(-.05, .05))

    def _frame_torn_wipe(self, u, t, kf):
        W, H, k = self.W, self.H, self.k; e = _eio(u); cx = self.cx; L = self.dir == "l"
        zA = self.nat('A', u)[2]; dend = W - cx + (cx + 90 * k) / zA + 40 * k
        an = self.nat('A', u)[0]; a = (an[0] + e * dend * (1 if L else -1), an[1] - 6 * k * u); s = (cx, self.cy)
        xe0 = cx + (W - a[0]) * zA if L else cx - a[0] * zA          # screen x of A's torn edge (A's right edge for 'l', left edge for 'r')
        tear = self.tear[(kf // 3) % 4] * (1 + .25 * math.sin(t * 5 + self.ph[0]))                  # torn edge jitters at ~10 fps like boil
        xe = xe0 + tear + self.tilt * (self.yy[:, 0] - self.cy)
        lo = int(math.floor(xe.min() - 70 * k)) if L else int(math.floor(xe.min() - 150 * k)); hi = int(math.ceil(xe.max() + 150 * k)) if L else int(math.ceil(xe.max() + 70 * k))
        # A's side is left of the edge for 'l' (right of it for 'r'); only the band around the edge needs real compositing
        if (L and lo >= W) or (not L and hi <= 0): return np.asarray(self.A.render(a, s, zA, t, keep=False), np.float32)
        if (L and hi <= 0) or (not L and lo >= W): return np.asarray(self.img_b(u, t), np.float32)
        Aim = np.asarray(self.A.render(a, s, zA, t, keep=False)); Bim = np.asarray(self.img_b(u, t))
        c0, c1 = max(lo, 0), min(hi, W)
        out = np.empty((H, W, 3), np.float32)
        if L: out[:, :c0] = Aim[:, :c0]; out[:, c1:] = Bim[:, c1:]
        else: out[:, :c0] = Bim[:, :c0]; out[:, c1:] = Aim[:, c1:]
        if c1 > c0:
            Ab = Aim[:, c0:c1].astype(np.float32); Bb = Bim[:, c0:c1].astype(np.float32); xs = self.xx[:, c0:c1]
            dist = (xs - xe[:, None]) * (1 if L else -1)                                                  # >0 on B's side
            aA = np.clip(.5 - dist, 0, 1)[..., None]                                                      # sheet A, 1 px antialiased
            inside = -dist                                                                                # >0 inside A
            ew = self.edge_w[:, None]
            edge = (np.clip((ew - inside) / 1.5, 0, 1) * (inside >= 0))[..., None]                        # cream torn fibre band along the edge
            fib = (.93 + .07 * np.clip(self.fibre[:, None] + .3 * np.sin(inside * .8), -1, 1))[..., None]
            cream = np.array([236, 228, 208], np.float32) * fib
            Ab = Ab * (1 - edge * .95) + cream * edge * .95
            Ab = Ab * (1 - .18 * np.exp(-np.clip(inside, 0, None) / (30 * k))[..., None] * (inside >= 0)[..., None])      # paper lifting
            shadow = .52 * (1 - .35 * e) * np.exp(-np.clip(dist, 0, None) / (28 * k)) * (dist > -1)       # shadow A throws on B
            Bb = Bb * (1 - shadow[..., None])
            out[:, c0:c1] = Ab * aA + Bb * (1 - aA)
        return out

    # ---------------- dissolve_alive
    def _setup_dissolve_alive(self):
        self.field = np.clip(_noise2d(np.random.default_rng(self.rng.integers(1 << 30)), (self.H, self.W), (6, 10), .5) + .5, 0, 1)

    def _frame_dissolve_alive(self, u, t, kf):
        e = _eio(u); pr = np.clip((e - self.field * .45) / .55, 0, 1); pr = pr * pr * (3 - 2 * pr)
        A = np.asarray(self.img_a(u, t), np.float32); B = np.asarray(self.img_b(u, t), np.float32)
        out = A * (1 - pr[..., None]) + B * pr[..., None]
        return out * (1 - .10 * math.sin(math.pi * u))

    # ---------------- whip
    def _setup_whip(self): pass

    def _frame_whip(self, u, t, kf):
        W, H, k, cx = self.W, self.H, self.k, self.cx; e = _eio(u)
        zA, zB = self.nat('A', u)[2], self.nat('B', u)[2]; zA0, zB1 = self.nat('A', 0.0)[2], self.nat('B', 1.0)[2]; nA, nB = self.nat('A', u)[0], self.nat('B', u)[0]
        if self.dir == "l":
            j0, j1 = cx + cx * zA0, cx - cx * zB1
            xj = _lerp(j0, j1, e); aA = (W - (xj - cx) / zA + nA[0] - cx, nA[1]); aB = ((cx - xj) / zB + nB[0] - cx, nB[1]); sgn = 1
        else:
            j0, j1 = cx - cx * zA0, cx + cx * zB1
            xj = _lerp(j0, j1, e); aA = ((cx - xj) / zA + nA[0] - cx, nA[1]); aB = (W - (xj - cx) / zB + nB[0] - cx, nB[1]); sgn = -1
        spd = math.sin(math.pi * u) ** 1.3                                                           # 0 at the ends, 1 at the fastest
        pa = (-sgn * 40 * k * e * self.I, 0.0); pb = (sgn * 40 * k * (1 - e) * self.I, 0.0)
        A = np.asarray(self.A.render(aA, (cx, self.cy), zA, t, pa, keep=False), np.float32); B = np.asarray(self.B.render(aB, (cx, self.cy), zB, t, pb, keep=False), np.float32)
        feather = max(2.0, 18 * k * spd); xs = np.arange(W, dtype=np.float32)[None, :, None]
        m = np.clip((xs - xj) / feather + .5, 0, 1) if self.dir == "l" else np.clip((xj - xs) / feather + .5, 0, 1)   # 1 where B shows
        out = A * (1 - m) + B * m
        L = int(round(.13 * W * spd)) | 1
        out = _box_x(out, L) if L > 2 else out
        return out * (1 - .08 * spd)

    # ---------------- push_through
    def _setup_push_through(self):
        W, H = self.W, self.H; i = self.info
        self.pa = (i["point_a"][0] * W, i["point_a"][1] * H); self.pb = (i["point_b"][0] * W, i["point_b"][1] * H)
        self.zmax = float(self.p.get("zoom_max", 4.6)); self.tm = .52
        dk = self.p.get("dip"); self.dipmax = float(dk) if dk is not None else float(np.clip(.35 + .55 * i.get("darkness", .3), .3, .92))

    def _cam_pt(self, which, q, u_nat):
        """q 0..1 = how far into the dive (0 natural framing, 1 pinned on the target at max zoom)."""
        a0, s0, z0, par = self.nat(which, u_nat); tgt = self.pa if which == "A" else self.pb
        w = _sm(q); a = (_lerp(a0[0], tgt[0], w), _lerp(a0[1], tgt[1], w)); z = math.exp(_lerp(math.log(z0), math.log(self.zmax), q ** 1.6))
        return a, s0, z, tuple(v * (1 - w) for v in par)

    @staticmethod
    def _zoom_blur(img: np.ndarray, c, d: float, n: int = 6) -> np.ndarray:
        """Radial motion blur: average of the frame magnified about c by 1..1+d (magnifying only, so no border can appear)."""
        im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)); acc = np.zeros(img.shape, np.float32); H, W = img.shape[:2]
        for j in range(n):
            sc = 1 + d * j / (n - 1); r = 1 / sc
            acc += np.asarray(im.transform((W, H), Image.Transform.AFFINE, (r, 0, c[0] * (1 - r), 0, r, c[1] * (1 - r)), Image.BILINEAR), np.float32)
        return acc / n

    def _frame_push_through(self, u, t, kf):
        tm = self.tm
        qa = lambda uu: (uu / tm) ** 2.0 if uu < tm else 1.0
        qb = lambda uu: (1 - (uu - tm) / (1 - tm)) ** 2.0 if uu > tm else 1.0
        mix = _sm((u - (tm - .09)) / .18); dip = self.dipmax * math.exp(-((u - tm) / .11) ** 2)
        def grab(which, qf):
            lay = self.A if which == "A" else self.B
            a, s, z, par = self._cam_pt(which, qf(u), u); s = lay.feasible(a, s, z)
            img = np.asarray(lay.render(a, s, z, t, par, keep=False), np.float32)
            du = 1.0 / max(self.n - 1, 1); z2 = self._cam_pt(which, qf(min(u + du, 1.0)), min(u + du, 1.0))[2]; z1 = self._cam_pt(which, qf(max(u - du, 0.0)), max(u - du, 0.0))[2]
            d = min(.16, 1.3 * abs(math.log(max(z2, z1) / min(z2, z1))) / 2 * 1.0)             # relative zoom change over ~a frame, stretched by the shutter
            return self._zoom_blur(img, s, d) if d > .008 else img
        A = grab("A", qa) if mix < .98 else None
        B = grab("B", qb) if mix > .02 else None
        if A is None and mix < .999: A = grab("A", qa)
        if B is None and mix > .001: B = grab("B", qb)
        out = A if B is None else (B if A is None else A * (1 - mix) + B * mix)
        return out * (1 - dip)

    # ---------------- match_cut
    def _setup_match_cut(self):
        W, H = self.W, self.H; i = self.info
        self.ma = (i["a"][0] * W, i["a"][1] * H); self.mb = (i["b"][0] * W, i["b"][1] * H); sc = float(i.get("scale", 1.0))
        # A's blob must be drawn the same size as B's: zoom whichever picture has the smaller blob (never below the natural zoom)
        self.mzA = max(1.0, 1.0 / sc) if sc >= 1 else max(1.0, 1.0 / sc)
        # sc = size(A blob)/size(B blob): sc>1 -> A's blob is bigger -> zoom B up by sc; sc<1 -> zoom A up by 1/sc
        self.mzA = 1.0 / sc if sc < 1 else 1.0; self.mzB = sc if sc > 1 else 1.0
        self.feature = i.get("feature", "blob")

    def _frame_match_cut(self, u, t, kf):
        W, H, k = self.W, self.H, self.k
        wa = _sm(u / .55)                    # A moves onto the feature during the first half
        wb = _sm((u - .45) / .55)            # B relaxes from the aligned framing to its own
        wb = 1 - wb
        aA, sA, zA, parA = self.nat("A", u); aB, sB, zB, parB = self.nat("B", u)
        horiz = self.feature == "horizon"
        # the common screen point where the two features coincide: A's own feature position (clamped so both fit)
        m = self.ma
        tgtA = self.ma; tgtB = self.mb
        zAm = zA * self.mzA * (1.0); zBm = zB * self.mzB
        mA = self.A.feasible(tgtA, m, zAm); mB = self.B.feasible(tgtB, mA, zBm)
        if horiz: m_scr = (self.cx, (self.ma[1] + self.mb[1]) / 2)
        else: m_scr = (_lerp(mA[0], mB[0], .5), _lerp(mA[1], mB[1], .5))
        # A: from natural framing to "feature at m_scr"
        a1 = (_lerp(aA[0], tgtA[0], wa), _lerp(aA[1], tgtA[1], wa)); s1 = (_lerp(sA[0], m_scr[0], wa), _lerp(sA[1], m_scr[1], wa)); z1 = math.exp(_lerp(math.log(zA), math.log(zAm), wa))
        b1 = (_lerp(aB[0], tgtB[0], wb), _lerp(aB[1], tgtB[1], wb)); s2 = (_lerp(sB[0], m_scr[0], wb), _lerp(sB[1], m_scr[1], wb)); z2 = math.exp(_lerp(math.log(zB), math.log(zBm), wb))
        mix = _sm((u - .36) / .28)
        A = np.asarray(self.A.render(a1, s1, z1, t, tuple(v * (1 - wa) for v in parA)), np.float32) if mix < .999 else None
        B = np.asarray(self.B.render(b1, s2, z2, t, tuple(v * (1 - wb) for v in parB)), np.float32) if mix > .001 else None
        out = A if B is None else (B if A is None else A * (1 - mix) + B * mix)
        return out * (1 - .05 * math.sin(math.pi * mix))

    # ---------------- common
    def frame(self, kf) -> np.ndarray:
        n = self.n; u = 0.0 if n <= 1 else kf / (n - 1); t = kf / self.fps
        comp = getattr(self, "_frame_" + self.kind)(u, t, kf)
        img = Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8))
        out = self.post.apply(img, t, kf)
        if self.size != self.out: out = np.asarray(Image.fromarray(out).resize(self.out, Image.BICUBIC))
        return np.ascontiguousarray(out)

def _key(a, b, kind, duration, fps, size, seed, params) -> str:
    blob = json.dumps(dict(v=VERSION, code=_code_hash(), a=_file_hash(a), b=_file_hash(b), kind=kind, d=round(float(duration), 4), fps=fps, size=list(size), seed=seed, p=params or {}), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]

def make_rig(still_a, still_b, kind, duration=1.2, fps=30, size=(1920, 1080), seed=0, params=None):
    """Build the frame generator without encoding (tests / contact sheets). Returns (rig, info)."""
    size = (int(size[0]) // 2 * 2, int(size[1]) // 2 * 2); info = resolve_link(still_a, still_b, kind, params)
    if kind == "push_through":
        info["darkness"] = _darkness(still_a, info["point_a"])
    n = max(2, int(round(duration * fps)))
    return _Rig(still_a, still_b, info["kind"], size, fps, n, seed, params, info), info

def render_link(still_a, still_b, kind, out_path, duration=1.2, fps=30, size=(1920, 1080), seed=0, params=None, cancel=None, progress=None):
    """Render the link clip A -> B to out_path. Cached; safe from several threads/processes; a cancelled or failed render leaves no partial file."""
    params = dict(params or {}); cancel = cancel or params.pop("cancel", None); progress = progress or params.pop("progress", None)
    size = (int(size[0]) // 2 * 2, int(size[1]) // 2 * 2)
    if kind not in KINDS: raise LinkError(f"unknown link kind {kind!r}; use one of {KINDS}")
    if not (duration and duration > 0): raise LinkError(f"duration must be > 0, got {duration!r}")
    if fps <= 0: raise LinkError(f"fps must be > 0, got {fps!r}")
    for p_ in (still_a, still_b):
        if not os.path.isfile(str(p_)): raise LinkError(f"still not found: {p_}")
    _intensity(params.get("intensity", "medium"))
    n = max(1, int(round(duration * fps))); out_path = str(out_path); out_dir = os.path.dirname(os.path.abspath(out_path)); os.makedirs(out_dir, exist_ok=True)
    key = _key(still_a, still_b, kind, duration, fps, size, seed, params); CACHE_DIR.mkdir(parents=True, exist_ok=True); cached = CACHE_DIR / f"{key}.mp4"
    if not cached.exists() or cached.stat().st_size == 0:
        if cancel and cancel(): raise Cancelled("link render cancelled")
        rig, _ = make_rig(still_a, still_b, kind, max(duration, 2.0 / fps), fps, size, seed, params); rig.n = max(2, n)
        fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".part.mp4"); os.close(fd)
        sink = _Sink(size, fps, tmp)
        try:
            for i in range(n):
                if cancel and cancel(): raise Cancelled("link render cancelled")
                sink.write(rig.frame(i).tobytes())
                if progress: progress((i + 1) / n)
            sink.close(); os.replace(tmp, cached)
        except BaseException:
            sink.abort()
            try: os.unlink(tmp)
            except OSError: pass
            raise
    fd, tmp2 = tempfile.mkstemp(dir=out_dir, suffix=".part"); os.close(fd)
    try: shutil.copyfile(cached, tmp2); os.replace(tmp2, out_path)
    except BaseException:
        try: os.unlink(tmp2)
        except OSError: pass
        raise
    return out_path
