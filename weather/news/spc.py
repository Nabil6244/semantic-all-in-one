"""Storm Prediction Center: categorical convective outlooks and the storm reports.

Outlooks (GeoJSON, SPC's own colours in each feature):
    current   https://www.spc.noaa.gov/products/outlook/day1otlk_cat.nolyr.geojson (day1..day3)
    archive   https://www.spc.noaa.gov/products/outlook/archive/YYYY/day1otlk_YYYYMMDD_HHMM_cat.nolyr.geojson
              Day 1 issuances 0100 (of the day before's convective day), 1200/1300, 1630, 2000 UTC; day 2: 0600, 1730; day 3: 0730.
Storm reports: https://www.spc.noaa.gov/climo/reports/YYMMDD_rpts_filtered.csv -- three tables (tornado, wind, hail) for the
convective day 12 UTC to 11:59 UTC the next day; times are UTC (HHMM). They are PRELIMINARY, and always labelled so."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List

from .timeline import UTC, iso

CURRENT = "https://www.spc.noaa.gov/products/outlook/day{n}otlk_cat.nolyr.geojson"
ARCHIVE = "https://www.spc.noaa.gov/products/outlook/archive/{y}/day{n}otlk_{ymd}_{hhmm}_cat.nolyr.geojson"
REPORTS = "https://www.spc.noaa.gov/climo/reports/{yymmdd}_rpts_filtered.csv"
DEFAULT_ISSUE = {1: ["1300", "1200", "1630"], 2: ["1730", "0600"], 3: ["0730"]}
SELECTOR = re.compile(r"^day(?P<n>[123])(?:_(?P<hhmm>\d{4}))?$")
# SPC's categorical colours (also inside every file; these are used when a file has none)
SPC_COLORS = {"TSTM": ("#C1E9C1", "#55BB55"), "MRGL": ("#66A366", "#005500"), "SLGT": ("#FFE066", "#DDAA00"),
              "ENH": ("#FFA366", "#FF6600"), "MDT": ("#E06666", "#CC0000"), "HIGH": ("#EE99EE", "#CC00CC")}
REPORT_KINDS = ("tornado", "wind", "hail")
REPORT_COLORS = {"tornado": "#FF2020", "wind": "#3D7BFF", "hail": "#22C55E"}   # SPC's report map: red, blue, green


def outlook_selector(sel: str) -> "tuple[int, str]":
    m = SELECTOR.match(sel or "day1")
    if not m:
        raise ValueError(f"#{sel}: an SPC outlook selector is day1, day2 or day3, optionally with its UTC issue time (day1_1630)")
    return int(m.group("n")), m.group("hhmm") or ""


def outlook_urls(day: str, sel: str) -> List[str]:
    """The URLs to try, in order, for spc:outlook@<day or latest>#<sel>."""
    n, hhmm = outlook_selector(sel)
    if day == "latest":
        return [CURRENT.format(n=n)]
    d = datetime.strptime(day, "%Y-%m-%d")
    return [ARCHIVE.format(y=d.year, n=n, ymd=d.strftime("%Y%m%d"), hhmm=h) for h in ([hhmm] if hhmm else DEFAULT_ISSUE[n])]


def _spc_time(text: str) -> str:
    return iso(datetime.strptime(str(text), "%Y%m%d%H%M").replace(tzinfo=UTC)) if text else ""


def outlook(text: str) -> Dict[str, Any]:
    """A categorical outlook GeoJSON -> {issued, valid, expires, areas: [{label, name, fill, stroke, polys}]} (lowest risk first)."""
    d = json.loads(text)
    areas, issued, valid, expires = [], "", "", ""
    for f in sorted(d.get("features") or [], key=lambda f: (f.get("properties") or {}).get("DN", 0)):
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        label = p.get("LABEL", "")
        fill, stroke = SPC_COLORS.get(label, ("#B0B0B0", "#808080"))
        areas.append({"label": label, "name": p.get("LABEL2") or label, "fill": p.get("fill") or fill, "stroke": p.get("stroke") or stroke,
                      "polys": [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]})
        issued, valid, expires = _spc_time(p.get("ISSUE")), _spc_time(p.get("VALID")), _spc_time(p.get("EXPIRE"))
    return {"issued": issued, "valid": valid, "expires": expires, "areas": areas}


def report_day(day: str) -> "tuple[datetime, datetime]":
    """The convective day of spc:reports@YYYY-MM-DD: 12 UTC that day to 12 UTC the next."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    return d + timedelta(hours=12), d + timedelta(hours=36)


def reports(text: str, day: str) -> List[Dict[str, Any]]:
    """The filtered reports CSV -> [{kind, time (UTC ISO), lon, lat, place, county, state, magnitude}] in time order."""
    start, _end = report_day(day)
    out, kind = [], None
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if row[0] == "Time":
            kind = {"F_Scale": "tornado", "Speed": "wind", "Size": "hail"}.get(row[1])
            continue
        if kind is None or len(row) < 7 or not row[0].isdigit():
            continue
        hh, mm = int(row[0].zfill(4)[:2]), int(row[0].zfill(4)[2:])
        t = start.replace(hour=hh, minute=mm)
        if t < start:   # 0000-1159 belongs to the next calendar day
            t += timedelta(days=1)
        try:
            lat, lon = float(row[5]), float(row[6])
        except ValueError:
            continue
        out.append({"kind": kind, "time": iso(t), "lon": lon, "lat": lat, "place": row[2], "county": row[3], "state": row[4],
                    "magnitude": row[1]})
    out.sort(key=lambda r: r["time"])
    return out


def count(reps: List[Dict[str, Any]], kind: str = "") -> int:
    return sum(1 for r in reps if not kind or r["kind"] == kind)
