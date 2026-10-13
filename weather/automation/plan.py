"""beats.csv and weather_layers.csv for the day's forecast, built from the snapshot, the story and the script.

One beat per script section (weather.automation.script.Section), in order, so the beats' text cells joined give the script word
for word (pronunciation hints in brackets are left out: they are not spoken). Each beat starts on its first words; each graphic
appears on the first words of the sentence that names its city. Every anchor is checked against the script itself (pakMap's
matcher on words estimated from the script) before the files are written, so a plan that would not load is never written.

    intro      the whole country (38.5,-97.5, frame continental): satellite for the whole video, up to 4 temperature markers
    lead       the lead city's area: the story's alert areas, the lead city's high
    now        same place (the camera holds): the now card, the latest temperature
    footage    2 or 3 full-screen beats of stock b-roll matching a city's forecast (rain -> rain shots ...); no weather layers
    region     one per region: a temperature marker per city named
    week/trend the lead city again: the forecast strip, then the highs-and-lows chart
    warnings   the whole country: the alert areas of the most common other warning
    close      the whole country, the pointer to the local NWS office
A source line is on every beat that shows a number. Places for the camera are names the atlas knows (a state or a named region),
chosen so the cities with markers are inside the view."""

from __future__ import annotations

import csv
import io
import json
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..resolve import Snapshot
from ..sidecar import COLUMNS as WX_COLUMNS
from . import spoken as sp
from .coverage import metro
from .fetch import day_index, national_alerts
from .script import Script, Section, category_of, day_of
from .story import NOT_LOWER48, Story, _lower48

BEAT_COLUMNS = ("beat", "row", "vo_anchor", "mode", "type", "id", "place", "frame", "label", "sub", "text", "role", "kind", "value_from",
                "value_to", "format", "anchor", "until", "hold", "asset", "dur", "why")
NATIONAL = ("38.5,-97.5", "continental")
MAX_MARKERS = 4
# Named US regions the atlas knows (pakMap's named regions), tried with the states as camera places.
US_REGIONS = ("New England", "Midwest", "Great Lakes", "Deep South", "Gulf Coast", "Pacific Northwest", "Appalachia", "Rust Belt", "Sun Belt")

# Generic weather b-roll for each footage condition: what to film, never "footage of" an event. Each description says its
# condition in words weather.footage_library recognises, so the user's own library can stand in for stock.
FOOTAGE = {
    "rain": ("rain drops falling into a puddle on a city sidewalk", "people with umbrellas walking on a wet street",
             "rain running down a window pane", "rain falling on parked cars on a quiet street"),
    "storm": ("dark storm clouds rolling over open farmland", "lightning flashing in a dark evening sky",
              "heavy storm rain pouring onto a dark street", "storm clouds gathering over a city skyline"),
    "snow": ("snow falling on a quiet residential street", "snow covered trees in a winter park", "cars driving slowly through falling snow"),
    "fog": ("morning fog over a city skyline", "fog drifting over a quiet road at dawn", "foggy morning in a city park"),
    "heat": ("hot sun over a busy city street in summer", "people walking on a hot sunny afternoon downtown",
             "a thermometer in hot afternoon sun"),
    "cold": ("frost on grass on a cold morning", "people in winter coats on a morning of frost", "ice crystals on a window on a cold day"),
    "wind": ("trees swaying in a strong wind", "flags flapping in the wind", "windy day with leaves blowing down a street"),
    "sun": ("bright sunshine over a green city park", "sunshine on a clear blue sky over rooftops", "people enjoying a sunny day in a park"),
    "cloud": ("gray clouds drifting over a city skyline", "overcast sky over a quiet neighborhood", "time lapse of cloudy sky over rooftops"),
}
WHY = {"rain": "the feel of a rainy day", "storm": "stormy skies", "snow": "a snowy day", "fog": "a foggy start", "heat": "the heat",
       "cold": "a cold day", "wind": "a windy day", "sun": "a sunny day", "cloud": "a gray day"}


class PlanBuildError(ValueError):
    pass


# ---- camera ---------------------------------------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def camera_places() -> List[Tuple[str, Tuple[float, float, float], Tuple[float, float, float, float]]]:
    """(name, (lon, lat, zoom) of its frame=region view, bbox) for every US state and named region the atlas resolves inside the US."""
    from pakmap.geo import resolve, view_for

    out = []
    names = [n for c, n in sp.STATES.items() if c not in ("AK", "HI", "PR", "DC")] + list(US_REGIONS)
    for name in names:
        try:
            loc = resolve(name, "area")
        except Exception:
            continue
        if not getattr(loc, "is_area", False) or not (-126 < loc.lon < -65 and 24 < loc.lat < 50):
            continue  # "Georgia" is the country to the atlas: not offered
        out.append((name, view_for(loc, "region"), tuple(loc.bbox)))
    return out


def _merc_y(lat: float) -> float:
    s = math.sin(math.radians(max(-85.0, min(85.0, lat))))
    return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def in_view(view: Tuple[float, float, float], lon: float, lat: float, margin: float = 0.14, w: int = 1920, h: int = 1080) -> bool:
    """True when (lon, lat) lands inside the frame of a camera view, `margin` (a fraction of the frame) away from every edge."""
    clon, clat, z = view
    scale = 512 * 2 ** z  # px per world width
    x = w / 2 + (lon - clon) / 360.0 * scale
    y = h / 2 + (_merc_y(lat) - _merc_y(clat)) * scale
    return margin * w <= x <= (1 - margin) * w and margin * h <= y <= (1 - margin) * h


def choose_camera(points: Sequence[Tuple[float, float]], extra: Sequence[Tuple[float, float]] = ()) -> Tuple[str, List[bool]]:
    """The camera place showing the most of `points`, then the one that is itself around most of them (Texas, not Louisiana, for
    Dallas and Houston), then showing the most of `extra`, then the closest in; and which points are in view."""
    best = None
    for name, view, (w, s, e, n) in camera_places():
        inside = [in_view(view, lon, lat) for lon, lat in points]
        own = sum(1 for (lon, lat), ok in zip(points, inside) if ok and w <= lon <= e and s <= lat <= n)
        more = sum(in_view(view, lon, lat, 0.05) for lon, lat in extra)
        key = (sum(inside), own, more, view[2], name)
        if best is None or key > best[0]:
            best = (key, name, inside)
    return best[1], best[2]


# ---- anchors --------------------------------------------------------------------------------------------------------------------

def _tokens(text: str) -> List[str]:
    from pakmap.anchor import tokenize

    return tokenize(sp.strip_hints(text))


def _find(tokens: Sequence[str], phrase: Sequence[str], start: int = 0) -> int:
    n = len(phrase)
    for i in range(start, len(tokens) - n + 1):
        if list(tokens[i:i + n]) == list(phrase):
            return i
    return -1


def anchor_at(text: str, words_before: int, search_from_words: int, *, lo: int = 3, hi: int = 8) -> str:
    """The first `lo`..`hi` words of `text` from word `words_before` on (as written in the text), the fewest whose first
    occurrence after word `search_from_words` is right there. Raises PlanBuildError when no such phrase exists."""
    raw = sp.strip_hints(text).split()
    toks = _tokens(text)
    # raw word index -> token index (a hyphenated word is two tokens)
    starts, k = [], 0
    for wd in raw:
        starts.append(k)
        k += len(_tokens(wd))
    starts.append(k)
    t0, s0 = starts[words_before], starts[search_from_words]
    for n in range(lo, hi + 1):
        if words_before + n > len(raw):
            break
        phrase = toks[t0:starts[words_before + n]]
        if any(t in sp.ONES or t in sp.TENS.values() or t.isdigit() for t in phrase):
            continue
        if _find(toks, phrase, s0) == t0:
            return " ".join(raw[words_before:words_before + n]).strip(",.;:")
    raise PlanBuildError(f"no unique words to anchor on at {' '.join(raw[words_before:words_before + 5])!r}")


# ---- the plan --------------------------------------------------------------------------------------------------------------------

@dataclass
class Plan:
    beats_csv: str
    layers_csv: str
    beats: List[Dict[str, Any]] = field(default_factory=list)  # one per beat: id, section, mode, place, words


def build_plan(snap: Snapshot, story: Story, script: Script) -> Plan:
    on = story.on
    full = " ".join(s.text for s in script.sections)
    lead = metro(story.lead_city)
    rng = random.Random(f"weather-footage-{on.isoformat()}")
    beat_rows: List[Dict[str, str]] = []
    wx_rows: List[Dict[str, str]] = []
    beats: List[Dict[str, Any]] = []
    used_clips: set = set()
    words_so_far, prev_start = 0, 0
    prev_place: Optional[Tuple[str, str]] = None
    lead_place: Optional[Tuple[str, str]] = None
    title_date = f"{on.strftime('%A').upper()} · {on.strftime('%b').upper()} {on.day}"

    def dn(key: str) -> int:
        return day_index(snap, key, on)

    for n, sec in enumerate(script.sections, start=1):
        bid = f"b{n}"
        text = sp.strip_hints(sec.text)
        nwords = len(text.split())
        anchor = anchor_at(full, words_so_far, prev_start)
        sent_at, k = [], words_so_far   # word index of each sentence
        for s in sec.sentences:
            sent_at.append(k)
            k += len(sp.strip_hints(s.text).split())

        def sentence_anchor(i: int) -> str:
            return anchor_at(full, sent_at[i], words_so_far)

        def wx(typ: str, lid: str, i: int, place: str = "", ds: str = "", until: str = "", extra: Optional[Dict[str, Any]] = None) -> None:
            wx_rows.append({"beat": bid, "vo_anchor": sentence_anchor(i), "t": "", "id": lid, "type": typ, "place": place, "data_source": ds,
                            "hold": "", "until": until, "extra": json.dumps(extra) if extra else ""})

        if sec.kind == "footage":
            beat_rows.append({"beat": bid, "row": "beat", "vo_anchor": anchor, "mode": "footage", "text": text, "why": WHY[sec.footage]})
            options = [d for d in FOOTAGE[sec.footage] if d not in used_clips]
            for _ in range(2 if nwords >= 18 else 1):
                if not options:
                    break
                d = options.pop(rng.randrange(len(options)))
                used_clips.add(d)
                beat_rows.append({"beat": bid, "row": "clip", "asset": f"stock_video:{d}", "why": f"{WHY[sec.footage]} ({metro(sec.footage_city).name}'s forecast)"})
            beats.append({"id": bid, "section": sec.id, "mode": "footage", "place": "", "words": nwords, "footage": sec.footage})
            words_so_far += nwords
            prev_start = words_so_far - nwords
            continue

        # where the camera looks, and which marked cities it shows
        markers = [c for c in sec.cities][:MAX_MARKERS]
        if sec.kind in ("intro", "warnings", "close"):
            place, frame = NATIONAL
            visible = [True] * len(markers)
        else:
            pts = [(metro(c).city.lon, metro(c).city.lat) for c in markers]
            extra = [(a["centre"][1], a["centre"][0]) for a in story.alerts if a.get("centre")] if sec.kind == "lead" else []
            if sec.kind in ("lead", "now", "week", "trend"):
                pts = [(lead.city.lon, lead.city.lat)]
                markers = [lead.key]
            if sec.kind in ("now", "week", "trend") and lead_place:
                place, frame = lead_place   # the lead city's view again
                visible = [True]
            else:
                place, visible = choose_camera(pts, extra)
                frame = "region"
                if sec.kind == "lead":
                    lead_place = (place, frame)
        move = "hold" if prev_place == (place, frame) else ("push_in" if sec.kind == "lead" else "")
        if n == 1:
            move = ""
        prev_place = (place, frame)
        beat_rows.append({"beat": bid, "row": "beat", "vo_anchor": anchor, "mode": "map", "type": move, "place": place, "frame": frame,
                          "text": text, "why": {"intro": "national overview", "lead": "the day's lead story", "now": f"{lead.name} now",
                                                "region": f"{sec.region} forecast", "week": f"{lead.name} this week", "trend": f"{lead.name} highs and lows",
                                                "warnings": "warnings to know", "close": "wrap up"}.get(sec.kind, sec.kind)})
        title = {"intro": ("YOUR WEATHER", title_date), "lead": _story_title(story, lead), "week": (lead.name.upper(), "THE WEEK AHEAD"),
                 "warnings": ("WARNINGS TO KNOW", "ACROSS THE COUNTRY"), "region": (_region_title(sec), "")}.get(sec.kind)
        if title:
            beat_rows.append({"beat": bid, "row": "layer", "vo_anchor": anchor, "type": "hud_title", "id": f"{bid}_title", "label": title[0], "sub": title[1]})
        numbers = False

        # the weather layers of the beat
        if sec.kind == "intro":
            wx("satellite", "sat", 0, ds="gibs:geocolor@latest", until="end", extra={"opacity": 0.9})
            i3 = len(sec.sentences) - 1
            for c in markers:
                m = metro(c)
                wx("temp_marker", f"{bid}_{_slug(m.name)}", i3, place=m.key, ds=f"nws:forecast@{m.name},{m.city.state}#day{dn(m.key)}")
                numbers = True
        elif sec.kind in ("lead", "region"):
            if sec.kind == "lead":
                for j, st in enumerate(story.states[:2]):
                    if st in NOT_LOWER48:
                        continue
                    wx("alert_area", f"{bid}_alerts_{st.lower()}", 0, place=st, ds=f"nws:alerts@{st}",
                       extra={"events": story.events[:4], **({"legend": False} if j else {})})
                    numbers = True
            for c, ok in zip(markers, visible):
                if not ok:
                    continue
                m = metro(c)
                i = next((j for j, s in enumerate(sec.sentences) if s.city == c), 0)
                wx("temp_marker", f"{bid}_{_slug(m.name)}", i, place=m.key, ds=f"nws:forecast@{m.name},{m.city.state}#day{dn(m.key)}")
                numbers = True
        elif sec.kind == "now":
            if lead.key in snap.observations:
                wx("now_card", f"{bid}_now", 0, place=lead.key, ds=f"nws:obs@{lead.name},{lead.city.state}")
                wx("temp_marker", f"{bid}_mk", 0, place=lead.key, ds=f"nws:obs@{lead.name},{lead.city.state}")
                numbers = True
        elif sec.kind == "week":
            a = dn(lead.key)
            b = min(a + 4, len(snap.forecasts[lead.key]["days"]))
            if b - a + 1 >= 3:
                wx("forecast_strip", f"{bid}_strip", 0, place=lead.key, ds=f"nws:forecast@{lead.name},{lead.city.state}#day{a}-{b}")
                numbers = True
        elif sec.kind == "trend":
            a = dn(lead.key)
            b = min(a + 6, len(snap.forecasts[lead.key]["days"]))
            if b - a + 1 >= 3:
                wx("temp_trend", f"{bid}_trend", 0, place=lead.key, ds=f"nws:forecast@{lead.name},{lead.city.state}#day{a}-{b}")
                numbers = True
        elif sec.kind == "warnings":
            st, events = _warning_state(snap, story)
            if st:
                wx("alert_area", f"{bid}_alerts_{st.lower()}", 0, place=st, ds=f"nws:alerts@{st}", extra={"events": events})
                numbers = True
        if numbers:
            wx("source_line", f"{bid}_src", 0)
        beats.append({"id": bid, "section": sec.id, "mode": "map", "place": place, "frame": frame, "words": nwords})
        prev_start = words_so_far
        words_so_far += nwords

    plan = Plan(_csv(BEAT_COLUMNS, beat_rows), _csv(WX_COLUMNS, wx_rows), beats)
    check_plan(plan, script)
    return plan


def _slug(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())[:12]


def _story_title(story: Story, lead) -> Tuple[str, str]:
    if story.kind == "routine":
        return lead.name.upper(), "TODAY'S LEAD"
    if story.events:
        e = story.events[0].upper()
        title = e if Counter(a["event"] for a in story.alerts)[story.events[0]] == 1 else sp.event_phrase(story.events[0], 2).upper()
        return title, " · ".join(sp.STATES.get(s, s).upper() for s in story.states[:3])
    return {"extreme_temp": "EXTREME TEMPERATURES", "heavy_rain": "HEAVY RAIN"}.get(story.kind, story.kind.upper()), lead.name.upper()


def _region_title(sec: Section) -> str:
    states = {metro(c).city.state for c in sec.cities}
    if len(states) == 1 and sec.region in ("South Central",):
        return sp.STATES[states.pop()].upper()
    return {"Pacific": "WEST COAST"}.get(sec.region, sec.region.upper())


def _warning_state(snap: Snapshot, story: Story) -> Tuple[str, List[str]]:
    """The state with the most land warnings/watches outside the story, and their event names there (what the warnings beat draws)."""
    alerts = [a for a in national_alerts(snap) if _lower48(a) and a["event"] not in story.events and a["event"].endswith(("Warning", "Watch"))]
    if not alerts:
        return "", []
    top_events = [e for e, _ in sorted(Counter(a["event"] for a in alerts).items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    c = Counter(s for a in alerts if a["event"] in top_events for s in a["states"] if s not in NOT_LOWER48)
    st = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return st, sorted({a["event"] for a in alerts if st in a["states"] and a["event"] in top_events})


def _csv(columns: Sequence[str], rows: List[Dict[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in columns})
    return buf.getvalue()


def check_plan(plan: Plan, script: Script, words: Optional[Sequence] = None) -> None:
    """Load the plan the way the render will: beats against the narration's words (estimated from the script when no
    transcript is given), the weather layers on their beats. Raises PlanBuildError with every problem."""
    from hybrid.beat_csv import plan_from_csv
    from hybrid.plan import PlanError
    from pakmap.words import estimate_words

    from ..footage import footage_problems
    from ..sidecar import SidecarError, parse_sidecar
    from ..timing import layer_windows

    words = list(words) if words is not None else estimate_words(sp.strip_hints(script.text))
    duration = words[-1][2] + 1.0
    try:
        hp = plan_from_csv(plan.beats_csv, words, duration)
        rows = parse_sidecar(plan.layers_csv)
        layer_windows(rows, hp, words)
    except (PlanError, SidecarError) as exc:
        raise PlanBuildError("the generated plan does not load: " + "; ".join(exc.problems)) from None
    bad = footage_problems(hp)
    if bad:
        raise PlanBuildError("; ".join(bad))
