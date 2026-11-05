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
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_world import DATA, HERE, download_tile, elevation_grid, overlaps, rasterize, tile_xy  # noqa: E402

TILE = 160
PAD = 16
DOWNLOADERS = 16      # elevation files fetched at once before the tiles are built
GIVE_UP_AFTER = 30    # this many failures in a row means the network is down: stop instead of waiting on every file
LEVELS = {1: {"k": 4, "cells": 40, "zoom": 9, "river_acc": 260}, 2: {"k": 16, "cells": 10, "zoom": 10, "river_acc": 1400}}
BASE_RES = 0.025  # the world block size the zooms above are set for


def detail_zoom(level: int, world_res: float) -> int:
    """Terrarium zoom for a detail level: one step coarser per doubling of the world's block size over BASE_RES.
    Mirrors lib/lod.mjs detailZoom()."""
    shift = max(0, math.floor(math.log2((world_res or BASE_RES) / BASE_RES) + 1e-9))
    return max(1, LEVELS[level]["zoom"] - shift)


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


def tile_bbox(world: dict, level: int, tx: int, tz: int) -> tuple:
    L = LEVELS[level]
    lon0, _, _, lat1 = world["bbox"]
    res = world["res"] / L["k"]
    tlon0 = lon0 + tx * L["cells"] * world["res"]
    tlat1 = lat1 - tz * L["cells"] * world["res"]
    span = L["cells"] * world["res"]
    pad = PAD * res
    return (tlon0 - pad, tlat1 - span - pad, tlon0 + span + pad, tlat1 + pad)


def missing_elevation(world: dict, todo: list, cache: Path) -> list:
    """The (z, x, y) elevation files the tiles in `todo` read that are not in the cache yet."""
    names = set()
    for t in todo:
        lon0, lat0, lon1, lat1 = tile_bbox(world, t["level"], t["tx"], t["tz"])
        z = detail_zoom(t["level"], world["res"])
        x0, y0 = tile_xy(lon0, lat1, z)
        x1, y1 = tile_xy(lon1, lat0, z)
        for y in range(int(y0), int(y1) + 1):
            for x in range(int(x0), int(x1) + 1):
                names.add((z, x, y))
    return sorted(n for n in names if not (cache / str(n[0]) / str(n[1]) / f"{n[2]}.png").exists())


def download_all(names: list, cache: Path, *, get=download_tile, workers: int = DOWNLOADERS, give_up_after: int = GIVE_UP_AFTER) -> bool:
    """Fetches the elevation files side by side (downloading is what takes the time, not building). A file that fails is
    tried again when its tile is built; False when so many fail in a row that the network must be down."""
    def one(name):
        try:
            get(*name, cache)
            return True
        except Exception:
            return False

    streak = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for done, ok in enumerate(ex.map(one, names), start=1):
            streak = 0 if ok else streak + 1
            print(json.dumps({"event": "fetch", "done": done, "total": len(names)}), flush=True)
            if streak >= give_up_after:
                ex.shutdown(wait=False, cancel_futures=True)
                return False
    return True


def die_with_parent() -> None:
    """A closed or stopped app must not leave this running: end (with any workers) as soon as the process that started it is gone."""
    parent = os.getppid()

    def watch() -> None:
        while os.getppid() == parent:
            time.sleep(2)
        import multiprocessing as mp
        for c in mp.active_children():
            c.kill()
        os._exit(1)

    threading.Thread(target=watch, daemon=True).start()


def build_tile(world: dict, level: int, tx: int, tz: int, features) -> Path:
    L = LEVELS[level]
    out = HERE / "worlds" / world["id"] / f"L{level}" / f"{tx}_{tz}.bin"
    if out.exists():
        return out
    res = world["res"] / L["k"]
    bbox = tile_bbox(world, level, tx, tz)
    n = TILE + 2 * PAD
    elev = elevation_grid(bbox, res, detail_zoom(level, world["res"]), HERE / "cache" / "terrarium")[:n, :n]
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
    """(args, "") or (args, why it failed): one bad tile must not throw away the rest (that area renders with coarser terrain)."""
    world, feats = _JOB
    try:
        build_tile(world, args[0], args[1], args[2], feats)
        return args, ""
    except Exception as exc:  # noqa: BLE001
        return args, f"{type(exc).__name__}: {exc}"


def _network_error() -> int:
    print(json.dumps({"event": "error", "message": "Could not download the elevation data: check the internet connection, then click Generate again. "
                                                    "Everything already downloaded is kept."}), flush=True)
    return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--world", required=True)
    p.add_argument("--needs", required=True, help="JSON from render.mjs --prepare: {tiles: [{level, tx, tz}]}")
    p.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="tiles built at once (default up to 4)")
    a = p.parse_args(argv)
    die_with_parent()
    world = json.loads((HERE / "worlds" / a.world / "meta.json").read_text(encoding="utf-8"))
    needs = json.loads(Path(a.needs).read_text(encoding="utf-8"))["tiles"]
    wb = tuple(world["bbox"])
    land_f = [f for f in json.load(gzip.open(DATA / "land.json.gz"))["features"] if overlaps(f, wb)]
    adm = [f for f in json.load(gzip.open(DATA / "admin1.json.gz"))["features"] if overlaps(f, wb)]
    index = {id(f): i for i, f in enumerate(adm, start=1)}  # the world's numbering (tools/build_world.py)
    feats = (land_f, adm, index)
    todo = [t for t in needs if not (HERE / "worlds" / a.world / f"L{t['level']}" / f"{t['tx']}_{t['tz']}.bin").exists()]
    cache = HERE / "cache" / "terrarium"
    if not download_all(missing_elevation(world, todo, cache), cache):
        return _network_error()
    built = failed = streak = 0
    workers = max(1, min(a.workers, len(todo)))
    ctx = None
    if workers > 1:
        try:
            import multiprocessing as mp
            ctx = mp.get_context("fork")   # workers inherit the loaded shapes; no fork (Windows) -> sequential below
        except ValueError:
            ctx = None
    done_n = len(needs) - len(todo)
    global _JOB
    _JOB = (world, feats)
    jobs = [(t["level"], t["tx"], t["tz"]) for t in todo]
    pool = ctx.Pool(workers, initializer=die_with_parent) if ctx is not None else None
    try:
        for _args, err in (pool.imap_unordered(_build_one, jobs) if pool else map(_build_one, jobs)):
            done_n += 1
            if err:
                failed += 1; streak += 1
                print(f"tile {_args}: {err}", file=sys.stderr, flush=True)
                if streak >= GIVE_UP_AFTER:
                    return _network_error()
            else:
                built += 1; streak = 0
            print(json.dumps({"event": "tile", "done": done_n, "total": len(needs)}), flush=True)
    finally:
        if pool:
            pool.terminate()
            pool.join()
    print(json.dumps({"event": "done", "built": built, "failed": failed, "total": len(needs)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
