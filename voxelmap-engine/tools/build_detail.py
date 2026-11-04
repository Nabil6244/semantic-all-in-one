"""Build the detail tiles (levels 1 and 2, see lib/lod.mjs) a story's camera needs, from real elevation.

    node render.mjs story.csv --prepare        (plans the tiles, then runs this)
    python3 tools/build_detail.py --world indochina --needs worlds/indochina/needs_<story>.json

Only the listed tiles are built; a tile on disk is never rebuilt. Elevation: Terrain Tiles on AWS Open Data (Terrarium),
zoom 9 for level 1 and zoom 10 (~150 m, close to level 2's 175 m blocks) for level 2, cached in cache/terrarium/. Land and provinces: the app's Natural Earth data,
rasterised at the tile's resolution with the same province numbering as the world. Rivers: from the elevation itself
(D8 flow accumulation on the tile plus a margin), so no river dataset is needed.

Tile file worlds/<id>/L<level>/<tx>_<tz>.bin: int16 elevation (m), uint8 land (0 sea, 1 land, 2 river), uint16 region,
160 x 160 each, row 0 = north edge.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_world import DATA, HERE, elevation_grid, overlaps, rasterize  # noqa: E402

TILE = 160
PAD = 16
LEVELS = {1: {"k": 4, "cells": 40, "zoom": 9, "river_acc": 260}, 2: {"k": 16, "cells": 10, "zoom": 10, "river_acc": 1400}}


def flow_rivers(elev: np.ndarray, land: np.ndarray, threshold: int) -> np.ndarray:
    """Cells whose upstream area (in cells) reaches `threshold`: each land cell drains to its lowest lower neighbour."""
    h, w = elev.shape
    acc = np.ones(h * w, np.int64)
    flat = elev.ravel()
    order = np.argsort(-flat, kind="stable")
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for i in order:
        z, x = divmod(int(i), w)
        best, bi = flat[i], -1
        for dz, dx in offs:
            zz, xx = z + dz, x + dx
            if 0 <= zz < h and 0 <= xx < w:
                j = zz * w + xx
                if flat[j] < best:
                    best, bi = flat[j], j
        if bi >= 0:
            acc[bi] += acc[i]
    acc = acc.reshape(h, w)
    return (acc >= threshold) & (land == 1) & (elev < 1800)


def build_tile(world: dict, level: int, tx: int, tz: int, features) -> Path:
    L = LEVELS[level]
    out = HERE / "worlds" / world["id"] / f"L{level}" / f"{tx}_{tz}.bin"
    if out.exists():
        return out
    lon0, _, _, lat1 = world["bbox"]
    res = world["res"] / L["k"]
    tlon0 = lon0 + tx * L["cells"] * world["res"]
    tlat1 = lat1 - tz * L["cells"] * world["res"]
    span = L["cells"] * world["res"]
    pad = PAD * res
    bbox = (tlon0 - pad, tlat1 - span - pad, tlon0 + span + pad, tlat1 + pad)
    n = TILE + 2 * PAD
    elev = elevation_grid(bbox, res, L["zoom"], HERE / "cache" / "terrarium")[:n, :n]
    land_f, adm, index = features
    lf = [f for f in land_f if overlaps(f, bbox)]
    land = rasterize(lf, bbox, res, n, n, lambda f: 1).astype(np.uint8)
    af = [f for f in adm if overlaps(f, bbox)]
    region = rasterize(af, bbox, res, n, n, lambda f: index[id(f)]).astype(np.uint16)
    rivers = flow_rivers(elev.astype(np.float32), land, L["river_acc"])
    land = np.where(rivers, 2, land).astype(np.uint8)
    region[land == 0] = 0
    elev = np.where(land >= 1, np.maximum(elev, 1.0), np.minimum(elev, -1.0))
    c = slice(PAD, PAD + TILE)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(elev[c, c].astype("<i2").tobytes())
        fh.write(land[c, c].astype(np.uint8).tobytes())
        fh.write(region[c, c].astype("<u2").tobytes())
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--world", required=True)
    p.add_argument("--needs", required=True, help="JSON from render.mjs --prepare: {tiles: [{level, tx, tz}]}")
    a = p.parse_args(argv)
    world = json.loads((HERE / "worlds" / a.world / "meta.json").read_text(encoding="utf-8"))
    needs = json.loads(Path(a.needs).read_text(encoding="utf-8"))["tiles"]
    wb = tuple(world["bbox"])
    land_f = [f for f in json.load(gzip.open(DATA / "land.json.gz"))["features"] if overlaps(f, wb)]
    adm = [f for f in json.load(gzip.open(DATA / "admin1.json.gz"))["features"] if overlaps(f, wb)]
    index = {id(f): i for i, f in enumerate(adm, start=1)}  # the world's numbering (tools/build_world.py)
    built = 0
    for k, t in enumerate(needs):
        path = HERE / "worlds" / a.world / f"L{t['level']}" / f"{t['tx']}_{t['tz']}.bin"
        if not path.exists():
            build_tile(world, t["level"], t["tx"], t["tz"], (land_f, adm, index))
            built += 1
        print(json.dumps({"event": "tile", "done": k + 1, "total": len(needs)}), flush=True)
    print(json.dumps({"event": "done", "built": built, "total": len(needs)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
