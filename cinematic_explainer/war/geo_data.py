"""Geography for the War Documentary maps: the app's own Natural Earth data (map_scene/data) as numpy rings, framing presets, a small gazetteer.

Nothing here is downloaded or invented: countries and admin-1 areas come from map_scene/data/*.json.gz (read only), city coordinates from the
GAZETTEER below (well-known city centres, rounded to 0.01 degree), framing boxes are approximate and only decide what is on screen.
Rivers, roads and ports: the repo has no such data, so the map renderer skips them.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

DATA_DIR = Path(__file__).resolve().parents[2] / "map_scene" / "data"

BBox = Tuple[float, float, float, float]  # lon0, lat0, lon1, lat1


def merc(lat_deg) -> float:
    """Mercator y (radians) of a latitude in degrees; clamped away from the poles. Works on numpy arrays too."""
    lat = np.clip(np.asarray(lat_deg, dtype=np.float64), -85.0, 85.0)
    out = np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    return float(out) if out.ndim == 0 else out


def unmerc(y) -> float:
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)


# ---------------------------------------------------------------------------------------------------------------- framing presets
# Approximate framing boxes (lon0, lat0, lon1, lat1). They only choose what is visible; the renderer fits them to 16:9.
PRESETS: Dict[str, BBox] = {
    "ukraine": (21.8, 44.0, 40.6, 52.8),
    "ukraine_russia": (22.0, 42.0, 58.0, 60.0),
    "black_sea": (26.0, 39.8, 42.8, 48.6),
    "europe_east": (10.0, 36.0, 50.0, 62.0),
    "crimea": (31.6, 43.8, 37.4, 46.9),
    "donbas": (35.6, 46.6, 40.8, 49.8),
    "baltic": (9.0, 53.0, 31.0, 61.0),
    "nato_east": (12.0, 40.0, 40.0, 60.0),
    "kharkiv_region": (34.2, 48.2, 39.2, 51.2),
    "odesa_region": (27.6, 44.6, 33.4, 48.4),
    "kyiv_region": (28.2, 49.0, 33.4, 52.0),
}

# ---------------------------------------------------------------------------------------------------------------- gazetteer (lat, lon)
GAZETTEER: Dict[str, Tuple[float, float]] = {
    "Kyiv": (50.45, 30.52), "Kharkiv": (49.99, 36.23), "Odesa": (46.48, 30.73), "Lviv": (49.84, 24.03), "Dnipro": (48.46, 35.05),
    "Zaporizhzhia": (47.84, 35.14), "Donetsk": (48.00, 37.80), "Luhansk": (48.57, 39.31), "Mariupol": (47.10, 37.54),
    "Kherson": (46.64, 32.62), "Mykolaiv": (46.98, 31.99), "Poltava": (49.59, 34.55), "Sumy": (50.91, 34.80), "Chernihiv": (51.49, 31.29),
    "Sevastopol": (44.62, 33.52), "Simferopol": (44.95, 34.10), "Kerch": (45.36, 36.47), "Melitopol": (46.84, 35.37),
    "Bakhmut": (48.59, 38.00), "Kramatorsk": (48.72, 37.56), "Sloviansk": (48.87, 37.62), "Pokrovsk": (48.28, 37.18),
    "Moscow": (55.76, 37.62), "St Petersburg": (59.93, 30.34), "Rostov-on-Don": (47.24, 39.72), "Belgorod": (50.60, 36.59),
    "Kursk": (51.73, 36.19), "Bryansk": (53.24, 34.36), "Voronezh": (51.67, 39.18), "Volgograd": (48.71, 44.51),
    "Novorossiysk": (44.72, 37.77), "Sochi": (43.60, 39.73), "Krasnodar": (45.04, 38.98), "Kaliningrad": (54.71, 20.51),
    "Minsk": (53.90, 27.57), "Warsaw": (52.23, 21.01), "Bucharest": (44.43, 26.10), "Chisinau": (47.01, 28.86),
    "Istanbul": (41.01, 28.98), "Ankara": (39.93, 32.86), "Vilnius": (54.69, 25.28), "Riga": (56.95, 24.11),
    "Tallinn": (59.44, 24.75), "Helsinki": (60.17, 24.94), "Constanta": (44.18, 28.65), "Varna": (43.21, 27.91),
    "Sofia": (42.70, 23.32), "Budapest": (47.50, 19.04), "Bratislava": (48.15, 17.11), "Tbilisi": (41.72, 44.79),
    "Batumi": (41.65, 41.64), "Berlin": (52.52, 13.40), "Prague": (50.08, 14.44), "Vienna": (48.21, 16.37),
}


def gazetteer(name: str) -> Optional[Tuple[float, float]]:
    n = _norm(name)
    for k, v in GAZETTEER.items():
        if _norm(k) == n:
            return v
    return None


# ---------------------------------------------------------------------------------------------------------------- names
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z]", "", s)


_ALIASES = {"odesa": "odessa", "kyiv": "kiev", "kyivoblast": "kiev", "kyivcity": "kievcity", "zaporizhzhia": "zaporizhzhya",
            "mykolaiv": "mykolayiv", "dnipro": "dnipropetrovsk", "khmelnytskyi": "khmelnytskyy", "vinnytsia": "vinnytsya",
            "autonomousrepublicofcrimea": "crimea", "transcarpathian": "transcarpathia", "zakarpattia": "transcarpathia",
            "russianfederation": "russia", "czechrepublic": "czechia"}


# ---------------------------------------------------------------------------------------------------------------- features
class Ring:
    __slots__ = ("lon", "ym", "bbox")

    def __init__(self, coords: Sequence[Sequence[float]]):
        a = np.asarray(coords, dtype=np.float64)
        self.lon = a[:, 0]
        self.ym = merc(a[:, 1])
        self.bbox = (float(a[:, 0].min()), float(a[:, 1].min()), float(a[:, 0].max()), float(a[:, 1].max()))


class Feature:
    __slots__ = ("name", "iso", "alts", "polys", "bbox", "centroid")

    def __init__(self, raw: dict):
        self.name = str(raw.get("n") or "")
        self.iso = str(raw.get("iso") or "")
        self.alts = [str(x) for x in (raw.get("alt") or [])]
        g = raw["g"]
        multi = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        self.polys: List[Tuple[Ring, List[Ring]]] = []
        for poly in multi:
            if not poly or len(poly[0]) < 3:
                continue
            self.polys.append((Ring(poly[0]), [Ring(h) for h in poly[1:] if len(h) >= 3]))
        if self.polys:
            bs = [p[0].bbox for p in self.polys]
            self.bbox = (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
            big = max(self.polys, key=lambda p: (p[0].bbox[2] - p[0].bbox[0]) * (p[0].bbox[3] - p[0].bbox[1]))[0]
            self.centroid = (float(big.lon.mean()), float(np.degrees(0) + unmerc(float(big.ym.mean()))))
        else:
            self.bbox = (0.0, 0.0, 0.0, 0.0)
            self.centroid = (0.0, 0.0)


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _raw_countries() -> List[dict]:
    with gzip.open(DATA_DIR / "countries.json.gz", "rt", encoding="utf-8") as fh:
        return json.load(fh)["features"]


@lru_cache(maxsize=1)
def countries() -> List[Feature]:
    with _lock:
        return [Feature(r) for r in _raw_countries()]


@lru_cache(maxsize=1)
def _raw_admin1() -> Dict[str, List[dict]]:
    """Raw admin-1 features indexed by normalised name (several areas can share a name in different countries)."""
    with gzip.open(DATA_DIR / "admin1.json.gz", "rt", encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    idx: Dict[str, List[dict]] = {}
    for f in feats:
        for nm in {f.get("n", "")} | set(f.get("alt") or []):
            idx.setdefault(_norm(nm), []).append(f)
    return idx


_admin_cache: Dict[Tuple[str, str], Optional[Feature]] = {}


def find_country(key: str) -> Optional[Feature]:
    """Country by ISO3 code, name or alternate name (case/accents ignored)."""
    k = _norm(key)
    k = _ALIASES.get(k, k)
    up = str(key or "").strip().upper()
    feats = countries()
    for f in feats:
        if f.iso == up:
            return f
    for f in feats:
        if _norm(f.name) == k or any(_norm(a) == k for a in f.alts):
            return f
    return None


def find_oblast(name: str, iso: str = "") -> Optional[Feature]:
    """Admin-1 area (oblast, region, province) by name, optionally restricted to a country's ISO3."""
    ck = (_norm(name), iso.upper())
    if ck in _admin_cache:
        return _admin_cache[ck]
    k = _ALIASES.get(_norm(name), _norm(name))
    hits = _raw_admin1().get(k, [])
    if iso:
        hits = [h for h in hits if h.get("iso") == iso.upper()]
    else:   # prefer the theatre's countries when a name is shared
        pref = {"UKR": 0, "RUS": 1, "BLR": 2, "POL": 3, "ROU": 4, "MDA": 5}
        hits = sorted(hits, key=lambda h: pref.get(h.get("iso"), 9))
    out = Feature(hits[0]) if hits else None
    _admin_cache[ck] = out
    return out


def preset_bbox(name: str) -> Optional[BBox]:
    return PRESETS.get(_norm(name)) or PRESETS.get(str(name).strip().lower().replace(" ", "_"))


def geodesic_circle(lat: float, lon: float, km: float, n: int = 96) -> List[Tuple[float, float]]:
    """(lon, lat) points of a circle of `km` radius around a point (spherical earth, R = 6371 km)."""
    d = km / 6371.0
    la, lo = math.radians(lat), math.radians(lon)
    pts = []
    for i in range(n + 1):
        br = 2 * math.pi * i / n
        la2 = math.asin(math.sin(la) * math.cos(d) + math.cos(la) * math.sin(d) * math.cos(br))
        lo2 = lo + math.atan2(math.sin(br) * math.sin(d) * math.cos(la), math.cos(d) - math.sin(la) * math.sin(la2))
        pts.append((math.degrees(lo2), math.degrees(la2)))
    return pts


def great_circle(a: Tuple[float, float], b: Tuple[float, float], n: int = 48) -> List[Tuple[float, float]]:
    """(lon, lat) points along the great circle between two (lat, lon) points."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = 2 * math.asin(min(1.0, math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)))
    if d < 1e-9:
        return [(a[1], a[0])] * 2
    pts = []
    for i in range(n + 1):
        f = i / n
        A, B = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
        x = A * math.cos(la1) * math.cos(lo1) + B * math.cos(la2) * math.cos(lo2)
        y = A * math.cos(la1) * math.sin(lo1) + B * math.cos(la2) * math.sin(lo2)
        z = A * math.sin(la1) + B * math.sin(la2)
        pts.append((math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, math.hypot(x, y)))))
    return pts


# ---------------------------------------------------------------------------------------------------------------- context layers (rivers, lakes, cities, oblasts)
# data/ne_context.json.gz: Natural Earth 1:50m rivers_lake_centerlines, lakes and populated_places_simple clipped to lon 8..70, lat 34..70
# (public domain, https://www.naturalearthdata.com, retrieved 2026-10-27). Only drawing context: nothing here says anything about events.
CONTEXT_PATH = Path(__file__).resolve().parent / "data" / "ne_context.json.gz"
THEATRE_ISO = ("UKR", "RUS", "BLR", "POL", "ROU", "MDA", "SVK", "HUN", "LTU", "LVA", "EST", "FIN", "GEO", "TUR", "BGR", "KAZ", "AZE", "ARM")
CONTEXT_SOURCE = "Natural Earth 1:50m rivers, lakes, populated places and admin-1 areas (public domain)"

# Sea names at well-known open-water points (lat, lon), drawn as quiet labels when in view.
SEAS: Dict[str, Tuple[float, float]] = {
    "BLACK SEA": (43.3, 34.2), "SEA OF AZOV": (46.1, 36.9), "BALTIC SEA": (57.6, 19.6), "CASPIAN SEA": (42.0, 50.6),
    "SEA OF MARMARA": (40.7, 28.2), "WHITE SEA": (65.5, 38.0), "BARENTS SEA": (70.5, 38.0),
}
# a second and third open-water point for the larger seas, so the name is still on screen when the first point is not
SEA_ALT: Dict[str, Tuple[Tuple[float, float], ...]] = {"BLACK SEA": ((45.1, 31.6), (44.0, 30.9), (43.0, 38.6), (42.2, 31.0), (43.6, 28.8)), "BALTIC SEA": ((55.0, 17.0), (59.0, 21.0))}
# Rivers whose names are worth printing (ne name -> printed name)
RIVER_LABELS = {"Dnipro": "Dnipro", "Dnepre": "Dnipro", "Don": "Don", "Volga": "Volga", "Dniester": "Dniester", "Danube": "Danube", "Donau": "Danube",
                "Vistula": "Vistula", "Neva": "Neva"}
_CAPITALS = {"Kyiv", "Moscow", "Minsk", "Warsaw", "Bucharest", "Chisinau", "Ankara", "Vilnius", "Riga", "Tallinn", "Helsinki", "Sofia", "Budapest",
             "Bratislava", "Tbilisi", "Berlin", "Prague", "Vienna"}
_BIG = {"Kharkiv", "Odesa", "Dnipro", "Donetsk", "Lviv", "Zaporizhzhia", "St Petersburg", "Rostov-on-Don", "Volgograd", "Voronezh", "Istanbul",
        "Krasnodar", "Sevastopol", "Mariupol", "Luhansk"}


@lru_cache(maxsize=1)
def context() -> Dict[str, object]:
    """The clipped Natural Earth context (rivers, lakes, cities) or empty lists when the file is missing or unreadable."""
    try:
        with gzip.open(CONTEXT_PATH, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return d
    except (OSError, ValueError):
        pass
    return {"rivers": [], "lakes": [], "cities": [], "source": ""}


@lru_cache(maxsize=1)
def context_cities() -> List[Dict[str, object]]:
    """Quiet-context cities: the curated gazetteer (weights: capital 3, big city 2, other 1) plus Natural Earth cities of 400 000 or more that are
    not within 0.6 degrees of a gazetteer entry (weight 1.5 from a million, else 1)."""
    out: List[Dict[str, object]] = []
    for name, (la, lo) in GAZETTEER.items():
        out.append({"n": name, "lat": la, "lon": lo, "w": 3.0 if name in _CAPITALS else 2.0 if name in _BIG else 1.0})
    for c in context().get("cities", []) or []:
        try:
            pop = c.get("pop") or 0
            if pop < 400_000:
                continue
            if any(abs(o["lat"] - c["lat"]) < 0.6 and abs(o["lon"] - c["lon"]) < 0.9 for o in out):
                continue
            out.append({"n": str(c["n"]).replace("  ", " "), "lat": float(c["lat"]), "lon": float(c["lon"]), "w": 1.5 if pop >= 1_000_000 else 1.0})
        except (KeyError, TypeError, ValueError):
            continue
    return out


@lru_cache(maxsize=1)
def theatre_admin1() -> List[Feature]:
    """Admin-1 areas (oblasts, regions, provinces) of the theatre's countries, as Features (built once)."""
    seen = set()
    out: List[Feature] = []
    for lst in _raw_admin1().values():
        for raw in lst:
            if id(raw) in seen or raw.get("iso") not in THEATRE_ISO:
                continue
            seen.add(id(raw))
            try:
                out.append(Feature(raw))
            except Exception:
                continue
    return out
