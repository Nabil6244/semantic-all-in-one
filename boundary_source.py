"""City boundaries from OpenStreetMap (Nominatim), for planning only.

The app's own data has real polygons for countries, states/provinces and US counties but none for cities. For a city the narration discusses, this module
asks Nominatim once, checks that what came back really is that city (name, administrative type, country, position, a real Polygon/MultiPolygon), keeps
the validated outline in a per-user cache and never asks again. The renderer never calls the network: it only receives the polygon in the event.

Nominatim usage policy (https://operations.osmfoundation.org/policies/nominatim/): an identifying User-Agent, at most one request per second, no bulk
use, cache results. This module sends at most one request per `min_interval` seconds, at most `max_queries` new places per planning run, and remembers
both good answers and rejected ones so the same place is not asked twice. A network error is not remembered (it may be temporary).

Data © OpenStreetMap contributors, licensed under the Open Database Licence (ODbL) 1.0: https://www.openstreetmap.org/copyright
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ATTRIBUTION = "Place boundaries: © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)"
LICENCE = "ODbL 1.0"
ENDPOINT = "https://nominatim.openstreetmap.org/search"
OK_TTL_S = 365 * 86400
REJECT_TTL_S = 30 * 86400
MAX_POINTS = 2500                      # a city outline is simplified to about this many vertices in total
_PLACE_TYPES = {"administrative", "city", "town", "village", "municipality", "borough", "county", "hamlet", "suburb"}
_PREFIXES = re.compile(r"^(?:city|town|village|municipality|borough|county)\s+of\s+|\s+(?:city|town|municipality)$")

_lock = threading.Lock()
_last_request = [0.0]
_offline_until = [0.0]                 # after a network failure no further request is made for a while (a plan is compiled many times)
OFFLINE_BACKOFF_S = 600


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


@dataclass
class CityQuery:
    name: str
    country: str                       # the country's English name, for the query and for checking the answer
    iso3: str
    lon: float                         # where the app's own city list puts it: the answer must contain (or sit right next to) this point
    lat: float
    region: str = ""


@dataclass
class BoundaryResult:
    ok: bool
    reason: str = ""                   # why not, in words for the plan report
    polys: Optional[list] = None       # MultiPolygon coordinates [[ring, ...], ...]
    osm_type: str = ""
    osm_id: int = 0
    display_name: str = ""
    from_cache: bool = False
    queried: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


# ---- geometry ----------------------------------------------------------------------------------------------------------------------------
def _rings_ok(polys) -> bool:
    if not polys:
        return False
    for poly in polys:
        if not poly or any(len(r) < 4 for r in poly):
            return False
        for r in poly:
            if any(len(p) < 2 or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in r):
                return False
    return True


def _as_multipolygon(geom: Dict[str, Any]) -> Optional[list]:
    if geom.get("type") == "Polygon":
        return [geom["coordinates"]]
    if geom.get("type") == "MultiPolygon":
        return geom["coordinates"]
    return None                         # a Point, a line, a collection: never turned into an area


def _in_ring(x: float, y: float, ring) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi, xj, yj = ring[i][0], ring[i][1], ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def contains_point(polys, lon: float, lat: float) -> bool:
    for poly in polys:
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def bbox_of(polys) -> Tuple[float, float, float, float]:
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    return min(xs), min(ys), max(xs), max(ys)


def _km(lon1, lat1, lon2, lat2) -> float:
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110.57
    return math.hypot(dx, dy)


def _near(polys, lon: float, lat: float, km: float) -> bool:
    best = 1e9
    for poly in polys:
        for x, y in poly[0]:
            best = min(best, _km(lon, lat, x, y))
    return best <= km


def _rdp(pts, eps):
    if len(pts) < 5:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a][:2], pts[b][:2]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        far, idx = 0.0, -1
        for i in range(a + 1, b):
            d = abs(dy * (pts[i][0] - ax) - dx * (pts[i][1] - ay)) / norm
            if d > far:
                far, idx = d, i
        if far > eps and idx > 0:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def simplify(polys, max_points: int = MAX_POINTS):
    """Fewer vertices when the outline is heavy, never fewer than a valid ring; coordinates rounded to 5 decimals (about a metre)."""
    def count(ps):
        return sum(len(r) for poly in ps for r in poly)

    out = [[[[round(x, 5), round(y, 5)] for x, y in r] for r in poly] for poly in polys]
    eps = 1e-5
    while count(out) > max_points and eps < 0.05:
        eps *= 1.6
        nxt = []
        for poly in out:
            rings = []
            for r in poly:
                body = r[:-1] if r[0] == r[-1] else r              # a closed ring has the same first and last point: split it at the farthest vertex
                k = max(range(len(body)), key=lambda i: (body[i][0] - body[0][0]) ** 2 + (body[i][1] - body[0][1]) ** 2)
                s = _rdp(body[: k + 1], eps)[:-1] + _rdp(body[k:] + [body[0]], eps)
                rings.append(s if len(s) >= 4 else r)
            nxt.append(rings)
        out = nxt
    return out


# ---- the validation of one Nominatim answer ------------------------------------------------------------------------------------------------
def _country_matches(q: CityQuery, addr: Dict[str, Any], iso_of_name: Callable[[str], str]) -> bool:
    cc = fold(addr.get("country", ""))
    if not cc:
        return False
    if fold(q.country) == cc:
        return True
    return bool(q.iso3) and iso_of_name(addr.get("country", "")) == q.iso3


def validate(q: CityQuery, item: Dict[str, Any], iso_of_name: Callable[[str], str]) -> Tuple[bool, str, Optional[list]]:
    """-> (accepted, reason, polygons)."""
    if item.get("osm_type") not in ("relation", "way"):
        return False, "the match is a point, not an area", None
    if item.get("category") not in ("boundary", "place") or item.get("type") not in _PLACE_TYPES:
        return False, f"the match is a {item.get('category')}/{item.get('type')}, not a city or an administrative area", None
    names = {fold(item.get("name", "")), fold((item.get("display_name") or "").split(",")[0])}
    names |= {_PREFIXES.sub("", n).strip() for n in list(names)}
    if fold(q.name) not in names:
        return False, f"the match is called {item.get('name') or item.get('display_name', '')[:40]!r}, not {q.name!r}", None
    if not _country_matches(q, item.get("address") or {}, iso_of_name):
        return False, f"the match is not in {q.country}", None
    polys = _as_multipolygon(item.get("geojson") or {})
    if polys is None or not _rings_ok(polys):
        return False, "the match has no usable polygon", None
    west, south, east, north = bbox_of(polys)
    if _km(west, south, east, north) > 400:
        return False, "the match is far larger than a city", None
    if not (contains_point(polys, q.lon, q.lat) or _near(polys, q.lon, q.lat, 5.0)):
        return False, f"the match does not contain {q.name}'s position", None
    return True, "", polys


# ---- the store ---------------------------------------------------------------------------------------------------------------------------
def default_cache_dir() -> Path:
    try:
        from map_scene.render import cache_dir

        return Path(cache_dir()) / "boundaries"
    except Exception:
        return Path.home() / ".semantic_yt_studio" / "boundaries"


def _user_agent() -> str:
    try:
        from app_version import APP_VERSION  # type: ignore

        v = str(APP_VERSION)
    except Exception:
        v = "dev"
    return f"SemanticYTStudio/{v} (place-boundary-highlighting; planning-time lookups, cached)"


def _http_fetch(params: Dict[str, str], timeout: float = 10.0) -> List[Dict[str, Any]]:
    req = urllib.request.Request(f"{ENDPOINT}?{urllib.parse.urlencode(params)}", headers={"User-Agent": _user_agent(), "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class BoundaryStore:
    def __init__(self, cache_dir: Optional[Path] = None, fetch: Optional[Callable[[Dict[str, str]], List[Dict[str, Any]]]] = None, *, min_interval: float = 1.1,
                 max_queries: int = 8, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep, network: bool = True,
                 iso_of_name: Optional[Callable[[str], str]] = None):
        self.dir = Path(cache_dir) if cache_dir else default_cache_dir()
        self.fetch = fetch or _http_fetch
        self.min_interval, self.max_queries, self.now, self.sleep, self.network = min_interval, max_queries, now, sleep, network
        self.queries = 0
        self.iso_of_name = iso_of_name or (lambda n: "")

    # cache -----------------------------------------------------------------------------------------------------------------------------------
    def key(self, q: CityQuery) -> str:
        raw = "|".join([fold(q.name), fold(q.region), q.iso3 or fold(q.country), f"{q.lon:.1f}", f"{q.lat:.1f}"])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]

    def _path(self, q: CityQuery) -> Path:
        return self.dir / f"{self.key(q)}.json"

    def _read(self, q: CityQuery) -> Optional[BoundaryResult]:
        try:
            d = json.loads(self._path(q).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        age = self.now() - float(d.get("fetched", 0))
        if d.get("status") == "ok" and age < OK_TTL_S and _rings_ok(d.get("polys")):
            return BoundaryResult(True, polys=d["polys"], osm_type=d.get("osm_type", ""), osm_id=int(d.get("osm_id", 0)), display_name=d.get("display_name", ""),
                                  from_cache=True, meta={"licence": LICENCE})
        if d.get("status") == "rejected" and age < REJECT_TTL_S:
            return BoundaryResult(False, d.get("reason", "rejected earlier"), from_cache=True)
        return None

    def _write(self, q: CityQuery, d: Dict[str, Any]) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            d = dict(d, key=self.key(q), query={"name": q.name, "region": q.region, "country": q.country}, fetched=self.now(), licence=LICENCE, attribution=ATTRIBUTION)
            tmp = self._path(q).with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path(q))
        except OSError:
            pass                                                        # no cache is a slower next time, never a failed plan

    # lookup ----------------------------------------------------------------------------------------------------------------------------------
    def lookup(self, q: CityQuery) -> BoundaryResult:
        hit = self._read(q)
        if hit is not None:
            return hit
        if not self.network:
            return BoundaryResult(False, "not cached and the network is off")
        if self.now() < _offline_until[0]:
            return BoundaryResult(False, "OpenStreetMap could not be reached a moment ago; not trying again yet")
        if self.queries >= self.max_queries:
            return BoundaryResult(False, f"not looked up: this plan already asked OpenStreetMap about {self.max_queries} places (the limit that keeps it polite)")
        with _lock:
            wait = self.min_interval - (self.now() - _last_request[0])
            if wait > 0:
                self.sleep(wait)
            _last_request[0] = self.now()
        self.queries += 1
        params = {"q": ", ".join(x for x in (q.name, q.region, q.country) if x), "format": "jsonv2", "polygon_geojson": "1", "polygon_threshold": "0.0015",
                  "addressdetails": "1", "limit": "5", "accept-language": "en"}
        try:
            items = self.fetch(params)
        except Exception as exc:                                        # offline, timeout, blocked: not remembered, the highlight is skipped this time
            _offline_until[0] = self.now() + OFFLINE_BACKOFF_S
            return BoundaryResult(False, f"OpenStreetMap could not be reached ({type(exc).__name__})", queried=True)
        good, reasons = [], []
        for it in items or []:
            ok, why, polys = validate(q, it, self.iso_of_name)
            (good if ok else reasons).append((it, polys) if ok else why)
        ids = {(it.get("osm_type"), it.get("osm_id")) for it, _p in good}
        if len(ids) > 1:
            res = BoundaryResult(False, f"{len(ids)} different OpenStreetMap areas are called {q.name!r} in {q.country}: not guessing", queried=True)
        elif not good:
            res = BoundaryResult(False, (reasons[0] if reasons else f"OpenStreetMap has no area called {q.name!r}"), queried=True)
        else:
            it, polys = good[0]
            res = BoundaryResult(True, polys=simplify(polys), osm_type=it.get("osm_type", ""), osm_id=int(it.get("osm_id", 0)), display_name=it.get("display_name", ""),
                                 queried=True, meta={"licence": LICENCE})
        if res.ok:
            self._write(q, {"status": "ok", "polys": res.polys, "osm_type": res.osm_type, "osm_id": res.osm_id, "display_name": res.display_name})
        else:
            self._write(q, {"status": "rejected", "reason": res.reason})
        return res
