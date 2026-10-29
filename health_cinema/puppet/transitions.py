"""Character-carrying transitions between two stills.

Each transition is built for direction 'right' from two Fit objects (scene.Fit) and returns per-t state: the world frame (already composed from both
stills), occluder mask, depth, the puppet's screen placement (x, y feet, h px, alpha, walk phase in strides) and extras (iris darkness, pan, light).
For direction 'left' the renderer mirrors the inputs (mirror_fit), runs the same code and mirrors the outputs, so the stills themselves are never flipped.
Registry: TRANSITIONS / make()."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
from .scene import Fit, Scene, shapes_mask

STRIDE = 0.62   # one walk cycle covers this many character heights of ground

def ease(u): u = min(max(u, 0.0), 1.0); return u * u * (3 - 2 * u)
def lerp(a, b, t): return a + (b - a) * t

@dataclass
class TFrame:
    img: Image.Image
    occ: Image.Image | None
    depth: np.ndarray | None
    char: dict | None          # x, y (feet), h (px), alpha, phase (cycles), fit: 'a' | 'b' | float weight toward b
    light_w: float = 0.0       # 0 = still A's light, 1 = still B's
    dark: float = 0.0
    dark_xy: tuple = (.5, .5)
    pan: tuple = (0.0, 0.0)
    par: tuple = (0.0, 0.0)
    zoom: float = 1.0
    fade: float = 0.0

def torn_line(rng, n: int, amp: float) -> np.ndarray:
    """Smooth wandering torn-edge offset of n samples: slow drift plus a little fine fraying (not a regular zigzag)."""
    def band(k): return np.asarray(Image.fromarray(rng.standard_normal((1, k)).astype(np.float32)).resize((n, 1), Image.BICUBIC))[0]
    return band(9) * amp + band(40) * amp * .22 + band(160) * amp * .08

def mirror_fit(f: Fit) -> Fit:
    sc = f.scene
    light = dict(sc.light); light["shadow_dx"] = -light.get("shadow_dx", .3)
    doors = [(1 - cx, b, w, h) for cx, b, w, h in sc.doors]
    ns = Scene(sc.key, sc.size, sc.horizon, sc.walk_y, light, doors, sc.depth[:, ::-1].copy(), sc.occ[:, ::-1].copy(), sc.path, sc.extra)
    return Fit(ns, f.rgb.transpose(Image.FLIP_LEFT_RIGHT), f.depth[:, ::-1].copy(), f.occ.transpose(Image.FLIP_LEFT_RIGHT), f.size, f.zoom)

def mix_light(la: dict, lb: dict, w: float) -> dict:
    if w <= 0: return la
    if w >= 1: return lb
    return {k: ([lerp(x, y, w) for x, y in zip(la[k], lb[k])] if isinstance(la[k], list) else lerp(la[k], lb[k], w)) for k in la}

class Trans:
    name = ""
    def __init__(self, fa: Fit, fb: Fit, size, params=None, seed: int = 5):
        self.fa, self.fb, self.size = fa, fb, size; self.W, self.H = size; self.p = params or {}; self.rng = np.random.default_rng(seed)
        for f, k in ((fa, "y_a"), (fb, "y_b")):
            if self.p.get(k) is not None: f.ground = float(self.p[k])
        self.ch = self.p.get("char_h", .44) * self.H; self.stride = self.p.get("stride_ratio", STRIDE)
        self.xs = []
        self._tab = None
    def h_at(self, fit: Fit, y: float) -> float: return self.ch * fit.scene.scale_at(y / self.H)
    def wpath(self, u): raise NotImplementedError   # (x, y, h) in ground-plane pixels including any scroll
    def phase(self, u: float) -> float:
        if self._tab is None:
            n = 400; pts = [self.wpath(i / n) for i in range(n + 1)]; tab = [0.0]
            for (x0, y0, h0), (x1, y1, h1) in zip(pts, pts[1:]): tab.append(tab[-1] + math.hypot(x1 - x0, y1 - y0) / (self.stride * (h0 + h1) / 2))
            self._tab = np.array(tab)
        return float(np.interp(u * 400, np.arange(401), self._tab))
    def frame(self, u: float) -> TFrame: raise NotImplementedError

# --------------------------------------------------------------------------------------------------------------------------------------------------
class TearSeam(Trans):
    """World scrolls left under a fixed-x puppet; the two stills are joined by a torn paper seam with a cream edge and a soft shadow."""
    name = "tear_seam"
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        W, H = self.W, self.H; self.xc = self.p.get("char_x", .34) * W; k = W / 1920.0
        seam_c = W + int(50 * k); self.xb = seam_c - 30                 # B's left edge; its column 30 sits at the seam centre, so the seam starts just off-screen
        seam = seam_c + torn_line(self.rng, H, 22 * k)
        pad = int(120 * k) + 40
        A = np.asarray(self.fa.rgb, dtype=np.float32); A = np.pad(A, ((0, 0), (0, pad), (0, 0)), mode="constant", constant_values=0); A[:, -pad:] = np.median(A[:, -pad - 24:-pad], axis=(0, 1)); B = np.asarray(self.fb.rgb, dtype=np.float32)
        SW = W + self.xb; strip = np.zeros((H, SW, 3), np.float32); strip[:, :W + pad] = A
        x0 = self.xb - 40; x1 = self.xb + 120; cols = np.arange(x0, x1)[None, :]
        d = (cols - seam[:, None]).astype(np.float32); band = strip[:, x0:x1].copy()
        sh = np.clip(1 + d / (42 * k), 0, 1) * (d < 0) * .5; band = band * (1 - sh[..., None])
        bb = B[:, np.clip(cols[0] - self.xb, 0, W - 1)]
        edge = ((d >= 0) & (d < 14 * k))[..., None]; vis = (d >= 0)[..., None]
        band = np.where(vis, np.where(edge, np.array([244, 236, 218], np.float32), bb), band)
        strip[:, x0:x1] = band; strip[:, x1:] = B[:, x1 - self.xb:]
        self.strip = Image.fromarray(np.clip(strip, 0, 255).astype(np.uint8))
        self.dstrip = np.zeros((H, SW), np.float32); self.dstrip[:, :W] = self.fa.depth; self.dstrip[:, self.xb + 40:] = self.fb.depth[:, 40:]
        self.ostrip = Image.new("L", (SW, H), 0); self.ostrip.paste(self.fa.occ, (0, 0)); self.ostrip.paste(self.fb.occ.crop((40, 0, W, H)), (self.xb + 40, 0))
        self.seam_x = self.xb + 30; self.k = k
    def cam(self, u):
        a = b = .16; v = 1 / (1 - (a + b) / 2)
        p = v * u * u / (2 * a) if u < a else 1 - v * (1 - u) ** 2 / (2 * b) if u > 1 - b else v * a / 2 + v * (u - a)
        return min(max(p, 0.0), 1.0) * self.xb
    def wpath(self, u): return (self.cam(u) + self.xc, self.fa.walk_y, self.ch)
    def frame(self, u):
        cam = self.cam(u); ci = int(cam); W, H = self.W, self.H
        img = self.strip.crop((ci, 0, ci + W, H)); occ = self.ostrip.crop((ci, 0, ci + W, H)); dep = self.dstrip[:, ci:ci + W]
        wx = cam + self.xc; w = ease((wx - self.seam_x + 40 * self.k) / (90 * self.k))
        y = lerp(self.fa.walk_y, self.fb.walk_y, w)
        return TFrame(img, occ, dep, dict(x=self.xc, y=y, h=self.ch, alpha=1.0, phase=self.phase(u)), light_w=w, pan=(cam - ci, 0), par=(8 * math.sin(math.pi * u), 0))

# --------------------------------------------------------------------------------------------------------------------------------------------------
class DoorWalk(Trans):
    """Camera pushes toward a doorway-shaped dark region in A while the puppet walks into it and the screen irises to black; B opens from a doorway of B
    and the puppet walks out into the light."""
    name = "door_walk"
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        W, H = self.W, self.H
        da = self.p.get("door_a") or (self.fa.scene.doors[0] if self.fa.scene.doors else (.5, .55, .06, .18))
        db = self.p.get("door_b") or (self.fb.scene.doors[0] if self.fb.scene.doors else (.5, .55, .06, .18))
        self.da = (da[0] * W, da[1] * H, da[2] * W, da[3] * H); self.db = (db[0] * W, db[1] * H, db[2] * W, db[3] * H)
        self.zmax = float(self.p.get("door_zoom", 1.55))
        ya = max(self.da[1] + .12 * H, min(self.fa.walk_y, self.da[1] + .35 * H)); xa = self.da[0] - .26 * W
        self.pa0 = (min(max(xa, .08 * W), .92 * W), ya, self.h_at(self.fa, ya)); self.pa1 = (self.da[0], self.da[1], .86 * self.da[3])
        ye = max(self.db[1] + .14 * H, min(self.fb.walk_y, self.db[1] + .4 * H)); xe = self.db[0] + .22 * W
        self.pb0 = (self.db[0], self.db[1], .86 * self.db[3]); self.pb1 = (min(xe, .9 * W), ye, self.h_at(self.fb, ye))
    @staticmethod
    def _lh(a, b, p): return (lerp(a[0], b[0], p), lerp(a[1], b[1], p), a[2] * (b[2] / max(a[2], 1)) ** p)
    def wpath(self, u):
        if u < .5: return self._lh(self.pa0, self.pa1, ease(u / .5)**.9)
        return self._lh(self.pb0, self.pb1, ease((u - .5) / .5)**.9)
    def _view(self, fit, focus, z):
        W, H = self.W, self.H
        l = min(max(focus[0] - W / (2 * z), 0), W - W / z); t = min(max(focus[1] - H / (2 * z), 0), H - H / z)
        box = (l, t, l + W / z, t + H / z)
        return fit.rgb.resize((W, H), Image.BICUBIC, box=box), fit.occ.resize((W, H), Image.BILINEAR, box=box), l, t
    def frame(self, u):
        W, H = self.W, self.H
        if u < .5:
            q = u / .5; p = ease(q); z = 1 + (self.zmax - 1) * p ** 1.3; door = self.da; fit = self.fa
            focus = (lerp(W / 2, door[0], p), lerp(H / 2, door[1] - door[3] / 2, p))
            x, y, h = self.wpath(u); alpha = 1 - ease((q - .7) / .22); dark = .5 * ease((q - .35) / .55); fade = ease((q - .86) / .14)
        else:
            q = (u - .5) / .5; p = 1 - ease(q); z = 1 + (self.zmax - 1) * p ** 1.3; door = self.db; fit = self.fb
            focus = (lerp(W / 2, door[0], p), lerp(H / 2, door[1] - door[3] / 2, p))
            x, y, h = self.wpath(u); alpha = ease((q - .08) / .22); dark = .5 * (1 - ease(q / .6)); fade = 1 - ease(q / .14)
        img, occ, l, t = self._view(fit, focus, z)
        dxy = ((door[0] - l) * z / W, (door[1] - door[3] * .4 - t) * z / H)
        ch = dict(x=(x - l) * z, y=(y - t) * z, h=h * z, alpha=alpha, phase=self.phase(u))
        return TFrame(img, occ, None, ch, light_w=0.0 if u < .5 else 1.0, dark=dark, dark_xy=dxy, fade=fade)

# --------------------------------------------------------------------------------------------------------------------------------------------------
class PageFlip(Trans):
    """A is a page that turns about the left edge (squeezes toward the spine with a shaded curl) revealing B; the puppet keeps walking across on top."""
    name = "page_flip"
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.A = np.asarray(self.fa.rgb, dtype=np.float32); self.B = np.asarray(self.fb.rgb, dtype=np.float32)
        W = self.W; self.x0 = self.p.get("char_x0", .2) * W; self.x1 = self.p.get("char_x1", .8) * W
    def pos(self, u): return lerp(self.x0, self.x1, ease(u) * .35 + u * .65)
    def wpath(self, u): return (self.pos(u), lerp(self.fa.walk_y, self.fb.walk_y, ease((u - .35) / .3)), self.ch)
    def frame(self, u):
        W, H = self.W, self.H; p = ease(min(max((u - .12) / .76, 0), 1)); w = max(int(W * (1 - p)), 1)
        out = self.B.copy()
        occ = np.asarray(self.fb.occ, dtype=np.uint8).copy()
        if w > 2:
            a = np.asarray(self.fa.rgb.resize((w, H), Image.BILINEAR), dtype=np.float32)
            xs = np.arange(w, dtype=np.float32); curl = np.clip((xs - (w - .22 * W * min(1, p * 3 + .15))) / (.22 * W), 0, 1)
            a = a * (1 - .38 * curl)[None, :, None] ** 1
            a[:, max(w - 3, 0):] = np.array([246, 240, 224])
            skew = int(.05 * H * math.sin(math.pi * p)); rows = np.arange(H)
            top = skew * (np.arange(w) / max(w, 1)); vis = (rows[:, None] >= top[None, :]) & (rows[:, None] < H - top[None, :])
            sw = min(int(.05 * W), W - w)
            if sw > 0:
                gx = np.arange(sw, dtype=np.float32); sh = (1 - gx / sw) ** 2 * .42 * min(1, p * 4)
                out[:, w:w + sw] *= (1 - sh)[None, :, None]
            out[:, :w] = np.where(vis[..., None], a, out[:, :w])
            ao = np.asarray(self.fa.occ.resize((w, H), Image.BILINEAR)); occ[:, :w] = np.where(vis, ao, occ[:, :w])
        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
        x, y, h = self.wpath(u)
        return TFrame(img, Image.fromarray(occ), None, dict(x=x, y=y, h=h, alpha=1.0, phase=self.phase(u)), light_w=ease((u - .35) / .3))

# --------------------------------------------------------------------------------------------------------------------------------------------------
class BehindObject(Trans):
    """A torn paper pillar sweeps across the frame, swapping A for B behind it; the puppet walks across and passes behind the pillar."""
    name = "behind_object"
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        W, H = self.W, self.H; self.pw = int(self.p.get("pillar_w", .13) * W)
        r = self.rng; k = W / 1920.0; edge = torn_line(r, H, 9 * k); edge2 = torn_line(r, H, 9 * k); m = int(14 * k); rm = int(6 * k) + 1
        cols = np.arange(self.pw)[None, :]
        al = ((cols >= (m + edge)[:, None]) & (cols < (self.pw - m + edge2)[:, None]))
        tone = np.array(self.fa.scene.light["tone"], np.float32) * .5 + np.array([105, 76, 48], np.float32) * .5
        streak = np.asarray(Image.fromarray(r.standard_normal((6, self.pw // 2 + 2)).astype(np.float32)).resize((self.pw, H), Image.BICUBIC)) * 16
        fine = np.asarray(Image.fromarray(r.standard_normal((H // 3, self.pw // 3 + 1)).astype(np.float32)).resize((self.pw, H), Image.BILINEAR)) * 6
        rim = ((cols >= (m + edge)[:, None]) & (cols < (m + rm + edge)[:, None])) | ((cols < (self.pw - m + edge2)[:, None]) & (cols >= (self.pw - m - rm + edge2)[:, None]))
        col = np.clip(tone[None, None, :] + (streak + fine)[..., None], 0, 255); col = np.where(rim[..., None], np.array([240, 230, 208], np.float32), col)
        self.pil = Image.fromarray(np.concatenate([col, (al * 255)[..., None]], 2).astype(np.uint8), "RGBA")
        self.pocc = Image.fromarray((al * 255).astype(np.uint8))
        self.pshadow = self.pil.split()[3].filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * .5))
        self.xs0 = self.p.get("char_x0", .12) * W; self.xs1 = self.p.get("char_x1", .88) * W
        self.Af = np.asarray(self.fa.rgb); self.Bf = np.asarray(self.fb.rgb)
        self.Ao = np.asarray(self.fa.occ); self.Bo = np.asarray(self.fb.occ)
    def px(self, u): return lerp(-.12 * self.W, 1.12 * self.W, ease(u) * .35 + u * .65)
    def cx(self, u): return lerp(self.xs0, self.xs1, u)
    def wpath(self, u):
        side = ease((self.cx(u) - self.px(u)) / 80 * -1 + .5)
        return (self.cx(u), lerp(self.fa.walk_y, self.fb.walk_y, side), self.ch)
    def frame(self, u):
        W, H = self.W, self.H; P = int(self.px(u))
        m = np.arange(W)[None, :] < P
        img = np.where(m[..., None], self.Bf, self.Af); occ = np.where(m, self.Bo, self.Ao)
        im = Image.fromarray(img.astype(np.uint8)); ox = P - self.pw // 2
        im.paste((0, 0, 0), (ox - 6, 0), self.pshadow); im.paste(self.pil.convert("RGB"), (ox, 0), self.pil.split()[3])
        o = Image.fromarray(occ.astype(np.uint8)); o.paste(255, (ox, 0), self.pocc)
        x, y, h = self.wpath(u); w = ease(-(self.cx(u) - self.px(u)) / 120 + .5)
        return TFrame(im, o, None, dict(x=x, y=y, h=h, alpha=1.0, phase=self.phase(u)), light_w=w)

TRANSITIONS = {c.name: c for c in (TearSeam, DoorWalk, PageFlip, BehindObject)}

def list_transitions() -> list: return list(TRANSITIONS)

def make(name: str, fa: Fit, fb: Fit, size, params=None, seed: int = 5) -> Trans:
    if name not in TRANSITIONS: raise ValueError(f"unknown transition {name!r}; choose from {list(TRANSITIONS)}")
    return TRANSITIONS[name](fa, fb, size, params, seed)
