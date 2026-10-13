"""Timed tile loops of Weather News: the radar loop and the satellite loop.

    radar           iem:radar@2024-05-06T21:00Z..2024-05-07T03:00Z#n0q   a past window (UTC), every scan IEM lists, thinned
                    iem:radar@latest#n0q                                 the last ~2 hours (a "now" product: stale after 1 h)
                    extra: provider (iem_n0q | noaa_mapservices | none), frames (default 18), opacity, legend (true), tz, date
    satellite_loop  gibs:geocolor_loop@2026-10-12T15:00Z..2026-10-12T21:00Z   GOES-East GeoColor every 10 min (GIBS keeps ~2 months)
                    gibs:truecolor_loop@2022-09-25..2022-09-29                  one Suomi NPP VIIRS true-colour picture a day (any year)
                    extra: frames (default 16), opacity (1), tz

A loop replays its real window over the layer's on-screen time (weather.news.timeline.to_layer), so a warnings_archive row with
the same window and the same beat shows each warning on the radar frame of its issue time. The clock chip names each frame's
time ("RADAR · 3:05 PM EDT"); the source line names the radar and the window."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..news import radar_providers as rp
from ..news.rows import at
from ..news.timeline import UTC, iso, parse_window, span, stamp, to_layer, tz_of
from ..provenance import Sourced
from ..tz import clock, parse_iso
from . import Frame, LayerType, Raster, register

GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
GEOCOLOR = ("GOES-East_ABI_GeoColor", 7, "png")
TRUECOLOR = ("VIIRS_SNPP_CorrectedReflectance_TrueColor", 9, "jpg")
SAT_CREDIT = {"geocolor_loop": "Satellite: GOES-East GeoColor (NOAA/NESDIS), served by NASA GIBS.",
              "truecolor_loop": "Satellite: Suomi NPP VIIRS true colour (NASA/NOAA), served by NASA GIBS."}
SAT_ON_SCREEN = {"geocolor_loop": "Satellite: NOAA GOES-East via NASA GIBS", "truecolor_loop": "Satellite: NASA/NOAA Suomi NPP VIIRS via NASA GIBS"}


# ---- radar -----------------------------------------------------------------------------------------------------------

def _radar_key(row) -> str:
    return f"radar:{row.extra.get('provider') or rp.DEFAULT_PROVIDER}@{row.data_source.target}"


def check_radar(row) -> None:
    ds = row.data_source
    if (ds.selector or "n0q") != "n0q":
        raise ValueError(f"radar takes #n0q (base reflectivity), got #{ds.selector}")
    if ds.target != "latest":
        parse_window(ds.target, max_hours=48)
    rp.get_provider(row.extra.get("provider"))
    n = row.extra.get("frames", rp.DEFAULT_FRAMES)
    if not isinstance(n, int) or not 2 <= n <= 60:
        raise ValueError("radar extra frames must be a whole number from 2 to 60")


def fetch_radar(row, ctx) -> None:
    key = _radar_key(row)
    if key in ctx.snap.extra:
        return
    p = rp.get_provider(row.extra.get("provider"))
    start, end = (None, None) if row.data_source.target == "latest" else parse_window(row.data_source.target, max_hours=48)
    try:
        got = rp.fetch_scans(p, start, end, ctx.get_text, ctx.now)
    except (ValueError, KeyError) as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    ctx.snap.extra[key] = {"provider": p.id, "target": row.data_source.target, "fetched": iso(ctx.now), **got}


def fresh_radar(snap, now: datetime) -> List[str]:
    out = []
    for key, v in snap.extra.items():
        if key.startswith("radar:") and v.get("target") == "latest" and v.get("scans"):
            newest = parse_iso(v["scans"][-1])
            if now - newest > rp.MAX_LATEST_AGE:
                out.append(f"the latest radar ({v['provider']}) ends at {stamp(newest)}, {(now - newest).total_seconds() / 3600:.1f} h ago (more than 1 h)")
    return out


def _label(prefix: str, t: datetime, tz: str, date: bool) -> str:
    return f"{prefix} · {clock(t, tz, date=date).upper()}"


def build_radar(row, snap, window, out) -> None:
    v = snap.extra[_radar_key(row)]
    p = rp.get_provider(v["provider"])
    tz = tz_of(row)
    if p.id == "none" or not v.get("scans"):
        out.shown[row.id] = [{"kind": "text", "text": p.on_screen}]
        return
    scans = [parse_iso(s) for s in v["scans"]]
    frames = rp.pick_frames(scans, int(row.extra.get("frames", rp.DEFAULT_FRAMES)))
    start, end = parse_iso(v.get("start") or iso(frames[0])), parse_iso(v.get("end") or iso(frames[-1]))
    if v.get("target") == "latest":
        start, end = frames[0], frames[-1]
    date = bool(row.extra.get("date", (end - start) > timedelta(hours=20)))
    fr = [Frame(to_layer(t, start, end, window.t_in, window.t_out) - window.t_in, rp.frame_provider(p, t), _label("RADAR", t, tz, date)) for t in frames]
    fr[0].at = 0.0
    out.rasters.append(Raster(f"wx_{row.id}", window.t_in, window.t_out, fr, opacity=float(row.extra.get("opacity", 0.8)), crossfade_s=0.15,
                              above_fills=True, clock=True).to_dict())
    if row.extra.get("legend", True) and p.legend:
        out.events.append({"id": f"wx_{row.id}_legend", "type": "radar_legend", "t_in": window.t_in, "t_out": window.t_out,
                           "stops": [{"dbz": d, "color": c} for d, c in p.legend],
                           "labels": [{"dbz": d, "text": tx} for d, tx in rp.LEGEND_LABELS], "title": "RADAR"})
    out.credit(p.attribution + f" ({p.licence_note}; {p.terms_url}).")
    shown = span(frames[0], frames[-1], tz, date=True)
    out.report.add(row.id, "radar loop scan times", shown, Sourced(shown, "", f"{p.title} (N0Q, {len(frames)} scans)", v["list_url"], "USCOMP",
                                                                  iso(frames[-1]), v["fetched"]))
    out.shown[row.id] = [{"kind": "text", "text": f"{p.on_screen}, {shown}"}]


register(LayerType(name="radar", products=[("iem", "radar")], extra_keys=frozenset({"provider", "frames", "opacity", "legend", "tz", "date"}),
                   fetch=fetch_radar, build=build_radar, check=check_radar, fresh=fresh_radar,
                   about="radar loop (NEXRAD mosaic via IEM): a past UTC window or the last two hours"))


# ---- satellite loop --------------------------------------------------------------------------------------------------

def _sat_key(row) -> str:
    return f"satloop:{row.data_source.product}@{row.data_source.target}"


def _days(target: str) -> List[datetime]:
    a, sep, b = target.partition("..")
    if not sep:
        raise ValueError(f"{target!r}: a daily loop is written YYYY-MM-DD..YYYY-MM-DD")
    d0, d1 = (datetime.strptime(x.strip(), "%Y-%m-%d").replace(tzinfo=UTC) for x in (a, b))
    if not timedelta(days=1) <= d1 - d0 <= timedelta(days=20):
        raise ValueError(f"{target!r}: a daily loop covers 2 to 21 days")
    return [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]


def check_sat(row) -> None:
    ds = row.data_source
    if ds.selector:
        raise ValueError(f"satellite_loop takes no #selector (got #{ds.selector})")
    if ds.product == "geocolor_loop":
        parse_window(ds.target, max_hours=24)
    else:
        _days(ds.target)
    n = row.extra.get("frames", 16)
    if not isinstance(n, int) or not 2 <= n <= 40:
        raise ValueError("satellite_loop extra frames must be a whole number from 2 to 40")


def _template(layer, t_text: str) -> str:
    name, z, ext = layer
    return f"{GIBS}/{name}/default/{t_text}/GoogleMapsCompatible_Level{z}/{{z}}/{{y}}/{{x}}.{ext}"


def fetch_sat(row, ctx) -> None:
    key = _sat_key(row)
    if key in ctx.snap.extra:
        return
    from ..resolve import GEOCOLOR_MAX_ZOOM, geocolor_times

    ds = row.data_source
    n = int(row.extra.get("frames", 16))
    try:
        if ds.product == "geocolor_loop":
            start, end = parse_window(ds.target, max_hours=24)
            url = (f"{GIBS}/1.0.0/{GEOCOLOR[0]}/default/GoogleMapsCompatible_Level{GEOCOLOR_MAX_ZOOM}/all/"
                   f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}--{end.strftime('%Y-%m-%dT%H:%M:%SZ')}.xml")
            times = []
            for a, b, step in geocolor_times(ctx.get_text(url)):
                t = a
                while t <= b:
                    if start <= t <= end:
                        times.append(t)
                    t += step
            times = rp.pick_frames(sorted(set(times)), n) if len(times) >= 2 else times
            if len(times) < 2:
                raise ValueError(f"GIBS lists fewer than 2 GOES-East GeoColor pictures between {stamp(start)} and {stamp(end)}")
            # GIBS lists times it no longer keeps (about two months): the first and last pictures must really be there
            for t in (times[0], times[-1]):
                probe = _template(GEOCOLOR, t.strftime("%Y-%m-%dT%H:%M:%SZ")).format(z=2, y=1, x=1)
                try:
                    ctx.get_bytes(probe)
                except Exception:
                    raise ValueError(f"GIBS no longer keeps GOES-East GeoColor for {stamp(t)} (it keeps about two months); for an "
                                     "older event use gibs:truecolor_loop@YYYY-MM-DD..YYYY-MM-DD") from None
            frames = [{"time": iso(t), "template": _template(GEOCOLOR, t.strftime("%Y-%m-%dT%H:%M:%SZ")), "max_zoom": GEOCOLOR[1]} for t in times]
            list_url = url
        else:
            days = _days(ds.target)
            frames = [{"time": iso(d), "template": _template(TRUECOLOR, d.strftime("%Y-%m-%d")), "max_zoom": TRUECOLOR[1], "daily": True} for d in days]
            list_url = _template(TRUECOLOR, days[0].strftime("%Y-%m-%d"))
    except (ValueError, KeyError) as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    ctx.snap.extra[key] = {"product": ds.product, "frames": frames, "list_url": list_url, "fetched": iso(ctx.now)}


def build_sat(row, snap, window, out) -> None:
    v = snap.extra[_sat_key(row)]
    tz = tz_of(row)
    times = [parse_iso(f["time"]) for f in v["frames"]]
    daily = v["product"] == "truecolor_loop"
    start, end = times[0], times[-1]
    frames = []
    for f, t in zip(v["frames"], times):
        label = f"SATELLITE · {t.strftime('%b').upper()} {t.day}" if daily else _label("SATELLITE", t, tz, False)
        prov = {"id": f"wx_sat_{v['product']}_{t.strftime('%Y%m%d%H%M')}", "title": f"{v['product']} {iso(t)}", "urlTemplate": f["template"],
                "format": "jpg" if daily else "png", "tileSize": 256, "maxNativeZoom": f["max_zoom"]}
        frames.append(Frame(to_layer(t, start, end, window.t_in, window.t_out) - window.t_in, prov, label))
    frames[0].at = 0.0
    out.rasters.append(Raster(f"wx_{row.id}", window.t_in, window.t_out, frames, opacity=float(row.extra.get("opacity", 1.0)),
                              crossfade_s=0.4 if daily else 0.25, above_fills=False, clock=True).to_dict())
    out.credit(SAT_CREDIT[v["product"]])
    shown = (f"{start.strftime('%b')} {start.day}–{end.strftime('%b')} {end.day}, {end.year}" if daily else span(start, end, tz, date=True))
    out.report.add(row.id, "satellite loop picture times", shown, Sourced(shown, "", SAT_CREDIT[v["product"]], v["list_url"], "GIBS",
                                                                           v["frames"][-1]["time"], v["fetched"]))
    out.shown[row.id] = [{"kind": "text", "text": f"{SAT_ON_SCREEN[v['product']]}, {shown}"}]


register(LayerType(name="satellite_loop", products=[("gibs", "geocolor_loop"), ("gibs", "truecolor_loop")],
                   extra_keys=frozenset({"frames", "opacity", "tz"}), fetch=fetch_sat, build=build_sat, check=check_sat,
                   about="satellite loop (GOES-East GeoColor every 10 min, or daily VIIRS true colour) at full strength"))
