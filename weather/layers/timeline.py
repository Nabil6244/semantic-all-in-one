"""The event timeline (phase 4, post-event): a horizontal line of days drawing in, with dated marks read from the data.

    event_timeline   post:timeline@2017-08-24..2017-09-02
                     extra {"marks": [{"from": "nhc:landfall@AL092017#1"},
                                      {"from": "acis:peak_day@Houston,TX#2017-08-25..2017-09-01"},
                                      {"from": "usgs:crest@08074000#2017-08-25..2017-09-05", "title": "BUFFALO BAYOU CRESTS"}]}

Every date, time and number on a mark comes from its source (weather.post.timeline): a landfall from the NHC best track, the
wettest day from RCC-ACIS, a river crest from USGS, a record day from ACIS. An author may change a mark's words, never its
numbers. Times are shown in extra.tz (Central by default).

extra: marks (2 to 6), title (words), tz."""

from __future__ import annotations

from datetime import timedelta

from ..post import timeline as T
from ..post.fmt import date_range, named, no_digits, short
from ..tz import ZONES
from . import LayerType, register


def _marks(row):
    marks = row.extra.get("marks")
    if not isinstance(marks, list) or not 1 <= len(marks) <= 6:
        raise ValueError("event_timeline needs extra marks: a list of 1 to 6 {\"from\": data source} entries")
    return [T.parse_mark(m) for m in marks]


def _check(row) -> None:
    a, b = date_range(row.data_source.target)
    if (b - a).days < 1 or (b - a).days > 21:
        raise ValueError("an event timeline spans 2 to 22 days")
    _marks(row)
    if "title" in row.extra:
        no_digits(row.extra["title"], "the title")
    if row.extra.get("tz", "America/Chicago") not in ZONES:
        raise ValueError(f"extra tz {row.extra.get('tz')!r} is not a US time zone name")


def _fetch(row, ctx) -> None:
    for ds, _title in _marks(row):
        T.fetch_mark(ds, ctx)


def _build(row, snap, window, out) -> None:
    a, b = date_range(row.data_source.target)
    tz = row.extra.get("tz", "America/Chicago")
    marks = []
    for ds, title in _marks(row):
        m = T.build_mark(ds, title, snap, tz, (a, b))
        f = T.position(m, a, b)
        if not (a <= m.when.date() <= b):
            raise ValueError(f"the mark from {ds.text} falls on {m.when.date()}, outside the timeline {a}..{b}: widen it")
        marks.append((f, m))
        for label, shown, src in m.report:
            out.report.add(row.id, label, shown, src)
    marks.sort(key=lambda x: x[0])
    n = (b - a).days + 1
    ticks = [{"f": (k + 0.5) / n, "label": short(a + timedelta(days=k))} for k in range(n)]
    out.events.append({"id": f"wx_{row.id}", "type": "post_timeline", "t_in": window.t_in, "t_out": window.t_out,
                       "title": no_digits(str(row.extra.get("title", "TIMELINE")).upper(), "the title"), "ticks": ticks,
                       "marks": [{"f": f, "when": T.stamp(m), "title": m.title, "detail": m.detail} for f, m in marks]})
    texts = []
    kinds = {ds.provider for ds, _t in _marks(row)}
    if "nhc" in kinds:
        texts.append("NHC best track")
    if "acis" in kinds:
        texts.append("NOAA RCC-ACIS")
    if "usgs" in kinds:
        texts.append("USGS")
    out.shown[row.id] = [{"kind": "text", "text": "Timeline: " + ", ".join(texts)}]
    from ..post import acis, besttrack, usgs

    for k, c in (("nhc", besttrack.CREDIT), ("acis", acis.CREDIT), ("usgs", usgs.CREDIT)):
        if k in kinds:
            out.credit(c)


register(LayerType(name="event_timeline", products=[("post", "timeline")], extra_keys=frozenset({"marks", "title", "tz"}),
                   fetch=named(_fetch), build=named(_build), check=_check,
                   about="a timeline of the event's days with dated marks read from the data (landfall, wettest day, river crest, records)"))
