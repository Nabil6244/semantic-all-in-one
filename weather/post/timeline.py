"""The marks of an event timeline, each read from a product (never typed in): a date, a few words, and the number the data gives.

A mark names its source the way a layer's data_source does:
    nhc:landfall@AL092017#1                         the first landfall in the NHC best track inside the timeline's days (#2 ...)
    acis:peak_day@Houston,TX#2017-08-25..2017-09-01 the wettest single day at the station in that range
    usgs:crest@08074000#2017-08-25..2017-09-05      a river gauge's crest
    acis:record@Houston,TX#pcpn#2017-08-27          the day of a record (its headline)
An author may replace a mark's title words ({"from": ..., "title": "HARVEY COMES ASHORE"}); numbers always come from data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..provenance import Sourced
from ..sidecar import DataSource, parse_data_source
from ..tz import to_local
from . import acis, besttrack, usgs
from .fmt import amount, date_range, day, no_digits, short

KINDS = {("nhc", "landfall"), ("acis", "peak_day"), ("usgs", "crest"), ("acis", "record")}


@dataclass
class Mark:
    when: datetime  # local time (a daily value sits at noon)
    title: str
    detail: str
    timed: bool  # the time of day is known (shown as '10 PM')
    report: List[Tuple[str, str, Sourced]] = field(default_factory=list)
    lon: Optional[float] = None
    lat: Optional[float] = None


def parse_mark(spec: Any) -> Tuple[DataSource, str]:
    if isinstance(spec, str):
        spec = {"from": spec}
    if not isinstance(spec, dict) or "from" not in spec:
        raise ValueError('each timeline mark is {"from": "nhc:landfall@AL092017#1"} (optionally with "title" words)')
    bad = set(spec) - {"from", "title"}
    if bad:
        raise ValueError(f"a timeline mark takes from and title (not {', '.join(sorted(bad))})")
    ds = parse_data_source(spec["from"])
    if (ds.provider, ds.product) not in KINDS:
        raise ValueError(f"a timeline mark comes from {', '.join(f'{a}:{b}@' for a, b in sorted(KINDS))} (got {ds.text})")
    title = no_digits(str(spec.get("title", "")).upper(), "the mark title") if spec.get("title") else ""
    if ds.product == "landfall":
        besttrack.check_id(ds.target)
        if ds.selector and not ds.selector.isdigit():
            raise ValueError(f"{ds.text}: the landfall number after # must be 1, 2, 3 ...")
    elif ds.product in ("peak_day", "crest"):
        date_range(ds.selector)
        if ds.product == "crest":
            usgs.site_ok(ds.target)
        else:
            acis.station_for(ds.target)
    else:
        sel = ds.selector.split("#")
        if len(sel) != 2:
            raise ValueError(f"{ds.text}: a record mark needs #element#date")
        day(sel[1])
        acis.station_for(ds.target, record=True)
    return ds, title


def fetch_mark(ds: DataSource, ctx) -> None:
    from . import products as P

    if ds.product == "landfall":
        P.fetch_track(ctx, ds.target)
    elif ds.product == "peak_day":
        a, b = date_range(ds.selector)
        P.fetch_daily(ctx, [acis.station_for(ds.target)], a, b)
    elif ds.product == "crest":
        a, b = date_range(ds.selector)
        P.fetch_gauge(ctx, ds.target, a, b)
    else:
        elem, d = ds.selector.split("#")
        e = acis.ELEM_RE.match(elem)
        if not e:
            raise ValueError(f"{ds.text}: unknown element {elem!r}")
        P.fetch_record(ctx, acis.station_for(ds.target, record=True), e.group(1), day(d), e.group(2) or "all")


def build_mark(ds: DataSource, title: str, snap, tz: str, axis: Optional[Tuple[date, date]] = None) -> Mark:
    from . import products as P

    if ds.product == "landfall":
        entry = snap.extra[f"post:nhc:best:{ds.target.upper()}"]
        name, fixes = besttrack.parse_block(entry["lines"])
        lands = [f for f in besttrack.landfalls(fixes) if axis is None or axis[0] <= to_local(f.time, tz)[0].date() <= axis[1]]
        n = int(ds.selector or 1)
        if n > len(lands):
            raise ValueError(f"{ds.target} has {len(lands)} landfall(s) in the best track"
                             + (f" between {axis[0]} and {axis[1]}" if axis else "") + f", not {n}")
        f = lands[n - 1]
        local, _abbr = to_local(f.time, tz)
        cat = besttrack.category(f.wind_kt, f.status)
        detail = f"{cat} · {besttrack.mph(f.wind_kt)} MPH"
        src = Sourced(f.wind_kt, "kt", "NHC best track (HURDAT2), landfall row", entry["url"], f"{f.lat:.1f}N {abs(f.lon):.1f}W", f.time.isoformat(), entry["fetched"])
        return Mark(local, title or "LANDFALL", detail, True,
                    [(f"{name.title()} landfall {n} at {f.time:%Y-%m-%d %H:%MZ}: wind {f.wind_kt} kt = {besttrack.mph(f.wind_kt)} mph (nearest 5)", detail, src)],
                    f.lon, f.lat)
    if ds.product == "peak_day":
        a, b = date_range(ds.selector)
        sid = acis.station_for(ds.target)
        entry = snap.extra[P.daily_key([sid], a, b)]
        st = entry["stations"][0]
        pk = acis.peak_day([tuple(v) for v in st["values"]])
        if pk is None:
            raise ValueError(f"ACIS has no daily rainfall for {sid} between {a} and {b}")
        d, v = pk
        label = acis.label_for(sid, st["name"])
        detail = f"{v:.2f} IN · {label}"
        src = Sourced(v, "in", "RCC-ACIS daily precipitation, observed (wettest day in the range)", entry["url"], f"{sid} {st['name']}", d, entry["fetched"])
        dd = day(d)
        return Mark(datetime.combine(dd, time(12)), title or "WETTEST DAY", detail, False, [(f"{label} wettest day {d}", detail, src)],
                    st["ll"][0], st["ll"][1])
    if ds.product == "crest":
        a, b = date_range(ds.selector)
        entry = snap.extra[P.gauge_key(ds.target, a, b)]
        s = P.series(entry)
        c = usgs.crest(s)
        local, _abbr = to_local(c.when.astimezone(timezone.utc), tz)
        name = usgs.short_name(s.name)
        unit = "FT" if s.unit.lower() in ("ft", "feet") else s.unit.upper()
        detail = f"{name} {amount(c.value)} {unit}" + (" · PROVISIONAL" if c.provisional else "")
        src = Sourced(c.value, s.unit, "USGS gage height (00065)" + (", provisional" if c.provisional else ""), entry["url"], f"USGS {ds.target}",
                      usgs.utc(c.when), entry["fetched"])
        # a crest beside a gap in the record has no sure time: the day only
        return Mark(local if not c.gap_near else datetime.combine(local.date(), time(12)), title or "RIVER CREST", detail, not c.gap_near,
                    [(f"{name} crest", detail, src)], s.lon, s.lat)
    elem, d = ds.selector.split("#")
    e = acis.ELEM_RE.match(elem)
    sid = acis.station_for(ds.target, record=True)
    entry = snap.extra[P.record_key(sid, e.group(1), day(d), e.group(2) or "all")]
    r = P.ranking(entry)
    head = acis.headline(r, e.group(2) or "all")
    detail = f"{acis.amount_text(r.elem, r.value)} · {acis.label_for(sid, entry['name'])}"
    src = Sourced(r.value, acis.ELEMS[r.elem][0], "RCC-ACIS period-of-record summary", entry["url"], sid, entry["day"], entry["fetched"])
    return Mark(datetime.combine(day(d), time(12)), title or head, detail, False, [(f"record day {d}", f"{head} · {detail}", src)])


def position(m: Mark, a: date, b: date) -> float:
    """0..1 along an axis from the start of day a to the end of day b."""
    t0 = datetime.combine(a, time(0))
    total = (b - a).days + 1
    w = m.when.replace(tzinfo=None)
    return max(0.0, min(1.0, (w - t0).total_seconds() / (total * 86400)))


def stamp(m: Mark) -> str:
    """'AUG 25 · 10 PM' (a timed mark) or 'AUG 27'."""
    s = short(m.when.date())
    if m.timed:
        h = m.when.hour % 12 or 12
        s += f" · {h} {'AM' if m.when.hour < 12 else 'PM'}"
    return s
