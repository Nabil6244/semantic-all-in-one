"""War Documentary situation maps: a deterministic PIL renderer on the app's own Natural Earth data (no new mapping engine, no network).

    MAP_CARDS = {"map_card": full-frame opaque map, "map_inset": small locator map on a transparent frame}

params (all optional except what you want drawn):
  frame            preset name (ukraine, ukraine_russia, black_sea, europe_east, crimea, donbas, baltic, nato_east, kharkiv_region,
                   odesa_region, kyiv_region), a bbox [lon0, lat0, lon1, lat1], or a country name; fitted to 16:9 (Mercator)
  camera           {from_frame, to_frame, start, length}: push or pull between two frames (ease in/out), ends exactly on to_frame
  style            "dark" (default) or "natural"
  fills            [{name | iso3, role: a|b|neutral|highlight, label}]       countries; a labelled fill always gets a legend row
  oblasts          [{name, iso?, role, label}]                                admin-1 areas from the app's data
  cities           [{name, lat?, lon?, note?, importance: 1..3}]              coordinates from the gazetteer when omitted; unknown skipped
  pins             [{lat, lon, label, note, start, name?}]                    drop in staggered (start defaults to 0.6 + 0.25 i)
  pulses           [{lat, lon, start}]                                        expanding location rings
  arrows           [{from: (lat, lon), to: (lat, lon), label, start, length, kind: movement|supply|trajectory, illustrative, source}]
                   trajectory is always a great-circle arc between the two named endpoints and always labelled ILLUSTRATIVE; a movement
                   or supply arrow without `source` is illustrative too
  range_rings      [{lat, lon, km, source, label}]                            drawn ONLY when `source` is non-empty
  control_snapshots [{as_of: YYYY-MM-DD, source, polygons: [[(lon, lat), ...]], role}]  rejected unless as_of and source are present;
                   no snapshot data ships with the app, so by default no control layer is drawn
  snapshot_wipe    {start, length}   wipes from the first valid snapshot to the second, left to right, both dates shown
  caption {title, sub}, as_of, legend (False | list of {label, role}), status, labels (False hides place names), graticule (bool)
The status chip (bottom left) is ILLUSTRATIVE unless a valid control snapshot is shown (then ATTRIBUTED) or `status` says otherwise.
Rivers, roads and ports are not drawn: the repo has no such data and nothing is invented.
"""

from __future__ import annotations

import datetime as _dt
import math
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import geo_data as G
from . import motion as M
from . import tokens as T
from .. import look as L

W, H = T.W, T.H
SS = 2
SOURCE_LINE = "Map data: Natural Earth (public domain). Schematic."
CRIMEA_NOTES = {
    "recognized": "Crimea is shown within Ukraine's internationally recognised borders (UN General Assembly resolution 68/262).",
    "source": "Borders are drawn as in the source data; not a statement on status.",
    "neutral": "Crimea is shown without a border affiliation.",
}

_STYLES = {
    "dark": {"water": T.WATER, "land": T.LAND, "border": T.BORDER, "grat": (30, 44, 62, 255), "vig": 0.55},
    "natural": {"water": (30, 54, 80, 255), "land": (82, 92, 76, 255), "border": (150, 152, 132, 255), "grat": (40, 66, 92, 255),
                "vig": 0.35},
}
ROLE_FILL = {"a": T.FILL_A, "b": T.FILL_B, "neutral": T.FILL_NEUTRAL, "highlight": (128, 110, 66, 255)}
ROLE_OUTLINE = {"a": (214, 150, 140, 255), "b": (150, 186, 224, 255), "neutral": (170, 176, 184, 255), "highlight": T.AMBER}
HALO = (8, 10, 14, 255)


# ================================================================================================================ view / camera
class View:
    """Mercator view: centre (radians), half width (radians), pixel size."""

    def __init__(self, cx: float, cy: float, hw: float, w: int, h: int):
        self.cx, self.cy, self.hw, self.w, self.h = cx, cy, hw, w, h
        self.hh = hw * h / w

    def key(self) -> tuple:
        return (round(self.cx, 7), round(self.cy, 7), round(self.hw, 7), self.w, self.h)

    @property
    def lon_left(self) -> float:
        return math.degrees(self.cx - self.hw)

    @property
    def lon_span(self) -> float:
        return math.degrees(2 * self.hw)

    def bounds(self) -> G.BBox:
        return (self.lon_left, G.unmerc(self.cy - self.hh), self.lon_left + self.lon_span, G.unmerc(self.cy + self.hh))

    def px(self, lon, ym, scale: float = 1.0):
        x = (np.asarray(lon) - self.lon_left) / self.lon_span * self.w * scale
        y = ((self.cy + self.hh) - np.asarray(ym)) / (2 * self.hh) * self.h * scale
        return x, y

    def pt(self, lat: float, lon: float, scale: float = 1.0) -> Tuple[float, float]:
        x, y = self.px(lon, G.merc(lat), scale)
        return float(x), float(y)

    def contains(self, lat: float, lon: float, pad: float = 0.0) -> bool:
        x, y = self.pt(lat, lon)
        return -pad <= x <= self.w + pad and -pad <= y <= self.h + pad


def _frame_bbox(frame: Any, warnings: List[str]) -> G.BBox:
    if isinstance(frame, dict):
        frame = frame.get("bbox") or frame.get("region") or frame.get("name")
    if isinstance(frame, (list, tuple)) and len(frame) == 4:
        try:
            a = tuple(float(x) for x in frame)
            if a[0] < a[2] and a[1] < a[3]:
                return a  # type: ignore[return-value]
        except (TypeError, ValueError):
            pass
    elif isinstance(frame, str) and frame.strip():
        bb = G.preset_bbox(frame)
        if bb:
            return bb
        f = G.find_country(frame)
        if f is not None:
            areas = [(p[0].bbox[2] - p[0].bbox[0]) * (p[0].bbox[3] - p[0].bbox[1]) for p in f.polys]
            top = max(areas)
            bs = [p[0].bbox for p, a in zip(f.polys, areas) if a >= top * 0.1]
            return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
        warnings.append(f"unknown frame: {frame}")
    elif frame is not None:
        warnings.append("unusable frame")
    return G.PRESETS["ukraine"]


def view_for(frame: Any, size: Tuple[int, int] = (W, H), warnings: Optional[List[str]] = None, pad: float = 1.06) -> View:
    warn = warnings if warnings is not None else []
    lon0, lat0, lon1, lat1 = _frame_bbox(frame, warn)
    w, h = size
    cx = math.radians((lon0 + lon1) / 2)
    y0, y1 = G.merc(lat0), G.merc(lat1)
    cy = (y0 + y1) / 2
    hw = max(math.radians(lon1 - lon0) / 2 * pad, (y1 - y0) / 2 * pad * w / h)
    return View(cx, cy, hw, w, h)


def camera_view(params: dict, t: float, size: Tuple[int, int], warnings: List[str]) -> View:
    cam = params.get("camera")
    if isinstance(cam, dict) and cam.get("to_frame") is not None:
        a = view_for(cam.get("from_frame", params.get("frame")), size, warnings)
        b = view_for(cam["to_frame"], size, warnings)
        k = M.ease_in_out(M.ramp(t, float(cam.get("start", 0.0)), float(cam.get("length", T.CAMERA_S))))
        if k <= 0:
            return a
        if k >= 1:
            return b
        return View(M.lerp(a.cx, b.cx, k), M.lerp(a.cy, b.cy, k), math.exp(M.lerp(math.log(a.hw), math.log(b.hw), k)), size[0], size[1])
    return view_for(params.get("frame") if params.get("frame") is not None else "ukraine", size, warnings)


# ================================================================================================================ text helpers
def _text(d: ImageDraw.ImageDraw, xy, text: str, font, fill, halo: bool = True):
    d.text(xy, text, font=font, fill=fill, stroke_width=2 if halo else 0, stroke_fill=HALO)


def _tbox(d: ImageDraw.ImageDraw, xy, text: str, font, halo: bool = True) -> Tuple[int, int, int, int]:
    return d.textbbox(xy, text, font=font, stroke_width=2 if halo else 0)


def _wrap(d: ImageDraw.ImageDraw, text: str, font, width: int) -> List[str]:
    lines, cur = [], ""
    for w in str(text).split():
        trial = (cur + " " + w).strip()
        if cur and d.textlength(trial, font=font) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


class Placer:
    """Greedy label placement: a rectangle is taken only if it is free and inside the safe box."""

    def __init__(self, safe: Tuple[int, int, int, int], reserved: Sequence[Tuple[int, int, int, int]] = ()):
        self.safe = safe
        self.rects = list(reserved)
        self.placed: List[Tuple[str, Tuple[int, int, int, int]]] = []

    @staticmethod
    def _hit(a, b) -> bool:
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    def free(self, r) -> bool:
        s = self.safe
        if r[0] < s[0] or r[1] < s[1] or r[2] > s[2] or r[3] > s[3]:
            return False
        return not any(self._hit(r, o) for o in self.rects)

    def take(self, text: str, r) -> None:
        self.rects.append(r)
        self.placed.append((text, r))

    def first_free(self, cands):
        for r in cands:
            r = tuple(int(round(v)) for v in r)
            if self.free(r):
                return r
        return None


def _side_candidates(ax: float, ay: float, w: int, h: int, gap: float):
    return [(ax + gap, ay - h / 2, ax + gap + w, ay + h / 2), (ax - gap - w, ay - h / 2, ax - gap, ay + h / 2),
            (ax - w / 2, ay - gap - h, ax + w / 2, ay - gap), (ax - w / 2, ay + gap, ax + w / 2, ay + gap + h),
            (ax + gap, ay - gap - h, ax + gap + w, ay - gap), (ax - gap - w, ay + gap, ax - gap, ay + gap + h),
            (ax + gap, ay + gap, ax + gap + w, ay + gap + h), (ax - gap - w, ay - gap - h, ax - gap, ay - gap)]


# ================================================================================================================ polygons
def _poly(d: ImageDraw.ImageDraw, pts, fill, outline=None, width: int = 1) -> None:
    try:
        d.polygon(pts, fill=fill, outline=outline, width=width)
    except TypeError:
        d.polygon(pts, fill=fill, outline=outline)


def _ring_pts(ring: G.Ring, view: View, scale: float) -> Optional[List[Tuple[int, int]]]:
    x, y = view.px(ring.lon, ring.ym, scale)
    q = np.clip(np.stack([x, y], axis=1), -30000, 30000)
    q = np.round(q).astype(np.int32)
    keep = np.ones(len(q), dtype=bool)
    keep[1:] = np.any(q[1:] != q[:-1], axis=1)
    q = q[keep]
    if len(q) < 3:
        return None
    return [tuple(p) for p in q.tolist()]


def _intersects(bb: G.BBox, vb: G.BBox) -> bool:
    return not (bb[2] < vb[0] or bb[0] > vb[2] or bb[3] < vb[1] or bb[1] > vb[3])


def _in_crimea(b: G.BBox) -> bool:
    return b[0] >= 32.0 and b[2] <= 37.0 and b[1] >= 44.0 and b[3] <= 46.3


def _draw_feature(d: ImageDraw.ImageDraw, feat: G.Feature, view: View, vb: G.BBox, fill, outline, hole_fill, scale: float,
                  width: int = 1, only=None) -> None:
    if not _intersects(feat.bbox, vb):
        return
    for outer, holes in feat.polys:
        if not _intersects(outer.bbox, vb):
            continue
        if only is not None and not only(outer.bbox):
            continue
        pts = _ring_pts(outer, view, scale)
        if pts:
            _poly(d, pts, fill, outline, width)
        for h in holes:
            if _intersects(h.bbox, vb):
                hp = _ring_pts(h, view, scale)
                if hp:
                    _poly(d, hp, hole_fill, None)


# ================================================================================================================ static base (cached)
_BASE_CACHE: "OrderedDict[tuple, Tuple[Image.Image, Optional[Image.Image]]]" = OrderedDict()
_BASE_MAX = 8
_VIG: Dict[Tuple[int, int, float], Image.Image] = {}


def _vignette(size: Tuple[int, int], strength: float) -> Image.Image:
    key = (size[0], size[1], strength)
    if key not in _VIG:
        w, h = size
        small = Image.new("L", (64, 36), 0)
        px = small.load()
        for j in range(36):
            for i in range(64):
                dx, dy = (i - 31.5) / 31.5, (j - 17.5) / 17.5
                r = min(1.0, math.sqrt(dx * dx * 0.7 + dy * dy * 0.9))
                px[i, j] = int(255 * strength * max(0.0, r - 0.45) / 0.55) if r > 0.45 else 0
        _VIG[key] = small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
    return _VIG[key]


def _fills_sig(fills: List[dict], oblasts: List[dict], crimea: str = "recognized") -> tuple:
    return (crimea, tuple((str(f.get("iso3") or f.get("iso") or f.get("name")), f.get("role", "neutral")) for f in fills),
            tuple((str(o.get("name")), str(o.get("iso", "")), o.get("role", "neutral")) for o in oblasts))


def _graticule(d: ImageDraw.ImageDraw, view: View, color, scale: float, width: int = SS) -> None:
    lo0, la0, lo1, la1 = view.bounds()
    span = lo1 - lo0
    step = 10 if span > 40 else 5 if span > 15 else 2 if span > 6 else 1
    lon = math.floor(lo0 / step) * step
    while lon <= lo1:
        x, _ = view.px(lon, 0.0, scale)
        d.line([(float(x), 0), (float(x), view.h * scale)], fill=color, width=width)
        lon += step
    lat = math.floor(la0 / step) * step
    while lat <= la1:
        _, y = view.px(0.0, G.merc(lat), scale)
        d.line([(0, float(y)), (view.w * scale, float(y))], fill=color, width=width)
        lat += step


def _base(view: View, style: str, fills: List[dict], oblasts: List[dict], grat: bool, warnings: List[str], crimea: str = "recognized", ss: int = SS):
    """(plain, filled): the map without and with role fills, both at final size, vignette applied. Cached per view/style/fills."""
    key = (view.key(), style, _fills_sig(fills, oblasts, crimea), grat, ss)
    hit = _BASE_CACHE.get(key)
    if hit is not None:
        _BASE_CACHE.move_to_end(key)
        return hit
    st = _STYLES.get(style, _STYLES["dark"])
    vb = view.bounds()
    # a little outside the view so rings that straddle the edge still intersect
    vb = (vb[0] - 0.5, vb[1] - 0.5, vb[2] + 0.5, vb[3] + 0.5)
    big = Image.new("RGBA", (view.w * ss, view.h * ss), st["water"])
    d = ImageDraw.Draw(big)
    if grat:
        _graticule(d, view, st["grat"], ss, ss)
    for f in G.countries():
        _draw_feature(d, f, view, vb, st["land"], st["border"], st["water"], ss)
    plain = big.reduce(ss).convert("RGB")
    filled: Optional[Image.Image] = None
    if fills or oblasts:
        d = ImageDraw.Draw(big)
        for fl in fills:
            key_ = fl.get("iso3") or fl.get("iso") or fl.get("name")
            feat = G.find_country(str(key_)) if key_ else None
            if feat is None:
                warnings.append(f"unknown country: {key_}")
                continue
            role = fl.get("role", "neutral")
            _draw_feature(d, feat, view, vb, ROLE_FILL.get(role, T.FILL_NEUTRAL), ROLE_OUTLINE.get(role, st["border"]), st["water"], ss)
        if crimea != "source" and _in_view_crimea(vb):
            roles = _fill_roles(fills)
            rus = G.find_country("RUS")
            colour, edge = None, st["border"]
            if crimea == "neutral":
                colour = T.FILL_NEUTRAL
            elif "UKR" in roles:
                colour, edge = ROLE_FILL.get(roles["UKR"], T.FILL_NEUTRAL), ROLE_OUTLINE.get(roles["UKR"], st["border"])
            elif "RUS" in roles:
                colour = st["land"]
            if colour is not None and rus is not None:
                _draw_feature(d, rus, view, vb, colour, edge, st["water"], ss, only=_in_crimea)
        if oblasts:
            ov = Image.new("RGBA", big.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for ob in oblasts:
                feat = G.find_oblast(str(ob.get("name", "")), str(ob.get("iso", "")))
                if feat is None:
                    warnings.append(f"unknown oblast: {ob.get('name')}")
                    continue
                role = ob.get("role", "neutral")
                c = ROLE_FILL.get(role, T.FILL_NEUTRAL)
                _draw_feature(od, feat, view, vb, c[:3] + (215,), ROLE_OUTLINE.get(role, st["border"]), (0, 0, 0, 0), ss, ss)
            big = Image.alpha_composite(big, ov)
        filled = big.reduce(ss).convert("RGB")
    vig = _vignette((view.w, view.h), st["vig"])
    black = Image.new("RGB", (view.w, view.h), (0, 0, 0))
    plain = Image.composite(black, plain, vig)
    if filled is not None:
        filled = Image.composite(black, filled, vig)
    _BASE_CACHE[key] = (plain, filled)
    while len(_BASE_CACHE) > _BASE_MAX:
        _BASE_CACHE.popitem(last=False)
    return plain, filled


def _fill_roles(fills: List[dict]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for f_ in fills:
        key_ = f_.get("iso3") or f_.get("iso") or f_.get("name")
        feat = G.find_country(str(key_)) if key_ else None
        if feat is not None:
            out[feat.iso] = f_.get("role", "neutral")
    return out


def _in_view_crimea(vb: G.BBox) -> bool:
    return _intersects((32.0, 44.0, 37.0, 46.3), vb)


def clear_cache() -> None:
    _BASE_CACHE.clear()


# ================================================================================================================ dynamic parts
def validate_snapshot(s: Any) -> Tuple[bool, str]:
    """A control snapshot is drawn only with a real date, a named source and at least one ring of 3+ (lon, lat) points."""
    if not isinstance(s, dict):
        return False, "not a snapshot"
    try:
        _dt.date.fromisoformat(str(s.get("as_of", ""))[:10] if len(str(s.get("as_of", ""))) >= 10 else str(s.get("as_of", "")) + "-01")
    except ValueError:
        return False, "missing or invalid as_of"
    if not str(s.get("source") or "").strip():
        return False, "missing source"
    rings = s.get("polygons") or []
    if not rings or not all(isinstance(r, (list, tuple)) and len(r) >= 3 for r in rings):
        return False, "no usable polygon"
    return True, ""


def _date_label(as_of: str) -> str:
    try:
        d = _dt.date.fromisoformat(as_of[:10]) if len(as_of) >= 10 else _dt.date.fromisoformat(as_of + "-01")
        return d.strftime("%d %b %Y").upper() if len(as_of) >= 10 else d.strftime("%b %Y").upper()
    except ValueError:
        return as_of.upper()


def _curve(a: Tuple[float, float], b: Tuple[float, float], bend: float = 0.14, n: int = 36) -> List[Tuple[float, float]]:
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    cx, cy = mx - dy * bend, my + dx * bend
    pts = []
    for i in range(n + 1):
        f = i / n
        pts.append(((1 - f) ** 2 * a[0] + 2 * (1 - f) * f * cx + f * f * b[0], (1 - f) ** 2 * a[1] + 2 * (1 - f) * f * cy + f * f * b[1]))
    return pts


def _dashes(pts: Sequence[Tuple[float, float]], dash: float, gap: float) -> List[List[Tuple[float, float]]]:
    out, cur, acc, on = [], [pts[0]], 0.0, True
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while pos < seg:
            lim = (dash if on else gap) - acc
            step = min(lim, seg - pos)
            pos += step
            acc += step
            px, py = x0 + (x1 - x0) * pos / seg, y0 + (y1 - y0) * pos / seg
            if on:
                cur.append((px, py))
            if acc >= (dash if on else gap) - 1e-6:
                if on and len(cur) > 1:
                    out.append(cur)
                on, acc = not on, 0.0
                cur = [(px, py)]
    if on and len(cur) > 1:
        out.append(cur)
    return out


def _arrow_head(d: ImageDraw.ImageDraw, tip: Tuple[float, float], prev: Tuple[float, float], size: float, color) -> None:
    ang = math.atan2(tip[1] - prev[1], tip[0] - prev[0])
    p1 = (tip[0] - size * math.cos(ang - 0.45), tip[1] - size * math.sin(ang - 0.45))
    p2 = (tip[0] - size * math.cos(ang + 0.45), tip[1] - size * math.sin(ang + 0.45))
    d.polygon([tip, p1, p2], fill=color)


def _chip(d: ImageDraw.ImageDraw, x: int, y: int, text: str, color, size: int = 13) -> Tuple[int, int, int, int]:
    f = T.font("bold", size)
    w = int(L.spaced_width(d, text, f, 0.1)) + 18
    h = size + 12
    d.rectangle([x, y, x + w, y + h], fill=(10, 12, 16, 235), outline=color, width=2)
    L.spaced(d, (x + 9, y + 5), text, f, color, 0.1)
    return (x, y, x + w, y + h)


# ================================================================================================================ the renderer
def _core(params: dict, t: float, dur: float, size: Tuple[int, int], inset: bool = False) -> Tuple[Image.Image, dict]:
    w, h = size
    k = w / W
    info: Dict[str, Any] = {"warnings": [], "labels": [], "chips": [], "rings_drawn": 0, "rings_skipped": 0, "snapshots_drawn": 0,
                            "snapshots_rejected": [], "pins": 0, "cities": 0, "unresolved": []}
    warn: List[str] = info["warnings"]
    style = params.get("style", "dark")
    view = camera_view(params, t, size, warn)
    info["view"] = view.key()
    fills = [f for f in (params.get("fills") or []) if isinstance(f, dict)]
    oblasts = [o for o in (params.get("oblasts") or []) if isinstance(o, dict)]
    crimea = str(params.get("crimea", "recognized"))
    crimea = crimea if crimea in ("recognized", "source", "neutral") else "recognized"
    cam = params.get("camera")
    moving = isinstance(cam, dict) and cam.get("to_frame") is not None and 0 < M.ramp(t, float(cam.get("start", 0.0)), float(cam.get("length", T.CAMERA_S))) < 1
    plain, filled = _base(view, style, fills, oblasts, bool(params.get("graticule", True)), warn, crimea, 1 if moving else SS)
    img = plain
    if filled is not None:
        kf = M.ease_out(M.ramp(t, float(params.get("fills_start", 0.3)), 0.6))
        img = filled if kf >= 1 else (plain if kf <= 0 else Image.blend(plain, filled, kf))
    img = img.convert("RGBA")

    # ---- snapshots, rings, arrows, pulses on a 2x overlay
    ov = None
    od = None

    def overlay():
        nonlocal ov, od
        if ov is None:
            ov = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
        return od

    snaps = []
    for i, s in enumerate(params.get("control_snapshots") or []):
        ok, why = validate_snapshot(s)
        if ok:
            snaps.append(s)
        else:
            info["snapshots_rejected"].append((i, why))
    wipe = params.get("snapshot_wipe") if isinstance(params.get("snapshot_wipe"), dict) else None
    snap_chips: List[str] = []
    if snaps and not inset:
        def paint(s, alpha, clip_x=None):
            layer = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            role = s.get("role", "a")
            c = ROLE_FILL.get(role, T.FILL_A)
            for ring in s["polygons"]:
                a = np.asarray(ring, dtype=np.float64)
                x, y = view.px(a[:, 0], G.merc(a[:, 1]), SS)
                pts = [(float(px_), float(py_)) for px_, py_ in zip(x, y)]
                _poly(ld, pts, c[:3] + (alpha,), ROLE_OUTLINE.get(role, T.BORDER), 2)
            if clip_x is not None:
                cut = Image.new("RGBA", layer.size, (0, 0, 0, 0))
                cut.paste(layer.crop((0, 0, int(clip_x * SS), h * SS)), (0, 0))
                layer = cut
            return layer

        first = snaps[0]
        fa = int(150 * M.ease_out(M.ramp(t, 0.4, 0.5)))
        layers_ = [paint(first, fa)]
        snap_chips.append(f"AS OF {_date_label(str(first['as_of']))} · {first['source']}")
        if len(snaps) >= 2 and wipe:
            frac = M.ease_in_out(M.ramp(t, float(wipe.get("start", 1.5)), float(wipe.get("length", 1.2))))
            if frac > 0:
                layers_.append(paint(snaps[1], 150, clip_x=frac * w))
                snap_chips.append(f"AS OF {_date_label(str(snaps[1]['as_of']))} · {snaps[1]['source']}")
        o = overlay()
        for lay in layers_:
            ov.alpha_composite(lay)  # type: ignore[union-attr]
        info["snapshots_drawn"] = len(snap_chips)

    ring_labels: List[Tuple[str, Tuple[float, float]]] = []
    for rg in params.get("range_rings") or []:
        if not (isinstance(rg, dict) and str(rg.get("source") or "").strip() and float(rg.get("km") or 0) > 0):
            info["rings_skipped"] += 1
            continue
        pts_ll = G.geodesic_circle(float(rg["lat"]), float(rg["lon"]), float(rg["km"]) * M.draw_fraction(t, float(rg.get("start", 0.5)), 0.9))
        a = np.asarray(pts_ll)
        x, y = view.px(a[:, 0], G.merc(a[:, 1]), SS)
        pts = [(float(px_), float(py_)) for px_, py_ in zip(x, y)]
        o = overlay()
        _poly(o, pts, T.AMBER[:3] + (36,), T.AMBER[:3] + (210,), 2)
        info["rings_drawn"] += 1
        if M.ramp(t, float(rg.get("start", 0.5)), 0.9) >= 1:
            east = view.pt(float(rg["lat"]), float(rg["lon"]) + float(rg["km"]) / (111.32 * max(0.2, math.cos(math.radians(float(rg["lat"]))))))
            ring_labels.append((str(rg.get("label") or f"{float(rg['km']):g} km") + " · " + str(rg["source"]), east))

    arrow_labels: List[Tuple[str, Tuple[float, float], bool]] = []
    arrow_chips: List[Tuple[float, float]] = []
    for i, ar in enumerate(params.get("arrows") or []):
        try:
            a_ll, b_ll = tuple(ar["from"]), tuple(ar["to"])
            lat_a, lon_a, lat_b, lon_b = float(a_ll[0]), float(a_ll[1]), float(b_ll[0]), float(b_ll[1])
        except (KeyError, TypeError, ValueError, IndexError):
            warn.append(f"arrow {i} skipped: unusable endpoints")
            continue
        kind = ar.get("kind", "movement")
        illustrative = bool(ar.get("illustrative", True)) or kind == "trajectory" or not str(ar.get("source") or "").strip()
        if kind == "trajectory":
            ll = G.great_circle((lat_a, lon_a), (lat_b, lon_b), 48)
            xy = [view.pt(la, lo, SS) for lo, la in ll]
        else:
            xy = _curve(view.pt(lat_a, lon_a, SS), view.pt(lat_b, lon_b, SS))
        frac = M.draw_fraction(t, float(ar.get("start", 0.8 + 0.4 * i)), float(ar.get("length", 1.4)))
        if frac <= 0:
            continue
        part = M.partial_polyline(xy, frac)
        if len(part) < 2:
            continue
        o = overlay()
        col = T.AMBER if kind == "trajectory" else T.CREAM if kind == "movement" else T.SAND
        lw = int((6 if kind == "movement" else 4) * k * SS)
        lw = max(lw, 2)
        if kind == "supply":
            for seg in _dashes(part, 22 * SS * k, 14 * SS * k):
                o.line(seg, fill=col, width=lw, joint="curve")
        elif kind == "trajectory":
            for seg in _dashes(part, 2 * SS * k, 12 * SS * k):
                o.line(seg, fill=col, width=lw + 2 * SS)
        else:
            o.line(part, fill=col, width=lw, joint="curve")
        if frac > 0.02 and len(part) >= 2:
            _arrow_head(o, part[-1], part[-2] if len(part) > 2 else part[0], 18 * SS * k, col)
        mid = M.point_on_polyline(xy, 0.5)
        if ar.get("label") and frac >= 0.6:
            arrow_labels.append((str(ar["label"]), (mid[0] / SS, mid[1] / SS), illustrative))
        elif illustrative and frac >= 0.6:
            arrow_labels.append(("", (mid[0] / SS, mid[1] / SS), True))

    for pu in params.get("pulses") or []:
        try:
            lat, lon, st_ = float(pu["lat"]), float(pu["lon"]), float(pu.get("start", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if t < st_:
            continue
        cx, cy = view.pt(lat, lon, SS)
        o = overlay()
        for off in (0.0, 0.5):
            sc, al = M.pulse(t - st_ + off * T.PULSE_S)
            r = 9 * sc * SS * k
            o.ellipse([cx - r, cy - r, cx + r, cy + r], outline=T.AMBER[:3] + (int(200 * al),), width=max(2, int(2 * SS * k)))
    if ov is not None:
        img = Image.alpha_composite(img, ov.reduce(SS))

    # ---- text layer at 1x
    d = ImageDraw.Draw(img)
    safe = (T.MARGIN_X, T.MARGIN_Y, w - T.MARGIN_X, T.LOWER_ZONE_Y) if not inset else (6, 6, w - 6, h - 6)
    reserved: List[Tuple[int, int, int, int]] = []

    caption = params.get("caption") if isinstance(params.get("caption"), dict) else None
    status = str(params.get("status") or ("attributed" if info["snapshots_drawn"] else "illustrative")).lower()
    status = status if status in T.STATUSES else "unverified"
    info["status"] = status
    panel = None
    if caption and not inset:
        ft, fs, fk = T.font("display", 36), T.font("regular", 15), T.font("bold", 12)
        tw = 380
        sub_lines = _wrap(d, caption.get("sub", ""), fs, tw - 32)
        title = str(caption.get("title", "")).upper()
        kick = str(params.get("as_of") and f"AS OF {_date_label(str(params['as_of']))}" or "SITUATION MAP")
        ph = 20 + 16 + 44 + 8 + 20 * len(sub_lines) + 14
        py1 = int(H * 0.84)
        px1 = safe[2] if str(params.get("panel", "br")) != "bl" else safe[0] + tw
        panel = (px1 - tw, py1 - ph, px1, py1)
        reserved.append(panel)
    legend_rows: List[Tuple[str, str]] = []
    if not inset and params.get("legend", True) is not False:
        if isinstance(params.get("legend"), list):
            legend_rows = [(str(r.get("label", "")), r.get("role", "neutral")) for r in params["legend"] if isinstance(r, dict)]
        else:
            seen = set()
            for f_ in fills + oblasts:
                lab, role = f_.get("label"), f_.get("role", "neutral")
                if lab and (lab, role) not in seen:
                    seen.add((lab, role))
                    legend_rows.append((str(lab), role))
    leg_rect = None
    if legend_rows:
        fl = T.font("regular", 14)
        lw_ = max(int(d.textlength(r[0], font=fl)) for r in legend_rows) + 46
        lh_ = 16 + 26 * len(legend_rows)
        leg_rect = (safe[2] - lw_, safe[1], safe[2], safe[1] + lh_)
        reserved.append(leg_rect)
    chip_y = int(H * 0.80) if not inset else h - 28
    chip_text = T.STATUS_LABEL[status]
    chip_rect = None
    if not inset:
        chip_rect = ((safe[0] if str(params.get("panel", "br")) != "bl" else safe[2] - 140), chip_y, safe[0] + int(L.spaced_width(d, chip_text, T.font("bold", 13), 0.1)) + 18, chip_y + 25)
        reserved.append(chip_rect)
    snap_rects = []
    for i, txt in enumerate(snap_chips):
        fb = T.font("bold", 12)
        wd = int(L.spaced_width(d, txt, fb, 0.08)) + 18
        r = (safe[0], safe[1] + i * 30, safe[0] + wd, safe[1] + i * 30 + 24)
        snap_rects.append((txt, r))
        reserved.append(r)
    src_lines = [SOURCE_LINE]
    if view.contains(45.3, 34.5) and not inset:
        src_lines.insert(0, CRIMEA_NOTES[crimea])
    fsrc = T.font("regular", 11)
    src_rect = None
    if not inset:
        sw = max(int(d.textlength(x, font=fsrc)) for x in src_lines)
        src_rect = (safe[2] - sw, H - 14 - 16 * len(src_lines), safe[2], H - 12)
        reserved.append(src_rect)

    placer = Placer(safe, reserved)
    pin_font, note_font = T.font("display", max(12, int(22 * k))), T.font("regular", max(9, int(12 * k)))

    # pins first (highest priority)
    pins = [p for p in (params.get("pins") or []) if isinstance(p, dict)]
    for i, p in enumerate(pins):
        try:
            lat, lon = float(p["lat"]), float(p["lon"])
        except (KeyError, TypeError, ValueError):
            if p.get("name") and G.gazetteer(str(p["name"])):
                lat, lon = G.gazetteer(str(p["name"]))  # type: ignore[misc]
            else:
                info["unresolved"].append(str(p.get("label") or p.get("name") or i))
                continue
        st_ = float(p.get("start", 0.6 + 0.25 * i))
        kk = M.ramp(t, st_, 0.3)
        if kk <= 0:
            continue
        ax, ay = view.pt(lat, lon)
        if not (0 <= ax <= w and 0 <= ay <= h):
            continue
        drop = 18 * (1 - M.ease_out(kk)) * k
        r = 6 * k
        cy = ay - drop
        d.ellipse([ax - r - 2, cy - r - 2, ax + r + 2, cy + r + 2], fill=(8, 10, 14, 230))
        d.ellipse([ax - r, cy - r, ax + r, cy + r], fill=T.RED, outline=T.CREAM, width=max(1, int(2 * k)))
        info["pins"] += 1
        label = str(p.get("label") or p.get("name") or "").upper()
        note = str(p.get("note") or "")
        if label and kk >= 1:
            tb = _tbox(d, (0, 0), label, pin_font)
            lw0, lh0 = tb[2] - tb[0], tb[3] - tb[1]
            nb = _tbox(d, (0, 0), note, note_font) if note else (0, 0, 0, 0)
            bw, bh = max(lw0, nb[2] - nb[0]) + 4, lh0 + (nb[3] - nb[1] + 4 if note else 0) + 4
            rect = placer.first_free(_side_candidates(ax, ay, bw, bh, r + 8)) or (
                placer.first_free(_side_candidates(ax, ay, lw0 + 4, lh0 + 4, r + 8)) if note else None)
            if rect:
                note_ok = note and (rect[3] - rect[1]) >= bh - 1
                placer.take(label, rect)
                _text(d, (rect[0] + 2 - tb[0], rect[1] + 2 - tb[1]), label, pin_font, T.CREAM)
                if note_ok:
                    _text(d, (rect[0] + 2, rect[1] + 2 + lh0 + 2 - nb[1]), note, note_font, T.CREAM_DIM)
            else:
                warn.append(f"label dropped: {label}")

    # cities
    cities = [c for c in (params.get("cities") or []) if isinstance(c, dict)]
    cities.sort(key=lambda c: -int(c.get("importance", 1)))
    for c in cities:
        name = str(c.get("name", ""))
        if "lat" in c and "lon" in c:
            try:
                lat, lon = float(c["lat"]), float(c["lon"])
            except (TypeError, ValueError):
                info["unresolved"].append(name)
                continue
        else:
            ll = G.gazetteer(name)
            if ll is None:
                info["unresolved"].append(name)
                continue
            lat, lon = ll
        ax, ay = view.pt(lat, lon)
        if not (4 <= ax <= w - 4 and 4 <= ay <= h - 4):
            continue
        imp = max(1, min(3, int(c.get("importance", 1))))
        fnt = T.font("display", max(11, int((14 + 3 * imp) * k)))
        label = name.upper()
        tb = _tbox(d, (0, 0), label, fnt)
        bw, bh = tb[2] - tb[0] + 4, tb[3] - tb[1] + 4
        nb = _tbox(d, (0, 0), str(c.get("note", "")), note_font) if c.get("note") else None
        rect = placer.first_free(_side_candidates(ax, ay, bw, bh, 7 * k + 2))
        if rect is None:
            continue
        placer.take(label, rect)
        r = (2 + imp) * k
        d.ellipse([ax - r, ay - r, ax + r, ay + r], fill=T.CREAM, outline=HALO)
        _text(d, (rect[0] + 2 - tb[0], rect[1] + 2 - tb[1]), label, fnt, T.CREAM)
        info["cities"] += 1
        del nb

    # range ring labels
    for text, (ax, ay) in ring_labels:
        fa = T.font("bold", max(10, int(12 * k)))
        tb = _tbox(d, (0, 0), text, fa)
        rect = placer.first_free(_side_candidates(ax, ay, tb[2] - tb[0] + 4, tb[3] - tb[1] + 4, 6 * k))
        if rect:
            placer.take(text, rect)
            _text(d, (rect[0] + 2 - tb[0], rect[1] + 2 - tb[1]), text, fa, T.AMBER)

    # arrow labels
    for text, (ax, ay), illus in arrow_labels:
        fa = T.font("bold", max(11, int(13 * k)))
        if text:
            tb = _tbox(d, (0, 0), text, fa)
            bw, bh = tb[2] - tb[0] + 4, tb[3] - tb[1] + 4
            rect = placer.first_free(_side_candidates(ax, ay, bw, bh, 8 * k)[2:4] + _side_candidates(ax, ay, bw, bh, 8 * k)[:2])
            if rect:
                placer.take(text, rect)
                _text(d, (rect[0] + 2 - tb[0], rect[1] + 2 - tb[1]), text, fa, T.CREAM)
        if illus and not inset:
            cw = int(L.spaced_width(d, "ILLUSTRATIVE", T.font("bold", 11), 0.08)) + 14
            ry = int(ay + (22 if text else 10))
            rect = placer.first_free([(ax - cw / 2, ry, ax + cw / 2, ry + 20), (ax - cw / 2, ay - 34, ax + cw / 2, ay - 14)])
            if rect:
                placer.take("ILLUSTRATIVE", rect)
                d.rectangle(rect, fill=(10, 12, 16, 230), outline=T.STATUS_COLOUR["illustrative"], width=1)
                L.spaced(d, (rect[0] + 7, rect[1] + 4), "ILLUSTRATIVE", T.font("bold", 11), T.STATUS_COLOUR["illustrative"], 0.08)
                info["chips"].append("ILLUSTRATIVE")

    # fill / oblast names and country names (lowest priority)
    if params.get("labels", True) is not False:
        filled_iso = set(_fill_roles(fills))
        cam_ = params.get("camera")
        anchor_view = view_for(cam_["to_frame"], size) if isinstance(cam_, dict) and cam_.get("to_frame") is not None else view
        city_norms = {G._norm(str(c_.get("name", ""))) for c_ in cities}
        named: List[Tuple[str, Tuple[float, float], Any, int]] = []
        for ob in oblasts:
            feat = G.find_oblast(str(ob.get("name", "")), str(ob.get("iso", "")))
            if feat is not None and ob.get("show_name", True) and G._norm(feat.name) not in city_norms:
                named.append((feat.name.replace("'", "").upper(), _visible_center(feat, view, anchor_view), T.CREAM, 13))
        if not inset or params.get("country_names", True):
            vb = view.bounds()
            for f in G.countries():
                if not _intersects(f.bbox, vb):
                    continue
                c = _visible_center(f, view, anchor_view)
                if c is None:
                    continue
                if (f.bbox[2] - f.bbox[0]) / view.lon_span * view.w < 46 * k and f.iso not in filled_iso:
                    continue   # too small to carry its name legibly at this zoom
                named.append((f.name.upper(), c, T.CREAM if f.iso in filled_iso else (150, 158, 168, 255), 12))
        for text, c, col, size in named:
            if c is None:
                continue
            fnt = T.font("display", max(10, int(size * k * 1.15)))
            wd = int(L.spaced_width(d, text, fnt, 0.14))
            ht = fnt.size + 2
            rect = placer.first_free([(c[0] - wd / 2 + dx, c[1] - ht / 2 + dy, c[0] + wd / 2 + dx, c[1] + ht / 2 + dy)
                                      for dx, dy in ((0, 0), (0, -16), (0, 16), (-24, 0), (24, 0))])
            if rect:
                placer.take(text, rect)
                L.spaced(d, (rect[0], rect[1]), text, fnt, col, 0.14)

    # panels, legend, chips, source (on top)
    if panel:
        d.rectangle(panel, fill=(8, 10, 14, 238))
        d.rectangle([panel[0], panel[1], panel[0] + 4, panel[3]], fill=T.AMBER)
        L.spaced(d, (panel[0] + 18, panel[1] + 14), kick, fk, T.AMBER, 0.12)
        d.text((panel[0] + 18, panel[1] + 30), title, font=ft, fill=T.CREAM)
        for i, ln in enumerate(sub_lines):
            d.text((panel[0] + 18, panel[1] + 30 + 46 + 4 + 20 * i), ln, font=fs, fill=T.CREAM_DIM)
        info["labels"].append((title, panel))
    if leg_rect:
        d.rectangle(leg_rect, fill=(8, 10, 14, 225))
        for i, (lab, role) in enumerate(legend_rows):
            y0 = leg_rect[1] + 10 + 26 * i
            d.rectangle([leg_rect[0] + 10, y0 + 2, leg_rect[0] + 28, y0 + 18], fill=ROLE_FILL.get(role, T.FILL_NEUTRAL),
                        outline=ROLE_OUTLINE.get(role, T.BORDER))
            d.text((leg_rect[0] + 36, y0), lab, font=T.font("regular", 14), fill=T.CREAM)
    if chip_rect:
        _chip(d, chip_rect[0], chip_rect[1], chip_text, T.STATUS_COLOUR[status])
        info["chips"].append(chip_text)
    for txt, r in snap_rects:
        d.rectangle(r, fill=(8, 10, 14, 235), outline=T.AMBER, width=1)
        L.spaced(d, (r[0] + 9, r[1] + 5), txt, T.font("bold", 12), T.AMBER, 0.08)
        info["chips"].append(txt)
    if src_rect:
        for i, ln in enumerate(src_lines):
            d.text((safe[2] - int(d.textlength(ln, font=fsrc)), src_rect[1] + 16 * i), ln, font=fsrc, fill=(120, 126, 136, 255))
    info["labels"].extend(placer.placed)
    info["safe"] = safe
    img.putalpha(255)   # ImageDraw writes RGBA values without blending: the map is opaque by definition
    return img, info


_ANCHORS: Dict[tuple, Optional[Tuple[float, float]]] = {}


def _inside(feat: G.Feature, lon: np.ndarray, ym: np.ndarray) -> np.ndarray:
    """Even-odd point-in-feature test for arrays of (lon, merc y); ring edges are thinned to keep it light."""
    res = np.zeros(len(lon), dtype=bool)
    for outer, holes in feat.polys:
        for ring, sign in [(outer, True)] + [(h, False) for h in holes]:
            x, y = ring.lon, ring.ym
            step = max(1, len(x) // 1500)
            x, y = x[::step], y[::step]
            x2, y2 = np.roll(x, -1), np.roll(y, -1)
            cross = ((y[None, :] > ym[:, None]) != (y2[None, :] > ym[:, None])) & \
                    (lon[:, None] < (x2 - x)[None, :] * (ym[:, None] - y[None, :]) / np.where(y2 - y == 0, 1e-12, y2 - y)[None, :] + x[None, :])
            odd = (cross.sum(axis=1) % 2) == 1
            res = np.where(odd, sign, res) if not sign else (res | odd)
    return res


def _anchor(feat: G.Feature, view: View) -> Optional[Tuple[float, float]]:
    """(lon, merc y) of a label point inside the visible part of the feature: the inside grid point nearest to the mean of the inside points."""
    vb = view.bounds()
    key = (feat.iso, feat.name, tuple(round(v, 2) for v in vb))
    if key in _ANCHORS:
        return _ANCHORS[key]
    out: Optional[Tuple[float, float]] = None
    if _intersects(feat.bbox, vb):
        lo = np.linspace(max(vb[0], feat.bbox[0]), min(vb[2], feat.bbox[2]), 22)
        ys = np.linspace(G.merc(max(vb[1], feat.bbox[1])), G.merc(min(vb[3], feat.bbox[3])), 14)
        gx, gy = np.meshgrid(lo, ys)
        gx, gy = gx.ravel(), gy.ravel()
        m = _inside(feat, gx, gy)
        if m.sum() >= 6:
            ix, iy = gx[m], gy[m]
            j = int(np.argmin((ix - ix.mean()) ** 2 + ((iy - iy.mean()) * 1.0) ** 2))
            out = (float(ix[j]), float(iy[j]))
    _ANCHORS[key] = out
    if len(_ANCHORS) > 400:
        _ANCHORS.pop(next(iter(_ANCHORS)))
    return out


def _visible_center(feat: G.Feature, view: View, anchor_view: Optional[View] = None) -> Optional[Tuple[float, float]]:
    a = _anchor(feat, anchor_view or view)
    if a is None:
        return None
    x, y = view.px(a[0], a[1])
    x, y = float(x), float(y)
    return (x, y) if 0 <= x <= view.w and 0 <= y <= view.h else None




# ================================================================================================================ cards
def map_card(t: float, dur: float, params: dict) -> Optional[Image.Image]:
    """Full-frame opaque situation map, fades in and out with the card envelope."""
    img, _ = _core(params or {}, t, dur, (W, H))
    return L.fade(img, L.card_alpha(t, dur))


def map_inset(t: float, dur: float, params: dict) -> Optional[Image.Image]:
    """Small locator map on a transparent frame (pos: tl|tr|bl|br, width: pixels)."""
    p = dict(params or {})
    wd = int(p.get("width", 360))
    ht = int(round(wd * H / W))
    img, _ = _core(p, t, dur, (wd, ht), inset=True)
    frame = L.blank()
    m = T.MARGIN_X
    x = m if str(p.get("pos", "tr"))[1] == "l" else W - m - wd
    y = T.MARGIN_Y + 40 if str(p.get("pos", "tr"))[0] == "t" else T.LOWER_ZONE_Y - ht - 10
    d = ImageDraw.Draw(frame)
    d.rectangle([x - 3, y - 3, x + wd + 2, y + ht + 2], fill=(8, 10, 14, 255), outline=T.PANEL_LINE, width=1)
    frame.paste(img.convert("RGBA"), (x, y))
    if p.get("title"):
        f = T.font("bold", 12)
        L.spaced(d, (x + 8, y + 8), str(p["title"]).upper(), f, T.CREAM, 0.1)
    return L.fade(frame, L.card_alpha(t, dur))


def render_info(params: dict, t: float, dur: float = 8.0) -> dict:
    """The drawn map's bookkeeping (status, chips, label rectangles, rejected snapshots, warnings) for tests and the plan log."""
    return _core(params or {}, t, dur, (W, H))[1]


MAP_CARDS = {"map_card": map_card, "map_inset": map_inset}
