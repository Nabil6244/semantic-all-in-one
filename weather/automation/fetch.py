"""One snapshot of everything the daily forecast is written from: the forecast (and, where it answers, the latest observation) of
every covered metro, plus the national list of active alerts. Saved as coverage.json in the project (a weather.resolve.Snapshot:
forecasts and observations keyed "Dallas, TX"; the national alerts, summarised, in extra["auto:national_alerts"]).

The video itself is built from resolved.json (only the products its layers show), whose forecasts and observations are copied
from this snapshot, so the script and the screen say the same numbers from the same NWS answers."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..alerts import county_shapes
from ..cities import US_STATES
from ..nws import NwsClient, NwsError
from ..resolve import MAX_FORECAST_AGE, Snapshot, _iso, fetch_forecast, fetch_observation
from ..tz import parse_iso
from .coverage import Metro, metros

NATIONAL = "auto:national_alerts"
MAX_FORECAST_FAILURES = 3  # more covered cities than this without a usable forecast (none, or older than 6 h): the prep stops


class PrepDataError(RuntimeError):
    pass


def fetch_coverage(client: NwsClient, *, now: Optional[datetime] = None, covered: Optional[Sequence[Metro]] = None,
                   log: Callable[[str], None] = lambda s: None) -> Snapshot:
    """Fetch every covered metro and the national alerts. A missing observation is a note; a missing or too old (6 h) forecast leaves the city out, up to
    MAX_FORECAST_FAILURES cities, then PrepDataError; no national alerts is PrepDataError (the story needs them)."""
    now = now or datetime.now(timezone.utc)
    covered = list(covered if covered is not None else metros())
    snap = Snapshot(prepared=_iso(now))
    failed: List[str] = []
    for m in covered:
        log(f"forecast {m.key}")
        try:
            snap.forecasts[m.key] = fetch_forecast(client, m.city, snap.notes)
        except NwsError as exc:
            failed.append(f"{m.key} ({exc})")
            continue
        try:
            snap.observations[m.key] = fetch_observation(client, m.city, now, snap.notes)
        except NwsError as exc:
            snap.notes.append(f"{m.key}: no current observation ({exc})")
    for key in [k for k, f in snap.forecasts.items() if now - parse_iso(f["issued"]) > MAX_FORECAST_AGE]:
        age = (now - parse_iso(snap.forecasts[key]["issued"])).total_seconds() / 3600
        failed.append(f"{key} (its latest NWS forecast is {age:.1f} h old; offices update it early each morning)")
        del snap.forecasts[key]
        snap.observations.pop(key, None)
    if failed:
        snap.notes += [f"left out: {f}" for f in failed]
        if len(failed) > MAX_FORECAST_FAILURES:
            raise PrepDataError(f"{len(failed)} of {len(covered)} cities have no usable NWS forecast ({'; '.join(failed)}). "
                                "Nothing was written; try the prep again later.")
    log("alerts US")
    try:
        fc, resp, url = client.alerts("US")
    except NwsError as exc:
        raise PrepDataError(f"the national alerts could not be fetched ({exc}). Nothing was written; try the prep again in a few minutes.") from None
    snap.extra[NATIONAL] = {"url": url, "fetched": _iso(resp.fetched), "alerts": summarise_alerts(fc, covered)}
    return snap


# ---- the national alerts, summarised ------------------------------------------------------------------------------------

def _states(ugc: Sequence[str]) -> List[str]:
    return sorted({u[:2] for u in ugc if len(u) == 6 and u[:2] in US_STATES and u[2] in "CZ"})


def _ring_contains(ring, lon: float, lat: float) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i - 1][0], ring[i - 1][1]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _polys_contain(polys, lon: float, lat: float) -> bool:
    return any(poly and _ring_contains(poly[0], lon, lat) for poly in polys)


def _centre(polys) -> Optional[Tuple[float, float]]:
    pts = [p for poly in polys for p in (poly[0] if poly else [])]
    if not pts:
        return None
    return round(sum(p[1] for p in pts) / len(pts), 3), round(sum(p[0] for p in pts) / len(pts), 3)


def summarise_alerts(fc: Dict[str, Any], covered: Sequence[Metro]) -> List[Dict[str, Any]]:
    """The national FeatureCollection -> one small record per alert (no shapes): event, severity, the states it touches, whether
    it is over land, its rough centre, and the covered metros it covers (by county code, or by its own polygon)."""
    shapes = None
    out = []
    for f in fc.get("features", []):
        p = f.get("properties") or {}
        geo = p.get("geocode") or {}
        ugc = [str(u) for u in geo.get("UGC", [])]
        same = [str(s)[-5:] for s in geo.get("SAME", []) if len(str(s)) == 6]
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            polys = [g["coordinates"]]
        elif g.get("type") == "MultiPolygon":
            polys = g.get("coordinates") or []
        else:
            polys = []
        states = _states(ugc)
        hit = []
        for m in covered:
            if m.county_fips in same or (polys and _polys_contain(polys, m.city.lon, m.city.lat)):
                hit.append(m.key)
        centre = _centre(polys)
        if centre is None and same:
            shapes = shapes if shapes is not None else county_shapes()
            cs = [_centre(shapes[c]["polys"]) for c in same if c in shapes]
            cs = [c for c in cs if c]
            if cs:
                centre = (round(sum(c[0] for c in cs) / len(cs), 3), round(sum(c[1] for c in cs) / len(cs), 3))
        out.append({"id": str(p.get("id") or f.get("id") or ""), "event": p.get("event", ""), "severity": p.get("severity", ""),
                    "certainty": p.get("certainty", ""), "urgency": p.get("urgency", ""), "area": p.get("areaDesc") or "",
                    "sent": p.get("sent") or "", "expires": p.get("expires") or "", "ends": p.get("ends") or "",
                    "sender": p.get("senderName") or "", "states": states, "land": bool(states), "metros": hit,
                    "centre": list(centre) if centre else None})
    return out


def national_alerts(snap: Snapshot) -> List[Dict[str, Any]]:
    return list((snap.extra.get(NATIONAL) or {}).get("alerts") or [])


# ---- which forecast day is "the day" ----------------------------------------------------------------------------------------

def day_date(d: Dict[str, Any]) -> date:
    """A forecast day's local date (its start time is written in the city's own offset)."""
    return date.fromisoformat(str(d["start"])[:10])


def target_date(snap: Snapshot) -> date:
    """The date the forecast is for: the first daytime period every city still has. At 5:30 AM Central that is today
    everywhere; later in the day the East has moved on to tomorrow while the West still has this afternoon, and the video
    then speaks about tomorrow for every city."""
    firsts = [day_date(f["days"][0]) for f in snap.forecasts.values() if f.get("days")]
    if not firsts:
        raise PrepDataError("the snapshot has no forecast days")
    return max(firsts)


def day_index(snap: Snapshot, city_key: str, on: date) -> int:
    """1-based index (the #dayN of a data_source) of the city's forecast day on `on`."""
    for i, d in enumerate(snap.forecasts[city_key]["days"], start=1):
        if day_date(d) == on:
            return i
    raise PrepDataError(f"the {city_key} forecast has no day on {on.isoformat()}")


def distance_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))
