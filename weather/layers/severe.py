"""Severe weather and heavy rain: SPC outlooks and storm reports, WPC excessive rainfall outlooks, and archived NWS warnings.

    spc_outlook       spc:outlook@2024-05-06#day1        SPC categorical outlook (archive; #day1_1630 picks an issuance)
                      spc:outlook@latest#day1            the current one (a "now" product: stale once it expires)
    storm_reports     spc:reports@2024-05-06             tornado / wind / hail reports of the convective day, revealed in time
                      spc:reports@2024-05-06#tornado     order, labelled PRELIMINARY (#tornado,hail keeps those kinds)
    wpc_ero           wpc:ero@latest#day1                WPC excessive rainfall outlook (current)
                      wpc:ero@2022-09-28#day1            archive (#day1_16 picks the 16 UTC issuance)
    warnings_archive  iem:warnings@2022-09-28T14:00Z..2022-09-28T22:00Z#TO,SV,FF,EW
                                                         storm-based warnings of a past window, each shown from its issue time
                                                         (the window replays over the layer like a radar loop with the same window)
    extra: opacity, legend (true), states (warnings_archive: ["FL"]), tz

Colours: SPC's own (in each outlook file), WPC's (its KML), NWS warning colours from weather/alerts.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from ..news import iem_warnings, spc, wpc
from ..news.rows import at, first_answer
from ..news.timeline import iso, parse_day, parse_window, span, to_layer, tz_of
from ..provenance import Sourced
from ..tz import clock, parse_iso
from . import LayerType, register

SPC_CREDIT = "Severe weather outlooks and storm reports: NOAA/NWS Storm Prediction Center. Storm reports are preliminary."
WPC_CREDIT = "Excessive rainfall outlook: NOAA/NWS Weather Prediction Center."
IEM_CREDIT = "Warnings: National Weather Service, archived by the Iowa Environmental Mesonet (Iowa State University)."
REPORT_LABELS = {"tornado": "TORNADO", "wind": "WIND DAMAGE", "hail": "HAIL"}
DEFAULT_WARNINGS = ["TO", "SV", "FF"]


def _day_or_latest(target: str, allow_latest: bool = True) -> None:
    if target == "latest" and allow_latest:
        return
    parse_day(target)


# ---- SPC outlook -----------------------------------------------------------------------------------------------------

def check_outlook(row) -> None:
    _day_or_latest(row.data_source.target)
    spc.outlook_selector(row.data_source.selector or "day1")


def fetch_outlook(row, ctx) -> None:
    ds = row.data_source
    key = f"spc_outlook:{ds.target}#{ds.selector or 'day1'}"
    if key in ctx.snap.extra:
        return
    try:
        url, text = first_answer(spc.outlook_urls(ds.target, ds.selector or "day1"), ctx.get_text, f"the SPC outlook for {ds.target}")
        data = spc.outlook(text)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    if not data["areas"]:
        raise ValueError(f"{at(row)}: the SPC outlook at {url} has no risk areas (no thunderstorms forecast)")
    ctx.snap.extra[key] = {"url": url, "latest": ds.target == "latest", "fetched": iso(ctx.now), **data}


def _areas_out(row, window, out, areas, product: str, url: str, issued: str, fetched: str, tz: str) -> None:
    for i, a in enumerate(areas):
        out.fills.append({"id": f"wx_{row.id}_{i}", "type": "fill", "polys": a["polys"], "color": a["fill"], "outline_color": a["stroke"],
                          "opacity": float(row.extra.get("opacity", 0.55)), "t_in": window.t_in + 0.15 * i, "t_out": window.t_out})
        out.report.add(row.id, f"{product} area", a["name"], Sourced(a["name"], "", product, url, "US", issued, fetched))
    if row.extra.get("legend", True):
        items, seen = [], set()
        for a in reversed(areas):   # highest risk first
            if a["name"] not in seen:
                seen.add(a["name"])
                items.append({"label": a["name"].upper(), "color": a["fill"]})
        out.events.append({"id": f"wx_{row.id}_legend", "type": "alert_legend", "t_in": window.t_in, "t_out": window.t_out, "items": items})


def build_outlook(row, snap, window, out) -> None:
    ds = row.data_source
    v = snap.extra[f"spc_outlook:{ds.target}#{ds.selector or 'day1'}"]
    tz = tz_of(row, "America/Chicago")
    _areas_out(row, window, out, v["areas"], "SPC convective outlook", v["url"], v["issued"], v["fetched"], tz)
    out.credit(SPC_CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Outlook: NOAA Storm Prediction Center, issued {clock(parse_iso(v['issued']), tz, date=True)}"}]


def fresh_outlooks(snap, now: datetime) -> List[str]:
    out = []
    for key, v in snap.extra.items():
        if (key.startswith("spc_outlook:") or key.startswith("wpc_ero:")) and v.get("latest") and v.get("expires"):
            if parse_iso(v["expires"]) <= now:
                out.append(f"the {'SPC' if key.startswith('spc') else 'WPC'} outlook fetched {v['fetched']} expired at {v['expires']}")
    return out


register(LayerType(name="spc_outlook", products=[("spc", "outlook")], extra_keys=frozenset({"opacity", "legend", "tz"}),
                   fetch=fetch_outlook, build=build_outlook, check=check_outlook, fresh=fresh_outlooks,
                   about="SPC categorical severe-thunderstorm outlook (archive or current)"))


# ---- WPC excessive rainfall outlook ----------------------------------------------------------------------------------

def check_ero(row) -> None:
    _day_or_latest(row.data_source.target)
    wpc.selector(row.data_source.selector or "day1")


def fetch_ero(row, ctx) -> None:
    ds = row.data_source
    key = f"wpc_ero:{ds.target}#{ds.selector or 'day1'}"
    if key in ctx.snap.extra:
        return
    try:
        urls = wpc.urls(ds.target, ds.selector or "day1")
        if ds.target == "latest":
            url, text = first_answer(urls, ctx.get_text, "the current WPC excessive rainfall outlook")
            data = wpc.from_geojson(text)
        else:
            url, blob = first_answer(urls, ctx.get_bytes, f"the WPC excessive rainfall outlook for {ds.target}")
            data = wpc.from_zip(blob)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    if not data["areas"]:
        raise ValueError(f"{at(row)}: the WPC outlook at {url} has no risk areas")
    ctx.snap.extra[key] = {"url": url, "latest": ds.target == "latest", "fetched": iso(ctx.now), **data}


def build_ero(row, snap, window, out) -> None:
    ds = row.data_source
    v = snap.extra[f"wpc_ero:{ds.target}#{ds.selector or 'day1'}"]
    tz = tz_of(row)
    areas = [{"name": a["label"], "fill": a["color"], "stroke": a["color"], "polys": a["polys"]} for a in v["areas"]]
    _areas_out(row, window, out, areas, "WPC excessive rainfall outlook", v["url"], v["issued"], v["fetched"], tz)
    out.credit(WPC_CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Rain outlook: NOAA Weather Prediction Center, issued {clock(parse_iso(v['issued']), tz, date=True)}"}]


register(LayerType(name="wpc_ero", products=[("wpc", "ero")], extra_keys=frozenset({"opacity", "legend", "tz"}),
                   fetch=fetch_ero, build=build_ero, check=check_ero,
                   about="WPC excessive rainfall outlook (archive or current)"))


# ---- SPC storm reports -----------------------------------------------------------------------------------------------

def report_kinds(sel: str) -> List[str]:
    kinds = [k.strip() for k in (sel or "").split(",") if k.strip()] or list(spc.REPORT_KINDS)
    bad = [k for k in kinds if k not in spc.REPORT_KINDS]
    if bad:
        raise ValueError(f"storm report kinds are tornado, wind and hail (got {', '.join(bad)})")
    return kinds


def check_reports(row) -> None:
    parse_day(row.data_source.target)
    report_kinds(row.data_source.selector)


def reports_key(day: str) -> str:
    return f"spc_reports:{day}"


def fetch_reports(row, ctx) -> None:
    day = row.data_source.target
    key = reports_key(day)
    if key in ctx.snap.extra:
        return
    d = parse_day(day)
    try:
        url, text = first_answer([spc.REPORTS.format(yymmdd=d.strftime("%y%m%d"))], ctx.get_text, f"the SPC storm reports of {day}")
    except ValueError as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    reps = spc.reports(text, day)
    a, b = spc.report_day(day)
    ctx.snap.extra[key] = {"url": url, "day": day, "start": iso(a), "end": iso(b), "fetched": iso(ctx.now), "reports": reps}


def build_reports(row, snap, window, out) -> None:
    v = snap.extra[reports_key(row.data_source.target)]
    kinds = report_kinds(row.data_source.selector)
    reps = [r for r in v["reports"] if r["kind"] in kinds]
    pts = []
    if reps:
        a, b = parse_iso(reps[0]["time"]), parse_iso(reps[-1]["time"])
        for r in reps:
            pts.append({"lon": r["lon"], "lat": r["lat"], "kind": r["kind"], "at": to_layer(parse_iso(r["time"]), a, b, window.t_in + 0.4, window.t_out)})
    totals = {k: spc.count(reps, k) for k in kinds}
    legend = [{"kind": k, "label": REPORT_LABELS[k], "color": spc.REPORT_COLORS[k], "total": totals[k]} for k in kinds]
    out.events.append({"id": f"wx_{row.id}", "type": "storm_reports", "t_in": window.t_in, "t_out": window.t_out, "points": pts,
                       "legend": legend if row.extra.get("legend", True) else [], "title": "STORM REPORTS", "sub": "PRELIMINARY"})
    for k in kinds:
        out.report.add(row.id, f"{k} reports {v['day']} (preliminary)", str(totals[k]),
                       Sourced(totals[k], "reports", "SPC storm reports (preliminary)", v["url"], "US", v["end"], v["fetched"]))
    out.credit(SPC_CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Storm reports: NOAA Storm Prediction Center, preliminary, {v['day']}"}]


register(LayerType(name="storm_reports", products=[("spc", "reports")], extra_keys=frozenset({"legend", "tz"}),
                   fetch=fetch_reports, build=build_reports, check=check_reports,
                   about="SPC tornado / wind / hail reports of a day, revealed in time order (preliminary)"))


# ---- archived warnings -----------------------------------------------------------------------------------------------

def warning_types(sel: str) -> List[str]:
    kinds = [k.strip().upper() for k in (sel or "").split(",") if k.strip()] or list(DEFAULT_WARNINGS)
    bad = [k for k in kinds if k not in iem_warnings.NAMES]
    if bad:
        raise ValueError(f"warning types are {', '.join(iem_warnings.NAMES)} (got {', '.join(bad)})")
    return kinds


def check_warnings(row) -> None:
    parse_window(row.data_source.target, max_hours=72)
    warning_types(row.data_source.selector)
    st = row.extra.get("states", [])
    if not isinstance(st, list) or not all(isinstance(s, str) and len(s) == 2 for s in st):
        raise ValueError('warnings_archive extra states is a list of two-letter states, like ["FL"]')


def warnings_key(target: str, states) -> str:
    return f"iem_warnings:{target}|{','.join(sorted(s.upper() for s in states or []))}"


def fetch_warnings(row, ctx) -> None:
    states = row.extra.get("states", [])
    key = warnings_key(row.data_source.target, states)
    if key in ctx.snap.extra:
        return
    start, end = parse_window(row.data_source.target, max_hours=72)
    url = iem_warnings.url(start, end, states)
    try:
        _u, text = first_answer([url], ctx.get_text, f"the IEM warnings archive for {row.data_source.target}")
    except ValueError as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    ctx.snap.extra[key] = {"url": url, "start": iso(start), "end": iso(end), "fetched": iso(ctx.now),
                           "warnings": iem_warnings.warnings(text, list(iem_warnings.NAMES))}


def selected_warnings(snap, row) -> "tuple[Dict[str, Any], List[Dict[str, Any]]]":
    v = snap.extra[warnings_key(row.data_source.target, row.extra.get("states", []))]
    kinds = warning_types(row.data_source.selector)
    return v, [w for w in v["warnings"] if w["phenomena"] in kinds]


def build_warnings(row, snap, window, out) -> None:
    v, ws = selected_warnings(snap, row)
    a, b = parse_iso(v["start"]), parse_iso(v["end"])
    tz = tz_of(row)
    legend: Dict[str, str] = {}
    for i, w in enumerate(ws):
        if parse_iso(w["ends"]) <= a or parse_iso(w["starts"]) >= b:   # the archive also returns warnings that touch the window's edges
            continue
        t_in = to_layer(max(a, parse_iso(w["starts"])), a, b, window.t_in, window.t_out)
        t_out = to_layer(min(b, parse_iso(w["ends"])), a, b, window.t_in, window.t_out) if parse_iso(w["ends"]) < b else window.t_out
        t_out = min(window.t_out, max(t_out, t_in + 1.0))
        if t_out - t_in < 0.3:
            continue
        out.fills.append({"id": f"wx_{row.id}_{i}", "type": "fill", "polys": w["polys"], "color": w["color"], "outline_color": w["color"],
                          "opacity": float(row.extra.get("opacity", 0.45)), "t_in": round(t_in, 3), "t_out": round(t_out, 3), "fade_in": 0.25})
        # the outline again as a pakMap line: lines are drawn on the overlay, so the warning stays visible over a radar loop (which
        # sits above the map's fills)
        for k, poly in enumerate(w["polys"]):
            out.fills.append({"id": f"wx_{row.id}_{i}_edge{k}", "type": "line", "kind": "border_trace", "coords": poly[0], "color": w["color"],
                              "width": 4, "t_in": round(t_in, 3), "t_out": round(t_out, 3), "draw_s": 0.3})
        legend.setdefault(w["name"], w["color"])
        out.report.add(row.id, f"{w['name']} {w['wfo']} #{w['eventid']}", w["name"],
                       Sourced(w["name"], "", "NWS warning (IEM archive)", v["url"], w["wfo"] or "", w["issued"], v["fetched"]))
    if row.extra.get("legend", True) and legend:
        out.events.append({"id": f"wx_{row.id}_legend", "type": "alert_legend", "t_in": window.t_in, "t_out": window.t_out,
                           "items": [{"label": k.upper(), "color": c} for k, c in legend.items()]})
    out.credit(IEM_CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Warnings: National Weather Service via IEM, {span(a, b, tz)}"}]


register(LayerType(name="warnings_archive", products=[("iem", "warnings")], extra_keys=frozenset({"opacity", "legend", "states", "tz"}),
                   fetch=fetch_warnings, build=build_warnings, check=check_warnings,
                   about="NWS storm-based warnings of a past window (IEM archive), each from its issue time"))
