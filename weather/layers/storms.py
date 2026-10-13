"""Hurricanes from the National Hurricane Center's GIS archive.

    storm_cone   nhc:cone@AL092022#024     the advisory's cone of uncertainty (white, translucent, outlined) and, with extra
                                           {"coast": true} (default), its coastal hurricane / tropical storm watches and warnings
    storm_track  nhc:track@AL092022#024    the advisory's forecast track (dashed) and forecast points ("CAT 4 · 155 MPH · WED 2 PM")
                 nhc:track@AL092022#best   the best track (the storm's analysed path), coloured by strength, drawn in time order
    extra: opacity (cone), coast, legend, labels (how many forecast points are labelled, default 4), label_times (best track:
           UTC times to label, e.g. ["2022-09-28T18:00Z"]; default the strongest point), draw_s (seconds to draw the track), tz

The cone and the lines are ordinary pakMap fill and line events; the dots and their labels are weather-engine's storm_points
plugin. Wind is shown in mph rounded to 5 from NHC's knots, as NHC's public advisories write it; each label is in the numbers
report with the advisory (or best-track) file it came from."""

from __future__ import annotations

from typing import Any, Dict, List

from ..news import nhc
from ..news.rows import at, first_answer
from ..news.timeline import iso, parse_stamp, tz_of
from ..provenance import Sourced
from ..tz import clock, parse_iso, to_local
from . import LayerType, register

CREDIT = "Hurricane data: NOAA National Hurricane Center (NHC). Not an official NHC product; follow your local officials and NHC advisories."


def _key(row) -> str:
    ds = row.data_source
    return f"nhc:{ds.target.upper()}#{ds.selector}"


def _check(row, allow_best: bool) -> None:
    ds = row.data_source
    nhc.check_storm(ds.target)
    sel = ds.selector
    if allow_best and sel == "best":
        return
    if not sel or not nhc.ADV.match(sel):
        raise ValueError(f"{row.type} takes the advisory number as #024 (three digits{', or #best for the best track' if allow_best else ''})")


def fetch(row, ctx) -> None:
    key = _key(row)
    if key in ctx.snap.extra:
        return
    sid, sel = row.data_source.target.upper(), row.data_source.selector
    try:
        if sel == "best":
            url, blob = first_answer([nhc.BEST.format(id=sid.lower())], ctx.get_bytes, f"the NHC best track of {sid}")
            data = nhc.best_track(blob)
            issued = data["points"][-1]["time"] if data["points"] else ""
        else:
            url, blob = first_answer([nhc.ARCHIVE.format(id=sid.lower(), adv=sel)], ctx.get_bytes, f"NHC advisory {sel} of {sid}")
            data = nhc.advisory(blob)
            issued = data["issued"]
    except ValueError as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    ctx.snap.extra[key] = {"storm": sid, "selector": sel, "url": url, "issued": issued, "fetched": iso(ctx.now), **data}


def _adv_text(v, tz: str) -> str:
    return f"NHC Advisory {int(v['adv']) if v['adv'].isdigit() else v['adv']}, {clock(parse_iso(v['issued']), tz, date=True)}"


def build_cone(row, snap, window, out) -> None:
    v = snap.extra[_key(row)]
    tz = tz_of(row)
    out.fills.append({"id": f"wx_{row.id}_cone", "type": "fill", "polys": v["cone"], "color": "#FFFFFF", "opacity": float(row.extra.get("opacity", 0.35)),
                      "outline_color": "#FFFFFF", "t_in": window.t_in, "t_out": window.t_out, "fade_in": 0.6})
    legend = [{"label": "CONE OF UNCERTAINTY", "color": "#FFFFFF"}]
    if row.extra.get("coast", True):
        seen = {}
        for i, c in enumerate(v["coast"]):   # pakMap line events travel with the fills (merged into spec.events)
            out.fills.append({"id": f"wx_{row.id}_coast{i}", "type": "line", "kind": "border_trace", "coords": c["coords"], "color": c["color"],
                              "width": 7, "t_in": window.t_in, "t_out": window.t_out, "t_draw": window.t_in + 0.4, "draw_s": 1.2})
            seen.setdefault(c["label"], c["color"])
        legend += [{"label": k, "color": c} for k, c in seen.items()]
    if row.extra.get("legend", True):
        out.events.append({"id": f"wx_{row.id}_legend", "type": "alert_legend", "t_in": window.t_in, "t_out": window.t_out, "items": legend})
    text = _adv_text(v, tz)
    out.report.add(row.id, f"{v['name']} cone", text, Sourced(text, "", "NHC 5-day cone", v["url"], v["storm"], v["issued"], v["fetched"]))
    out.credit(CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Data: NOAA National Hurricane Center · {text}"}]


def _fmt_time(t, tz: str) -> str:
    local, _ = to_local(t, tz)
    h = local.hour % 12 or 12
    return f"{local.strftime('%a').upper()} {h}{'' if local.minute == 0 else f':{local.minute:02d}'} {'AM' if local.hour < 12 else 'PM'}"


def point_label(p: Dict[str, Any], tz: str, *, date: bool = False) -> str:
    """'CAT 4 · 155 MPH · WED 2 PM' (or with the date for a best track: 'CAT 4 · 155 MPH · SEP 28 2 PM')."""
    parts = [nhc.strength_label(p["cat"], p.get("kind", ""))]
    if p.get("wind_mph"):
        parts.append(f"{p['wind_mph']} MPH")
    t = parse_iso(p["time"])
    if date:
        local, _ = to_local(t, tz)
        parts.append(f"{local.strftime('%b').upper()} {local.day} {_fmt_time(t, tz).split(' ', 1)[1]}")
    else:
        parts.append(_fmt_time(t, tz))
    return " · ".join(parts)


def build_track(row, snap, window, out) -> None:
    v = snap.extra[_key(row)]
    tz = tz_of(row)
    dur = window.t_out - window.t_in
    draw_s = float(row.extra.get("draw_s", min(6.0, 0.6 * dur) if v["selector"] == "best" else min(2.5, 0.5 * dur)))
    t0 = window.t_in + 0.3
    pts: List[Dict[str, Any]] = []
    if v["selector"] == "best":
        times = [parse_iso(p["time"]) for p in v["points"]]
        a, b = times[0], times[-1]
        frac = [(t - a).total_seconds() / max(1.0, (b - a).total_seconds()) for t in times]

        def nearest(lon, lat):
            return min(range(len(v["points"])), key=lambda k: (v["points"][k]["lon"] - lon) ** 2 + (v["points"][k]["lat"] - lat) ** 2)

        for i, s in enumerate(v["segments"]):
            f0, f1 = frac[nearest(*s["coords"][0])], frac[nearest(*s["coords"][-1])]
            out.fills.append({"id": f"wx_{row.id}_seg{i}", "type": "line", "kind": "border_trace", "coords": s["coords"],
                              "color": nhc.CAT_COLORS.get(s["cat"], "#FFFFFF"), "width": 6, "t_in": window.t_in, "t_out": window.t_out,
                              "t_draw": round(t0 + f0 * draw_s, 3), "draw_s": round(max(0.05, (f1 - f0) * draw_s), 3)})
        wanted = {iso(parse_stamp(x)) for x in row.extra.get("label_times", [])}
        if not wanted:
            strongest = max(v["points"], key=lambda p: p["wind_kt"] or 0)
            wanted = {strongest["time"]}
        for p, f in zip(v["points"], frac):
            lab = point_label(p, tz, date=True) if p["time"] in wanted and p["cat"] >= -1 else ""
            pts.append({"lon": p["lon"], "lat": p["lat"], "color": nhc.CAT_COLORS.get(p["cat"], "#BBBBBB"), "label": lab, "at": round(t0 + f * draw_s, 3),
                        "size": 7 if p["cat"] < 1 else 9})
            if lab:
                out.report.add(row.id, f"{v['storm']} best track {p['time']}", lab,
                               Sourced(f"{p['wind_kt']:g} kt", "kt", "NHC best track", v["url"], f"{p['lat']}N {abs(p['lon'])}W", v["issued"], v["fetched"]))
        product = "NHC best track"
        text = f"Data: NOAA National Hurricane Center best track ({v['storm']})"
    else:
        out.fills.append({"id": f"wx_{row.id}_track", "type": "line", "kind": "connector", "coords": v["track"], "color": "#FFFFFF", "width": 4,
                          "t_in": window.t_in, "t_out": window.t_out, "t_draw": t0, "draw_s": draw_s})
        n_lab = int(row.extra.get("labels", 4))
        for i, p in enumerate(v["points"]):
            lab = point_label(p, tz) if i < n_lab else ""
            pts.append({"lon": p["lon"], "lat": p["lat"], "color": nhc.CAT_COLORS.get(p["cat"], "#BBBBBB"), "label": lab,
                        "at": round(t0 + draw_s * i / max(1, len(v["points"]) - 1), 3), "size": 9, "ring": i == 0})
            if lab:
                out.report.add(row.id, f"{v['storm']} advisory {v['adv']} point {p['time']}", lab,
                               Sourced(f"{p['wind_kt']:g} kt" if p["wind_kt"] is not None else "", "kt", "NHC forecast point", v["url"],
                                       f"{p['lat']}N {abs(p['lon'])}W", v["issued"], v["fetched"]))
        product = "NHC forecast track"
        text = f"Data: NOAA National Hurricane Center · {_adv_text(v, tz)}"
    out.events.append({"id": f"wx_{row.id}_points", "type": "storm_points", "t_in": window.t_in, "t_out": window.t_out, "points": pts,
                       "name": (v.get("name") or v["storm"]).upper()})
    out.credit(CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": text}]
    if not any(ln["layer"] == row.id for ln in out.report.lines):
        out.report.add(row.id, product, v["storm"], Sourced(v["storm"], "", product, v["url"], v["storm"], v["issued"], v["fetched"]))


register(LayerType(name="storm_cone", products=[("nhc", "cone")], extra_keys=frozenset({"opacity", "coast", "legend", "tz"}),
                   fetch=fetch, build=build_cone, check=lambda r: _check(r, False),
                   about="NHC cone of uncertainty (and coastal watches/warnings) of one advisory"))
register(LayerType(name="storm_track", products=[("nhc", "track")], extra_keys=frozenset({"labels", "label_times", "draw_s", "tz"}),
                   fetch=fetch, build=build_track, check=lambda r: _check(r, True),
                   about="NHC forecast track with labelled points, or the best track coloured by strength"))


# ---- the credit chip of event footage (weather/news/approval.py writes these rows) -------------------------------------

def check_credit(row) -> None:
    if not str(row.extra.get("text", "")).strip():
        raise ValueError('footage_credit needs extra {"text": "VIDEO: NASA · SEP 28, 2022"} (approval.py writes it from the approved clip)')


def build_credit(row, snap, window, out) -> None:
    out.events.append({"id": f"wx_{row.id}", "type": "footage_credit", "t_in": window.t_in, "t_out": window.t_out, "text": str(row.extra["text"]).upper()})
    out.credit(str(row.extra["text"]))


register(LayerType(name="footage_credit", products=(), extra_keys=frozenset({"text"}), build=build_credit, check=check_credit,
                   about="the credit chip of an approved event clip (on the footage beat it belongs to)"))
