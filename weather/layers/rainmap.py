"""Observed rainfall over an area as a colour map (phase 4, post-event): NOAA MRMS radar estimates added up day by day.

    rain_map   mrms:total@2017-08-25..2017-09-01    extra {"bbox": [-98, 27.5, -93, 31.5]}

The total runs from 12 UTC (7 AM CDT) on the first date to 7 AM CDT on the last (one 24-hour grid per day, weather.post.mrms).
It is drawn as a pakMap value_overlay (a colour grid under the borders and graphics) with a legend in inches; cells under
extra.min_in (1 inch by default) are left clear so the map shows through.

extra: bbox [west, south, east, north] (degrees, at most 12 x 10), min_in, opacity (0.75), legend (true), peak (false: also name
the wettest cell's estimate on the legend), by_day (false: true shows the flood's progression — the running total day by day)."""

from __future__ import annotations

from datetime import datetime

from ..post import mrms
from ..post.fmt import date_range, named, short, span
from ..provenance import Sourced
from . import LayerType, register

MIN_SHARE = 0.55  # pakMap refuses a grid that covers less than half its box: keep a margin


def _bbox(row):
    b = row.extra.get("bbox")
    if not (isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b)):
        raise ValueError("rain_map needs extra bbox: [west, south, east, north] in degrees, e.g. [-98, 27.5, -93, 31.5]")
    w, s, e, n = (float(x) for x in b)
    if not (-130 <= w < e <= -60 and 20 <= s < n <= 55):
        raise ValueError(f"rain_map bbox {b} must lie inside the MRMS grid (130W-60W, 20N-55N), west < east, south < north")
    if e - w > 12 or n - s > 10:
        raise ValueError(f"rain_map bbox {b} is larger than 12 x 10 degrees: frame the area the event hit")
    return [w, s, e, n]


def _check(row) -> None:
    a, b = date_range(row.data_source.target)
    mrms.day_endings(a, b)
    if a.year < 2015:
        raise ValueError("the MRMS rainfall archive starts in 2015")
    _bbox(row)
    if float(row.extra.get("min_in", 1)) < 0:
        raise ValueError("extra min_in must be 0 or more inches")


def _fetch(row, ctx) -> None:
    from ..post.products import fetch_rain_grid

    a, b = date_range(row.data_source.target)
    fetch_rain_grid(ctx, a, b, _bbox(row))
    if row.extra.get("by_day"):   # the flood's progression: the total so far, one more day each step
        for d in _ends(a, b)[:-1]:
            fetch_rain_grid(ctx, a, d, _bbox(row))


def _ends(a, b):
    from datetime import timedelta

    return [a + timedelta(days=k) for k in range(1, (b - a).days + 1)]


def _hour(d, tz: str) -> str:
    """12 UTC on day d in the viewer's zone: '7 AM CDT' (6 AM CST in winter)."""
    from datetime import timezone

    from ..tz import to_local

    local, abbr = to_local(datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc), tz)
    return f"{local.hour % 12 or 12} {'AM' if local.hour < 12 else 'PM'} {abbr}"


def grid_folder():
    from ..cache import cache_root

    return cache_root() / "post_grids"


def _build(row, snap, window, out) -> None:
    a, b = date_range(row.data_source.target)
    if not row.extra.get("by_day"):
        _overlay(row, snap, a, b, window.t_in, window.t_out, out, f"wx_{row.id}", last=True)
        return
    ends = _ends(a, b)
    step = (window.t_out - window.t_in) / len(ends)
    for k, d in enumerate(ends):   # each step holds the running total until the next one fades in over it
        _overlay(row, snap, a, d, round(window.t_in + k * step, 3), window.t_out if k == len(ends) - 1 else round(window.t_in + (k + 1) * step + 0.4, 3),
                 out, f"wx_{row.id}_d{k}", last=k == len(ends) - 1)


def _overlay(row, snap, a, b, t_in, t_out, out, eid, *, last: bool) -> None:
    from ..post.products import grid_key

    bbox = _bbox(row)
    entry = snap.extra[grid_key(a, b, bbox)]
    grid = mrms.RainGrid.from_dict(entry["grid"])
    min_in = float(row.extra.get("min_in", 1))
    share = grid.share_at_least(min_in)
    if last and share < MIN_SHARE:
        raise ValueError(f"only {share * 100:.0f}% of the box got {min_in:g} inch or more: draw a smaller bbox around the rain, or lower min_in")
    path = mrms.write_asc(grid, min_in, grid_folder())
    ramp = [[v, c] for v, c in mrms.RAMP_IN]
    out.fills.append({"id": eid, "type": "value_overlay", "t_in": t_in, "t_out": t_out, "data": f"file:{path}",
                      "bbox": [grid.west, grid.south, grid.east, grid.north], "ramp": ramp, "min": ramp[0][0], "max": ramp[-1][0],
                      "opacity": float(row.extra.get("opacity", 0.75)), "fade_in": 1.2 if eid == f"wx_{row.id}" else 0.4})
    when = span(a, b, year=True)
    src = lambda v, what: Sourced(v, "in", f"NOAA MRMS 24-hour radar estimates, {what}", entry["urls"][0], f"{len(entry['urls'])} grids ending 12 UTC {a}..{b}",  # noqa: E731
                                   entry["end"], entry["fetched"])
    tz = row.extra.get("tz", "America/Chicago")
    if row.extra.get("legend", True):
        ev = {"id": f"{eid}_legend", "type": "post_rainlegend", "t_in": t_in, "t_out": t_out, "title": "RAINFALL" if last else "RAINFALL SO FAR",
              "sub": f"{short(a)} {_hour(a, tz)} – {short(b)} {_hour(b, tz)}", "unit": "IN", "stops": [{"value": v, "color": c, "text": f"{v:g}"} for v, c in mrms.RAMP_IN],
              "foot": "MRMS radar estimate", "peak": ""}
        if last:
            out.report.add(row.id, "rain map colour scale (inches; a scale, not a measurement)", " ".join(s["text"] for s in ev["stops"]), src(min_in, "colour scale"))
        if last and row.extra.get("peak"):
            v, lon, lat, at_least = grid.peak()
            ev["peak"] = f"PEAK ESTIMATE AT LEAST {int(v)} IN" if at_least else f"PEAK ESTIMATE {v:.0f} IN"   # a lower bound is never rounded up
            out.report.add(row.id, f"wettest cell of the rain map at {lat:.2f}N {abs(lon):.2f}W"
                           + (" (a day there reached the top of MRMS's encoding: the total is at least this)" if at_least else ""),
                           ev["peak"], src(round(v, 2), "summed, wettest cell"))
        out.events.append(ev)
    if last and grid.capped:
        snap.notes.append(f"rain map {row.id}: {grid.capped} cells reached MRMS's 495 mm daily cap; their totals are lower bounds")
    if last:
        out.credit(mrms.CREDIT)
        out.shown[row.id] = [{"kind": "text", "text": f"{mrms.SOURCE_TEXT}, {when}"}]


register(LayerType(name="rain_map", products=[("mrms", "total")], extra_keys=frozenset({"bbox", "min_in", "opacity", "legend", "peak", "tz", "by_day"}),
                   fetch=named(_fetch), build=named(_build), check=_check,
                   about="observed multi-day rainfall (NOAA MRMS radar estimates) as a colour map with a legend in inches"))
