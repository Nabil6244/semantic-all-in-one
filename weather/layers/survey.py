"""Surveyed tornado tracks from the NWS Damage Assessment Toolkit (weather.news.dat): each track drawn as a line coloured by its EF
rating, the story's tornado labelled with the survey's own numbers ("EF2 · 115 MPH · 1.47 MI · 450 YD").

    tornado_tracks   dat:tracks@2026-10-10T12:00Z..2026-10-12T12:00Z#SC        every track surveyed in SC in that window
                     extra {"focus": "2026-10-11T10:05Z"}   label the track that began within 20 minutes of that time
                     extra {"labels": ["Barnwell Tornado"]} label tracks by the survey's name; "all" labels every track
                     extra legend (true), tz, draw_s (seconds to draw each track, 1.2)

The DAT calls its data preliminary (the official record is NCEI Storm Data), so the legend says SURVEYED · PRELIMINARY and the
numbers report marks every value preliminary. A window with no surveyed track in those states is not drawn (the row is left out
with that reason)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from ..news import dat
from ..news.rows import at, first_answer
from ..news.timeline import iso, parse_stamp, parse_window
from ..provenance import Sourced
from ..tz import parse_iso
from . import LayerType, register


def _states(row) -> List[str]:
    from ..cities import US_STATES

    st = [s.strip().upper() for s in (row.data_source.selector or "").split(",") if s.strip()]
    if not st or any(s not in US_STATES for s in st):
        raise ValueError("tornado_tracks names the states to search after #, like dat:tracks@2026-10-10T12:00Z..2026-10-12T12:00Z#SC")
    return st


def _key(row) -> str:
    return f"dat:tracks@{row.data_source.target}#{','.join(_states(row))}"


def _check(row) -> None:
    parse_window(row.data_source.target, max_hours=96)
    _states(row)
    f = row.extra.get("focus")
    if f is not None:
        parse_stamp(f)
    lab = row.extra.get("labels")
    if lab is not None and lab != "all" and not (isinstance(lab, list) and all(isinstance(x, str) for x in lab)):
        raise ValueError('tornado_tracks extra labels is "all" or a list of the surveys\' names')


def bbox_of(states: List[str]) -> List[float]:
    from ..intel.placegeo import state_boxes

    boxes = [b for s, b in state_boxes().items() if s in states]
    if not boxes:
        raise ValueError(f"no outline for {', '.join(states)}")
    return [round(min(b[0] for b in boxes), 3), round(min(b[1] for b in boxes), 3), round(max(b[2] for b in boxes), 3),
            round(max(b[3] for b in boxes), 3)]


def in_states(tracks: List[Dict[str, Any]], states: List[str]) -> List[Dict[str, Any]]:
    """The tracks that begin inside the states (an envelope also catches its neighbours' tracks)."""
    from ..intel.placegeo import state_of_point

    return [t for t in tracks if state_of_point(t["coords"][0][1], t["coords"][0][0]) in states]


def _fetch(row, ctx) -> None:
    key = _key(row)
    if key in ctx.snap.extra:
        return
    a, b = parse_window(row.data_source.target, max_hours=96)
    url = dat.lines_url(bbox_of(_states(row)), a, b)
    try:
        _u, text = first_answer([url], ctx.get_text, f"the NWS damage surveys of {row.data_source.target}")
        tracks = in_states(dat.parse_lines(text), _states(row))
    except ValueError as exc:
        raise ValueError(f"{at(row)}: {exc}") from None
    ctx.snap.extra[key] = {"url": url, "start": iso(a), "end": iso(b), "fetched": iso(ctx.now), "tracks": tracks}


def chosen(row, tracks: List[Dict[str, Any]]) -> List[int]:
    """Indexes of the tracks to label."""
    lab = row.extra.get("labels")
    if lab == "all":
        return list(range(len(tracks)))
    out = []
    if row.extra.get("focus"):
        t = parse_stamp(row.extra["focus"])
        near = [i for i, tr in enumerate(tracks) if tr["start"] and abs(parse_iso(tr["start"]) - t) <= timedelta(minutes=20)]
        out += near[:1]
    for name in lab or []:
        out += [i for i, tr in enumerate(tracks) if tr["name"].lower() == name.lower() and i not in out]
    return out


def _build(row, snap, window, out) -> None:
    v = snap.extra[_key(row)]
    tracks = in_states(v["tracks"], _states(row))   # again here: a snapshot saved before the filter keeps every envelope track
    if not tracks:
        raise ValueError(f"{at(row)}: the NWS damage surveys have no tornado track in {', '.join(_states(row))} in that window")
    draw_s = float(row.extra.get("draw_s", 1.2))
    t0 = window.t_in + 0.3
    step = min(0.5, max(0.1, (window.t_out - t0 - draw_s) / max(1, len(tracks)) / 2))
    picked = chosen(row, tracks)
    order = picked + [i for i in range(len(tracks)) if i not in picked]   # the labelled tracks draw first: the story's tornado leads
    when = {i: round(t0 + k * step, 3) for k, i in enumerate(order)}
    for i, tr in enumerate(tracks):
        out.fills.append({"id": f"wx_{row.id}_t{i}", "type": "line", "kind": "border_trace", "coords": tr["coords"],
                          "color": dat.EF_COLORS[tr["ef"]], "width": 7, "t_in": window.t_in, "t_out": window.t_out,
                          "t_draw": when[i], "draw_s": draw_s})
    pts = []
    for i in picked:
        tr = tracks[i]
        mid = tr["coords"][len(tr["coords"]) // 2]
        text = dat.label(tr)
        pts.append({"lon": mid[0], "lat": mid[1], "color": dat.EF_COLORS[tr["ef"]], "label": text, "at": round(when[i] + draw_s, 3), "size": 9})
        out.report.add(row.id, f"NWS survey {tr['name'] or tr['wfo'] + ' track'} ({tr['start']}..{tr['end']}, preliminary)", text,
                       Sourced(text, "", "NWS damage survey (DAT), preliminary", v["url"], f"{tr['wfo']} {tr['coords'][0][1]}N {abs(tr['coords'][0][0])}W",
                               tr["start"], v["fetched"]))
    if pts:
        out.events.append({"id": f"wx_{row.id}_labels", "type": "storm_points", "t_in": window.t_in, "t_out": window.t_out, "points": pts,
                           "name": "SURVEYED TORNADO"})
    if row.extra.get("legend", True):
        efs = sorted({tr["ef"] for tr in tracks}, key=lambda e: list(dat.EF_COLORS).index(e))
        items = [{"label": f"{e} TORNADO TRACK", "color": dat.EF_COLORS[e]} for e in efs] + [{"label": "SURVEYED · PRELIMINARY", "color": "#FFFFFF"}]
        out.events.append({"id": f"wx_{row.id}_legend", "type": "alert_legend", "t_in": window.t_in, "t_out": window.t_out, "items": items})
    out.report.add(row.id, f"surveyed tornado tracks in {', '.join(_states(row))} (preliminary)", str(len(tracks)),
                   Sourced(len(tracks), "tracks", "NWS damage survey (DAT), preliminary", v["url"], ",".join(_states(row)), v["end"], v["fetched"]))
    out.credit(dat.CREDIT)
    out.shown[row.id] = [{"kind": "text", "text": "Tornado surveys: NWS Damage Assessment Toolkit, preliminary"}]


register(LayerType(name="tornado_tracks", products=[("dat", "tracks")], extra_keys=frozenset({"focus", "labels", "legend", "tz", "draw_s"}),
                   fetch=_fetch, build=_build, check=_check,
                   about="NWS-surveyed tornado tracks coloured by EF rating, the story's tornado labelled (preliminary)"))
