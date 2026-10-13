"""Fetch each post-event product once into the snapshot (snap.extra, keys starting "post:"), so the layer types and the
timeline read the same numbers. Every entry keeps the URL it came from and when it was fetched."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import acis, besttrack, mrms, usgs


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat()


# ---- ACIS ---------------------------------------------------------------------------------------------------------------

def daily_key(sids: Sequence[str], a: date, b: date) -> str:
    return f"post:acis:pcpn:{','.join(sids)}:{a}..{b}"


def fetch_daily(ctx, sids: Sequence[str], a: date, b: date) -> str:
    """Daily precipitation for the stations (one ACIS request), with each station's location. Returns the snapshot key."""
    key = daily_key(sids, a, b)
    if key in ctx.snap.extra:
        return key
    url = acis.daily_url(sids, a, b)
    stations = acis.parse_multi(ctx.get_text(url), sids, a, b)
    for st in stations:
        if not st.get("ll"):   # a threaded record has no location: its airport station's
            st["ll"] = fetch_meta(ctx, acis.base_sid(st["sid"]))["ll"]
    ctx.snap.extra[key] = {"url": url, "fetched": _iso(ctx.now), "sdate": a.isoformat(), "edate": b.isoformat(), "stations": stations}
    return key


def fetch_meta(ctx, sid: str, elem: str = "pcpn") -> Dict[str, Any]:
    key = f"post:acis:meta:{sid}:{elem}"
    if key not in ctx.snap.extra:
        url = acis.meta_url(sid, elem)
        ctx.snap.extra[key] = dict(acis.parse_meta(ctx.get_text(url), sid), url=url, fetched=_iso(ctx.now))
    return ctx.snap.extra[key]


def record_key(sid: str, elem: str, d: date, scope: str) -> str:
    return f"post:acis:rank:{sid}:{elem}:{scope}:{d}"


def fetch_record(ctx, sid: str, elem: str, d: date, scope: str = "all") -> str:
    key = record_key(sid, elem, d, scope)
    if key in ctx.snap.extra:
        return key
    rurl, durl = acis.rank_url(sid, elem, d, scope), acis.day_url(sid, elem, d)
    top, meta = acis.parse_rank(ctx.get_text(rurl))
    v = acis.parse_day(ctx.get_text(durl))
    if v.amount is None:
        raise ValueError(f"ACIS has no {elem} value for {sid} on {d} (missing)")
    ctx.snap.extra[key] = {"sid": sid, "elem": elem, "day": d.isoformat(), "scope": scope, "value": v.amount, "raw": v.raw,
                           "top": [[x, w] for x, w in top], "name": meta["name"], "por_start": meta["por_start"],
                           "url": rurl, "day_url": durl, "fetched": _iso(ctx.now)}
    return key


def ranking(entry: Dict[str, Any]) -> acis.Ranking:
    return acis.rank_day(entry["elem"], entry["day"], entry["value"], [(v, d) for v, d in entry["top"]], station=entry["name"] or entry["sid"],
                         por_start=entry["por_start"] or "")


# ---- USGS + NWS water -------------------------------------------------------------------------------------------------------

def gauge_key(site: str, a: date, b: date) -> str:
    return f"post:usgs:{site}:{a}..{b}"


def fetch_gauge(ctx, site: str, a: date, b: date) -> str:
    key = gauge_key(site, a, b)
    if key in ctx.snap.extra:
        return key
    url = usgs.iv_url(site, a, b)
    s = usgs.parse_iv(ctx.get_text(url), site)
    nwps, nurl = None, usgs.nwps_url(site)
    try:
        nwps = usgs.parse_nwps(ctx.get_text(nurl))
    except Exception as exc:   # flood categories are a bonus: the crest stands without them
        ctx.snap.notes.append(f"USGS {site}: no NWS flood categories ({exc})")
    ctx.snap.extra[key] = {"site": site, "name": s.name, "lon": s.lon, "lat": s.lat, "unit": s.unit, "url": url, "fetched": _iso(ctx.now),
                           "points": [[t.isoformat(), v, q] for t, v, q in s.points], "nwps": nwps, "nwps_url": nurl}
    return key


def series(entry: Dict[str, Any]) -> usgs.Series:
    return usgs.Series(entry["site"], entry["name"], entry["lon"], entry["lat"], entry["unit"],
                       [(datetime.fromisoformat(t), v, list(q)) for t, v, q in entry["points"]])


# ---- NHC best track -------------------------------------------------------------------------------------------------------

def fetch_track(ctx, storm: str) -> str:
    storm = besttrack.check_id(storm)
    key = f"post:nhc:best:{storm}"
    if key in ctx.snap.extra:
        return key
    url = besttrack.latest_file(ctx.get_text(besttrack.INDEX), storm[:2])
    block = besttrack.storm_block(ctx.get_text(url), storm)
    ctx.snap.extra[key] = {"storm": storm, "url": url, "fetched": _iso(ctx.now), "lines": block}
    return key


# ---- MRMS rain grids ------------------------------------------------------------------------------------------------------

def grid_key(a: date, b: date, bbox: Sequence[float]) -> str:
    return f"post:mrms:{a}..{b}:{','.join(f'{x:g}' for x in bbox)}"


def fetch_rain_grid(ctx, a: date, b: date, bbox: Sequence[float]) -> str:
    key = grid_key(a, b, bbox)
    if key in ctx.snap.extra:
        return key
    urls = [mrms.png_url(d) for d in mrms.day_endings(a, b)]
    world = mrms.parse_world(ctx.get_text(mrms.world_url(urls[0])))
    pngs: List[bytes] = []
    for u in urls:
        try:
            pngs.append(ctx.get_bytes(u))
        except Exception as exc:
            raise ValueError(f"the MRMS rainfall grid {u} could not be fetched ({exc}); IEM keeps them from 2015 on") from None
    grid = mrms.sum_days(pngs, world, bbox)
    ctx.snap.extra[key] = {"urls": urls, "fetched": _iso(ctx.now), "start": f"{a}T12:00:00Z", "end": f"{b}T12:00:00Z", "grid": grid.to_dict()}
    return key
