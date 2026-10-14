"""Forecast hurricane pack: what is coming, from NHC's and WPC's live products (the same files are kept in NHC's archive).

    wind_arrival    nhc:arrival@EP202026#028A           earliest reasonable arrival of tropical-storm-force winds: time lines
                    nhc:arrival@EP202026#028A_likely    the most likely arrival time instead
    wind_prob       nhc:wsp@2026101406#34               chance of tropical-storm-force (34 kt) winds over 5 days (#50, #64 too)
                    nhc:wsp@latest#34
    rain_forecast   wpc:qpf@latest#day1-5               WPC's expected rain, 5 days (#day1-7: 7 days)
                    extra {"bbox": [west, south, east, north]}  the area drawn (at most 20 x 16 degrees)
    countdown       nhc:countdown@EP202026#028A          hours from the advisory until the forecast centre passes nearest a place
                    place "22.89,-109.92" extra {"text": "Cabo San Lucas"}

All are FORECASTS, labelled so on screen and in the numbers report, with the advisory / issuance they come from. A forecast more
than 12 hours old is refused at render time (fetch again)."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ..news import kml, nhc
from ..news.rows import at, first_answer
from ..news.timeline import iso
from ..provenance import Sourced
from . import LayerType, register, register_fresh

UTC = timezone.utc
API = "https://www.nhc.noaa.gov/storm_graphics/api/"
ARCH = "https://www.nhc.noaa.gov/gis/forecast/archive/"
WPC_QPF = {"day1-5": "https://www.wpc.ncep.noaa.gov/kml/qpf/QPF120hr_Day1-5_latest.kmz",
           "day1-7": "https://www.wpc.ncep.noaa.gov/kml/qpf/QPF168hr_Day1-7_latest.kmz"}
STALE = timedelta(hours=12)
CREDIT = "Forecasts: NOAA National Hurricane Center and Weather Prediction Center (forecasts, not observations)."


def _adv(sel: str) -> str:
    a = (sel or "").split("_")[0].upper()
    if not re.fullmatch(r"\d{3}[A-Z]?", a):
        raise ValueError("give the advisory as #028 or #028A (three digits)")
    return a


# ---- wind arrival --------------------------------------------------------------------------------------------------------------

def arrival_url(sid: str, sel: str) -> str:
    kind = "most_likely" if sel.lower().endswith("_likely") else "earliest_reasonable"
    return f"{API}{sid.upper()}_{_adv(sel)}adv_{kind}_toa_34.kmz"


def _check_arrival(row) -> None:
    nhc.check_storm(row.data_source.target)
    _adv(row.data_source.selector)


def _fetch_arrival(row, ctx) -> None:
    key = f"nhc_toa:{row.data_source.target.upper()}#{row.data_source.selector}"
    if key in ctx.snap.extra:
        return
    url = arrival_url(row.data_source.target, row.data_source.selector)
    urls = [url] + ([url.replace(f"_{_adv(row.data_source.selector)}adv", f"_{_adv(row.data_source.selector)[:3]}adv")]
                    if _adv(row.data_source.selector)[-1].isalpha() else [])   # arrival maps come with full advisories only
    try:
        url, blob = first_answer(urls, ctx.get_bytes, "the NHC arrival-time map")
    except ValueError as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    pms = kml.read(blob)
    timed = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", re.I)   # time lines only ("Thu 2 am"), not the 5% contour
    lines = [{"label": p.text or p.name, "coords": [list(c) for c in ln]} for p in pms for ln in p.lines
             if len(ln) >= 2 and timed.match(p.text or p.name or "")]
    if not lines:
        raise ValueError(f"{at(row)}: the NHC arrival-time map has no time lines")
    ctx.snap.extra[key] = {"url": url, "fetched": iso(ctx.now), "issued": iso(ctx.now), "lines": lines,
                           "kind": "most likely" if row.data_source.selector.lower().endswith("_likely") else "earliest reasonable"}


def _build_arrival(row, snap, window, out) -> None:
    v = snap.extra[f"nhc_toa:{row.data_source.target.upper()}#{row.data_source.selector}"]
    n = len(v["lines"])
    pts = []
    for i, ln in enumerate(v["lines"]):
        t_draw = round(window.t_in + 0.3 + i * min(0.6, (window.t_out - window.t_in) / max(1, n) / 2), 3)
        out.fills.append({"id": f"wx_{row.id}_l{i}", "type": "line", "kind": "border_trace", "coords": ln["coords"], "color": "#FFD43B",
                          "width": 4, "t_in": window.t_in, "t_out": window.t_out, "t_draw": t_draw, "draw_s": 0.8})
        mid = ln["coords"][len(ln["coords"]) // 2]
        label = ln["label"].upper()
        pts.append({"lon": mid[0], "lat": mid[1], "color": "#FFD43B", "label": label, "at": t_draw + 0.8, "size": 5})
        out.report.add(row.id, f"{v['kind']} arrival of tropical-storm-force winds (NHC forecast)", label,
                       Sourced(label, "", f"NHC {v['kind']} arrival time of 34-kt winds (forecast; NHC's local time)", v["url"], row.data_source.target, v["issued"], v["fetched"]))
    out.events.append({"id": f"wx_{row.id}_labels", "type": "storm_points", "t_in": window.t_in, "t_out": window.t_out, "points": pts,
                       "name": "TROPICAL-STORM WINDS ARRIVE"})
    out.events.append({"id": f"wx_{row.id}_legend", "type": "alert_legend", "t_in": window.t_in, "t_out": window.t_out,
                       "items": [{"label": f"TROPICAL-STORM WINDS: {v['kind'].upper()} ARRIVAL", "color": "#FFD43B"},
                                 {"label": "NHC FORECAST", "color": "#FFFFFF"}]})
    out.credit(CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Forecast: NOAA National Hurricane Center, {v['kind']} arrival of tropical-storm-force winds"}]


# ---- wind probability ----------------------------------------------------------------------------------------------------------

def wsp_url(target: str, sel: str) -> str:
    kt = sel or "34"
    if kt not in ("34", "50", "64"):
        raise ValueError("wind_prob takes #34, #50 or #64 (knots)")
    if target == "latest":
        return f"{ARCH}latest_wsp{kt}knt120hr_5km.kmz"
    if not re.fullmatch(r"\d{10}", target):
        raise ValueError("wind_prob target is latest or the issuance as YYYYMMDDHH (2026101406)")
    return f"{ARCH}{target}_wsp{kt}knt120hr_5km.kmz"


def _fetch_polys(row, ctx, url: str, what: str) -> None:
    key = f"kmlpoly:{url}"
    if key in ctx.snap.extra:
        return
    try:
        _u, blob = first_answer([url], ctx.get_bytes, what)
    except ValueError as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    bands = []
    for p in kml.read(blob):
        if p.alpha <= 0.01 or not p.polygons:
            continue
        bands.append({"label": p.name or p.style, "style": p.style, "color": p.color, "alpha": round(p.alpha, 2),
                      "polys": [[[list(c) for c in kml.thin(r)] for r in poly] for poly in p.polygons]})
    ctx.snap.extra[key] = {"url": url, "fetched": iso(ctx.now), "issued": iso(ctx.now), "bands": bands}


def _fills(row, v, window, out, bbox=None) -> List[Dict[str, Any]]:
    shown = []
    for i, b in enumerate(v["bands"]):
        polys = [p for p in b["polys"] if not bbox or kml.clip_bbox(p, bbox)]
        if not polys:
            continue
        out.fills.append({"id": f"wx_{row.id}_b{i}", "type": "fill", "polys": polys, "color": b["color"], "outline_color": b["color"],
                          "opacity": float(row.extra.get("opacity", 0.6)), "t_in": round(window.t_in + 0.15 * i, 3), "t_out": window.t_out,
                          "fade_in": 0.5})
        shown.append(b)
    return shown


def _build_wsp(row, snap, window, out) -> None:
    url = wsp_url(row.data_source.target, row.data_source.selector)
    v = snap.extra[f"kmlpoly:{url}"]
    shown = _fills(row, v, window, out)
    if not shown:
        raise ValueError(f"{at(row)}: the wind-speed probability map has no area above 5%")
    kt = row.data_source.selector or "34"
    words = {"34": "TROPICAL-STORM-FORCE", "50": "50-KNOT", "64": "HURRICANE-FORCE"}[kt]
    out.events.append({"id": f"wx_{row.id}_legend", "type": "alert_legend", "t_in": window.t_in, "t_out": window.t_out,
                       "items": [{"label": f"CHANCE OF {words} WINDS", "color": "#FFFFFF"}]
                       + [{"label": b["label"].replace("&lt;", "<").replace("&gt;", ">").upper(), "color": b["color"]} for b in shown[-5:]]})
    out.report.add(row.id, f"probability of {words.lower()} winds, 5 days (NHC forecast)", ", ".join(b["label"] for b in shown),
                   Sourced(len(shown), "bands", "NHC wind speed probabilities (forecast)", url, row.data_source.target, v["issued"], v["fetched"]))
    out.credit(CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": "Forecast: NOAA National Hurricane Center wind speed probabilities, next 5 days"}]


# ---- rain forecast -------------------------------------------------------------------------------------------------------------

def _check_qpf(row) -> None:
    if row.data_source.target != "latest" or row.data_source.selector not in WPC_QPF:
        raise ValueError("rain_forecast takes wpc:qpf@latest#day1-5 or #day1-7")
    bb = row.extra.get("bbox")
    if bb is not None and not (isinstance(bb, list) and len(bb) == 4 and bb[2] - bb[0] <= 20 and bb[3] - bb[1] <= 16):
        raise ValueError("rain_forecast extra bbox is [west, south, east, north], at most 20 x 16 degrees")


def qpf_inches(style: str) -> str:
    m = re.search(r"(\d+)_(\d+)$", style or "")
    return f"{int(m.group(1))}.{m.group(2)}".rstrip("0").rstrip(".") if m else ""


def _build_qpf(row, snap, window, out) -> None:
    url = WPC_QPF[row.data_source.selector]
    v = snap.extra[f"kmlpoly:{url}"]
    shown = _fills(row, v, window, out, row.extra.get("bbox"))
    if not shown:
        raise ValueError(f"{at(row)}: WPC forecasts no rain in that area")
    days = row.data_source.selector.split("-")[1]
    items = [{"label": f"EXPECTED RAIN, NEXT {days} DAYS (IN)", "color": "#FFFFFF"}]
    for b in shown[-6:]:
        inch = qpf_inches(b["style"])
        items.append({"label": f"{inch}+ IN" if inch else b["label"].upper(), "color": b["color"]})
    out.events.append({"id": f"wx_{row.id}_legend", "type": "alert_legend", "t_in": window.t_in, "t_out": window.t_out, "items": items})
    top = qpf_inches(shown[-1]["style"])
    out.report.add(row.id, f"highest WPC rain-forecast band in view, {days} days (forecast)", f"{top}+ IN" if top else shown[-1]["label"],
                   Sourced(top, "in", "WPC quantitative precipitation forecast", url, "view", v["issued"], v["fetched"]))
    out.credit(CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Forecast: NOAA Weather Prediction Center, expected rain next {days} days"}]


# ---- countdown -----------------------------------------------------------------------------------------------------------------

def _km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def closest_approach(points: List[Dict[str, Any]], place) -> Dict[str, Any]:
    """The forecast centre's nearest pass to (lon, lat), interpolated between forecast points every 30 minutes."""
    from ..tz import parse_iso

    best = None
    for p, q in zip(points, points[1:]):
        t0, t1 = parse_iso(p["time"]), parse_iso(q["time"])
        steps = max(1, int((t1 - t0).total_seconds() // 1800))
        for k in range(steps + 1):
            f = k / steps
            pos = (p["lon"] + f * (q["lon"] - p["lon"]), p["lat"] + f * (q["lat"] - p["lat"]))
            d = _km(pos, place)
            if best is None or d < best["km"]:
                best = {"km": round(d), "time": t0 + f * (t1 - t0), "lon": pos[0], "lat": pos[1]}
    return best


def _check_countdown(row) -> None:
    nhc.check_storm(row.data_source.target)
    _adv(row.data_source.selector)
    from .broadcast import place_point

    place_point(row)


def _fetch_countdown(row, ctx) -> None:
    from .storms import fetch as fetch_storm

    class R:   # the advisory's forecast points, fetched as a storm_track row would (shared snapshot entry)
        pass

    r = R()
    r.data_source, r.line, r.id = type(row.data_source)("nhc", "track", row.data_source.target, _adv(row.data_source.selector)), row.line, row.id
    fetch_storm(r, ctx)


def _build_countdown(row, snap, window, out) -> None:
    from ..tz import clock, parse_iso
    from .broadcast import place_point

    v = snap.extra[f"nhc:{row.data_source.target.upper()}#{_adv(row.data_source.selector)}"]
    lon, lat, name = place_point(row)
    ca = closest_approach(v["points"], (lon, lat))
    issued = parse_iso(v["issued"])
    hours = int(round((ca["time"] - issued).total_seconds() / 3600))
    if hours <= 0:
        raise ValueError(f"{at(row)}: the forecast centre is nearest {name} at the advisory time already")
    tz = row.extra.get("tz", "America/New_York")
    when = clock(ca["time"], tz, date=True).upper()
    out.events.append({"id": f"wx_{row.id}", "type": "counter", "t_in": window.t_in, "t_out": window.t_out, "value": hours,
                       "label": f"HOURS UNTIL CLOSEST TO {name.upper()}", "sub": f"NHC FORECAST · ADV {v['adv']} · {when} · {ca['km']} KM",
                       "anchor": row.extra.get("anchor", "tr"), "count_s": 1.5})
    out.report.add(row.id, f"hours from advisory {v['adv']} until the forecast centre is nearest {name} (derived)", str(hours),
                   Sourced(hours, "h", "derived from the NHC forecast track (30-min interpolation between forecast points)", v["url"],
                           f"{lat},{lon}", v["issued"], v["fetched"]))
    out.credit(CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Forecast: NOAA National Hurricane Center, advisory {v['adv']}"}]


def fresh(snap, now: datetime) -> List[str]:
    from ..tz import parse_iso

    out = []
    for k, v in snap.extra.items():
        if (k.startswith("nhc_toa:") or k.startswith("kmlpoly:")) and isinstance(v, dict) and v.get("fetched"):
            if now - parse_iso(v["fetched"]) > STALE:
                out.append(f"a forecast map ({v.get('url', k)}) was fetched more than 12 h ago")
    return out


register_fresh(fresh)
register(LayerType(name="wind_arrival", products=[("nhc", "arrival")], extra_keys=frozenset({"tz"}), fetch=_fetch_arrival,
                   build=_build_arrival, check=_check_arrival, about="when tropical-storm-force winds are forecast to arrive (NHC)"))
register(LayerType(name="wind_prob", products=[("nhc", "wsp")], extra_keys=frozenset({"opacity"}),
                   fetch=lambda r, c: _fetch_polys(r, c, wsp_url(r.data_source.target, r.data_source.selector), "the NHC wind probabilities"),
                   build=_build_wsp, check=lambda r: wsp_url(r.data_source.target, r.data_source.selector),
                   about="the chance of tropical-storm or hurricane-force winds over 5 days (NHC forecast)"))
register(LayerType(name="rain_forecast", products=[("wpc", "qpf")], extra_keys=frozenset({"bbox", "opacity"}),
                   fetch=lambda r, c: _fetch_polys(r, c, WPC_QPF[r.data_source.selector], "the WPC rain forecast"),
                   build=_build_qpf, check=_check_qpf, about="WPC's expected rain over the next 5 or 7 days"))
register(LayerType(name="countdown", products=[("nhc", "countdown")], extra_keys=frozenset({"text", "anchor", "tz"}), fetch=_fetch_countdown,
                   build=_build_countdown, check=_check_countdown, needs_place=True,
                   about="hours until the forecast centre passes nearest a place (derived from the NHC forecast track)"))
