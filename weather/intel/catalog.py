"""The graphic catalogue: every graphic the engine can propose, what narration calls for it, what evidence it needs, how it is
built from the resolved event, and how it is checked once its data is fetched.

A GraphicSpec never names a beat: placement (weather.intel.planner) finds the beat whose words discuss the spec's topics, then
asks the spec to build its drafts FOR that beat (a cone's advisory follows the time that beat says; a rain-total chart shows
the gauges that beat names). A spec that cannot be built raises Skip with the reason, which the report lists.

Every spec renders through an existing weather layer type (weather/layers/*): the engine adds no renderer of its own."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple  # noqa: F401

from ..news.timeline import STATE_NAMES
from .context import EventContext, local_to_utc, seg_day
from .understand import Segment, split_sentences, tokens

UTC = timezone.utc
CODE_STATE = {v: k.title() for k, v in STATE_NAMES.items()}
DATA_KINDS = ("loop", "counter", "data")


class Skip(Exception):
    """A graphic that cannot be made; `local` = only for this beat (placement may try the next one)."""

    def __init__(self, reason: str, local: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.local = local


@dataclass
class Draft:
    spec: str
    id: str
    type: str
    data_source: str = ""
    place: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    hold: Optional[float] = None
    until: str = "beat_end"
    beat: str = ""
    vo_anchor: str = ""
    companion_of: str = ""
    why: str = ""
    entity: str = ""
    kind: str = "data"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class GraphicSpec:
    key: str
    layer: str
    title: str
    categories: Tuple[str, ...]
    topics: Dict[str, float]
    kind: str  # loop | counter | data | label | headline | source
    min_s: float
    build: Callable[["Planner", Segment], List[Draft]]
    needs: str
    fallback: str
    min_score: float = 1.0
    covers: Tuple[str, ...] = ()  # layer types in the user's plan that already give the viewer this graphic
    per_entity: Optional[Callable[["Planner"], List[Tuple[str, List[str]]]]] = None  # [(entity, seg ids that name it)]
    verify: Optional[Callable[[Draft, Any], Optional[str]]] = None  # (draft, snapshot) -> reason to drop it
    priority: int = 50  # lower first (claims its beat first)
    must: Tuple[str, ...] = ()  # at least one of these topics must be in the beat's words (not only related ones)
    local: bool = False  # a small-scale graphic (a 1-mile track): beats whose camera is close to the event are preferred
    repeat_after_s: float = 0.0  # > 0: shown again (up to twice) on a later beat that discusses it as much, this long after the last time


# ---- helpers the builders share ------------------------------------------------------------------------------------------------

def state_name(code: str) -> str:
    return CODE_STATE.get(code, code)


def stamp(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def times_in(p: "Planner", seg: Segment) -> List[datetime]:
    """The clock times a beat says, on the day it talks about, in UTC."""
    day = seg_day(p.ctx.u, p.seg_ids, seg.id, p.ctx.year) or p.ctx.main_day
    if not day:
        return []
    return [local_to_utc(day, t.hour, t.minute, t.zone, p.ctx.tz) for t in p.ctx.u.times if t.seg == seg.id]


def dates_in(p: "Planner", seg: Segment) -> List[str]:
    return [d.day for d in p.ctx.u.dates if d.seg == seg.id and d.day and not d.relative and (not p.ctx.year or int(d.day[:4]) == p.ctx.year)]


def has_words(seg: Segment, *phrases: str) -> bool:
    low = " " + " ".join(tokens(seg.text)) + " "
    return any(" " + " ".join(tokens(ph)) + " " in low for ph in phrases)


def need_storm(p: "Planner") -> None:
    if p.ctx.storm is None:
        raise Skip("no storm was identified in the NHC records" + (f" ({p.ctx.storm_note})" if p.ctx.storm_note else ""))


def need_day(p: "Planner") -> str:
    if not p.ctx.main_day:
        raise Skip("the event's date is unknown (the script never says it)")
    return p.ctx.main_day


def warn_types_said(seg: Segment, default: Sequence[str]) -> List[str]:
    said = []
    for words, code in (("extreme wind", "EW"), ("tornado warning", "TO"), ("tornado warnings", "TO"), ("severe thunderstorm warning", "SV"),
                        ("severe thunderstorm warnings", "SV"), ("flash flood warning", "FF"), ("flash flood warnings", "FF")):
        if has_words(seg, words) and code not in said:
            said.append(code)
    return said or list(default)


# ---- hurricanes ----------------------------------------------------------------------------------------------------------------

def synoptic(t: datetime) -> Optional[datetime]:
    """A said time on a best-track step (00/06/12/18 UTC), when it is within 45 minutes of one."""
    base = t.replace(minute=0, second=0, microsecond=0)
    cand = min((base.replace(hour=h) + timedelta(days=d) for h in (0, 6, 12, 18) for d in (-1, 0, 1)), key=lambda c: abs(c - t))
    return cand if abs(cand - t) <= timedelta(minutes=45) else None


def b_best_track(p: "Planner", seg: Segment) -> List[Draft]:
    need_storm(p)
    s = p.ctx.storm
    if s.year < 2008 and s.basin != "AL":
        raise Skip(f"NHC's GIS best track archive does not hold {s.id}")
    said = [x for x in (synoptic(t) for t in times_in(p, seg)) if x is not None]
    extra = {"label_times": [stamp(t) for t in dict.fromkeys(said)][:3]} if said else {}
    why = f"the narration describes {s.name.title()}'s path or strength; NHC best track of {s.id}"
    if said:
        why += f", labelled at the times the beat says ({', '.join(extra['label_times'])})"
    return [Draft("hurricane.best_track", "auto_best_track", "storm_track", f"nhc:track@{s.id}#best", place=p.place_name(), extra=extra,
                  why=why)]


def b_storm_stats(p: "Planner", seg: Segment) -> List[Draft]:
    need_storm(p)
    s = p.ctx.storm
    if not p.ctx.peak:
        if s.status == "ARCHIVE":
            raise Skip(f"{s.name.title()} ({s.id}) could not be read from NHC's final best track (HURDAT2)")
        return [Draft("hurricane.stats", "auto_storm_stats", "storm_stats", f"nhc:stats@{s.id}#working", place=p.place_name(),
                      extra={"anchor": "l"}, why=f"{s.name.title()} is from the current season: peak and lowest pressure from NHC's WORKING "
                      "best track, labelled preliminary (HURDAT2 is published each spring; the working track marks no landfalls)")]
    extra: Dict[str, Any] = {"anchor": card_side(p, seg)}
    if p.ctx.moment is not None and p.ctx.landfalls:
        n = next((i for i, lf in enumerate(p.ctx.landfalls, 1) if lf["time"].startswith(p.ctx.moment.strftime("%Y-%m-%dT%H:%M"))), None)
        if n:
            extra["landfall"] = n
    return [Draft("hurricane.stats", "auto_storm_stats", "storm_stats", f"nhc:stats@{s.id}", place=p.place_name(), extra=extra,
                  why=f"the narration discusses {s.name.title()}'s strength; peak, lowest pressure and landfall from HURDAT2")]


def card_side(p: "Planner", seg: Segment) -> str:
    """The side of the frame a side card goes on: away from the storm's track as the beat's camera sees it (more of the track west
    of the camera's centre -> the card goes right). With no camera or no track, the left."""
    if not seg.cam or not p.ctx.track:
        return "l"
    try:
        from hybrid.geo import resolve as geo

        c = geo(seg.cam)
    except Exception:
        return "l"
    near = [(la, lo) for la, lo in p.ctx.track if abs(lo - c.lon) <= 22 and abs(la - c.lat) <= 14]
    west = sum(1 for _la, lo in near if lo < c.lon)
    return "r" if west > len(near) - west else "l"


def b_landfall_marker(p: "Planner", seg: Segment) -> List[Draft]:
    need_storm(p)
    if p.ctx.moment is None or not p.ctx.landfalls:
        raise Skip("no landfall in NHC's final best track to mark")
    lf = next((x for x in p.ctx.landfalls if x["time"].startswith(p.ctx.moment.strftime("%Y-%m-%dT%H:%M"))), None)
    if lf is None:
        raise Skip("the story's landfall time is not a landfall record of the best track")
    return [Draft("hurricane.landfall", "auto_landfall", "place_label", place=f"{lf['lat']:.2f},{lf['lon']:.2f}", extra={"text": "LANDFALL"},
                  kind="label", why=f"the landfall the story is about: HURDAT2 {lf['time']} at {lf['lat']}, {lf['lon']}")]


def b_cone(p: "Planner", seg: Segment) -> List[Draft]:
    need_storm(p)
    s = p.ctx.storm
    if s.year < 2008:
        raise Skip(f"NHC's GIS advisory archive starts in 2008 ({s.id} is older)")
    said = times_in(p, seg)
    if said:
        target, how = said[0], "the advisory time the beat says"
    elif p.ctx.moment is not None:
        target, how = p.ctx.moment - timedelta(hours=12), "about 12 hours before landfall"
    elif p.ctx.peak:
        target, how = datetime.strptime(p.ctx.peak["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC), "the storm's peak"
    else:
        raise Skip("no time to choose an advisory for (no landfall, peak or time in the narration)")
    adv, issued, notes = p.advisory(target)
    p.notes += notes
    if adv is None:
        raise Skip(f"no NHC advisory of {s.id} could be matched to {stamp(target)}")
    why = f"advisory {adv} of {s.id}, issued {stamp(issued)}: the last one at or before {stamp(target)} ({how})"
    cone = Draft("hurricane.cone", "auto_cone", "storm_cone", f"nhc:cone@{s.id}#{adv}", place=p.place_name(), why=why)
    track = Draft("hurricane.cone", "auto_cone_track", "storm_track", f"nhc:track@{s.id}#{adv}", place=p.place_name(),
                  extra={"labels": 3}, companion_of="auto_cone", why="the forecast track and points of the same advisory")
    return [cone, track]


def b_satellite_loop(p: "Planner", seg: Segment) -> List[Draft]:
    need_storm(p)
    s = p.ctx.storm
    if s.year < 2012:
        raise Skip("the daily true-colour satellite archive (VIIRS) starts in 2012")
    end = p.ctx.local(p.ctx.moment).date() if p.ctx.moment else (date.fromisoformat(p.ctx.main_day) if p.ctx.main_day else None)
    if end is None:
        raise Skip("no landfall or event day to end the satellite loop on")
    start_storm = datetime.fromisoformat(s.start.replace("Z", "+00:00")).date() if s.start else end - timedelta(days=4)
    start = max(start_storm, end - timedelta(days=5))
    if (end - start).days < 1:
        start = end - timedelta(days=1)
    return [Draft("hurricane.satellite_loop", "auto_sat_loop", "satellite_loop", f"gibs:truecolor_loop@{start}..{end}", place=p.place_name(),
                  why=f"one NASA true-colour picture a day, {start} to {end}, as the narration describes the storm from space", kind="loop")]


def _radar_window(p: "Planner", seg: Segment, before_h: float, after_h: float) -> Tuple[datetime, datetime, str]:
    said = sorted(times_in(p, seg))
    if len(said) >= 2 and timedelta(hours=1) <= said[-1] - said[0] <= timedelta(hours=24):
        return said[0], said[-1], "the times the beat says"
    w = p.ctx.window(before_h, after_h)
    if w is None:
        raise Skip("the event's date is unknown, so there is no radar window")
    return w[0], w[1], p.ctx.moment_note or "the storm day (10 UTC to 04 UTC)"


def b_radar(p: "Planner", seg: Segment) -> List[Draft]:
    hurricane = p.ctx.category in ("hurricane", "tropical_storm")
    a, b, how = _radar_window(p, seg, 4 if hurricane else 2, 4 if hurricane else 2)
    if a < datetime(2010, 11, 13, tzinfo=UTC):
        raise Skip("the IEM N0Q radar archive starts on 2010-11-13")
    win = f"{stamp(a)}..{stamp(b)}"
    types = warn_types_said(seg, ("TO", "EW") if hurricane else ("FF",) if p.ctx.category in ("flood", "heavy_rain") else ("TO", "SV"))
    st = {"states": p.ctx.states[:3]} if p.ctx.states else {}
    radar = Draft("radar.loop", "auto_radar", "radar", f"iem:radar@{win}#n0q", place=p.place_name(), kind="loop",
                  why=f"radar mosaic {win} ({how})", entity="said" if how == "the times the beat says" else "")
    warn = Draft("radar.loop", "auto_warnings", "warnings_archive", f"iem:warnings@{win}#{','.join(types)}", place=p.place_name(),
                 extra=dict(st), companion_of="auto_radar", why=f"NWS {', '.join(types)} warnings in the same window, each from its issue time")
    return [radar, warn]


def b_warning_counter(p: "Planner", seg: Segment) -> List[Draft]:
    if not has_words(seg, "warning", "warnings"):
        raise Skip("this beat counts something, but not warnings", local=True)
    types = warn_types_said(seg, ())
    if len(types) != 1:
        raise Skip("the beat does not name one warning type to count", local=True)
    if not any(m.seg == seg.id and m.unit == "count" for m in p.ctx.u.measurements):
        raise Skip("the beat does not say how many warnings there were", local=True)
    said = sorted(times_in(p, seg))
    if len(said) >= 2 and said[-1] > said[0]:
        a, b = said[0], said[-1]
    else:   # the whole local day the beat talks about
        from zoneinfo import ZoneInfo

        day = date.fromisoformat(seg_day(p.ctx.u, p.seg_ids, seg.id, p.ctx.year) or need_day(p))
        a = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(p.ctx.tz)).astimezone(UTC)
        b = a + timedelta(hours=24)
    st = {"states": p.ctx.states[:3]} if p.ctx.states else {}
    return [Draft("warnings.counter", "auto_warn_count", "counter", f"iem:warnings@{stamp(a)}..{stamp(b)}#{types[0]}", place=p.place_name(),
                  extra={**st, "anchor": "tr"}, kind="counter", why=f"the narration counts {types[0]} warnings; IEM archive {stamp(a)}..{stamp(b)}")]


# ---- severe weather ------------------------------------------------------------------------------------------------------------

def _report_kinds(p: "Planner") -> str:
    return "tornado" if p.ctx.category == "tornado" or "tornado" in p.ctx.u.hazards[:1] else "tornado,wind,hail"


def b_reports(p: "Planner", seg: Segment) -> List[Draft]:
    if any(d.spec in ("severe.survey", "severe.survey_overview") for d in p.drafts):
        raise Skip("the NWS-surveyed tracks are shown instead (surveys rate each tornado; reports are preliminary and repeat)")
    day = p.ctx.conv_day or need_day(p)
    if day < "2004-01-01":
        raise Skip("SPC's filtered storm-report files start in 2004")
    extra = {"states": p.ctx.states[:3]} if p.ctx.states else {}
    why = f"SPC preliminary reports of the convective day {day}"
    if p.ctx.moment is not None and day != p.ctx.local(p.ctx.moment).date().isoformat():
        why += f" (the event at {stamp(p.ctx.moment)} is before 12 UTC, so it is in the previous day's file)"
    return [Draft("severe.reports", "auto_reports", "storm_reports", f"spc:reports@{day}#{_report_kinds(p)}", place=p.place_name(),
                  extra=extra, why=why)]


def b_report_counter(p: "Planner", seg: Segment) -> List[Draft]:
    day = p.ctx.conv_day or need_day(p)
    kind = "tornado" if "tornado" in _report_kinds(p) else "wind"
    extra = {"anchor": "tr", **({"states": p.ctx.states[:3]} if p.ctx.states else {})}
    return [Draft("severe.counter", "auto_report_count", "counter", f"spc:reports@{day}#{kind}", place=p.place_name(), extra=extra,
                  kind="counter", why=f"the narration counts {kind} reports; SPC preliminary reports of {day}")]


def survey_window(p: "Planner") -> Tuple[datetime, datetime]:
    """The DAT search window: the convective day of the event and the next one (surveys of a weekend's storms)."""
    day = p.ctx.conv_day or need_day(p)
    a = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(hours=12)
    return a, a + timedelta(hours=48)


def b_survey(p: "Planner", seg: Segment) -> List[Draft]:
    if not p.ctx.states:
        raise Skip("no state to search the NWS damage surveys in")
    a, b = survey_window(p)
    tracks = p.surveys(a, b)
    if not tracks:
        raise Skip(f"the NWS damage surveys (DAT) hold no tornado track in {', '.join(p.ctx.states[:3])} for {a:%Y-%m-%d}..{b:%Y-%m-%d}")
    extra: Dict[str, Any] = {}
    focus = None
    if p.ctx.moment is not None:
        from ..tz import parse_iso

        focus = next((t for t in tracks if t["start"] and abs(parse_iso(t["start"]) - p.ctx.moment) <= timedelta(minutes=20)), None)
        if focus is not None:
            extra["focus"] = stamp(p.ctx.moment)
    why = "NWS-surveyed tornado tracks (DAT, preliminary)"
    if focus is not None:
        from ..news.dat import label

        why += f"; the story's tornado: {label(focus)}, {focus['start']}..{focus['end']}"
    return [Draft("severe.survey", "auto_survey", "tornado_tracks", f"dat:tracks@{stamp(a)}..{stamp(b)}#{','.join(p.ctx.states[:3])}",
                  place=p.place_name(), extra=extra, why=why)]


def b_survey_overview(p: "Planner", seg: Segment) -> List[Draft]:
    if not p.ctx.states:
        raise Skip("no state to search the NWS damage surveys in")
    a, b = survey_window(p)
    tracks = p.surveys(a, b)
    words = " ".join(tokens(seg.text))
    named = [t["name"] for t in tracks if t["name"] and any(w in words for w in tokens(t["name"]) if len(w) > 3 and w not in ("tornado", "county", "northern",
             "southern", "eastern", "western", "central"))]
    if not named:
        raise Skip("the beat names none of the surveyed tornadoes", local=True)
    return [Draft("severe.survey_overview", "auto_survey_wide", "tornado_tracks", f"dat:tracks@{stamp(a)}..{stamp(b)}#{','.join(p.ctx.states[:3])}",
                  place=p.place_name(), extra={"labels": named[:4]},
                  why=f"the beat names other surveyed tornadoes ({', '.join(named[:4])}); NWS damage surveys (DAT, preliminary)")]


def b_watch_warning(p: "Planner", seg: Segment) -> List[Draft]:
    if not (has_words(seg, "watch") and has_words(seg, "warning")):
        raise Skip("the beat does not compare a watch with a warning", local=True)
    return [Draft("severe.watch_warning", "auto_watch_warning", "explainer", extra={"template": "watch_warning"},
                  why="the narration explains a tornado watch versus a tornado warning; NWS definitions")]


def b_outlook(p: "Planner", seg: Segment) -> List[Draft]:
    day = p.ctx.conv_day or need_day(p)
    return [Draft("severe.outlook", "auto_outlook", "spc_outlook", f"spc:outlook@{day}#day1", place=p.place_name(),
                  why=f"the narration discusses the outlook; SPC day 1 outlook valid {day}")]


# ---- rain and floods -----------------------------------------------------------------------------------------------------------

def _span(p: "Planner") -> Tuple[date, date]:
    sp = p.ctx.span_days()
    if sp is None:
        if p.ctx.moment is not None:
            d = p.ctx.local(p.ctx.moment).date()
            return d, d + timedelta(days=2)
        raise Skip("the event's dates are unknown")
    a, b = sp
    if p.ctx.moment is not None:
        a = min(a, p.ctx.local(p.ctx.moment).date())
    return a, b


def b_rain_map(p: "Planner", seg: Segment) -> List[Draft]:
    said = sorted(dates_in(p, seg))
    a, b = (date.fromisoformat(said[0]), date.fromisoformat(said[-1])) if len(said) >= 2 else _span(p)
    if (b - a).days < 1:
        b = a + timedelta(days=1)
    if (b - a).days > 10:
        a = b - timedelta(days=10)
    if a < date(2015, 1, 1):
        raise Skip("the MRMS radar-rainfall archive starts in 2015")
    if p.ctx.focus is None:
        raise Skip("no place to centre the rain map on")
    from .placegeo import bbox_around

    bbox = bbox_around(*p.ctx.focus)
    return [Draft("rain.map", "auto_rain_map", "rain_map", f"mrms:total@{a}..{b}", extra={"bbox": bbox, "peak": True, "opacity": 0.72},
                  why=f"MRMS radar-estimated rain {a} to {b} around {p.ctx.focus_name or 'the story'} (an estimate, labelled so)")]


ACIS_NAMES = {  # words a narrator says -> the ACIS station (weather.post.acis LABELS / PLACES)
    "port arthur": "BPT", "beaumont": "BPT", "houston hobby": "HOU", "hobby": "HOU", "houston intercontinental": "IAH", "intercontinental": "IAH",
    "galveston": "GLS", "sugar land": "SGR", "conroe": "CXO", "angleton": "LBX", "ellington": "EFD", "lake charles": "LCH",
    "corpus christi": "CRP", "victoria": "VCT", "new orleans": "MSY", "miami": "MIA", "tampa": "TPA", "dallas": "DFW", "austin": "AUS",
    "college station": "CLL", "chicago": "ORD", "phoenix": "PHX", "las vegas": "LAS", "denver": "DEN", "atlanta": "ATL",
    "nashville": "BNA", "asheville": "AVL", "sacramento": "SAC", "seattle": "SEA", "portland": "PDX", "los angeles": "LAX",
    "new york": "NYC", "houston": "IAH",
}


def stations_said(seg: Segment) -> List[str]:
    low = " " + " ".join(tokens(seg.text)) + " "
    hits = []
    for words in sorted(ACIS_NAMES, key=len, reverse=True):
        for m in re.finditer(" " + re.escape(words) + " ", low):
            hits.append((m.start(), ACIS_NAMES[words]))
        low = low.replace(" " + words + " ", " " + "#" * len(words) + " ")
    out = []
    for _pos, sid in sorted(hits):
        if sid not in out:
            out.append(sid)
    return out


def b_rain_totals(p: "Planner", seg: Segment) -> List[Draft]:
    sids = stations_said(seg)
    if not sids:
        raise Skip("the beat names no place with a known rain gauge", local=True)
    said = sorted(dates_in(p, seg))
    a, b = (date.fromisoformat(said[0]), date.fromisoformat(said[-1])) if len(said) >= 2 else _span(p)
    if len(sids) == 1:
        return [Draft("rain.totals", "auto_rain_total", "rain_total", f"acis:pcpn_total@{sids[0]}#{a}..{b}", extra={"side": "l"},
                      why=f"observed rain at {sids[0]}, {a} to {b} (RCC-ACIS)")]
    return [Draft("rain.totals", "auto_rain_totals", "rain_total", f"acis:pcpn_total@{'|'.join(sids[:6])}#{a}..{b}",
                  extra={"title": "RAIN GAUGE TOTALS"}, why=f"observed rain at the gauges the beat names ({', '.join(sids[:6])}), {a} to {b}")]


def b_record(p: "Planner", seg: Segment) -> List[Draft]:
    from ..post.acis import PLACES

    said = dates_in(p, seg)
    if not said:
        raise Skip("the beat names no day for the record", local=True)
    elem = "maxt" if has_words(seg, "hottest", "heat", "degrees") else "mint" if has_words(seg, "coldest") else "snow" if has_words(seg, "snowiest", "snow") else "pcpn"
    cities = [pl for pl in p.ctx.u.places if pl.seg == seg.id and pl.kind == "city" and f"{pl.name.lower()},{pl.state}" in PLACES]
    if not cities:
        raise Skip("the beat names no city with a long station record", local=True)
    c = cities[0]
    typ = "temp_extreme" if elem in ("maxt", "mint") else "record"
    return [Draft("record", "auto_record", typ, f"acis:record@{c.name},{c.state}#{elem}#{said[0]}", place=f"{c.name}, {c.state}",
                  why=f"where {said[0]} stands in {c.name}'s period of record ({elem}, RCC-ACIS ranking)")]


def rivers(p: "Planner") -> List[Tuple[str, List[str]]]:
    out: Dict[str, List[str]] = {}
    for pl in p.ctx.u.places_of("river"):
        out.setdefault(pl.name, [])
    for pl in p.ctx.u.places:
        if pl.kind == "river":
            out[pl.name].append(pl.seg)
    return list(out.items())


def b_river_crest(p: "Planner", seg: Segment, entity: str = "") -> List[Draft]:
    sentence = next((s for s in split_sentences(seg.text) if entity.split()[0].lower() in s.lower()), seg.text)
    gauge, how = p.gauge(entity, sentence + " " + seg.text)
    if gauge is None:
        raise Skip(how)
    a, b = _span(p)
    a, b = a, max(b, a + timedelta(days=4)) + timedelta(days=3)
    if a < date(2007, 10, 1):
        raise Skip("USGS instantaneous values start about October 2007")
    n = len([d for d in p.drafts if d.spec == "river.crest"])
    extra = {"chart": True, "anchor": "l", "side": "b"} if n == 0 else {"side": "t"}
    slug = re.sub(r"[^a-z0-9]+", "_", entity.lower()).strip("_")
    return [Draft("river.crest", f"auto_crest_{slug}", "river_crest", f"usgs:crest@{gauge.site}#{a}..{b}", extra=extra, entity=entity,
                  why=f"{how}; the highest gage height {a} to {b}")]


def b_ero(p: "Planner", seg: Segment) -> List[Draft]:
    day = seg_day(p.ctx.u, p.seg_ids, seg.id, p.ctx.year) or (p.ctx.local(p.ctx.moment).date().isoformat() if p.ctx.moment else None) or need_day(p)
    return [Draft("rain.ero", "auto_ero", "wpc_ero", f"wpc:ero@{day}#day1", place=p.place_name(),
                  why=f"the narration discusses the rain outlook; WPC day 1 excessive rainfall outlook of {day}")]


def b_before_after(p: "Planner", seg: Segment) -> List[Draft]:
    said = sorted(set(dates_in(p, seg)))
    if len(said) >= 2:
        a, b = date.fromisoformat(said[0]), date.fromisoformat(said[-1])
        how = "the two days the beat names"
    else:
        s0, s1 = _span(p)
        a, b = s0 - timedelta(days=3), s1 + timedelta(days=1)
        how = "three days before the event and the day after it"
    product = "falsecolor" if p.ctx.category in ("flood", "heavy_rain") or has_words(seg, "false colour", "false color", "water shows") else "truecolor"
    return [Draft("satellite.before_after", "auto_before_after", "before_after", f"gibs:{product}@{a}|{b}", extra={"crossfade": 1.5},
                  kind="loop", why=f"NASA {product} pictures of {a} and {b} ({how})")]


def b_timeline(p: "Planner", seg: Segment) -> List[Draft]:
    a, b = _span(p)
    a, b = a - timedelta(days=1), max(b, a + timedelta(days=2))
    marks = []
    if p.ctx.storm is not None and p.ctx.landfalls:
        # landfalls inside the timeline's days (#n counts them there); one a day at most, so close ones do not crowd the line
        n, last = 0, None
        for lf in p.ctx.landfalls:
            if a.isoformat() <= lf["time"][:10] <= b.isoformat():
                n += 1
                t = datetime.fromisoformat(lf["time"].replace("Z", "+00:00"))
                if (last is None or t - last >= timedelta(hours=24)) and len(marks) < 2:
                    marks.append({"from": f"nhc:landfall@{p.ctx.storm.id}#{n}"})
                    last = t
    from ..post.acis import PLACES

    city = next((pl for pl in p.ctx.u.places if pl.kind == "city" and f"{pl.name.lower()},{pl.state}" in PLACES), None)
    if city is not None:
        marks.append({"from": f"acis:peak_day@{city.name},{city.state}#{a}..{b}"})
    crest = next((d for d in p.drafts if d.spec == "river.crest"), None)
    if crest is not None:
        site = crest.data_source.split("@")[1].split("#")[0]
        marks.append({"from": f"usgs:crest@{site}#{crest.data_source.split('#')[1]}", "title": f"{crest.entity.upper()} CREST"})
    if len(marks) < 2:
        raise Skip("fewer than two dated marks could be read from the data (landfall, wettest day, river crest)")
    title = (f"{p.ctx.storm.name} TIMELINE" if p.ctx.storm else "EVENT TIMELINE")
    return [Draft("timeline", "auto_timeline", "event_timeline", f"post:timeline@{a}..{b}", extra={"title": title, "marks": marks[:6]},
                  why=f"dated marks from the data: {', '.join(m['from'] for m in marks)}")]


# ---- forecast (current) --------------------------------------------------------------------------------------------------------

def _forecast_city(p: "Planner", seg: Segment):
    from ..cities import find_city

    for pl in [x for x in p.ctx.u.places if x.seg == seg.id and x.kind == "city"] + p.ctx.u.places_of("city"):
        try:
            return find_city(f"{pl.name}, {pl.state}")
        except KeyError:
            continue
    raise Skip("the narration names no city Weather has forecasts for", local=True)


def b_forecast_strip(p: "Planner", seg: Segment) -> List[Draft]:
    if p.ctx.historical:
        raise Skip("a forecast strip shows today's forecast; this story is about a past event")
    if not p.contact:
        raise Skip("the NWS asks for a contact before its forecasts can be fetched (Settings > General > Weather)")
    c = _forecast_city(p, seg)
    return [Draft("forecast.strip", "auto_forecast_strip", "forecast_strip", f"nws:forecast@{c.key}#day1-5", place=c.key,
                  why=f"the narration discusses the forecast for {c.key}; NWS forecast")]


def b_now_card(p: "Planner", seg: Segment) -> List[Draft]:
    if p.ctx.historical:
        raise Skip("current conditions are for today's video; this story is about a past event")
    if not p.contact:
        raise Skip("the NWS asks for a contact before its observations can be fetched")
    c = _forecast_city(p, seg)
    return [Draft("forecast.now", "auto_now_card", "now_card", f"nws:obs@{c.key}", place=c.key, why=f"current conditions at {c.key} (NWS)")]


def b_alerts_now(p: "Planner", seg: Segment) -> List[Draft]:
    if p.ctx.historical:
        raise Skip("active alerts are for today's video; past warnings come from the archive")
    if not p.contact or not p.ctx.states:
        raise Skip("no NWS contact or no state named")
    st = p.ctx.states[0]
    return [Draft("forecast.alerts", "auto_alerts", "alert_area", f"nws:alerts@{st}", place=st, why=f"active NWS alerts in {st}")]


def b_winter(p: "Planner", seg: Segment) -> List[Draft]:
    raise Skip("snow, ice and wind-chill graphics are not built yet (planned for phase 5)")


# ---- broadcast compositions ----------------------------------------------------------------------------------------------------

KICKERS = {"hurricane": "HURRICANE", "tropical_storm": "TROPICAL STORM", "tornado": "TORNADO", "severe": "SEVERE STORMS",
           "flood": "FLOODING", "heavy_rain": "HEAVY RAIN", "heat": "HEAT", "winter": "WINTER STORM", "forecast": "FORECAST"}


TITLE_LAYERS = ("hud_title", "tp_title", "title", "lower_third")


def b_headline(p: "Planner", seg: Segment) -> List[Draft]:
    if any(t in TITLE_LAYERS for t in seg.layers):
        raise Skip("the beat plan already opens with its own title card on that beat")
    c = p.ctx
    kicker = f"{KICKERS.get(c.storm.max_type == 'TS' and 'tropical_storm' or 'hurricane')} {c.storm.name}" if c.storm and c.storm_role == "primary" \
        else KICKERS.get(c.category, "WEATHER")
    county = next((pl for pl in c.u.places_of("county") if pl.state), None)
    if county is not None:
        title = f"{county.name}, {state_name(county.state)}"
    elif c.states:
        title = " AND ".join(state_name(s) for s in c.states[:2])
    else:
        raise Skip("no place to name in the headline")
    sub = ""
    if c.main_day:
        d = date.fromisoformat(c.main_day)
        sub = f"{d:%A}, {d:%B} {d.day}, {d.year}"
    tone = {"news": "news", "post": "post"}.get(p.fmt, "news")
    extra = {"kicker": re.sub(r"\d", "", kicker).upper().strip(), "title": re.sub(r"\d", "", title).upper().strip(), "tone": tone}
    if sub:
        extra["sub"] = sub.upper()
    return [Draft("broadcast.headline", "auto_headline", "headline", extra=extra, hold=7.0, until="beat_end", kind="headline",
                  why="the opening lower-third names the event, the place and the day")]


def counties(p: "Planner") -> List[Tuple[str, List[str]]]:
    out: Dict[str, List[str]] = {}
    for pl in p.ctx.u.places:
        if pl.kind == "county" and pl.lat is not None and (not p.ctx.states or pl.state in p.ctx.states):
            out.setdefault(pl.name, []).append(pl.seg)
    return list(out.items())[:3]


def b_place_label(p: "Planner", seg: Segment, entity: str = "") -> List[Draft]:
    pl = next(x for x in p.ctx.u.places if x.kind == "county" and x.name == entity and x.lat is not None)
    slug = re.sub(r"[^a-z0-9]+", "_", entity.lower()).strip("_")
    return [Draft("broadcast.place_label", f"auto_label_{slug}", "place_label", place=f"{pl.lat:.2f},{pl.lon:.2f}",
                  extra={"text": entity.replace(" County", " County")}, kind="label", entity=entity,
                  why=f"{entity} is named here; the label marks the county's centre on the map")]


# ---- verification after the data is fetched -----------------------------------------------------------------------------------

def v_reports(d: Draft, snap) -> Optional[str]:
    from ..layers.severe import report_kinds, reports_key

    v = snap.extra.get(reports_key(d.data_source.split("@")[1].split("#")[0]))
    if not v:
        return "the SPC reports were not fetched"
    kinds = report_kinds(d.data_source.split("#")[1] if "#" in d.data_source else "")
    states = set(d.extra.get("states") or [])
    n = sum(1 for r in v["reports"] if r["kind"] in kinds and (not states or r.get("state") in states))
    if n == 0:
        return f"SPC lists no {'/'.join(kinds)} reports{' in ' + ', '.join(sorted(states)) if states else ''} on that convective day"
    return None


def v_warnings(d: Draft, snap) -> Optional[str]:
    from ..layers.severe import warning_types, warnings_key
    from ..tz import parse_iso

    target = d.data_source.split("@")[1].split("#")[0]
    v = snap.extra.get(warnings_key(target, d.extra.get("states", [])))
    if not v:
        return "the warnings archive was not fetched"
    kinds = warning_types(d.data_source.split("#")[1])
    a, b = parse_iso(v["start"]), parse_iso(v["end"])
    n = sum(1 for w in v["warnings"] if w["phenomena"] in kinds and parse_iso(w["ends"]) > a and parse_iso(w["starts"]) < b)
    if n == 0:
        return f"no {', '.join(kinds)} warnings were in effect in that window{' in ' + ', '.join(d.extra.get('states', [])) if d.extra.get('states') else ''}"
    return None


def v_counter(d: Draft, snap) -> Optional[str]:
    from ..layers.counters import count
    from ..sidecar import parse_data_source

    class R:  # the counter reads a row
        pass

    r = R()
    r.data_source, r.extra, r.id = parse_data_source(d.data_source), d.extra, d.id
    try:
        n = count(r, snap)[0]
    except (KeyError, ValueError) as exc:
        return f"the data to count is missing ({exc})"
    if n == 0:
        return "the count is zero, which a counter cannot show meaningfully"
    if n == 1:
        return "the count is one: a counter would add nothing to what the narration says"
    return None


def v_radar(d: Draft, snap) -> Optional[str]:
    for k, v in snap.extra.items():
        if k.startswith("radar:") and k.endswith("@" + d.data_source.split("@")[1].split("#")[0]):
            scans = v.get("scans") or v.get("frames") or []
            if len(scans) < 2:
                return "the radar archive returned fewer than two scans for the window"
            return None
    return "the radar scans were not fetched"


# ---- the catalogue -------------------------------------------------------------------------------------------------------------

STORMY = ("hurricane", "tropical_storm")
WET = ("flood", "heavy_rain")
SEVERE = ("tornado", "severe")

CATALOG: List[GraphicSpec] = [
    GraphicSpec("broadcast.headline", "headline", "Opening lower-third", ("*",), {}, "headline", 4.0, b_headline,
                "the event, its place and day", "no headline", min_score=0.0, covers=("headline", "tp_title"), priority=1),
    GraphicSpec("hurricane.best_track", "storm_track", "Best track by intensity", STORMY + WET, {"track": 1.0, "intensity": 0.8, "landfall": 0.3},
                "data", 5.0, b_best_track, "the storm's NHC id", "the map without the track", covers=("storm_track",), priority=10),
    GraphicSpec("hurricane.stats", "storm_stats", "Storm statistics card", STORMY + WET, {"intensity": 1.2, "landfall": 0.4}, "data", 5.0,
                b_storm_stats, "the storm in NHC's final best track", "no card", min_score=1.2, covers=("storm_stats",), priority=13,
                must=("intensity",)),
    GraphicSpec("hurricane.landfall", "place_label", "Landfall marker", STORMY, {"landfall": 1.0}, "label", 3.0, b_landfall_marker,
                "a landfall record in HURDAT2", "no marker", min_score=1.0, covers=(), priority=55, must=("landfall",)),
    GraphicSpec("hurricane.cone", "storm_cone", "Forecast cone, track and coastal warnings", STORMY, {"cone": 1.5}, "data", 5.0, b_cone,
                "the storm's NHC id and an advisory issued near the narrated time", "the best track only", min_score=1.4,
                covers=("storm_cone",), priority=11),
    GraphicSpec("hurricane.satellite_loop", "satellite_loop", "Satellite loop (daily true colour)", STORMY + WET,
                {"satellite": 1.2}, "loop", 6.0, b_satellite_loop, "the storm's days", "a still map", covers=("satellite_loop", "satellite"),
                min_score=1.5, priority=20),
    GraphicSpec("radar.loop", "radar", "Radar loop with warnings", STORMY + SEVERE + WET, {"radar": 1.2, "warnings": 0.8, "landfall": 0.2},
                "loop", 6.0, b_radar, "the event moment or day (UTC window)", "the map without radar", covers=("radar",),
                priority=12, must=("radar", "warnings")),
    GraphicSpec("warnings.counter", "counter", "Warnings issued (count)", STORMY + SEVERE + WET, {"count": 1.5, "warnings": 0.8}, "counter",
                4.0, b_warning_counter, "the warning type the narration counts", "no counter", min_score=2.0, covers=(), priority=30,
                must=("count",)),
    GraphicSpec("severe.survey", "tornado_tracks", "Surveyed tornado track (NWS DAT)", SEVERE, {"track": 1.2, "reports": 0.4}, "data", 5.0,
                b_survey, "the NWS damage surveys of the event's days", "storm reports", min_score=1.2, covers=("tornado_tracks",),
                priority=13, must=("track",), local=True, repeat_after_s=120.0),
    GraphicSpec("severe.survey_overview", "tornado_tracks", "Other surveyed tornadoes", SEVERE, {"reports": 1.0, "count": 0.5}, "data", 5.0,
                b_survey_overview, "surveyed tornadoes the narration names", "storm reports", min_score=1.0, covers=(), priority=14),
    GraphicSpec("severe.watch_warning", "explainer", "Watch vs warning explainer", SEVERE, {"warnings": 1.0}, "data", 5.0, b_watch_warning,
                "the narration comparing a watch and a warning", "none", min_score=1.0, covers=("explainer",), priority=35,
                must=("warnings",)),
    GraphicSpec("severe.reports", "storm_reports", "Storm reports (preliminary)", SEVERE, {"reports": 1.0, "count": 0.5}, "data", 5.0,
                b_reports, "the SPC convective day", "no reports", min_score=2.0, covers=("storm_reports",), verify=v_reports, priority=15),
    GraphicSpec("severe.counter", "counter", "Report counter", SEVERE, {"count": 1.5, "reports": 0.6}, "counter", 4.0, b_report_counter,
                "the SPC convective day", "no counter", min_score=2.2, covers=("counter",), verify=v_counter, priority=31, must=("count",)),
    GraphicSpec("severe.outlook", "spc_outlook", "SPC outlook", SEVERE, {"outlook": 1.5}, "data", 5.0, b_outlook, "the convective day",
                "no outlook", min_score=1.4, covers=("spc_outlook",), priority=15),
    GraphicSpec("rain.ero", "wpc_ero", "Excessive rainfall outlook", STORMY + WET + SEVERE, {"rain_outlook": 1.5}, "data", 4.0, b_ero,
                "the day", "no outlook", min_score=1.4, covers=("wpc_ero",), priority=32),
    GraphicSpec("rain.map", "rain_map", "Rainfall (radar estimate) map", STORMY + WET, {"rain_estimate": 1.5, "rain": 0.4}, "data", 5.0,
                b_rain_map, "the event's days and a place", "no rain map", min_score=1.4, covers=("rain_map",), priority=16,
                must=("rain_estimate",)),
    GraphicSpec("rain.totals", "rain_total", "Gauge rain totals", STORMY + WET, {"gauge_totals": 1.2, "rain": 0.6}, "data", 4.0,
                b_rain_totals, "gauges the narration names", "no totals", min_score=1.6, covers=("rain_total",), priority=17),
    GraphicSpec("record", "record", "Verified record", STORMY + WET + ("heat", "winter"), {"record": 1.5}, "data", 4.0, b_record,
                "a city with a long record and a day", "no record badge", min_score=1.4, covers=("record", "temp_extreme"), priority=18),
    GraphicSpec("river.crest", "river_crest", "River crest and flood stage", STORMY + WET, {"river": 1.2}, "data", 5.0, b_river_crest,
                "a USGS gauge on the named river", "no crest", min_score=1.0, covers=("river_crest",), per_entity=rivers, priority=19),
    GraphicSpec("satellite.before_after", "before_after", "Before and after from space", STORMY + WET, {"before_after": 1.0, "satellite": 0.8},
                "loop", 6.0, b_before_after, "dates before and after", "no comparison", min_score=1.6, covers=("before_after",), priority=19,
                must=("before_after",)),
    GraphicSpec("timeline", "event_timeline", "Event timeline", STORMY + WET, {"timeline": 1.5}, "data", 5.0, b_timeline,
                "dated marks from the data", "no timeline", min_score=1.4, covers=("event_timeline",), priority=40),
    GraphicSpec("forecast.strip", "forecast_strip", "Five-day forecast", ("forecast", "heat", "winter"), {"forecast": 1.0}, "data", 5.0,
                b_forecast_strip, "a covered city and the NWS contact", "no strip", min_score=1.5, covers=("forecast_strip", "temp_trend"),
                priority=22),
    GraphicSpec("forecast.now", "now_card", "Current conditions", ("forecast",), {"forecast": 0.5}, "data", 4.0, b_now_card,
                "a covered city and the NWS contact", "no card", min_score=1.5, covers=("now_card",), priority=23),
    GraphicSpec("forecast.alerts", "alert_area", "Active alerts", ("forecast", "heat", "winter") + SEVERE, {"warnings": 1.0}, "data", 4.0,
                b_alerts_now, "a state and the NWS contact", "no alerts", min_score=1.5, covers=("alert_area",), priority=24),
    GraphicSpec("winter.snow", "-", "Snow and ice totals", ("winter",), {}, "data", 4.0, b_winter, "snow data", "none", min_score=0.0,
                priority=90),
    GraphicSpec("broadcast.place_label", "place_label", "County label", SEVERE + WET, {}, "label", 3.0, b_place_label,
                "a county the narration names", "no label", min_score=0.0, covers=("place_label", "tp_place"), per_entity=counties, priority=60),
]
SPECS = {s.key: s for s in CATALOG}
