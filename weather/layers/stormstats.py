"""A storm's statistics card from NHC's final best track (HURDAT2): its peak strength, its lowest pressure and one landfall.

    storm_stats   nhc:stats@AL092022     extra {"landfall": 3, "anchor": "l" | "r", "tz": "America/New_York"}
                  nhc:stats@AL092026#working   a storm of the current season: NHC's working best track (GIS), PRELIMINARY, no landfall

Every value comes from the HURDAT2 block of the storm (weather.post.besttrack): the peak is the highest sustained wind (the first
time it was reached), the lowest pressure the lowest MSLP, the landfall the record marked L (extra.landfall: which one, 1-based;
default the strongest). Wind is shown in mph rounded to 5, as NHC writes it, with the Saffir-Simpson category. A storm of the
current season is not in HURDAT2 yet (it is published each spring): #working reads the working best track instead, labelled
PRELIMINARY (it is revised after the season and marks no landfalls)."""

from __future__ import annotations

from typing import Any, Dict, List

from ..news.rows import at
from ..news.timeline import tz_of
from ..post import besttrack
from ..post.products import fetch_track
from ..provenance import Sourced
from ..tz import clock
from . import LayerType, register

ANCHORS = ("l", "r")


def _check(row) -> None:
    besttrack.check_id(row.data_source.target)
    if row.data_source.selector not in ("", "working"):
        raise ValueError("storm_stats takes no #selector, or #working (the working best track of a current storm)")
    n = row.extra.get("landfall")
    if n is not None and (not isinstance(n, int) or n < 1):
        raise ValueError("storm_stats extra landfall is a whole number from 1 (which landfall to show)")
    if row.extra.get("anchor", "l") not in ANCHORS:
        raise ValueError("storm_stats anchor is l or r")


def _working_key(row) -> str:
    return f"nhc:{row.data_source.target.upper()}#best"   # the same entry a storm_track #best row fetches (weather.layers.storms)


def _fetch(row, ctx) -> None:
    if row.data_source.selector == "working":
        from ..news import nhc
        from ..news.rows import first_answer
        from ..news.timeline import iso

        key = _working_key(row)
        if key in ctx.snap.extra:
            return
        sid = row.data_source.target.upper()
        try:
            url, blob = first_answer([nhc.BEST.format(id=sid.lower())], ctx.get_bytes, f"the NHC best track of {sid}")
            data = nhc.best_track(blob)
        except ValueError as exc:
            raise ValueError(f"{at(row)}: {exc}") from None
        ctx.snap.extra[key] = {"storm": sid, "selector": "best", "url": url, "issued": data["points"][-1]["time"] if data["points"] else "",
                               "fetched": iso(ctx.now), **data}
        return
    try:
        fetch_track(ctx, row.data_source.target)
    except ValueError as exc:
        raise ValueError(f"{at(row)}: {exc}") from None


def _build_working(row, snap, window, out) -> None:
    from ..news import nhc
    from ..tz import parse_iso

    v = snap.extra[_working_key(row)]
    tz = tz_of(row)
    pts = [p for p in v["points"] if p.get("wind_kt") is not None]
    if not pts:
        raise ValueError(f"{at(row)}: the working best track of {v['storm']} has no intensities")
    peak = max(pts, key=lambda p: p["wind_kt"])
    lows = [p for p in pts if p.get("mslp")]
    rows = []

    def src(value, unit, what, p) -> Sourced:
        return Sourced(value, unit, f"NHC working best track (preliminary), {what}", v["url"], f"{p['lat']}N {abs(p['lon'])}W", p["time"], v["fetched"])

    value = f"{short_category(int(peak['wind_kt']), peak.get('kind', ''))} · {nhc.mph(peak['wind_kt'])} MPH"
    rows.append({"label": "PEAK STRENGTH", "value": value, "sub": clock(parse_iso(peak["time"]), tz, date=True).upper()})
    out.report.add(row.id, f"{v['storm']} peak sustained wind ({peak['wind_kt']:g} kt, preliminary)", value, src(peak["wind_kt"], "kt", "peak", peak))
    if lows:
        low = min(lows, key=lambda p: p["mslp"])
        value = f"{int(low['mslp'])} MB"
        rows.append({"label": "LOWEST PRESSURE", "value": value, "sub": clock(parse_iso(low["time"]), tz, date=True).upper()})
        out.report.add(row.id, f"{v['storm']} minimum central pressure (preliminary)", value, src(low["mslp"], "mb", "minimum pressure", low))
    name = (pts[-1].get("name") or v["storm"]).upper()
    kind = "HURRICANE" if peak["wind_kt"] >= 64 else "TROPICAL STORM" if peak["wind_kt"] >= 34 else "TROPICAL DEPRESSION"
    out.events.append({"id": f"wx_{row.id}", "type": "storm_stats", "t_in": window.t_in, "t_out": window.t_out, "title": f"{kind} {name}",
                       "rows": rows, "foot": "NHC WORKING BEST TRACK · PRELIMINARY", "anchor": row.extra.get("anchor", "l")})
    out.credit(besttrack.CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": f"Data: NOAA National Hurricane Center working best track ({v['storm']}), preliminary"}]


def short_category(kt: int, status: str) -> str:
    """'CAT 4' / 'TROPICAL STORM' / 'TROPICAL DEPRESSION' (Saffir-Simpson from the sustained wind)."""
    full = besttrack.category(kt, status)
    return full.replace("CATEGORY ", "CAT ").replace(" HURRICANE", "") if full.startswith("CATEGORY") else full


def facts(lines: List[str], landfall: int = 0) -> Dict[str, Any]:
    """{name, peak, low, landfall, landfalls}: the fixes the card shows (landfall 0 = the strongest)."""
    name, fixes = besttrack.parse_block(lines)
    peak = max(fixes, key=lambda f: f.wind_kt)   # max() keeps the first fix at the peak
    lows = [f for f in fixes if f.pressure_mb]
    low = min(lows, key=lambda f: f.pressure_mb) if lows else None
    lfs = besttrack.landfalls(fixes)
    if landfall and landfall > len(lfs):
        raise ValueError(f"the best track has {len(lfs)} landfall(s), not {landfall}")
    lf = lfs[landfall - 1] if landfall else (max(lfs, key=lambda f: f.wind_kt) if lfs else None)
    return {"name": name, "peak": peak, "low": low, "landfall": lf, "landfalls": len(lfs)}


def _build(row, snap, window, out) -> None:
    if row.data_source.selector == "working":
        return _build_working(row, snap, window, out)
    v = snap.extra[f"post:nhc:best:{row.data_source.target.upper()}"]
    tz = tz_of(row)
    f = facts(v["lines"], int(row.extra.get("landfall") or 0))
    peak, low, lf = f["peak"], f["low"], f["landfall"]

    def src(value, unit, what, fix) -> Sourced:
        return Sourced(value, unit, f"NHC best track (HURDAT2), {what}", v["url"], f"{fix.lat}N {abs(fix.lon)}W",
                       fix.time.isoformat().replace("+00:00", "Z"), v["fetched"])

    rows = []
    value = f"{short_category(peak.wind_kt, peak.status)} · {besttrack.mph(peak.wind_kt)} MPH"
    rows.append({"label": "PEAK STRENGTH", "value": value, "sub": clock(peak.time, tz, date=True).upper()})
    out.report.add(row.id, f"{f['name']} peak sustained wind ({peak.wind_kt} kt)", value, src(peak.wind_kt, "kt", "peak", peak))
    if low is not None:
        value = f"{low.pressure_mb} MB"
        rows.append({"label": "LOWEST PRESSURE", "value": value, "sub": clock(low.time, tz, date=True).upper()})
        out.report.add(row.id, f"{f['name']} minimum central pressure", value, src(low.pressure_mb, "mb", "minimum pressure", low))
    if lf is not None:
        value = f"{short_category(lf.wind_kt, lf.status)} · {besttrack.mph(lf.wind_kt)} MPH"
        rows.append({"label": "LANDFALL", "value": value, "sub": clock(lf.time, tz, date=True).upper()})
        out.report.add(row.id, f"{f['name']} landfall at {lf.time:%Y-%m-%d %H:%MZ} ({lf.wind_kt} kt)", value, src(lf.wind_kt, "kt", "landfall", lf))
    kind = "HURRICANE" if peak.wind_kt >= 64 else "TROPICAL STORM" if peak.wind_kt >= 34 else "TROPICAL DEPRESSION"
    out.events.append({"id": f"wx_{row.id}", "type": "storm_stats", "t_in": window.t_in, "t_out": window.t_out,
                       "title": f"{kind} {f['name'].upper()}", "rows": rows, "foot": "NHC BEST TRACK (HURDAT2) · FINAL",
                       "anchor": row.extra.get("anchor", "l")})
    out.credit(besttrack.CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": "Storm record: NHC best track (HURDAT2, final)"}]


register(LayerType(name="storm_stats", products=[("nhc", "stats")], extra_keys=frozenset({"landfall", "anchor", "tz"}),
                   fetch=_fetch, build=_build, check=_check,
                   about="a storm's peak strength, lowest pressure and a landfall, from NHC's final best track (HURDAT2)"))
