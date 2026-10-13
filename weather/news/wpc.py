"""Weather Prediction Center excessive rainfall outlooks (ERO).

    current  https://www.wpc.ncep.noaa.gov/exper/eromap/geojson/Day{n}_Latest.geojson
    archive  https://www.wpc.ncep.noaa.gov/archives/ero/YYYYMMDD/shp_<94e|98e|99e>_YYYYMMDDHH.zip (day 1 / 2 / 3; zipped shapefile)
             day 1 issuances 01, 09, 16 UTC; days 2-3: 09, 21 UTC.
Categories carry WPC's colours (its KML): Marginal green, Slight yellow, Moderate red, High magenta."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List

from .shapefile import read_zip
from .timeline import UTC, iso

CURRENT = "https://www.wpc.ncep.noaa.gov/exper/eromap/geojson/Day{n}_Latest.geojson"
ARCHIVE = "https://www.wpc.ncep.noaa.gov/archives/ero/{ymd}/shp_{code}_{ymd}{hh}.zip"
CODES = {1: "94e", 2: "98e", 3: "99e"}
DEFAULT_ISSUE = {1: ["09", "16", "01"], 2: ["09", "21"], 3: ["09", "21"]}
SELECTOR = re.compile(r"^day(?P<n>[123])(?:_(?P<hh>\d\d))?$")
ERO = {"Marginal": ("MARGINAL RISK", "#00FF00", 1), "Slight": ("SLIGHT RISK", "#FFFF00", 2), "Moderate": ("MODERATE RISK", "#FF0000", 3),
       "High": ("HIGH RISK", "#FF00FF", 4)}


def selector(sel: str) -> "tuple[int, str]":
    m = SELECTOR.match(sel or "day1")
    if not m:
        raise ValueError(f"#{sel}: a WPC outlook selector is day1, day2 or day3, optionally with its UTC issue hour (day1_16)")
    return int(m.group("n")), m.group("hh") or ""


def urls(day: str, sel: str) -> List[str]:
    n, hh = selector(sel)
    if day == "latest":
        return [CURRENT.format(n=n)]
    ymd = datetime.strptime(day, "%Y-%m-%d").strftime("%Y%m%d")
    return [ARCHIVE.format(ymd=ymd, code=CODES[n], hh=h) for h in ([hh] if hh else DEFAULT_ISSUE[n])]


def _when(text: str) -> str:
    return iso(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)) if text else ""


def _areas(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    areas, issued, start, end = [], "", "", ""
    for props, polys in features:
        risk = str(props.get("OUTLOOK", "")).split(" ")[0]
        if risk not in ERO or not polys:
            continue
        label, color, rank = ERO[risk]
        areas.append({"label": label, "color": color, "rank": rank, "polys": polys})
        issued, start, end = _when(props.get("ISSUE_TIME", "")), _when(props.get("START_TIME", "")), _when(props.get("END_TIME", ""))
    areas.sort(key=lambda a: a["rank"])
    return {"issued": issued, "valid": start, "expires": end, "areas": areas}


def from_geojson(text: str) -> Dict[str, Any]:
    feats = []
    for f in json.loads(text).get("features") or []:
        g = f.get("geometry") or {}
        if g.get("type") in ("Polygon", "MultiPolygon"):
            feats.append((f.get("properties") or {}, [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]))
    return _areas(feats)


def from_zip(blob: bytes) -> Dict[str, Any]:
    layers = read_zip(blob)
    feats = [(r.attrs, r.parts) for layer in layers.values() for r in layer.records if r.kind == "polygon"]
    return _areas(feats)
