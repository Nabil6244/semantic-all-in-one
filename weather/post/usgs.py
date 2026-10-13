"""River gauges: USGS Water Services instantaneous values (gage height, parameter 00065) and the NWS water service's gauge page
(flood categories and historic crests, https://api.water.noaa.gov/nwps/v1/gauges/<USGS id or NWS LID>).

USGS marks each value: "P" provisional (may be revised: shown as PROVISIONAL on screen), "A" approved, "e" estimated, "R" revised.
Values flagged as equipment trouble, ice, backwater and the like carry no number and are skipped. A crest is the highest
gage height in the window; when the record has a gap next to it (a gauge often fails in a record flood) the time of the crest
is uncertain, so only its date is shown (always: the screen names the day, the report keeps the time)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

IV = "https://nwis.waterservices.usgs.gov/nwis/iv/"
NWPS = "https://api.water.noaa.gov/nwps/v1/gauges/"
CREDIT = "River gauges: U.S. Geological Survey (USGS); flood categories: NOAA National Weather Service."
GAP = timedelta(hours=2)
CATEGORIES = ("major", "moderate", "minor", "action")


def site_ok(site: str) -> str:
    if not re.fullmatch(r"\d{8,15}", str(site).strip()):
        raise ValueError(f"{site!r} is not a USGS site number (8 to 15 digits, e.g. 08074000)")
    return str(site).strip()


def iv_url(site: str, a: date, b: date, param: str = "00065") -> str:
    return f"{IV}?format=json&sites={site}&parameterCd={param}&startDT={a.isoformat()}&endDT={b.isoformat()}&siteStatus=all"


def nwps_url(site: str) -> str:
    return f"{NWPS}{site}"


@dataclass
class Series:
    site: str
    name: str
    lon: float
    lat: float
    unit: str
    points: List[Tuple[datetime, float, List[str]]] = field(default_factory=list)


def parse_iv(text: str, site: str, param: str = "00065") -> Series:
    d = json.loads(text)
    for ts in (d.get("value") or {}).get("timeSeries") or []:
        var = ts.get("variable") or {}
        code = ((var.get("variableCode") or [{}])[0]).get("value")
        if code != param:
            continue
        info = ts.get("sourceInfo") or {}
        geo = (info.get("geoLocation") or {}).get("geogLocation") or {}
        nodata = var.get("noDataValue")
        s = Series(site, info.get("siteName", site), float(geo.get("longitude")), float(geo.get("latitude")), (var.get("unit") or {}).get("unitCode", "ft"))
        for block in ts.get("values") or []:
            for v in block.get("value") or []:
                try:
                    x = float(v["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                if nodata is not None and x == float(nodata):
                    continue
                s.points.append((datetime.fromisoformat(v["dateTime"]), x, list(v.get("qualifiers") or [])))
        s.points.sort(key=lambda p: p[0])
        if s.points:
            return s
    raise ValueError(f"USGS has no gage height (parameter {param}) for site {site} in that window")


@dataclass
class Crest:
    when: datetime
    value: float
    provisional: bool
    qualifiers: List[str]
    gap_near: bool  # a gap of more than 2 h in the record beside the crest: its time is uncertain


def crest(s: Series, a: Optional[datetime] = None, b: Optional[datetime] = None) -> Crest:
    pts = [p for p in s.points if (a is None or p[0] >= a) and (b is None or p[0] <= b)]
    if not pts:
        raise ValueError(f"USGS site {s.site} has no gage height in that window")
    i = max(range(len(pts)), key=lambda k: (pts[k][1], -k))   # highest; the first time it was reached
    when, v, q = pts[i]
    gap = (i > 0 and when - pts[i - 1][0] > GAP) or (i + 1 < len(pts) and pts[i + 1][0] - when > GAP)
    return Crest(when, v, "P" in q, q, gap)


def any_provisional(s: Series) -> bool:
    return any("P" in q for _, _, q in s.points)


def short_name(site_name: str) -> str:
    """'Buffalo Bayou at Houston, TX' -> 'BUFFALO BAYOU'; 'San Jacinto Rv nr Sheldon, TX' -> 'SAN JACINTO RIVER'."""
    n = re.split(r"\s+(?:at|near|nr|abv|blw|above|below)\s+", str(site_name), maxsplit=1, flags=re.I)[0]
    n = re.sub(r"\bRv\b|\bR\b", "River", n)
    n = re.sub(r"\bCk\b", "Creek", n)
    n = re.sub(r"\bBy\b", "Bayou", n)
    return " ".join(n.split()).upper()


def parse_nwps(text: str) -> Dict[str, Any]:
    """{lid, name, categories: {major: 32.0, ...} (stages; missing ones left out), crests: [{time, stage, olddatum}]}."""
    d = json.loads(text)
    flood = d.get("flood") or {}
    cats = {}
    for k in CATEGORIES:
        v = ((flood.get("categories") or {}).get(k) or {}).get("stage")
        if isinstance(v, (int, float)) and v > -999:
            cats[k] = float(v)
    crests = [{"time": c.get("occurredTime"), "stage": float(c["stage"]), "olddatum": bool(c.get("olddatum")), "preliminary": c.get("preliminary")}
              for c in ((flood.get("crests") or {}).get("historic") or []) if isinstance(c.get("stage"), (int, float))]
    return {"lid": d.get("lid"), "name": d.get("name"), "categories": cats, "units": flood.get("stageUnits", "ft"), "crests": crests}


def category(stage: float, cats: Dict[str, float]) -> Optional[str]:
    """'major' / 'moderate' / 'minor' / 'action' (the highest reached), or None."""
    for k in CATEGORIES:
        if k in cats and stage >= cats[k]:
            return k
    return None


def record_standing(stage: float, when: datetime, crests: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Against the NWS list of historic crests (this event's own entry left out, within 3 days): {'record': bool, 'previous': crest}."""
    others = []
    for c in crests:
        try:
            t = datetime.fromisoformat(str(c["time"]).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if abs((t - when).total_seconds()) > 3 * 86400:
            others.append(dict(c, t=t))
    if not others:
        return None
    top = max(others, key=lambda c: c["stage"])
    return {"record": stage > top["stage"], "previous": {"time": top["time"], "stage": top["stage"], "olddatum": top["olddatum"]},
            "listed": len(others)}


def hourly(s: Series, a: datetime, b: datetime) -> List[Optional[float]]:
    """Hourly maxima from a to b (None for an hour with no value: the chart shows the gap)."""
    n = int((b - a).total_seconds() // 3600) + 1
    out: List[Optional[float]] = [None] * n
    for t, v, _ in s.points:
        k = int((t - a).total_seconds() // 3600)
        if 0 <= k < n and (out[k] is None or v > out[k]):
            out[k] = v
    return out


def utc(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
