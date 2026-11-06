#!/usr/bin/env python3
"""Real-look data for a City Timelapse world (optional, once per city, cached): real building footprints, land use, satellite ground.

    python3 tools/build_real.py --id dubai [--kinds buildings,landuse,satellite] [--chunks 3]

Writes worlds/<id>/:
  buildings.json   [[x, z, rot, w, d, height_m], ...]  each OpenStreetMap building as its smallest rotated rectangle (metres from the
                   world centre, z south, same axes as the engine); height from the height / building:levels tags, else a size guess
  landuse.png      2048 px colour map of the ground in world space (OpenStreetMap land use, parks, sand, water-free): north edge = top
  ground_sat.jpg   2048 px satellite mosaic of the same area (Esri World Imagery: check its terms before publishing a film that uses it)
Sources: OpenStreetMap contributors (ODbL) for buildings and land use. Chunks that fail are skipped and reported; rerun to fill them.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
UA = "SemanticYTStudio-citygrow/0.1 (one-time cached fetch)"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
M_LAT, M_LON = 110574.0, 111320.0
TEX = 2048

# land use -> ground colour (dry-land palette is chosen by the page for everything the map does not cover)
LANDUSE = {
    "residential": (176, 170, 150), "commercial": (170, 166, 156), "retail": (170, 166, 156), "industrial": (160, 156, 148),
    "construction": (196, 180, 140), "brownfield": (200, 184, 146), "farmland": (160, 170, 96), "farmyard": (170, 170, 110),
    "meadow": (150, 168, 100), "grass": (132, 160, 92), "forest": (74, 112, 64), "wood": (74, 112, 64), "scrub": (150, 150, 98),
    "park": (118, 158, 92), "garden": (122, 160, 96), "golf_course": (112, 160, 86), "pitch": (130, 160, 96), "recreation_ground": (126, 160, 94),
    "sand": (226, 208, 160), "beach": (232, 216, 170), "bare_rock": (150, 142, 128), "heath": (150, 150, 100), "wetland": (130, 150, 120),
    "cemetery": (140, 160, 110), "religious": (172, 166, 150), "education": (172, 168, 154), "military": (150, 146, 132),
}


def post(url: str, query: str, timeout: int = 180) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def overpass(query: str, cache: Path, tries: int = 6) -> dict | None:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    for t in range(tries):
        for url in OVERPASS:
            try:
                data = post(url, query)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data), encoding="utf-8")
                return data
            except Exception as e:  # noqa: BLE001
                print(json.dumps({"event": "retry", "url": url.split("/")[2], "error": str(e)[:80]}), flush=True)
        time.sleep(8 * (t + 1))
    return None


class World:
    def __init__(self, wid: str):
        self.dir = HERE / "worlds" / wid
        self.meta = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        self.lon0, self.lat0 = self.meta["center"]
        self.size = float(self.meta["size_m"])
        self.half = self.size / 2
        self.kx = M_LON * math.cos(math.radians(self.lat0))

    def xz(self, lon: float, lat: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.kx, -(lat - self.lat0) * M_LAT

    def bbox(self, fx0=0.0, fy0=0.0, fx1=1.0, fy1=1.0):
        """(south, west, north, east) of a fraction of the world (fy from the north)."""
        w = self.lon0 - self.half / self.kx
        e = self.lon0 + self.half / self.kx
        n = self.lat0 + self.half / M_LAT
        s = self.lat0 - self.half / M_LAT
        return (n - (n - s) * fy1, w + (e - w) * fx0, n - (n - s) * fy0, w + (e - w) * fx1)


# ---------------------------------------------------------------- buildings

def min_rect(pts: np.ndarray):
    """Smallest rotated rectangle round the points: (cx, cz, rot, w, d). rot is the angle of the w side from the x axis."""
    hull = convex_hull(pts)
    if len(hull) < 3:
        return None
    best = None
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        c, s = math.cos(-ang), math.sin(-ang)
        r = hull @ np.array([[c, s], [-s, c]]).T
        mn, mx = r.min(axis=0), r.max(axis=0)
        area = (mx[0] - mn[0]) * (mx[1] - mn[1])
        if best is None or area < best[0]:
            best = (area, ang, mn, mx)
    _, ang, mn, mx = best
    cx, cz = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    c, s = math.cos(ang), math.sin(ang)
    return cx * c - cz * s, cx * s + cz * c, ang, mx[0] - mn[0], mx[1] - mn[1]


def convex_hull(p: np.ndarray) -> np.ndarray:
    pts = sorted(set(map(tuple, np.round(p, 2))))
    if len(pts) < 3:
        return np.array(pts)
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])  # noqa: E731
    lo, up = [], []
    for q in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    return np.array(lo[:-1] + up[:-1])


def number(v) -> float | None:
    try:
        return float(str(v).lower().replace("m", "").replace(",", ".").split(";")[0].strip())
    except (TypeError, ValueError):
        return None


def height_of(tags: dict, area: float) -> float:
    h = number(tags.get("height")) or number(tags.get("building:height"))
    if h:
        return max(2.5, h)
    lv = number(tags.get("building:levels"))
    if lv:
        return max(3.0, lv * 3.3 + 1.0)
    if area > 2500:
        return 22.0
    if area > 900:
        return 14.0
    return 7.0 if tags.get("building") not in ("garage", "shed", "roof", "kiosk") else 3.5


def build_buildings(w: World, chunks: int) -> dict:
    out, failed, seen = [], 0, set()
    for j in range(chunks):
        for i in range(chunks):
            s, we, n, e = w.bbox(i / chunks, j / chunks, (i + 1) / chunks, (j + 1) / chunks)
            q = f'[out:json][timeout:170];way["building"]({s:.5f},{we:.5f},{n:.5f},{e:.5f});out geom tags;'
            d = overpass(q, HERE / "cache" / "osm_real" / f"{w.meta['id']}_b{chunks}_{i}_{j}.json")
            print(json.dumps({"event": "buildings_chunk", "i": i, "j": j, "ok": d is not None}), flush=True)
            if d is None:
                failed += 1
                continue
            for el in d.get("elements", []):
                if el.get("type") != "way" or el["id"] in seen or len(el.get("geometry", [])) < 4:
                    continue
                seen.add(el["id"])
                pts = np.array([w.xz(g["lon"], g["lat"]) for g in el["geometry"]])
                if np.abs(pts).max() > w.half:
                    continue
                r = min_rect(pts)
                if r is None:
                    continue
                cx, cz, rot, bw, bd = r
                if bw * bd < 14:
                    continue
                out.append([round(cx, 1), round(cz, 1), round(rot, 3), round(bw, 1), round(bd, 1), round(height_of(el.get("tags", {}), bw * bd), 1)])
    (w.dir / "buildings.json").write_text(json.dumps(out), encoding="utf-8")
    return {"buildings": len(out), "chunks_failed": failed, "chunks": chunks * chunks}


# ---------------------------------------------------------------- land use

def build_landuse(w: World) -> dict:
    s, we, n, e = w.bbox()
    b = f"{s:.5f},{we:.5f},{n:.5f},{e:.5f}"
    q = (f"[out:json][timeout:170];("
         f'way["landuse"]({b});way["leisure"~"park|garden|golf_course|pitch|recreation_ground"]({b});'
         f'way["natural"~"sand|beach|scrub|wood|heath|bare_rock|grassland|wetland"]({b}););out geom tags;')
    d = overpass(q, HERE / "cache" / "osm_real" / f"{w.meta['id']}_landuse.json")
    if d is None:
        return {"landuse": "download failed"}
    img = Image.new("RGB", (TEX, TEX), (0, 0, 0))
    mask = Image.new("L", (TEX, TEX), 0)
    dr, dm = ImageDraw.Draw(img), ImageDraw.Draw(mask)
    k = TEX / w.size
    items = []
    for el in d.get("elements", []):
        t = el.get("tags", {})
        kind = t.get("landuse") or t.get("leisure") or t.get("natural")
        col = LANDUSE.get(kind)
        if not col or len(el.get("geometry", [])) < 4:
            continue
        pts = [((x + w.half) * k, (z + w.half) * k) for x, z in (w.xz(g["lon"], g["lat"]) for g in el["geometry"])]
        items.append((polygon_area(pts), pts, col))
    for _a, pts, col in sorted(items, key=lambda x: -x[0]):   # big areas first, small ones on top
        dr.polygon(pts, fill=col)
        dm.polygon(pts, fill=255)
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    rgba.save(w.dir / "landuse.png")
    return {"landuse_areas": len(items)}


def polygon_area(p) -> float:
    return abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))) / 2


# ---------------------------------------------------------------- satellite

ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180) / 360 * n, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n


def build_satellite(w: World, z: int = 15) -> dict:
    s, we, n, e = w.bbox()
    x0, y0 = tile_xy(we, n, z)
    x1, y1 = tile_xy(e, s, z)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    mos = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            cache = HERE / "cache" / "esri" / str(z) / str(tx) / f"{ty}.jpg"
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                for attempt in range(3):
                    try:
                        req = urllib.request.Request(ESRI.format(z=z, x=tx, y=ty), headers={"User-Agent": UA})
                        cache.write_bytes(urllib.request.urlopen(req, timeout=30).read())
                        break
                    except Exception:  # noqa: BLE001
                        time.sleep(1.5 * (attempt + 1))
            if cache.exists():
                mos.paste(Image.open(cache).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    box = ((x0 - tx0) * 256, (y0 - ty0) * 256, (x1 - tx0) * 256, (y1 - ty0) * 256)
    mos.crop(tuple(int(round(v)) for v in box)).resize((TEX, TEX), Image.LANCZOS).save(w.dir / "ground_sat.jpg", quality=90)
    return {"satellite_tiles": (tx1 - tx0 + 1) * (ty1 - ty0 + 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--kinds", default="buildings,landuse,satellite")
    ap.add_argument("--chunks", type=int, default=3)
    a = ap.parse_args(argv)
    w = World(a.id)
    res = {}
    kinds = set(a.kinds.split(","))
    if "satellite" in kinds:
        res.update(build_satellite(w))
    if "landuse" in kinds:
        res.update(build_landuse(w))
    if "buildings" in kinds:
        res.update(build_buildings(w, a.chunks))
    print(json.dumps({"event": "done", **res}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
