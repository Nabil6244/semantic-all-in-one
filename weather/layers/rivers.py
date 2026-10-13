"""River crests (phase 4, post-event): the highest gage height a USGS gauge recorded in a window, as a marker at the gauge.

    river_crest   usgs:crest@08074000#2017-08-25..2017-09-05     "BUFFALO BAYOU 41.9 FT" · "CREST AUG 28 · MAJOR FLOOD"

The gauge name, place and readings come from USGS Water Services (gage height, parameter 00065). Values USGS still marks
provisional ("P") are labelled PROVISIONAL. Flood categories (action / minor / moderate / major stage) and the list of historic
crests come from the NWS water service when it knows the gauge; its categories are today's, so the report says so. The screen
names the crest's DAY (in extra.tz, Central by default); the report keeps the exact time.

extra: label (words: the river's name on screen), chart (true: a hydrograph panel next to the map), tz, side."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..post import usgs
from ..post.fmt import amount, date_range, named, no_digits, short
from ..provenance import Sourced
from ..tz import ZONES, to_local
from . import LayerType, register

CAT_COLOR = {"major": "#B03AF0", "moderate": "#E2402A", "minor": "#F29A2E", "action": "#F2E03A"}


def _check(row) -> None:
    usgs.site_ok(row.data_source.target)
    date_range(row.data_source.selector)
    if "label" in row.extra:
        no_digits(row.extra["label"], "the label")
    if row.extra.get("tz", "America/Chicago") not in ZONES:
        raise ValueError(f"extra tz {row.extra.get('tz')!r} is not a US time zone name (America/Chicago ...)")


def _fetch(row, ctx) -> None:
    from ..post.products import fetch_gauge

    a, b = date_range(row.data_source.selector)
    fetch_gauge(ctx, row.data_source.target, a, b)


def local_day(t: datetime, tz: str) -> datetime:
    return to_local(t.astimezone(timezone.utc), tz)[0]


def crest_facts(entry, a, b, tz="America/Chicago"):
    """Everything the crest marker, the hydrograph and the timeline say about one gauge's crest."""
    from ..post.products import series

    s = series(entry)
    c = usgs.crest(s)
    loc = local_day(c.when, tz)
    nw = entry.get("nwps") or {}
    cats = nw.get("categories") or {}
    cat = usgs.category(c.value, cats)
    standing = usgs.record_standing(c.value, c.when, nw.get("crests") or [])
    return s, c, loc, cat, cats, standing


def _build(row, snap, window, out) -> None:
    from ..post.products import gauge_key

    a, b = date_range(row.data_source.selector)
    site = row.data_source.target
    entry = snap.extra[gauge_key(site, a, b)]
    tz = row.extra.get("tz", "America/Chicago")
    s, c, loc, cat, cats, standing = crest_facts(entry, a, b, tz)
    name = str(row.extra.get("label") or usgs.short_name(s.name)).upper()
    unit = "FT" if s.unit.lower() in ("ft", "feet") else s.unit.upper()
    value = f"{amount(c.value)} {unit}"
    sub = [f"CREST {short(loc.date())}"]
    if cat:
        sub.append(f"{cat.upper()} FLOOD" if cat != "action" else "ABOVE ACTION STAGE")
    record = bool(standing and standing["record"])
    tag = "PROVISIONAL" if c.provisional else ("RECORD CREST" if record else "")
    issued = usgs.utc(c.when)
    out.events.append({"id": f"wx_{row.id}", "type": "post_chip", "t_in": window.t_in, "t_out": window.t_out, "lon": s.lon, "lat": s.lat,
                       "label": name, "value": value, "count": True, "decimals": len(amount(c.value).split(".")[1]), "sub": " · ".join(sub),
                       "tag": tag, "side": row.extra.get("side", "auto"), "kind": "river", "accent": CAT_COLOR.get(cat or "", "#3FC8E0")})
    q = "provisional" if c.provisional else ("approved" if "A" in c.qualifiers else "/".join(c.qualifiers) or "unmarked")
    timing = " (the record has a gap beside the crest: its time is uncertain)" if c.gap_near else ""
    out.report.add(row.id, f"{name} crest, {loc:%Y-%m-%d %H:%M} local{timing}", value,
                   Sourced(c.value, s.unit, f"USGS gage height (00065), {q}", entry["url"], f"USGS {site} {s.name}", issued, entry["fetched"]))
    if cat:
        out.report.add(row.id, f"{name} flood category at the crest (NWS's current stages: {', '.join(f'{k} {v:g}' for k, v in cats.items())})",
                       sub[1], Sourced(cats[cat], s.unit, "NWS water gauge flood categories (current)", entry["nwps_url"], (entry.get("nwps") or {}).get("lid") or site,
                                       issued, entry["fetched"]))
    if record:
        p = standing["previous"]
        out.report.add(row.id, f"{name} record crest: above every other crest NWS lists ({standing['listed']}; highest {p['stage']:g} on {p['time']}"
                       + (", an older datum" if p["olddatum"] else "") + ")", "RECORD CREST",
                       Sourced(p["stage"], s.unit, "NWS water gauge historic crests", entry["nwps_url"], (entry.get("nwps") or {}).get("lid") or site,
                               p["time"], entry["fetched"]))
    if row.extra.get("chart"):
        start = datetime(a.year, a.month, a.day, tzinfo=c.when.tzinfo)
        end = datetime(b.year, b.month, b.day, 23, 59, tzinfo=c.when.tzinfo)
        vals = usgs.hourly(s, start, end)
        ci = int((c.when - start).total_seconds() // 3600)
        lines = [{"label": f"{k.upper()} FLOOD {amount(v)} {unit}" if k != "action" else f"ACTION {amount(v)} {unit}", "value": v,
                  "color": CAT_COLOR[k]} for k, v in cats.items() if k in ("major", "moderate", "minor")]
        for ln in lines:
            out.report.add(row.id, f"{name} hydrograph line (NWS's current flood stage)", ln["label"],
                           Sourced(ln["value"], s.unit, "NWS water gauge flood categories (current)", entry["nwps_url"],
                                   (entry.get("nwps") or {}).get("lid") or site, entry["fetched"], entry["fetched"]))
        days = [short((a + timedelta(days=k))) for k in range((b - a).days + 1)]
        out.events.append({"id": f"wx_{row.id}_chart", "type": "post_hydrograph", "t_in": window.t_in, "t_out": window.t_out,
                           "title": name, "sub": f"GAGE HEIGHT ({unit}) · USGS {site}", "values": vals, "per_day": 24, "days": days,
                           "lines": lines, "crest": {"index": ci, "text": value}, "tag": "PROVISIONAL" if usgs.any_provisional(s) else "",
                           "anchor": row.extra.get("anchor", "r")})
    out.credit(usgs.CREDIT)
    prov = " (provisional)" if usgs.any_provisional(s) else ""
    out.shown[row.id] = [{"kind": "text", "text": f"River: USGS {site}{prov}" + (" · flood stages: NWS" if cat else "")}]


register(LayerType(name="river_crest", products=[("usgs", "crest")], extra_keys=frozenset({"label", "chart", "tz", "side", "anchor"}),
                   fetch=named(_fetch), build=named(_build), check=_check,
                   about="the highest gage height a USGS river gauge recorded in a window, as a marker (and an optional hydrograph)"))
