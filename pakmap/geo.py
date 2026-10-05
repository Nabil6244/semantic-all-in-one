"""Where things are: turn the names in a CSV into coordinates and camera framings.

geo_ref forms (checked in this order):
    "-1.29,36.82"          latitude,longitude
    "KEN"                  an ISO 3166 alpha-3 country code
    "city:Nairobi"         a populated place (add the country to disambiguate: "city:Moscow,RUS")
    "Kenya" / "Nairobi"    a country, state, county or named region (map_scene data), else a city
Several places for a line are joined with ";" ("Mombasa;Nairobi;Lodwar").
"""

from __future__ import annotations

import difflib
import gzip
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Tuple

from map_scene.places import PlaceNotFound, _dataset, find_place



def _engine_data(name: str) -> Path:
    """data/<name> of pakmap-engine: the packaged app's copy when there is one, else next to this package."""
    try:
        from .engine_runner import engine_dir

        return engine_dir() / "data" / name
    except Exception:
        return Path(__file__).resolve().parent.parent / "pakmap-engine" / "data" / name


BBox = Tuple[float, float, float, float]


class GeoError(LookupError):
    pass


@dataclass
class Located:
    name: str
    kind: str  # point | city | country | admin1 | county | region
    lon: float  # a point inside the place (the place's own position for a point or city)
    lat: float
    bbox: BBox
    iso: str = ""  # ISO3 of the country (or of the country the place is in)
    polys: Optional[list] = None  # MultiPolygon coordinates for areas
    population: int = 0

    @property
    def is_area(self) -> bool:
        return self.polys is not None


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_ISO3 = re.compile(r"^[A-Z]{3}$")


@lru_cache(maxsize=1)
def _cities() -> list:
    f = _engine_data("places_index.json.gz")
    if not f.exists():
        raise GeoError(f"the city index is missing ({f}); run: python3 pakmap-engine/tools/build_datasets.py")
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    out = []
    for name, ascii_name, alts, lon, lat, pop, iso, region in rows:
        keys = {_fold(name), _fold(ascii_name)} | {_fold(a) for a in alts}
        out.append((keys - {""}, name, lon, lat, pop, iso, region))
    return out


def _city(query: str) -> Optional[Located]:
    name, _, iso = query.partition(",")
    key, iso = _fold(name), iso.strip().upper()
    hits = [c for c in _cities() if key in c[0] and (not iso or c[5] == iso)]
    if not hits:
        return None
    keys, nm, lon, lat, pop, c_iso, region = max(hits, key=lambda c: c[4])
    return Located(nm, "city", lon, lat, (lon, lat, lon, lat), c_iso, None, pop)


def _suggest_city(query: str) -> List[str]:
    key = _fold(query.partition(",")[0])
    pool = {_fold(c[1]): c[1] for c in _cities()}
    return [pool[k] for k in difflib.get_close_matches(key, list(pool), n=3, cutoff=0.78)]


def _from_place(p, ref: str) -> Located:
    bb = p.bbox()
    lon, lat = p.anchor()
    return Located(p.name, "point" if p.is_point else p.kind, lon, lat, tuple(bb), p.country or "", None if p.is_point else [list(poly) for poly in p.polygons])


def resolve(ref: str, prefer: str = "area") -> Located:
    """prefer="point": a bare name is looked up as a city first (markers, labels, route stops: "Nairobi" the city),
    prefer="area": as a country/state/county/region first (fills, overlays: "Nairobi" the county)."""
    ref = (ref or "").strip()
    if not ref:
        raise GeoError("geo_ref is empty")
    m = _LATLON.match(ref)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise GeoError(f"{ref!r} is not a valid lat,lon (latitude -90..90, longitude -180..180; write latitude first)")
        return Located(ref, "point", lon, lat, (lon, lat, lon, lat))
    if ref.lower().startswith("city:"):
        c = _city(ref[5:])
        if c:
            return c
        tips = _suggest_city(ref[5:])
        raise GeoError(f"no city called {ref[5:].strip()!r}" + (f" (did you mean {', '.join(tips)}?)" if tips else "") + "; or write its coordinates as lat,lon")
    if _ISO3.match(ref):
        for f in _dataset("countries"):
            if f.get("iso") == ref:
                return _from_place(find_place(f["n"]), ref)
        raise GeoError(f"unknown country code {ref!r} (use ISO 3166 alpha-3, for example KEN)")
    if prefer == "point":
        c = _city(ref)
        if c:
            return c
    try:
        return _from_place(find_place(ref), ref)
    except PlaceNotFound:
        pass
    c = _city(ref)
    if c:
        return c
    tips = _suggest_city(ref)
    raise GeoError(f"can't find {ref!r}" + (f" (did you mean {', '.join(tips)}?)" if tips else "")
                   + ". Use a country, state, county or named region, a city (city:Name), an ISO code, or lat,lon.")


def resolve_many(ref: str, prefer: str = "point") -> List[Located]:
    return [resolve(part, prefer) for part in re.split(r"\s*;\s*", ref.strip()) if part]


# ---- camera framing ---------------------------------------------------------------------

def merc_y(lat: float) -> float:
    s = math.sin(math.radians(max(-85.0511, min(85.0511, lat))))
    return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def merc_lat(y: float) -> float:
    n = math.pi - 2 * math.pi * y
    return math.degrees(math.atan(0.5 * (math.exp(n) - math.exp(-n))))


FRAME_ZOOM = {"globe": 1.7, "continental": 3.3, "local": 8.4}


def fit(bbox: BBox, width: int = 1920, height: int = 1080, pad: float = 0.18, min_zoom: float = 1.5, max_zoom: float = 11.0) -> Tuple[float, float, float]:
    """Centre and zoom that show bbox with `pad` (fraction of the frame) of room on every side."""
    w, s, e, n = bbox
    dx = max((e - w) / 360.0, 1e-9)
    dy = max(abs(merc_y(s) - merc_y(n)), 1e-9)
    zx = math.log2(width * (1 - 2 * pad) / (512 * dx))
    zy = math.log2(height * (1 - 2 * pad) / (512 * dy))
    cx = (w + e) / 2
    cy = merc_lat((merc_y(s) + merc_y(n)) / 2)
    return cx, cy, max(min_zoom, min(max_zoom, min(zx, zy)))


def view_for(loc: Located, frame: str = "", width: int = 1920, height: int = 1080) -> Tuple[float, float, float]:
    """(lon, lat, zoom) for showing a place. Areas fit their shape, cities and points sit at local scale."""
    if frame in ("globe", "continental"):
        return loc.lon, loc.lat, FRAME_ZOOM[frame]
    if frame == "local" or not loc.is_area:
        return loc.lon, loc.lat, FRAME_ZOOM["local"]
    pad = 0.25 if frame == "region" else 0.18
    cx, cy, z = fit(loc.bbox, width, height, pad)
    return cx, cy, (max(z, 5.0) if frame == "region" else z)


def suggest_names(query: str, n: int = 3) -> List[str]:
    """Names the atlas knows that look like `query`: countries, states and provinces and named regions first, then cities."""
    from map_scene.places import _dataset as _places, _named_regions, _norm

    key = _norm(query)
    if not key:
        return []
    pool = {}
    for ds in ("countries", "admin1"):
        try:
            for f in _places(ds):
                pool.setdefault(_norm(f["n"]), f["n"])
        except Exception:
            pass
    for v in _named_regions().values():
        pool.setdefault(_norm(v["name"]), v["name"])
    out = [pool[h] for h in difflib.get_close_matches(key, list(pool), n=n, cutoff=0.6)]
    out += [pool[k] for k in pool if key in k and pool[k] not in out][: max(0, n - len(out))]
    if len(out) < n:
        out += [c for c in _suggest_city(query) if c not in out]
    return out[:n]
