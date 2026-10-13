"""Observed station rainfall and records (phase 4, post-event), from NOAA's RCC-ACIS.

    rain_total    acis:pcpn_total@Houston,TX#2017-08-25..2017-08-30            one place: a chip on the map ("HOUSTON (IAH) 31.26 IN")
                  acis:pcpn_total@Houston,TX|HOU|BPT|GLS#2017-08-25..2017-09-01 several: a bar chart (bars grow, values count up)
    record        acis:record@Houston,TX#pcpn#2017-08-27        where the day stands in the station's period of record:
                                                                 "WETTEST DAY ON RECORD" / "3RD WETTEST DAY ON RECORD", new vs old
                  acis:record@Houston,TX#pcpn:date#2017-08-27   only that calendar date ("WETTEST AUG 27 ON RECORD")
    temp_extreme  acis:record@Phoenix,AZ#maxt#2023-07-19          the same for heat (maxt) or cold (mint)

A place is 'City, ST' (weather.post.acis.PLACES: the airport for totals, the long threaded record for records) or an ACIS station
id. Totals count a trace as 0 and never fill a missing day: a total with missing days says how many. Data less than 90 days old
is labelled PRELIMINARY (NOAA's quality control is still running)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import List

from ..post import acis
from ..post.fmt import date_range, day, named, no_digits, short, span
from ..provenance import Sourced
from ..tz import parse_iso
from . import LayerType, register

PRELIMINARY_DAYS = 90


def _places(row) -> List[str]:
    return [p.strip() for p in row.data_source.target.split("|") if p.strip()]


def _labels(row, n: int) -> List[str]:
    labels = row.extra.get("labels")
    if labels is None:
        return []
    if not isinstance(labels, list) or len(labels) != n:
        raise ValueError(f"extra labels must list one name for each of the {n} place(s)")
    return [no_digits(str(x).upper(), "the label") for x in labels]


def _preliminary(last: date, fetched: str) -> bool:
    return parse_iso(fetched).date() - last < timedelta(days=PRELIMINARY_DAYS)


# ---- rain_total ---------------------------------------------------------------------------------------------------------

def _check_total(row) -> None:
    places = _places(row)
    if not places:
        raise ValueError("rain_total needs at least one place before the #")
    if len(places) > 8:
        raise ValueError(f"a rain_total bar chart shows at most 8 places (got {len(places)})")
    for p in places:
        acis.station_for(p)
    date_range(row.data_source.selector)
    _labels(row, len(places))
    show = row.extra.get("show", "chip" if len(places) == 1 else "bars")
    if show not in ("chip", "chips", "bars"):
        raise ValueError("extra show must be chip(s) or bars")
    if "decimals" in row.extra and row.extra["decimals"] not in (0, 1, 2):
        raise ValueError("extra decimals must be 0, 1 or 2")


def _fetch_total(row, ctx) -> None:
    from ..post.products import fetch_daily

    a, b = date_range(row.data_source.selector)
    fetch_daily(ctx, [acis.station_for(p) for p in _places(row)], a, b)


def _build_total(row, snap, window, out) -> None:
    from ..post.products import daily_key

    a, b = date_range(row.data_source.selector)
    places = _places(row)
    sids = [acis.station_for(p) for p in places]
    entry = snap.extra[daily_key(sids, a, b)]
    labels = _labels(row, len(places))
    dec = int(row.extra.get("decimals", 2))
    prelim = _preliminary(b, entry["fetched"])
    items = []
    for i, st in enumerate(entry["stations"]):
        tot = acis.total([tuple(v) for v in st["values"]])
        if tot.missing and len(tot.missing) == tot.days:
            raise ValueError(f"ACIS has no rainfall at all for {st['sid']} between {a} and {b}")
        label = labels[i] if labels else acis.label_for(st["sid"], st["name"])
        note = f"{len(tot.missing)} DAY{'S' if len(tot.missing) > 1 else ''} MISSING" if tot.missing else ""
        value = round(tot.amount, dec)
        text = f"{value:.{dec}f}"
        items.append({"label": label, "value": value, "text": text, "note": note, "ll": st["ll"], "sid": st["sid"], "name": st["name"]})
        out.report.add(row.id, f"{label} observed rainfall {span(a, b, True)}" + (f" ({note.lower()}: at least)" if note else ""),
                       f"{text} IN", Sourced(tot.amount, "in", "RCC-ACIS daily precipitation, observed (trace = 0)", entry["url"],
                                            f"{st['sid']} {st['name']}", b.isoformat(), entry["fetched"]))
    when = span(a, b, year=True)
    show = row.extra.get("show", "chip" if len(items) == 1 else "bars")
    tag = "PRELIMINARY" if prelim else ""
    if show == "bars":
        if row.extra.get("sort", True):
            items.sort(key=lambda x: -x["value"])
        out.events.append({"id": f"wx_{row.id}", "type": "post_bars", "t_in": window.t_in, "t_out": window.t_out,
                           "title": no_digits(str(row.extra.get("title", "RAINFALL TOTALS")).upper(), "the title"), "sub": f"{when} · OBSERVED",
                           "unit": "IN", "decimals": dec, "tag": tag, "anchor": row.extra.get("anchor", "r"),
                           "bars": [{"label": x["label"], "value": x["value"], "text": x["text"], "note": x["note"]} for x in items],
                           "foot": "Station data: NOAA RCC-ACIS"})
    else:
        for k, x in enumerate(items):
            lon, lat = x["ll"]
            out.events.append({"id": f"wx_{row.id}" + (f"_{k}" if len(items) > 1 else ""), "type": "post_chip", "t_in": window.t_in + 0.25 * k,
                               "t_out": window.t_out, "lon": lon, "lat": lat, "label": x["label"], "value": f"{x['text']} IN", "count": True,
                               "decimals": dec, "sub": f"{span(a, b)} · OBSERVED", "tag": x["note"] or tag, "side": row.extra.get("side", "auto"),
                               "kind": "rain"})
    out.credit(acis.CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": acis.SOURCE_TEXT + (" (preliminary)" if prelim else "")}]


register(LayerType(name="rain_total", products=[("acis", "pcpn_total")],
                   extra_keys=frozenset({"show", "labels", "title", "decimals", "sort", "anchor", "side"}),
                   fetch=named(_fetch_total), build=named(_build_total), check=_check_total,
                   about="observed station rainfall over a date range: a chip on the map, or a bar chart for several places"))


# ---- record / temp_extreme ----------------------------------------------------------------------------------------------------

SELECTOR = re.compile(r"^(?P<elem>[a-z]+(?::[a-z]+)?)#(?P<day>\d{4}-\d\d-\d\d)$")


def _parse(row, allowed) -> "tuple[str, str, date]":
    m = SELECTOR.match(row.data_source.selector or "")
    if not m:
        raise ValueError(f"{row.type} needs #element#date after the place, e.g. #pcpn#2017-08-27 or #maxt:date#2023-07-19")
    e = acis.ELEM_RE.match(m.group("elem"))
    if not e or e.group(1) not in allowed:
        raise ValueError(f"{row.type} element must be one of {', '.join(allowed)} (optionally :date for that calendar date), got {m.group('elem')!r}")
    return e.group(1), e.group(2) or "all", day(m.group("day"))


def _record_check(allowed):
    def check(row) -> None:
        _parse(row, allowed)
        acis.station_for(row.data_source.target, record=True)
        if "label" in row.extra:
            no_digits(row.extra["label"], "the label")
    return check


def _record_fetch(allowed):
    def fetch(row, ctx) -> None:
        from ..post.products import fetch_record

        elem, scope, d = _parse(row, allowed)
        fetch_record(ctx, acis.station_for(row.data_source.target, record=True), elem, d, scope)
    return fetch


def _record_build(allowed):
    def build(row, snap, window, out) -> None:
        from ..post.products import ranking, record_key

        elem, scope, d = _parse(row, allowed)
        sid = acis.station_for(row.data_source.target, record=True)
        entry = snap.extra[record_key(sid, elem, d, scope)]
        r = ranking(entry)
        head = acis.headline(r, scope)
        place = str(row.extra.get("label") or acis.label_for(sid, entry["name"])).upper()
        since = (entry["por_start"] or "")[:4]
        old_v, old_d = r.record
        prev_label = ("TIES" if r.tied else "PREVIOUS RECORD") if r.rank == 1 else "RECORD"
        src = lambda v, what, url: Sourced(v, acis.ELEMS[elem][0], f"RCC-ACIS {what}", url, f"{sid} {entry['name']}", entry["day"], entry["fetched"])  # noqa: E731
        prelim = _preliminary(d, entry["fetched"])
        e = {"id": f"wx_{row.id}", "type": "post_record", "t_in": window.t_in, "t_out": window.t_out, "headline": head, "place": place,
             "value": acis.amount_text(elem, r.value), "date": short(d, year=True), "prev_label": prev_label,
             "prev_value": acis.amount_text(elem, old_v), "prev_date": short(day(old_d), year=True),
             "since": f"RECORDS SINCE {since}" if since else "", "foot": "Observed station data · NOAA RCC-ACIS",
             "kind": {"pcpn": "rain", "snow": "snow", "maxt": "heat", "mint": "cold"}[elem], "tag": "PRELIMINARY" if prelim else "",
             "anchor": row.extra.get("anchor", "r")}
        out.events.append(e)
        out.report.add(row.id, f"{place} {elem} on {d}", e["value"], src(r.value, f"daily {elem}, observed", entry["day_url"]))
        out.report.add(row.id, f"{place} rank ({head})", head, src(r.rank, f"{acis.ELEMS[elem][2]} of the period of record to {d} (top {r.n})", entry["url"]))
        out.report.add(row.id, f"{place} {prev_label.lower()} ({old_d})", e["prev_value"], src(old_v, "period-of-record summary", entry["url"]))
        if since:
            out.report.add(row.id, f"{place} records begin", e["since"], src(entry["por_start"], "station valid date range", entry["url"]))
        out.credit(acis.CREDIT)
        out.shown[row.id] = [{"kind": "text", "text": acis.SOURCE_TEXT + (" (preliminary)" if prelim else "")}]
    return build


REC = ("pcpn", "snow", "maxt", "mint")
TEMP = ("maxt", "mint")
register(LayerType(name="record", products=[("acis", "record")], extra_keys=frozenset({"label", "anchor"}),
                   fetch=named(_record_fetch(REC)), build=named(_record_build(REC)), check=_record_check(REC),
                   about="where a day's rain, snow or temperature stands in the station's period of record (a record badge)"))
register(LayerType(name="temp_extreme", products=[("acis", "record")], extra_keys=frozenset({"label", "anchor"}),
                   fetch=named(_record_fetch(TEMP)), build=named(_record_build(TEMP)), check=_record_check(TEMP),
                   about="a heat (maxt) or cold (mint) record badge"))
