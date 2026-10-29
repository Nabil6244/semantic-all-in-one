"""Still analysis for the puppet layer: ground line, perspective, pseudo-depth, foreground occluders, doorways and lighting.

Pure numpy + Pillow. The analysis of one still is cached under out/puppet_cache/ keyed by the pixel hash and VERSION. `analyse()` returns a Scene;
`Scene.fit(size)` resizes the still and the maps to the render size. All coordinates inside Scene are fractions of width/height."""
from __future__ import annotations
import hashlib, json, os, tempfile
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

VERSION = "5"
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "out" / "puppet_cache"
AN = 480   # analysis width; the occluder mask is refined to full size in fit()

class SceneError(RuntimeError): pass

def _box(a: np.ndarray, r: int) -> np.ndarray:
    """Separable box blur of a 2-D array (edge-padded), radius r."""
    if r <= 0: return a
    k = 2 * r + 1
    p = np.pad(a, ((r, r), (r, r)), mode="edge")
    c = np.cumsum(p, axis=0, dtype=np.float64); c = np.concatenate([np.zeros((1, c.shape[1])), c])
    p = (c[k:] - c[:-k])
    c = np.cumsum(p, axis=1); c = np.concatenate([np.zeros((c.shape[0], 1)), c], axis=1)
    return ((c[:, k:] - c[:, :-k]) / (k * k)).astype(np.float32)

def _load(path) -> Image.Image:
    try:
        with Image.open(path) as im: return im.convert("RGB")
    except Exception as e:
        raise SceneError(f"cannot read still {path}: {e}") from e

def _hash(im: Image.Image) -> str:
    t = im.resize((128, 72), Image.BILINEAR)
    return hashlib.sha256(VERSION.encode() + t.tobytes() + str(im.size).encode()).hexdigest()[:20]

@dataclass
class Scene:
    key: str
    size: tuple                # original (w, h)
    horizon: float             # fraction of height where the floor meets the back wall
    walk_y: float              # fraction of height of the default walking line
    light: dict                # tone / dark rgb, tint multiplier, shadow dx
    doors: list                # [(cx, base_y, w, h)] dark doorway-like regions (fractions)
    depth: np.ndarray          # float32 0..1 (1 = near) at AN width
    occ: np.ndarray            # uint8 0/255 at AN width
    path: str = ""
    extra: dict = field(default_factory=dict)
    floor_conf: float = 0.0    # 0..1 confidence that the picture shows a real walkable ground plane across the lower part
    floor_ok: bool = False     # floor_conf is high enough for the planner to put a character on this picture

    def scale_at(self, y_frac: float) -> float:
        """Character height multiplier at screen row y_frac relative to the walking line (simple linear perspective)."""
        return float(np.clip((y_frac - self.horizon) / max(self.walk_y - self.horizon, 0.05), 0.3, 2.2))

    def fit(self, size, zoom: float = 1.0, shapes=None, auto_occ: bool = True):
        """-> Fit: RGB image, float depth map and occluder L mask at `size`, cover-fitted and zoomed about the centre."""
        W, H = size; w0, h0 = self.size
        s = max(W / w0, H / h0) * zoom
        im = _load(self.path).resize((max(W, round(w0 * s)), max(H, round(h0 * s))), Image.LANCZOS)
        ox, oy = (im.width - W) // 2, (im.height - H) // 2
        im = im.crop((ox, oy, ox + W, oy + H))
        def up(a, mode):
            t = Image.fromarray(a).resize((max(W, round(w0 * s)), max(H, round(h0 * s))), Image.BILINEAR if mode == "b" else Image.LANCZOS)
            return t.crop((ox, oy, ox + W, oy + H))
        depth = np.asarray(up((self.depth * 255).astype(np.uint8), "b"), dtype=np.float32) / 255.0
        occ = up(self.occ, "b").filter(ImageFilter.GaussianBlur(1.2)) if auto_occ else Image.new("L", (W, H), 0)
        if shapes:
            m = shapes_mask((W, H), shapes); occ = Image.fromarray(np.maximum(np.asarray(occ), np.asarray(m)))
        return Fit(self, im, depth, occ, size, zoom)

@dataclass
class Fit:
    scene: Scene; rgb: Image.Image; depth: np.ndarray; occ: Image.Image; size: tuple; zoom: float; ground: float = None
    @property
    def walk_y(self) -> float: return (self.scene.walk_y if self.ground is None else self.ground) * self.size[1]
    @property
    def horizon(self) -> float: return self.scene.horizon * self.size[1]

def shapes_mask(size, shapes) -> Image.Image:
    """Occluder hints in fractions: ('rect', x0, y0, x1, y1) or ('poly', [(x, y), ...])."""
    W, H = size; m = Image.new("L", size, 0); d = ImageDraw.Draw(m)
    for s in shapes or []:
        if s[0] == "rect": d.rectangle([s[1] * W, s[2] * H, s[3] * W, s[4] * H], fill=255)
        elif s[0] == "poly": d.polygon([(x * W, y * H) for x, y in s[1]], fill=255)
    return m

def _cutouts(im: Image.Image, walk: float, pic, size) -> np.ndarray:
    """Foreground cut-out pieces: collage cut-outs are ringed by a thin cream paper edge, so regions the ring seals off from the main picture are candidates.
    Kept only when they are mid-sized, hang from the bottom of the picture and are not a wide scene half; at most two."""
    from collections import deque
    B = 4; a = np.asarray(im, dtype=np.float32); H0, W0 = a.shape[:2]; h, w = H0 // B, W0 // B
    mx = a.max(2); mn = a.min(2); cream = (a.mean(2) > 205) & ((mx - mn) / (mx + 1) < .25)
    bar = cream[:h * B, :w * B].reshape(h, B, w, B).mean((1, 3)) > .10
    bar = np.asarray(Image.fromarray((bar * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    lab = np.full((h, w), -1, np.int32); sizes = []; boxes = []
    for y in range(h):
        for x in range(w):
            if bar[y, x] or lab[y, x] >= 0: continue
            k = len(sizes); q = deque([(y, x)]); lab[y, x] = k; n = 0; x0 = x1 = x; y0 = y1 = y
            while q:
                p, r = q.popleft(); n += 1
                x0 = min(x0, r); x1 = max(x1, r); y0 = min(y0, p); y1 = max(y1, p)
                for dp, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    pp, rr = p + dp, r + dr
                    if 0 <= pp < h and 0 <= rr < w and lab[pp, rr] < 0 and not bar[pp, rr]:
                        lab[pp, rr] = k; q.append((pp, rr))
            sizes.append(n); boxes.append((x0, y0, x1, y1))
    out = np.zeros((h, w), bool)
    if not sizes: return np.zeros((size[1], size[0]), bool)
    big = int(np.argmax(sizes)); area = h * w; kept = 0
    for k in np.argsort(sizes)[::-1]:
        x0, y0, x1, y1 = boxes[k]; n = sizes[k]
        if k == big or kept >= 2: continue
        if not (.015 * area <= n <= .11 * area): continue
        if (x1 - x0) > .47 * w or (y1 - y0) > .55 * h or y1 < .84 * h or y0 < .38 * h: continue
        if n < .45 * (x1 - x0 + 1) * (y1 - y0 + 1): continue
        out |= lab == k; kept += 1
    out = np.asarray(Image.fromarray((out * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
    return np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize((size[0], size[1]), Image.BILINEAR)) > 100

FLOOR_OK = .76

def _floor_conf(lum, sat, cream, pic, horizon: float, walk: float) -> float:
    """0..1 confidence that this picture is an environment with a ground plane to walk on (not objects floating on paper). Weights were tuned on 32 real
    collage stills: the picture must reach the lower rows (no page margin under the feet), fill the mid frame, be mostly dark/mid-tone (little blank paper)."""
    h, w = lum.shape; cl = lambda x: float(np.clip(x, 0, 1)); c0, c1 = int(w * .08), int(w * .92)
    cov = min(pic[int(y * h):int((y + .04) * h), c0:c1].mean() for y in (.80, .84, .88)); mid = pic[int(.5 * h):int(.8 * h), c0:c1].mean()
    A = lum[int(.05 * h):int(.92 * h), int(.05 * w):int(.95 * w)]; hh, ww = A.shape[0] // 20 * 20, A.shape[1] // 20 * 20
    if hh < 20 or ww < 20: return 0.0
    cells = A[:hh, :ww].reshape(hh // 20, 20, ww // 20, 20).mean((1, 3)); pale = (cells > 190).mean(); dark = (cells < 110).mean()
    conf = .2 * cl((cov - .7) / .28) + .2 * cl((mid - .55) / .4) + .3 * cl(1 - pale / .3) + .3 * cl(dark / .4)
    if walk - horizon < .2: conf *= .85
    return float(round(conf, 3))

def _analyse(im: Image.Image, key: str, path: str) -> Scene:
    w0, h0 = im.size; w = AN; h = round(h0 * w / w0)
    a = np.asarray(im.resize((w, h), Image.LANCZOS), dtype=np.float32)
    lum = a.mean(2); mx = a.max(2); mn = a.min(2); sat = (mx - mn) / (mx + 1)
    cream = (lum > 205) & (sat < 0.25)
    pic = _box(cream.astype(np.float32), 3) < 0.6   # inside the printed picture, not the page margin
    gy, gx = np.gradient(_box(lum, 1)); tex = _box(np.hypot(gx, gy), 3)
    t = tex / (np.percentile(tex, 95) + 1e-3)
    rows = np.arange(h, dtype=np.float32)[:, None] / h
    # horizon: strongest brightness change between wall and floor in the middle band
    prof = _box(lum, 2).mean(1); d = np.abs(np.diff(prof)); lo, hi = int(h * .28), int(h * .62)
    horizon = float(np.clip((lo + int(np.argmax(_box(d[None, :], 3)[0, lo:hi])) ) / h, .30, .58)) if hi > lo else .42
    # walk line: calmest row band in the lower part that is still inside the printed picture, biased toward 0.88
    rt = _box(t, 2).mean(1); lo, hi = int(h * .74), int(h * .915)
    c0, c1 = int(w * .08), int(w * .92)
    rcov = pic[:, c0:c1].mean(1)
    bias = np.abs(np.arange(lo, hi) / h - .88) * .6 + (1 - _box(rcov[None, :], 2)[0, lo:hi]) * 3
    walk = float(np.clip((lo + int(np.argmin(rt[lo:hi] / (rt[lo:hi].mean() + 1e-3) + bias))) / h, .78, .91))
    fconf = _floor_conf(lum, sat, cream, pic, horizon, walk)
    occ = _cutouts(im, walk, pic, (w, h))
    # pseudo depth
    depth = .55 * np.clip((rows - horizon * .6) / (1 - horizon * .6), 0, 1) * np.ones((1, w), np.float32) + .25 * np.clip(t, 0, 1.2) / 1.2 + .15 * (1 - lum / 255) * .8 + .0
    depth = np.maximum(depth, occ * 1.0)
    depth = np.clip(_box(depth, 4), 0, 1)
    # lighting
    pix = a[pic] if pic.sum() > 100 else a.reshape(-1, 3)
    tone = pix.mean(0); dark = np.percentile(pix, 8, axis=0)
    L = pix.mean(1); half = a[pic.any(1)][:, : w // 2].mean() - a[pic.any(1)][:, w // 2:].mean() if pic.any() else 0
    tint = tone / (tone.mean() + 1e-3)
    light = dict(tone=[float(x) for x in tone], dark=[float(x) for x in dark], tint=[float(x) for x in tint], shadow_dx=float(np.clip(-half / 40, -1, 1)) or .3, contrast=float(L.std() / 255))
    # doorways: darkest door-sized windows between the horizon and the walking line
    s8 = _box(lum, 1); doors = []; bw, bh = max(3, int(w * .045)), max(5, int(h * .16))
    cum = np.cumsum(np.cumsum(np.pad(s8, ((1, 0), (1, 0))), 0), 1)
    def mean_win(y, x): return (cum[y + bh, x + bw] - cum[y, x + bw] - cum[y + bh, x] + cum[y, x]) / (bw * bh)
    cand = []
    for y in range(int(h * max(horizon - .12, .18)), min(int(h * (walk + .02)), h - bh - 1), 3):
        for x in range(0, w - bw - 1, 3):
            if not pic[y + bh // 2, x + bw // 2]: continue
            m = mean_win(y, x); cand.append((m, x, y))
    cand.sort(); gl = lum[pic].mean() if pic.any() else 128
    for m, x, y in cand:
        if m > gl * .55 or len(doors) >= 3: break
        cx, base = (x + bw / 2) / w, (y + bh) / h
        if all(abs(cx - d[0]) > .08 for d in doors): doors.append((float(cx), float(base), bw / w, bh / h))
    return Scene(key, (w0, h0), horizon, walk, light, doors, depth.astype(np.float32), (occ * 255).astype(np.uint8), path, floor_conf=fconf, floor_ok=fconf >= FLOOR_OK)

def analyse(path, cache: bool = True) -> Scene:
    path = str(path); im = _load(path); key = _hash(im)
    f = CACHE_DIR / f"scene_{key}"
    if cache and f.with_suffix(".json").exists() and f.with_suffix(".npz").exists():
        try:
            j = json.loads(f.with_suffix(".json").read_text()); z = np.load(f.with_suffix(".npz"))
            return Scene(key, tuple(j["size"]), j["horizon"], j["walk_y"], j["light"], [tuple(d) for d in j["doors"]], z["depth"].astype(np.float32), z["occ"], path,
                         floor_conf=float(j.get("floor_conf", 0.0)), floor_ok=bool(j.get("floor_ok", False)))
        except Exception: pass
    sc = _analyse(im, key, path)
    if cache:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            for suf, writer in ((".npz", lambda p: np.savez_compressed(p, depth=sc.depth.astype(np.float16), occ=sc.occ)),
                                (".json", lambda p: Path(p).write_text(json.dumps(dict(size=sc.size, horizon=sc.horizon, walk_y=sc.walk_y, light=sc.light, doors=sc.doors, floor_conf=sc.floor_conf, floor_ok=bool(sc.floor_ok)))))):
                fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=suf); os.close(fd); writer(tmp); os.replace(tmp, f.with_suffix(suf))
        except OSError: pass
    return sc

def tint_character(rgba: Image.Image, light: dict, strength: float = .55) -> Image.Image:
    """Pull the puppet's colours toward the still's tone: multiply by the scene tint and lift blacks to the scene's dark colour."""
    a = np.asarray(rgba, dtype=np.float32); rgb = a[..., :3]
    tint = np.array(light["tint"], np.float32); dark = np.array(light["dark"], np.float32)
    mul = 1 + (tint - 1) * strength
    lifted = rgb * mul * (1 - .12 * strength) + dark * (.12 * strength) * (1 - rgb / 255)
    out = np.concatenate([np.clip(lifted, 0, 255), a[..., 3:]], axis=2).astype(np.uint8)
    return Image.fromarray(out, "RGBA")

def ground_shadow(box_size, foot, char_h: float, light: dict, opacity: float = .55) -> Image.Image:
    """Soft elliptical contact shadow as an RGBA layer of `box_size`, centred at `foot` (px in that layer) and leaning with the light."""
    sh = Image.new("RGBA", box_size, (0, 0, 0, 0)); d = ImageDraw.Draw(sh)
    fx, fy = foot; dx = light.get("shadow_dx", .3) * char_h * .30
    rw, rh = char_h * .34, char_h * .055
    d.ellipse([fx - rw + dx, fy - rh, fx + rw + dx, fy + rh], fill=(*[int(c * .35) for c in light["dark"]], int(255 * opacity)))
    d.ellipse([fx - rw * .45, fy - rh * .6, fx + rw * .45, fy + rh * .6], fill=(*[int(c * .25) for c in light["dark"]], int(255 * min(opacity * 1.3, .9))))   # darker contact core under the feet
    return sh.filter(ImageFilter.GaussianBlur(max(2, char_h * .018)))
