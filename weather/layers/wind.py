"""wind_flow: the forecast wind at a city, as streaks drifting the way the wind blows (phase 5).

Data: nws:forecast@City,ST#dayN — the NWS forecast's own windSpeed ("10 to 15 mph") and windDirection ("SSW") for that day. The
direction is where the wind comes FROM (meteorological), so the streaks flow the opposite way. The speed only sets how fast the
streaks move and is printed as the forecast wrote it; nothing is interpolated between cities."""

from __future__ import annotations

import re

from ..cities import find_city
from ..provenance import Sourced
from . import LayerType, register

# compass point -> degrees the wind comes FROM
COMPASS = {d: i * 22.5 for i, d in enumerate("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())}


def mph_range(text: str) -> "tuple[int, int]":
    """'10 to 15 mph' -> (10, 15); '5 mph' -> (5, 5); 'Calm' -> (0, 0)."""
    nums = [int(n) for n in re.findall(r"\d+", str(text))]
    return (nums[0], nums[-1]) if nums else (0, 0)


def wind_text(direction: str, speed: str) -> str:
    lo, hi = mph_range(speed)
    if hi == 0:
        return "CALM"
    return f"{direction} {lo}–{hi} MPH" if hi != lo else f"{direction} {hi} MPH"


def _check(row) -> None:
    find_city(row.data_source.target)
    a, b = row.data_source.days()
    if a != b:
        raise ValueError("wind_flow shows one day (#day1, #day2 ...)")


def _fetch(row, ctx) -> None:
    from ..resolve import fetch_forecast

    city = find_city(row.data_source.target)
    if city.key not in ctx.snap.forecasts:
        if ctx.nws is None:
            raise ValueError("wind_flow needs the National Weather Service forecast: set the NWS contact first")
        ctx.snap.forecasts[city.key] = fetch_forecast(ctx.nws, city, ctx.snap.notes)


def _build(row, snap, window, out) -> None:
    city = find_city(row.data_source.target)
    n = row.data_source.days()[0]
    days = snap.forecasts[city.key]["days"]
    if n > len(days):
        raise ValueError(f"the {city.key} forecast has {len(days)} days, not {n}")
    d = days[n - 1]
    if not d.get("wind"):
        raise ValueError(f"the {city.key} forecast for day {n} has no wind (fetch the data again)")
    src = Sourced.from_dict(d["wind"])
    direction = d.get("wind_dir") or ""
    if direction not in COMPASS:
        raise ValueError(f"the {city.key} forecast wind direction {direction!r} is not a compass point")
    label = wind_text(direction, src.value)
    _lo, hi = mph_range(src.value)
    out.events.append({"id": f"wx_{row.id}", "type": "wind_flow", "t_in": window.t_in, "t_out": window.t_out, "lon": city.lon, "lat": city.lat,
                       "from_deg": COMPASS[direction], "mph": hi, "label": label, "city": city.name.upper(), "dow": d["dow"]})
    out.report.add(row.id, f"{city.key} {d['dow']} wind", label, src)
    out.shown[row.id] = [{"kind": "forecast", "issued": snap.forecasts[city.key]["issued"], "tz": city.tz}]


register(LayerType(name="wind_flow", products=[("nws", "forecast")], extra_keys=frozenset(), fetch=_fetch, build=_build, check=_check,
                   about="the forecast wind at a city as moving streaks"))
