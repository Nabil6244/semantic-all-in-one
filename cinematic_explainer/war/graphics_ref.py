"""War Documentary reference graphics (owner, 2026-11-16: "adopt these two animations into war too").

Two full-frame templates studied from the owner's reference recordings:

  sat_map    "Animated map": a real satellite base (NASA Blue Marble, shaded relief + bathymetry, via NASA GIBS; the same free tiles and
             the same disk cache pakMap uses), graded dark navy. The camera pushes in slowly from a wider frame; every coastline in view
             carries a thin glowing outline; the defending country is filled translucent blue with a bright rim; a red point (side A) and
             a blue point (side B) pop in with a pulsing ring and their names, and a gold line draws between them. Title box top-left
             (orange bar, heavy caps, grey sub line), a small "ANIMATED MAP" tag top-right, colour legend bottom-right, imagery credit
             bottom-left. Without tiles (offline, first run) the same map is drawn on flat Natural Earth land, never a blank frame.
      params: a {name|label, lat, lon} *, b {...} *  (or the names of a known strait in `strait`), fill (country name / iso3 lit blue),
              title, sub, tag ("ANIMATED MAP"), legend [{colour: red|blue|gold, text}], km (shown in the sub line when no sub is given)

  kit_chain  "IN 24 HOURS" icon chain: near-black plate with a warm orange glow, heading with an orange dash, a small date tag top-right.
             Icons sit in dark discs with a glowing orange ring; they arrive one by one, each joined to the one before by an orange line
             that grows across with a white dot riding its tip (the dots keep travelling afterwards). Bold caps labels under each disc.
             Leaves on a slanted wipe that reveals the shot underneath.
      params: items [{name (stickers.NAMES), label, start?}] (2-5) *, title, date, step (s between items)

Both are fn(t, dur, params) -> RGBA 1280x720 or None (None only when the required input is missing), pure functions of t and params.
Text comes from the narration (labels, numbers, place names); nothing here invents a figure, a position or a front line.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import geo_data as G
from . import stickers as ST
from . import tokens as T
from .. import look as L

log = logging.getLogger("cinematic_explainer.war.graphics_ref")
W, H = T.W, T.H

ORANGE = (244, 104, 40, 255)
GOLD = (246, 190, 64, 255)
RED_PT = (232, 62, 62, 255)
BLUE_PT = (74, 154, 244, 255)
WHITE = (250, 250, 250, 255)
GREY = (176, 182, 192, 255)
PANEL = (16, 20, 28, 226)

# ============================================================================================================ satellite tiles (NASA GIBS)
ROOT = Path(__file__).resolve().parents[2]
TILE_ID = "nasa_bluemarble_bathymetry"
TILE_URL = ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/"
            "GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg")
MAX_Z = 8
CREDIT = "Imagery: NASA Blue Marble (GIBS)"
_FETCH_TIMEOUT = 8.0
_tile_lock = threading.Lock()
_failed: set = set()


def tile_dir() -> Path:
    """pakMap's tile cache (same z/y/x layout), so a tile fetched by either style is never fetched again."""
    return ROOT / "CACHE_DIR" / "pakmap_imagery" / TILE_ID


def _tile_path(z: int, x: int, y: int) -> Path:
    return tile_dir() / str(z) / str(y) / f"{x}.jpg"


def _tile(z: int, x: int, y: int, fetch: bool = True) -> Optional[Image.Image]:
    n = 1 << z
    x %= n
    if not 0 <= y < n:
        return None
    p = _tile_path(z, x, y)
    if p.is_file() and p.stat().st_size > 0:
        try:
            return Image.open(p).convert("RGB")
        except Exception:  # noqa: BLE001  a broken cache file is fetched again
            pass
    if not fetch or (z, x, y) in _failed:
        return None
    try:
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": "video-generator-war-maps"})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as r:
            data = r.read()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(p)
        return Image.open(p).convert("RGB")
    except Exception as exc:  # noqa: BLE001  offline: the flat base is used, said once per tile in the debug log
        with _tile_lock:
            _failed.add((z, x, y))
        log.debug("satellite tile %s/%s/%s not fetched: %s", z, x, y, exc)
        return None


# ------------------------------------------------------------------------------------------------------------ web-mercator maths
def _wx(lon: Any, z: int) -> Any:
    return (np.asarray(lon, dtype=np.float64) + 180.0) / 360.0 * 256.0 * (1 << z)


def _wy(lat: Any, z: int) -> Any:
    return (0.5 - np.asarray(G.merc(lat), dtype=np.float64) / (2 * math.pi)) * 256.0 * (1 << z)


def _lat_of(wy: float, z: int) -> float:
    return G.unmerc((0.5 - wy / (256.0 * (1 << z))) * 2 * math.pi)


# ------------------------------------------------------------------------------------------------------------ known straits / gaps
# Two shore points per crossing the narration may name; coordinates are the towns' own (approximate, labelled as places only).
STRAITS: Dict[str, Dict[str, Any]] = {
    "taiwan strait": {"title": "The Taiwan Strait", "a": {"label": "Pingtan", "lat": 25.50, "lon": 119.79}, "b": {"label": "Hsinchu", "lat": 24.80, "lon": 120.97},
                      "fill": "TWN", "km": 130},
    "strait of hormuz": {"title": "The Strait of Hormuz", "a": {"label": "Bandar Abbas", "lat": 27.18, "lon": 56.27}, "b": {"label": "Khasab", "lat": 26.18, "lon": 56.25},
                         "fill": "OMN", "km": 55},
    "kerch strait": {"title": "The Kerch Strait", "a": {"label": "Taman", "lat": 45.21, "lon": 36.72}, "b": {"label": "Kerch", "lat": 45.36, "lon": 36.47},
                     "fill": "UKR", "km": 5},
    "suwalki gap": {"title": "The Suwałki Gap", "a": {"label": "Kaliningrad", "lat": 54.71, "lon": 20.51}, "b": {"label": "Grodno", "lat": 53.68, "lon": 23.83},
                    "fill": "LTU", "km": 100},
    "english channel": {"title": "The English Channel", "a": {"label": "Calais", "lat": 50.95, "lon": 1.86}, "b": {"label": "Dover", "lat": 51.13, "lon": 1.31},
                        "fill": "GBR", "km": 33},
    "strait of gibraltar": {"title": "The Strait of Gibraltar", "a": {"label": "Tangier", "lat": 35.77, "lon": -5.80}, "b": {"label": "Gibraltar", "lat": 36.14, "lon": -5.35},
                            "fill": "ESP", "km": 14},
    "bab el mandeb": {"title": "Bab-el-Mandeb", "a": {"label": "Mocha", "lat": 13.32, "lon": 43.25}, "b": {"label": "Djibouti", "lat": 11.59, "lon": 43.15},
                      "fill": "DJI", "km": 30},
}
_STRAIT_RX = [(re.compile(r"\btaiwan strait\b", re.I), "taiwan strait"), (re.compile(r"\b(strait of hormuz|hormuz strait)\b", re.I), "strait of hormuz"),
              (re.compile(r"\bkerch strait\b", re.I), "kerch strait"), (re.compile(r"\bsuwa[lł]ki gap\b", re.I), "suwalki gap"),
              (re.compile(r"\benglish channel\b", re.I), "english channel"), (re.compile(r"\b(strait of gibraltar|gibraltar strait)\b", re.I), "strait of gibraltar"),
              (re.compile(r"\bbab[ -]el[ -]mandeb\b", re.I), "bab el mandeb")]


def _km(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def _resolve(p: dict) -> Optional[Tuple[dict, dict, dict]]:
    """(a, b, merged params) with numeric lat/lon on both points, or None."""
    q = dict(p or {})
    s = STRAITS.get(str(q.get("strait") or "").lower())
    if s:
        for k, v in s.items():
            q.setdefault(k, v)
    pts = []
    for key in ("a", "b"):
        v = q.get(key)
        if not isinstance(v, dict):
            return None
        try:
            pts.append({"label": str(v.get("label") or v.get("name") or ""), "lat": float(v["lat"]), "lon": float(v["lon"])})
        except (KeyError, TypeError, ValueError):
            return None
    return pts[0], pts[1], q


# ------------------------------------------------------------------------------------------------------------ the base mosaic
_BASE: "OrderedDict[tuple, Tuple[Image.Image, int, float, float, bool]]" = OrderedDict()
_BASE_LOCK = threading.Lock()


def _views(a: dict, b: dict, fill: Optional[G.Feature]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """(start, end) views as (centre lon, centre lat, width in degrees of longitude). End: both points plus a share of the lit country,
    the pair about a fifth of the frame apart (as in the reference); start: 1.8x wider, centred further south-west, so the push-in travels."""
    mlon, mlat = (a["lon"] + b["lon"]) / 2, (a["lat"] + b["lat"]) / 2
    if fill is not None:
        clon, clat = fill.centroid
        if abs(clon - mlon) < 12 and abs(clat - mlat) < 12:
            mlon, mlat = mlon + 0.22 * (clon - mlon), mlat + 0.12 * (clat - mlat)
    span = max(abs(a["lon"] - b["lon"]), abs(a["lat"] - b["lat"]) * 1.2, 0.08)
    w_end = min(60.0, max(0.9, span * 4.2))
    end = (mlon, mlat, w_end)
    start = (mlon - w_end * 0.18, mlat - w_end * 0.10, w_end * 1.8)
    return start, end


def _zoom_for(w_end: float) -> int:
    for z in range(2, MAX_Z + 1):
        if w_end / 360.0 * 256.0 * (1 << z) >= W * 0.95:
            return z
    return MAX_Z


def _grade(img: Image.Image) -> Image.Image:
    """Blue Marble graded to the reference: darker, a little less saturated, the sea pushed to deep navy, land kept grey-green."""
    a = np.asarray(img, dtype=np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    a = lum[..., None] + (a - lum[..., None]) * 0.78
    sea = np.clip((a[..., 2] - a[..., 0]) * 3.0, 0.0, 1.0)[..., None]           # blue-dominant pixels
    navy = np.array([0.05, 0.11, 0.20], dtype=np.float32) + a * np.array([0.18, 0.26, 0.42], dtype=np.float32)
    a = a * (1 - sea) + navy * sea
    a = np.clip(a * 0.74, 0.0, 1.0) ** 1.08
    return Image.fromarray((a * 255).astype(np.uint8), "RGB")


def _flat(size: Tuple[int, int], x0: float, y0: float, z: int, vb: Tuple[float, float, float, float]) -> Image.Image:
    """Offline base: deep navy sea and dark grey-green land from Natural Earth."""
    img = Image.new("RGB", size, (14, 28, 48))
    d = ImageDraw.Draw(img)
    for f in G.countries():
        if f.bbox[2] < vb[0] or f.bbox[0] > vb[2] or f.bbox[3] < vb[1] or f.bbox[1] > vb[3]:
            continue
        for outer, _holes in f.polys:
            xs = _wx(outer.lon, z) - x0
            ys = (0.5 - outer.ym / (2 * math.pi)) * 256.0 * (1 << z) - y0
            if len(xs) >= 3:
                d.polygon(list(zip(xs.tolist(), ys.tolist())), fill=(58, 66, 60))
    return img


def _mosaic(views: Sequence[Tuple[float, float, float]], key: Any) -> Tuple[Image.Image, int, float, float, bool]:
    """(graded mosaic, zoom, world x0, world y0, satellite?) covering every camera view (lon, lat, width in deg); cached by key."""
    with _BASE_LOCK:
        hit = _BASE.get(key)
        if hit is not None:
            _BASE.move_to_end(key)
            return hit
    tight = min(v[2] for v in views)
    wide = max(v[2] for v in views)
    z = _zoom_for(tight)
    while z > 2 and wide / 360.0 * 256.0 * (1 << z) > 6400:                # memory guard for very wide moves
        z -= 1
    xs0, xs1, ys0, ys1 = [], [], [], []
    for lon, lat, wd in views:
        hw = wd / 360.0 * 256.0 * (1 << z) / 2 * 1.12
        hh = hw * H / W * 1.12
        cx, cy = float(_wx(lon, z)), float(_wy(lat, z))
        xs0.append(cx - hw); xs1.append(cx + hw); ys0.append(cy - hh); ys1.append(cy + hh)
    x0, y0 = math.floor(min(xs0)), max(0, math.floor(min(ys0)))
    size = (int(math.ceil(max(xs1) - x0)), int(math.ceil(min(max(ys1), 256 * (1 << z)) - y0)))
    tx0, tx1, ty0, ty1 = int(x0 // 256), int((x0 + size[0]) // 256), int(y0 // 256), int((y0 + size[1]) // 256)
    coords = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    with ThreadPoolExecutor(max_workers=6) as ex_:
        tiles = list(ex_.map(lambda c: _tile(z, c[0], c[1]), coords))
    sat = all(t_ is not None for t_ in tiles) and bool(tiles)
    if sat:
        img = Image.new("RGB", size)
        for (tx, ty), t_ in zip(coords, tiles):
            img.paste(t_, (int(tx * 256 - x0), int(ty * 256 - y0)))
        img = _grade(img)
    else:
        vb = (min(v[0] for v in views) - wide, min(v[1] for v in views) - wide, max(v[0] for v in views) + wide, max(v[1] for v in views) + wide)
        img = _flat(size, x0, y0, z, vb)
    out = (img, z, float(x0), float(y0), sat)
    with _BASE_LOCK:
        _BASE[key] = out
        while len(_BASE) > 6:
            _BASE.popitem(last=False)
    return out


def _base(a: dict, b: dict, fill_key: str) -> Tuple[Image.Image, int, float, float, bool]:
    fill = G.find_country(fill_key) if fill_key else None
    key = ("pair", round(a["lat"], 3), round(a["lon"], 3), round(b["lat"], 3), round(b["lon"], 3), fill_key)
    return _mosaic(_views(a, b, fill), key)


def _between(v0: Tuple[float, float, float], v1: Tuple[float, float, float], k: float) -> Tuple[float, float, float]:
    return v0[0] + (v1[0] - v0[0]) * k, v0[1] + (v1[1] - v0[1]) * k, v0[2] * (v1[2] / v0[2]) ** k      # zoom eases geometrically


def _even(t: float, dur: float) -> float:
    x_ = min(1.0, max(0.0, t / max(0.1, dur * 0.95)))
    return x_ * x_ * (3 - 2 * x_) * 0.6 + x_ * 0.4                       # slow, even camera move (no early lurch), settles at the end


def _shot(mos: Tuple[Image.Image, int, float, float, bool], view: Tuple[float, float, float], lit_iso: str = "", fa: float = 1.0,
          coast: float = 1.0):
    """(RGBA frame of the mosaic seen through `view` with glowing coastlines and the lit country, px(lons, lats) -> frame x, y)."""
    base, z, x0, y0, _sat = mos
    lon, lat, wdeg = view
    cx, cy = float(_wx(lon, z)) - x0, float(_wy(lat, z)) - y0
    vw = wdeg / 360.0 * 256.0 * (1 << z)
    vh = vw * H / W
    box = (cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2)
    frame = base.transform((W, H), Image.Transform.EXTENT, box, Image.Resampling.BILINEAR).convert("RGBA")
    s = W / vw

    def px(lons, lats):
        return (_wx(lons, z) - x0 - box[0]) * s, (_wy(lats, z) - y0 - box[1]) * s

    lon0 = (box[0] + x0) / (256.0 * (1 << z)) * 360.0 - 180.0
    lon1 = (box[2] + x0) / (256.0 * (1 << z)) * 360.0 - 180.0
    lat1, lat0 = _lat_of(box[1] + y0, z), _lat_of(box[3] + y0, z)
    vb = (lon0 - 0.5, lat0 - 0.5, lon1 + 0.5, lat1 + 0.5)
    SS = 2
    ov = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    glow = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for f in G.countries():                                               # coastlines: thin white rim, the lit country brighter
        if f.bbox[2] < vb[0] or f.bbox[0] > vb[2] or f.bbox[3] < vb[1] or f.bbox[1] > vb[3]:
            continue
        lit = bool(lit_iso) and f.iso == lit_iso
        for outer, _holes in f.polys:
            ob = outer.bbox
            if ob[2] < vb[0] or ob[0] > vb[2] or ob[3] < vb[1] or ob[1] > vb[3]:
                continue
            xs = (_wx(outer.lon, z) - x0 - box[0]) * s * SS
            ys = ((0.5 - outer.ym / (2 * math.pi)) * 256.0 * (1 << z) - y0 - box[1]) * s * SS
            pts = list(zip(xs.tolist(), ys.tolist()))
            if len(pts) < 3:
                continue
            if lit:
                od.polygon(pts, fill=(70, 140, 230, int(92 * fa)))
                gd.line(pts + pts[:1], fill=(150, 200, 255, int(200 * fa)), width=7 * SS)
                od.line(pts + pts[:1], fill=(226, 238, 255, int(235 * fa)), width=2 * SS)
            elif coast > 0:
                gd.line(pts + pts[:1], fill=(200, 230, 255, int(70 * coast)), width=4 * SS)
                od.line(pts + pts[:1], fill=(222, 236, 250, int(150 * coast)), width=1 * SS + 1)
    glow = glow.filter(ImageFilter.GaussianBlur(5 * SS))
    frame.alpha_composite(Image.alpha_composite(glow, ov).resize((W, H), Image.Resampling.LANCZOS))
    return frame, px


# ------------------------------------------------------------------------------------------------------------ drawing helpers
def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _ramp(t: float, a: float, length: float) -> float:
    return min(1.0, max(0.0, (t - a) / max(1e-6, length)))


def _out(t: float, dur: float, fade: float = 0.3) -> float:
    return 1.0 if dur <= 0 else min(1.0, max(0.0, (dur - t) / fade), max(0.0, t / 0.2))


def _halo_text(d: ImageDraw.ImageDraw, xy, text: str, f, fill=WHITE, a: float = 1.0) -> None:
    x, y = xy
    sh = (0, 0, 0, int(170 * a))
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 2)):
        d.text((x + dx, y + dy), text, font=f, fill=sh)
    d.text((x, y), text, font=f, fill=fill[:3] + (int(fill[3] * a),))


def _f(kind: str, size: int):
    try:
        return L.font(kind, size)
    except Exception:  # noqa: BLE001
        return T.font("bold", size)


def _title_box(img: Image.Image, t: float, title: str, sub: str) -> None:
    if not title:
        return
    k = _ease(_ramp(t, 0.15, 0.45))
    if k <= 0:
        return
    ft, fs = _f("heavy", 30), _f("regular", 15)
    d = ImageDraw.Draw(img)
    tw = max(d.textlength(title.upper(), font=ft), d.textlength(sub, font=fs) if sub else 0)
    bw, bh = int(tw + 44), 74 if sub else 54
    x = int(34 - (1 - k) * 40)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.rectangle([x, 34, x + bw, 34 + bh], fill=PANEL[:3] + (int(PANEL[3] * k),))
    ld.rectangle([x, 34, x + 4, 34 + bh], fill=ORANGE[:3] + (int(255 * k),))
    ld.text((x + 20, 44), title.upper(), font=ft, fill=WHITE[:3] + (int(255 * k),))
    if sub:
        ld.text((x + 20, 82), sub, font=fs, fill=GREY[:3] + (int(255 * k),))
    img.alpha_composite(lay)


def _tag(img: Image.Image, t: float, text: str) -> None:
    if not text:
        return
    a = _ramp(t, 0.3, 0.4)
    d = ImageDraw.Draw(img)
    f = _f("bold", 12)
    tw = L.spaced_width(d, text.upper(), f, 0.06)
    x = int(W - 34 - tw - 14)
    d.rectangle([x - 8, 34, W - 34, 54], fill=(10, 12, 16, int(200 * a)))
    d.rectangle([x - 8, 34, x - 6, 54], fill=ORANGE[:3] + (int(255 * a),))
    L.spaced(d, (x, 37), text.upper(), f, WHITE[:3] + (int(255 * a),), 0.06)


def _legend(img: Image.Image, t: float, items: Sequence[dict]) -> None:
    if not items:
        return
    a = _ramp(t, 0.6, 0.5)
    d = ImageDraw.Draw(img)
    f = _f("regular", 13)
    cols = {"red": RED_PT, "blue": BLUE_PT, "gold": GOLD, "orange": ORANGE}
    x = W - 34
    for it in reversed(list(items)[:3]):
        txt = str(it.get("text") or "")[:40]
        if not txt:
            continue
        tw = d.textlength(txt, font=f)
        x -= tw
        d.text((x, H - 44), txt, font=f, fill=(214, 218, 226, int(230 * a)))
        x -= 18
        c = cols.get(str(it.get("colour") or "blue"), BLUE_PT)
        d.rectangle([x, H - 39, x + 11, H - 31], fill=c[:3] + (int(255 * a),))
        x -= 22


def _pt_label(d, x: float, y: float, text: str, side: str, f, a: float) -> None:
    if not text:
        return
    tw = d.textlength(text, font=f)
    if side == "left":
        _halo_text(d, (x - tw - 16, y - 2), text, f, WHITE, a)
    elif side == "below":
        _halo_text(d, (x + 6, y + 12), text, f, WHITE, a)
    else:
        _halo_text(d, (x + 16, y - 24), text, f, WHITE, a)


# ------------------------------------------------------------------------------------------------------------ sat_map
def sat_map(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    r = _resolve(p)
    if r is None:
        return None
    a, b, q = r
    fill_key = str(q.get("fill") or "")
    mos = _base(a, b, fill_key)
    sat = mos[4]
    fill = G.find_country(fill_key) if fill_key else None
    v0, v1 = _views(a, b, fill)
    frame, px = _shot(mos, _between(v0, v1, _even(t, dur)), fill.iso if fill is not None else "", _ease(_ramp(t, 0.5, 0.9)))

    top = Image.new("RGBA", (W, H), (0, 0, 0, 0))                       # drawn marks blend over the map (drawing on it would cut holes)
    d = ImageDraw.Draw(top)
    (ax,), (ay,) = [np.atleast_1d(v) for v in px([a["lon"]], [a["lat"]])]
    (bx,), (by,) = [np.atleast_1d(v) for v in px([b["lon"]], [b["lat"]])]
    ka, kb = _ease(_ramp(t, 0.6, 0.35)), _ease(_ramp(t, 1.5, 0.35))
    kl = _ease(_ramp(t, 0.9, 0.8))
    if kl > 0:                                                            # the gold line draws from A to B
        lx, ly_ = ax + (bx - ax) * kl, ay + (by - ay) * kl
        d.line([(ax, ay + 2), (lx, ly_ + 2)], fill=(0, 0, 0, 110), width=6)
        d.line([(ax, ay), (lx, ly_)], fill=GOLD, width=4)
    fl = _f("heavy", 24)
    side_a = "below" if ax < bx else "left"
    for (x, y, col, kk, lab, side, t0) in ((ax, ay, RED_PT, ka, a["label"], side_a, 0.6), (bx, by, BLUE_PT, kb, b["label"], "right", 1.5)):
        if kk <= 0:
            continue
        ph = ((t - t0) % 1.6) / 1.6                                       # pulsing ring
        rr = 9 + 20 * ph
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=col[:3] + (int(200 * (1 - ph) * kk),), width=2)
        r0 = 9 * (0.5 + 0.5 * kk)
        d.ellipse([x - r0 - 3, y - r0 - 3, x + r0 + 3, y + r0 + 3], fill=(255, 255, 255, int(255 * kk)))
        d.ellipse([x - r0, y - r0, x + r0, y + r0], fill=col[:3] + (int(255 * kk),))
        _pt_label(d, x, y, lab, side, fl, kk)

    title = str(q.get("title") or "")
    sub = str(q.get("sub") or "")
    if not sub:
        km = q.get("km") or round(_km(a, b))
        sub = f"~{int(km):,} km across" if km else ""
    _tag(top, t, str(q.get("tag") if q.get("tag") is not None else "ANIMATED MAP"))
    _legend(top, t, q.get("legend") or [])
    cf = _f("regular", 11)
    d.text((34, H - 30), CREDIT if sat else "Natural Earth (public domain) · illustrative", font=cf, fill=(170, 176, 186, 170))
    frame.alpha_composite(top)
    _title_box(frame, t, title, sub)
    return L.fade(frame, _out(t, dur))


# ------------------------------------------------------------------------------------------------------------ kit_chain
_CHAIN_MEMO: "OrderedDict[str, Image.Image]" = OrderedDict()


def _memo(key: str, build) -> Image.Image:
    hit = _CHAIN_MEMO.get(key)
    if hit is None:
        hit = build()
        _CHAIN_MEMO[key] = hit
        while len(_CHAIN_MEMO) > 48:
            _CHAIN_MEMO.popitem(last=False)
    return hit


def _chain_plate() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = np.exp(-(((xx - W * 0.16) / (W * 0.42)) ** 2 + ((yy - H * 0.30) / (H * 0.62)) ** 2))
    base = np.stack([8 + 70 * g, 9 + 24 * g, 12 + 8 * g], axis=-1)
    v = 1 - 0.45 * np.clip(((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - H / 2) / (H * 0.8)) ** 2, 0, 1)
    base = base * v[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)
    for y in (int(H * 0.13), int(H * 0.86)):                              # the faint rules of the reference
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 12), width=1)
    return img


def _disc(name: str, r: int) -> Image.Image:
    size = r * 2 + 60
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c = size / 2
    ImageDraw.Draw(g).ellipse([c - r - 4, c - r - 4, c + r + 4, c + r + 4], outline=ORANGE[:3] + (200,), width=10)
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(9)))
    d = ImageDraw.Draw(im)
    d.ellipse([c - r, c - r, c + r, c + r], fill=(14, 16, 24, 255), outline=ORANGE, width=4)
    try:
        ic = ST.draw_sticker(name, int(r * 1.15))
        im.alpha_composite(ic, (int(c - ic.width / 2), int(c - ic.height / 2)))
    except Exception:  # noqa: BLE001  an unknown pictogram leaves the disc empty, never breaks the card
        pass
    return im


def _wrap(d, text: str, f, width: int, max_lines: int = 4) -> List[str]:
    out: List[str] = []
    cur = ""
    for w_ in text.split():
        trial = (cur + " " + w_).strip()
        if d.textlength(trial, font=f) <= width or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = w_
    if cur:
        out.append(cur)
    return out[:max_lines]


def kit_chain(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    p = p or {}
    items = [i for i in (p.get("items") or []) if isinstance(i, dict) and str(i.get("label") or "").strip()][:5]
    if len(items) < 2:
        return None
    img = _memo("plate", _chain_plate).copy()
    top = Image.new("RGBA", (W, H), (0, 0, 0, 0))                       # lines and words blend over the plate and discs
    d = ImageDraw.Draw(top)
    n = len(items)
    gap = min(W * 0.208, W * 0.80 / max(1, n - 1))
    x0 = W / 2 - gap * (n - 1) / 2
    cy, r = H * 0.43, 44
    step = float(p.get("step") or max(0.45, min(1.3, (dur * 0.55) / n)))
    starts = [float(it.get("start", 0.35 + step * i)) for i, it in enumerate(items)]

    title = str(p.get("title") or "").strip().upper()
    if title:
        k = _ease(_ramp(t, 0.05, 0.4))
        ft = _f("heavy", 34)
        xo = int(52 - 30 * (1 - k))
        d.rectangle([xo, 80, xo + 22, 83], fill=ORANGE[:3] + (int(255 * k),))
        d.text((xo + 30, 62), title, font=ft, fill=WHITE[:3] + (int(255 * k),))
    date = str(p.get("date") or "").strip().upper()
    if date:
        fd = _f("bold", 12)
        tw = L.spaced_width(d, date, fd, 0.06)
        d.rectangle([W - 50 - tw - 10, 28, W - 50 - tw - 8, 46], fill=ORANGE)
        L.spaced(d, (W - 50 - tw, 31), date, fd, WHITE, 0.06)

    fl = _f("heavy", 21)
    for i, it in enumerate(items):
        cx = x0 + gap * i
        if i > 0:                                                         # connector grows in just before the disc lands
            px_ = x0 + gap * (i - 1)
            la, lb = px_ + r + 6, cx - r - 6
            g = _ease(_ramp(t, starts[i] - 0.35, 0.35))
            if g > 0:
                tip = la + (lb - la) * g
                d.line([(la, cy), (tip, cy)], fill=ORANGE, width=3)
                if g < 1:
                    dot = tip
                else:                                                     # the dots keep travelling along the chain
                    ph = ((t - starts[i] + 0.37 * i) % 1.8) / 1.8
                    dot = la + (lb - la) * ph
                d.ellipse([dot - 4, cy - 4, dot + 4, cy + 4], fill=WHITE)
        k = _ramp(t, starts[i], 0.4)
        if k <= 0:
            continue
        kb = 1 + 0.12 * math.sin(math.pi * min(1.0, k)) if k < 1 else 1.0   # a small overshoot
        disc = _memo(f"disc:{it.get('name')}:{r}", lambda nm=str(it.get("name") or ""): _disc(nm, r))
        sc = (0.6 + 0.4 * _ease(k)) * kb
        dd = disc.resize((max(1, int(disc.width * sc)), max(1, int(disc.height * sc))), Image.Resampling.BILINEAR)
        if k < 1:
            a_ = dd.getchannel("A").point(lambda v, kk=k: int(v * kk))
            dd.putalpha(a_)
        img.alpha_composite(dd, (int(cx - dd.width / 2), int(cy - dd.height / 2)))
        kl = _ramp(t, starts[i] + 0.15, 0.35)
        if kl > 0:
            lines = _wrap(d, str(it["label"]).upper(), fl, int(gap * 0.92) if n > 1 else 260)
            y = cy + r + 22 + 8 * (1 - kl)
            for ln in lines:
                tw = d.textlength(ln, font=fl)
                d.text((cx - tw / 2, y), ln, font=fl, fill=WHITE[:3] + (int(255 * kl),))
                y += 26

    img.alpha_composite(top)
    return _wipe(img, t, dur)


def _wipe(img: Image.Image, t: float, dur: float) -> Image.Image:
    """Fade in over 0.2 s; leave on a slanted wipe (last 0.45 s) that shows the shot underneath, an orange edge riding it."""
    if dur > 0 and t > dur - 0.45:
        k = _ease((t - (dur - 0.45)) / 0.45)
        edge = -W * 0.35 + (W * 1.7) * k
        mask = Image.new("L", (W, H), 255)
        md = ImageDraw.Draw(mask)
        md.polygon([(-10, -10), (edge + H * 0.18, -10), (edge - H * 0.18, H + 10), (-10, H + 10)], fill=0)
        a_ = Image.composite(img.getchannel("A"), Image.new("L", (W, H), 0), mask)
        img.putalpha(a_)
        ImageDraw.Draw(img).line([(edge + H * 0.18, -10), (edge - H * 0.18, H + 10)], fill=ORANGE[:3] + (180,), width=3)
        return img
    return L.fade(img, min(1.0, max(0.0, t / 0.2)))


def _heading(d, t: float, title: str, date: str = "") -> None:
    """Orange dash + heavy caps heading top-left, optional date tag top-right (the chain reference's header)."""
    title = (title or "").strip().upper()
    if title:
        k = _ease(_ramp(t, 0.05, 0.4))
        ft = _f("heavy", 34)
        xo = int(52 - 30 * (1 - k))
        d.rectangle([xo, 80, xo + 22, 83], fill=ORANGE[:3] + (int(255 * k),))
        d.text((xo + 30, 62), title, font=ft, fill=WHITE[:3] + (int(255 * k),))
    date = (date or "").strip().upper()
    if date:
        fd = _f("bold", 12)
        tw = L.spaced_width(d, date, fd, 0.06)
        d.rectangle([W - 50 - tw - 10, 28, W - 50 - tw - 8, 46], fill=ORANGE)
        L.spaced(d, (W - 50 - tw, 31), date, fd, WHITE, 0.06)


def _fmt_num(v: float, like: str = "") -> str:
    """A counted value written the way the script wrote its figure (thousands commas, a decimal only when the script used one, % kept)."""
    pct = "%" in like
    dec = 1 if re.search(r"\d\.\d", like or "") else 0
    body = f"{v:,.{dec}f}"
    return body + ("%" if pct else "") + ("+" if like.endswith("+") else "")


# ------------------------------------------------------------------------------------------------------------ kit_counter
def kit_counter(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """A figure that rose or fell, as the script states it: the big number rolls from the old value to the new one, two bars compare them,
    and a change chip (+400% / x5 / -60%) lands when the count stops. params: a {value, shown, label}, b {...} *, unit, title, date."""
    p = p or {}
    try:
        va, vb_ = float(p["a"]["value"]), float(p["b"]["value"])
    except (KeyError, TypeError, ValueError):
        return None
    if va == vb_ or max(abs(va), abs(vb_)) == 0:
        return None
    img = _memo("plate", _chain_plate).copy()
    top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(top)
    _heading(d, t, str(p.get("title") or ""), str(p.get("date") or ""))
    k = _ease(_ramp(t, 0.6, min(1.8, max(0.8, dur * 0.3))))
    v = va + (vb_ - va) * k
    sa, sb = str(p["a"].get("shown") or _fmt_num(va)), str(p["b"].get("shown") or _fmt_num(vb_))
    txt = sb if k >= 1 else _fmt_num(v, sb)
    fn = _f("heavy", 150)
    a_in = _ease(_ramp(t, 0.3, 0.35))
    tw = d.textlength(txt, font=fn)
    cx, ny = W * 0.5, H * 0.22
    d.text((cx - tw / 2 + 4, ny + 6), txt, font=fn, fill=(0, 0, 0, int(120 * a_in)))
    d.text((cx - tw / 2, ny), txt, font=fn, fill=WHITE[:3] + (int(255 * a_in),))
    unit = str(p.get("unit") or "").upper()
    if unit:
        fu = _f("bold", 26)
        uw = L.spaced_width(d, unit, fu, 0.08)
        L.spaced(d, (cx - uw / 2, ny + 172), unit, fu, GREY[:3] + (int(255 * a_in),), 0.08)
    if k >= 1:                                                            # the change chip
        kc = _ease(_ramp(t, 0.6 + min(1.8, max(0.8, dur * 0.3)), 0.3))
        r_ = vb_ / va if va else 0
        if "%" in sb and "%" in sa:
            chg = f"{vb_ - va:+,.0f} pts"
        elif r_ >= 3:
            chg = f"\u00d7{r_:.0f}" if abs(r_ - round(r_)) < 0.05 else f"\u00d7{r_:.1f}"
        else:
            chg = f"{(r_ - 1) * 100:+,.0f}%"
        fc = _f("heavy", 30)
        cw = d.textlength(chg, font=fc)
        col = ORANGE if vb_ > va else BLUE_PT
        x = cx + tw / 2 + 24
        d.rounded_rectangle([x, ny + 46, x + cw + 28, ny + 96], 8, fill=col[:3] + (int(235 * kc),))
        d.text((x + 14, ny + 50), chg, font=fc, fill=WHITE[:3] + (int(255 * kc),))
    mx = max(abs(va), abs(vb_))
    bx, bw, fl = W * 0.5 - 380, 760, _f("bold", 18)
    for i, (lab, val, col, t0) in enumerate(((str(p["a"].get("label") or "THEN"), va, (120, 126, 138, 255), 0.4),
                                             (str(p["b"].get("label") or "NOW"), v, ORANGE, 0.6))):
        y = H * 0.66 + i * 52
        a2 = _ease(_ramp(t, t0, 0.3))
        d.text((bx - 18 - d.textlength(lab.upper(), font=fl), y + 2), lab.upper(), font=fl, fill=GREY[:3] + (int(255 * a2),))
        d.rectangle([bx, y, bx + bw, y + 26], fill=(255, 255, 255, int(16 * a2)))
        ln = bw * abs(val) / mx * (a2 if i == 0 else 1)
        if ln > 0:
            d.rectangle([bx, y, bx + ln, y + 26], fill=col[:3] + (int(255 * a2),))
        shown = sa if i == 0 else txt
        d.text((bx + bw + 16, y + 1), shown, font=fl, fill=WHITE[:3] + (int(255 * a2),))
    img.alpha_composite(top)
    return _wipe(img, t, dur)


# ------------------------------------------------------------------------------------------------------------ kit_forces
def kit_forces(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """Two sides' counts face off, one row per kind of thing both sides are said to have: icon disc in the middle, the left side's bar
    grows to the left in red, the right side's to the right in blue, each figure at its bar end.
    params: left {name}, right {name} *, rows [{name (sticker), label, a, b, a_shown, b_shown}] (1-4) *, title, date."""
    p = p or {}
    rows = [r for r in (p.get("rows") or []) if isinstance(r, dict)][:4]
    ln_, rn_ = str((p.get("left") or {}).get("name") or ""), str((p.get("right") or {}).get("name") or "")
    if not rows or not ln_ or not rn_:
        return None
    try:
        vals = [(float(r["a"]), float(r["b"])) for r in rows]
    except (KeyError, TypeError, ValueError):
        return None
    img = _memo("plate", _chain_plate).copy()
    top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(top)
    _heading(d, t, str(p.get("title") or ""), str(p.get("date") or ""))
    cx = W / 2
    fh = _f("heavy", 30)
    ka = _ease(_ramp(t, 0.2, 0.4))
    for name, col, side in ((ln_.upper(), RED_PT, -1), (rn_.upper(), BLUE_PT, 1)):
        w_ = d.textlength(name, font=fh)
        x = cx - 90 - w_ if side < 0 else cx + 90
        d.text((x, 128), name, font=fh, fill=col[:3] + (int(255 * ka),))
    fv = _f("heavy", 22)
    vw_ = d.textlength("VS", font=fv)
    d.text((cx - vw_ / 2, 134), "VS", font=fv, fill=ORANGE[:3] + (int(255 * ka),))
    n = len(rows)
    gap = min(118, (H - 250) / n)
    y0 = 200 + (H - 250 - gap * n) / 2 + gap / 2
    r_ = 34
    maxw = W * 0.5 - r_ - 170
    fl, fn = _f("bold", 15), _f("heavy", 26)
    for i, (row, (a_, b_)) in enumerate(zip(rows, vals)):
        y = y0 + i * gap
        t0 = 0.6 + i * max(0.35, min(0.7, dur * 0.08))
        k = _ease(_ramp(t, t0, 0.4))
        if k <= 0:
            continue
        m = max(a_, b_, 1e-9)
        g = _ease(_ramp(t, t0 + 0.2, 0.9))
        for v_, col, side, shown in ((a_, RED_PT, -1, str(row.get("a_shown") or _fmt_num(a_))), (b_, BLUE_PT, 1, str(row.get("b_shown") or _fmt_num(b_)))):
            ln = maxw * v_ / m * g
            x_in = cx + side * (r_ + 12)
            x_end = x_in + side * ln
            d.rectangle([min(x_in, x_end), y - 11, max(x_in, x_end), y + 11], fill=col[:3] + (int(230 * k),))
            sw_ = d.textlength(shown, font=fn)
            d.text((x_end + (10 if side > 0 else -10 - sw_), y - 16), shown, font=fn, fill=WHITE[:3] + (int(255 * min(1.0, g * 1.5)),))
        disc = _memo(f"disc:{row.get('name')}:{r_}", lambda nm=str(row.get("name") or ""): _disc(nm, r_))
        dd = disc.copy()
        if k < 1:
            dd.putalpha(dd.getchannel("A").point(lambda q, kk=k: int(q * kk)))
        img.alpha_composite(dd, (int(cx - dd.width / 2), int(y - dd.height / 2)))
        lab = str(row.get("label") or "").upper()
        if lab:
            lw = d.textlength(lab, font=fl)
            d.text((cx - lw / 2, y + r_ + 6), lab, font=fl, fill=GREY[:3] + (int(255 * k),))
    img.alpha_composite(top)
    return _wipe(img, t, dur)


# ------------------------------------------------------------------------------------------------------------ sat_range
def _deg_w(km: float, lat: float) -> float:
    return 2 * km / (111.32 * max(0.2, math.cos(math.radians(lat))))


def sat_range(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """How far something reaches, as the script states it: satellite base, the camera starts close on the launch site and pulls back while
    a ring grows out to the stated distance; its figure rides the ring's edge. params: centre {label, lat, lon} *, km *, shown ("300 km"),
    title, sub, fill (country lit blue), tag."""
    p = p or {}
    c = p.get("centre") or {}
    try:
        lat, lon, km = float(c["lat"]), float(c["lon"]), float(p["km"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 1.0 <= km <= 6000.0:
        return None
    diam = _deg_w(km, lat)
    v1 = (lon, lat, min(140.0, max(0.5, diam * 2.6)))
    v0 = (lon, lat, v1[2] * 0.42)
    fill_key = str(p.get("fill") or "")
    mos = _mosaic((v0, v1), ("range", round(lat, 3), round(lon, 3), round(km)))
    fill = G.find_country(fill_key) if fill_key else None
    frame, px = _shot(mos, _between(v0, v1, _even(t, dur)), fill.iso if fill is not None else "", _ease(_ramp(t, 0.3, 0.8)), 0.8)
    top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(top)
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gl)
    g = _ease(_ramp(t, 0.7, min(3.0, max(1.2, dur * 0.45))))
    (sx,), (sy,) = [np.atleast_1d(v_) for v_ in px([lon], [lat])]
    if g > 0:
        for frac, alpha in ((1 / 3, 60), (2 / 3, 60)):                       # faint inner distance rings once the ring has passed them
            if g >= frac:
                xs, ys = _ring_px(px, G.geodesic_circle(lat, lon, km * frac))
                d.line(list(zip(xs, ys)) + [(xs[0], ys[0])], fill=(255, 180, 140, alpha), width=1)
        ring = G.geodesic_circle(lat, lon, km * g)
        xs, ys = _ring_px(px, ring)
        pts = list(zip(xs, ys))
        d.polygon(pts, fill=(232, 62, 62, 46))
        gd.line(pts + pts[:1], fill=(255, 110, 70, 200), width=8)
        d.line(pts + pts[:1], fill=(255, 150, 110, 255), width=3)
        ex_ = max(range(len(pts)), key=lambda i: pts[i][0])                  # the figure rides the ring's east edge
        shown = str(p.get("shown") or f"{km:,.0f} km").upper()
        fc = _f("heavy", 22)
        cw = d.textlength(shown, font=fc)
        lx, ly_ = min(W - cw - 50, pts[ex_][0] + 12), max(60, min(H - 80, pts[ex_][1] - 18))
        d.rounded_rectangle([lx - 10, ly_ - 4, lx + cw + 10, ly_ + 30], 6, fill=(16, 20, 28, int(220 * g)))
        d.text((lx, ly_), shown, font=fc, fill=WHITE[:3] + (int(255 * g),))
    top = Image.alpha_composite(gl.filter(ImageFilter.GaussianBlur(5)), top)
    dd = ImageDraw.Draw(top)
    ph = (t % 1.6) / 1.6
    rr = 9 + 22 * ph
    dd.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], outline=RED_PT[:3] + (int(200 * (1 - ph)),), width=2)
    dd.ellipse([sx - 12, sy - 12, sx + 12, sy + 12], fill=WHITE)
    dd.ellipse([sx - 9, sy - 9, sx + 9, sy + 9], fill=RED_PT)
    _pt_label(dd, sx, sy, str(c.get("label") or ""), "right", _f("heavy", 24), 1.0)
    _tag(top, t, str(p.get("tag") if p.get("tag") is not None else "RANGE"))
    dd.text((34, H - 30), CREDIT if mos[4] else "Natural Earth (public domain) · illustrative", font=_f("regular", 11), fill=(170, 176, 186, 170))
    frame.alpha_composite(top)
    _title_box(frame, t, str(p.get("title") or ""), str(p.get("sub") or ""))
    return L.fade(frame, _out(t, dur))


def _ring_px(px, ring) -> Tuple[List[float], List[float]]:
    """geo_data.geodesic_circle points are (lon, lat) pairs; projected to frame pixels."""
    lons = [q[0] for q in ring]
    lats = [q[1] for q in ring]
    xs, ys = px(lons, lats)
    return np.atleast_1d(xs).tolist(), np.atleast_1d(ys).tolist()


# ------------------------------------------------------------------------------------------------------------ sat_quote
def sat_quote(t: float, dur: float, p: dict) -> Optional[Image.Image]:
    """A leader's words over the place they are about: the satellite drifts slowly behind a dark left-hand panel, the quote types in
    word by word under a big orange quote mark, the speaker's name and role under it, the place pinned (or the country lit) on the right.
    params: quote *, speaker, role, place {label, lat, lon} | country (name / iso3) *."""
    p = p or {}
    q = str(p.get("quote") or "").strip().strip('"\u201c\u201d')
    if not q:
        return None
    pl = p.get("place") or {}
    feat = G.find_country(str(p.get("country") or "")) if p.get("country") else None
    try:
        lat, lon = float(pl["lat"]), float(pl["lon"])
        wdeg = 7.0
    except (KeyError, TypeError, ValueError):
        if feat is None:
            return None
        lon, lat = feat.centroid
        wdeg = min(120.0, max(4.0, (feat.bbox[2] - feat.bbox[0]) * 2.4))
    v0 = (lon - wdeg * 0.20, lat + wdeg * 0.04, wdeg * 1.12)                  # the place sits right of centre; slow drift and push
    v1 = (lon - wdeg * 0.26, lat, wdeg)
    mos = _mosaic((v0, v1), ("quote", round(lat, 3), round(lon, 3), round(wdeg, 2)))
    frame, px = _shot(mos, _between(v0, v1, _even(t, dur)), feat.iso if feat is not None else "", _ease(_ramp(t, 0.4, 0.8)), 0.7)
    sh = np.zeros((H, W), dtype=np.float32)                                  # dark panel fading out to the right
    xx = np.arange(W, dtype=np.float32)
    sh[:] = np.clip(1.0 - (xx - W * 0.42) / (W * 0.30), 0.0, 1.0) * 0.86
    shade = Image.new("RGBA", (W, H), (8, 10, 14, 255))
    shade.putalpha(Image.fromarray((sh * 255).astype(np.uint8), "L"))
    frame.alpha_composite(shade)
    top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(top)
    if pl.get("lat") is not None:
        try:
            (sx,), (sy,) = [np.atleast_1d(v_) for v_ in px([lon], [lat])]
            ka = _ease(_ramp(t, 0.5, 0.4))
            ph = (t % 1.6) / 1.6
            rr = 9 + 20 * ph
            d.ellipse([sx - rr, sy - rr, sx + rr, sy + rr], outline=RED_PT[:3] + (int(200 * (1 - ph) * ka),), width=2)
            d.ellipse([sx - 11, sy - 11, sx + 11, sy + 11], fill=(255, 255, 255, int(255 * ka)))
            d.ellipse([sx - 8, sy - 8, sx + 8, sy + 8], fill=RED_PT[:3] + (int(255 * ka),))
            _pt_label(d, sx, sy, str(pl.get("label") or ""), "right", _f("heavy", 24), ka)
        except Exception:  # noqa: BLE001
            pass
    km_ = _ease(_ramp(t, 0.2, 0.4))
    d.text((70, 92), "\u201c", font=_f("heavy", 120), fill=ORANGE[:3] + (int(255 * km_),))
    fq = _f("heavy", 40)
    lines = _wrap(d, q, fq, 560, max_lines=6)
    while len(lines) >= 6 and fq.size > 26:
        fq = _f("heavy", fq.size - 4)
        lines = _wrap(d, q, fq, 560, max_lines=7)
    words = sum(len(ln.split()) for ln in lines)
    shown = int(round(words * _ramp(t, 0.5, min(2.6, max(0.8, dur * 0.45)))))
    y = 200
    lh = int(fq.size * 1.18)
    for ln in lines:
        ws = ln.split()
        x = 80.0
        for w_ in ws:
            on = shown > 0
            d.text((x, y), w_, font=fq, fill=WHITE[:3] + (255 if on else 40,))
            x += d.textlength(w_ + " ", font=fq)
            shown -= 1
        y += lh
    who, role = str(p.get("speaker") or "").upper(), str(p.get("role") or "")
    if who:
        ks = _ease(_ramp(t, 0.9, 0.4))
        y += 18
        d.rectangle([80, y, 84, y + (46 if role else 24)], fill=ORANGE[:3] + (int(255 * ks),))
        d.text((96, y - 2), who, font=_f("heavy", 22), fill=WHITE[:3] + (int(255 * ks),))
        if role:
            d.text((96, y + 26), role, font=_f("regular", 16), fill=GREY[:3] + (int(255 * ks),))
    d.text((34, H - 30), CREDIT if mos[4] else "Natural Earth (public domain) · illustrative", font=_f("regular", 11), fill=(170, 176, 186, 170))
    frame.alpha_composite(top)
    return L.fade(frame, _out(t, dur))


REF_CARDS = {"sat_map": sat_map, "kit_chain": kit_chain, "sat_range": sat_range, "sat_quote": sat_quote, "kit_counter": kit_counter,
             "kit_forces": kit_forces}
FULL = set(REF_CARDS)


# ================================================================================================================ narration -> params
_NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
         "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100, "dozens of": 0, "hundreds of": 0}
_NUM = r"(?:\d[\d,]*(?:\.\d+)?|" + "|".join(sorted(map(re.escape, _NUMW), key=len, reverse=True)) + r"|an?)"
_COUNT = re.compile(r"(?P<pre>\b(?:more than|over|at least|nearly|almost|about|around|some)\s+)?\b(?P<n>" + _NUM + r")\s+(?P<what>[^,;.:()]+?)"
                    r"(?=\s*(?:,|;|\.|:|$|\band\s+(?:then\s+)?(?:" + _NUM + r"|more than|over|at least)\b))", re.IGNORECASE)
_PERIOD = re.compile(r"\b(?:in|within|over|during)\s+(?:just\s+|only\s+)?(?:the\s+)?(?:past\s+|last\s+|first\s+)?(?:\d+|one|two|three|four|five|six|seven|"
                     r"ten|twelve|twenty-four|forty-eight|a|a single)\s+(?:hours?|days?|nights?|weeks?|months?)\b|\bovernight\b|\bin one day\b", re.IGNORECASE)


_CUT = {"that", "which", "who", "to", "toward", "towards", "into", "near", "around", "in", "on", "at", "off", "across", "against", "while", "as"}
_CHAIN_FIRST = [(r"\b(aircraft )?carriers?\b", "ship"), (r"\b(warships?|destroyers?|frigates?|submarines?|coast guard)\b", "ship"),
                (r"\b(drones?|uavs?)\b", "drone"), (r"\b(fighter jets?|fighters?|jets?|bombers?|warplanes?|aircraft)\b", "jet")]


def _value(n: str) -> Optional[float]:
    n = n.lower().strip()
    if n in ("a", "an"):
        return 1.0
    if n in _NUMW:
        return float(_NUMW[n]) or None
    try:
        return float(n.replace(",", ""))
    except ValueError:
        return None


def _counted(text: str, stickers: Sequence[Tuple[str, str, str]]) -> List[Dict[str, Any]]:
    """Every "number + thing the icon set can draw" in the text: {name, label, shown, value, real, at}, in the script's own words."""
    items: List[Dict[str, Any]] = []
    for m in _COUNT.finditer(text or ""):
        what = m.group("what").strip()
        if _PERIOD.fullmatch(f"in {m.group('n')} {what}") or re.match(r"(hours?|days?|weeks?|months?|years?|km|kilometres?|miles?|percent)\b", what, re.I):
            continue
        words = []
        for w_ in what.split()[:6]:                                                       # the noun phrase, up to a clause word
            if words and w_.lower() in _CUT:
                break
            words.append(w_)
        chunk = _PERIOD.sub("", " ".join(words)).strip()
        rules = list(_CHAIN_FIRST) + [(rx, name) for rx, name, _lab in stickers]
        hits = [(mm.start(), i, name) for i, (rx, name) in enumerate(rules) for mm in [re.search(rx, chunk, re.IGNORECASE)] if mm]
        if not hits:
            continue
        name = min(hits)[2]                                           # the first thing the words name (a drone *from* a carrier is a drone)
        upto = re.sub(r"\s+and\s+", " & ", chunk)
        upto = re.sub(r"\s+(vessels?|units?|of them)$", "", upto, flags=re.IGNORECASE)
        n = m.group("n")
        real = n.lower() not in ("a", "an")
        shown = n.upper() if not real else n + ("+" if (m.group("pre") or "").strip().lower() in ("more than", "over", "at least") else "")
        items.append({"name": name, "label": f"{shown} {upto}".strip(), "shown": shown, "what": upto, "value": _value(n), "real": real,
                      "at": m.start("n")})
    return items


def chain_of(text: str, stickers: Sequence[Tuple[str, str, str]]) -> Optional[Dict[str, Any]]:
    """An icon chain from a sentence that counts different things (three or more, or two inside a stated period):
    each item is the script's own number and words, with the pictogram its words name. None when fewer items have a pictogram."""
    items = _counted(text, stickers)
    period = _PERIOD.search(text or "")
    if sum(1 for i in items if i["real"]) < 2 or len(items) < (2 if period else 3):
        return None
    title = period.group(0) if period else ""
    return {"items": [{"name": i["name"], "label": i["label"]} for i in items[:5]], "title": title.upper()}


_MULT = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
_UNIT_STOP = {"in", "by", "a", "an", "the", "per", "and", "to", "of", "at", "on", "over", "under", "with", "during", "after", "before", "this", "that",
              "last", "next", "when", "while", "since"}
_RISE = re.compile(
    r"(?P<subj>(?:[\w'-]+\s+){0,5}?)(?P<verb>rose|grew|jumped|soared|climbed|increased|fell|dropped|declined|shrank|went|surged|plunged|"
    r"rising|growing|jumping|falling|dropping|increasing|decreasing|decreased|ballooned|collapsed)\s+(?:\w+\s+){0,2}?from\s+"
    r"(?:about |around |roughly |just |only |nearly |some |under |fewer than |less than )?(?P<a>\d[\d,]*(?:\.\d+)?)\s*(?P<am>thousand|million|billion)?\s*"
    r"(?P<ap>%|percent)?\s*(?:(?P<aunit>(?!(?:a|an|per|in|by|and|to|the|of|on|at|over|since|after|before|during|this|last)\b)[a-z]+)\s+)?(?:in\s+(?P<ay>(?:19|20)\d\d)\s+)?to\s+(?:about |around |more than |over |nearly |some |almost )?"
    r"(?P<b>\d[\d,]*(?:\.\d+)?)\s*(?P<bm>thousand|million|billion)?\s*(?P<bp>%|percent)?(?:\s+(?P<bunit>(?!(?:a|an|per|in|by|and|to|the|of|on|at|over|since|after|before|during|this|last)\b)[a-z]+))?(?P<per>\s*\b(?:a|per)\s+(?:day|week|month|year))?"
    r"(?:[^.]*?\b(?:in|by)\s+(?P<by>(?:19|20)\d\d))?", re.IGNORECASE)


def counter_of(text: str) -> Optional[Dict[str, Any]]:
    """A figure the script says rose or fell "from X to Y" (never a date range): both values as written, years as the bar labels."""
    m = _RISE.search(text or "")
    if not m:
        return None
    va = float(m.group("a").replace(",", "")) * _MULT.get((m.group("am") or "").lower(), 1)
    vb = float(m.group("b").replace(",", "")) * _MULT.get((m.group("bm") or "").lower(), 1)
    pct = bool(m.group("ap") or m.group("bp"))
    if va == vb or (not pct and all(1900 <= v <= 2100 and float(v).is_integer() for v in (va, vb))):
        return None

    def shown(g, mult, p_):
        return g + (f" {mult}" if mult else "") + ("%" if p_ else "")

    unit = next((u for u in (m.group("aunit"), m.group("bunit")) if u and u.lower() not in _UNIT_STOP), "")
    if m.group("per"):
        unit = (unit + " " + m.group("per").strip()).strip()
    subj = [w for w in (m.group("subj") or "").split() if w.lower() not in ("the", "a", "an", "and", "its", "their", "has", "had", "have")]
    title = " ".join(subj[-4:]) if len(subj) >= 2 else (unit or "")
    return {"a": {"value": va, "shown": shown(m.group("a"), m.group("am"), pct), "label": m.group("ay") or "THEN"},
            "b": {"value": vb, "shown": shown(m.group("b"), m.group("bm"), pct), "label": m.group("by") or "NOW"},
            "unit": unit, "title": title.upper()}


_SPLIT = re.compile(r"\b(?:while|whereas|compared (?:with|to)|against|versus|vs\.?)\b|;|,?\s\bbut\b", re.IGNORECASE)
_DEMONYM = {"russian": "Russia", "ukrainian": "Ukraine", "chinese": "China", "taiwanese": "Taiwan", "american": "United States", "israeli": "Israel",
            "iranian": "Iran", "british": "United Kingdom", "french": "France", "german": "Germany", "polish": "Poland", "indian": "India",
            "pakistani": "Pakistan", "japanese": "Japan", "korean": "South Korea", "turkish": "Turkey", "syrian": "Syria"}


def _side(half: str) -> Optional[str]:
    for m in re.finditer(r"\b(?:the\s)?([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", half):
        nm = m.group(1)
        if G.find_country(nm) is not None:
            return nm
        if nm.lower() in _DEMONYM:
            return _DEMONYM[nm.lower()]
    return None


def forces_of(text: str, stickers: Sequence[Tuple[str, str, str]]) -> Optional[Dict[str, Any]]:
    """Two sides' counts of the same kinds of thing ("Russia has 3,000 tanks and 300 jets, while Ukraine has 900 tanks and 60 jets").
    A row only when both sides' figures for that thing are in the sentence; a bare second-half figure pairs with the first half in order."""
    parts = _SPLIT.split(text or "", maxsplit=1)
    if len(parts) != 2:
        return None
    la, lb = _side(parts[0]), _side(parts[1])
    if not la or not lb or la == lb:
        return None
    ia, ib = _counted(parts[0], stickers), _counted(parts[1], stickers)
    ia = [i for i in ia if i["real"] and i["value"]]
    ib = [i for i in ib if i["real"] and i["value"]]
    if ia and not ib:
        bare = [m.group(1) for m in re.finditer(r"\b(\d[\d,]*)\b(?!\s*(?:km|%|percent|hours?|days?|years?))", parts[1])
                if not 1900 <= float(m.group(1).replace(",", "")) <= 2100]
        if len(bare) == len(ia):
            ib = [dict(a_, shown=n, value=_value(n)) for a_, n in zip(ia, bare)]
    rows = []
    for a_ in ia:
        b_ = next((x for x in ib if x["name"] == a_["name"]), None)
        if b_ is None or not b_["value"]:
            continue
        rows.append({"name": a_["name"], "label": re.sub(r"^(?:\w+\s)?(?:[\w-]+\s)?", "", a_["what"]) if len(a_["what"].split()) > 2 else a_["what"],
                     "a": a_["value"], "b": b_["value"], "a_shown": a_["shown"], "b_shown": b_["shown"]})
    if not rows:
        return None
    return {"left": {"name": la}, "right": {"name": lb}, "rows": rows[:4], "title": ""}


_RANGE_CUE = re.compile(r"\b(range|reach(?:es|ed)?|strike|hit|fly|flies|within|away|radius|cover(?:s|ed)?)\b", re.IGNORECASE)
_DIST = re.compile(r"\b(\d[\d,]*)\s*(km|kilomet(?:er|re)s?|miles?)\b", re.IGNORECASE)


def range_of(text: str, places: Sequence[dict] = (), countries: Sequence[str] = ()) -> Optional[Dict[str, Any]]:
    """A reach the script states ("a range of 300 km", "can hit targets 1,000 miles away") from a place it names: the range-ring map."""
    if not _RANGE_CUE.search(text or ""):
        return None
    m = _DIST.search(text or "")
    pts = [q for q in places if isinstance(q, dict) and q.get("lat") is not None and q.get("lon") is not None]
    if not m or not pts:
        return None
    n = float(m.group(1).replace(",", ""))
    mi = m.group(2).lower().startswith("mile")
    km = n * 1.609 if mi else n
    if not 20 <= km <= 6000:
        return None
    c = pts[0]
    fill = ""
    for nm in countries:
        f = G.find_country(str(nm))
        if f is not None and not (f.bbox[0] <= float(c["lon"]) <= f.bbox[2] and f.bbox[1] <= float(c["lat"]) <= f.bbox[3]):
            fill = f.iso                                                   # the country in reach is lit, not the launcher's own
            break
    shown = f"{m.group(1)} {'miles' if mi else 'km'}"
    label = str(c.get("name") or c.get("label") or "")
    return {"centre": {"label": label, "lat": float(c["lat"]), "lon": float(c["lon"])}, "km": round(km, 1), "shown": shown,
            "title": f"{shown} from {label}" if label else shown, "sub": "", "fill": fill}


def sat_quote_of(quote: Dict[str, Any], places: Sequence[dict] = (), countries: Sequence[str] = ()) -> Optional[Dict[str, Any]]:
    """Quoted words plus the place the scene names: the quote-over-satellite card (no place, no card)."""
    q = str((quote or {}).get("quote") or "").strip()
    if len(q.split()) < 4:
        return None
    out = {"quote": q, "speaker": str(quote.get("speaker") or ""), "role": str(quote.get("role") or "")}
    pts = [x for x in places if isinstance(x, dict) and x.get("lat") is not None]
    if pts:
        out["place"] = {"label": str(pts[0].get("name") or ""), "lat": float(pts[0]["lat"]), "lon": float(pts[0]["lon"])}
        return out
    for nm in countries:
        if G.find_country(str(nm)) is not None:
            out["country"] = str(nm)
            return out
    return None


def sat_map_of(text: str, places: Sequence[dict] = (), countries: Sequence[str] = ()) -> Optional[Dict[str, Any]]:
    """A satellite crossing map when the narration names a known strait / gap, or two places it can locate with a distance stated."""
    for rx, key in _STRAIT_RX:
        if rx.search(text or ""):
            s = STRAITS[key]
            out = {"strait": key, "title": s["title"]}
            km = re.search(r"\b(\d[\d,]*)\s*(?:km|kilomet(?:er|re)s?)\b", text or "", re.IGNORECASE)
            if km:
                out["km"] = int(km.group(1).replace(",", ""))
            return out
    pts = [q for q in places if isinstance(q, dict) and q.get("lat") is not None and q.get("lon") is not None][:2]
    if len(pts) == 2 and re.search(r"\b(\d[\d,]*)\s*(?:km|kilomet(?:er|re)s?|miles?)\b|\b(between|across|from)\b", text or "", re.IGNORECASE):
        a, b = ({"label": str(q.get("name") or ""), "lat": float(q["lat"]), "lon": float(q["lon"])} for q in pts)
        if 3.0 <= _km(a, b) <= 2500.0:
            fill = ""
            for c in countries:
                f = G.find_country(str(c))
                if f is not None and f.bbox[0] - 0.3 <= b["lon"] <= f.bbox[2] + 0.3 and f.bbox[1] - 0.3 <= b["lat"] <= f.bbox[3] + 0.3:
                    fill = f.iso
            return {"a": a, "b": b, "fill": fill, "title": f"{a['label']} to {b['label']}"}
    return None
