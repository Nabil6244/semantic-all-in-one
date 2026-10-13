"""National Hurricane Center GIS archive -> what a storm layer draws.

    advisory(zip)   <id>_5day_<adv>.zip: the cone (5day_pgn), the forecast track (5day_lin), the forecast points (5day_pts)
                    and the coastal watches/warnings (ww_wwlin)
    best_track(zip) <id>_best_track.zip: the analysed positions every 6 hours (pts) and the track coloured by strength (lin)

Wind in the files is in knots; on screen it is mph rounded to 5, the way NHC's own public advisories write it
(135 kt -> 155 mph). The category is NHC's Saffir-Simpson number (SSNUM / SS) when the file has it."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .shapefile import Layers, ShapefileError, read_zip
from .timeline import UTC, iso

ARCHIVE = "https://www.nhc.noaa.gov/gis/forecast/archive/{id}_5day_{adv}.zip"
BEST = "https://www.nhc.noaa.gov/gis/best_track/{id}_best_track.zip"
STORM_ID = re.compile(r"^(AL|EP|CP)\d{2}\d{4}$")
ADV = re.compile(r"^\d{3}[A-Z]?$")
# NHC's coastal watch/warning colours (its cone graphic)
COAST = {"HWR": ("HURRICANE WARNING", "#FF0000"), "HWA": ("HURRICANE WATCH", "#FF99FF"),
         "TWR": ("TROPICAL STORM WARNING", "#3366FF"), "TWA": ("TROPICAL STORM WATCH", "#FFFF00")}
# category colours of the dots and the best-track line (TD, TS, Cat 1-5)
CAT_COLORS = {-1: "#5EBAFF", 0: "#00FAF4", 1: "#FFFFCC", 2: "#FFE775", 3: "#FFC140", 4: "#FF8F20", 5: "#FF6060"}
KIND_NAMES = {"TD": "TROP DEPRESSION", "TS": "TROP STORM", "STD": "SUBTROP DEPR", "SS": "SUBTROP STORM", "EX": "POST-TROPICAL",
              "LO": "LOW", "PTC": "POST-TROPICAL", "DB": "DISTURBANCE", "WV": "TROPICAL WAVE"}
MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1)}
ZONE_OFFSET = {"EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7, "PDT": -7, "PST": -8, "AST": -4, "HST": -10, "UTC": 0, "GMT": 0}


def check_storm(target: str) -> str:
    s = target.strip().upper()
    if not STORM_ID.match(s):
        raise ValueError(f"{target!r} is not an NHC storm id like AL092022 (basin AL/EP/CP, number, year)")
    return s


def mph(kt: Optional[float]) -> Optional[int]:
    """Knots -> mph rounded to 5 (NHC's public-advisory convention)."""
    if kt is None or kt >= 999:
        return None
    return int(round(kt * 1.15078 / 5.0) * 5)


def category(kt: Optional[float]) -> int:
    """Saffir-Simpson from the wind (kt): -1 depression, 0 tropical storm, 1..5."""
    if kt is None:
        return -1
    for cat, low in ((5, 137), (4, 113), (3, 96), (2, 83), (1, 64), (0, 34)):
        if kt >= low:
            return cat
    return -1


def strength_label(cat: int, kind: str) -> str:
    if kind in ("HU", "MH") or cat >= 1:
        return f"CAT {cat}"
    return KIND_NAMES.get(kind, "TROP STORM" if cat == 0 else "TROP DEPRESSION")


def parse_adv_date(text: str) -> datetime:
    """'1100 PM EDT Thu Sep 29 2022' -> UTC."""
    m = re.match(r"^\s*(\d{3,4})\s+(AM|PM)\s+([A-Z]{3})\s+\w{3}\s+(\w{3})\s+(\d{1,2})\s+(\d{4})", text or "")
    if not m:
        raise ValueError(f"advisory time {text!r} is not in NHC's form '1100 PM EDT Thu Sep 29 2022'")
    hhmm, ampm, zone, mon, day, year = m.groups()
    hhmm = hhmm.zfill(4)
    h, mi = int(hhmm[:2]) % 12 + (12 if ampm == "PM" else 0), int(hhmm[2:])
    local = datetime(int(year), MONTHS[mon], int(day), h, mi)
    return (local - timedelta(hours=ZONE_OFFSET.get(zone, 0))).replace(tzinfo=UTC)


def point_time(valid: str, adv_utc: datetime) -> datetime:
    """VALIDTIME 'DD/HHMM' (UTC) -> the full time: the first such day on or after the day before the advisory."""
    d, hm = valid.split("/")
    t = adv_utc.replace(day=1, hour=int(hm[:2]), minute=int(hm[2:]), second=0)
    for k in range(3):
        y, mo = t.year + (t.month - 1 + k) // 12, (t.month - 1 + k) % 12 + 1
        try:
            cand = t.replace(year=y, month=mo, day=int(d))
        except ValueError:
            continue
        if cand >= adv_utc - timedelta(days=1):
            return cand
    raise ValueError(f"forecast time {valid!r} does not follow the advisory ({iso(adv_utc)})")


def time_label(fl: str) -> str:
    """FLDATELBL '2022-09-30 8:00 AM Fri EDT' -> 'FRI 8 AM'."""
    m = re.match(r"^\d{4}-\d\d-\d\d\s+(\d{1,2}):(\d\d)\s+(AM|PM)\s+(\w{3})", fl or "")
    if not m:
        return ""
    h, mi, ampm, dow = m.groups()
    return f"{dow.upper()} {int(h)}{'' if mi == '00' else ':' + mi} {ampm}"


def advisory(blob: bytes) -> Dict[str, Any]:
    """An advisory zip -> {name, adv, adv_date, issued (UTC ISO), cone, track, points, coast}."""
    layers: Layers = read_zip(blob)
    pgn, lin, pts = layers.find("_5day_pgn"), layers.find("_5day_lin"), layers.find("_5day_pts")
    head = (pgn.records or lin.records)[0].attrs
    issued = parse_adv_date(head.get("ADVDATE", ""))
    cone = [poly for r in pgn.records if r.kind == "polygon" for poly in r.parts]
    track = [pt for r in lin.records if r.kind == "line" for part in r.parts for pt in part]
    points = []
    for r in sorted(pts.records, key=lambda r: r.attrs.get("TAU") or 0):
        a = r.attrs
        kt = a.get("MAXWIND")
        kt = None if kt is None or kt >= 999 else float(kt)
        ss = a.get("SSNUM")
        cat = int(ss) if ss is not None and kt is not None and kt >= 64 else category(kt)
        when = point_time(a["VALIDTIME"], issued)
        points.append({"lon": r.parts[0], "lat": r.parts[1], "tau": a.get("TAU"), "time": iso(when), "wind_kt": kt, "wind_mph": mph(kt),
                       "gust_kt": a.get("GUST"), "kind": a.get("STORMTYPE", ""), "cat": cat, "when_label": time_label(a.get("FLDATELBL", "")),
                       "local_label": a.get("FLDATELBL", "")})
    coast = []
    try:
        ww = layers.find("_ww_wwlin")
        for r in ww.records:
            code = r.attrs.get("TCWW", "")
            if code in COAST and r.kind == "line":
                coast += [{"code": code, "label": COAST[code][0], "color": COAST[code][1], "coords": part} for part in r.parts if len(part) >= 2]
    except ShapefileError:
        pass   # an advisory with no coastal watches or warnings
    name = (pts.records[0].attrs.get("STORMNAME") if pts.records else "") or head.get("STORMNAME", "")
    return {"name": name, "adv": str(head.get("ADVISNUM", "")), "adv_date": head.get("ADVDATE", ""), "issued": iso(issued),
            "cone": cone, "track": track, "points": points, "coast": coast}


def best_track(blob: bytes) -> Dict[str, Any]:
    """A best-track zip -> {points: [{lon, lat, time, wind_kt, wind_mph, mslp, kind, cat}], segments: [{coords, cat}]}."""
    layers: Layers = read_zip(blob)
    pts, lin = layers.find("_pts"), layers.find("_lin")
    points = []
    for r in pts.records:
        a = r.attrs
        dtg = str(int(a["DTG"])) if a.get("DTG") is not None else ""
        t = datetime.strptime(dtg, "%Y%m%d%H").replace(tzinfo=UTC) if len(dtg) == 10 else None
        if t is not None and a.get("HHMM") and str(a["HHMM"]).isdigit():
            t = t.replace(hour=int(str(a["HHMM"]).zfill(4)[:2]), minute=int(str(a["HHMM"]).zfill(4)[2:]))
        kt = a.get("INTENSITY")
        kind = a.get("STORMTYPE", "")
        cat = int(a["SS"]) if a.get("SS") and kind in ("HU", "MH") else category(kt) if kind not in ("LO", "EX", "DB", "WV") else -1
        points.append({"lon": r.parts[0], "lat": r.parts[1], "time": iso(t), "wind_kt": kt, "wind_mph": mph(kt), "mslp": a.get("MSLP"),
                       "kind": kind, "cat": cat, "name": a.get("STORMNAME", "")})
    segments = []
    for r in lin.records:
        kind = r.attrs.get("STORMTYPE", "")
        ss = r.attrs.get("SS")
        cat = int(ss) if ss and kind in ("HU", "MH") else (0 if kind in ("TS", "SS") else -1)
        segments += [{"coords": part, "cat": cat, "kind": kind} for part in r.parts if len(part) >= 2]
    return {"points": points, "segments": segments}
