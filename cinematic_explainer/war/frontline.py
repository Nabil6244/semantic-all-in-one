"""War Documentary front lines: sourced, dated territorial-control snapshots, drawn on the tactical map (maps_tactical.tac_map, param "frontline").

Nothing here is invented. A front line is only ever drawn from a snapshot file that names its source, its licence and the date it describes.
The app ships NO real snapshot data (licensing is the user's call, see docs/war/FRONTLINE_PLAN.md); with an empty library every function here
is a no-op and existing videos are unchanged.

SNAPSHOT FILE (one JSON per snapshot, schema "war.frontline/1"; GeoJSON can be converted with import_geojson)
  id          unique, e.g. "isw-2024-03-12"
  as_of       YYYY-MM-DD: the date the source's assessment describes (not the download date)
  source      who made the assessment, e.g. "Institute for the Study of War and AEI's Critical Threats Project"
  licence     the terms it is used under, e.g. "OGL v3.0", "CC BY-SA 4.0", "used with permission (email 2026-11-10)"
  source_url  optional, shown in the credits
  status      assessed (default) | claimed | disputed       claimed/disputed areas are hatched, never drawn as solid control
  claimant    who claims it (status claimed)
  side        whose control the areas show: "russia" (default) | "ukraine"
  theatre     "ukraine" (default)
  areas       [[[lon, lat], ...], ...] or [{"outer": [...], "holes": [[...], ...]}, ...]   rings of (lon, lat)
  test_data   true for synthetic test files: every frame then says TEST DATA - NOT A REAL FRONT LINE

ON THE MAP (tac_map params["frontline"], made by attach() or by hand)
  {"mode": "single", "snap": <snapshot dict>}                           the controlled area, the contact line, its date and source
  {"mode": "compare", "a": <older>, "b": <newer>, "start", "length"}   the older line stays as a ghost, gains and losses sweep in, then
                                                                         the change is measured (km2 between the two assessments)
  "stale": "MAY HAVE CHANGED SINCE" chip (attach sets it when the latest snapshot is older than stale_days and the narration speaks of now)

Honesty rules enforced here: no source / licence / date -> rejected; a date is always on screen with the line; disputed or claimed areas are
hatched with a dashed edge; the newest snapshot is never called "current" (only "as of <date>"); a narration date with no snapshot within
max_gap_days gets no line at all (an older line is not passed off as that date).
"""

from __future__ import annotations

import datetime as _dt
import gzip
import json
import math
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import geo_data as G
from . import motion as M
from . import tokens as T
from .. import look as L

SCHEMA = "war.frontline/1"
DATA_DIR = Path(__file__).resolve().parent / "data" / "frontlines"
STATUSES = ("assessed", "claimed", "disputed")
STALE_DAYS = 14
MAX_GAP_DAYS = 45
W, H = T.W, T.H

OCC = {"russia": (200, 44, 56), "ukraine": (52, 112, 220)}
OTHER = {"russia": "ukraine", "ukraine": "russia"}
SIDE_NAME = {"russia": "RUSSIAN", "ukraine": "UKRAINIAN"}
AMBER = (246, 196, 52)


# ================================================================================================================ library
def _date(s: Any) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def _rings(areas: Any) -> List[Tuple[List[Tuple[float, float]], List[List[Tuple[float, float]]]]]:
    out = []
    for a in areas or []:
        if isinstance(a, dict):
            outer, holes = a.get("outer") or [], a.get("holes") or []
        else:
            outer, holes = a, []
        try:
            o = [(float(p[0]), float(p[1])) for p in outer]
            hs = [[(float(p[0]), float(p[1])) for p in h] for h in holes]
        except (TypeError, ValueError, IndexError):
            continue
        if len(o) >= 3 and all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in o):
            out.append((o, [h for h in hs if len(h) >= 3]))
    return out


def validate(s: Any) -> Tuple[bool, str]:
    """(ok, why). A snapshot is usable only with a real date, a named source, a licence and at least one area."""
    if not isinstance(s, dict):
        return False, "not a snapshot"
    if _date(s.get("as_of")) is None:
        return False, "missing or invalid as_of (YYYY-MM-DD)"
    if not str(s.get("source") or "").strip():
        return False, "missing source"
    if not str(s.get("licence") or s.get("license") or "").strip():
        return False, "missing licence"
    if str(s.get("status") or "assessed").lower() not in STATUSES:
        return False, "status must be assessed, claimed or disputed"
    if str(s.get("side") or "russia").lower() not in OCC:
        return False, "side must be russia or ukraine"
    if not _rings(s.get("areas")):
        return False, "no usable area"
    return True, ""


def normalise(s: dict) -> dict:
    d = dict(s)
    d["as_of"] = str(_date(s["as_of"]))
    d["licence"] = str(s.get("licence") or s.get("license"))
    d["status"] = str(s.get("status") or "assessed").lower()
    d["side"] = str(s.get("side") or "russia").lower()
    d["theatre"] = str(s.get("theatre") or "ukraine").lower()
    d["id"] = str(s.get("id") or f"{d['source'][:12]}-{d['as_of']}").strip()
    d["test_data"] = bool(s.get("test_data"))
    return d


def default_dirs() -> List[Path]:
    """The package folder (ships empty) and the per-user folder next to the War registry (where imported snapshots go)."""
    dirs = [DATA_DIR]
    try:
        from .registry import default_path

        dirs.append(Path(default_path()).parent / "frontlines")
    except Exception:
        pass
    return dirs


_LIB_CACHE: Dict[tuple, Tuple[List[dict], List[Tuple[str, str]]]] = {}


def load_library(dirs: Optional[Sequence[Any]] = None) -> Tuple[List[dict], List[Tuple[str, str]]]:
    """(valid snapshots sorted by date, [(file, why rejected)]). Cached on the files' names, sizes and times."""
    files: List[Path] = []
    for d in (default_dirs() if dirs is None else [Path(x) for x in dirs]):
        if d.is_dir():
            files += sorted(p for p in d.iterdir() if p.suffix in (".json", ".gz") and not p.name.startswith("."))
    key = tuple((str(p), p.stat().st_size, p.stat().st_mtime) for p in files)
    if key in _LIB_CACHE:
        return _LIB_CACHE[key]
    good, bad, seen = [], [], set()
    for p in files:
        try:
            raw = gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")
            s = json.loads(raw)
        except (OSError, ValueError) as exc:
            bad.append((p.name, f"unreadable: {exc}"))
            continue
        ok, why = validate(s)
        if not ok:
            bad.append((p.name, why))
            continue
        s = normalise(s)
        if s["id"] in seen:
            bad.append((p.name, "duplicate id " + s["id"]))
            continue
        seen.add(s["id"])
        good.append(s)
    good.sort(key=lambda s: (s["as_of"], s["id"]))
    _LIB_CACHE[key] = (good, bad)
    return good, bad


def _rdp(pts: np.ndarray, eps: float) -> np.ndarray:
    """Douglas-Peucker simplification (iterative)."""
    if len(pts) < 4 or eps <= 0:
        return pts
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg = pts[b] - pts[a]
        n = math.hypot(seg[0], seg[1])
        rel = pts[a + 1:b] - pts[a]
        dist = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / n if n > 0 else np.hypot(rel[:, 0], rel[:, 1])
        i = int(np.argmax(dist))
        if dist[i] > eps:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return pts[keep]


def import_geojson(path: Any, out_dir: Any, *, as_of: str, source: str, licence: str, source_url: str = "", status: str = "assessed",
                   claimant: str = "", side: str = "russia", snap_id: str = "", tolerance_deg: float = 0.004,
                   property_filter: Optional[Dict[str, Any]] = None) -> Path:
    """Convert a GeoJSON file (Polygon / MultiPolygon features; e.g. an ISW or DeepState export the user is entitled to use) into a snapshot
    file in out_dir. Every provenance field is required here, not guessed from the file. property_filter keeps only features whose properties
    match (e.g. {"name": "Assessed Russian-controlled Ukrainian Territory"}). Returns the written path; raises ValueError on bad input."""
    gj = json.loads(Path(path).read_text(encoding="utf-8"))
    feats = gj.get("features") if gj.get("type") == "FeatureCollection" else [gj if gj.get("type") == "Feature" else {"geometry": gj}]
    areas = []
    for f in feats or []:
        props = f.get("properties") or {}
        if property_filter and any(props.get(k) != v for k, v in property_filter.items()):
            continue
        g = f.get("geometry") or {}
        polys = g.get("coordinates") if g.get("type") == "MultiPolygon" else [g.get("coordinates")] if g.get("type") == "Polygon" else []
        for poly in polys or []:
            rings = [_rdp(np.asarray(r, dtype=np.float64)[:, :2], tolerance_deg) for r in poly if len(r) >= 4]
            rings = [np.round(r, 5).tolist() for r in rings if len(r) >= 4]
            if rings:
                areas.append({"outer": rings[0], "holes": rings[1:]} if len(rings) > 1 else rings[0])
    snap = {"schema": SCHEMA, "id": snap_id or f"{re.sub(r'[^a-z0-9]+', '-', source.lower())[:24].strip('-')}-{as_of}", "as_of": as_of,
            "source": source, "licence": licence, "source_url": source_url, "status": status, "claimant": claimant, "side": side,
            "theatre": "ukraine", "areas": areas, "imported_from": Path(path).name}
    ok, why = validate(snap)
    if not ok:
        raise ValueError(why)
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    dest = od / (snap["id"] + ".json.gz")
    with gzip.open(dest, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    return dest


# ================================================================================================================ picking by date
def pick(snaps: Sequence[dict], when: _dt.date, max_gap_days: int = MAX_GAP_DAYS, side: str = "russia") -> Optional[dict]:
    """The newest snapshot on or before `when`, no older than max_gap_days (an older line is not shown as `when`)."""
    best = None
    for s in snaps:
        d = _date(s["as_of"])
        if d is not None and d <= when and s.get("side", "russia") == side and (when - d).days <= max_gap_days:
            if best is None or d > _date(best["as_of"]):
                best = s
    return best


def latest(snaps: Sequence[dict], side: str = "russia") -> Optional[dict]:
    c = [s for s in snaps if s.get("side", "russia") == side]
    return max(c, key=lambda s: s["as_of"]) if c else None


def bbox(s: dict) -> Tuple[float, float, float, float]:
    xs = [x for o, _ in _rings(s.get("areas")) for x, _y in o]
    ys = [y for o, _ in _rings(s.get("areas")) for _x, y in o]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)


# ================================================================================================================ geometry: area on the ground
_AREA_CACHE: Dict[tuple, Dict[str, float]] = {}
CELL = 0.01           # degrees; ~1.1 x 0.75 km at 48 N


def _raster_ll(s: dict, box: Tuple[float, float, float, float]) -> np.ndarray:
    lon0, lat0, lon1, lat1 = box
    w, h = max(1, int(math.ceil((lon1 - lon0) / CELL))), max(1, int(math.ceil((lat1 - lat0) / CELL)))
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    for outer, holes in _rings(s.get("areas")):
        d.polygon([((x - lon0) / CELL, (lat1 - y) / CELL) for x, y in outer], fill=1)
        for hh in holes:
            d.polygon([((x - lon0) / CELL, (lat1 - y) / CELL) for x, y in hh], fill=0)
    return np.asarray(im, dtype=bool)


def change_km2(a: dict, b: dict) -> Dict[str, float]:
    """{gained, lost, net} in km2 for the side the snapshots show, from a 0.01-degree equal-area-weighted raster (rounded to 10 km2)."""
    key = (a["id"], b["id"])
    if key in _AREA_CACHE:
        return _AREA_CACHE[key]
    ba, bb = bbox(a), bbox(b)
    box = (min(ba[0], bb[0]) - CELL, min(ba[1], bb[1]) - CELL, max(ba[2], bb[2]) + CELL, max(ba[3], bb[3]) + CELL)
    ra, rb = _raster_ll(a, box), _raster_ll(b, box)
    h = ra.shape[0]
    lats = box[3] - (np.arange(h) + 0.5) * CELL
    cell_km2 = (CELL * 111.32) ** 2 * np.cos(np.radians(lats))[:, None]
    g = float((cell_km2 * (rb & ~ra)).sum())
    lo = float((cell_km2 * (ra & ~rb)).sum())
    r10 = lambda v: float(int(round(v / 10.0)) * 10)
    out = {"gained": r10(g), "lost": r10(lo), "net": r10(g - lo)}
    _AREA_CACHE[key] = out
    return out


# ================================================================================================================ drawing
_MASK_CACHE: "OrderedDict[tuple, Image.Image]" = OrderedDict()
_HATCH: Dict[int, Image.Image] = {}


def _feature(s: dict) -> G.Feature:
    polys = [[o] + hs for o, hs in _rings(s.get("areas"))]
    return G.Feature({"n": s.get("id", ""), "iso": "", "g": {"type": "MultiPolygon", "coordinates": polys}})


_FEAT_CACHE: Dict[str, G.Feature] = {}


def _mask(key: str, feat: Optional[G.Feature], view: Any) -> Image.Image:
    """Anti-aliased L mask of a feature at 1x (drawn at 2x and reduced), cached per view."""
    from . import maps as MP

    ck = (key, view.key())
    if ck in _MASK_CACHE:
        _MASK_CACHE.move_to_end(ck)
        return _MASK_CACHE[ck]
    im = Image.new("L", (W * 2, H * 2), 0)
    if feat is not None:
        MP._draw_feature(ImageDraw.Draw(im), feat, view, view.bounds(), 255, None, 0, 2)
    im = im.reduce(2)
    _MASK_CACHE[ck] = im
    while len(_MASK_CACHE) > 24:
        _MASK_CACHE.popitem(last=False)
    return im


def _snap_mask(s: dict, view: Any) -> Image.Image:
    f = _FEAT_CACHE.get(s["id"])
    if f is None:
        f = _FEAT_CACHE[s["id"]] = _feature(s)
    return _mask("snap:" + s["id"], f, view)


_LAND: List[Any] = []


def _land_mask(view: Any) -> Image.Image:
    """Ukraine within its internationally recognised borders (Natural Earth's UKR plus the Crimea polygon it files under RUS)."""
    if not _LAND:
        from . import maps as MP

        u, r = G.find_country("UKR"), G.find_country("RUS")
        f = G.Feature({"n": "UKR+CRIMEA", "iso": "", "g": {"type": "MultiPolygon", "coordinates": [[[0, 0], [0, 1], [1, 0]]]}})
        f.polys = list(u.polys if u else []) + [p for p in (r.polys if r else []) if MP._in_crimea(p[0].bbox)]
        f.bbox = u.bbox if u else (0.0, 0.0, 0.0, 0.0)
        _LAND.append(f)
    return _mask("land:UKR", _LAND[0], view)


def _hatch(spacing: int = 9) -> Image.Image:
    if spacing not in _HATCH:
        im = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(im)
        for x in range(-H, W, spacing):
            d.line([(x, H), (x + H, 0)], fill=255, width=2)
        _HATCH[spacing] = im
    return _HATCH[spacing]


def _dashed(spacing: int = 14) -> Image.Image:
    k = 1000 + spacing
    if k not in _HATCH:
        yy, xx = np.mgrid[0:H, 0:W]
        _HATCH[k] = Image.fromarray(((((xx + yy) // spacing) % 2) * 255).astype(np.uint8), "L")
    return _HATCH[k]


def _dilate(im: Image.Image, r: int) -> Image.Image:
    """Square max filter of radius r in numpy (separable shifts: ~20x faster than PIL's rank filter on a full frame)."""
    a = np.asarray(im)
    out = a.copy()
    for k in range(1, r + 1):
        np.maximum(out[:, k:], a[:, :-k], out=out[:, k:])
        np.maximum(out[:, :-k], a[:, k:], out=out[:, :-k])
    b = out.copy()
    for k in range(1, r + 1):
        np.maximum(out[k:, :], b[:-k, :], out=out[k:, :])
        np.maximum(out[:-k, :], b[k:, :], out=out[:-k, :])
    return Image.fromarray(out, "L")


def _edge(occ: Image.Image, land: Image.Image) -> Image.Image:
    """The contact line: the rim of the controlled area where it meets land of the other side (not the coast, not the state border)."""
    grown = _dilate(occ, 2)
    return ImageChops.multiply(ImageChops.subtract(grown, occ), land)


def _tint(mask: Image.Image, rgb: Tuple[int, int, int], alpha: float) -> Image.Image:
    lay = Image.new("RGBA", (W, H), rgb + (0,))
    lay.putalpha(mask.point(lambda v: int(v * alpha)))
    return lay


_YY, _XX = np.mgrid[0:H, 0:W].astype(np.float32)


def _sweep(mask: Image.Image, origin: Tuple[float, float], p: float) -> Image.Image:
    """Reveal `mask` as a soft front moving away from `origin` across it (p 0..1)."""
    a = np.asarray(mask, dtype=np.float32)
    ys, xs = np.nonzero(a[::4, ::4] > 8)
    ys, xs = ys * 4, xs * 4
    if len(xs) == 0 or p <= 0:
        return Image.new("L", (W, H), 0)
    if p >= 1:
        return mask
    cx, cy = xs.mean(), ys.mean()
    dx, dy = cx - origin[0], cy - origin[1]
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    proj = xs * dx + ys * dy
    lo, hi = float(proj.min()), float(proj.max())
    soft = max(8.0, 0.18 * (hi - lo))
    s = (_XX * dx + _YY * dy - lo) / max(1.0, hi - lo + soft)
    k = np.clip((p * 1.15 - s) * (hi - lo + soft) / soft, 0.0, 1.0)
    return Image.fromarray((a * k).astype(np.uint8), "L")


def _centre(mask: Image.Image) -> Optional[Tuple[float, float]]:
    a = np.asarray(mask)[::2, ::2]
    ys, xs = np.nonzero(a > 100)
    if len(xs) < 8:
        return None
    return float(np.median(xs)) * 2, float(np.median(ys)) * 2


def ticker_label(as_of: str) -> str:
    d = _date(as_of)
    return d.strftime("%b %Y").upper() if d else str(as_of).upper()


def draw_ticker(img: Image.Image, tick: Tuple[Any, ...], x: int, y: int, right: bool = False) -> Tuple[int, int, int, int]:
    """Big date ticker: the old date rolls up and out as the new one rolls in with the line; step dots below. right: x is the right edge."""
    prev, now, p, i, n = tick[:5]
    fade = float(tick[5]) if len(tick) > 5 else 1.0
    f = T.font("display", 64)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    w = int(max(d.textlength(prev, font=f), d.textlength(now, font=f))) + 8
    h = 70
    if right:
        x = x - max(w, 16 * n)
    clip = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(clip)
    e = M.ease_in_out(p)
    if prev != now and p < 1.0:
        cd.text((0, -h * e - 6), prev, font=f, fill=(236, 238, 242, int(255 * (1 - e))), stroke_width=2, stroke_fill=(8, 10, 14, 255))
    cd.text((0, h * (1 - e) - 6 if prev != now else -6), now, font=f, fill=(255, 255, 255, int(255 * max(e, 0.0 if prev != now else 1.0))),
            stroke_width=2, stroke_fill=(8, 10, 14, 255))
    lay.alpha_composite(clip, (x, y))
    for j in range(n):
        cx = x + 6 + j * 16
        on = j <= i
        d.ellipse([cx - 4, y + h + 6, cx + 4, y + h + 14], fill=(246, 196, 52, 255) if on else (90, 96, 106, 255))
        if j < n - 1:
            d.line([(cx + 5, y + h + 10), (cx + 11, y + h + 10)], fill=(90, 96, 106, 255), width=2)
    img.alpha_composite(L.fade(lay, fade) if fade < 1.0 else lay)
    return (x, y, x + max(w, 16 * n), y + h + 16)


def date_label(as_of: str) -> str:
    d = _date(as_of)
    return d.strftime("%d %b %Y").upper().lstrip("0") if d else str(as_of).upper()


def _short_source(s: dict) -> str:
    src = str(s.get("short_source") or s.get("source") or "")
    return src if len(src) <= 42 else src[:40].rstrip() + "…"


def stamp_lines(spec: dict) -> List[Tuple[str, Tuple[int, int, int]]]:
    """The data stamp under the map badge: what the area is, its date(s), its source; amber when stale or test data."""
    a = spec.get("a") if spec.get("mode") == "compare" else spec.get("snap")
    b = spec.get("b") if spec.get("mode") == "compare" else None
    s = b or a
    side = SIDE_NAME.get(s.get("side", "russia"), "")
    what = {"assessed": f"{side} CONTROL · ASSESSED", "claimed": f"{side} CONTROL · CLAIMED" + (f" BY {s['claimant'].upper()}" if s.get("claimant") else ""),
            "disputed": f"{side} CONTROL · DISPUTED"}[s.get("status", "assessed")]
    when = f"{date_label(a['as_of'])}  TO  {date_label(b['as_of'])}" if b else "AS OF " + date_label(a["as_of"])
    srcs = _short_source(a) if not b or _short_source(a) == _short_source(b) else f"{_short_source(a)} / {_short_source(b)}"
    out = [(what, (236, 238, 242)), (when, (236, 238, 242)), ("SOURCE: " + srcs.upper(), (170, 178, 190))]
    if spec.get("stale"):
        out.append((str(spec["stale"]).upper(), AMBER))
    if a.get("test_data") or (b or {}).get("test_data"):
        out.append(("TEST DATA · NOT A REAL FRONT LINE", AMBER))
    return out


def _seq_step(spec: dict, t: float) -> Tuple[dict, int, float]:
    """(the single/compare spec in force at t, step index, transition progress) for a sequence spec."""
    snaps = [s for s in spec.get("snaps") or [] if validate(s)[0]]
    step = float(spec.get("step", 3.5))
    t_first = float(spec.get("start", 0.6))
    times = [float(x) for x in spec.get("times") or []]
    if len(times) != len(snaps):
        times = [t_first + step * i for i in range(len(snaps))]
    i = max([j for j, tt in enumerate(times) if tt <= t] or [0])
    if i == 0 or len(snaps) < 2:
        return {"mode": "single", "snap": snaps[0] if snaps else None, "start": times[0] if times else t_first,
                "alpha_boost": spec.get("alpha_boost", 1.0)}, 0, 1.0
    gap = times[i] - times[i - 1]
    ln = min(float(spec.get("length", 2.2)), max(0.8, gap - 0.6))
    sub = {"mode": "compare", "a": snaps[i - 1], "b": snaps[i], "start": times[i], "length": ln, "fade_at": times[0], "labels": i == len(snaps) - 1,
           "alpha_boost": spec.get("alpha_boost", 1.0)}
    return sub, i, M.ease_in_out(M.ramp(t, times[i], ln))


def draw(img: Image.Image, view: Any, spec: dict, t: float) -> Tuple[Image.Image, dict]:
    """Composite the front-line layer onto the map image (1x RGBA) at time t (s from card start). Returns (image, info)."""
    if spec.get("mode") == "sequence":
        sub, i, p = _seq_step(spec, t)
        img, info = draw(img, view, sub, t)
        snaps = [s for s in spec.get("snaps") or [] if validate(s)[0]]
        info["current_spec"] = sub
        times = [float(x) for x in spec.get("times") or []]
        end_t = (times[-1] if len(times) == len(snaps) and times else float(spec.get("start", 0.6)) + float(spec.get("step", 3.5)) * (len(snaps) - 1))
        fade = 1.0 - M.ramp(t, end_t + float(spec.get("length", 2.2)) + 3.0, 0.6)       # the ticker leaves once the history has been told
        if snaps and fade > 0:
            prev = snaps[max(0, i - 1)]["as_of"]
            info["ticker"] = (ticker_label(prev), ticker_label(snaps[i]["as_of"]), p if i > 0 else 1.0, i, len(snaps), fade)
        return img, info
    info: Dict[str, Any] = {"drawn": False, "labels": []}
    mode = spec.get("mode", "single")
    a = spec.get("a") if mode == "compare" else spec.get("snap")
    b = spec.get("b") if mode == "compare" else None
    if not a or not validate(a)[0] or (b is not None and not validate(b)[0]):
        info["rejected"] = "invalid snapshot"
        return img, info
    side = a.get("side", "russia")
    col = OCC.get(side, OCC["russia"])
    t0 = float(spec.get("fade_at", spec.get("start", 0.6)))
    k_in = M.ease_out(M.ramp(t, t0, 0.8))
    land = _land_mask(view)
    ma = ImageChops.multiply(_snap_mask(a, view), land)      # a source polygon that overshoots the coast stops at the shore
    out = img
    status = (b or a).get("status", "assessed")

    boost = float(spec.get("alpha_boost", 1.0))

    def area(mask: Image.Image, rgb, alpha: float, st: str) -> None:
        nonlocal out
        alpha *= boost
        if st in ("claimed", "disputed"):
            mask = ImageChops.multiply(mask, _hatch())
            alpha *= 1.6
        out = Image.alpha_composite(out, _tint(mask, rgb, min(1.0, alpha)))

    def line(mask_occ: Image.Image, rgb, k: float, st: str, ghost: bool = False) -> None:
        nonlocal out
        e = _edge(mask_occ, land)
        if st in ("claimed", "disputed") or ghost:
            e = ImageChops.multiply(e, _dashed())
        if not ghost:
            glow = e.filter(ImageFilter.GaussianBlur(5))
            out = Image.alpha_composite(out, _tint(glow, rgb, 0.9 * k))
            out = Image.alpha_composite(out, _tint(_dilate(e, 1), (12, 12, 14), 0.75 * k))
            out = Image.alpha_composite(out, _tint(e, tuple(min(255, c + 70) for c in rgb), k))
        else:
            out = Image.alpha_composite(out, _tint(e, (230, 232, 236), 0.55 * k))

    if mode != "compare" or b is None:
        area(ma, col, 0.40 * k_in, a.get("status", "assessed"))
        line(ma, col, k_in, a.get("status", "assessed"))
        info["drawn"] = True
    else:
        mb = ImageChops.multiply(_snap_mask(b, view), land)
        p = M.ease_in_out(M.ramp(t, float(spec.get("start", 1.2)), float(spec.get("length", 2.6))))
        gain = ImageChops.subtract(mb, ma)
        loss = ImageChops.subtract(ma, mb)
        keep = ImageChops.multiply(ma, mb)
        area(keep, col, 0.40 * k_in, status)
        c_keep = _centre(ma) or (W / 2, H / 2)
        g_now = _sweep(gain, c_keep, p)                          # gains spread outward from the area already held
        c_loss = _centre(loss)
        l_now = _sweep(loss, (2 * c_loss[0] - c_keep[0], 2 * c_loss[1] - c_keep[1]) if c_loss else c_keep, p)   # losses roll back toward it
        flash = 1.0 + 0.6 * math.exp(-6 * max(0.0, t - float(spec.get("start", 1.2)) - float(spec.get("length", 2.6)))) * (p >= 1)
        area(g_now, tuple(min(255, int(c * 1.15)) for c in col), 0.62 * k_in * min(1.4, flash), status)
        other = OCC[OTHER.get(side, "ukraine")]
        area(ImageChops.subtract(loss, l_now), col, 0.40 * k_in, status)       # what is not yet lost is still held
        area(l_now, other, 0.55 * k_in, status)
        line(ma, col, k_in * (1 - 0.6 * p), a.get("status", "assessed"), ghost=p > 0.02)   # the old line stays as a dashed ghost
        cur = ImageChops.add(ImageChops.subtract(ma, l_now), g_now)
        line(cur, col, k_in, status)
        info["drawn"] = True
        if p >= 1.0 and spec.get("labels", True):
            ch = change_km2(a, b)
            info["change_km2"] = ch
            k_lab = M.ease_out(M.ramp(t, float(spec.get("start", 1.2)) + float(spec.get("length", 2.6)), 0.5))
            sn = SIDE_NAME.get(side, "")
            on = SIDE_NAME.get(OTHER.get(side, ""), "")
            if ch["gained"] >= 10 and (_centre(gain) is not None):
                info["labels"].append((f"{sn} GAINS ~{int(ch['gained']):,} KM²", _centre(gain), col, k_lab))
            if ch["lost"] >= 10 and c_loss is not None:
                info["labels"].append((f"{on} GAINS ~{int(ch['lost']):,} KM²", c_loss, other, k_lab))
    return out, info


def draw_labels(img: Image.Image, info: dict, placer: Any) -> List[str]:
    """Change labels (after the map's own labels have their places): a dark chip with a coloured rule, beside the changed area."""
    d = ImageDraw.Draw(img)
    f = T.font("bold", 15)
    done = []
    for txt, (x, y), rgb, k in info.get("labels", []):
        if k <= 0:
            continue
        w = int(L.spaced_width(d, txt, f, 0.08)) + 22
        cands = [(x - w / 2, y - 46, x + w / 2, y - 18), (x - w / 2, y + 18, x + w / 2, y + 46), (x + 20, y - 14, x + 20 + w, y + 14),
                 (x - 20 - w, y - 14, x - 20, y + 14)]
        r = placer.first_free(cands)
        if r is None:
            continue
        placer.take(txt, r)
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(lay)
        ld.rectangle(r, fill=(10, 12, 16, 236), outline=(200, 206, 216, 255), width=1)
        ld.rectangle((r[0], r[1], r[0] + 4, r[3]), fill=rgb + (255,))
        L.spaced(ld, (r[0] + 13, r[1] + 6), txt, f, (240, 242, 246, 255), 0.08)
        img.alpha_composite(L.fade(lay, k))
        done.append(txt)
    return done


def draw_stamp(img: Image.Image, spec: dict, x: int, y: int, t: float) -> Tuple[int, int, int, int]:
    """The data stamp (what, when, who) under the badge. Returns its rectangle."""
    d = ImageDraw.Draw(img)
    lines = stamp_lines(spec)
    fs = [T.font("bold", 13)] + [T.font("bold", 13)] + [T.font("regular", 12)] * (len(lines) - 2)
    w = max(int(L.spaced_width(d, s, f, 0.08)) for (s, _), f in zip(lines, fs)) + 26
    h = 10 + 19 * len(lines)
    k = M.ease_out(M.ramp(t, float(spec.get("fade_at", spec.get("start", 0.6))), 0.5))
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    side = ((spec.get("b") or spec.get("a") or spec.get("snap") or {}).get("side") or "russia")
    ld.rectangle((x, y, x + w, y + h), fill=(10, 12, 16, 236), outline=(170, 176, 186, 255), width=1)
    ld.rectangle((x, y, x + 4, y + h), fill=OCC.get(side, OCC["russia"]) + (255,))
    for i, ((s, c), f) in enumerate(zip(lines, fs)):
        L.spaced(ld, (x + 14, y + 6 + 19 * i), s, f, c + (255,), 0.08)
    img.alpha_composite(L.fade(lay, k))
    if any(s.startswith("TEST DATA") for s, _ in lines):          # synthetic data can never pass for real: a watermark across the frame
        wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        wd = ImageDraw.Draw(wm)
        fw = T.font("bold", 54)
        txt = "TEST DATA · NOT A REAL FRONT LINE"
        tw = wd.textlength(txt, font=fw)
        wd.text(((W - tw) / 2, H / 2 - 30), txt, font=fw, fill=(246, 196, 52, 70))
        img.alpha_composite(wm.rotate(14, resample=Image.BICUBIC))
    return (x, y, x + w, y + h)


def source_line(spec: dict) -> str:
    a = spec.get("a") if spec.get("mode") == "compare" else spec.get("snap")
    b = spec.get("b") if spec.get("mode") == "compare" else None
    parts = []
    for s in [a] + ([b] if b and _short_source(b) != _short_source(a) else []):
        parts.append(f"Control: {_short_source(s)} ({s.get('licence')})")
    return "Map: Natural Earth (public domain). " + "; ".join(parts) + "."


def credit_lines(spec: dict) -> List[str]:
    out = []
    for s in [spec.get("snap"), spec.get("a"), spec.get("b")] + list(spec.get("snaps") or []):
        if s:
            line = f"Territorial control as of {s['as_of']}: {s['source']} ({s.get('status', 'assessed')}), licence: {s['licence']}" + \
                   (f", {s['source_url']}" if s.get("source_url") else "") + (" [TEST DATA]" if s.get("test_data") else "")
            if line not in out:
                out.append(line)
    return out


# ================================================================================================================ narration -> front line
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_MON = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
_FULL = re.compile(r"\b(\d{1,2})\s+" + _MON + r",?\s+((?:19|20)\d{2})\b|\b" + _MON + r"\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b", re.IGNORECASE)
_MONTH = re.compile(r"\b(?:(early|mid|late)[- ])?" + _MON + r",?\s+((?:19|20)\d{2})\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:in|by|since|until|of|during|through)\s+((?:19|20)\d{2})\b", re.IGNORECASE)
_ISO = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")
CUE = re.compile(r"\b(front ?lines?|the lines?|line of contact|contact line|territor(?:y|ies|ial)|control(?:led|s)?|occupied|occupation|captured?|seized?|"
                 r"took|taken|retook|recaptured?|liberated?|advance[sd]?|advancing|gains?|gained|counter-?offensive|offensive|retreat(?:ed|s)?|"
                 r"withdr(?:ew|awn|awal)|pushed back|lost|annex(?:ed|ation)?|salient|encircle(?:d|ment)?|breakthrough)\b", re.IGNORECASE)
CHANGE = re.compile(r"\b(retook|recaptured?|liberated?|advance[sd]?|advancing|gains?|gained|counter-?offensive|offensive|retreat(?:ed|s)?|"
                    r"withdr(?:ew|awn|awal)|pushed back|captured?|seized?|took|lost|breakthrough|shifted|moved)\b", re.IGNORECASE)
NOW = re.compile(r"\b(now|today|currently|current|at present|so far|as of|still|this week|this month)\b", re.IGNORECASE)


def dates_in(text: str) -> List[Tuple[_dt.date, _dt.date]]:
    """Every date the narration states, as (first day, last day) of the period it names, in order of appearance."""
    found: List[Tuple[int, _dt.date, _dt.date]] = []
    taken: List[Tuple[int, int]] = []

    def free(sp):
        return not any(sp[0] < b and a < sp[1] for a, b in taken)

    for m in _ISO.finditer(text):
        try:
            d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        found.append((m.start(), d, d))
        taken.append(m.span())
    for m in _FULL.finditer(text):
        if not free(m.span()):
            continue
        if m.group(1):
            day, mon, yr = int(m.group(1)), m.group(2), int(m.group(3))
        else:
            mon, day, yr = m.group(4), int(m.group(5)), int(m.group(6))
        try:
            d = _dt.date(yr, _MONTHS.index(mon.lower()) + 1, day)
        except ValueError:
            continue
        found.append((m.start(), d, d))
        taken.append(m.span())
    for m in _MONTH.finditer(text):
        if not free(m.span()):
            continue
        yr, mo = int(m.group(3)), _MONTHS.index(m.group(2).lower()) + 1
        first = _dt.date(yr, mo, 1)
        last = (_dt.date(yr + (mo == 12), mo % 12 + 1, 1) - _dt.timedelta(days=1))
        q = (m.group(1) or "").lower()
        if q == "early":
            last = _dt.date(yr, mo, 10)
        elif q == "mid":
            first, last = _dt.date(yr, mo, 11), _dt.date(yr, mo, 20)
        elif q == "late":
            first = _dt.date(yr, mo, 21)
        found.append((m.start(), first, last))
        taken.append(m.span())
    for m in _YEAR.finditer(text):
        if not free(m.span()):
            continue
        yr = int(m.group(1))
        found.append((m.start(), _dt.date(yr, 1, 1), _dt.date(yr, 12, 31)))
        taken.append(m.span())
    return [(a, b) for _, a, b in sorted(found, key=lambda x: x[0])]


def spec_for(text: str, snaps: Sequence[dict], *, carried: Optional[Tuple[_dt.date, _dt.date]] = None,
             reference: Optional[_dt.date] = None, stale_days: int = STALE_DAYS, max_gap_days: int = MAX_GAP_DAYS) -> Tuple[Optional[dict], str]:
    """(frontline spec or None, why). The narration decides: no territorial cue -> nothing; dates -> the snapshot(s) for those dates;
    a change verb over one period -> before/after comparison; no date -> only when it speaks of now (latest, with its own date)."""
    if not snaps or not CUE.search(text or ""):
        return None, "no territorial cue" if snaps else "no front-line data"
    ds = dates_in(text)
    change = bool(CHANGE.search(text))
    if not ds and carried is not None:
        ds = [carried]
    if len(ds) >= 2:
        a, b = pick(snaps, ds[0][1], max_gap_days), pick(snaps, ds[-1][1], max_gap_days)
        if a and b and a["id"] != b["id"]:
            if a["as_of"] > b["as_of"]:
                a, b = b, a
            return {"mode": "compare", "a": a, "b": b}, f"two dates named: {a['as_of']} vs {b['as_of']}"
        s = a or b
        return ({"mode": "single", "snap": s}, f"one snapshot covers the dates named ({s['as_of']})") if s else (None, "no snapshot near the dates named")
    if len(ds) == 1:
        first, last = ds[0]
        after = pick(snaps, last, max_gap_days)
        if after is None:
            return None, f"no snapshot within {max_gap_days} days of {last}"
        if change:
            before = pick(snaps, first - _dt.timedelta(days=1), max_gap_days)
            if before and before["id"] != after["id"]:
                return {"mode": "compare", "a": before, "b": after}, f"change during {first}..{last}: {before['as_of']} vs {after['as_of']}"
        return {"mode": "single", "snap": after}, f"control as of {after['as_of']} for {first}..{last}"
    if NOW.search(text):
        s = latest(snaps)
        if s is None:
            return None, "no snapshot"
        spec = {"mode": "single", "snap": s}
        ref = reference or _dt.date.today()
        age = (ref - _date(s["as_of"])).days
        if age > stale_days:
            spec["stale"] = "may have changed since"
        return spec, f"narration speaks of now: latest snapshot {s['as_of']} ({age} days old)"
    return None, "territorial cue without a date: a line from another time is not shown"


def _sequence_for(ly: Any, rows: Sequence[Dict[str, Any]], snaps: Sequence[dict], row_carry: Dict[int, Any], cfg: Dict[str, Any]):
    """A map that stays up across several dated territorial sentences steps through their snapshots, each step landing as its date is
    spoken (map_build stretches, long CSV maps). (spec, why, first row) or None when fewer than two distinct snapshots are named."""
    chain: List[Tuple[float, dict]] = []
    first = None
    for i, r in enumerate(rows):
        if r["_end"] <= ly.start + 0.05 or r["_start"] >= ly.end - 0.05:
            continue
        sp, _ = spec_for(str(r.get("text") or ""), snaps, carried=row_carry.get(i), stale_days=int(cfg.get("stale_days", STALE_DAYS)),
                         max_gap_days=int(cfg.get("max_gap_days", MAX_GAP_DAYS)))
        if sp is None:
            continue
        first = first or r
        at = max(0.6, r["_start"] - ly.start + 0.4)
        for s in ([sp["a"], sp["b"]] if sp["mode"] == "compare" else [sp["snap"]]):
            if not chain or chain[-1][1]["id"] != s["id"]:
                chain.append((at if chain else 0.6, s))
                at += 2.6
    if len(chain) < 3 and len({c[1]["id"] for c in chain}) < 2:
        return None
    if len(chain) < 3 and first is not None and sum(1 for r in rows if r["_end"] > ly.start + 0.05 and r["_start"] < ly.end - 0.05) < 2:
        return None                                    # one sentence, two dates: an ordinary compare does it
    chain.sort(key=lambda c: c[1]["as_of"])
    times, last = [], -9.0
    for at, _ in chain:
        at = max(at, last + 2.4)
        times.append(round(at, 2))
        last = at
    if times[-1] > ly.end - ly.start - 1.0:
        return None
    spec = {"mode": "sequence", "snaps": [c[1] for c in chain], "times": times, "length": 2.2, "start": times[0]}
    return spec, "dated sentences across the map: " + " > ".join(c[1]["as_of"] for c in chain), first


def attach(plan: Any, rows: Sequence[Dict[str, Any]], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Direction post-pass: every tactical map whose narration is about territory gets the sourced front line for the dates it names.
    Never adds a map, never moves one; with no library this returns at once. Returns {attached, skipped: [...], credits: [...]}"""
    out: Dict[str, Any] = {"attached": 0, "skipped": [], "credits": [], "library": 0, "rejected_files": []}
    snaps = cfg.get("frontline_snapshots")
    if snaps is None:
        snaps, bad = load_library(cfg.get("frontline_dirs"))
        out["rejected_files"] = bad
    else:
        snaps = [normalise(s) for s in snaps if validate(s)[0]]
    out["library"] = len(snaps)
    if not snaps:
        return out
    ref = _date(cfg.get("reference_date")) if cfg.get("reference_date") else None
    rows = sorted(rows, key=lambda r: r["_start"])
    carried: Optional[Tuple[_dt.date, _dt.date]] = None
    carry_left = 0
    row_carry: Dict[int, Optional[Tuple[_dt.date, _dt.date]]] = {}
    for i, r in enumerate(rows):                      # the story's date carries to the next few sentences ("Within days, ...")
        ds = dates_in(str(r.get("text") or ""))
        if ds:
            carried, carry_left = ds[-1], 3
        elif carry_left > 0:
            carry_left -= 1
        else:
            carried = None
        row_carry[i] = carried if not ds else None
    log_by_no = {str(d.scene_no): d for d in getattr(plan, "log", [])}
    for ly in plan.layers:
        if ly.kind != "tac_map" or (ly.params or {}).get("frontline"):
            continue
        seq = _sequence_for(ly, rows, snaps, row_carry, cfg)
        if seq is not None:
            spec, why, r = seq
        else:
            idx = next((i for i, r in enumerate(rows) if r["_start"] - 0.05 <= ly.start < r["_end"]), None)
            if idx is None:
                continue
            r = rows[idx]
            spec, why = spec_for(str(r.get("text") or ""), snaps, carried=row_carry.get(idx), reference=ref,
                             stale_days=int(cfg.get("stale_days", STALE_DAYS)), max_gap_days=int(cfg.get("max_gap_days", MAX_GAP_DAYS)))
        dec = log_by_no.get(str(r.get("_no")))
        if spec is None:
            if CUE.search(str(r.get("text") or "")):
                out["skipped"].append({"scene": r.get("_no"), "why": why})
            continue
        if spec["mode"] != "sequence":
            spec["start"] = 0.6 if spec["mode"] == "single" else 1.2
            spec["length"] = 2.6
        p = dict(ly.params or {})
        p["frontline"] = spec
        if not p.get("places") and not p.get("frame"):
            bb = bbox(spec.get("b") or spec.get("snap"))
            p["frame"] = [bb[0] - 1.0, bb[1] - 0.8, bb[2] + 1.0, bb[3] + 0.8]
        ly.params = p
        out["attached"] += 1
        for c in credit_lines(spec):
            if c not in out["credits"]:
                out["credits"].append(c)
        if dec is not None:
            dec.flags.append("dir:frontline")
            dec.candidates.append({"kind": "tac_map", "score": 0.0, "reason": "frontline: " + why, "accepted": True, "start": ly.start, "end": ly.end})
    return out
