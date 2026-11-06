#!/usr/bin/env python3
"""Build a city world: real ground heights and water on a metre grid around a city centre.

    python3 tools/build_city.py --id istanbul --center 28.975,41.010 --size 8 --cell 8

Elevation: AWS Open Data "Terrain Tiles" (Terrarium PNG), zoom 14, sampled bilinearly, cached once in cache/terrarium/.
Water: OpenStreetMap through the Overpass API (coastline, lakes, river areas), cached once in cache/osm/<id>.json.
The coastline is drawn as a barrier and the sea is flood-filled from deep cells; if Overpass is unreachable the sea is
the low ground connected to the area's edge.

Writes worlds/<id>/: height.f32 (metres, row 0 = north), water.u8 (1 = water), meta.json, preview.png (hillshade).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = "SemanticYTStudio-citygrow/0.1 (one-time cached fetch)"
CREDITS = [
    "Elevation: Terrain Tiles on AWS Open Data (Mapzen Terrarium; sources include SRTM, GMTED2010, ETOPO1)",
    "Water and coastline: © OpenStreetMap contributors (ODbL)",
]
M_PER_DEG_LAT = 110574.0
M_PER_DEG_LON = 111320.0
MIN_WATER_CELLS = 48            # inland water smaller than this many cells (~3,000 m2 at 8 m) is dropped


# ---------------------------------------------------------------- grid geometry

class Grid:
    """A north-up metre grid centred on (lon0, lat0). Cell (row, col) centres; row 0 is the north edge."""

    def __init__(self, lon0: float, lat0: float, size_m: float, cell: float):
        self.lon0, self.lat0, self.cell = lon0, lat0, cell
        self.w = self.h = max(2, int(round(size_m / cell)))
        self.kx = M_PER_DEG_LON * math.cos(math.radians(lat0))
        self.half = self.w * cell / 2.0

    def lonlat_to_px(self, lon: float, lat: float) -> tuple[float, float]:
        x = (lon - self.lon0) * self.kx + self.half
        y = self.half - (lat - self.lat0) * M_PER_DEG_LAT
        return x / self.cell, y / self.cell

    def cell_lons(self) -> np.ndarray:
        x = (np.arange(self.w) + 0.5) * self.cell - self.half
        return self.lon0 + x / self.kx

    def cell_lats(self) -> np.ndarray:
        y = self.half - (np.arange(self.h) + 0.5) * self.cell
        return self.lat0 + y / M_PER_DEG_LAT

    def bbox(self, pad: float = 0.0) -> tuple[float, float, float, float]:
        dlon = (self.half + pad) / self.kx
        dlat = (self.half + pad) / M_PER_DEG_LAT
        return self.lon0 - dlon, self.lat0 - dlat, self.lon0 + dlon, self.lat0 + dlat


# ---------------------------------------------------------------- elevation

def tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


def ssl_context() -> ssl.SSLContext:
    """HTTPS checked against certifi's certificates: the installed app's Python has no system store on a Mac, and every download
    failed there with "certificate verify failed: unable to get local issuer certificate"."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def download(url: str, path: Path, data: bytes | None = None, timeout: int = 60) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
                tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
                tmp.write_bytes(r.read())
                os.replace(tmp, path)
            return path
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return path


def terrarium_tile(z: int, x: int, y: int) -> np.ndarray:
    path = download(TILE_URL.format(z=z, x=x, y=y), HERE / "cache" / "terrarium" / str(z) / str(x) / f"{y}.png")
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0 - 32768.0


def elevation(grid: Grid, z: int = 14, fetch_tile=terrarium_tile, on_tile=None) -> np.ndarray:
    """Bilinear Terrarium elevation at every cell centre (metres)."""
    gx = np.array([tile_xy(lo, 0.0, z)[0] for lo in grid.cell_lons()]) * 256.0
    gy = np.array([tile_xy(0.0, la, z)[1] for la in grid.cell_lats()]) * 256.0
    px0, py0 = int(math.floor(gx.min() - 1)), int(math.floor(gy.min() - 1))
    tx0, ty0 = px0 // 256, py0 // 256
    tx1, ty1 = int(gx.max() + 2) // 256, int(gy.max() + 2) // 256
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    total, done = (tx1 - tx0 + 1) * (ty1 - ty0 + 1), 0
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = fetch_tile(z, tx, ty)
            done += 1
            print(json.dumps({"event": "tile", "done": done, "total": total}), flush=True)
            if on_tile:
                on_tile(done, total)
    fx = gx - tx0 * 256 - 0.5
    fy = gy - ty0 * 256 - 0.5
    x0 = np.clip(np.floor(fx).astype(int), 0, mosaic.shape[1] - 2)
    y0 = np.clip(np.floor(fy).astype(int), 0, mosaic.shape[0] - 2)
    ax = np.clip(fx - x0, 0, 1)[None, :]
    ay = np.clip(fy - y0, 0, 1)[:, None]
    yy, xx = y0[:, None], x0[None, :]
    a = mosaic[yy, xx] * (1 - ax) + mosaic[yy, xx + 1] * ax
    b = mosaic[yy + 1, xx] * (1 - ax) + mosaic[yy + 1, xx + 1] * ax
    return (a * (1 - ay) + b * ay).astype(np.float32)


# ---------------------------------------------------------------- water from OSM

def overpass_query(bbox) -> str:
    s, w, n, e = bbox[1], bbox[0], bbox[3], bbox[2]
    b = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"
    return (f"[out:json][timeout:90];("
            f'way["natural"="coastline"]({b});'
            f'way["natural"="water"]({b});relation["natural"="water"]({b});'
            f'way["waterway"="riverbank"]({b});relation["waterway"="riverbank"]({b});'
            f'way["water"~"river|canal|lake|reservoir|lagoon|harbour|basin"]({b});'
            f'relation["water"~"river|canal|lake|reservoir|lagoon|harbour|basin"]({b});'
            f");out geom;")


def fetch_osm(world_id: str, bbox) -> dict:
    path = HERE / "cache" / "osm" / f"{world_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = urllib.parse.urlencode({"data": overpass_query(bbox)}).encode()
    last = None
    for url in OVERPASS_URLS:
        try:
            tmp = path.with_suffix(".part")
            if tmp.exists():
                tmp.unlink()
            download(url, tmp, data=data, timeout=120)
            doc = json.loads(tmp.read_text(encoding="utf-8"))
            os.replace(tmp, path)
            return doc
        except Exception as e:   # try the next mirror
            last = e
    raise RuntimeError(f"Overpass unreachable: {last}")


def _way_line(el) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in el.get("geometry") or [] if p]


def _join_rings(lines: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Join open way pieces end to end into rings (multipolygon members come as pieces)."""
    pieces = [list(l) for l in lines if len(l) >= 2]
    rings = []
    while pieces:
        cur = pieces.pop(0)
        grew = True
        while grew and cur[0] != cur[-1]:
            grew = False
            for i, p in enumerate(pieces):
                if p[0] == cur[-1]:
                    cur += p[1:]
                elif p[-1] == cur[-1]:
                    cur += p[::-1][1:]
                elif p[-1] == cur[0]:
                    cur = p[:-1] + cur
                elif p[0] == cur[0]:
                    cur = p[::-1][:-1] + cur
                else:
                    continue
                pieces.pop(i)
                grew = True
                break
        if len(cur) >= 4:
            rings.append(cur)
    return rings


def water_features(doc: dict) -> tuple[list, list]:
    """(coastlines as polylines, water areas as (outer rings, inner rings)) from an Overpass `out geom` answer."""
    coast, areas = [], []
    for el in doc.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "way":
            line = _way_line(el)
            if tags.get("natural") == "coastline":
                coast.append(line)
            elif len(line) >= 4 and line[0] == line[-1]:
                areas.append(([line], []))
        elif el["type"] == "relation":
            outer = [_way_line(m) for m in el.get("members", []) if m.get("type") == "way" and m.get("role") != "inner"]
            inner = [_way_line(m) for m in el.get("members", []) if m.get("type") == "way" and m.get("role") == "inner"]
            areas.append((_join_rings(outer), _join_rings(inner)))
    return coast, areas


def flood(open_: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """Cells reachable from `seeds` through `open_` cells (4-neighbour)."""
    h, w = open_.shape
    out = seeds & open_
    q = deque(map(tuple, np.argwhere(out)))
    while q:
        r, c = q.popleft()
        for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= rr < h and 0 <= cc < w and open_[rr, cc] and not out[rr, cc]:
                out[rr, cc] = True
                q.append((rr, cc))
    return out


def sea_mask(elev: np.ndarray, barrier: np.ndarray, deep: float = -2.0) -> np.ndarray:
    """Flood-fill the sea from deep cells, never crossing the coastline barrier or land above 3 m."""
    open_ = (~barrier) & (elev < 3.0)
    sea = flood(open_, elev < deep)
    if barrier.any():   # barrier cells join the side most of their open neighbours are on
        n = np.zeros(elev.shape, np.int32)
        k = np.zeros(elev.shape, np.int32)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            n += np.roll(sea, (dr, dc), (0, 1))
            k += np.roll(~barrier, (dr, dc), (0, 1))
        sea |= barrier & (n * 2 > k)
    return sea


def edge_sea(elev: np.ndarray, level: float = 0.5) -> np.ndarray:
    """Fallback without OSM: low ground connected to the area's edge."""
    low = elev <= level
    edge = np.zeros_like(low)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    return flood(low, edge)


def rasterize_water(grid: Grid, coast, areas) -> tuple[np.ndarray, np.ndarray]:
    """(coast barrier, water areas) as boolean grids."""
    bimg = Image.new("L", (grid.w, grid.h), 0)
    bd = ImageDraw.Draw(bimg)
    for line in coast:
        pts = [grid.lonlat_to_px(lo, la) for lo, la in line]
        if len(pts) >= 2:
            bd.line(pts, fill=1, width=2)
    aimg = Image.new("L", (grid.w, grid.h), 0)
    ad = ImageDraw.Draw(aimg)
    for outers, inners in areas:
        for ring in outers:
            ad.polygon([grid.lonlat_to_px(lo, la) for lo, la in ring], fill=1)
        for ring in inners:
            ad.polygon([grid.lonlat_to_px(lo, la) for lo, la in ring], fill=0)
    return np.asarray(bimg, bool), np.asarray(aimg, bool)


# ---------------------------------------------------------------- inland water levels

def components(mask: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """4-connected labels of a boolean mask (0 = background) and each label's size."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    sizes = [0]
    for r0, c0 in np.argwhere(mask):
        if lab[r0, c0]:
            continue
        k = len(sizes); lab[r0, c0] = k; n = 0
        q = deque([(r0, c0)])
        while q:
            r, c = q.popleft(); n += 1
            for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= rr < h and 0 <= cc < w and mask[rr, cc] and not lab[rr, cc]:
                    lab[rr, cc] = k; q.append((rr, cc))
        sizes.append(n)
    return lab, sizes


def _shift_min(a: np.ndarray, r: int) -> np.ndarray:
    out = a.copy()
    for dr in range(-r, r + 1):
        for dc in range(-r, r + 1):
            out = np.minimum(out, np.roll(np.roll(a, dr, 0), dc, 1))
    return out


def inland_levels(elev: np.ndarray, inland: np.ndarray, radius: int = 4, passes: int = 40) -> np.ndarray:
    """Surface height for river and lake cells: just under the lowest nearby bank, filled across wide water, smoothed."""
    land_h = np.where(inland, np.inf, elev).astype(np.float64)
    bank = _shift_min(land_h, radius)
    level = np.where(inland & np.isfinite(bank), bank - 1.0, np.nan)
    for _ in range(passes):          # wide water: take the neighbours' mean until every water cell has a level
        missing = inland & np.isnan(level)
        if not missing.any():
            break
        acc = np.zeros_like(level); cnt = np.zeros_like(level)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            v = np.roll(np.roll(level, dr, 0), dc, 1); ok = ~np.isnan(v)
            acc[ok] += v[ok]; cnt[ok] += 1
        fill = missing & (cnt > 0)
        level[fill] = acc[fill] / cnt[fill]
    level[inland & np.isnan(level)] = float(np.nanmin(level)) if np.isfinite(np.nanmin(level)) else 0.0
    for _ in range(6):               # a river surface runs smooth along its length
        acc = level.copy(); cnt = np.ones_like(level)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            v = np.roll(np.roll(level, dr, 0), dc, 1); ok = inland & ~np.isnan(v)
            acc[ok] += v[ok]; cnt[ok] += 1
        level = np.where(inland, acc / cnt, level)
    return np.where(inland, np.maximum(level, 0.2), 0.0).astype(np.float32)


# ---------------------------------------------------------------- streets from OSM

ROAD_CLASS = {"motorway": 1, "trunk": 1, "primary": 1, "secondary": 2, "tertiary": 2, "unclassified": 3,
              "residential": 3, "living_street": 3, "pedestrian": 3}


def roads_query(bbox) -> str:
    s, w, n, e = bbox[1], bbox[0], bbox[3], bbox[2]
    kinds = "|".join(ROAD_CLASS)
    return f'[out:json][timeout:180];way["highway"~"^({kinds})$"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});out geom;'


def fetch_roads(world_id: str, bbox) -> dict:
    path = HERE / "cache" / "osm" / f"{world_id}_roads.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = urllib.parse.urlencode({"data": roads_query(bbox)}).encode()
    last = None
    for url in OVERPASS_URLS:
        try:
            tmp = path.with_suffix(".part")
            if tmp.exists():
                tmp.unlink()
            download(url, tmp, data=data, timeout=240)
            doc = json.loads(tmp.read_text(encoding="utf-8"))
            os.replace(tmp, path)
            return doc
        except Exception as e:
            last = e
    raise RuntimeError(f"Overpass unreachable: {last}")


def road_lines(doc: dict, grid: Grid, water: np.ndarray) -> list[dict]:
    """Streets in metres from the centre (x east, z south), cut where they cross water (bridges are not streets)."""
    out = []
    for el in doc.get("elements", []):
        cls = ROAD_CLASS.get(el.get("tags", {}).get("highway"))
        if not cls or el.get("tags", {}).get("bridge") or el.get("tags", {}).get("tunnel"):
            continue
        run = []
        pts = [grid.lonlat_to_px(lo, la) for lo, la in _way_line(el)]
        dense = pts[:1]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):   # a point every cell, so a street is cut where it meets water
            n = max(1, int(math.hypot(bx - ax, by - ay)))
            dense += [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(1, n + 1)]
        for i, (px, py) in enumerate(dense):
            if 0 < i < len(dense) - 1 and run and i % 4:   # keep every 4th dense point (and all cut points)
                ok = 0 <= px < grid.w and 0 <= py < grid.h and not water[int(py), int(px)]
                if ok:
                    continue
            inside = 0 <= px < grid.w and 0 <= py < grid.h and not water[int(py), int(px)]
            if inside:
                run.append([round(px * grid.cell - grid.half, 1), round(py * grid.cell - grid.half, 1)])
            elif len(run) >= 2:
                out.append({"c": cls, "p": run}); run = []
            else:
                run = []
        if len(run) >= 2:
            out.append({"c": cls, "p": run})
    return out


# ---------------------------------------------------------------- preview

def hillshade(elev: np.ndarray, water: np.ndarray, cell: float) -> Image.Image:
    gy, gx = np.gradient(elev.astype(np.float64), cell)
    slope = np.arctan(np.hypot(gx, gy) * 2.0)
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)
    shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    top = max(float(elev.max()), 1.0)
    t = np.clip(elev / top, 0, 1)[..., None]
    land = (np.array([120, 150, 90]) * (1 - t) + np.array([200, 190, 160]) * t) * (0.45 + 0.65 * shade[..., None])
    depth = np.clip(-elev / 60.0, 0, 1)[..., None]
    sea = np.array([90, 160, 200]) * (1 - depth) + np.array([30, 80, 130]) * depth
    rgb = np.where(water[..., None], sea, land)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------- build

def build(world_id: str, center: tuple[float, float], size_km: float = 8.0, cell: float = 8.0, zoom: int = 14,
          fetch_tile=terrarium_tile, osm_fetch=fetch_osm, roads_fetch=fetch_roads, out_root: Path | None = None, on_tile=None, landuse_fetch=None) -> Path:
    grid = Grid(center[0], center[1], size_km * 1000.0, cell)
    out = (out_root or HERE / "worlds") / world_id
    out.mkdir(parents=True, exist_ok=True)
    elev = elevation(grid, zoom, fetch_tile, on_tile)
    warnings = []
    try:
        coast, areas = water_features(osm_fetch(world_id, grid.bbox(pad=200)))
        barrier, inland = rasterize_water(grid, coast, areas)
        sea = sea_mask(elev, barrier) if coast else np.zeros_like(barrier)
        if coast and not sea.any():
            warnings.append("coastline found but no deep water cells to start the sea from; used the edge fallback")
            sea = edge_sea(elev)
        inland &= ~sea
        lab, sizes = components(inland)          # fountains and garden pools are not lakes
        small = np.array([n < MIN_WATER_CELLS for n in sizes])
        inland &= ~small[lab]
        water = sea | inland
        source = "osm"
    except Exception as e:
        warnings.append(f"OSM water unavailable ({e}); sea = low ground connected to the edge")
        water = edge_sea(elev)
        sea, inland = water, np.zeros_like(water)
        source = "elevation"
    level = inland_levels(elev, inland) if inland.any() else np.zeros(elev.shape, np.float32)
    elev = np.where(sea, np.minimum(elev, -1.0), np.where(inland, np.minimum(elev, level - 2.5), np.maximum(elev, 0.5))).astype(np.float32)
    level.astype("<f4").tofile(out / "water_level.f32")
    elev.astype("<f4").tofile(out / "height.f32")
    water.astype(np.uint8).tofile(out / "water.u8")
    try:
        roads = road_lines(roads_fetch(world_id, grid.bbox()), grid, water)
    except Exception as e:
        warnings.append(f"OSM streets unavailable ({e}); the city will lay out its own lanes")
        roads = []
    (out / "roads.json").write_text(json.dumps(roads, separators=(",", ":")), encoding="utf-8")
    img = hillshade(elev, water, cell)
    d = ImageDraw.Draw(img)
    for r in roads:
        d.line([((x + grid.half) / cell, (z + grid.half) / cell) for x, z in r["p"]], fill=(90, 70, 60), width=1)
    img.save(out / "preview.png")
    # land use (parks, farmland, sand, built-up) colours the ground and decides where trees stand; without it the look follows the climate rule
    landuse = False
    try:
        from importlib import util as _u
        _spec = _u.spec_from_file_location("ctl_build_real", HERE / "tools" / "build_real.py")
        real = _u.module_from_spec(_spec)
        _spec.loader.exec_module(real)
        lw = real.World(world_id, {"id": world_id, "center": [center[0], center[1]], "size_m": grid.w * cell}, out)
        landuse = "landuse_areas" in (real.build_landuse(lw, fetch=landuse_fetch) if landuse_fetch is not False else {})
        if not landuse:
            warnings.append("land use unavailable: the ground colour follows the climate rule")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"land use unavailable ({str(e)[:80]}): the ground colour follows the climate rule")
    meta = {"id": world_id, "center": [center[0], center[1]], "size_m": grid.w * cell, "cell": cell, "landuse": landuse,
            "w": grid.w, "h": grid.h, "zoom": zoom, "water_source": source, "warnings": warnings,
            "elev_min": float(elev.min()), "elev_max": float(elev.max()),
            "water_share": round(float(water.mean()), 4), "inland_share": round(float(inland.mean()), 4),
            "border_water": round(float(np.concatenate([water[0], water[-1], water[:, 0], water[:, -1]]).mean()), 3), "roads": len(roads), "credits": CREDITS, "built": time.strftime("%Y-%m-%d")}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    for wmsg in warnings:
        print(json.dumps({"event": "warning", "message": wmsg}), flush=True)
    print(json.dumps({"event": "done", "dir": str(out), "w": grid.w, "h": grid.h, "water_share": meta["water_share"],
                      "elev_range": [meta["elev_min"], meta["elev_max"]]}), flush=True)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--center", required=True, help="lon,lat")
    p.add_argument("--size", type=float, default=8.0, help="km across (square)")
    p.add_argument("--cell", type=float, default=8.0, help="metres per cell")
    p.add_argument("--zoom", type=int, default=14)
    a = p.parse_args(argv)
    lon, lat = (float(v) for v in a.center.split(","))
    build(a.id, (lon, lat), a.size, a.cell, a.zoom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
