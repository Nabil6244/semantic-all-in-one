"""Where is the picture's subject?  Fast saliency (numpy + PIL only) so the camera can go where the picture is about.

    find_focus(still, cache_dir=None) -> {"points": [{x, y, w, h, score, kind}], "main": {x, y}, "bg": "light"|"dark"|"busy"}
    auto_focus(job) -> tparams copy with "focus" / "focus_from" ([x, y] in 0..1 of the picture) filled for the job's treatment

Plain-background pictures (cartoon host beside a chart / object / second person) give the host's head and the object as separate points;
busy cinematic pictures give their strongest 1-3 regions (centre-surround contrast + edges). Results are cached by file hash."""
from __future__ import annotations
import hashlib, io, json, os
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VERSION = "focus-2"
CACHE = ROOT / "out" / "story_fast_cache" / "focus"
CELL = 4
WIDTH = 320
MIN_SCORE = 0.05

def _empty(bg="light"):
    return {"points": [], "main": {"x": 0.5, "y": 0.5}, "bg": bg}

# ---------------------------------------------------------------- analysis
def _blur_box(a: np.ndarray, r: int) -> np.ndarray:
    """Box blur with an integral image (a: H x W x C or H x W)."""
    p = np.pad(a, [(r + 1, r), (r + 1, r)] + [(0, 0)] * (a.ndim - 2), mode="edge")
    c = p.cumsum(0).cumsum(1)
    H, W = a.shape[:2]; k = 2 * r + 1
    s = c[k:k + H, k:k + W] - c[0:H, k:k + W] - c[k:k + H, 0:W] + c[0:H, 0:W]
    return s / float(k * k)

def _dilate(m: np.ndarray) -> np.ndarray:
    p = np.pad(m, 1); out = np.zeros_like(m)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out |= p[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    return out

def _label(mask: np.ndarray):
    """8-connected labels of a small boolean grid. Returns (labels int32, count)."""
    gh, gw = mask.shape; lab = np.zeros((gh, gw), np.int32); n = 0
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if lab[y0, x0]: continue
        n += 1; lab[y0, x0] = n; st = [(y0, x0)]
        while st:
            y, x = st.pop()
            for yy in (y - 1, y, y + 1):
                if yy < 0 or yy >= gh: continue
                for xx in (x - 1, x, x + 1):
                    if 0 <= xx < gw and mask[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n; st.append((yy, xx))
    return lab, n

def _split(ys, xs, depth=0):
    """Two figures that touch make one blob: cut it at a deep valley of its column profile."""
    x0 = int(xs.min()); wdt = int(xs.max()) - x0 + 1
    if depth >= 2 or wdt < 14: return [(ys, xs)]
    cnt = np.bincount(xs - x0, minlength=wdt).astype(np.float32)
    sm = np.convolve(cnt, [1, 2, 1], "same") / 4
    lo, hi = int(wdt * .22), int(wdt * .78)
    if hi <= lo: return [(ys, xs)]
    k = lo + int(np.argmin(sm[lo:hi + 1]))
    pl, pr = float(sm[:k].max()), float(sm[k + 1:].max())
    if min(pl, pr) >= 4 and sm[k] <= .22 * min(pl, pr):
        left = xs - x0 < k; right = xs - x0 > k
        return _split(ys[left], xs[left], depth + 1) + _split(ys[right], xs[right], depth + 1)
    return [(ys, xs)]

def _analyse(im: Image.Image) -> dict:
    w0, h0 = im.size
    r = max(1, int(w0 // (WIDTH * 1.5)))
    if r > 1: im = im.reduce(r)
    nh = max(CELL * 4, int(round(h0 * WIDTH / max(1, w0))) // CELL * CELL)
    im = im.resize((WIDTH, nh), Image.BILINEAR)
    a = np.asarray(im, np.float32); H, W = a.shape[:2]; gh, gw = H // CELL, W // CELL
    lum = a @ np.array([.299, .587, .114], np.float32)
    grad = np.zeros((H, W), np.float32)
    grad[:, 1:] = np.abs(lum[:, 1:] - lum[:, :-1]); grad[1:, :] = np.maximum(grad[1:, :], np.abs(lum[1:, :] - lum[:-1, :]))
    b = 3
    ring = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    bg = np.median(ring, axis=0); bdev = float(np.linalg.norm(ring - bg, axis=1).mean())
    dist = np.linalg.norm(a - bg, axis=2)
    busy = bdev >= 22
    fg = None
    if not busy:
        fg = (dist > max(40.0, 2.2 * bdev + 14)) | ((grad > 30) & (dist > 14))
        if fg.mean() > .6: busy = True
    if busy:
        loc = np.linalg.norm(a - _blur_box(a, max(8, W // 6)), axis=2)
        sal = loc + .8 * _blur_box(grad, 1)
        th = max(18.0, float(np.percentile(sal, 82)))
        fg = sal > th; dist = sal
        if float(sal.std()) < 3: fg = np.zeros_like(fg)
    cr = a[..., 0] - lum
    ycb = np.stack([-.1687 * a[..., 0] - .3313 * a[..., 1] + .5 * a[..., 2] + 128, .5 * a[..., 0] - .4187 * a[..., 1] - .0813 * a[..., 2] + 128])
    skin = (ycb[0] > 77) & (ycb[0] < 127) & (ycb[1] > 135) & (ycb[1] < 162) & (lum > 60)
    cells = lambda m: m[:gh * CELL, :gw * CELL].reshape(gh, CELL, gw, CELL).mean((1, 3))
    active = cells(fg.astype(np.float32)) > .3
    cd = cells(dist); skc = cells(skin.astype(np.float32)) > .4
    minc = max(3, .004 * gh * gw)
    def pieces_of(act, region=None, grow=1):
        dm = act | False
        for _ in range(grow): dm = _dilate(dm)
        lab, n = _label(dm); out = []
        for i in range(1, n + 1):
            m = (lab == i) & act
            ys, xs = np.nonzero(m)
            if len(ys) >= minc: out += _split(ys, xs)
        return out
    pieces = []
    for ys, xs in pieces_of(active):
        bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
        if (not busy) and bw * bh > .45 * gh * gw and len(ys) > .12 * gh * gw:
            # one blob swallowed a whole room / street: look only at the dark, saturated things in it (people, shelves, signs)
            m = np.zeros((gh, gw), bool); m[ys, xs] = True
            sub = []
            for th in (105, 135, 165, 195):               # tighten until the blob falls apart into separate things
                strict = m & (cells((dist > th).astype(np.float32)) > .3)
                if strict.sum() < minc: break
                cand = pieces_of(strict, grow=1)
                if cand and all((int(x.max() - x.min() + 1) * int(y.max() - y.min() + 1)) <= .45 * gh * gw for y, x in cand):
                    sub = cand; break
            if sub: pieces += sub; continue
        pieces.append((ys, xs))
    pts = []
    for ys, xs in pieces:
        if len(ys) < max(3, .004 * gh * gw): continue
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        wc, hc = x1 - x0 + 1, y1 - y0 + 1; area = len(ys)
        contrast = float(cd[ys, xs].mean())
        touch_bottom = y1 >= gh - 2
        figure = (not busy) and hc >= .38 * gh and (hc / wc >= 1.45 or (touch_bottom and area > .06 * gh * gw and hc / wc >= 1.0))
        kind = "region" if busy else "object"
        if figure:
            kind = "face"; closeup = hc / wc < 1.45
            top = ys <= y0 + max(2, int(.22 * hc))
            cx = float(xs[top].mean()) + .5
            hs = (.30 if closeup else .17) * hc
            cy = y0 + (.20 if closeup else .11) * hc
            px, py, pw, ph = cx / gw, cy / gh, hs / gw, hs / gh
        else:
            sk = skc[ys, xs]
            if (not busy) and sk.sum() > .35 * area and area < .25 * gh * gw:
                kind = "face"; px, py = (float(xs[sk].mean()) + .5) / gw, (float(ys[sk].mean()) + .5) / gh
            elif busy:
                px, py = (float(xs.mean()) + .5) / gw, (float(ys.mean()) + .5) / gh
            else:
                px, py = (x0 + wc / 2) / gw, (y0 + hc / 2) / gh
            pw, ph = wc / gw, hc / gh
            if kind != "face" and wc / hc > 3 and hc < .12 * gh: kind = "text"
        dc = float(np.hypot(px - .5, py - .5))
        score = (area / float(gh * gw)) ** .55 * (.3 + contrast / 120.0) * (1 - .3 * min(1.0, dc * 2))
        pts.append({"x": float(np.clip(px, 0, 1)), "y": float(np.clip(py, 0, 1)), "w": float(min(1, pw)), "h": float(min(1, ph)), "score": float(score), "kind": kind})
    pts.sort(key=lambda p: -p["score"])
    if pts: pts = [p for p in pts if p["score"] >= .18 * pts[0]["score"]][:4]
    pts = [p for p in pts if p["score"] >= MIN_SCORE]
    for p in pts:
        for k in ("x", "y", "w", "h"): p[k] = round(p[k], 3)
        p["score"] = round(p["score"], 4)
    bgk = "busy" if busy else ("light" if float(bg @ np.array([.299, .587, .114])) >= 128 else "dark")
    if not pts: return _empty(bgk)
    return {"points": pts, "main": {"x": pts[0]["x"], "y": pts[0]["y"]}, "bg": bgk}

def find_focus(still: str, cache_dir: str | None = None) -> dict:
    """Subject regions of the picture (up to 4, best first). Never raises for an unreadable picture: returns no points."""
    try:
        raw = Path(still).read_bytes()
    except OSError:
        return _empty()
    key = hashlib.sha1(raw).hexdigest()[:24] + f"_{len(raw)}_{VERSION}"
    base = Path(cache_dir) if cache_dir else CACHE
    cp = base / f"{key}.json"
    try:
        if cp.is_file(): return json.loads(cp.read_text())
    except Exception:
        pass
    try:
        im = Image.open(io.BytesIO(raw)); im.draft("RGB", (WIDTH * 2, WIDTH * 2)); im = im.convert("RGB")
        res = _analyse(im)
    except Exception:
        return _empty()
    try:
        base.mkdir(parents=True, exist_ok=True)
        tmp = cp.with_name(cp.name + f".{os.getpid()}.tmp"); tmp.write_text(json.dumps(res)); os.replace(tmp, cp)
    except OSError:
        pass
    return res

# ---------------------------------------------------------------- choosing the ends of a move
_PAN_LIKE = {"pan_left", "pan_right", "parallax_left", "parallax_right", "track_lateral", "arc"}
_TILT_LIKE = {"tilt_up", "tilt_down"}
_ZOOM_LIKE = {"push_in", "pull_out", "dolly_through", "handheld", "hold_alive"}

def _c(v, lo=.06, hi=.94): return round(float(min(hi, max(lo, v))), 3)

def auto_focus(job: dict) -> dict:
    """tparams copy with focus / focus_from filled from find_focus; unchanged when the picture shows nothing confident."""
    tp = dict(job.get("tparams") or {})
    if "focus" in tp or tp.get("auto_focus") is False: return tp
    try:
        f = find_focus(job["still"])
    except Exception:
        return tp
    pts = f.get("points") or []
    if not pts or pts[0]["score"] < MIN_SCORE: return tp
    tr = job.get("treatment") or "push_in"; seed = int(job.get("seed") or 0); d = tp.get("dir")
    rk = tp.get("focus_rank")
    try: rk = None if rk is None else max(0, int(rk))
    except (TypeError, ValueError): rk = None
    P = [(p["x"], p["y"]) for p in pts[:(4 if rk is not None else 3)]]
    m = P[0]
    if rk is not None:
        m = P[rk % len(P)]
        if tr in (_PAN_LIKE | _TILT_LIKE) and len(P) > 1:
            A, B = P[rk % len(P)], P[(rk + 1) % len(P)]
            tp["focus_from"] = [_c(A[0]), _c(A[1])]; tp["focus"] = [_c(B[0]), _c(B[1])]
            return tp
    def pair():
        """(A, B) = two different subject points, the main one preferred; A != B by at least .12 in x or y."""
        for q in P[1:]:
            if abs(q[0] - m[0]) >= .12 or abs(q[1] - m[1]) >= .12: return m, q
        return m, None
    if tr in _ZOOM_LIKE:
        idx = (rk % len(P)) if rk is not None else (seed % min(2, len(P)) if len(P) > 1 else 0)
        tp["focus"] = [_c(P[idx][0]), _c(P[idx][1])]
    elif tr in _PAN_LIKE:
        sgn = {"l": -1, "r": 1}.get(d)
        if sgn is None:
            sgn = -1 if tr == "pan_left" or tr == "parallax_left" else (1 if tr in ("pan_right", "parallax_right") else (1 if seed % 2 == 0 else -1))
        a, b = pair()
        if b is not None:
            lo, hi = (a, b) if a[0] <= b[0] else (b, a)
            if abs(a[0] - b[0]) < .12:       # stacked, not side by side: travel along y instead
                A, B = (a, b) if a[1] >= b[1] else (b, a)
            else:
                A, B = (lo, hi) if sgn > 0 else (hi, lo)
        else:
            x, y = m
            if sgn > 0: A, B = ((x - .2, y), (x, y)) if x - .2 >= .1 else ((x, y), (x + .2, y))
            else: A, B = ((x + .2, y), (x, y)) if x + .2 <= .9 else ((x, y), (x - .2, y))
        tp["focus_from"] = [_c(A[0]), _c(A[1])]; tp["focus"] = [_c(B[0]), _c(B[1])]
    elif tr in _TILT_LIKE:
        up = tr == "tilt_up"
        a, b = pair()
        if b is not None and abs(a[1] - b[1]) >= .12:
            hi, lo = (a, b) if a[1] <= b[1] else (b, a)      # hi = smaller y = higher on screen
            A, B = (lo, hi) if up else (hi, lo)
        else:
            x, y = m
            A, B = ((x, y + .2), (x, y)) if up else ((x, y - .2), (x, y))
            if (up and y + .2 > .94) or ((not up) and y - .2 < .06): A, B = (x, y), ((x, y - .2) if up else (x, y + .2))
        tp["focus_from"] = [_c(A[0]), _c(A[1])]; tp["focus"] = [_c(B[0]), _c(B[1])]
    elif tr == "reveal_up":
        top = m if rk is not None else min(P, key=lambda q: q[1]) if len(P) > 1 and min(P, key=lambda q: q[1])[1] < m[1] - .08 else m
        low = max(P, key=lambda q: q[1])
        A = low if low[1] > top[1] + .1 else (top[0], top[1] + .22)
        tp["focus_from"] = [_c(A[0]), _c(A[1])]; tp["focus"] = [_c(top[0]), _c(top[1])]
    else:
        tp["focus"] = [_c(m[0]), _c(m[1])]
    return tp
