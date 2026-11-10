#!/usr/bin/env python3
"""Real-look data for a City Timelapse world (optional, once per city, cached): real building footprints, land use, satellite ground.

    python3 tools/build_real.py --id dubai [--kinds buildings,landuse,satellite] [--buildings-source auto|overture|osm] [--chunks 3]

Writes worlds/<id>/ (landuse_cls.u8 is also made with every new world by build_city.py):
  buildings.json   [[x, z, rot, w, d, height_m], ...]  each building as its smallest rotated rectangle (metres from the world
                   centre, z south, same axes as the engine). Source: Overture Maps (OSM + Microsoft + Google footprints; needs
                   `pip install duckdb`) or OpenStreetMap through Overpass. Height from the height / floors data, else a size guess.
                   The buildings credit is written into meta.json.
  landuse_cls.u8   1024 x 1024 bytes, land-use class per cell (0 unmapped, 1 built up, 2 green, 3 dry, 4 wet), north edge = first row
  landuse.png      2048 px colour map of the ground in world space (OpenStreetMap land use, parks, sand, water-free): north edge = top
  ground_sat.jpg   2048 px satellite mosaic of the same area (Esri World Imagery: check its terms before publishing a film that uses it)
Sources: Overture Maps Foundation or OpenStreetMap contributors (ODbL) for buildings; OpenStreetMap for land use. Chunks that fail are skipped and reported; rerun to fill them.
"""
from __future__ import annotations

import argparse
import json
import math
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent.parent


def ssl_context() -> ssl.SSLContext:
    """HTTPS checked against certifi's certificates (the installed Mac app has no system store)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


UA = "SemanticYTStudio-citygrow/0.1 (one-time cached fetch)"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
M_LAT, M_LON = 110574.0, 111320.0
TEX = 2048

# land use -> class code for the ground colour and the trees (landuse_cls.u8): 0 unmapped, 1 built up, 2 green, 3 dry, 4 wet
CLASS_OF = {}
for _k in ("residential", "commercial", "retail", "industrial", "religious", "education", "military"):
    CLASS_OF[_k] = 1
for _k in ("park", "garden", "golf_course", "pitch", "recreation_ground", "grass", "meadow", "forest", "wood", "farmland", "farmyard",
           "cemetery", "orchard", "vineyard", "village_green", "allotments", "greenfield"):
    CLASS_OF[_k] = 2
for _k in ("sand", "beach", "bare_rock", "scrub", "heath", "brownfield", "construction", "quarry", "desert", "landfill"):
    CLASS_OF[_k] = 3
CLASS_OF["wetland"] = 4
CLS = 1024

# land use -> ground colour (dry-land palette is chosen by the page for everything the map does not cover)
LANDUSE = {
    "residential": (176, 170, 150), "commercial": (170, 166, 156), "retail": (170, 166, 156), "industrial": (160, 156, 148),
    "construction": (196, 180, 140), "brownfield": (200, 184, 146), "farmland": (160, 170, 96), "farmyard": (170, 170, 110),
    "meadow": (150, 168, 100), "grass": (132, 160, 92), "forest": (74, 112, 64), "wood": (74, 112, 64), "scrub": (150, 150, 98),
    "park": (118, 158, 92), "garden": (122, 160, 96), "golf_course": (112, 160, 86), "pitch": (130, 160, 96), "recreation_ground": (126, 160, 94),
    "sand": (226, 208, 160), "beach": (232, 216, 170), "bare_rock": (150, 142, 128), "heath": (150, 150, 100), "wetland": (130, 150, 120),
    "cemetery": (140, 160, 110), "orchard": (120, 156, 90), "vineyard": (140, 160, 96), "allotments": (140, 160, 96), "quarry": (190, 176, 150), "desert": (226, 208, 160), "religious": (172, 166, 150), "education": (172, 168, 154), "military": (150, 146, 132),
}


def post(url: str, query: str, timeout: int = 180) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
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
    def __init__(self, wid: str, meta: dict | None = None, out_dir: Path | None = None):
        self.dir = out_dir or HERE / "worlds" / wid
        self.meta = meta if meta is not None else json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
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


def to_building(w: World, pts: np.ndarray, height) -> list | None:
    """One footprint (metres, engine axes) -> [x, z, rot, w, d, height_m], or None when outside the world or too small.
    `height` is a number or a function of the footprint area."""
    if len(pts) < 4 or np.abs(pts).max() > w.half:
        return None
    r = min_rect(pts)
    if r is None:
        return None
    cx, cz, rot, bw, bd = r
    if bw * bd < 14:
        return None
    h = height(bw * bd) if callable(height) else height
    return [round(cx, 1), round(cz, 1), round(rot, 3), round(bw, 1), round(bd, 1), round(h, 1)]


def build_buildings_osm(w: World, chunks: int) -> dict:
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
                tags = el.get("tags", {})
                b = to_building(w, pts, lambda area, tags=tags: height_of(tags, area))
                if b:
                    out.append(b)
    (w.dir / "buildings.json").write_text(json.dumps(out), encoding="utf-8")
    set_buildings_credit(w, OSM_BUILDINGS_CREDIT)
    return {"buildings": len(out), "buildings_source": "osm", "chunks_failed": failed, "chunks": chunks * chunks}


# ---------------------------------------------------------------- buildings from Overture Maps
# Overture's buildings theme joins OpenStreetMap with Microsoft and Google machine-traced footprints (and more), so cities
# that OSM maps thinly get far more houses. Read with DuckDB straight from Overture's public S3 bucket (no account). Only the
# files whose box touches the world are read: their boxes come from Overture's STAC catalog, cached once per release.

OSM_BUILDINGS_CREDIT = "Buildings: © OpenStreetMap contributors (ODbL)"
OVERTURE_STAC = "https://stac.overturemaps.org"
OVERTURE_CREDIT_OF = {   # sources[].dataset -> credit wording
    "OpenStreetMap": "© OpenStreetMap contributors (ODbL)",
    "Microsoft ML Buildings": "Microsoft Global ML Building Footprints (ODbL)",
    "Google Open Buildings": "Google Open Buildings (CC BY 4.0 / ODbL)",
    "Esri Community Maps": "Esri Community Maps contributors",
}


def get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
        return json.loads(r.read())


def set_buildings_credit(w: World, line: str) -> None:
    """Puts the buildings credit in meta.json (replacing an older one), so the film's credits file carries it."""
    path = w.dir / "meta.json"
    if not path.exists():
        return
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["credits"] = [c for c in meta.get("credits", []) if not c.startswith("Buildings:")] + [line]
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    w.meta = meta


def overture_release(fetch=get_json) -> str:
    return fetch(f"{OVERTURE_STAC}/catalog.json")["latest"]


def overture_index(release: str, fetch=get_json, workers: int = 32) -> list:
    """[[xmin, ymin, xmax, ymax, s3_url], ...] for every buildings file of a release (512 small JSONs, cached once)."""
    cache = HERE / "cache" / "overture" / f"{release}_buildings_index.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    from concurrent.futures import ThreadPoolExecutor
    base = f"{OVERTURE_STAC}/{release}/buildings/building/"
    hrefs = [l["href"] for l in fetch(base + "collection.json")["links"] if l["rel"] == "item"]

    def item(href):
        d = fetch(href)
        return [*d["bbox"], d["assets"]["aws"]["alternate"]["s3"]["href"]]
    with ThreadPoolExecutor(workers) as ex:
        index = list(ex.map(item, hrefs))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(index), encoding="utf-8")
    return index


def files_for(index: list, s: float, we: float, n: float, e: float) -> list:
    return [f[4] for f in index if f[0] <= e and f[2] >= we and f[1] <= n and f[3] >= s]


def wkb_rings(blob: bytes) -> list:
    """Outer rings ([[lon, lat], ...]) of a WKB Polygon or MultiPolygon (2D, or with Z/M values that are dropped)."""
    import struct
    rings, pos = [], 0

    def geom():
        nonlocal pos
        end = "<" if blob[pos] == 1 else ">"
        kind = struct.unpack_from(end + "I", blob, pos + 1)[0]
        pos += 5
        t = kind & 0x0FFFFFFF                      # ISO codes (1000s Z, 2000s M, 3000s ZM) or EWKB flag bits
        has_z = bool(kind & 0x80000000) or t // 1000 in (1, 3)
        has_m = bool(kind & 0x40000000) or t // 1000 in (2, 3)
        dims, base = 2 + has_z + has_m, t % 1000
        if base == 3:
            nr = struct.unpack_from(end + "I", blob, pos)[0]
            pos += 4
            for k in range(nr):
                npt = struct.unpack_from(end + "I", blob, pos)[0]
                pos += 4
                a = np.frombuffer(blob, dtype=end + "f8", count=npt * dims, offset=pos).reshape(npt, dims)[:, :2]
                pos += npt * dims * 8
                if k == 0:
                    rings.append(a)
        elif base == 6:
            n = struct.unpack_from(end + "I", blob, pos)[0]
            pos += 4
            for _ in range(n):
                geom()
        else:
            raise ValueError(f"not a polygon (WKB type {kind})")
    geom()
    return rings


def overture_height(height, floors, cls, area: float) -> float:
    if height and height > 0:
        return max(2.5, float(height))
    if floors and floors > 0:
        return max(3.0, floors * 3.3 + 1.0)
    return height_of({"building": cls or "yes"}, area)


def overture_buildings_from_rows(w: World, rows) -> tuple[list, dict]:
    """Rows of (geometry WKB, height, num_floors, class, [datasets]) -> (buildings, {dataset: count})."""
    out, by_source = [], {}
    for blob, height, floors, cls, datasets in rows:
        try:
            rings = wkb_rings(bytes(blob))
        except Exception:  # noqa: BLE001  a broken footprint is skipped, never the city
            continue
        if not rings:
            continue
        ring = max(rings, key=len)
        pts = np.array([w.xz(lon, lat) for lon, lat in ring])
        b = to_building(w, pts, lambda area: overture_height(height, floors, cls, area))
        if b:
            out.append(b)
            for d in set(datasets or []) or {"unknown"}:
                by_source[d] = by_source.get(d, 0) + 1
    return out, by_source


def query_overture(w: World, release: str, index: list) -> list:
    """Downloads (once, cached as Parquet) the world's Overture buildings and returns their rows."""
    import duckdb
    cache = HERE / "cache" / "overture" / f"{w.meta['id']}_{release}_buildings.parquet"
    s, we, n, e = w.bbox()
    con = duckdb.connect()
    if not cache.exists():
        files = files_for(index, s, we, n, e)
        if not files:
            raise RuntimeError("no Overture buildings files cover this area")
        con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".part")
        src = ", ".join(f"'{f}'" for f in files)
        con.execute(f"""COPY (SELECT geometry, height, num_floors, class, [x.dataset FOR x IN sources] AS datasets
            FROM read_parquet([{src}])
            WHERE bbox.xmin <= {e} AND bbox.xmax >= {we} AND bbox.ymin <= {n} AND bbox.ymax >= {s}
              AND coalesce(is_underground, false) = false) TO '{tmp}' (FORMAT parquet)""")
        tmp.rename(cache)
    return con.execute(f"SELECT geometry::BLOB, height, num_floors, class, datasets FROM read_parquet('{cache}')").fetchall()


def build_buildings_overture(w: World) -> dict:
    release = overture_release()
    rows = query_overture(w, release, overture_index(release))
    out, by_source = overture_buildings_from_rows(w, rows)
    (w.dir / "buildings.json").write_text(json.dumps(out), encoding="utf-8")
    parts = [OVERTURE_CREDIT_OF.get(d, d) for d, _ in sorted(by_source.items(), key=lambda kv: -kv[1]) if d != "unknown"]
    set_buildings_credit(w, f"Buildings: Overture Maps Foundation, release {release} (overturemaps.org), including "
                            + "; ".join(parts or ["© OpenStreetMap contributors (ODbL)"]))
    return {"buildings": len(out), "buildings_source": "overture", "overture_release": release, "by_source": by_source}


def build_buildings(w: World, chunks: int = 3, source: str = "auto") -> dict:
    """source: "overture", "osm", or "auto" (Overture when DuckDB is installed and the download works, else OpenStreetMap)."""
    if source in ("auto", "overture"):
        try:
            import duckdb  # noqa: F401
        except ImportError:
            if source == "overture":
                raise SystemExit("Overture needs DuckDB: pip install duckdb")
            print(json.dumps({"event": "note", "message": "DuckDB not installed (pip install duckdb): using OpenStreetMap buildings"}), flush=True)
        else:
            try:
                return build_buildings_overture(w)
            except Exception as ex:  # noqa: BLE001
                if source == "overture":
                    raise
                print(json.dumps({"event": "note", "message": f"Overture unavailable ({str(ex)[:120]}): using OpenStreetMap buildings"}), flush=True)
    return build_buildings_osm(w, chunks)


# ---------------------------------------------------------------- land use

def build_landuse(w: World, fetch=None, tries: int = 3) -> dict:
    s, we, n, e = w.bbox()
    b = f"{s:.5f},{we:.5f},{n:.5f},{e:.5f}"
    q = (f"[out:json][timeout:170];("
         f'way["landuse"]({b});way["leisure"~"park|garden|golf_course|pitch|recreation_ground"]({b});'
         f'way["natural"~"sand|beach|scrub|wood|heath|bare_rock|grassland|wetland|desert"]({b}););out geom tags;')
    cache = HERE / "cache" / "osm_real" / f"{w.meta['id']}_landuse.json"
    d = fetch(q, cache) if fetch else overpass(q, cache, tries=tries)
    if d is None:
        return {"landuse": "download failed"}
    cls_img = Image.new("L", (CLS, CLS), 0)
    dc = ImageDraw.Draw(cls_img)
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
    kc = CLS / w.size
    for el in d.get("elements", []):
        t = el.get("tags", {})
        code = CLASS_OF.get(t.get("landuse") or t.get("leisure") or t.get("natural"))
        if code and len(el.get("geometry", [])) >= 4:
            dc.polygon([((x + w.half) * kc, (z + w.half) * kc) for x, z in (w.xz(g["lon"], g["lat"]) for g in el["geometry"])], fill=code)
    cls_img.save(w.dir / "landuse_cls.png")
    (w.dir / "landuse_cls.u8").write_bytes(cls_img.tobytes())
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
                        cache.write_bytes(urllib.request.urlopen(req, timeout=30, context=ssl_context()).read())
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
    ap.add_argument("--chunks", type=int, default=3, help="OpenStreetMap buildings: Overpass requests per side")
    ap.add_argument("--buildings-source", choices=("auto", "overture", "osm"), default="auto",
                    help="auto = Overture Maps when DuckDB is installed, else OpenStreetMap")
    a = ap.parse_args(argv)
    w = World(a.id)
    res = {}
    kinds = set(a.kinds.split(","))
    if "satellite" in kinds:
        res.update(build_satellite(w))
    if "landuse" in kinds:
        res.update(build_landuse(w))
    if "buildings" in kinds:
        res.update(build_buildings(w, a.chunks, a.buildings_source))
    print(json.dumps({"event": "done", **res}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
