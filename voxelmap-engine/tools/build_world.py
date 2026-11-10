"""Build a reusable block-world asset for a region: real elevation, a coastline mask and region ids, on a lon/lat grid.

    python3 tools/build_world.py --id indochina --bbox 92,5,112,25 --res 0.025

Built once per region and reused by every video set there; the renderer never touches the network.

Elevation and sea depth: AWS Open Data "Terrain Tiles" (Terrarium PNG, https://registry.opendata.aws/terrain-tiles/),
fetched once into cache/terrarium/ and kept. Coastlines, countries and provinces: the app's bundled Natural Earth data
(map_scene/data/*.json.gz). Output in worlds/<id>/:
    height.i16   int16 metres per cell, row 0 = north edge (sea floor negative)
    land.u8      1 = land (Natural Earth land polygons), 0 = sea
    region.u16   index into meta.regions (provinces / states), 0 = none
    meta.json    bbox, res, w, h, regions [{i, iso, name, lon, lat}], credits
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent
DATA = REPO / "map_scene" / "data"
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
UA = "SemanticYTStudio-voxelmap/0.1 (one-time cached fetch)"
CREDITS = [
    "Elevation: Terrain Tiles on AWS Open Data (Mapzen Terrarium; sources include SRTM, GMTED2010, ETOPO1)",
    "Coastlines, countries and provinces: Natural Earth (public domain)",
]


def tile_xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


def tile_index(v: float, z: int) -> int:
    """A tile column/row number kept on the map: lon 180 (or a padded box past the edge) lands one past the last
    tile, which the server answers with 404."""
    return min(max(int(math.floor(v)), 0), 2 ** z - 1)


def download_tile(z: int, x: int, y: int, cache: Path) -> Path:
    """The elevation tile's file in the cache, downloaded when it is not there yet."""
    path = cache / str(z) / str(x) / f"{y}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": UA})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")   # atomic: parallel tile builders share this cache
                    tmp.write_bytes(r.read())
                    os.replace(tmp, path)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        time.sleep(0.05)
    return path


def fetch_tile(z: int, x: int, y: int, cache: Path) -> np.ndarray:
    path = download_tile(z, x, y, cache)
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return a[..., 0] * 256.0 + a[..., 1] + a[..., 2] / 256.0 - 32768.0


def elevation_grid(bbox, res, z, cache, on_tile=None) -> np.ndarray:
    lon0, lat0, lon1, lat1 = bbox
    w, h = round((lon1 - lon0) / res), round((lat1 - lat0) / res)
    x0, y0 = tile_xy(lon0, lat1, z)
    x1, y1 = tile_xy(lon1, lat0, z)
    tx0, ty0, tx1, ty1 = tile_index(x0, z), tile_index(y0, z), tile_index(x1, z), tile_index(y1, z)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    total = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    done = 0
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = fetch_tile(z, tx, ty, cache)
            done += 1
            print(json.dumps({"event": "tile", "done": done, "total": total}), flush=True)
            if on_tile:
                on_tile(done, total)      # may raise to stop (the app's Stop button); meta.json is not written then
    lons = lon0 + (np.arange(w) + 0.5) * res
    lats = lat1 - (np.arange(h) + 0.5) * res
    gx = np.array([tile_xy(lo, 0, z)[0] for lo in lons])
    gy = np.array([tile_xy(0, la, z)[1] for la in lats])
    px = np.clip(((gx - tx0) * 256).astype(int), 0, mosaic.shape[1] - 1)
    py = np.clip(((gy - ty0) * 256).astype(int), 0, mosaic.shape[0] - 1)
    return mosaic[py[:, None], px[None, :]]


def _rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def rasterize(features, bbox, res, w, h, value_of) -> np.ndarray:
    """Paint each feature's polygons (holes cut out) into a w x h grid; later features win."""
    lon0, _, _, lat1 = bbox
    img = Image.new("I", (w, h), 0)
    d = ImageDraw.Draw(img)
    for f in features:
        v = value_of(f)
        if not v:
            continue
        for poly in _rings(f["g"]):
            for k, ring in enumerate(poly):
                pts = [((lo - lon0) / res, (lat1 - la) / res) for lo, la in ring]
                if len(pts) >= 3:
                    d.polygon(pts, fill=v if k == 0 else 0)
    return np.asarray(img, dtype=np.int64)


def overlaps(f, bbox) -> bool:
    lon0, lat0, lon1, lat1 = bbox
    for poly in _rings(f["g"]):
        ring = np.asarray(poly[0])
        if ring[:, 0].max() >= lon0 and ring[:, 0].min() <= lon1 and ring[:, 1].max() >= lat0 and ring[:, 1].min() <= lat1:
            return True
    return False


def build(world_id: str, bbox, res: float, z: int, on_tile=None) -> Path:
    out = HERE / "worlds" / world_id
    out.mkdir(parents=True, exist_ok=True)
    lon0, lat0, lon1, lat1 = bbox
    w, h = round((lon1 - lon0) / res), round((lat1 - lat0) / res)
    elev = elevation_grid(bbox, res, z, HERE / "cache" / "terrarium", on_tile)

    land_f = [f for f in json.load(gzip.open(DATA / "land.json.gz"))["features"] if overlaps(f, bbox)]
    land = rasterize(land_f, bbox, res, w, h, lambda f: 1).astype(np.uint8)

    adm = [f for f in json.load(gzip.open(DATA / "admin1.json.gz"))["features"] if overlaps(f, bbox)]
    regions = []
    for i, f in enumerate(adm, start=1):
        ring = np.asarray(max((p[0] for p in _rings(f["g"])), key=len))
        regions.append({"i": i, "iso": f.get("iso", ""), "name": f.get("n", ""),
                        "lon": round(float(ring[:, 0].mean()), 3), "lat": round(float(ring[:, 1].mean()), 3)})
    idx = {id(f): i for i, f in enumerate(adm, start=1)}
    region = rasterize(adm, bbox, res, w, h, lambda f: idx[id(f)]).astype(np.uint16)
    region[land == 0] = 0

    # land never sits below sea level in a block world, and the sea never rises above it
    elev = np.where(land == 1, np.maximum(elev, 1.0), np.minimum(elev, -1.0))
    elev.astype("<i2").tofile(out / "height.i16")
    land.tofile(out / "land.u8")
    region.astype("<u2").tofile(out / "region.u16")
    meta = {"id": world_id, "bbox": list(bbox), "res": res, "w": w, "h": h, "regions": regions, "credits": CREDITS,
            "elev_min": float(elev.min()), "elev_max": float(elev.max()), "built": time.strftime("%Y-%m-%d")}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"event": "done", "dir": str(out), "w": w, "h": h, "regions": len(regions),
                      "land_cells": int(land.sum()), "elev_range": [meta["elev_min"], meta["elev_max"]]}), flush=True)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--bbox", required=True, help="lon0,lat0,lon1,lat1")
    p.add_argument("--res", type=float, default=0.025, help="degrees per block")
    p.add_argument("--zoom", type=int, default=7, help="Terrarium tile zoom")
    a = p.parse_args(argv)
    build(a.id, tuple(float(v) for v in a.bbox.split(",")), a.res, a.zoom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
