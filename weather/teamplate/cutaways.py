"""Teamplate's B-roll cutaways: the reference is footage-first, so a Teamplate video cuts from the map to generic stock footage of
what the narration is describing (rain, flooding, surge, waves, wind, snow ...) wherever the map is only holding.

Where a cutaway may go: inside a map beat, in a stretch where nothing on the map is arriving (no layer appearing, no camera move)
and no timed loop is running (radar and satellite loops are protected for their whole time: under footage their frames would be
skipped), at least CUT_MIN_S long, and while the words spoken there name something a camera can film. The request is built from
those words only (so it passes teamplate.footage.relevance_problems), goes to the app's stock providers (your library first), and a
cutaway of 9 s or more becomes two shots (split_long_shots). The map's layers pause underneath and carry on after it, so no data
moment is lost. At most MAX_SHARE of the video is footage (counting the footage the plan already has).

The map beat is split in three (map, footage, map): layers that started before the cut stay in the first part, held to the
original beat end; layers after it move to the last part. The sidecar's windows were computed before the split, so
weather_layers.csv rows still name the beats you wrote."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import List, Optional, Sequence, Tuple

from .footage import SETTINGS

MAX_SHARE = 0.40
CUT_MIN_S = 4.0
CUT_MAX_S = 10.0
MAP_BETWEEN_S = 5.0  # in a long quiet stretch, the map is back this long between two cutaways
EDGE_S = 2.5          # a map piece left before or after a cutaway is at least this long (or nothing)
ARRIVE_BEFORE, ARRIVE_AFTER = 0.6, 3.5   # around a layer appearing: the map stays on screen while it arrives and is read
QUIET_TYPES = {"source_line", "alert_legend", "radar_legend", "footage_credit"}   # credits and keys arriving do not hold the map

# what the narration says -> what to ask the stock providers for. First match wins (most specific first). `{place}` options are
# added only when the narration allows that setting (teamplate.footage.SETTINGS), so the request never contradicts it.
SUBJECTS: Tuple[Tuple[Tuple[str, ...], str, dict], ...] = (
    (("surge",), "storm surge flooding", {"coast": " the coast"}),
    (("flood", "flooding", "flooded", "floods", "floodwater", "floodwaters", "inundated"), "aerial view of floodwater", {"city": " in city streets"}),
    (("hurricane", "hurricanes", "eyewall", "landfall", "typhoon", "cyclone"), "hurricane winds and heavy rain", {"tropical": " bending palm trees"}),
    (("tornado", "tornadoes", "funnel"), "tornado funnel cloud", {}),
    (("waves", "erosion", "beach", "beaches", "shoreline", "coastline", "coast", "coastal", "lakeshore", "shore"), "aerial drone view of waves on the coast", {}),
    (("blizzard", "snow", "snowfall", "snowstorm"), "heavy snow falling", {"city": " on a city street"}),
    (("ice", "icy", "freezing", "sleet"), "ice storm frozen trees", {}),
    (("thunderstorm", "thunderstorms", "lightning", "thunder", "supercell", "hail"), "thunderstorm with lightning", {}),
    (("rain", "rainfall", "downpour", "showers", "rains", "raining"), "heavy rain falling", {"city": " on a city street"}),
    (("wind", "winds", "gusts", "gust", "windy"), "strong wind bending trees", {}),
    (("heat", "heatwave", "hot", "scorching"), "heat haze shimmering", {"city": " over a city street"}),
    (("fog", "foggy", "mist"), "thick fog", {}),
    (("storm", "storms", "clouds", "cloudy"), "dark storm clouds rolling", {}),
)
_SETTING_FOR = {"coast": "coast", "city": "city", "tropical": "tropical"}


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z]+", str(text).lower())


# names of agencies and products are not weather to film ("the National Hurricane Center", "an extreme wind warning")
NOT_WEATHER = re.compile(r"\b(national hurricane center|hurricane center|national weather service|weather service|storm prediction center|"
                         r"weather prediction center|prediction center|\w+ (warnings?|watch(es)?|advisory|advisories|outlooks?)|storm reports?|"
                         r"rain outlook|for the latest on any storm)\b")
# measurements being read out ("category five", "160 miles per hour", "10 inches"): the map or a number card shows them while they
# are said, so a cutaway never covers one. Plain numbers ("eight in the morning") do not hold the map.
NUMBER_WORDS = {"category", "percent", "mph", "miles", "inches", "inch", "degrees", "feet", "knots", "millibars"}


def is_data_word(word: str) -> bool:
    w = str(word).lower().strip(".,;:!?\"'()")
    return any(ch.isdigit() for ch in w) or w in NUMBER_WORDS


# words that mean the narration is about the data or its sources ("radar rainfall estimates", "the rain map", "from space"), not about
# weather a camera could film: such a stretch keeps the map
SOURCE_WORDS = {"data", "radar", "gauge", "gauges", "estimate", "estimates", "map", "maps", "report", "reports", "satellite", "survey",
                "analysis", "analyzed", "advisory", "track", "according", "nasa", "noaa", "space", "station", "video", "number", "numbers",
                "chart", "record", "records", "observed", "readings", "reading", "measured", "forecast", "outlook", "mosaic", "frame", "colors",
                "colours", "issued", "thanks", "watching", "follow"}


def request_for(spoken: str) -> Optional[str]:
    """The stock request for what is being said (None when nothing in it can be filmed, or it is about the data)."""
    said = set(_words(NOT_WEATHER.sub(" ", str(spoken).lower())))
    if said & SOURCE_WORDS:
        return None
    for keys, base, places in SUBJECTS:
        if said & set(keys):
            for setting, extra in places.items():
                if said & SETTINGS[_SETTING_FOR[setting]][1]:
                    return base + extra
            return base
    return None


def _merge(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def busy_spans(plan, payload, words: Sequence = ()) -> List[List[float]]:
    """Times the map must stay on screen: layers and data arriving, camera moves, timed loops, the opening chapter card, numbers said."""
    spans = [[float(w[1]) - 1.0, float(w[2]) + 1.0] for w in words if is_data_word(w[0])]
    for b in plan.beats:
        for lay in b.layers:
            spans.append([lay.t - ARRIVE_BEFORE, lay.t + (5.5 if lay.type == "hud_title" and lay.t < 1.0 else ARRIVE_AFTER)])
        for c in b.camera:
            if c.action == "start":
                continue
            dur = c.dur if c.dur is not None else {"fly_to": 2.2, "push_in": 8.0, "pull_back": 2.0}.get(c.action, 2.0)
            spans.append([c.t - ARRIVE_BEFORE, c.t + dur + 0.5])
    for e in list(payload.events) + list(payload.fills):
        if e.get("type") in QUIET_TYPES:
            continue
        spans.append([float(e["t_in"]) - ARRIVE_BEFORE, float(e["t_in"]) + ARRIVE_AFTER])
    for r in list(payload.rasters) + list(payload.satellite):
        spans.append([float(r["t_in"]) - ARRIVE_BEFORE, float(r["t_out"]) + 0.3])
    return _merge(spans)


def _spoken(words: Sequence, a: float, b: float) -> str:
    return " ".join(str(w[0]) for w in words if float(w[1]) < b and float(w[2]) > a)


def add_cutaways(plan, words: Sequence, payload, notes: Optional[List[str]] = None, *, max_share: float = MAX_SHARE) -> int:
    """Insert the cutaways into `plan` (in place); returns how many. See the module notes."""
    from hybrid.plan import Beat, Clip

    budget = max_share * plan.duration - sum(b.end - b.start for b in plan.beats if b.mode == "footage")
    busy = busy_spans(plan, payload, words)
    added = 0
    out: List = []
    for b in plan.beats:
        if b.mode != "map" or budget < CUT_MIN_S:
            out.append(b)
            continue
        # the free stretches of this beat
        free, t = [], b.start
        for a, z in busy:
            if z <= b.start or a >= b.end:
                continue
            if a > t:
                free.append([t, min(a, b.end)])
            t = max(t, z)
        if t < b.end:
            free.append([t, b.end])
        pieces, cur = [], b
        queue = [list(x) for x in free]
        while queue:
            a, z = queue.pop(0)
            if budget < CUT_MIN_S:
                break
            # keep a usable map piece on either side (or none at all, at the beat's own edges)
            if a > cur.start + 1e-6 and a - cur.start < EDGE_S:
                a = cur.start + EDGE_S
            length = min(z - a, CUT_MAX_S, budget)
            rest = cur.end - (a + length)
            if 1e-6 < rest < EDGE_S:   # no sliver of map after the cutaway: run on to the beat's end, or stop sooner
                length = cur.end - a if z >= cur.end - 1e-6 and cur.end - a <= min(CUT_MAX_S + EDGE_S, budget) else cur.end - EDGE_S - a
            if length < CUT_MIN_S or (a <= cur.start + 1e-6 and any(c.t < a + 1e-6 for c in cur.camera)):
                continue
            req = request_for(_spoken(words, a, a + length))
            if req is None:
                if z - a >= CUT_MIN_S + 2.0:   # nothing to film here: look a little later in the same stretch
                    queue.insert(0, [a + 2.0, z])
                continue
            c0, c1 = a, a + length
            k = added + 1
            head = replace(cur, end=c0, layers=[l for l in cur.layers if l.t < c0], camera=[c for c in cur.camera if c.t < c0]) if c0 > cur.start + 1e-6 else None
            tail = replace(cur, id=f"{b.id}_r{k}", start=c1, layers=[l for l in cur.layers if l.t >= c1], camera=[c for c in cur.camera if c.t >= c1])
            if head is not None:
                head.layers = [replace(l, until=float(b.end)) if l.until == "beat_end" and l.hold is None else l for l in head.layers]
            cut = Beat(id=f"{b.id}_x{k}", mode="footage", start=c0, end=c1, purpose="cutaway", narration=_spoken(words, c0, c1),
                       clips=[Clip(asset=f"stock_video:{req}", reason="Weather Teamplate cutaway: generic footage of what the narration describes")],
                       footage_intent="illustrate what is being said while the map holds")
            if head is not None:
                pieces.append(head)
            pieces.append(cut)
            cur = tail
            budget -= length
            added += 1
            if notes is not None:
                notes.append(f"beat {b.id}: {length:.1f}s cutaway at {c0:.1f}s to stock footage {req!r} (Weather Teamplate)")
            if z - c1 >= MAP_BETWEEN_S + CUT_MIN_S:   # a long quiet stretch alternates: back to the map, then footage again
                queue.insert(0, [c1 + MAP_BETWEEN_S, z])
        if cur.end - cur.start > 1e-6:
            pieces.append(cur)
        out.extend(pieces)
    plan.beats = out
    return added
