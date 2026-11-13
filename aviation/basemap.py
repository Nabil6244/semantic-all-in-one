"""Dark relief basemap for the Aviation flight maps (docs/aviation/PLAN.md N5): Web-Mercator helpers and a hillshade of free elevation.

    fit_bbox(points[(lat, lon)], pad, aspect) -> (lon0, lat0, lon1, lat1) fitted to the frame's aspect in Mercator
    merc(lon, lat) -> (x, y) in 0..1 of the world, y down          to_px(bbox, lat, lon, w, h) -> frame pixel
    zoom_for(bbox, width_px) -> tile zoom                            relief(bbox, size, fetch_tile=None, cache=None) -> RGB image

Elevation: Terrain Tiles on AWS Open Data (Mapzen Terrarium; sources include SRTM, GMTED2010, ETOPO1), the same tiles citygrow-engine
uses. Each tile is fetched once and kept in the per-user map cache (aviation/terrarium/z/x/y.npy), so a place costs one download
for all future videos. If a tile cannot be had the map still draws (that part is plain dark), it never stops a render.
The look: hillshade lit from the north-west, grey-blue, mountains lighter, water near black - the reference's night-satellite feel.
"""

from __future__ import annotations

import io
import math
import os
import threading
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageFilter

TILE = 256
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
SAT_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
SAT_CREDIT = "Sentinel-2 cloudless 2016 by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016), CC BY 4.0"
CREDIT = "Elevation: Terrain Tiles (AWS Open Data / Mapzen Terrarium) · Imagery: " + SAT_CREDIT
_UA = "video-generator-aviation/1.0"
_MEMO: "OrderedDict[tuple, Image.Image]" = OrderedDict()
_LOCK = threading.Lock()

BBox = Tuple[float, float, float, float]


# ---------------------------------------------------------------------------------------------------------------- projection

def merc(lon: float, lat: float) -> Tuple[float, float]:
    lat = max(-85.0, min(85.0, lat))
    x = (lon + 180.0) / 360.0
    y = (1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0
    return x, y


def unmerc(x: float, y: float) -> Tuple[float, float]:
    lon = x * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y))))
    return lon, lat


def fit_bbox(points: Sequence[Tuple[float, float]], pad: float = 0.15, aspect: float = 16 / 9, min_km: float = 60.0) -> BBox:
    """Smallest box of the given aspect holding every (lat, lon), padded by `pad` of its size, never narrower than min_km."""
    xs, ys = zip(*(merc(lon, lat) for lat, lon in points))
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w, h = (max(xs) - min(xs)) * (1 + 2 * pad), (max(ys) - min(ys)) * (1 + 2 * pad)
    lat_c = unmerc(cx, cy)[1]
    min_w = min_km / (40075.0 * math.cos(math.radians(lat_c)))
    w = max(w, min_w, h * aspect)
    h = w / aspect
    lon0, lat1 = unmerc(cx - w / 2, cy - h / 2)
    lon1, lat0 = unmerc(cx + w / 2, cy + h / 2)
    return lon0, lat0, lon1, lat1


def bbox_merc(bb: BBox) -> Tuple[float, float, float, float]:
    x0, y0 = merc(bb[0], bb[3])
    x1, y1 = merc(bb[2], bb[1])
    return x0, y0, x1, y1


def to_px(bb: BBox, lat: float, lon: float, w: int, h: int) -> Tuple[float, float]:
    x0, y0, x1, y1 = bbox_merc(bb)
    x, y = merc(lon, lat)
    return (x - x0) / (x1 - x0) * w, (y - y0) / (y1 - y0) * h


def scale_bbox(bb: BBox, k: float, dx: float = 0.0, dy: float = 0.0) -> BBox:
    """The box shrunk (k < 1, zoom in) or grown around its centre, shifted by dx, dy in fractions of its size."""
    x0, y0, x1, y1 = bbox_merc(bb)
    cx, cy = (x0 + x1) / 2 + dx * (x1 - x0), (y0 + y1) / 2 + dy * (y1 - y0)
    w, h = (x1 - x0) * k, (y1 - y0) * k
    lon0, lat1 = unmerc(cx - w / 2, cy - h / 2)
    lon1, lat0 = unmerc(cx + w / 2, cy + h / 2)
    return lon0, lat0, lon1, lat1


def km_per_px(bb: BBox, w: int) -> float:
    x0, y0, x1, y1 = bbox_merc(bb)
    lat_c = unmerc((x0 + x1) / 2, (y0 + y1) / 2)[1]
    return (x1 - x0) * 40075.0 * math.cos(math.radians(lat_c)) / w


def zoom_for(bb: BBox, width_px: int) -> int:
    x0, _, x1, _ = bbox_merc(bb)
    frac = max(1e-9, x1 - x0)
    return int(max(3, min(11, math.ceil(math.log2(width_px / (TILE * frac))))))


# ---------------------------------------------------------------------------------------------------------------- elevation

def default_cache() -> Path:
    try:
        from map_scene.render import cache_dir
        return cache_dir() / "aviation"
    except Exception:
        return Path.home() / ".cache" / "video-generator" / "aviation"


def terrarium_tile(z: int, x: int, y: int) -> np.ndarray:
    req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        a = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB"), dtype=np.float32)
    return a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0 - 32768.0


def sat_tile(z: int, x: int, y: int) -> np.ndarray:
    req = urllib.request.Request(SAT_URL.format(z=z, x=x, y=y), headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB"), dtype=np.uint8)


def _sat(z: int, x: int, y: int, fetch: Callable, cache: Path) -> Optional[np.ndarray]:
    n = 2 ** z
    x %= n
    if not 0 <= y < n:
        return None
    f = cache / "s2cloudless" / str(z) / str(x) / f"{y}.jpg"
    if f.exists():
        try:
            return np.asarray(Image.open(f).convert("RGB"), dtype=np.uint8)
        except Exception:  # noqa: BLE001
            pass
    try:
        a = np.asarray(fetch(z, x, y), dtype=np.uint8)
    except Exception:
        return None
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(a).save(f, quality=90)
    except OSError:
        pass
    return a


def imagery(bb: BBox, size: Tuple[int, int], fetch_sat: Callable, cache: Optional[Path] = None) -> Optional[np.ndarray]:
    """Satellite imagery for the box (h, w, 3) float, or None when no tile could be had."""
    cache = Path(cache) if cache else default_cache()
    w, h = size
    z = min(12, zoom_for(bb, w))                               # the same detail as the frame: 4x fewer tiles than one level finer
    n = 2 ** z
    x0, y0, x1, y1 = bbox_merc(bb)
    tx0, tx1 = int(math.floor(x0 * n)), int(math.floor(x1 * n))
    ty0, ty1 = int(math.floor(y0 * n)), int(math.floor(y1 * n))
    mosaic = np.zeros(((ty1 - ty0 + 1) * TILE, (tx1 - tx0 + 1) * TILE, 4), dtype=np.uint8)     # alpha = this tile came
    got = 0
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            a = _sat(z, tx, ty, fetch_sat, cache)
            if a is not None and a.shape[:2] == (TILE, TILE):
                mosaic[(ty - ty0) * TILE:(ty - ty0 + 1) * TILE, (tx - tx0) * TILE:(tx - tx0 + 1) * TILE, :3] = a[..., :3]
                mosaic[(ty - ty0) * TILE:(ty - ty0 + 1) * TILE, (tx - tx0) * TILE:(tx - tx0 + 1) * TILE, 3] = 255
                got += 1
    if not got:
        return None
    px0, py0 = (x0 * n - tx0) * TILE, (y0 * n - ty0) * TILE
    px1, py1 = (x1 * n - tx0) * TILE, (y1 * n - ty0) * TILE
    im = Image.fromarray(mosaic, "RGBA").transform((w, h), Image.EXTENT, (px0, py0, px1, py1), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32)                    # (h, w, 4): the 4th channel says where imagery exists


def _tile(z: int, x: int, y: int, fetch: Callable, cache: Path) -> Optional[np.ndarray]:
    n = 2 ** z
    x %= n
    if not 0 <= y < n:
        return None
    f = cache / "terrarium" / str(z) / str(x) / f"{y}.npy"
    if f.exists():
        try:
            return np.load(f).astype(np.float32)
        except (OSError, ValueError):
            pass
    try:
        a = np.asarray(fetch(z, x, y), dtype=np.float32)
    except Exception:
        return None                                    # offline or missing: that part of the map is plain dark
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.stem}.{os.getpid()}.tmp.npy")
        np.save(tmp, a.astype(np.float16))
        os.replace(tmp, f)
    except OSError:
        pass
    return a


def _from_parent(z: int, x: int, y: int, fetch: Callable, cache: Path, up: int = 3) -> Optional[np.ndarray]:
    """The part of a coarser tile (1-3 levels up) that covers tile (z, x, y), enlarged to a full tile."""
    for k in range(1, up + 1):
        if z - k < 0:
            break
        p = _tile(z - k, x >> k, y >> k, fetch, cache)
        if p is None or p.shape != (TILE, TILE):
            continue
        span = TILE >> k
        ox, oy = (x - ((x >> k) << k)) * span, (y - ((y >> k) << k)) * span
        part = np.ascontiguousarray(p[oy:oy + span, ox:ox + span], dtype=np.float32)
        return np.asarray(Image.fromarray(part, mode="F").resize((TILE, TILE), Image.BILINEAR), dtype=np.float32)
    return None


def elevation(bb: BBox, size: Tuple[int, int], fetch_tile: Optional[Callable] = None, cache: Optional[Path] = None) -> np.ndarray:
    fetch = fetch_tile or terrarium_tile
    cache = Path(cache) if cache else default_cache()
    w, h = size
    z = zoom_for(bb, w)
    n = 2 ** z
    x0, y0, x1, y1 = bbox_merc(bb)
    tx0, tx1 = int(math.floor(x0 * n)), int(math.floor(x1 * n))
    ty0, ty1 = int(math.floor(y0 * n)), int(math.floor(y1 * n))
    mosaic = np.zeros(((ty1 - ty0 + 1) * TILE, (tx1 - tx0 + 1) * TILE), dtype=np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            a = _tile(z, tx, ty, fetch, cache)
            if a is None or a.shape != (TILE, TILE):
                a = _from_parent(z, tx, ty, fetch, cache)      # a tile that did not come: its coarser parent, never a black square
            if a is not None and a.shape == (TILE, TILE):
                mosaic[(ty - ty0) * TILE:(ty - ty0 + 1) * TILE, (tx - tx0) * TILE:(tx - tx0 + 1) * TILE] = a
    # crop the mosaic to the box, resample to the wanted size
    px0, py0 = (x0 * n - tx0) * TILE, (y0 * n - ty0) * TILE
    px1, py1 = (x1 * n - tx0) * TILE, (y1 * n - ty0) * TILE
    im = Image.fromarray(mosaic, mode="F").transform((w, h), Image.EXTENT, (px0, py0, px1, py1), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32)


# ---------------------------------------------------------------------------------------------------------------- relief

def shade(elev: np.ndarray, metres_per_px: float, exaggerate: float = 2.5, azimuth: float = 315.0, altitude: float = 40.0) -> np.ndarray:
    gy, gx = np.gradient(elev * exaggerate, metres_per_px)
    slope = np.pi / 2.0 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(360.0 - azimuth + 90.0), math.radians(altitude)
    s = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return np.clip(s, 0.0, 1.0)


def relief(bb: BBox, size: Tuple[int, int], fetch_tile: Optional[Callable] = None, cache: Optional[Path] = None,
           fetch_sat: Optional[Callable] = None) -> Image.Image:
    """The dark map: hillshade of the elevation, and (when imagery can be had) the satellite picture muted, darkened and lit by that
    hillshade - the reference's night-satellite look. Imagery is fetched by default only on the real path (no fake elevation given)."""
    if fetch_sat is None and fetch_tile is None:
        fetch_sat = sat_tile
    key = (tuple(round(v, 5) for v in bb), tuple(size), id(fetch_tile) if fetch_tile else 0, str(cache or ""), id(fetch_sat) if fetch_sat else 0)
    with _LOCK:
        if key in _MEMO:
            _MEMO.move_to_end(key)
            return _MEMO[key]
    w, h = size
    e = elevation(bb, size, fetch_tile, cache)
    mpp = km_per_px(bb, w) * 1000.0
    s = shade(e, mpp)
    land = e > 0.5
    high = np.clip(e / 5000.0, 0.0, 1.0)
    # flat ground (shade ~0.64) stays dark; only slopes facing the light and high peaks come up
    v = 20.0 + 105.0 * s ** 2.2 + 70.0 * high * s
    v = np.where(land, v, 14.0)                                # water / no data: near black
    rgb = np.stack([v * 0.90, v * 0.95, v * 1.04 + 4.0], axis=-1)
    sat = imagery(bb, size, fetch_sat, cache) if fetch_sat is not None else None
    if sat is not None:
        cover = (sat[..., 3:4] / 255.0)                         # a tile that did not come leaves the relief there (no dark squares)
        sat = sat[..., :3]
        lum = sat.mean(axis=2, keepdims=True)
        muted = lum + (sat - lum) * 0.35                       # most of the colour out: a blue-grey night satellite
        lit = muted * (0.45 + 0.85 * s[..., None]) * 0.62      # lit by the hillshade, then darkened
        lit *= np.array([0.90, 0.96, 1.08], dtype=np.float32)
        mixed = 0.62 * lit + 0.38 * rgb
        rgb = np.where(land[..., None], cover * mixed + (1 - cover) * rgb, rgb)
    # a soft vignette keeps the eye in the middle
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    rgb *= np.clip(1.08 - 0.32 * r ** 2, 0.55, 1.0)[..., None]
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.SMOOTH)
    with _LOCK:
        _MEMO[key] = img
        while len(_MEMO) > 16:
            _MEMO.popitem(last=False)
    return img
