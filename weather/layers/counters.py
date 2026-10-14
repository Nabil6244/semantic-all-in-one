"""A big number that counts up: how many reports or warnings an event brought.

    counter   spc:reports@2024-05-06#tornado                           "TORNADO REPORTS  46  PRELIMINARY"
              iem:warnings@2022-09-28T12:00Z..2022-09-29T00:00Z#EW      "EXTREME WIND WARNINGS ISSUED  5"
    extra: label (the words over the number), sub (the small line under it), anchor (tr | tl | br | bl, default tr),
           states (warnings: ["FL"]), count_s (seconds to count up, default 2)

The number is counted from the same data the storm_reports / warnings_archive layers draw (fetched once): reports of one kind on
the SPC convective day, or warnings ISSUED inside the window (one per warning, however often its polygon was updated)."""

from __future__ import annotations

from ..news import spc
from ..news.timeline import parse_day, parse_window
from ..provenance import Sourced
from . import LayerType, register
from .severe import (fetch_reports, fetch_warnings, iem_warnings, reports_key, selected_warnings, warning_types)
from ..tz import parse_iso

ANCHORS = ("tr", "tl", "br", "bl")
WARNING_WORDS = {"TO": "TORNADO WARNINGS", "SV": "SEVERE T-STORM WARNINGS", "FF": "FLASH FLOOD WARNINGS", "EW": "EXTREME WIND WARNINGS",
                 "MA": "SPECIAL MARINE WARNINGS", "SQ": "SNOW SQUALL WARNINGS", "DS": "DUST STORM WARNINGS", "FA": "FLOOD WARNINGS",
                 "FL": "FLOOD WARNINGS"}


def check(row) -> None:
    ds = row.data_source
    if ds.provider == "spc":
        parse_day(ds.target)
        if ds.selector not in spc.REPORT_KINDS:
            raise ValueError("a report counter counts one kind: #tornado, #wind or #hail")
    else:
        parse_window(ds.target, max_hours=72)
        if len(warning_types(ds.selector)) != 1 or not ds.selector:
            raise ValueError("a warning counter counts one type, e.g. #TO or #EW")
    if row.extra.get("anchor", "tr") not in ANCHORS:
        raise ValueError(f"counter anchor is one of {', '.join(ANCHORS)}")


def fetch(row, ctx) -> None:
    (fetch_reports if row.data_source.provider == "spc" else fetch_warnings)(row, ctx)


def count(row, snap):
    """(value, label, sub, Sourced)."""
    ds = row.data_source
    if ds.provider == "spc":
        v = snap.extra[reports_key(ds.target)]
        states = [s.upper() for s in row.extra.get("states", []) or []]
        reps = [r for r in v["reports"] if not states or str(r.get("state", "")).upper() in states]
        n = spc.count(reps, ds.selector)
        label = row.extra.get("label") or f"{ds.selector.upper()} REPORTS" + (f" · {', '.join(states)}" if states else "")
        sub = row.extra.get("sub") or "PRELIMINARY · SPC"
        if "PRELIMINARY" not in sub.upper():
            sub = f"{sub} · PRELIMINARY"   # SPC reports are always labelled preliminary
        return n, label, sub, Sourced(n, "reports", f"SPC storm reports, {ds.selector} (preliminary)", v["url"], ",".join(states) or "US",
                                      v["end"], v["fetched"])
    v, ws = selected_warnings(snap, row)
    a, b = parse_iso(v["start"]), parse_iso(v["end"])
    n = sum(1 for w in ws if a <= parse_iso(w["issued"]) <= b)
    label = row.extra.get("label") or f"{WARNING_WORDS.get(ds.selector.upper(), ds.selector.upper())} ISSUED"
    sub = row.extra.get("sub") or "NATIONAL WEATHER SERVICE"
    return n, label, sub, Sourced(n, "warnings", f"NWS {iem_warnings.NAMES[ds.selector.upper()]}s issued (IEM archive)", v["url"],
                                  ",".join(row.extra.get("states", [])) or "US", v["end"], v["fetched"])


def build(row, snap, window, out) -> None:
    n, label, sub, src = count(row, snap)
    out.events.append({"id": f"wx_{row.id}", "type": "counter", "t_in": window.t_in, "t_out": window.t_out, "value": n, "label": label.upper(),
                       "sub": sub.upper(), "anchor": row.extra.get("anchor", "tr"), "count_s": float(row.extra.get("count_s", 2.0))})
    out.report.add(row.id, label.lower(), str(n), src)
    text = "Storm reports: NOAA Storm Prediction Center, preliminary" if row.data_source.provider == "spc" else "Warnings: National Weather Service via IEM"
    out.shown[row.id] = [{"kind": "text", "text": text}]


register(LayerType(name="counter", products=[("spc", "reports"), ("iem", "warnings")],
                   extra_keys=frozenset({"label", "sub", "anchor", "states", "count_s", "tz"}), fetch=fetch, build=build, check=check,
                   about="a number counting up: storm reports of one kind, or warnings of one type issued in a window"))
