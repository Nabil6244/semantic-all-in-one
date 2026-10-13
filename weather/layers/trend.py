"""temp_trend: the week's highs and lows of one city as a line chart (weather-engine/lib/layers/temp_trend.mjs draws it).

    beat,vo_anchor,t,id,type,place,data_source,hold,until,extra
    b6,the week ahead,,trend,temp_trend,"Dallas, TX","nws:forecast@Dallas,TX#day1-7",,,

data_source is the NWS forecast of a city with a day range of 3 to 7 days (#day1-7). Each day gives a high point and, when the
forecast has the night after it, a low point; every number drawn is in the numbers report. The chart sits where the forecast strip
sits, so a beat shows one or the other (the engine refuses two at once).

Loading this module also adds the covered metros (weather/data/metros.json) to find_city (weather.automation.coverage.install):
the layer types load before any row is read, so a sidecar naming "Boston, MA" works through the phase-1 code unchanged."""

from __future__ import annotations

from ..automation.coverage import install as _install_metros
from ..cities import find_city
from ..provenance import Sourced
from . import LayerType, register

_install_metros()


def _check(row) -> None:
    ds = row.data_source
    city = find_city(ds.target)  # KeyError names the known cities
    if row.place and find_city(row.place).key != city.key:
        raise ValueError(f"place {row.place!r} is not the city of the data_source ({ds.target})")
    a, b = ds.days()
    if not 3 <= b - a + 1 <= 7:
        raise ValueError(f"a temp_trend shows 3 to 7 days (got #day{a}-{b})")


def _fetch(row, ctx) -> None:
    from ..resolve import fetch_forecast

    city = find_city(row.data_source.target)
    if city.key in ctx.snap.forecasts:
        return
    if ctx.nws is None:
        raise ValueError(f"weather_layers.csv row {row.line} ({row.id}): temp_trend needs National Weather Service data: set the NWS contact first")
    ctx.snap.forecasts[city.key] = fetch_forecast(ctx.nws, city, ctx.snap.notes)


def _build(row, snap, window, out) -> None:
    at = f"weather_layers.csv row {row.line} ({row.id})"
    city = find_city(row.data_source.target)
    f = snap.forecasts.get(city.key)
    if f is None:
        raise ValueError(f"{at}: there is no {city.key} forecast in resolved.json: fetch the data again")
    a, b = row.data_source.days()
    if b > len(f["days"]):
        raise ValueError(f"{at}: the {city.key} forecast has {len(f['days'])} days, not {b}")
    days = []
    for d in f["days"][a - 1:b]:
        hi = Sourced.from_dict(d["high"])
        lo = Sourced.from_dict(d["low"]) if d.get("low") else None
        days.append({"dow": d["dow"], "hi": f"{int(hi.value)}°", "hi_v": int(hi.value),
                     "lo": f"{int(lo.value)}°" if lo else "", "lo_v": int(lo.value) if lo else None})
        out.report.add(row.id, f"{city.key} {d['dow']} high", f"{int(hi.value)}°", hi)
        if lo:
            out.report.add(row.id, f"{city.key} {d['dow']} low", f"{int(lo.value)}°", lo)
    out.events.append({"id": f"wx_{row.id}", "type": "temp_trend", "t_in": window.t_in, "t_out": window.t_out,
                       "title": row.extra.get("title") or f"{city.name.upper()}, {city.state} · HIGHS AND LOWS", "days": days})
    out.shown[row.id] = [{"kind": "forecast", "issued": f["issued"], "tz": city.tz}]


register(LayerType(name="temp_trend", products=[("nws", "forecast")], extra_keys=frozenset({"title"}), fetch=_fetch, build=_build,
                   check=_check, about="the week's highs and lows of one city as a line chart"))
