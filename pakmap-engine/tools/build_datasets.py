#!/usr/bin/env python3
"""Rebuild the small open datasets bundled with pakmap-engine (data/).

  python3 tools/build_datasets.py [--cache DIR]

Sources (all free to use; credits go into every render's sidecar file):
  * CHIRPS v2.0 annual rainfall, 2016-2020 mean, Climate Hazards Center, UC Santa Barbara.
    Public domain. 0.05 deg source, averaged here to 0.1 deg, stored as int16 mm/year.
  * Natural Earth 10m populated places (public domain): longitude, latitude, population, country;
    plus a name index (places_index.json.gz) so a CSV can say "Nairobi" instead of a coordinate.

Needs numpy and Pillow (already project dependencies) and network access. The outputs are
committed-size small (a few MB); the multi-hundred-MB downloads are only cached under --cache.
"""
from __future__ import annotations

import argparse, gzip, json, sys, urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data"
CHIRPS = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_annual/tifs/chirps-v2.0.{year}.tif"
PLACES = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_populated_places_simple.geojson"
YEARS = (2016, 2017, 2018, 2019, 2020)


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        print("downloading", url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
    return dest


def build_rainfall(cache: Path) -> None:
    acc = np.zeros((2000, 7200), np.float64)
    cnt = np.zeros((2000, 7200), np.int32)
    for y in YEARS:
        a = np.array(Image.open(fetch(CHIRPS.format(year=y), cache / f"chirps_{y}.tif")), dtype=np.float64)
        ok = a > -9000
        acc[ok] += a[ok]
        cnt[ok] += 1
    mean = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    # 2x2 block mean (ignoring ocean): 0.05 deg -> 0.1 deg, 1000 rows x 3600 cols, lat 50 .. -50, lon -180 .. 180
    blocks = mean.reshape(1000, 2, 3600, 2)
    with np.errstate(all="ignore"):
        coarse = np.nanmean(blocks, axis=(1, 3))
    out = np.where(np.isnan(coarse), -32768, np.round(coarse)).astype("<i2")
    OUT.mkdir(exist_ok=True)
    with gzip.open(OUT / "rainfall_chirps_2016_2020_0p1.i16.gz", "wb", compresslevel=9) as f:
        f.write(out.tobytes())
    meta = {
        "id": "rainfall_chirps",
        "title": "Annual rainfall, mean of 2016-2020 (CHIRPS v2.0)",
        "kind": "grid", "file": "rainfall_chirps_2016_2020_0p1.i16.gz", "dtype": "int16", "nodata": -32768,
        "cols": 3600, "rows": 1000, "west": -180.0, "east": 180.0, "north": 50.0, "south": -50.0,
        "unit": "mm/year", "ramp": "rainfall",
        "licence": "Public domain (CHIRPS, Climate Hazards Center). Cite: Funk et al. 2015, Scientific Data 2:150066.",
        "attribution": "Rainfall: CHIRPS v2.0, Climate Hazards Center, UC Santa Barbara (public domain); 2016-2020 mean, 0.1 degree.",
        "coverage": "land between 50 N and 50 S",
    }
    (OUT / "rainfall_chirps.json").write_text(json.dumps(meta, indent=2))
    print("rainfall:", out.shape, "land cells", int((out > -32768).sum()))


def build_places(cache: Path) -> None:
    raw = json.loads(fetch(PLACES, cache / "ne_10m_populated_places_simple.geojson").read_text(encoding="utf8"))
    rows = []
    for f in raw["features"]:
        p, (lon, lat) = f["properties"], f["geometry"]["coordinates"]
        pop = p.get("pop_max") or p.get("pop_min") or 0
        if pop > 0:
            rows.append([round(lon, 3), round(lat, 3), int(pop), p.get("adm0_a3") or p.get("iso_a3") or ""])
    with gzip.open(OUT / "populated_places.json.gz", "wt", encoding="utf8", compresslevel=9) as f:
        json.dump(rows, f, separators=(",", ":"))
    meta = {
        "id": "populated_places",
        "title": "Populated places (Natural Earth 10m)",
        "kind": "places", "file": "populated_places.json.gz", "fields": ["lon", "lat", "population", "country_iso3"],
        "licence": "Public domain (Natural Earth).",
        "attribution": "Populated places: Natural Earth (public domain). Dot positions are generated around these places, not a measured population grid.",
        "note": "Approximation for dot-density layers; supply a real population grid or point file for exact distributions.",
    }
    (OUT / "populated_places.json").write_text(json.dumps(meta, indent=2))
    print("places:", len(rows))

    # name index for geo_ref lookups: [name, ascii name, alt names, lon, lat, population, country, region]
    index = []
    for f in raw["features"]:
        p, (lon, lat) = f["properties"], f["geometry"]["coordinates"]
        alts = [a.strip() for a in (p.get("namealt") or "").split(";") if a.strip()]
        index.append([p.get("name") or "", p.get("nameascii") or "", alts, round(lon, 4), round(lat, 4),
                      int(p.get("pop_max") or 0), p.get("adm0_a3") or "", p.get("adm1name") or ""])
    with gzip.open(OUT / "places_index.json.gz", "wt", encoding="utf8", compresslevel=9) as f:
        json.dump(index, f, separators=(",", ":"), ensure_ascii=False)
    (OUT / "places_index.json").write_text(json.dumps({
        "id": "places_index", "title": "Populated place names (Natural Earth 10m)", "kind": "names", "file": "places_index.json.gz",
        "fields": ["name", "ascii", "alt", "lon", "lat", "population", "country_iso3", "region"],
        "licence": "Public domain (Natural Earth).",
        "attribution": "Place names and positions: Natural Earth (public domain).",
    }, indent=2))
    print("name index:", len(index))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "pakmap-datasets"))
    args = ap.parse_args()
    cache = Path(args.cache)
    build_rainfall(cache)
    build_places(cache)
