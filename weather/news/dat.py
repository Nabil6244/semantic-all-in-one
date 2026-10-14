"""NWS Damage Assessment Toolkit (DAT): the tornado tracks NWS survey teams map after an event.

    https://services.dat.noaa.gov/arcgis/rest/services/nws_damageassessmenttoolkit/DamageViewer/FeatureServer
      layer 1  Damage Lines   one line per surveyed tornado: start/end times (UTC), EF rating, peak wind (mph), path length (miles),
                              maximum width (yards), injuries, fatalities, the office (wfo), a name (event_id) and the survey notes
      layer 0  Damage Points  each surveyed damage indicator (EF, estimated wind)
      layer 2  Damage Polygons the EF-rated damage swaths

The service says of itself that its data, though quality controlled, is PRELIMINARY: the official record is NCEI's Storm Data,
published months later. Every value from here is shown and reported as preliminary. Queries are one envelope (the story's states)
and one UTC window; times are epoch milliseconds."""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

BASE = "https://services.dat.noaa.gov/arcgis/rest/services/nws_damageassessmenttoolkit/DamageViewer/FeatureServer"
CREDIT = "Tornado surveys: NOAA National Weather Service Damage Assessment Toolkit (preliminary; official record: NCEI Storm Data)."
# EF colours, light to dark (EFU: rated unknown)
EF_COLORS = {"EFU": "#BFBFBF", "EF0": "#FFE066", "EF1": "#FFA94D", "EF2": "#FF6B3D", "EF3": "#E8364F", "EF4": "#B5179E", "EF5": "#6A0DAD"}


def ms(t: datetime) -> int:
    return int(t.astimezone(timezone.utc).timestamp() * 1000)


def lines_url(bbox: Sequence[float], start: datetime, end: datetime) -> str:
    """The damage lines intersecting [west, south, east, north] whose time falls in the window, as GeoJSON."""
    q = {"where": "1=1", "geometry": ",".join(f"{x:g}" for x in bbox), "geometryType": "esriGeometryEnvelope", "inSR": "4326",
         "spatialRel": "esriSpatialRelIntersects", "time": f"{ms(start)},{ms(end)}", "outFields": "*", "outSR": "4326", "f": "geojson"}
    return f"{BASE}/1/query?" + urllib.parse.urlencode(q)


def _iso(v: Any) -> str:
    if isinstance(v, (int, float)) and v > 0:
        return datetime.fromtimestamp(v / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


def parse_lines(text: str) -> List[Dict[str, Any]]:
    """GeoJSON answer -> [{name, wfo, start, end, ef, efnum, wind_mph, length_mi, width_yd, injuries, fatalities, coords, comments}],
    in start-time order. ValueError for an answer that is not a feature collection (an error page, a server error)."""
    d = json.loads(text)
    if not isinstance(d, dict) or d.get("type") != "FeatureCollection":
        raise ValueError(f"the DAT answer is not a feature collection ({str(d.get('error') if isinstance(d, dict) else d)[:120]})")
    out = []
    for f in d.get("features") or []:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        coords = g.get("coordinates") or []
        if g.get("type") == "MultiLineString":
            coords = [pt for part in coords for pt in part]
        if len(coords) < 2:
            continue
        ef = str(p.get("efscale") or "EFU").upper().replace("-", "")
        out.append({"name": (p.get("event_id") or "").strip(), "wfo": p.get("wfo") or "", "start": _iso(p.get("starttime")), "end": _iso(p.get("endtime")),
                    "ef": ef if ef in EF_COLORS else "EFU", "efnum": p.get("efnum"), "wind_mph": p.get("maxwind"),
                    "length_mi": p.get("length"), "width_yd": p.get("width"), "injuries": p.get("injuries"), "fatalities": p.get("fatalities"),
                    "coords": [[round(x, 5), round(y, 5)] for x, y, *_ in coords], "comments": (p.get("comments") or "").strip(),
                    "qc": p.get("qc") or ""})
    return sorted(out, key=lambda r: r["start"])


def label(track: Dict[str, Any]) -> str:
    """'EF2 · 115 MPH · 1.47 MI · 450 YD' (the survey's own numbers; what is missing is left out)."""
    parts = [track["ef"]]
    if isinstance(track.get("wind_mph"), (int, float)) and track["wind_mph"] > 0:
        parts.append(f"{int(track['wind_mph'])} MPH")
    if isinstance(track.get("length_mi"), (int, float)) and track["length_mi"] > 0:
        parts.append(f"{track['length_mi']:.2f} MI")
    if isinstance(track.get("width_yd"), (int, float)) and track["width_yd"] > 0:
        parts.append(f"{int(track['width_yd'])} YD")
    return " · ".join(parts)
