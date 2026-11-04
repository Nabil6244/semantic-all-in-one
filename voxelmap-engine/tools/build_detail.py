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
import os
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
    tmp = out.with_name(out.name + f".{os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        fh.write(elev[c, c].astype("<i2").tobytes())
        fh.write(land[c, c].astype(np.uint8).tobytes())
        fh.write(region[c, c].astype("<u2").tobytes())
    os.replace(tmp, out)
    return out


_JOB = None


def _build_one(args):
    world, feats = _JOB
    build_tile(world, args[0], args[1], args[2], feats)
    return args


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--world", required=True)
    p.add_argument("--needs", required=True, help="JSON from render.mjs --prepare: {tiles: [{level, tx, tz}]}")
    p.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="tiles built at once (default up to 4)")
    a = p.parse_args(argv)
    world = json.loads((HERE / "worlds" / a.world / "meta.json").read_text(encoding="utf-8"))
    needs = json.loads(Path(a.needs).read_text(encoding="utf-8"))["tiles"]
    wb = tuple(world["bbox"])
    land_f = [f for f in json.load(gzip.open(DATA / "land.json.gz"))["features"] if overlaps(f, wb)]
    adm = [f for f in json.load(gzip.open(DATA / "admin1.json.gz"))["features"] if overlaps(f, wb)]
    index = {id(f): i for i, f in enumerate(adm, start=1)}  # the world's numbering (tools/build_world.py)
    feats = (land_f, adm, index)
    todo = [t for t in needs if not (HERE / "worlds" / a.world / f"L{t['level']}" / f"{t['tx']}_{t['tz']}.bin").exists()]
    built = 0
    workers = max(1, min(a.workers, len(todo)))
    ctx = None
    if workers > 1:
        try:
            import multiprocessing as mp
            ctx = mp.get_context("fork")   # workers inherit the loaded shapes; no fork (Windows) -> sequential below
        except ValueError:
            ctx = None
    done_n = len(needs) - len(todo)
    if ctx is None:
        for t in todo:
            build_tile(world, t["level"], t["tx"], t["tz"], feats); built += 1; done_n += 1
            print(json.dumps({"event": "tile", "done": done_n, "total": len(needs)}), flush=True)
    else:
        global _JOB
        _JOB = (world, feats)
        with ctx.Pool(workers) as pool:
            for _ in pool.imap_unordered(_build_one, [(t["level"], t["tx"], t["tz"]) for t in todo]):
                built += 1; done_n += 1
                print(json.dumps({"event": "tile", "done": done_n, "total": len(needs)}), flush=True)
    print(json.dumps({"event": "done", "built": built, "total": len(needs)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
