"""Build the whole-Earth block globe asset once: coarse real elevation on a lon/lat grid, the land mask and a surface class.

    python3 tools/build_globe.py [--res 0.5]

Shared by every video in every region (globe openings, intercontinental travel, globe endings). Elevation: Terrain Tiles
on AWS Open Data (Terrarium zoom 3, 64 tiles, cached in cache/terrarium/3). Land: the app's Natural Earth land polygons.
Output worlds/_globe/: height.i16 (m), land.u8 (0 sea, 1 land), surf.u8 (0 sea, 1 grass, 2 forest, 3 desert, 4 rock,
5 snow/ice), meta.json. Row 0 = 90 N. Latitudes past Terrarium's +-85 deg are filled as polar ice or sea.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_world import DATA, HERE, fetch_tile, rasterize  # noqa: E402

Z = 3


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=float, default=0.5)
    a = p.parse_args(argv)
    res = a.res
    w, h = round(360 / res), round(180 / res)
    n = 2 ** Z
    mosaic = np.zeros((n * 256, n * 256), np.float32)
    for ty in range(n):
        for tx in range(n):
            mosaic[ty * 256:(ty + 1) * 256, tx * 256:(tx + 1) * 256] = fetch_tile(Z, tx, ty, HERE / "cache" / "terrarium")
            print(json.dumps({"event": "tile", "done": ty * n + tx + 1, "total": n * n}), flush=True)
    lons = -180 + (np.arange(w) + 0.5) * res
    lats = 90 - (np.arange(h) + 0.5) * res
    gx = ((lons + 180) / 360 * n * 256).astype(int).clip(0, n * 256 - 1)
    latc = np.clip(lats, -85.05, 85.05)
    gy = ((1 - np.log(np.tan(np.radians(latc)) + 1 / np.cos(np.radians(latc))) / math.pi) / 2 * n * 256).astype(int).clip(0, n * 256 - 1)
    elev = mosaic[gy[:, None], gx[None, :]]

    land_f = json.load(gzip.open(DATA / "land.json.gz"))["features"]
    land = rasterize(land_f, (-180, -90, 180, 90), res, w, h, lambda f: 1).astype(np.uint8)
    elev = np.where(land == 1, np.maximum(elev, 1.0), np.minimum(elev, -1.0))

    # surface class: ice by latitude and height, deserts in the dry subtropical interiors (far from the sea), forest in
    # the wet tropics and the northern forest belt, rock on high ground; a coarse but recognisable reading of the planet
    sea = land == 0
    dist = np.full((h, w), 99, np.int16)  # cells to the nearest sea, capped
    frontier = sea.copy()
    d = 0
    cur = sea.copy()
    while d < 24:
        d += 1
        grown = cur.copy()
        grown[1:, :] |= cur[:-1, :]; grown[:-1, :] |= cur[1:, :]
        grown[:, 1:] |= cur[:, :-1]; grown[:, :-1] |= cur[:, 1:]
        grown[:, 0] |= cur[:, -1]; grown[:, -1] |= cur[:, 0]
        new = grown & ~cur
        dist[new] = d
        cur = grown
    alat = np.abs(lats)[:, None] * np.ones((1, w))
    surf = np.zeros((h, w), np.uint8)
    L = land == 1
    surf[L] = 1
    surf[L & ((alat < 12) | ((alat > 50) & (alat < 66)))] = 2
    # the world's great dry regions, as lon/lat boxes (no climate dataset is bundled); coasts inside them stay green
    LON = lons[None, :] * np.ones((h, 1)); LAT = lats[:, None] * np.ones((1, w))
    for lo0, lo1, la0, la1 in [(-17, 35, 15, 32), (35, 60, 14, 32), (60, 76, 23, 36), (52, 122, 37, 48), (115, 146, -32, -19),
                               (11, 26, -29, -17), (-120, -103, 25, 37), (-72, -68, -28, -17)]:
        surf[L & (LON >= lo0) & (LON <= lo1) & (LAT >= la0) & (LAT <= la1) & (dist > 2)] = 3
    surf[L & (elev > 2600)] = 4
    surf[L & ((alat > 66) | (elev > 4200))] = 5
    surf[(lats < -62)[:, None] * np.ones((1, w), bool) & L] = 5
    out = HERE / "worlds" / "_globe"
    out.mkdir(parents=True, exist_ok=True)
    elev.astype("<i2").tofile(out / "height.i16")
    land.tofile(out / "land.u8")
    surf.tofile(out / "surf.u8")
    meta = {"id": "_globe", "res": res, "w": w, "h": h, "credits": ["Elevation: Terrain Tiles on AWS Open Data (Terrarium)", "Land: Natural Earth (public domain)"]}
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    print(json.dumps({"event": "done", "w": w, "h": h, "land_cells": int(L.sum())}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
