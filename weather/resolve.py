"""data_source -> data, with provenance, frozen in a snapshot (resolved.json) that the video is built from.

Fetching ("prep") writes the snapshot; rendering reads it and re-checks freshness on the data's own issue times. A video is
never built from data fetched at render time behind the user's back: what was prepared, and recorded against, is what is shown.

Freshness (weather.resolve.check_fresh):
  - a forecast whose NWS updateTime is more than 6 hours old is refused (at prep and again right before the render);
  - an observation more than 6 hours old is refused the same way;
  - an alert that has expired by render time is refused (fetch again: the warnings may have changed)."""

from __future__ import annotations

import json
import math
import re
import urllib.request

from .netssl import ssl_context
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .alerts import alert_areas
from .cities import City, find_city
from .nws import NwsClient, NwsError
from .provenance import Sourced
from .sidecar import WxRow
from .tz import parse_iso, weekday

SNAPSHOT_VERSION = 1
MAX_FORECAST_AGE = timedelta(hours=6)
MAX_OBS_AGE = timedelta(hours=6)
GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
GEOCOLOR_LAYER = "GOES-East_ABI_GeoColor"
GEOCOLOR_MAX_ZOOM = 7
GIBS_CREDIT = "Satellite: GOES-East GeoColor (NOAA/NESDIS), served by NASA GIBS."   # pakMap adds the GIBS acknowledgement itself


class StaleDataError(ValueError):
    pass


def f_from_c(c: float) -> int:
    """Celsius -> whole Fahrenheit, halves rounded up (31 C -> 88 F, 30.5 C -> 87 F)."""
    return int(math.floor(c * 9 / 5 + 32 + 0.5))


def icon_for(short: str, is_day: bool = True) -> str:
    """The icon for an NWS shortForecast ('Chance Showers And Thunderstorms' -> storm). First match wins."""
    s = (short or "").lower()
    rules = (("thunder", "storm"), ("t-storm", "storm"), ("blizzard", "snow"), ("snow", "snow"), ("flurr", "snow"),
             ("sleet", "sleet"), ("freezing", "sleet"), ("ice", "sleet"), ("rain", "rain"), ("shower", "rain"), ("drizzle", "rain"),
             ("fog", "fog"), ("haze", "fog"), ("smoke", "fog"), ("mostly cloudy", "cloud"), ("overcast", "cloud"),
             ("partly", "partly"), ("mostly sunny", "partly"), ("mostly clear", "partly"), ("cloudy", "cloud"), ("wind", "wind"), ("breezy", "wind"),
             ("blustery", "wind"), ("sunny", "sun"), ("clear", "sun"), ("fair", "sun"), ("hot", "sun"))
    for key, icon in rules:
        if key in s:
            if not is_day and icon == "sun":
                return "moon"
            if not is_day and icon == "partly":
                return "partly_night"
            return icon
    return "cloud"


# ---- the snapshot ---------------------------------------------------------------------------------------------------

@dataclass
class Snapshot:
    prepared: str  # ISO UTC time of the prep
    forecasts: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # "Dallas, TX" -> forecast
    observations: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # "Dallas, TX" -> observation
    alerts: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # "TX" -> {"areas": [...], "skipped": [...], ...}
    satellite: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # "geocolor@latest" -> {"time", "url_template", ...}
    notes: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)  # data of the layer types in weather/layers/ (each module owns its keys)

    def to_json(self) -> str:
        return json.dumps({"version": SNAPSHOT_VERSION, "prepared": self.prepared, "forecasts": self.forecasts, "observations": self.observations,
                           "alerts": self.alerts, "satellite": self.satellite, "notes": self.notes, "extra": self.extra}, indent=1, ensure_ascii=False)

    @staticmethod
    def from_json(text: str) -> "Snapshot":
        d = json.loads(text)
        if d.get("version") != SNAPSHOT_VERSION:
            raise ValueError(f"resolved.json is version {d.get('version')}, this Weather reads version {SNAPSHOT_VERSION}: fetch again")
        return Snapshot(d["prepared"], d.get("forecasts", {}), d.get("observations", {}), d.get("alerts", {}), d.get("satellite", {}), d.get("notes", []),
                        d.get("extra", {}))


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat()


# ---- products ---------------------------------------------------------------------------------------------------------

def fetch_forecast(client: NwsClient, city: City, notes: List[str]) -> Dict[str, Any]:
    point, _ = client.point(city.lat, city.lon)
    grid = f"{point.get('gridId')} {point.get('gridX')},{point.get('gridY')}"
    if grid != city.grid:
        notes.append(f"{city.key}: the NWS grid for this point is now {grid} (cities.json says {city.grid}); the NWS answer was used")
    url = point.get("forecast")
    if not url:
        raise NwsError(f"{city.key}: the NWS point lookup has no forecast link")
    props, resp = client.forecast(url)
    issued = props.get("updateTime") or props.get("generatedAt")
    if not issued:
        raise NwsError(f"{city.key}: the forecast has no updateTime")
    fetched = _iso(resp.fetched)

    def src(value: Any, unit: str) -> Dict[str, Any]:
        return Sourced(value, unit, "NWS forecast", url, grid, issued, fetched).to_dict()

    days: List[Dict[str, Any]] = []
    for p in props.get("periods") or []:
        temp = p.get("temperature")
        if temp is None:
            continue
        unit = p.get("temperatureUnit") or "F"
        t_f = int(temp) if unit == "F" else f_from_c(float(temp))
        pop = (p.get("probabilityOfPrecipitation") or {}).get("value")
        start = parse_iso(p["startTime"])
        if p.get("isDaytime"):
            days.append({"name": p.get("name", ""), "dow": weekday(start, city.tz), "start": p["startTime"], "short": p.get("shortForecast", ""),
                         "icon": icon_for(p.get("shortForecast", ""), True), "high": src(t_f, "F"),
                         "pop": src(int(pop), "%") if pop is not None else None, "low": None, "night_short": "",
                         "wind": src(p.get("windSpeed") or "", "") if p.get("windSpeed") else None, "wind_dir": p.get("windDirection") or ""})
        elif days and days[-1]["low"] is None and parse_iso(days[-1]["start"]) < start:
            days[-1]["low"] = src(t_f, "F")
            days[-1]["night_short"] = p.get("shortForecast", "")
            if pop is not None and (days[-1]["pop"] is None or int(pop) > days[-1]["pop"]["value"]):
                days[-1]["pop_night"] = src(int(pop), "%")
    if not days:
        raise NwsError(f"{city.key}: the forecast has no daytime periods")
    return {"city": city.key, "tz": city.tz, "lat": city.lat, "lon": city.lon, "grid": grid, "url": url, "issued": issued, "fetched": fetched,
            "days": days}


def fetch_observation(client: NwsClient, city: City, now: datetime, notes: List[str]) -> Dict[str, Any]:
    tried = []
    for station in city.stations:
        try:
            props, resp, url = client.latest_observation(station)
        except NwsError as exc:
            tried.append(f"{station} ({str(exc).rsplit(': ', 1)[-1] or 'no answer'})")
            continue
        c = (props.get("temperature") or {}).get("value")
        stamp = props.get("timestamp")
        if c is None or not stamp:
            tried.append(f"{station} (no temperature reported)")
            continue
        age = now - parse_iso(stamp)
        if age > MAX_OBS_AGE:
            tried.append(f"{station} (last report {age.total_seconds() / 3600:.1f} h old)")
            continue
        if tried:
            notes.append(f"{city.key}: current conditions from {station}; skipped {', '.join(tried)}")
        sourced = lambda v, u: Sourced(v, u, "NWS observation", url, station, stamp, _iso(resp.fetched)).to_dict()  # noqa: E731
        text = props.get("textDescription") or ""
        return {"city": city.key, "tz": city.tz, "lat": city.lat, "lon": city.lon, "station": station, "url": url, "issued": stamp,
                "fetched": _iso(resp.fetched), "temp": sourced(f_from_c(float(c)), "F"), "temp_c": float(c), "text": text,
                "icon": icon_for(text, _daylight(parse_iso(stamp), city.lon))}
    raise NwsError(f"{city.key}: no current observation from {', '.join(tried)}")


def _daylight(utc: datetime, lon: float) -> bool:
    """Rough local solar hour between 6 and 18 (enough to pick a sun or a moon icon)."""
    solar = (utc.hour + utc.minute / 60 + lon / 15) % 24
    return 6 <= solar < 18


def fetch_alerts(client: NwsClient, area: str) -> Dict[str, Any]:
    fc, resp, url = client.alerts(area)
    s = alert_areas(fc)
    return {"area": area, "url": url, "fetched": _iso(resp.fetched), "issued": _iso(resp.fetched), "areas": [a.to_dict() for a in s.areas],
            "skipped": s.skipped}


def _gibs_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "SemanticYTStudio-Weather/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=ssl_context()) as r:
        return r.read().decode("utf-8")


def _utc(text: str) -> datetime:
    text = text.strip()
    if len(text) == 10:  # a bare date starts at midnight UTC
        text += "T00:00:00Z"
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def geocolor_times(domain_xml: str) -> List["tuple[datetime, datetime, timedelta]"]:
    """GIBS DescribeDomains answer -> the available time intervals (start, end, step). Times can have gaps."""
    m = re.search(r"<Domain>([^<]*)</Domain>", domain_xml)
    out = []
    for part in (m.group(1).split(",") if m else []):
        bits = part.strip().split("/")
        if len(bits) == 3 and bits[2].startswith("PT") and bits[2].endswith("M"):
            out.append((_utc(bits[0]), _utc(bits[1]), timedelta(minutes=int(bits[2][2:-1]))))
        elif len(bits) == 1 and bits[0]:
            t = _utc(bits[0])
            out.append((t, t, timedelta(minutes=10)))
    return out


def pick_geocolor_time(target: str, now: datetime, intervals) -> datetime:
    """latest = the newest picture GIBS lists (about an hour behind real time); a named time must be one GIBS lists."""
    if target == "latest":
        best = None
        for start, end, step in intervals:
            if start > now:
                continue
            t = min(end, now)
            t -= (t - start) % step   # back onto the interval's own steps
            best = t if best is None or t > best else best
        if best is None:
            raise NwsError("GOES-East GeoColor lists no picture for the last day: try again later, or name a time")
        return best
    t = datetime.strptime(target, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    for start, end, step in intervals:
        if start <= t <= end and (t - start) % step == timedelta(0):
            return t
    raise NwsError(f"GOES-East GeoColor has no picture at {target} (GIBS keeps about two months, with gaps)")


def fetch_geocolor(target: str, now: datetime, get_text: Callable[[str], str] = _gibs_get) -> Dict[str, Any]:
    around = now if target == "latest" else datetime.strptime(target, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    a, b = (around - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), (around + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    domain_url = f"{GIBS}/1.0.0/{GEOCOLOR_LAYER}/default/GoogleMapsCompatible_Level{GEOCOLOR_MAX_ZOOM}/all/{a}--{b}.xml"
    t = pick_geocolor_time(target, now, geocolor_times(get_text(domain_url)))
    stamp = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    template = f"{GIBS}/{GEOCOLOR_LAYER}/default/{stamp}/GoogleMapsCompatible_Level{GEOCOLOR_MAX_ZOOM}/{{z}}/{{y}}/{{x}}.png"
    return {"layer": GEOCOLOR_LAYER, "time": stamp, "url_template": template, "max_zoom": GEOCOLOR_MAX_ZOOM, "credit": GIBS_CREDIT,
            "domain_url": domain_url, "issued": stamp, "fetched": _iso(now)}


# ---- prep -------------------------------------------------------------------------------------------------------------

def prepare(rows: List[WxRow], client: Optional[NwsClient], *, now: Optional[datetime] = None, gibs_get: Callable[[str], str] = _gibs_get,
            get_text: Optional[Callable[[str], str]] = None, get_bytes: Optional[Callable[[str], bytes]] = None) -> Snapshot:
    """Fetch everything the layers need (each product once) and check it is fresh enough to build a video from."""
    from .layers import FetchContext, get as layer_type, http_bytes, http_text

    now = now or datetime.now(timezone.utc)
    snap = Snapshot(prepared=_iso(now))
    ctx = FetchContext(snap=snap, now=now, nws=client, get_text=get_text or http_text, get_bytes=get_bytes or http_bytes)
    for r in rows:
        ds = r.data_source
        lt = layer_type(r.type) if r.type not in ("temp_marker", "forecast_strip", "now_card", "alert_area", "satellite", "source_line") else None
        if lt is not None:
            if lt.fetch is not None:
                lt.fetch(r, ctx)
            continue
        if ds is None:
            continue
        if client is None and ds.provider == "nws":
            raise NwsError("this plan needs National Weather Service data: set the NWS contact first")
        if ds.product == "forecast":
            city = find_city(ds.target)
            if city.key not in snap.forecasts:
                snap.forecasts[city.key] = fetch_forecast(client, city, snap.notes)
        elif ds.product == "obs":
            city = find_city(ds.target)
            if city.key not in snap.observations:
                snap.observations[city.key] = fetch_observation(client, city, now, snap.notes)
        elif ds.product == "alerts":
            area = ds.target.upper()
            if area not in snap.alerts:
                snap.alerts[area] = fetch_alerts(client, area)
                snap.notes += [f"alerts {area}: {s}" for s in snap.alerts[area]["skipped"]]
        elif ds.product == "geocolor":
            key = f"geocolor@{ds.target}"
            if key not in snap.satellite:
                snap.satellite[key] = fetch_geocolor(ds.target, now, gibs_get)
    check_fresh(snap, now, when="prep")
    return snap


def prune_stale(snap: Snapshot, now: datetime, notes: List[str]) -> int:
    """Generate's way (check_fresh stays the strict check): what is too old to show now is taken out of the snapshot, so the graphics
    that need it are left out (weather.autofix.build) and the video is still made. An alert that has ended is not drawn; a forecast,
    observation or map older than its limit is not shown. Each is a note. Returns how many items were taken out (project #005,
    2026-10-14: two California alerts had ended and the whole video stopped)."""
    from .layers import fresh_problems

    gone: List[str] = []
    for key in [k for k, f in snap.forecasts.items() if now - parse_iso(f["issued"]) > MAX_FORECAST_AGE]:
        del snap.forecasts[key]
        gone.append(f"the {key} forecast (too old)")
    for key in [k for k, o in snap.observations.items() if now - parse_iso(o["issued"]) > MAX_OBS_AGE]:
        del snap.observations[key]
        gone.append(f"the {key} observation (too old)")
    for area, a in snap.alerts.items():
        live = [x for x in a.get("areas", []) if not ((x.get("ends") or x.get("expires")) and parse_iso(x.get("ends") or x["expires"]) <= now)]
        ended = len(a.get("areas", [])) - len(live)
        if ended:
            a["areas"] = live
            gone.append(f"{ended} {area} alert(s) that have ended")
    for key in list(snap.extra):
        alone = Snapshot(snap.prepared, extra={key: snap.extra[key]})
        try:
            stale = fresh_problems(alone, now)
        except Exception:
            stale = []
        if stale:
            del snap.extra[key]
            gone.append("; ".join(stale))
    if gone:
        notes.append("weather data too old to show now was left out, with the graphics that need it: " + "; ".join(gone)
                     + " (fetch the data again to show them, and re-record any line whose numbers changed)")
    return len(gone)


def check_fresh(snap: Snapshot, now: datetime, *, when: str = "render") -> None:
    """Raise StaleDataError naming every product that is too old (or expired) to build a video from now."""
    problems = []

    def age_h(iso: str) -> float:
        return (now - parse_iso(iso)).total_seconds() / 3600

    for key, f in snap.forecasts.items():
        if now - parse_iso(f["issued"]) > MAX_FORECAST_AGE:
            problems.append(f"the {key} forecast was issued {age_h(f['issued']):.1f} h ago (more than 6 h)")
    for key, o in snap.observations.items():
        if now - parse_iso(o["issued"]) > MAX_OBS_AGE:
            problems.append(f"the {key} observation ({o['station']}) is {age_h(o['issued']):.1f} h old (more than 6 h)")
    for area, a in snap.alerts.items():
        gone = [x["event"] for x in a["areas"] if (x.get("ends") or x.get("expires")) and parse_iso(x.get("ends") or x["expires"]) <= now]
        if gone:
            problems.append(f"{len(gone)} alert(s) for {area} have ended ({', '.join(sorted(set(gone)))})")
    from .layers import fresh_problems

    problems += fresh_problems(snap, now)
    if problems:
        raise StaleDataError(f"Weather data is not fresh enough to {'prepare' if when == 'prep' else 'render'}: " + "; ".join(problems)
                             + ". Fetch the data again (and re-record any line whose numbers changed).")
