"""Find a place's area for a map scene.

Order (first hit wins):
  1. Inside the parent's context (a US state's counties, a country's provinces)
  2. Named-region list (map_scene/data/named_regions.json): informal regions
     such as "Florida Panhandle", defined as groups of official areas
  3. Official borders: countries, then states/provinces, then US counties
  4. AI fallback (Gemini, answer cached on disk so each name is asked once):
     a group of official areas, or a point
  5. Otherwise PlaceNotFound with a clear message
A point becomes a glowing pin + circle on the map.
"""

from __future__ import annotations

import gzip
import json
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

DATA_DIR = Path(__file__).resolve().parent / "data"

BBox = Tuple[float, float, float, float]  # min lon, min lat, max lon, max lat


class PlaceNotFound(LookupError):
    pass


@dataclass
class Place:
    name: str
    kind: str  # country | admin1 | county | region | point
    polygons: List[List[List[List[float]]]] = field(default_factory=list)  # MultiPolygon coordinates
    point: Optional[Tuple[float, float]] = None  # (lon, lat) for kind == "point"
    radius_km: float = 0.0
    country: str = ""  # ISO3 where known
    state: str = ""  # US state for counties / US regions
    source: str = ""  # boundary | named_region | ai

    @property
    def is_point(self) -> bool:
        return self.kind == "point"

    def main_polygons(self) -> list:
        """Polygons that make up the place's main landmass (drops far-flung
        islets so e.g. a country's camera doesn't span the antimeridian)."""
        if not self.polygons:
            return []
        areas = [abs(_ring_area(p[0])) for p in self.polygons]
        biggest = max(areas)
        return [p for p, a in zip(self.polygons, areas) if a >= biggest * 0.1]

    def bbox(self) -> BBox:
        if self.is_point:
            lon, lat = self.point
            # A site is shown with its surroundings (like the reference), not
            # filling the screen: at least ~40 km around it.
            d_lat = max(self.radius_km * 4.0, 40.0) / 111.0
            d_lon = d_lat / max(0.2, _cos_deg(lat))
            return (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)
        xs, ys = [], []
        for poly in self.main_polygons():
            for x, y in poly[0]:
                xs.append(x)
                ys.append(y)
        return (min(xs), min(ys), max(xs), max(ys))

    def anchor(self) -> Tuple[float, float]:
        """A point well inside the place (for its label's pointer line)."""
        if self.is_point:
            return self.point
        if self.kind == "region":  # many counties: the whole shape, not one piece
            return _inner_point_of_many(self.main_polygons(), self.outline(), self.bbox())
        biggest = max(self.polygons, key=lambda p: abs(_ring_area(p[0])))
        return _inner_point(biggest)

    def outline(self) -> List[List[List[float]]]:
        """Outer border only: edges shared by two of this place's polygons
        (e.g. between the counties of a region) are dropped."""
        return _outer_edges(self.polygons)

    def geojson(self) -> dict:
        if self.is_point:
            return {"type": "Point", "coordinates": list(self.point)}
        return {"type": "MultiPolygon", "coordinates": self.polygons}


# ---- data ------------------------------------------------------------------

_LOAD_LOCK = threading.Lock()


@lru_cache(maxsize=None)
def _dataset(name: str) -> list:
    with _LOAD_LOCK:
        with gzip.open(DATA_DIR / f"{name}.json.gz", "rt", encoding="utf-8") as fh:
            return json.load(fh)["features"]


@lru_cache(maxsize=1)
def _named_regions() -> Dict[str, dict]:
    data = json.loads((DATA_DIR / "named_regions.json").read_text(encoding="utf-8"))
    return {_norm(k): dict(v, name=k) for k, v in data["regions"].items()}


def _norm(text: str) -> str:
    t = (text or "").lower().replace("&", " and ")
    t = re.sub(r"\bsaint\b", "st", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"^the ", "", t)


_COUNTY_WORDS = re.compile(r"\s+(county|parish|borough|census area|city and borough|municipality)$")


def _names(feature: dict) -> List[str]:
    return [_norm(feature["n"])] + [_norm(a) for a in feature.get("alt", [])]


def _to_place(feature: dict, kind: str) -> Place:
    return Place(name=feature["n"], kind=kind, polygons=feature["g"]["coordinates"],
                 country=feature.get("iso", "USA" if kind == "county" else ""),
                 state=feature.get("state", feature["n"] if kind == "admin1" and feature.get("iso") == "USA" else ""),
                 source="boundary")


def _match(dataset: str, key: str, *, where: Callable[[dict], bool] = lambda f: True) -> List[dict]:
    return [f for f in _dataset(dataset) if where(f) and key in _names(f)]


def _county(key: str, state: Optional[str]) -> Optional[Place]:
    bare = _COUNTY_WORDS.sub("", key)
    hits = [f for f in _dataset("us_counties")
            if (state is None or _norm(f["state"]) == _norm(state))
            and (bare == _norm(f["n"]) or key in _names(f))]
    return _to_place(hits[0], "county") if len(hits) == 1 else None


def _from_components(name: str, kind_key: str, items: Sequence[str], source: str) -> Optional[Place]:
    polygons, state, country = [], "", ""
    for item in items:
        outer, _, inner = str(item).partition("|")
        if kind_key == "us_counties":
            hit = _county(_norm(inner), outer)
            if hit is None:
                return None
            state, country = outer, "USA"
        elif kind_key == "admin1":
            hits = [f for f in _dataset("admin1") if _norm(inner) in _names(f)
                    and (_norm(outer) in (_norm(f.get("country", "")), _norm(f.get("iso", ""))))]
            if not hits:
                return None
            hit, country = _to_place(hits[0], "admin1"), hits[0].get("iso", "")
        elif kind_key == "countries":
            hits = _match("countries", _norm(item))
            if not hits:
                return None
            hit = _to_place(hits[0], "country")
        elif kind_key == "countries_iso":
            # Continents / multi-country regions: a code missing from the
            # bundled data (a tiny territory) is skipped, not fatal.
            hits = [f for f in _dataset("countries") if f.get("iso") == str(item).strip().upper()]
            if not hits:
                continue
            hit = _to_place(hits[0], "country")
        else:
            return None
        polygons.extend(hit.polygons)
    if not polygons:
        return None
    return Place(name=name, kind="region", polygons=polygons, country=country, state=state, source=source)


def _within_parent(key: str, parent: Place) -> Optional[Place]:
    if parent.kind in ("admin1", "region") and parent.country == "USA" and parent.state:
        hit = _county(key, parent.state)
        if hit:
            return hit
    if parent.kind == "country":
        hits = _match("admin1", key, where=lambda f: f.get("iso") == parent.country)
        if hits:
            return _to_place(hits[0], "admin1")
    return None


# ---- public ----------------------------------------------------------------

AiResolver = Callable[[str, Optional[str]], Optional[dict]]


def find_place(name: str, *, parent: Optional[Place] = None, ai: Optional[AiResolver] = None) -> Place:
    key = _norm(name)
    if not key:
        raise PlaceNotFound("Map place is empty.")
    if parent is not None:
        hit = _within_parent(key, parent)
        if hit:
            return hit
    region = _named_regions().get(key)
    if region:
        for kind_key in ("us_counties", "admin1", "countries", "countries_iso"):
            if kind_key in region:
                hit = _from_components(region["name"], kind_key, region[kind_key], "named_region")
                if hit:
                    return hit
    countries = _match("countries", key)
    if countries:
        return _to_place(countries[0], "country")
    admin1 = _match("admin1", key)
    if admin1:
        admin1.sort(key=lambda f: f.get("iso") != "USA")  # "Georgia" alone is the country above
        return _to_place(admin1[0], "admin1")
    county_name, _, county_state = name.partition(",")
    county = _county(_norm(county_name), county_state.strip() or None)
    if county:
        return county
    if ai is not None:
        answer = None
        try:
            answer = ai(name, parent.name if parent is not None else None)
        except Exception:
            answer = None
        place = _place_from_ai(name, answer)
        if place is not None:
            return place
    where = f" in {parent.name}" if parent is not None else ""
    ai_error = getattr(ai, "last_error", None) if ai is not None else None
    if ai_error:
        raise PlaceNotFound(
            f"Couldn't find \"{name}\"{where}: it isn't in the built-in map data, and the AI place lookup "
            f"failed ({ai_error}). Try again later, or name the county, state or country around it."
        )
    raise PlaceNotFound(
        f"Couldn't find \"{name}\"{where} on the map. Use an official name (country, state/province, "
        "US county, continent) or a region from the named-region list, or pick another source for this scene."
    )


def _place_from_ai(name: str, answer: Optional[dict]) -> Optional[Place]:
    if not isinstance(answer, dict):
        return None
    kind = answer.get("type")
    if kind == "point":
        try:
            lon, lat = float(answer["lon"]), float(answer["lat"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return None
        return Place(name=name, kind="point", point=(lon, lat),
                     radius_km=float(answer.get("radius_km") or 8.0), source="ai")
    if kind in ("us_counties", "admin1", "countries") and isinstance(answer.get("items"), list):
        return _from_components(name, kind, answer["items"], "ai")
    return None


def sea_polygon(view: BBox) -> dict:
    """Everything that isn't land near ``view``, from Natural Earth's land
    outlines: painted flat navy over the satellite sea (as in the reference
    style), which also hides the imagery's uneven ocean tiles.

    Rings nest (coast -> lake -> island in the lake -> ...): even depth is
    land (a hole in the sea), odd depth is water (its own sea polygon) —
    a fill can't have a hole inside a hole."""
    minx, miny, maxx, maxy = view
    rings = []
    for feature in _dataset("land"):
        for poly in feature["g"]["coordinates"]:
            xs, ys = [p[0] for p in poly[0]], [p[1] for p in poly[0]]
            if max(xs) < minx or min(xs) > maxx or max(ys) < miny or min(ys) > maxy:
                continue
            rings.extend(poly)
    boxes = [(min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)) for r in rings]
    areas = [abs(_ring_area(r)) for r in rings]
    parent: List[Optional[int]] = []
    for i, r in enumerate(rings):
        x, y = r[0]
        best = None
        for j, other in enumerate(rings):
            b = boxes[j]
            if i == j or areas[j] <= areas[i] or not (b[0] <= x <= b[2] and b[1] <= y <= b[3]):
                continue
            if _point_in_ring(x, y, other) and (best is None or areas[j] < areas[best]):
                best = j
        parent.append(best)
    depth = []
    for i in range(len(rings)):
        d, j = 0, parent[i]
        while j is not None:
            d, j = d + 1, parent[j]
        depth.append(d)
    world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]
    polys = [[world] + [r for r, d in zip(rings, depth) if d == 0]]
    for i, r in enumerate(rings):
        if depth[i] % 2 == 1:
            polys.append([r] + [rings[k] for k in range(len(rings)) if parent[k] == i])
    return {"type": "MultiPolygon", "coordinates": polys}


# ---- geometry helpers --------------------------------------------------------

def _cos_deg(lat: float) -> float:
    import math

    return math.cos(math.radians(lat))


def _ring_area(ring) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:])) / 2.0


def _point_in_ring(x: float, y: float, ring) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / ((y1 - y0) or 1e-12) + x0:
            inside = not inside
    return inside


def _dist_to_ring(x: float, y: float, ring) -> float:
    best = float("inf")
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        dx, dy = x1 - x0, y1 - y0
        t = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / ((dx * dx + dy * dy) or 1e-12)))
        px, py = x0 + t * dx, y0 + t * dy
        best = min(best, (x - px) ** 2 + (y - py) ** 2)
    return best ** 0.5


def _inner_point(polygon) -> Tuple[float, float]:
    """Point inside the polygon, farthest from its edge (grid search)."""
    outer, holes = polygon[0], polygon[1:]
    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    best, best_d = None, -1.0
    steps = 24
    for i in range(1, steps):
        for j in range(1, steps):
            x = minx + (maxx - minx) * i / steps
            y = miny + (maxy - miny) * j / steps
            if not _point_in_ring(x, y, outer) or any(_point_in_ring(x, y, h) for h in holes):
                continue
            d = _dist_to_ring(x, y, outer)
            if d > best_d:
                best, best_d = (x, y), d
    if best is None:
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    return best


def _inner_point_of_many(polygons, outline, bbox: BBox) -> Tuple[float, float]:
    """Point inside any of the polygons, farthest from the combined outer border."""
    segments = [seg for line in outline for seg in zip(line, line[1:])]
    stride = max(1, len(segments) // 1500)
    segments = segments[::stride]
    minx, miny, maxx, maxy = bbox
    best, best_d = None, -1.0
    steps = 24
    for i in range(1, steps):
        for j in range(1, steps):
            x = minx + (maxx - minx) * i / steps
            y = miny + (maxy - miny) * j / steps
            if not any(_point_in_ring(x, y, p[0]) for p in polygons):
                continue
            d = min(_dist_to_ring(x, y, [a, b]) for a, b in segments) if segments else 0.0
            if d > best_d:
                best, best_d = (x, y), d
    if best is None:
        return ((minx + maxx) / 2, (miny + maxy) / 2)
    return best


def _outer_edges(polygons) -> List[List[List[float]]]:
    counts: Dict[tuple, int] = {}
    edges = []
    for poly in polygons:
        for ring in poly:
            for a, b in zip(ring, ring[1:]):
                ka, kb = tuple(a), tuple(b)
                key = (ka, kb) if ka <= kb else (kb, ka)
                counts[key] = counts.get(key, 0) + 1
                edges.append((ka, kb, key))
    kept = [(a, b) for a, b, key in edges if counts[key] == 1]
    # Chain consecutive edges into lines (fewer, smoother strokes).
    lines: List[List[List[float]]] = []
    for a, b in kept:
        if lines and lines[-1][-1] == list(a):
            lines[-1].append(list(b))
        else:
            lines.append([list(a), list(b)])
    return lines
