"""Event understanding: what the narration is about, read deterministically from the script (no AI, no network).

    understand(segments, recorded_at=None) -> Understanding

A segment is a beat of the plan (or, with no plan, a few sentences of the transcript): its id, its mode (map / footage) and its
words. From all of them together the engine reads:

  category        hurricane | tropical_storm | tornado | severe | flood | heavy_rain | heat | winter | forecast  (and the scores)
  hazards         every category with enough evidence in the words (a tornado story that mentions a hurricane's remnants has
                  "tornado" first and "hurricane" as a secondary hazard)
  storms          named tropical systems ("Hurricane Ian", "Harvey") with the segment they appear in
  years / dates   absolute dates in digits or words ("September twenty eighth", "August 25, 2017", "October 11, 2026"), years in
                  digits or words ("twenty twenty two"), relative days ("yesterday", "early Sunday morning") resolved against the
                  recording date when there is one, and flagged as an assumption when there is not
  times           clock times ("6:05 a.m. Eastern Daylight Time", "eleven o'clock", "two in the afternoon")
  places          states, known cities, counties ("Newberry County"), rivers / bayous / creeks, coordinates
  measurements    numbers with units the narrator states (115 miles per hour, 450 yards, 31.26 inches, EF2) — CLAIMS of the
                  narration, checked against the evidence later, never used as data
  topics          per segment: what it discusses (track, cone, landfall, radar, warnings, reports, rain, river ...), the input of
                  graphic placement
  phase           per segment: setup / development / peak / landfall / impacts / aftermath / recovery / forecast / closing

Nothing here invents a fact: a date the words do not support stays unknown, and every guess is written to `assumptions`."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from ..news.timeline import STATE_NAMES
from .numwords import ORD_TENS, ORD_UNITS, number_at, ordinal_at, tokens, year_at

ORDINAL_WORDS = set(ORD_UNITS) | set(ORD_TENS)

MONTHS = {m: i for i, m in enumerate("january february march april may june july august september october november december".split(), 1)}
MONTH_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
WEEKDAYS = {d: i for i, d in enumerate("monday tuesday wednesday thursday friday saturday sunday".split())}
CODE_STATE = {v: k for k, v in STATE_NAMES.items()}

# category -> words (single tokens) and phrases, with weights; a category needs MIN_SCORE to count as a hazard
CATEGORY_WORDS: Dict[str, Dict[str, float]] = {
    "hurricane": {"hurricane": 3, "hurricanes": 3, "landfall": 2, "eyewall": 3, "cone": 1.5, "advisory": 1, "saffir": 2,
                  "tropical": 1, "typhoon": 3, "storm surge": 2, "national hurricane center": 2, "came ashore": 1.5, "category": 0.5},
    "tropical_storm": {"tropical storm": 3, "tropical depression": 3},
    "tornado": {"tornado": 3, "tornadoes": 3, "twister": 3, "touched down": 2, "funnel": 2, "ef0": 2, "ef1": 2, "ef2": 2, "ef3": 2,
                "ef4": 2, "ef5": 2, "supercell": 1.5, "rotation": 1, "damage survey": 1.5},
    "severe": {"severe": 1.5, "thunderstorm": 2, "thunderstorms": 2, "hail": 2, "damaging winds": 2, "derecho": 3, "squall line": 2,
               "storm reports": 1.5, "severe weather": 2, "outlook": 0.5},
    "flood": {"flood": 2.5, "flooding": 2.5, "floods": 2.5, "flash flood": 2, "crest": 2, "crested": 2, "flood stage": 2,
              "bayou": 1, "river": 0.8, "inundated": 2, "high water": 1.5},
    "heavy_rain": {"rainfall": 1.5, "inches of rain": 2.5, "rain totals": 2, "wettest": 2, "downpours": 1.5, "excessive rainfall": 2,
                   "rain gauge": 1.5, "gauges": 1},
    "heat": {"heat": 2, "heat wave": 3, "heatwave": 3, "heat index": 3, "hottest": 2.5, "scorching": 2, "triple digits": 2.5,
             "record high": 2, "excessive heat": 3},
    "winter": {"snow": 2.5, "snowfall": 2.5, "blizzard": 3, "ice storm": 3, "freezing rain": 3, "sleet": 2, "wind chill": 3,
               "winter storm": 3, "whiteout": 2, "snowstorm": 3},
    "forecast": {"forecast": 1, "tomorrow": 1.5, "tonight": 1.2, "this week": 1.5, "highs": 1.5, "lows": 1.5, "chance of rain": 2,
                 "weekend": 0.8, "next week": 1.5, "expect": 1, "partly cloudy": 2, "sunny": 1},
}
MIN_SCORE = 3.0

# topic -> words and phrases that make a segment discuss it (graphic placement scores these)
TOPIC_WORDS: Dict[str, Tuple[str, ...]] = {
    "track": ("path", "track", "analyzed", "colored by strength", "coloured by strength", "best track", "crossed", "turned north",
              "moved across", "passed over", "traveled", "travelled", "headed"),
    "intensity": ("category", "intensified", "strengthened", "weakened", "winds near", "peak", "strongest", "rapid intensification",
                  "sustained winds", "millibars", "pressure"),
    "cone": ("cone", "advisory", "forecast track", "forecast had", "forecast cone", "uncertainty"),
    "landfall": ("landfall", "came ashore", "made landfall", "moved onshore", "onshore", "ashore", "coast"),
    "radar": ("radar", "line of storms", "storms moved", "rotation", "eyewall", "touched down", "squall", "cells", "reflectivity"),
    "warnings": ("warning", "warnings", "warned", "tornado warning", "extreme wind warning"),
    "reports": ("reports", "reported", "confirmed", "survey", "surveyed", "damage", "touched down", "ef", "rating", "path stretched",
                "width"),
    "count": ("in all", "total of", "a total", "number of", "how many", "counted", "tally", "altogether"),
    "outlook": ("outlook", "enhanced risk", "moderate risk", "slight risk", "marginal risk", "high risk of severe",
                "storm prediction center"),
    "rain_outlook": ("excessive rainfall", "rain outlook", "risk of flooding", "weather prediction center"),
    "rain": ("rain", "rainfall", "inches", "downpour", "wettest", "totals", "precipitation"),
    "rain_estimate": ("radar rainfall", "rainfall estimates", "radar estimate", "multi radar", "adds up", "estimate"),
    "gauge_totals": ("gauge", "gauges", "measured", "airport", "station"),
    "record": ("record", "wettest day", "hottest", "all time", "on record", "previous record"),
    "river": ("river", "bayou", "creek", "crest", "crested", "flood stage", "gauge record"),
    "satellite": ("satellite", "from space", "space", "imagery", "picture a day"),
    "before_after": ("before the storm", "before", "after", "change is clear", "compare"),
    "timeline": ("timeline", "chronology"),
    "heat": ("heat", "temperatures", "degrees", "heat index", "hottest"),
    "forecast": ("forecast", "tomorrow", "tonight", "this week", "highs", "lows", "chance of", "next few days"),
    "wrap": ("thanks for watching", "follow your local", "for the latest", "stay safe", "subscribe"),
}

# words that look like a topic but are another one ("radar rainfall estimates" is rain, not a radar loop)
TOPIC_NOT: Dict[str, Tuple[str, ...]] = {
    "radar": ("radar rainfall", "radar estimate", "radar estimates", "radar rain", "radar estimated", "multi radar"),
    "before_after": ("before lifting", "before it", "before the tornado", "before dawn", "never before", "before that"),
    "landfall": ("gulf coast", "east coast", "west coast"),
}

PHASE_WORDS: Dict[str, Tuple[str, ...]] = {
    "development": ("formed", "developed", "organized", "began as"),
    "intensification": ("intensified", "strengthened", "rapid intensification", "grew"),
    "peak": ("peak", "strongest", "category five", "category 5", "maximum"),
    "landfall": ("landfall", "came ashore", "touched down", "struck", "made landfall", "onshore"),
    "impacts": ("damage", "flooded", "flooding", "destroyed", "injuries", "fatalities", "power outages", "crested"),
    "aftermath": ("aftermath", "survey", "confirmed", "in all", "afterward", "after the storm", "cleanup"),
    "recovery": ("recovery", "recover", "rebuild", "fell back", "receded"),
    "forecast": ("forecast", "tomorrow", "expect", "will"),
}

STORM_NAME = re.compile(r"\b(Hurricane|Tropical Storm|Tropical Depression|Typhoon|Post-Tropical Cyclone|Storm)\s+([A-Z][a-z]{2,})\b")
NOT_NAMES = {"Center", "Centre", "Prediction", "Warning", "Warnings", "Watch", "Season", "Hunters", "Hunter", "Week", "Day", "Track",
             "Surge", "Damage", "Reports", "Survey", "Team", "The", "Data"}
RIVER = re.compile(r"\b((?:[A-Z][a-z]+\s){0,2}[A-Z][a-z]+)\s(River|Bayou|Creek)\b")
COUNTY = re.compile(r"\b((?:[A-Z][a-z]+\s)?[A-Z][a-z]+)\s(County|Counties|Parish)\b")
COUNTIES_AND = re.compile(r"\b([A-Z][a-z]+)\sand\s([A-Z][a-z]+)\scounties\b")
LEAD_WORDS = {"The", "Along", "Near", "From", "And", "Of", "On", "In", "At", "For", "Across", "Through", "Northeastern", "Northwestern",
              "Southeastern", "Southwestern", "Northern", "Southern", "Eastern", "Western", "Central", "Rural", "Neighboring", "Nearby",
              "Both", "Into", "To", "By", "With", "Over", "Upper", "Lower"}
COORD = re.compile(r"(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)")
ZONES = {"eastern daylight time": "EDT", "eastern standard time": "EST", "central daylight time": "CDT", "central standard time": "CST",
         "mountain daylight time": "MDT", "mountain standard time": "MST", "pacific daylight time": "PDT", "pacific standard time": "PST",
         "eastern time": "ET", "central time": "CT", "mountain time": "MT", "pacific time": "PT", "edt": "EDT", "est": "EST",
         "cdt": "CDT", "cst": "CST", "utc": "UTC"}
UNIT_WORDS = (  # (token sequence, unit, quantity)
    (("miles", "per", "hour"), "mph", "speed"), (("mph",), "mph", "speed"), (("mile", "per", "hour"), "mph", "speed"),
    (("knots",), "kt", "speed"), (("inches",), "in", "length_rain"), (("inch",), "in", "length_rain"), (("feet",), "ft", "length"),
    (("foot",), "ft", "length"), (("yards",), "yd", "length"), (("miles",), "mi", "distance"), (("mile",), "mi", "distance"),
    (("degrees",), "F", "temperature"), (("percent",), "%", "percent"), (("millibars",), "mb", "pressure"), (("minutes",), "min", "duration"),
    (("hours",), "h", "duration"), (("tornadoes",), "count", "count_tornado"), (("warnings",), "count", "count_warnings"),
    (("reports",), "count", "count_reports"),
)


@dataclass
class Segment:
    id: str
    mode: str  # map | map_footage | footage | ...
    text: str
    start: Optional[float] = None
    end: Optional[float] = None
    anchor: str = ""  # the beat's own vo_anchor (its first words), when it has one
    cam: str = ""  # where the map camera looks during the beat (a place name or "lat,lon"), when known
    layers: Tuple[str, ...] = ()  # the beat plan's own layer types on this beat (hud_title ...)


@dataclass
class Mention:
    seg: str
    text: str


@dataclass
class DateMention(Mention):
    day: str = ""  # ISO date
    relative: bool = False
    year_from: str = ""  # "said" | "context" | "recording" | "assumed"


@dataclass
class TimeMention(Mention):
    hour: int = 0
    minute: int = 0
    zone: str = ""  # EDT, CDT, ET ... ("" = local time of the event)


@dataclass
class Place(Mention):
    kind: str = ""  # state | city | county | river | coords
    name: str = ""
    state: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class Measurement(Mention):
    value: float = 0.0
    unit: str = ""
    quantity: str = ""


@dataclass
class StormMention(Mention):
    name: str = ""
    kind: str = ""  # the word before the name ("Hurricane")


@dataclass
class Understanding:
    category: str
    scores: Dict[str, float]
    hazards: List[str]
    storms: List[StormMention] = field(default_factory=list)
    years: List[Tuple[int, str]] = field(default_factory=list)  # (year, seg)
    dates: List[DateMention] = field(default_factory=list)
    times: List[TimeMention] = field(default_factory=list)
    places: List[Place] = field(default_factory=list)
    measurements: List[Measurement] = field(default_factory=list)
    topics: Dict[str, Dict[str, float]] = field(default_factory=dict)  # seg -> topic -> strength
    phases: Dict[str, str] = field(default_factory=dict)
    recorded_at: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)

    @property
    def states(self) -> List[str]:
        """States named, most-named first (ties: first named first); a county / city adds its state."""
        c: Counter = Counter()
        first: Dict[str, int] = {}
        for i, p in enumerate(self.places):
            if p.state:
                c[p.state] += 2 if p.kind == "state" else 1
                first.setdefault(p.state, i)
        return sorted(c, key=lambda s: (-c[s], first[s]))

    def places_of(self, kind: str) -> List[Place]:
        seen, out = set(), []
        for p in self.places:
            if p.kind == kind and (p.name, p.state) not in seen:
                seen.add((p.name, p.state))
                out.append(p)
        return out

    def to_dict(self) -> dict:
        return asdict(self)


# ---- helpers -------------------------------------------------------------------------------------------------------------------

def _low(text: str) -> str:
    return " " + " ".join(tokens(text)) + " "


def _phrase_hits(low: str, phrase: str) -> int:
    return len(re.findall(r"(?<= )" + re.escape(" ".join(tokens(phrase))) + r"(?= )", low))


def score_categories(text: str) -> Dict[str, float]:
    low = _low(text)
    return {cat: round(sum(w * _phrase_hits(low, ph) for ph, w in words.items()), 2) for cat, words in CATEGORY_WORDS.items()}


def pick_category(scores: Dict[str, float], storms: Sequence[StormMention]) -> Tuple[str, List[str]]:
    """The main category and every hazard over MIN_SCORE, strongest first. A named storm called a hurricane with no stronger
    tornado / flood story makes it a hurricane story; a story mostly about a flood stays a flood even when its cause is a storm."""
    hazards = sorted((c for c, s in scores.items() if s >= MIN_SCORE), key=lambda c: -scores[c])
    if not hazards:
        return "forecast" if scores.get("forecast", 0) > 0 else "general", []
    main = hazards[0]
    if main == "tropical_storm" and scores.get("hurricane", 0) >= scores["tropical_storm"] * 0.6:
        main = "hurricane"
    if main == "heavy_rain" and scores.get("flood", 0) >= MIN_SCORE:
        main = "flood"
    return main, hazards


def _date_ok(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _month_at(toks: List[str], i: int) -> Optional[int]:
    t = toks[i]
    if t in MONTHS:
        return MONTHS[t]
    if t in MONTH_ABBR and (t != "may") and i + 1 < len(toks) and (toks[i + 1] == "." or ordinal_at(toks, i + 1)):
        return MONTH_ABBR[t]
    return None


def find_years(seg: Segment) -> List[Tuple[int, int]]:
    """(year, token index) for years the segment says: digits anywhere, words only after a month, "of", "in" or a comma
    (so "twenty seventeen inches" is never a year)."""
    toks = tokens(seg.text)
    out = []
    i = 0
    while i < len(toks):
        if re.fullmatch(r"(18[5-9]\d|19\d\d|20\d\d)", toks[i]):
            out.append((int(toks[i]), i))
            i += 1
            continue
        prev = toks[i - 1] if i else ""
        if prev in ("of", "in", ",", "since", "back", "year") or prev in MONTHS or (i >= 2 and ordinal_at(toks, i - 1) and toks[i - 2] in MONTHS):
            y = year_at(toks, i)
            if y and y[1] >= 2:
                out.append((y[0], i))
                i += y[1]
                continue
        i += 1
    return out


def find_dates(seg: Segment, year_hint: Optional[int]) -> List[DateMention]:
    """Month + day (+ year) in digits or words: "September twenty eighth", "Aug. 25, 2017", "October 11, 2026", "the 28th of
    September"; an ISO date (2026-10-11)."""
    toks = tokens(seg.text)
    out: List[DateMention] = []
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", seg.text):
        d = _date_ok(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            out.append(DateMention(seg.id, m.group(0), d.isoformat(), False, "said"))
    i = 0
    while i < len(toks):
        mo = _month_at(toks, i)
        if mo is None:
            # "the twenty eighth of September"
            o = ordinal_at(toks, i) if i and toks[i - 1] == "the" else None
            if o and i + o[1] + 1 < len(toks) and toks[i + o[1]] == "of" and toks[i + o[1] + 1] in MONTHS:
                mo2 = MONTHS[toks[i + o[1] + 1]]
                j = i + o[1] + 2
                y = year_at(toks, j + (1 if j < len(toks) and toks[j] == "," else 0))
                yr, src = (y[0], "said") if y else (year_hint, "context")
                d = _date_ok(yr, mo2, o[0]) if yr else None
                if d:
                    out.append(DateMention(seg.id, " ".join(toks[i:j]), d.isoformat(), False, src))
                i = j
                continue
            i += 1
            continue
        j = i + 1
        if j < len(toks) and toks[j] == ".":
            j += 1
        o = ordinal_at(toks, j)
        if not o or (o[1] == 1 and re.fullmatch(r"\d{3,}", toks[j] or "")):
            # "September of twenty twenty two" / "August 2017": a month and year only
            i += 1
            continue
        k = j + o[1]
        # a plain cardinal day must not swallow the start of a year ("August twenty seventeen" is a month and a year)
        yy = year_at(toks, j)
        if yy and yy[1] >= 2 and toks[j] not in ORDINAL_WORDS and toks[j + 1] not in ORDINAL_WORDS:
            i = j + yy[1]
            continue
        kk = k + (1 if k < len(toks) and toks[k] == "," else 0)
        y = year_at(toks, kk)
        if y:
            yr, src, k = y[0], "said", kk + y[1]
        else:
            yr, src = year_hint, "context"
        d = _date_ok(yr, mo, o[0]) if yr else None
        if d:
            out.append(DateMention(seg.id, " ".join(toks[i:k]), d.isoformat(), False, src))
        i = k
    return out


def find_relative(seg: Segment, ref: Optional[date]) -> List[DateMention]:
    """yesterday / today / last night / this morning / (early) Sunday (morning): the date before the recording they mean.
    Without a recording date nothing is resolved (the caller reports it)."""
    toks = tokens(seg.text)
    out = []
    for i, t in enumerate(toks):
        day = None
        if t == "yesterday":
            day = ref - timedelta(days=1) if ref else None
        elif t in ("today", "tonight") or (t == "this" and i + 1 < len(toks) and toks[i + 1] in ("morning", "afternoon", "evening")):
            day = ref
        elif t == "last" and i + 1 < len(toks) and toks[i + 1] == "night":
            day = ref - timedelta(days=1) if ref else None
        elif t in WEEKDAYS:
            # a weekday is read against a full date the story says first (understand: _resolve_weekdays), the recording second
            out.append(DateMention(seg.id, t, "", True, "unresolved"))
            continue
        else:
            continue
        if day is not None:
            out.append(DateMention(seg.id, " ".join(toks[i:i + 2]), day.isoformat(), True, "recording"))
        elif t in ("yesterday", "last"):
            out.append(DateMention(seg.id, t, "", True, "unresolved"))
    return out


def _future_context(toks: List[str], i: int) -> bool:
    window = toks[max(0, i - 8):i + 8]
    return any(w in window for w in ("will", "forecast", "expect", "expected", "next", "coming", "ahead"))


def find_times(seg: Segment) -> List[TimeMention]:
    """6:05 a.m. / 6:05 AM / eleven o'clock / two in the afternoon / eight in the morning, with a zone when one is said."""
    out = []
    text = seg.text
    low = text.lower()
    for m in re.finditer(r"\b(\d{1,2}):(\d{2})\s*(a\.?\s?m\.?|p\.?\s?m\.?)?", low):
        h, mi = int(m.group(1)), int(m.group(2))
        ap = (m.group(3) or "").replace(".", "").replace(" ", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        out.append(TimeMention(seg.id, m.group(0), h, mi, _zone_after(low, m.end())))
    toks = tokens(text)
    for i, t in enumerate(toks):
        n = number_at(toks, i)
        if not n or n[0] != int(n[0]) or not 1 <= n[0] <= 12:
            continue
        h = int(n[0])
        rest = toks[i + n[1]:i + n[1] + 4]
        if rest[:1] == ["o'clock"]:
            out.append(TimeMention(seg.id, " ".join(toks[i:i + n[1] + 1]), h, 0, ""))
        elif rest[:3] == ["in", "the", "morning"]:
            out.append(TimeMention(seg.id, " ".join(toks[i:i + n[1] + 3]), h % 12, 0, ""))
        elif rest[:3] in (["in", "the", "afternoon"], ["in", "the", "evening"]):
            out.append(TimeMention(seg.id, " ".join(toks[i:i + n[1] + 3]), h % 12 + 12, 0, ""))
        elif rest[:2] == ["at", "night"]:
            out.append(TimeMention(seg.id, " ".join(toks[i:i + n[1] + 2]), h % 12 + 12 if h >= 6 else h % 12, 0, ""))
        elif rest[:2] in (["a", "m"], ["p", "m"]) and not re.match(r"\d", toks[i]):
            out.append(TimeMention(seg.id, " ".join(toks[i:i + n[1] + 2]), h % 12 + (12 if rest[0] == "p" else 0), 0, ""))
    return out


def _zone_after(low: str, pos: int) -> str:
    tail = low[pos:pos + 40]
    for words, code in ZONES.items():
        if re.match(r"\s*" + re.escape(words) + r"\b", tail):
            return code
    return ""


def find_measurements(seg: Segment) -> List[Measurement]:
    toks = tokens(seg.text)
    out = []
    i = 0
    while i < len(toks):
        m = re.fullmatch(r"ef(\d)", toks[i])
        if m or (toks[i] == "ef" and i + 1 < len(toks) and number_at(toks, i + 1)):
            v = int(m.group(1)) if m else int(number_at(toks, i + 1)[0])
            out.append(Measurement(seg.id, f"EF{v}", float(v), "EF", "rating"))
            i += 1 if m else 2
            continue
        if toks[i] == "category" and i + 1 < len(toks) and number_at(toks, i + 1):
            v = number_at(toks, i + 1)[0]
            if 1 <= v <= 5:
                out.append(Measurement(seg.id, f"category {int(v)}", v, "cat", "category"))
            i += 2
            continue
        n = number_at(toks, i)
        if n and not year_at(toks, i) or (n and n[1] == 1 and re.fullmatch(r"\d+(\.\d+)?", toks[i]) and not re.fullmatch(r"(19|20)\d\d", toks[i])):
            j = i + n[1]
            for seq, unit, qty in UNIT_WORDS:
                if tuple(toks[j:j + len(seq)]) == seq:
                    out.append(Measurement(seg.id, " ".join(toks[i:j + len(seq)]), n[0], unit, qty))
                    i = j + len(seq) - 1
                    break
            else:
                # a count with words between ("five extreme wind warnings", "nine confirmed tornadoes")
                for k in range(j + 1, min(j + 4, len(toks))):
                    if toks[k] in (".", ",", ";"):
                        break
                    hit = next(((u, q) for seq, u, q in UNIT_WORDS if u == "count" and seq == (toks[k],)), None)
                    if hit:
                        out.append(Measurement(seg.id, " ".join(toks[i:k + 1]), n[0], hit[0], hit[1]))
                        i = k
                        break
            i += 1
            continue
        i += 1
    return out


def _county_centroids():
    from ..alerts import county_shapes

    table: Dict[Tuple[str, str], Tuple[float, float]] = {}
    for c in county_shapes().values():
        pts = [pt for poly in c["polys"] for pt in poly[0]]
        if pts:
            lon = sum(p[0] for p in pts) / len(pts)
            lat = sum(p[1] for p in pts) / len(pts)
            st = STATE_NAMES.get(str(c["state"]).lower(), str(c["state"]))
            table[(c["name"].lower(), st)] = (lat, lon)
    return table


_COUNTIES = None


def county_point(name: str, state: str) -> Optional[Tuple[float, float]]:
    global _COUNTIES
    if _COUNTIES is None:
        try:
            _COUNTIES = _county_centroids()
        except Exception:
            _COUNTIES = {}
    return _COUNTIES.get((name.lower(), state))


def _known_cities():
    from ..cities import cities
    from ..layers import discover

    discover()   # the metros join find_city's table when the layer types load
    out = {}
    for c in cities().values():
        out.setdefault(c.name.lower(), []).append(c)
    try:
        from ..post.acis import PLACES

        for key in PLACES:
            name, st = key.split(",")
            if not any(c.state == st for c in out.get(name, [])):
                out.setdefault(name, []).append(type("P", (), {"name": name.title(), "state": st, "lat": None, "lon": None})())
    except Exception:
        pass
    return out


NOT_PLACES = ("iowa environmental mesonet", "iowa state university", "texas a m", "penn state", "ohio state", "washington post",
              "new york times", "washington d c", "national weather service", "michigan state", "florida state university")


def find_places(seg: Segment, states_hint: Sequence[str]) -> List[Place]:
    out: List[Place] = []
    low = " " + re.sub(r"[^a-z ]+", " ", seg.text.lower()) + " "
    for org in NOT_PLACES:
        low = low.replace(f" {org} ", " " + "#" * len(org) + " ")
    masked = low
    for name in sorted(STATE_NAMES, key=len, reverse=True):
        for _hit in re.finditer(rf" {name} ", masked):
            out.append(Place(seg.id, name, "state", name.title(), STATE_NAMES[name]))
        masked = masked.replace(f" {name} ", " " + "#" * len(name) + " ")
    hint = [p.state for p in out] + list(states_hint)
    for name, cands in _known_cities().items():
        if re.search(rf" {re.escape(name)} ", low):
            pick = next((c for c in cands for s in hint if c.state == s), cands[0] if len(cands) == 1 else None)
            if pick is not None:
                out.append(Place(seg.id, name, "city", pick.name, pick.state, getattr(pick, "lat", None), getattr(pick, "lon", None)))
    for m in COUNTIES_AND.finditer(seg.text):
        for nm in (m.group(1), m.group(2)):
            out += _county(seg, nm, hint, m.group(0))
    for m in COUNTY.finditer(seg.text):
        words = m.group(1).split()
        while len(words) > 1 and words[0] in LEAD_WORDS:
            words = words[1:]
        out += _county(seg, " ".join(words), hint, m.group(0))
    for m in RIVER.finditer(seg.text):
        name = m.group(1)
        words = name.split()
        while words and words[0] in LEAD_WORDS:
            words = words[1:]
        if words:
            out.append(Place(seg.id, m.group(0), "river", f"{' '.join(words)} {m.group(2)}", hint[0] if hint else ""))
    for m in COORD.finditer(seg.text):
        lat, lon = float(m.group(1)), float(m.group(2))
        if 15 <= lat <= 72 and -170 <= lon <= -60:
            out.append(Place(seg.id, m.group(0), "coords", m.group(0), "", lat, lon))
    return out


def _county(seg: Segment, name: str, hint: Sequence[str], text: str) -> List[Place]:
    for st in list(dict.fromkeys(hint)):
        pt = county_point(name, st)
        if pt:
            return [Place(seg.id, text, "county", f"{name} County", st, pt[0], pt[1])]
    return [Place(seg.id, text, "county", f"{name} County", "")]


def find_storms(seg: Segment) -> List[StormMention]:
    out = []
    for m in STORM_NAME.finditer(seg.text):
        name = m.group(2)
        if name in NOT_NAMES:
            continue
        kind = m.group(1)
        if kind == "Storm" and name in ("Prediction", "Reports"):
            continue
        out.append(StormMention(seg.id, m.group(0), name.upper(), kind))
    return out


def topic_strengths(text: str) -> Dict[str, float]:
    low = _low(text)
    out = {}
    for topic, phrases in TOPIC_WORDS.items():
        s = sum((1.5 if " " in ph else 1.0) * _phrase_hits(low, ph) for ph in phrases)
        s -= sum(_phrase_hits(low, ph) for ph in TOPIC_NOT.get(topic, ()))
        if s > 0:
            out[topic] = s
    return out


def phase_of(text: str, index: int, count: int) -> str:
    low = _low(text)
    if index == count - 1 and _phrase_hits(low, "thanks for watching") + _phrase_hits(low, "follow your local") + _phrase_hits(low, "for the latest"):
        return "closing"
    best, score = "", 0.0
    for ph, words in PHASE_WORDS.items():
        s = sum(_phrase_hits(low, w) for w in words)
        if s > score:
            best, score = ph, s
    if best:
        return best
    return "setup" if index == 0 else "development"


# ---- the whole story -----------------------------------------------------------------------------------------------------------

def understand(segments: Sequence[Segment], recorded_at: Optional[datetime] = None, *, year_override: Optional[int] = None) -> Understanding:
    full = " ".join(s.text for s in segments)
    scores = score_categories(full)
    storms = [m for s in segments for m in find_storms(s)]
    category, hazards = pick_category(scores, storms)
    u = Understanding(category=category, scores=scores, hazards=hazards, storms=storms,
                      recorded_at=recorded_at.isoformat() if recorded_at else None)
    years = [(y, s.id) for s in segments for y, _i in find_years(s)]
    u.years = years
    ref = recorded_at.date() if recorded_at else None
    if year_override:
        year_hint = year_override
    elif years:
        counts = Counter(y for y, _ in years)
        top = max(counts.values())
        year_hint = next(y for y, _ in years if counts[y] == top)   # the most said; a tie goes to the first said
    else:
        year_hint = None
    if year_hint is None and ref is not None:
        year_hint = ref.year
        if any(_month_mentioned(s.text) for s in segments):
            u.assumptions.append(f"the script never says a year: the year of the recording ({ref.year}) is assumed for its dates")
    states: List[str] = []
    for s in segments:
        ps = find_places(s, states)
        u.places += ps
        states = list(dict.fromkeys(states + [p.state for p in ps if p.state]))
        # a date with no year: the year said in the same sentence, else the story's year (a record year said in passing, like
        # "the previous record, in nineteen eighty-nine", does not move the story)
        for sent in split_sentences(s.text):
            part = Segment(s.id, s.mode, sent)
            said = [y for y, _i in find_years(part)]
            u.dates += find_dates(part, said[0] if said else year_hint)
        u.dates += find_relative(s, ref)
        u.times += find_times(s)
        u.measurements += find_measurements(s)
    for i, s in enumerate(segments):
        u.topics[s.id] = topic_strengths(s.text)
        u.phases[s.id] = phase_of(s.text, i, len(segments))
    _resolve_weekdays_from_story(u)
    _resolve_weekdays_from_recording(u, segments, ref)
    unresolved = [d for d in u.dates if d.year_from == "unresolved"]
    if unresolved:
        u.ambiguities.append("the script says " + ", ".join(sorted({repr(d.text) for d in unresolved})) + " but neither a recording date "
                             "nor a nearby full date tells which day that is (set the recording date, or say the full date)")
    _check_weekdays(u, segments)
    return u


ABBREVIATIONS = ("U.S.", "U.K.", "Dr.", "St.", "Mt.", "Ft.", "a.m.", "p.m.", "No.", "Jan.", "Feb.", "Aug.", "Sept.", "Sep.", "Oct.",
                 "Nov.", "Dec.", "Mr.", "Mrs.", "Ms.", "vs.", "approx.", "Lt.", "Gov.", "Sen.", "Rep.")


def split_sentences(text: str) -> List[str]:
    """Sentences; never split after an abbreviation ("the U.S. Geological Survey", "6:05 a.m. Eastern")."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", str(text).strip())
    out: List[str] = []
    for p in parts:
        if out and any(out[-1].endswith(a) for a in ABBREVIATIONS):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return [p for p in out if p.strip()]


def _resolve_weekdays_from_recording(u: Understanding, segments: Sequence[Segment], ref: Optional[date]) -> None:
    """A weekday no full date explains is the last such day on or before the recording (the next one in a forecast)."""
    if ref is None:
        return
    text = {s.id: tokens(s.text) for s in segments}
    for d in u.dates:
        if d.year_from != "unresolved" or d.text not in WEEKDAYS:
            continue
        toks = text.get(d.seg, [])
        i = toks.index(d.text) if d.text in toks else 0
        future = _future_context(toks, i)
        delta = (WEEKDAYS[d.text] - ref.weekday()) % 7 if future else -((ref.weekday() - WEEKDAYS[d.text]) % 7)
        d.day, d.year_from = (ref + timedelta(days=delta)).isoformat(), "recording"


def _resolve_weekdays_from_story(u: Understanding) -> None:
    """A weekday with no recording date ("early Sunday morning") is the day with that name nearest a full date the story says,
    within three days of it; the choice is written to the assumptions."""
    anchors = sorted({date.fromisoformat(d.day) for d in u.dates if d.day and not d.relative})
    if not anchors:
        return
    done = set()
    for d in u.dates:
        if d.year_from != "unresolved" or d.text not in WEEKDAYS:
            continue
        best = None
        for a in anchors:
            for k in range(-3, 4):
                c = a + timedelta(days=k)
                if c.weekday() == WEEKDAYS[d.text] and (best is None or abs(k) < best[0]):
                    best = (abs(k), c, a)
        if best is not None:
            d.day, d.year_from = best[1].isoformat(), "story"
            if d.text not in done:
                done.add(d.text)
                u.assumptions.append(f"\"{d.text.title()}\" is read as {best[1]:%A %B %-d, %Y}, the {d.text.title()} nearest the date the "
                                     f"script says ({best[2]:%B %-d, %Y})")


def _month_mentioned(text: str) -> bool:
    return any(t in MONTHS for t in tokens(text))


def _check_weekdays(u: Understanding, segments: Sequence[Segment]) -> None:
    """A weekday said in the same segment as a full date must be that date's weekday; a mismatch is an ambiguity."""
    for s in segments:
        absolute = [d for d in u.dates if d.seg == s.id and not d.relative and d.day]
        days = [t for t in tokens(s.text) if t in WEEKDAYS]
        for d in absolute:
            wd = date.fromisoformat(d.day).strftime("%A").lower()
            for w in days:
                if w != wd and len(absolute) == 1 and len(set(days)) == 1:
                    u.ambiguities.append(f"beat {s.id} says {w.title()} and {d.text} ({d.day}), which was a {wd.title()}")


def event_text_days(u: Understanding) -> List[str]:
    """Every distinct ISO day the narration names, in story order."""
    return list(dict.fromkeys(d.day for d in u.dates if d.day))
