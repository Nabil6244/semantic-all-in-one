"""Storm-based NWS warnings of a past window, from the Iowa Environmental Mesonet's archive
(https://mesonet.agron.iastate.edu/geojson/sbw.geojson?sts=...&ets=...[&states=FL]): every polygon warning (tornado,
severe thunderstorm, flash flood, extreme wind, special marine ...) active in the window, with its VTEC phenomena (TO, SV, FF,
EW, MA ...), significance (W warning) and polygon times. A warning updated during its life appears once per polygon version; it
is drawn from its first polygon's start to its last polygon's end, and counted once (by office, phenomena and event number)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from .timeline import stamp

URL = "https://mesonet.agron.iastate.edu/geojson/sbw.geojson"
NAMES = {"TO": "Tornado Warning", "SV": "Severe Thunderstorm Warning", "FF": "Flash Flood Warning", "EW": "Extreme Wind Warning",
         "MA": "Special Marine Warning", "SQ": "Snow Squall Warning", "DS": "Dust Storm Warning", "FA": "Areal Flood Warning",
         "FL": "Flood Warning"}
# NWS map colours for the ones weather/alerts.py ALERT_COLORS does not list yet (integrator request: add them there)
EXTRA_COLORS = {"Extreme Wind Warning": "#FF8C00", "Special Marine Warning": "#FFA500", "Snow Squall Warning": "#C71585",
                "Areal Flood Warning": "#00FF00"}


def url(start, end, states: Optional[List[str]] = None) -> str:
    q = {"sts": stamp(start).replace("Z", ":00Z"), "ets": stamp(end).replace("Z", ":00Z")}
    if states:
        q["states"] = ",".join(s.upper() for s in states)
    return f"{URL}?{urlencode(q)}"


def color(name: str) -> str:
    from ..alerts import ALERT_COLORS, alert_color

    return ALERT_COLORS.get(name) or EXTRA_COLORS.get(name) or alert_color(name)


def warnings(text: str, phenomena: List[str]) -> List[Dict[str, Any]]:
    """sbw GeoJSON -> one record per warning of the wanted phenomena (significance W):
    {key, phenomena, name, wfo, eventid, issued, ends, polys (its first polygon), color} in issue order."""
    d = json.loads(text)
    out: Dict[str, Dict[str, Any]] = {}
    for f in d.get("features") or []:
        p = f.get("properties") or {}
        ph, sig = p.get("phenomena"), p.get("significance")
        if sig != "W" or (phenomena and ph not in phenomena):
            continue
        g = f.get("geometry") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        key = f"{p.get('wfo')}.{ph}.{p.get('eventid')}.{p.get('year')}"
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        begin = p.get("polygon_begin") or p.get("issue")
        end = p.get("polygon_end") or p.get("expire")
        rec = out.get(key)
        if rec is None:
            name = NAMES.get(ph, p.get("ps") or ph)
            out[key] = {"key": key, "phenomena": ph, "name": name, "wfo": p.get("wfo"), "eventid": p.get("eventid"),
                        "issued": p.get("issue") or begin, "starts": begin, "ends": end, "polys": polys, "color": color(name),
                        "emergency": bool(p.get("is_emergency")), "product": p.get("product_id", "")}
        else:
            if begin and begin < rec["starts"]:
                rec["starts"], rec["polys"] = begin, polys
            if end and end > rec["ends"]:
                rec["ends"] = end
    return sorted(out.values(), key=lambda r: (r["issued"], r["key"]))
