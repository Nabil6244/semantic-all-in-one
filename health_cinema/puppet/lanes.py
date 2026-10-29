"""Per-picture WALKING LANE for the puppet layer: where a character may stand/walk on a still, and where it must stay clear.

    lane_for(still_path, scene_no=None, overrides=None, project_dir=None) -> dict | None

The dict (all values are fractions of frame width / height):
    x0, x1   walkable span left..right
    y        feet row (a walker's feet stay on this row)
    h_hint   suggested character height at that row (fraction of frame height)
    avoid    [[a, b], ...] x spans the walker must not overlap (people / objects drawn in the picture)
    conf     0..1 how sure we are
    source   "override" | "sidecar" | "auto"
None means "no usable lane: do not place a character on this picture". A missing lane is always preferred to a wrong one.

Precedence: explicit `overrides` argument > sidecar `<project_dir>/state/puppet_lanes.json` > automatic detection > None.

SIDECAR FORMAT (user editable, tolerant of mistakes; a bad file or a bad entry is ignored, never raised):
    {
      "3":   {"x0": 0.55, "x1": 0.96, "y": 0.92, "h_hint": 0.2, "avoid": [[0.63, 0.86]], "conf": 0.9},
      "012": {"x0": 0.08, "x1": 0.93, "y": 0.86},
      "019": null
    }
Keys are the scene number ("3" or "003") or the file stem ("003"); the file name ("003.png") also works. `null` (or false) means
"this picture has NO lane, do not place anyone" and also stops automatic detection. Keys starting with "_" are comments.
`h_hint`, `avoid` and `conf` are optional. Values outside 0..1 are clamped; x1 must exceed x0 by at least 0.05."""
from __future__ import annotations
import json, re
from pathlib import Path
import numpy as np
from PIL import Image

SIDECAR = Path("state") / "puppet_lanes.json"
MIN_SPAN = 0.05
AUTO_MIN_CONF = 0.55
_NONE = object()

# ------------------------------------------------------------------ validation
def _num(v, lo=0.0, hi=1.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return min(max(f, lo), hi)

def default_h_hint(y: float) -> float:
    return round(min(max(0.12 + 0.35 * (y - 0.5), 0.10), 0.40), 3)

def clean_lane(d, source="override"):
    """Validate / normalise one lane dict. Returns a lane dict or None if unusable."""
    if not isinstance(d, dict):
        return None
    x0, x1, y = _num(d.get("x0")), _num(d.get("x1")), _num(d.get("y"))
    if x0 is None or x1 is None or y is None:
        return None
    if x0 > x1:
        x0, x1 = x1, x0
    if x1 - x0 < MIN_SPAN or y < 0.2:
        return None
    h = _num(d.get("h_hint"), 0.04, 0.8)
    if h is None:
        h = default_h_hint(y)
    conf = _num(d.get("conf"))
    conf = 0.9 if conf is None else conf
    av = []
    raw = d.get("avoid")
    for s in (raw if isinstance(raw, (list, tuple)) else []):
        if not isinstance(s, (list, tuple)) or len(s) != 2:
            continue
        a, b = _num(s[0]), _num(s[1])
        if a is None or b is None:
            continue
        if a > b:
            a, b = b, a
        if b - a > 0.005:
            av.append([round(a, 4), round(b, 4)])
    av.sort()
    merged = []
    for a, b in av:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return {"x0": round(x0, 4), "x1": round(x1, 4), "y": round(y, 4), "h_hint": round(h, 4),
            "avoid": merged, "conf": round(conf, 3), "source": source}

def free_spans(lane, min_w=MIN_SPAN):
    """Walkable x spans of a lane after removing its avoid zones."""
    if not lane:
        return []
    out, x = [], lane["x0"]
    for a, b in lane.get("avoid", []):
        if a > x:
            out.append([x, min(a, lane["x1"])])
        x = max(x, b)
    if x < lane["x1"]:
        out.append([x, lane["x1"]])
    return [s for s in out if s[1] - s[0] >= min_w]

# ------------------------------------------------------------------ sidecar / overrides
def load_overrides(project_dir):
    """Read <project_dir>/state/puppet_lanes.json -> {key: lane dict | None}. Missing / bad file -> {}. Bad entries are dropped."""
    if not project_dir:
        return {}
    try:
        raw = json.loads((Path(project_dir) / SIDECAR).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        k = str(k)
        if k.startswith("_"):
            continue
        if v is None or v is False:
            out[k] = None
        else:
            c = clean_lane(v, "sidecar")
            if c is not None:
                out[k] = c
    return out

def _keys(still_path, scene_no):
    p = Path(str(still_path)) if still_path else None
    ks = []
    if scene_no is None and p is not None:
        m = re.match(r"^(\d+)", p.stem)
        if m:
            scene_no = int(m.group(1))
    if scene_no is not None:
        try:
            n = int(scene_no)
            ks += [str(n), f"{n:03d}"]
        except (TypeError, ValueError):
            pass
    if p is not None:
        ks += [p.stem, p.name]
    return ks

def _lookup(table, keys):
    if not isinstance(table, dict):
        return _NONE
    norm = {str(k): v for k, v in table.items()}
    for k in keys:
        if k in norm:
            return norm[k]
    return _NONE

def _resolve(table, keys, source):
    v = _lookup(table, keys)
    if v is _NONE:
        return _NONE
    if v is None or v is False:
        return None
    c = clean_lane(v, source)
    return _NONE if c is None else c      # a malformed entry is ignored, detection continues

def lane_for(still_path, scene_no=None, overrides=None, project_dir=None):
    """See module docstring. Never raises."""
    keys = _keys(still_path, scene_no)
    r = _resolve(overrides, keys, "override")
    if r is not _NONE:
        return r
    r = _resolve(load_overrides(project_dir), keys, "sidecar")
    if r is not _NONE:
        return r
    try:
        return auto_lane(still_path)
    except Exception:
        return None

# ------------------------------------------------------------------ automatic detection
AW = 192   # analysis width

def _box(a, r):
    if r <= 0:
        return a
    k = 2 * r + 1
    p = np.pad(a, ((r, r), (r, r)), mode="edge")
    c = np.cumsum(p, axis=0, dtype=np.float64); c = np.concatenate([np.zeros((1, c.shape[1])), c])
    p = c[k:] - c[:-k]
    c = np.cumsum(p, axis=1); c = np.concatenate([np.zeros((c.shape[0], 1)), c], axis=1)
    return ((c[:, k:] - c[:, :-k]) / (k * k)).astype(np.float32)

def _components(mask):
    """Tiny 4-connected labelling (iterative flood fill). Returns list of (ys, xs) index arrays."""
    H, W = mask.shape
    seen = np.zeros_like(mask, bool)
    out = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        st = [(y0, x0)]; seen[y0, x0] = True; pts = []
        while st:
            y, x = st.pop(); pts.append((y, x))
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True; st.append((yy, xx))
        a = np.array(pts)
        out.append((a[:, 0], a[:, 1]))
    return out

def auto_lane(still_path):
    """Heuristic lane for a still, or None (with nothing to place) when the picture has no believable floor.
    Ground = calm, non-blue, non-paper-cream, non-dark lower band; sky / cloud / water / paper margin / text / dense detail are rejected.
    Dark person silhouettes and white-outlined cut-outs inside the band become `avoid` spans."""
    with Image.open(still_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        aw, ah = AW, max(int(round(AW * h / w)), 24)
        small = np.asarray(im.resize((aw, ah), Image.BILINEAR), dtype=np.float32)
        full = np.asarray(im.resize((aw * 2, ah * 2), Image.BILINEAR), dtype=np.float32)
    R, G, B = small[..., 0], small[..., 1], small[..., 2]
    gray = 0.299 * R + 0.587 * G + 0.114 * B
    mx, mn = small.max(-1), small.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    mean = _box(gray, 1)
    tex = np.sqrt(np.maximum(_box(gray * gray, 2) - _box(gray, 2) ** 2, 0))   # local std
    blue = (B > R + 6) & (B > G - 4)
    cream = (gray > 190) & (sat < 0.30) & (tex < 14)                         # blank paper
    dark = gray < 70
    yy = (np.arange(ah)[:, None] + 0.5) / ah
    xx = (np.arange(aw)[None, :] + 0.5) / aw
    margin = (xx < 0.045) | (xx > 0.955) | (yy > 0.955)
    # sheet of text / map / chart / crowd: dense fine detail over the lower two thirds
    low = np.broadcast_to((yy > 0.45) & (yy < 0.95), tex.shape)
    lowb = np.broadcast_to(yy > 0.35, tex.shape)
    dense = float(((tex > 26) & low).sum()) / max(float(low.sum()), 1)
    bluefrac = float((blue & lowb).sum()) / max(float(lowb.sum()), 1)
    if dense > 0.42 or bluefrac > 0.35:
        return None
    ground = (~blue) & (~cream) & (~dark) & (~margin) & (tex < 20) & (mean > 70)
    ground = ground & (_box(ground.astype(np.float32), 1) > 0.6)
    # best feet row: longest horizontal run of ground in a 3-row band, preferring lower rows
    best = None
    band = max(int(round(0.05 * ah)), 3)
    for r in range(int(0.72 * ah), int(0.94 * ah)):
        rows = ground[max(r - band, 0): r + 1]
        col_ok = rows.mean(0) > 0.8
        # longest run
        run, bs, be, s = 0, 0, 0, None
        for x in range(aw + 1):
            if x < aw and col_ok[x]:
                if s is None:
                    s = x
            else:
                if s is not None and x - s > run:
                    run, bs, be = x - s, s, x
                s = None
        span = run / aw
        if span < 0.28:
            continue
        # body room above the feet must not be sky/blue/paper margin
        body = slice(max(r - int(0.22 * ah), 0), r)
        cols = slice(bs, be)
        bad = float((blue[body, cols] | cream[body, cols]).mean())
        if bad > 0.55:
            continue
        score = span * (0.6 + 0.4 * (r / ah)) * (1 - 0.5 * bad)
        if best is None or score > best[0]:
            best = (score, r, bs, be, span, bad)
    if best is None:
        return None
    score, r, bs, be, span, bad = best
    x0, x1, y = bs / aw, be / aw, (r + 1) / ah
    # avoid: dark silhouettes and white-outlined cut-outs that reach into the body band over the lane
    av = []
    top = max(int((y - 0.30) * ah), 0)
    dmask = dark.copy(); dmask[:, :bs - 2 if bs > 2 else 0] = False; dmask[:, min(be + 2, aw):] = False
    for ys, xs in _components(dmask):
        if len(ys) < 0.003 * aw * ah:
            continue
        if ys.max() >= top and ys.min() <= r and (ys.max() - ys.min()) > 0.12 * ah and ys.max() >= r - int(0.12 * ah):
            av.append([max(xs.min() / aw - 0.02, 0), min((xs.max() + 1) / aw + 0.02, 1)])
    fh, fw = full.shape[:2]
    white = full.min(-1) >= 249
    wy0, wy1 = int(top * 2), min(int((r + 1) * 2), fh)
    colw = white[wy0:wy1].mean(0)
    wcols = _box(colw[None, :].astype(np.float32), 0)[0] > 0.04
    s = None
    for x in range(fw + 1):
        if x < fw and wcols[x]:
            if s is None:
                s = x
        else:
            if s is not None and (x - s) / fw > 0.02:
                av.append([max(s / fw - 0.02, 0), min(x / fw + 0.02, 1)])
            s = None
    lane = clean_lane({"x0": x0, "x1": x1, "y": y, "avoid": [a for a in av if a[1] > x0 and a[0] < x1],
                       "conf": min(0.4 + score * 0.9, 0.85)}, "auto")
    if lane is None:
        return None
    # avoid zones may swallow the lane
    if sum(b - a for a, b in free_spans(lane)) < 0.25:
        return None
    if lane["conf"] < AUTO_MIN_CONF or bad > 0.35:
        return None
    return lane
