"""Resolved weather data + layer windows -> what weather-engine draws, and the numbers report.

Every number is formatted HERE (the engine draws strings it is given), so the numbers report lists exactly what is on screen.
Alert areas become ordinary pakMap `fill` events (a type the engine and its checks already know); everything else goes to
spec["weather"], which only weather-engine reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .alerts import alert_color
from .cities import find_city
from .provenance import NumbersReport, Sourced
from .resolve import Snapshot
from .sidecar import WxRow
from .timing import Window
from .tz import clock, parse_iso

POP_SHOWN_FROM = 20  # a chance of rain under 20 % is not printed on the strip (the NWS does not mention it either)
DEFAULT_TZ = "America/New_York"


@dataclass
class WeatherPayload:
    fills: List[Dict[str, Any]] = field(default_factory=list)  # pakMap fill events (alert areas)
    events: List[Dict[str, Any]] = field(default_factory=list)  # weather-engine events
    satellite: List[Dict[str, Any]] = field(default_factory=list)  # timed satellite layers
    rasters: List[Dict[str, Any]] = field(default_factory=list)  # timed tile loops (radar, satellite loops): weather.layers.Raster.to_dict()
    credits: List[str] = field(default_factory=list)
    report: NumbersReport = field(default_factory=NumbersReport)
    shown: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)  # row id -> the sources it shows (named by source lines)

    def spec_part(self) -> Dict[str, Any]:
        return {"events": self.events, "satellite": self.satellite, "rasters": self.rasters, "credits": self.credits}

    def credit(self, text: str) -> None:
        if text and text not in self.credits:
            self.credits.append(text)


def deg(v: int) -> str:
    return f"{int(v)}°"


def _day(snap: Snapshot, city_key: str, n: int, at: str) -> Dict[str, Any]:
    days = snap.forecasts[city_key]["days"]
    if n > len(days):
        raise ValueError(f"{at}: the {city_key} forecast has {len(days)} days, not {n}")
    return days[n - 1]


def build(rows: List[WxRow], snap: Snapshot, windows: Dict[str, Window]) -> WeatherPayload:
    out = WeatherPayload()
    rep = out.report
    shown_products: Dict[str, List[Dict[str, Any]]] = {}  # row id -> the products it shows (for source lines)

    def put(e: Dict[str, Any], r: WxRow) -> None:
        w = windows[r.id]
        e.update(id=f"wx_{r.id}", t_in=w.t_in, t_out=w.t_out)
        out.events.append(e)

    from .layers import get as layer_type

    out.shown = shown_products
    for r in rows:
        at = f"weather_layers.csv row {r.line} ({r.id})"
        ds = r.data_source
        lt = layer_type(r.type) if r.type not in ("temp_marker", "forecast_strip", "now_card", "alert_area", "satellite", "source_line") else None
        if lt is not None:
            if lt.build is not None:
                lt.build(r, snap, windows[r.id], out)
            continue
        if r.type == "temp_marker":
            city = find_city(ds.target)
            if ds.product == "obs":
                o = snap.observations[city.key]
                src, tag, icon = Sourced.from_dict(o["temp"]), "NOW", o["icon"]
                shown_products[r.id] = [{"kind": "obs", "issued": o["issued"], "tz": city.tz}]
            else:
                n = ds.days()[0]
                d = _day(snap, city.key, n, at)
                kind = r.extra.get("kind", "high")
                if kind == "low" and d["low"] is None:
                    raise ValueError(f"{at}: the forecast has no low for day {n}")
                src = Sourced.from_dict(d["low"] if kind == "low" else d["high"])
                tag, icon = f"{d['dow']} {kind.upper()}", d["icon"]
                shown_products[r.id] = [{"kind": "forecast", "issued": snap.forecasts[city.key]["issued"], "tz": city.tz}]
            put({"type": "temp_marker", "lon": city.lon, "lat": city.lat, "city": city.name.upper(), "temp": deg(src.value), "tag": tag,
                 "icon": icon, "side": r.extra.get("side", "auto")}, r)
            rep.add(r.id, f"{city.key} {tag.lower()}", deg(src.value), src)
        elif r.type == "forecast_strip":
            city = find_city(ds.target)
            a, b = ds.days()
            days = []
            for n in range(a, b + 1):
                d = _day(snap, city.key, n, at)
                hi = Sourced.from_dict(d["high"])
                lo = Sourced.from_dict(d["low"]) if d["low"] else None
                pops = [p for p in (d.get("pop"), d.get("pop_night")) if p]
                pop = Sourced.from_dict(max(pops, key=lambda p: p["value"])) if pops else None
                pop_txt = f"{pop.value}%" if pop and pop.value >= POP_SHOWN_FROM else ""
                days.append({"dow": d["dow"], "icon": d["icon"], "hi": deg(hi.value), "lo": deg(lo.value) if lo else "", "pop": pop_txt})
                rep.add(r.id, f"{city.key} {d['dow']} high", deg(hi.value), hi)
                if lo:
                    rep.add(r.id, f"{city.key} {d['dow']} low", deg(lo.value), lo)
                if pop_txt:
                    rep.add(r.id, f"{city.key} {d['dow']} chance of rain", pop_txt, pop)
            put({"type": "forecast_strip", "title": r.extra.get("title") or f"{city.name.upper()}, {city.state}", "days": days}, r)
            shown_products[r.id] = [{"kind": "forecast", "issued": snap.forecasts[city.key]["issued"], "tz": city.tz}]
        elif r.type == "now_card":
            city = find_city(ds.target)
            o = snap.observations[city.key]
            src = Sourced.from_dict(o["temp"])
            put({"type": "now_card", "title": f"{city.name.upper()} NOW", "temp": deg(src.value), "text": o["text"], "icon": o["icon"],
                 "foot": f"Observed {clock(parse_iso(o['issued']), city.tz)} · {o['station']}", "anchor": r.extra.get("anchor", "tr")}, r)
            rep.add(r.id, f"{city.key} now", deg(src.value), src)
            shown_products[r.id] = [{"kind": "obs", "issued": o["issued"], "tz": city.tz}]
        elif r.type == "alert_area":
            area = ds.target.upper()
            a = snap.alerts[area]
            wanted = r.extra.get("events")
            areas = [x for x in a["areas"] if not wanted or x["event"] in wanted]
            w = windows[r.id]
            legend: Dict[str, str] = {}
            for i, x in enumerate(areas):
                color = alert_color(x["event"], x["severity"])
                legend.setdefault(x["event"], color)
                out.fills.append({"id": f"wx_{r.id}_{i}", "type": "fill", "polys": x["polys"], "color": color, "opacity": float(r.extra.get("opacity", 0.5)),
                                  "outline_color": color, "t_in": w.t_in, "t_out": w.t_out})
                rep.add(r.id, f"{area} alert area", x["event"], Sourced(x["event"], "", "NWS alert", a["url"], area, x["sent"] or a["issued"], a["fetched"]))
            if r.extra.get("legend", True) and legend:
                put({"type": "alert_legend", "items": [{"label": k.upper(), "color": v} for k, v in legend.items()]}, r)
            shown_products[r.id] = [{"kind": "alerts", "issued": a["fetched"], "tz": DEFAULT_TZ}]
        elif r.type == "satellite":
            key = f"geocolor@{ds.target}"
            s = snap.satellite[key]
            w = windows[r.id]
            out.satellite.append({"id": f"wx_{r.id}", "t_in": w.t_in, "t_out": w.t_out, "opacity": float(r.extra.get("opacity", 1.0)),
                                  "provider": {"id": "wx_geocolor_" + s["time"].replace("-", "").replace(":", "").replace("T", "_").rstrip("Z"),
                                               "title": "GOES-East GeoColor", "urlTemplate": s["url_template"], "format": "png", "tileSize": 256,
                                               "maxNativeZoom": s["max_zoom"]}})
            out.credit(s["credit"])
            shown_products[r.id] = [{"kind": "satellite", "issued": s["time"], "tz": DEFAULT_TZ}]
    for r in rows:
        if r.type != "source_line":
            continue
        w = windows[r.id]
        tz = r.extra.get("tz")
        on = [p for o in rows if o.type != "source_line" and o.id in windows and windows[o.id].t_in < w.t_out and w.t_in < windows[o.id].t_out
              for p in shown_products.get(o.id, [])]
        text = r.extra.get("text") or source_text(on, tz)
        put({"type": "source_line", "text": text}, r)
    if any(r.type in ("temp_marker", "forecast_strip", "now_card", "alert_area") for r in rows):
        out.credits.insert(0, "Weather data: National Weather Service (NOAA). Not an official NWS product; for warnings, follow your local NWS office.")
    return out


def source_text(products: List[Dict[str, Any]], tz: Optional[str] = None) -> str:
    """'Data: National Weather Service · Forecast as of 4:11 PM CDT · Satellite: NASA GIBS / NOAA GOES-East, 3:00 PM CDT'."""
    parts = []
    nws = [p for p in products if p["kind"] in ("forecast", "obs", "alerts")]
    if nws:
        zone = tz or nws[0]["tz"]
        parts.append("Data: National Weather Service")
        fc = [p["issued"] for p in nws if p["kind"] == "forecast"]
        if fc:
            parts.append(f"Forecast as of {clock(min(parse_iso(x) for x in fc), zone, date=True)}")
        ob = [p["issued"] for p in nws if p["kind"] == "obs"]
        if ob:
            parts.append(f"Observed {clock(min(parse_iso(x) for x in ob), zone)}")
        al = [p["issued"] for p in nws if p["kind"] == "alerts"]
        if al:
            parts.append(f"Alerts as of {clock(max(parse_iso(x) for x in al), zone)}")
    sat = [p["issued"] for p in products if p["kind"] == "satellite"]
    if sat:
        zone = tz or (nws[0]["tz"] if nws else DEFAULT_TZ)
        parts.append(f"Satellite: NASA GIBS / NOAA GOES-East, {clock(parse_iso(sat[0]), zone)}")
    for p in products:   # layer types in weather/layers/ describe their own source ("Radar: NOAA NEXRAD via IEM, 4:35 PM CDT")
        if p["kind"] == "text" and p.get("text") and p["text"] not in parts:
            parts.append(p["text"])
    return " · ".join(parts) or "Data: National Weather Service"
