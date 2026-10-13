"""Radar providers (docs/weather/radar_source_terms.md §4): which service draws a radar loop, chosen per layer with extra
{"provider": "iem_n0q"} (the app-wide default is iem_n0q). The renderer only ever sees the resolved frames, never a URL
written here by hand.

    iem_n0q           NOAA/NWS NEXRAD base-reflectivity mosaic made by the Iowa Environmental Mesonet: every 5 minutes since
                      13 Nov 2010, public domain. XYZ tiles (checked against IEM's whole-CONUS picture over Hurricane Ian).
    noaa_mapservices  NOAA's radar_base_reflectivity_time ImageServer: federal, but about 2 hours of history and pictures by
                      area (exportImage), not XYZ tiles, so weather-engine cannot draw it yet (an integrator request).
    none              no radar: the beat stays on the map and the source line says the radar is not shown.

Frames: the scans IEM lists for the window (json/radar ... operation=list), thinned evenly to the frame count the layer
asks for. A gap in IEM's listing is kept as a gap (the previous picture holds), never filled with a made-up time."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from .timeline import UTC, iso, stamp

# The NWS reflectivity colours (dBZ) IEM's N0Q mosaic is drawn with; the legend shows this ramp.
DBZ_RAMP = [(5, "#04E9E7"), (10, "#019FF4"), (15, "#0300F4"), (20, "#02FD02"), (25, "#01C501"), (30, "#008E00"), (35, "#FDF802"),
            (40, "#E5BC00"), (45, "#FD9500"), (50, "#FD0000"), (55, "#D40000"), (60, "#BC0000"), (65, "#F800FD"), (70, "#9854C6"),
            (75, "#FDFDFD")]
LEGEND_LABELS = [(20, "LIGHT"), (50, "HEAVY"), (65, "HAIL")]   # 40 dBZ "MODERATE" collides with HEAVY on a 400 px bar


@dataclass(frozen=True)
class RadarProvider:
    id: str
    title: str
    url_template: str  # live picture ("" = none)
    archive_url_template: str  # one picture time: {stamp} = YYYYMMDDHHMI ("" = no archive)
    archive_from: str  # first archived time (UTC ISO), "" = none
    history_h: float  # how far back "latest" may reach
    max_zoom: int
    tile_size: int
    attribution: str  # the credit line in the description
    on_screen: str  # the source-line wording
    terms_url: str
    licence_note: str
    max_parallel: int = 4
    xyz: bool = True  # False: the service is not XYZ tiles (weather-engine cannot draw it yet)
    list_url: str = ""  # scans in a window: {start} {end} as 2024-05-06T21:00Z
    latest_url: str = ""  # the newest scan's time
    step_min: int = 5
    legend: List[Tuple[float, str]] = field(default_factory=lambda: list(DBZ_RAMP))


PROVIDERS: Dict[str, RadarProvider] = {
    "iem_n0q": RadarProvider(
        id="iem_n0q", title="NEXRAD base reflectivity (IEM mosaic)",
        url_template="https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png",
        archive_url_template="https://mesonet.agron.iastate.edu/c/tile.py/1.0.0/ridge::USCOMP-N0Q-{stamp}/{z}/{x}/{y}.png",
        archive_from="2010-11-13T00:00:00+00:00", history_h=24 * 365 * 30, max_zoom=8, tile_size=256,
        attribution="Radar: NOAA/NWS NEXRAD via Iowa Environmental Mesonet (Iowa State University)",
        on_screen="Radar: NOAA/NWS NEXRAD via Iowa Environmental Mesonet",
        terms_url="https://mesonet.agron.iastate.edu/disclaimer.php",
        licence_note="public domain; attribution requested; not an official NWS product",
        list_url="https://mesonet.agron.iastate.edu/json/radar?operation=list&product=N0Q&radar=USCOMP&start={start}&end={end}",
        latest_url="https://mesonet.agron.iastate.edu/data/gis/images/4326/USCOMP/n0q_0.json"),
    "noaa_mapservices": RadarProvider(
        id="noaa_mapservices", title="NOAA radar base reflectivity (ImageServer)",
        url_template="https://mapservices.weather.noaa.gov/eventdriven/rest/services/radar/radar_base_reflectivity_time/ImageServer/exportImage"
                     "?bbox={bbox}&bboxSR=3857&imageSR=3857&size=256,256&format=png&transparent=true&time={time_ms}&f=image",
        archive_url_template="", archive_from="", history_h=2.0, max_zoom=8, tile_size=256,
        attribution="Radar: NOAA/NWS (NOAA map services)", on_screen="Radar: NOAA/NWS",
        terms_url="https://www.weather.gov/disclaimer", licence_note="public domain (US government)", xyz=False),
    "none": RadarProvider(
        id="none", title="No radar", url_template="", archive_url_template="", archive_from="", history_h=0, max_zoom=0, tile_size=256,
        attribution="", on_screen="Radar not shown", terms_url="", licence_note="", legend=[]),
}
DEFAULT_PROVIDER = "iem_n0q"
MAX_LATEST_AGE = timedelta(hours=1)  # a "latest" loop older than this at render time is stale
LATEST_SPAN = timedelta(hours=2)
DEFAULT_FRAMES = 18


def get_provider(pid: Optional[str]) -> RadarProvider:
    pid = pid or DEFAULT_PROVIDER
    if pid not in PROVIDERS:
        raise ValueError(f"unknown radar provider {pid!r} (use {', '.join(PROVIDERS)})")
    return PROVIDERS[pid]


def compact(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y%m%d%H%M")


def parse_scan_list(text: str) -> List[datetime]:
    """IEM json/radar list -> scan times (UTC), sorted."""
    d = json.loads(text)
    out = []
    for s in d.get("scans") or []:
        ts = str(s.get("ts", ""))
        try:
            out.append(datetime.strptime(ts, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC))
        except ValueError:
            continue
    return sorted(set(out))


def parse_latest(text: str) -> datetime:
    """IEM n0q_0.json -> the newest scan time."""
    v = json.loads(text)["meta"]["valid"]
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def pick_frames(scans: List[datetime], n: int) -> List[datetime]:
    """n scans spread evenly across the listed ones (always the first and the last); every scan when there are fewer."""
    if n < 2:
        raise ValueError("a radar loop needs at least 2 frames")
    if len(scans) <= n:
        return list(scans)
    idx = sorted({round(i * (len(scans) - 1) / (n - 1)) for i in range(n)})
    return [scans[i] for i in idx]


def frame_provider(p: RadarProvider, t: datetime) -> Dict[str, Any]:
    """The tile provider record weather-engine gets for one picture time (its id changes with the time)."""
    return {"id": f"wx_radar_{p.id}_{compact(t)}", "title": f"{p.title} {stamp(t)}",
            "urlTemplate": p.archive_url_template.replace("{stamp}", compact(t)), "format": "png", "tileSize": p.tile_size,
            "maxNativeZoom": p.max_zoom}


def fetch_scans(p: RadarProvider, start: Optional[datetime], end: Optional[datetime], get_text: Callable[[str], str],
                now: datetime) -> Dict[str, Any]:
    """The scans of a window (or, start None, of the last two hours). Raises ValueError naming what is missing."""
    if not p.xyz:
        raise ValueError(f"radar provider {p.id} serves pictures by area, not map tiles; weather-engine cannot draw it yet "
                         f"(use iem_n0q)")
    if p.id == "none":
        return {"scans": [], "list_url": "", "latest": ""}
    latest_url = ""
    if start is None:
        latest_url = p.latest_url
        newest = parse_latest(get_text(latest_url))
        start, end = newest - LATEST_SPAN, newest
    else:
        if p.archive_from and start < datetime.fromisoformat(p.archive_from):
            raise ValueError(f"{p.title} is archived from {p.archive_from[:10]} only")
        if now - start > timedelta(hours=p.history_h):
            raise ValueError(f"{p.title} keeps about {p.history_h:g} hours of history; {stamp(start)} is too old")
    url = p.list_url.format(start=stamp(start), end=stamp(end + timedelta(minutes=1)))   # IEM's end is exclusive
    scans = [s for s in parse_scan_list(get_text(url)) if start <= s <= end]
    if not scans:
        raise ValueError(f"{p.title} lists no radar picture between {stamp(start)} and {stamp(end)}")
    return {"scans": [iso(s) for s in scans], "list_url": url, "latest": latest_url, "start": iso(start), "end": iso(end)}
