"""Fast local shot compositor: ONE still picture -> a moving, grained, vignetted shot mp4 with ffmpeg and no per-frame Python.

    render_shot(job, out_path)  job = {still, duration, fps, size, seed, treatment, tparams, env, intensity, shot_id}

Depth treatments split the still into far / mid / near layers with the depth model; the far and mid layers are INPAINTED behind the nearer
ones, so a parallax move never shows ghosts or double edges. Every layer moves as one rigid scale+crop (no warps). The layers are decoded
once (single-frame input + loop) and the encoder is h264_videotoolbox when the Mac has it."""
from __future__ import annotations
import hashlib, json, math, os, shutil, subprocess, tempfile, threading, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CODE_VERSION = "sf-compose-13"
JOIN_VERSION = "join-5"                  # bump when the join code changes: only shots that carry a join are re-rendered
CACHE = ROOT / "out" / "story_fast_cache"
OV = 1.3                                  # layer canvas = output size * OV (no upscaling while the camera stays inside 1.3x)

TREATMENTS = {
    "push_in": "slow rigid push-in toward the middle of the picture",
    "pull_out": "starts tight and eases out to the full picture",
    "pan_left": "camera pans left across the picture",
    "pan_right": "camera pans right across the picture",
    "tilt_up": "camera tilts up",
    "tilt_down": "camera tilts down",
    "parallax_left": "depth-layer parallax, camera slides left (near layers move more)",
    "parallax_right": "depth-layer parallax, camera slides right (near layers move more)",
    "dolly_through": "push-in with strong depth separation, the near layer rushes past",
    "arc": "parallax slide that also rises, like a camera crane arc",
    "reveal_up": "starts low and tight, tilts up and eases out to reveal the scene",
    "track_lateral": "long slow lateral track with strong depth separation",
    "handheld": "subtle organic handheld drift and shake over a slow push",
    "hold_alive": "almost still but alive: tiny drift plus floating dust",
}
ENVIRONMENTS = {
    "dust": "floating dust motes drifting in the light",
    "fog": "slow low mist drifting across the frame",
    "embers": "warm sparks rising",
    "rain": "fine rain streaks falling",
    "snow": "soft snowflakes falling",
    "light_sweep": "one soft diagonal light band sweeps across the shot",
    "shimmer": "gentle breathing light and tiny sparkles",
    "none": "no overlay",
}
_DEPTH_TREATMENTS = {"parallax_left", "parallax_right", "dolly_through", "arc", "reveal_up", "track_lateral"}

class ComposeError(RuntimeError): pass
class Cancelled(ComposeError): pass

# ---------------------------------------------------------------- encoder / ffmpeg
_enc = None; _enc_lock = threading.Lock()

def _ffmpeg() -> str:
    from health_cinema.puppet import motion
    return motion._ffmpeg()

def available_encoder() -> str:
    global _enc
    with _enc_lock:
        if _enc is None:
            _enc = "libx264"
            try:
                ff = _ffmpeg()
                lst = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
                if "h264_videotoolbox" in lst:
                    r = subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=30:d=0.2", "-c:v", "h264_videotoolbox",
                                        "-b:v", "1M", "-pix_fmt", "yuv420p", "-f", "null", "-"], capture_output=True, timeout=30)
                    if r.returncode == 0: _enc = "h264_videotoolbox"
            except Exception:
                _enc = "libx264"
        return _enc

# ---------------------------------------------------------------- keys / hashing
_hash_memo: dict = {}; _hash_lock = threading.Lock()

def _file_hash(path: str) -> str:
    p = os.path.abspath(path); st = os.stat(p); k = (p, st.st_size, st.st_mtime_ns)
    with _hash_lock:
        h = _hash_memo.get(k)
    if h: return h
    d = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): d.update(b)
    h = d.hexdigest()[:24]
    with _hash_lock: _hash_memo[k] = h
    return h

def _norm(job: dict) -> dict:
    size = tuple(int(v) for v in (job.get("size") or (1920, 1080)))
    tr = job.get("treatment") or "push_in"
    if tr not in TREATMENTS: tr = "push_in"
    tp = dict(job.get("tparams") or {})
    env = [e for e in (job.get("env") or []) if e in ENVIRONMENTS and e != "none"]
    inten = job.get("intensity") if job.get("intensity") in ("low", "medium", "high") else "medium"
    fps = int(job.get("fps") or 30)
    dur = max(0.1, float(job.get("duration") or 3.0))
    return {"still": job["still"], "duration": dur, "fps": fps, "size": size, "seed": int(job.get("seed") or 0), "treatment": tr, "tparams": tp,
            "env": env, "intensity": inten, "shot_id": job.get("shot_id"), "grade_vf": str(job.get("grade_vf") or "")}

def job_key(job: dict) -> str:
    j = _norm(job)
    body = {"still": _file_hash(j["still"]), "dur": round(j["duration"], 3), "fps": j["fps"], "size": list(j["size"]), "tr": j["treatment"],
            "tp": {k: j["tparams"][k] for k in sorted(j["tparams"])}, "env": j["env"], "seed": j["seed"], "int": j["intensity"], "v": CODE_VERSION}
    if j["grade_vf"]: body["gr"] = j["grade_vf"]
    if j["tparams"].get("join"): body["jv"] = JOIN_VERSION
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:32]

# ---------------------------------------------------------------- layers
_locks: dict = {}; _locks_lock = threading.Lock(); _depth_lock = threading.Lock()

def _lock_for(k):
    with _locks_lock: return _locks.setdefault(k, threading.Lock())

def _depth_available() -> bool:
    try:
        from health_cinema.puppet import depth as dp
        return bool(dp.available())
    except Exception:
        return False

def _depth(path: str) -> np.ndarray:
    """float32 (H, W) 0..1, 1 = near, at the picture's own size (tests replace this with a synthetic map)."""
    from health_cinema.puppet import depth as dp
    return dp.depth_map(path)

def _even(v): return max(2, int(v) // 2 * 2)

def _cover(im: Image.Image, cw: int, ch: int) -> Image.Image:
    s = max(cw / im.width, ch / im.height); w, h = max(cw, round(im.width * s)), max(ch, round(im.height * s))
    im = im.resize((w, h), Image.LANCZOS); x, y = (w - cw) // 2, (h - ch) // 2
    return im.crop((x, y, x + cw, y + ch))

_swept = set()
def _sweep_parts(shots: Path):
    """Partial files left by a process that died (kill -9, power cut): remove the ones whose process is gone. Once per cache folder per run."""
    if str(shots) in _swept: return
    _swept.add(str(shots))
    for f in list(shots.glob("*.part.mp4*")):
        try:
            pid = int(f.name.split(".")[1])
            if pid == os.getpid(): continue
            try: os.kill(pid, 0); continue                      # still running: not ours to touch
            except ProcessLookupError: pass
            except PermissionError: continue
            f.unlink()
        except Exception: pass

QUALITY_TAG = "q2"
EDGE_TOL, EDGE_GRAD, EDGE_Q_MIN = 2, 25.0, 0.80   # layer boundary must sit within 2 px of a strong picture edge on >= 80% of its length, else the layer would drag background
def _edge_map(rgb: np.ndarray):
    g = np.asarray(Image.fromarray(rgb).convert("L").filter(ImageFilter.GaussianBlur(1.2)), np.float32)
    gy, gx = np.gradient(g)
    return np.hypot(gx, gy) > EDGE_GRAD

def panel_split(rgb: np.ndarray) -> bool:
    """A picture divided into panels (a long straight dividing line across most of the frame): depth layers would tear it."""
    h, w = rgb.shape[:2]; sc = max(1, w // 640)
    e = _edge_map(rgb[::sc, ::sc]); hh, ww = e.shape
    cols = e[:, int(ww * .2):int(ww * .8)].mean(0); rows = e[int(hh * .2):int(hh * .8), :].mean(1)
    colmax = max(cols.max(), np.maximum.reduce([np.roll(cols, k) for k in (-1, 0, 1)]).max())
    return bool(colmax > .82 or rows.max() > .82)

def layer_quality(rgb: np.ndarray, masks) -> float:
    """0..1: how well the layer masks' boundaries lie on real picture edges (1 = the layers are cut-outs that follow the objects; low = blobs that would
    carry background along and show doubles / smears when moved). Worst layer counts; a layer that is almost everything or almost nothing scores 0."""
    from health_cinema.puppet import layers as lay
    ed = lay._dilate(_edge_map(rgb), EDGE_TOL); worst = 1.0
    for m in masks:
        if not (.03 < float(m.mean()) < .65): return 0.0
        inn = ~lay._dilate(~m, 2); bnd = m & ~inn
        if bnd.sum() < 50: return 0.0
        worst = min(worst, float(ed[bnd].mean()))
    return worst

def _env_for_background(env, still: str):
    """Warm specks (embers, dust) on a white-paper cartoon read as dirt on the page: only the light overlays stay there."""
    if not any(e in ("embers", "dust") for e in env): return env
    try:
        from story_fast import focus
        if focus.find_focus(still).get("bg") == "light": return [e for e in env if e not in ("embers", "dust")]
    except Exception: pass
    return env

def needs_depth(treatment: str, still: str) -> bool:
    """Depth layers only where they help: a depth treatment on a picture that is not a plain light-background explainer (those stay on the faster flat path)."""
    if treatment not in _DEPTH_TREATMENTS: return False
    try:
        from story_fast import focus
        return focus.find_focus(still).get("bg") != "light"
    except Exception: return True

def prepare(still: str, size: tuple, cache_dir: str | None = None, need_depth: bool = True) -> dict:
    """Cover-fit canvas (OV x output size) and, when the depth model is there, far/mid/near layers with hidden parts inpainted."""
    W, H = (int(size[0]), int(size[1])); cw, ch = _even(W * OV), _even(H * OV)
    base = Path(cache_dir) if cache_dir else CACHE / "layers"
    d = base / f"{_file_hash(still)}_{W}x{H}"
    with _lock_for(str(d)):
        d.mkdir(parents=True, exist_ok=True)
        fit_p = d / "fit.jpg"
        if not fit_p.is_file():
            im = _cover(Image.open(still).convert("RGB"), cw, ch)
            im.save(str(fit_p) + ".tmp.jpg", quality=95, subsampling=0); os.replace(str(fit_p) + ".tmp.jpg", fit_p)
        use_depth = False
        try: use_depth = bool(need_depth) and _depth_available()
        except Exception: use_depth = False
        paths = [str(d / "far.jpg"), str(d / "mid.png"), str(d / "near.png")]
        flat_p, q_p = d / "flat.txt", d / "quality.json"
        if use_depth and flat_p.is_file() and flat_p.read_text().startswith(QUALITY_TAG): use_depth = False       # judged unsafe for layers before: stays a rigid move
        if use_depth and not (q_p.is_file() and all(Path(p).is_file() for p in paths)):
            try: _build_layers(still, d, cw, ch, paths)
            except Exception as e:
                use_depth = False
                try: flat_p.write_text(f"{QUALITY_TAG} {e}")
                except OSError: pass
        quality = 0.0
        if use_depth:
            try: quality = float(json.loads(q_p.read_text())["q"])
            except Exception: use_depth = False
        if use_depth and all(Path(p).is_file() for p in paths):
            return {"layers": paths, "depth": True, "fit": str(fit_p), "quality": quality}
        return {"layers": [str(fit_p)], "depth": False, "fit": str(fit_p), "quality": 0.0}

def _build_layers(still, d: Path, cw, ch, paths):
    from health_cinema.puppet import layers as lay, motion as mo
    rgb_im = Image.open(d / "fit.jpg").convert("RGB"); rgb = np.asarray(rgb_im, np.uint8)
    with _depth_lock: dm = _depth(still)
    dm = np.asarray(Image.fromarray(dm.astype(np.float32), "F"), np.float32)
    # the depth map is at the picture's own size: cover-fit it the same way as the picture
    dim = Image.fromarray(dm, "F"); s = max(cw / dim.width, ch / dim.height); w, h = max(cw, round(dim.width * s)), max(ch, round(dim.height * s))
    dim = dim.resize((w, h), Image.BILINEAR); x, y = (w - cw) // 2, (h - ch) // 2
    dm = np.asarray(dim, np.float32)[y:y + ch, x:x + cw]
    from health_cinema.puppet import scene as sc
    dm = sc._box(sc._box(dm, max(2, cw // 120)), max(2, cw // 120))          # smooth: layers must be blobs, never cut-outs of text or fine detail
    lo, hi = np.percentile(dm, [2, 98]); dm = np.clip((dm - lo) / max(hi - lo, 1e-6), 0, 1)
    def soft(th):
        m = Image.fromarray((np.clip((dm - th) / .12, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(2, cw // 400)))
        return m
    mid_a, near_a = soft(.38), soft(.68)
    mid_m = np.asarray(mid_a) > 100; near_m = np.asarray(near_a) > 100
    for m in (mid_m, near_m):                                   # a shredded mask (labels, diagrams, noise) would tear the picture apart: stay flat
        edge = float((m[:, 1:] != m[:, :-1]).mean() + (m[1:] != m[:-1]).mean())
        if edge > .02: raise ValueError("depth too fragmented for layers")
    if panel_split(rgb): raise ValueError("picture is divided into panels: no layers")
    q = layer_quality(rgb, (mid_m, near_m))
    if q < EDGE_Q_MIN: raise ValueError(f"layer edges do not follow the objects (edge match {q:.2f}): no layers, rigid camera move")
    R = max(6, int(round(.032 * cw)))                            # a layer can uncover this much of what lies behind it
    near_d = lay._dilate(near_m, R); mn_d = lay._dilate(mid_m | near_m, R)
    far = np.where(mn_d[..., None], mo._inpaint(rgb, mn_d), rgb.astype(np.float32)).clip(0, 255).astype(np.uint8)
    mid = np.where(near_d[..., None], mo._inpaint(rgb, near_d), rgb.astype(np.float32)).clip(0, 255).astype(np.uint8)
    Image.fromarray(far).save(paths[0] + ".tmp.jpg", quality=95, subsampling=0); os.replace(paths[0] + ".tmp.jpg", paths[0])
    for p, a, im in ((paths[1], mid_a, mid), (paths[2], near_a, rgb)):
        L = Image.fromarray(im).convert("RGBA"); L.putalpha(a); L.save(p + ".tmp.png", compress_level=1); os.replace(p + ".tmp.png", p)
    (d / "quality.json").write_text(json.dumps({"q": round(q, 3)}))

# ---------------------------------------------------------------- camera
_INT = {"low": .6, "medium": 1.0, "high": 1.5}
_GAINS = {  # (pan gain, zoom gain) far, mid, near
    "soft": [(.7, .7), (1.0, 1.0), (1.35, 1.35)],
    "strong": [(.3, .3), (1.0, 1.0), (2.0, 2.0)],
    "track": [(.2, .2), (1.0, 1.0), (2.4, 1.2)],
}

def _ease(name: str, P: str) -> str:
    if name == "linear": return P
    if name == "in": return f"({P}*{P})"
    if name == "out": return f"(1-(1-{P})*(1-{P}))"
    return f"({P}*{P}*(3-2*{P}))"

def _camera(j: dict, depth: bool, quality: float = 1.0) -> dict:
    tr, tp = j["treatment"], j["tparams"]; I = _INT[j["intensity"]]
    a = float(np.clip(tp.get("amount", .5), 0, 1)); A = max(.05, a) * I * 2 * .5 * 2 * .5 * 1.0   # amount .5 at medium -> A = .5
    A = max(.05, a) * I
    d = tp.get("dir"); mx = my = dz = 0.0; gains = None; shake = 0.0
    sx = {"l": -1, "r": 1}.get(d, None); sy = {"up": -1, "down": 1}.get(d, None)
    if tr == "push_in": dz = .06 + .20 * A; mx = (sx or 0) * .01 * A
    elif tr == "pull_out": dz = -(.06 + .20 * A)
    elif tr in ("pan_left", "pan_right"): mx = (sx or (-1 if tr == "pan_left" else 1)) * (.04 + .12 * A); dz = .02
    elif tr in ("tilt_up", "tilt_down"): my = (sy or (-1 if tr == "tilt_up" else 1)) * (.04 + .12 * A); dz = .02
    elif tr in ("parallax_left", "parallax_right"):
        mx = (sx or (-1 if tr == "parallax_left" else 1)) * (.02 + .045 * A); dz = .03; gains = "soft" if False else "strong"
    elif tr == "dolly_through": dz = .05 + .12 * A; mx = (sx or 0) * .01 * A; gains = "strong"
    elif tr == "arc": mx = (sx or 1) * (.015 + .035 * A); my = (sy or -1) * (.012 + .025 * A); dz = .03; gains = "strong"
    elif tr == "reveal_up": my = (sy or -1) * (.04 + .08 * A); dz = -(.05 + .07 * A); gains = "soft"
    elif tr == "track_lateral": mx = (sx or 1) * (.035 + .07 * A); dz = .015; gains = "track"
    elif tr == "handheld": dz = .02 + .04 * A; shake = .0028 * I * (.5 + a)
    elif tr == "hold_alive":
        dz = .012 + .02 * A; mx = (sx or 1) * (.004 + .008 * A); my = -.003 * A; shake = .0008 * I
        if j.get("more_drift"): dz += .03; mx += (sx or 1) * .012
        k = min(2.0, max(1.0, j["duration"] / 2.5)); dz *= k; mx *= k            # a longer hold drifts proportionally more: the same slow move over 4 s reads as still
    if gains and depth and quality < .92: gains = "soft"          # layer edges only roughly follow the objects: smaller differential move
    g = _GAINS[gains] if (gains and depth) else [(1.0, 1.0)]
    if gains and not depth: mx *= 1.4; dz *= 1.0
    # keep the biggest relative layer displacement hideable by the inpainted margin (2% of the width)
    def rel(mxx, dzz):
        worst = 0.0
        for e in (0, 1):
            offs = [pg * mxx * (e - .5) for pg, _ in g]; fs = [1 + zg * dzz * e for _, zg in g]
            worst = max(worst, (max(offs) - min(offs)) + .5 * (max(fs) / min(fs) - 1))
        return worst
    if len(g) > 1:
        r = rel(mx, dz)
        if r > .022: mx *= .022 / r; dz *= .022 / r
    # common base zoom F0 so no layer ever shows an edge
    F0 = 1.04
    for pg, zg in g:
        for e in (0, 1):
            offx = abs(pg * mx * (e - .5)) + 1.6 * shake; offy = abs(pg * my * (e - .5)) + 1.6 * shake
            F0 = max(F0, 1.012 * (1 + 2 * max(offx, offy)) / (1 + zg * dz * e))
    cam = {"gains": g, "mx": mx, "my": my, "dz": dz, "F0": F0, "shake": shake}
    fo = _focus_points(j)
    if fo: cam = _apply_focus(j, cam, fo, a)
    if j["tparams"].get("join"):
        try: cam = _apply_join(j, cam)
        except Exception: cam.pop("join", None)               # a join that cannot be built leaves the shot's own camera
    return cam

# ---------------------------------------------------------------- joins (continuity): the camera's END state at the cut
def _ease_py(name, p):
    if name == "linear": return p
    if name == "in": return p * p
    if name == "out": return 1 - (1 - p) * (1 - p)
    return p * p * (3 - 2 * p)

def _env_py(P, w, side):
    """envelope 0..1: 'in' is 1 at the start of the shot and fades out over the first share w; 'out' is 1 at the end and rises over the last share w."""
    x = (w - P) / w if side == "in" else (P - (1 - w)) / w
    return max(0.0, min(1.0, x)) ** 2

def _join_point(j, name):
    """(x, y, w, h) in picture fractions of a named subject: 'main' = the group of the strongest 1-3 regions (so two people stay together), 'object' = the best region
    that is not a face; a list [x, y] is taken as is. Default: the middle."""
    if isinstance(name, (list, tuple)):
        p = _pt(name) or (.5, .5); return (p[0], p[1], .1, .1)
    try:
        from story_fast import focus
        pts = focus.find_focus(j["still"]).get("points") or []
    except Exception:
        pts = []
    if not pts: return (.5, .5, .1, .1)
    if name == "object":
        for p in pts:
            if p.get("kind") not in ("face",): return (p["x"], p["y"], p.get("w", .1), p.get("h", .1))
    grp = [p for p in pts[:3] if p["score"] >= .4 * pts[0]["score"]]
    x0 = min(p["x"] - p.get("w", .1) / 2 for p in grp); x1 = max(p["x"] + p.get("w", .1) / 2 for p in grp)
    y0 = min(p["y"] - p.get("h", .1) / 2 for p in grp); y1 = max(p["y"] + p.get("h", .1) / 2 for p in grp)
    return ((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)

def _canvas_pt(j, p):
    try:
        with Image.open(j["still"]) as im: pw, ph = im.size
    except Exception:
        return p
    W, H = j["size"]; s = max(W / pw, H / ph); w, h = pw * s, ph * s
    return (min(.98, max(.02, (p[0] * w - (w - W) / 2) / W)), min(.98, max(.02, (p[1] * h - (h - H) / 2) / H)))

def _keep_subjects(j, base, target, bound):
    """Blend the join state from the shot's own state `base` (f, bx, by) toward `target` only as far as every strong subject of the picture (with its own size)
    stays inside the window: no head or hand cut off by a join. Returns the state to use (the base itself when even the first step would cut something)."""
    try:
        from story_fast import focus
        pts = [p for p in (focus.find_focus(j["still"]).get("points") or [])[:3]]
        pts = [p for p in pts if p["score"] >= .3 * pts[0]["score"]] if pts else []
    except Exception:
        pts = []
    if not pts: return target
    boxes = []
    for p in pts:
        cx, cy = _canvas_pt(j, (p["x"], p["y"])); boxes.append((cx, cy, min(.17, p.get("w", .1) / 2 + .03), min(.17, p.get("h", .1) / 2 + .03)))
    def fits_one(b, f, bx, by):
        cx, cy, hx, hy = b; px = cx * f - (f - 1) / 2 - bx; py = cy * f - (f - 1) / 2 - by
        return not (px - hx < 0.0 or px + hx > 1.0 or py - hy < 0.0 or py + hy > 1.0)
    def fits(f, bx, by): return all(fits_one(b, f, bx, by) for b in boxes)
    fb, bxb, byb = base
    boxes = [b for b in boxes if fits_one(b, fb, bxb, byb)]               # a subject the shot's own camera already crops is not ours to protect
    for lam in (1.0, .85, .7, .55, .4, .25, .12):
        st = (fb + (target[0] - fb) * lam, bxb + (target[1] - bxb) * lam, byb + (target[2] - byb) * lam)
        if fits(*st): return st
    return base

def _apply_join(j, cam):
    """tparams['join'] = {'in': spec, 'out': spec, 'D': shot seconds, 'w': share, 'blur': {...}}. spec = {'pt': 'main'|'object'|[x,y], 'z': zoom, 'k': 0..1}
    (centre that subject at that zoom) or {'dx', 'dy', 'zb', 'k'} (travel sideways + zoom boost). Added to the shot's own camera as a smooth envelope that is 1 exactly
    at the cut (first / last frame), so the outgoing shot's end state and the incoming shot's start state are the pair the edit asks for, whatever the shot's own move is."""
    jn = j["tparams"]["join"]; g = cam["gains"]; sh = cam["shake"]; r = len(g) // 2; pg, zg = g[r]
    F0, dz, mx, my = cam["F0"], cam["dz"], cam["mx"], cam["my"]
    bx0, bx1, by0, by1 = cam.get("bx0", 0.0), cam.get("bx1", 0.0), cam.get("by0", 0.0), cam.get("by1", 0.0)
    ease = j["tparams"].get("ease") if j["tparams"].get("ease") in ("linear", "smooth", "in", "out") else "smooth"
    N = max(1, round(j["duration"] * j["fps"])); Dj = float(jn.get("D") or N / j["fps"]); Dj = max(0.2, min(Dj, N / j["fps"]))
    w = float(min(.6, max(.12, float(jn.get("w") or .4))))
    def base(e):
        return (F0 * (1 + zg * dz * e), pg * mx * (e - .5) + bx0 + (bx1 - bx0) * e, pg * my * (e - .5) + by0 + (by1 - by0) * e)
    bound = lambda f: max(0.0, (f - 1) / 2 * .97 - 1.6 * sh)
    dl = {}
    for side, e in (("in", 0), ("out", 1)):
        sp = jn.get(side)
        if not sp: dl[side] = (0.0, 0.0, 0.0); continue
        fb, bxb, byb = base(e); k = float(sp.get("k", 1.0))
        if "pt" in sp:
            px, py, pw, ph = _join_point(j, sp["pt"]); pt = _canvas_pt(j, (px, py))
            zt = fb + (max(float(sp.get("z", fb)), fb * 1.04) - fb) * k
            z, bxt, byt = zt, (pt[0] - .5) * zt, (pt[1] - .5) * zt
        else:
            z = fb * (1 + float(sp.get("zb", .15)) * k); bxt, byt = bxb + float(sp.get("dx", 0)) * k, byb + float(sp.get("dy", 0)) * k
        z, bxt, byt = _keep_subjects(j, (fb, bxb, byb), (z, bxt, byt), bound)
        # leave room for the layers' own differential move
        room = max(0.0, bound(z) - max(abs(pgx * mx * .5) for pgx, _ in g) * (1 if len(g) > 1 else 0) - .002)
        bxt = float(np.clip(bxt, -room, room)); byt = float(np.clip(byt, -room, room))
        dl[side] = (z - fb, bxt - bxb, byt - byb)
    def valid(lam):
        for P in np.linspace(0, 1, 41):
            E = _ease_py(ease, P); ei, eo = _env_py(P, w, "in"), _env_py(P, w, "out")
            for pgk, zgk in g:
                f = F0 * (1 + zgk * dz * E) + lam * (dl["in"][0] * ei + dl["out"][0] * eo)
                ox = pgk * mx * (E - .5) + bx0 + (bx1 - bx0) * E + lam * (dl["in"][1] * ei + dl["out"][1] * eo)
                oy = pgk * my * (E - .5) + by0 + (by1 - by0) * E + lam * (dl["in"][2] * ei + dl["out"][2] * eo)
                if max(abs(ox), abs(oy)) > bound(f) + 1e-6: return False
        return True
    lam = next((l for l in (1.0, .85, .7, .55, .4, .25) if valid(l)), 0.0)
    if lam <= 0.0: raise ValueError("join does not fit the picture")
    for s_ in dl: dl[s_] = tuple(v * lam for v in dl[s_])
    bl = jn.get("blur") or {}
    cam = dict(cam); cam["join"] = {"in": dl["in"] if jn.get("in") else None, "out": dl["out"] if jn.get("out") else None, "D": Dj, "w": w,
                                    "blur_in": bool(bl.get("in_") and jn.get("in")), "blur_out": bool(bl.get("out") and jn.get("out")), "N_cut": int(round(Dj * j["fps"]))}
    if "bx0" not in cam: cam.update(bx0=0.0, bx1=0.0, by0=0.0, by1=0.0)
    return cam

# ---------------------------------------------------------------- focus-aware camera
def _pt(v):
    try:
        if isinstance(v, dict): x, y = v["x"], v["y"]
        else: x, y = v[0], v[1]
        return (float(min(1, max(0, x))), float(min(1, max(0, y))))
    except Exception:
        return None

def _focus_points(j: dict):
    """(from, to) in canvas fractions (0..1 of the cover-fitted frame) or None when the job has no focus."""
    tp = j["tparams"]; B = _pt(tp.get("focus")) if tp.get("focus") is not None else None
    if B is None: return None
    A = _pt(tp.get("focus_from")) if tp.get("focus_from") is not None else None
    try:
        with Image.open(j["still"]) as im: pw, ph = im.size
    except Exception:
        pw = ph = None
    W, H = j["size"]
    def cv(p):
        if p is None: return None
        if not pw: return p
        s = max(W / pw, H / ph); w, h = pw * s, ph * s
        return (min(.98, max(.02, (p[0] * w - (w - W) / 2) / W)), min(.98, max(.02, (p[1] * h - (h - H) / 2) / H)))
    return {"A": cv(A), "B": cv(B)}

def _apply_focus(j, cam, fo, amount):
    tr = j["treatment"]; A, B = fo["A"], fo["B"]
    g = cam["gains"]; layered = len(g) > 1; sh = cam["shake"]
    nd = lambda p, k: k / max(.08, .5 - max(abs(p[0] - .5), abs(p[1] - .5)))     # zoom that puts p within the central part of the frame
    cap = 1.35 + 1.0 * float(amount)
    bound = lambda f: max(0.0, (f - 1) / 2 * .97 - 1.6 * sh)
    shift = lambda p, f, f_lim: (float(np.clip((p[0] - .5) * f, -bound(f_lim), bound(f_lim))), float(np.clip((p[1] - .5) * f, -bound(f_lim), bound(f_lim))))
    F0, dz, mx, my = cam["F0"], cam["dz"], cam["mx"], cam["my"]
    out = dict(cam)
    if not layered:
        f0, f1 = F0, F0 * (1 + dz)
        if tr in ("push_in", "dolly_through", "handheld", "hold_alive"):
            c = {"push_in": cap, "dolly_through": cap, "handheld": min(cap, 1.3), "hold_alive": min(cap, 1.15)}[tr]
            f1 = max(f1, min(c, nd(B, .42 if tr in ("push_in", "dolly_through") else .35))); f0 = min(f0, f1) if f0 > f1 else f0
            S = A or (.5, .5)
        elif tr == "pull_out":
            f0 = max(f0, min(cap, nd(B, .42))); f1 = min(f1, f0); S = B; B = A or (.5, .5)
        elif tr == "reveal_up":
            S = A or (B[0], min(.92, B[1] + .22))
            f0 = max(f0, min(cap, nd(S, .3))); f1 = max(1.12, min(f1, f0), min(1.45, nd(B, .3))); f0 = max(f0, f1)
        else:                                     # pans, tilts, tracks, parallax, arc: window travels A -> B
            if A is None:
                A = (B[0] - (.18 if mx > 0 else -.18 if mx < 0 else 0), B[1] - (.18 if my > 0 else -.18 if my < 0 else 0))
                A = (min(.94, max(.06, A[0])), min(.94, max(.06, A[1])))
            f = min(min(1.7, cap), max(F0, nd(A, .36), nd(B, .42))); f0, f1 = f, f * 1.02; S = A
        b0 = shift(S, f0, f0); b1 = shift(B, f1, f1)
        out.update(F0=f0, dz=f1 / f0 - 1, mx=0.0, my=0.0, bx0=b0[0], by0=b0[1], bx1=b1[0], by1=b1[1])
        return out
    # layered (depth) treatments: layers keep their own differential move, the rigid camera centre travels A -> B
    if A is None and tr not in ("dolly_through",):
        A = (min(.94, max(.06, B[0] - (.15 if mx > 0 else -.15 if mx < 0 else 0))), min(.94, max(.06, B[1] - (.15 if my > 0 else -.15 if my < 0 else 0))))
    S = A or (.5, .5)
    if abs(B[0] - S[0]) > .04 and mx: mx = math.copysign(abs(mx), B[0] - S[0])
    if abs(B[1] - S[1]) > .04 and my: my = math.copysign(abs(my), B[1] - S[1])
    F0 = max(F0, min(min(1.5, cap), max(nd(S, .3), nd(B, .3))))
    allowed = []
    for e in (0, 1):
        al = min(bound(F0 * (1 + zg * dz * e) / 1.012 * 1.0) - abs(pg * mx * (e - .5)) * 1.0 for pg, zg in g)
        allowed.append(max(0.0, al))
    fs, fe = F0, F0 * (1 + dz)
    def pick(p, f, mxx, e, al):
        return (float(np.clip((p[0] - .5) * f - (mxx * (e - .5)), -al, al)), float(np.clip((p[1] - .5) * f, -al, al)))
    b0 = pick(S, fs, mx, 0, allowed[0]); b1 = pick(B, fe, mx, 1, allowed[1])
    # y: the layers' own y move
    b0 = (b0[0], float(np.clip((S[1] - .5) * fs - my * -.5, -allowed[0], allowed[0]))); b1 = (b1[0], float(np.clip((B[1] - .5) * fe - my * .5, -allowed[1], allowed[1])))
    out.update(F0=F0, mx=mx, my=my, bx0=b0[0], by0=b0[1], bx1=b1[0], by1=b1[1])
    return out

# ---------------------------------------------------------------- environments
def _tile(w, h): return f"scale={w}:{h}:flags=bilinear"

def _env_chain(name, k, W, H, fps, D, seed, I, label_out):
    """Returns (filter string, final label). Each env is a periodic grey mask (2x2 tiled), cropped by a moving window, alpha-merged onto a tint."""
    rnd = np.random.default_rng(seed * 131 + k * 17 + 5)
    sd = int(rnd.integers(1, 2 ** 30))
    px = lambda a, b: float(rnd.uniform(a, b))
    vx, vy = 0.0, 0.0; tint = "0xFFFFFF"; op = .5; gen = None; thr = .02; mode = "specks"; blur = 0.0; gw, gh = W // 3, H // 3
    if name == "dust":
        gw, gh, thr, op, vx, vy, tint, blur = W // 3, H // 3, .018, .75 * I, px(10, 22) * W / 1920, -px(6, 14) * W / 1920, "0xFFF4E0", .6
    elif name == "embers":
        gw, gh, thr, op, vx, vy, tint, blur = W // 3, H // 3, .016, 2.2 * min(I, 1.3), px(-14, 14) * W / 1920, px(55, 90) * H / 1080, "0xFF8A2A", .9
    elif name == "snow":
        gw, gh, thr, op, vx, vy, tint, blur = W // 5, H // 5, .022, .9 * I, px(-18, 18) * W / 1920, -px(70, 110) * H / 1080, "0xFFFFFF", .7
    elif name == "rain":
        gw, gh, thr, op, vx, vy, tint, blur = W // 2, max(8, H // 24), .03, .5 * min(I, 1.3), -px(20, 40) * W / 1920, -px(1100, 1500) * H / 1080, "0xD8E4F0", 0.0
    elif name == "fog":
        mode = "fog"; gw, gh = 10, 6; op = .13 * I; vx = px(14, 26) * W / 1920; vy = px(-4, 4); tint = "0xE6E8EC"
    elif name == "light_sweep":
        mode = "sweep"; op = .26 * I; tint = "0xFFF1D6"
    elif name == "shimmer":
        mode = "shimmer"; op = .8 * I
    f = []
    L = lambda s: f"[{label_out}_{s}]"
    if mode == "specks":
        f.append(f"color=c=gray:s={gw}x{gh}:r={fps}:d={1/fps:.5f},format=gray,noise=alls=100:allf=u:all_seed={sd},"
                 f"format=gray,lut=c0='if(gt(val,{178-100*thr:.1f}),min(255,(val-{178-100*thr:.1f})*{255/(100*thr)*op:.3f}),0)',{_tile(W, H)}"
                 + (f",gblur=sigma={blur}" if blur > 0 else "") + f",format=gray,split[t1][t2];[t1][t2]hstack,split[h1][h2];[h1][h2]vstack,loop=loop={int(D*fps)+2}:size=1,fps={fps}")
        crop = f"crop={W}:{H}:x='mod({vx:.3f}*t+{px(0,W):.0f},{W})':y='mod({vy:.3f}*t+{px(0,H):.0f}+{H},{H})'"
    elif mode == "fog":
        f.append(f"color=c=gray:s={gw}x{gh}:r={fps}:d={1/fps:.5f},format=gray,noise=alls=100:allf=u:all_seed={sd},"
                 f"format=gray,lut=c0='clip((val-78)*{2.6*op:.3f},0,255)',scale={W//2}:{H//2}:flags=bicubic,gblur=sigma={W/60:.1f},scale={W}:{H}:flags=bilinear,format=gray,split[t1][t2];[t1][t2]hstack,split[h1][h2];[h1][h2]vstack,"
                 f"loop=loop={int(D*fps)+2}:size=1,fps={fps}")
        crop = f"crop={W}:{H}:x='mod({vx:.3f}*t+{px(0,W):.0f},{W})':y='mod({vy:.3f}*t+{px(0,H):.0f}+{H},{H})'"
    elif mode == "sweep":
        f.append(f"color=c=gray:s=288x27:r={fps}:d={1/fps:.5f},format=yuv420p,geq=lum='255*exp(-pow(((X/W-0.5)*22+(Y/H-0.5)*0.9),2))*{op:.3f}':cb=128:cr=128,"
                 f"scale={3*W}:{H}:flags=bicubic,format=gray,loop=loop={int(D*fps)+2}:size=1,fps={fps}")
        crop = f"crop={W}:{H}:x='{2*W}*(0.1+0.8*min(t/{D:.4f},1))':y=0"
        sx0 = rnd.uniform(0, 1)
        if sx0 > .5: crop = f"crop={W}:{H}:x='{2*W}*(0.9-0.8*min(t/{D:.4f},1))':y=0"
    else:   # shimmer: per-frame flickering sparse sparkles
        f.append(f"color=c=gray:s={W//4}x{H//4}:r={fps}:d={D+1/fps:.4f},format=gray,noise=alls=100:allf=u:all_seed={sd},"
                 f"format=gray,lut=c0='if(gt(val,175),min(255,(val-174)*{60*op:.3f}),0)',scale={W}:{H}:flags=bilinear,gblur=sigma=0.8,format=gray")
        crop = ""
    chain = f[0] + ("," + crop if crop else "") + "[m]"
    # tint stream + alpha merge
    chain += f";color=c={tint}:s={W}x{H}:r={fps},format=yuva420p[c];[c][m]alphamerge[{label_out}]"
    return chain.replace("[m]", f"[m{k}]").replace("[c]", f"[c{k}]").replace("[c];", f"[c{k}];").replace("[c][m", f"[c{k}][m").replace("[m]", f"[m{k}]"), label_out

# ---------------------------------------------------------------- render
DEFAULT_FINISH = "vignette=PI/5:eval=init,noise=alls=3:allf=t"

def _build_graph(j: dict, cam: dict, nl: int, N: int):
    W, H = j["size"]; fps = j["fps"]; D = N / fps
    jn = cam.get("join")
    if jn: D = jn["D"]                              # the move completes exactly at the cut; the 0.3 s of margin after it holds the end state
    P = f"min(t/{D:.5f},1)"; E = _ease(j["tparams"].get("ease") if j["tparams"].get("ease") in ("linear", "smooth", "in", "out") else "smooth", P)
    rnd = np.random.default_rng(j["seed"] * 7919 + 31)
    sh = cam["shake"]; shx = shy = "0"
    if sh > 0:
        ph = rnd.uniform(0, 2 * math.pi, 4); fr = rnd.uniform(.35, .7), rnd.uniform(1.1, 1.9), rnd.uniform(.4, .8), rnd.uniform(1.0, 1.7)
        shx = f"{sh:.5f}*(sin(2*PI*{fr[0]:.3f}*t+{ph[0]:.3f})+0.6*sin(2*PI*{fr[1]:.3f}*t+{ph[1]:.3f}))"
        shy = f"{sh:.5f}*(sin(2*PI*{fr[2]:.3f}*t+{ph[2]:.3f})+0.6*sin(2*PI*{fr[3]:.3f}*t+{ph[3]:.3f}))"
    parts = []
    g = cam["gains"]
    for k in range(nl):
        pg, zg = g[k]
        f = f"({cam['F0']:.5f}*(1+{zg*cam['dz']:.5f}*{E}))"
        jx = jy = ""
        if jn:
            ein = f"pow(clip(({jn['w']:.4f}-{P})/{jn['w']:.4f},0,1),2)"; eout = f"pow(clip(({P}-{1-jn['w']:.4f})/{jn['w']:.4f},0,1),2)"
            def jterm(i_):
                t = []
                if jn["in"] and abs(jn["in"][i_]) > 1e-7: t.append(f"{jn['in'][i_]:.5f}*{ein}")
                if jn["out"] and abs(jn["out"][i_]) > 1e-7: t.append(f"{jn['out'][i_]:.5f}*{eout}")
                return "+".join(t)
            zt = jterm(0)
            if zt: f = f"({f}+{zt})"
            jx = jterm(1); jy = jterm(2)
            jx = f"+({jx})" if jx else ""; jy = f"+({jy})" if jy else ""
        fmt = "yuv420p" if k == 0 else "yuva420p"
        fx = fy = ""; cxs, cys = f"(iw-{W})/2", f"(ih-{H})/2"
        if "bx0" in cam:
            # crop keeps the input size it was configured with, so with a changing zoom iw/ih are stale: spell the size out
            cxs, cys = f"(trunc({W}*{f}/2)*2-{W})/2", f"(trunc({H}*{f}/2)*2-{H})/2"
            fx = f"+{cam['bx0']:.5f}+({cam['bx1']-cam['bx0']:.5f})*{E}"; fy = f"+{cam['by0']:.5f}+({cam['by1']-cam['by0']:.5f})*{E}"
        parts.append(f"[{k}:v]{'scale=in_range=full:out_range=limited,' if k == 0 else ''}format={fmt},loop=loop={N+1}:size=1:start=0,fps={fps},"
                     f"scale=w='trunc({W}*{f}/2)*2':h='trunc({H}*{f}/2)*2':eval=frame:flags=bilinear,"
                     f"crop={W}:{H}:x='{cxs}+{W}*({pg*cam['mx']:.5f}*({E}-0.5)+{shx}{fx}{jx})':y='{cys}+{H}*({pg*cam['my']:.5f}*({E}-0.5)+{shy}{fy}{jy})'[L{k}]")
    cur = "[L0]"
    for k in range(1, nl):
        parts.append(f"{cur}[L{k}]overlay=format=yuv420:eof_action=repeat[o{k}]"); cur = f"[o{k}]"
    for i, e in enumerate(j["env"]):
        if e == "shimmer":
            parts.append(f"{cur}eq=brightness='0.014*sin(2*PI*0.6*t)':eval=frame[e{i}b]"); cur = f"[e{i}b]"
        chain, lab = _env_chain(e, i, W, H, fps, D, j["seed"], _INT[j["intensity"]], f"E{i}")
        parts.append(chain)
        parts.append(f"{cur}[{lab}]overlay=format=yuv420:eof_action=repeat[x{i}]"); cur = f"[x{i}]"
    if jn and (jn["blur_in"] or jn["blur_out"]):                 # whip: a directional blur on the frames either side of the cut
        nc = jn["N_cut"]; bl = []
        if jn["blur_out"]: bl += [(8, f"between(n,{nc-6},{nc-4})"), (22, f"gte(n,{nc-3})")]
        if jn["blur_in"]: bl += [(22, "lt(n,3)"), (8, "between(n,3,5)")]
        for bi, (rad, en) in enumerate(bl):
            parts.append(f"{cur}dblur=angle=0:radius={rad}:enable='{en}'[bl{bi}]"); cur = f"[bl{bi}]"
    finish = j.get("grade_vf") or DEFAULT_FINISH                 # project grade (colour match + one vignette + grain) from story_fast/grade.py, else the fixed look
    parts.append(f"{cur}{finish},setsar=1,format=yuv420p[v]")
    return ";".join(parts)

def _run(cmd, N, cancel, progress, tmp_err):
    with open(tmp_err, "wb") as ef:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=ef, text=True, bufsize=1)
        try:
            for line in p.stdout:
                if cancel and cancel():
                    p.kill(); p.wait(timeout=30); raise Cancelled("cancelled")
                if line.startswith("frame=") and progress:
                    try: progress(min(1.0, int(line.split("=")[1]) / max(1, N)))
                    except Exception: pass
            rc = p.wait(timeout=300)      # its output has ended: ffmpeg is only finishing the file
        except BaseException:
            if p.poll() is None: p.kill(); p.wait(timeout=30)
            raise
    if cancel and cancel(): raise Cancelled("cancelled")
    return rc

def _with_auto_focus(job: dict) -> dict:
    tp = job.get("tparams") or {}
    if "focus" in tp or tp.get("auto_focus") is False: return job
    try:
        from . import focus as _F
        t2 = _F.auto_focus(job)
    except Exception:
        return job
    if t2 == tp: return job
    j2 = dict(job); j2["tparams"] = t2
    return j2

def render_shot(job: dict, out_path: str, cancel=None, progress=None) -> str:
    if os.path.isfile(str(job.get("still"))): job = _with_auto_focus(job)
    j = _norm(job)
    if not os.path.isfile(j["still"]): raise ComposeError(f"picture not found: {j['still']}")
    key = job_key(job); shots = CACHE / "shots"; shots.mkdir(parents=True, exist_ok=True); cached = shots / f"{key}.mp4"
    out = Path(out_path); out.parent.mkdir(parents=True, exist_ok=True)
    def deliver():
        tmp = out.with_name(out.name + f".{os.getpid()}.{threading.get_ident()}.tmp.mp4")
        try:
            try: os.link(cached, tmp)
            except OSError: shutil.copyfile(cached, tmp)
            os.replace(tmp, out)
        finally:
            if tmp.exists():
                try: tmp.unlink()
                except OSError: pass
        return str(out)
    if cached.is_file() and cached.stat().st_size > 1000:
        if progress: progress(1.0)
        return deliver()
    if cancel and cancel(): raise Cancelled("cancelled")
    N = max(1, round(j["duration"] * j["fps"]))
    W, H = j["size"]
    if j["treatment"] == "hold_alive" and not j["env"]: j["env"] = ["dust"]
    had = list(j["env"]); j["env"] = _env_for_background(j["env"], j["still"])
    if j["treatment"] == "hold_alive" and had and not j["env"]: j["more_drift"] = True      # the dust that made this hold alive is gone (white paper): the camera drifts a little more instead
    want_depth = needs_depth(j["treatment"], j["still"])
    try: prep = prepare(j["still"], (W, H), None, need_depth=want_depth)
    except Exception as e: raise ComposeError(f"could not prepare the picture: {e}") from e
    if cancel and cancel(): raise Cancelled("cancelled")
    layers = prep["layers"] if (want_depth and prep["depth"]) else [prep["layers"][0] if not prep["depth"] else prep["fit"]]
    cam = _camera(j, len(layers) > 1, prep.get("quality", 1.0) if len(layers) > 1 else 1.0)
    graph = _build_graph(j, cam, len(layers), N)
    enc = available_encoder()
    _sweep_parts(shots)
    part = shots / f"{key}.{os.getpid()}.{threading.get_ident()}.part.mp4"; errf = str(part) + ".log"
    def cmd_for(e):
        c = [_ffmpeg(), "-v", "error", "-y", "-nostats", "-progress", "pipe:1", "-stats_period", "0.15"]
        for p in layers: c += ["-framerate", str(j["fps"]), "-i", p]
        c += ["-filter_complex", graph, "-map", "[v]", "-frames:v", str(N), "-r", str(j["fps"]), "-an", "-pix_fmt", "yuv420p"]
        c += ["-c:v", e] + (["-b:v", "16M"] if e == "h264_videotoolbox" else ["-preset", "veryfast", "-crf", "18"])
        c += ["-movflags", "+faststart", str(part)]
        return c
    try:
        rc = _run(cmd_for(enc), N, cancel, progress, errf)
        if rc != 0 and enc != "libx264":
            rc = _run(cmd_for("libx264"), N, cancel, progress, errf)
        if rc != 0 or not part.is_file() or part.stat().st_size < 1000:
            msg = ""
            try: msg = Path(errf).read_text(errors="replace")[-600:]
            except Exception: pass
            raise ComposeError(f"ffmpeg failed ({j['treatment']}): {msg}")
        os.replace(part, cached)
    finally:
        for p in (part, Path(errf)):
            try:
                if p.exists(): p.unlink()
            except OSError: pass
    if progress: progress(1.0)
    return deliver()
