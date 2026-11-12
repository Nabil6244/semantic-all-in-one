"""Aviation narration router: sentence -> mode + extracted values, and a whole script -> modes with a carried flight state.

    extract_values(text) -> {times, fuel_kg, altitude_ft, distance_km, speed_kt, counts, money, percent, flights, dates}
    classify(text)       -> Classification(mode, scores, reasons, values, airlines, aircraft, airports, radio)
    route_script(lines)  -> [Classification] with .state = the flight state so far {flight, time, fuel_kg, altitude_ft, airport}

Modes (docs/aviation/PLAN.md section 2):
    news      business / corporate / dated events      -> Plane Curious look: real clip bursts + blue article cards
    flight    what the aircraft and crew are doing      -> Vistara look: dark map, gold route, clock/fuel HUD
    weather   storms, monsoon, gusts, visibility        -> dark map with storm cells, weather icons
    fleet     aircraft types, seats, range, cabins      -> beauty footage, spec / seat cards, 3D aircraft
    numbers   money, percentages, profit and loss       -> big number / chart cards
    evidence  investigation, report, court, regulator   -> report pages with highlighted lines
    people    captain, first officer, executives        -> name cards, crew counters
Pure rules and word lists: no network, no model calls (a CSV run must make zero Gemini calls). Every point is logged in .reasons.
A sentence that scores nothing is neutral: alone it is 'news'; inside route_script it takes its neighbours' mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import catalog as C

MODES = ("news", "flight", "weather", "fleet", "numbers", "evidence", "people")
NEUTRAL_BELOW = 1.0

_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"), 1)}
_MONTH_RE = "(" + "|".join(_MONTHS) + ")"

# (mode, weight, phrases). Phrases are matched word-bounded on lower-case text; a trailing * allows any word ending.
_WORDS: Tuple[Tuple[str, float, Tuple[str, ...]], ...] = (
    ("news", 2.0, ("announc*", "confirm*", "launch*", "unveil*", "deal", "deals", "merger", "acquir*", "takeover", "subsidiary",
                   "strike", "strikes", "restructur*", "bankrupt*", "collapse*", "ceased operations", "rebrand*", "codenamed",
                   "joint venture", "partnership", "order", "orders", "ordered", "rejected", "cancel*", "competition", "competitor*",
                   "undercut*", "market share", "new airline", "low-cost", "low cost", "budget airline", "flag carrier")),
    ("news", 1.0, ("plan", "plans", "strategy", "workers", "union*", "jobs", "brand", "network", "routes", "hub", "hubs", "launch",
                   "management", "government", "carrier", "carriers", "industry", "cut", "cuts", "nervous", "rival*")),
    ("flight", 2.0, ("take off", "takes off", "took off", "taking off", "takeoff", "climb*", "descen*", "cruis*", "divert*",
                     "diversion", "holding pattern", "the hold", "a hold", "go-around", "go around", "approach", "landed",
                     "landing", "touchdown", "touched down", "taxi*", "pushed back", "push back", "pushback", "runway", "fuel",
                     "mayday", "flight level", "airborne", "overhead", "en route", "alternate", "short hop")),
    ("flight", 1.0, ("airport", "tower", "air traffic control", "atc", "cleared", "heading", "towards", "minutes", "crew",
                     "cockpit", "autopilot", "altitude", "feet", "knots", "boarding", "departure", "arrival", "gate")),
    ("weather", 2.0, ("storm", "storms", "stormy", "storm cell*", "thunderstorm*", "monsoon", "weatherreport", "hail*", "gust*", "turbulence", "lightning", "cumulonimbus",
                      "windshear", "wind shear", "rain*", "fog", "visibility", "cloud*", "blizzard", "snowstorm", "typhoon",
                      "cyclone", "hurricane")),
    ("weather", 1.0, ("weather", "wind", "winds", "haze", "dust", "forecast", "metar", "sky", "skies", "heat", "hot")),
    ("fleet", 2.0, ("seats", "seat", "range", "cabin", "cabins", "business class", "premium economy", "first class",
                    "economy", "configuration", "engine*", "fuselage", "wing*", "variant*", "stretch*", "delivery", "deliveries",
                    "certification", "certified", "prototype", "fleet")),
    ("fleet", 1.0, ("aircraft", "airliner*", "jet", "jets", "widebod*", "narrowbod*", "efficien*", "payload", "capacity")),
    ("numbers", 2.0, ("profit*", "loss", "losses", "revenue*", "margin*", "billion", "million", "price*",
                      "fare*", "yield*", "debt", "per cent", "percent")),
    ("numbers", 1.0, ("cost", "costs")),
    ("evidence", 2.0, ("investigat*", "report", "reports", "inquiry", "findings", "found that", "court", "judge", "regulator*",
                       "aaib", "ntsb", "dgca", "bea", "recommendation*", "probable cause", "transcript", "black box",
                       "flight data recorder", "cockpit voice recorder")),
    ("evidence", 1.0, ("found", "document*", "according to", "concluded", "blamed")),
    ("people", 2.0, ("captain", "first officer", "co-pilot", "copilot", "logbook", "flying hours", "chief executive", "ceo",
                     "founder", "chairman", "president")),
    ("people", 1.0, ("pilot", "pilots", "hours", "years old", "experience", "his", "her", "cabincrew")),
)

# compounds whose parts belong to other modes are joined before the word lists run ('cabin crew' is people, not a cabin;
# a 'weather report' is weather, not an investigation report)
_COMPOUNDS = (("cabin crew", "cabincrew"), ("weather report", "weatherreport"), ("weather reports", "weatherreport"))

_RADIO_PHRASES = r"\b(request|requesting|cleared|roger|copy|wilco|climb to|climb and maintain|descend|maintain|contact|mayday|pan pan|squawk|orbit|join the hold|report)\b"


def _word_re(phrase: str) -> re.Pattern:
    star = phrase.endswith("*")
    body = r"\s+".join(re.escape(p) for p in phrase.rstrip("*").split())
    return re.compile(r"(?<![a-z0-9])" + body + (r"[a-z\-]*" if star else r"(?![a-z0-9])"))


_COMPILED = tuple((mode, w, tuple((p, _word_re(p)) for p in phrases)) for mode, w, phrases in _WORDS)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _intish(v: float):
    return int(round(v)) if abs(v - round(v)) < 1e-9 else v


# ---------------------------------------------------------------------------------------------------------------- values

_COUNT_NOUNS = ("cabin crew", "flight attendants", "passengers", "pilots", "crew", "seats", "aircraft", "jets", "planes", "freighters",
                "routes", "destinations", "jobs", "employees", "staff", "flights", "hours", "years", "airports", "engines")
_MULT = {"trillion": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3}
_CUR_SYM = {"$": "USD", "us$": "USD", "€": "EUR", "£": "GBP"}
_CUR_WORD = {"dollars": "USD", "dollar": "USD", "usd": "USD", "euros": "EUR", "euro": "EUR", "eur": "EUR", "pounds": "GBP",
             "gbp": "GBP"}
_CODE_EXCLUDE = {"FL", "MD", "DC", "CS", "ER", "LR", "XL", "XW", "Q4", "Z4", "E1", "E2", "MK"}


_WORDNUM = {w: i for i, w in enumerate(("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                          "sixteen seventeen eighteen nineteen twenty").split())}
_WORDNUM.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100})
_MULTS = r"(?:trillion|billion|bn|million|thousand|percent|per\s+cent|%)"


def _digits(low: str) -> str:
    """Word numbers as digits ('five new freighters' -> '5 new freighters'), for counts and changes only."""
    return re.sub(r"\b(" + "|".join(_WORDNUM) + r")\b", lambda m: str(_WORDNUM[m.group(1)]), low)


def extract_values(text: str) -> Dict[str, Any]:
    t = str(text or "")
    low = t.lower()
    v: Dict[str, Any] = {k: [] for k in ("times", "fuel_kg", "altitude_ft", "distance_km", "speed_kt", "counts", "money",
                                         "percent", "flights", "dates", "changes")}

    for m in re.finditer(r"\b(\d{1,2}):(\d{2})\s*(?:([ap])\.?\s?m\b\.?)?", low):
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        if ap == "p" and h < 12:
            h += 12
        elif ap == "a" and h == 12:
            h = 0
        if h < 24 and mi < 60:
            v["times"].append(f"{h:02d}:{mi:02d}")

    fuel_word = "fuel" in low
    for m in re.finditer(_NUM + r"\s*(kg|kgs|kilograms?|kilos?|tonnes?|tons?)\b", low):
        n, unit = _num(m.group(1)), m.group(2)
        if unit.startswith(("kg", "kilo")):
            v["fuel_kg"].append(_intish(n))
        elif fuel_word:
            v["fuel_kg"].append(_intish(round(n * 1000, 3)))

    alts: List[Tuple[int, int]] = []
    for m in re.finditer(r"\b(?:flight level|fl)\s*(\d{2,3})\b", low):
        alts.append((m.start(), int(m.group(1)) * 100))
    for m in re.finditer(_NUM + r"\s*(feet|foot|ft)\b", low):
        alts.append((m.start(), int(_num(m.group(1)))))
    v["altitude_ft"] = [a for _, a in sorted(alts)]

    dists: List[Tuple[int, int]] = []
    for m in re.finditer(_NUM + r"\s*(km|kilomet(?:re|er)s?)\b", low):
        dists.append((m.start(), int(round(_num(m.group(1))))))
    for m in re.finditer(_NUM + r"\s*(nautical miles?|nm)\b", low):
        dists.append((m.start(), int(round(_num(m.group(1)) * 1.852))))
    for m in re.finditer(_NUM + r"\s*miles?\b", low):
        dists.append((m.start(), int(round(_num(m.group(1)) * 1.609))))
    v["distance_km"] = [d for _, d in sorted(dists)]

    for m in re.finditer(_NUM + r"\s*(knots|kts|kt)\b", low):
        v["speed_kt"].append(_intish(_num(m.group(1))))

    nouns = "|".join(re.escape(n) for n in sorted(_COUNT_NOUNS, key=len, reverse=True))
    dlow = _digits(low)
    craft_names = " ".join(a.matched.lower() for a in C.find_aircraft(t))
    # a number, up to three describing words (a type name like 'Boeing 777' may sit between), then the counted noun. Never across
    # 'million' / 'billion' / 'percent' ('53.2 million passengers' is not a crew of 53), never a number that is an aircraft type
    for m in re.finditer(r"(?<![\d.,])" + _NUM + r"((?:\s+(?:[a-z\-]+|\d{3}[a-z]?)){0,3}?)\s+(" + nouns + r")\b", dlow):
        between = m.group(2) or ""
        if re.search(_MULTS, between) or re.match(r"\s*" + _MULTS, dlow[m.end(1):]):
            continue
        if "." in m.group(1):
            continue                                           # 3.5 crews is not a count
        if re.search(r"(?<!\d)" + re.escape(m.group(1)) + r"(?!\d)", craft_names):
            continue                                           # '777 freighters': 777 is the type, not a number of them
        v["counts"].append((_intish(_num(m.group(1))), m.group(3)))
    # vertical speed, runway, runway length, a crew member's age
    for m in re.finditer(_NUM + r"\s*(?:feet|ft)\s+(?:per|a)\s+minute|" + _NUM + r"\s*fpm\b", low):
        n = _num(m.group(1) or m.group(2))
        down = re.search(r"\b(sink\w*|descen\w*|down|drop\w*|fall\w*|plung\w*)\b", low)
        v.setdefault("vs_fpm", []).append(-int(n) if down else int(n))
    v["runways"] = [m.group(1).upper() for m in re.finditer(r"\brunway\s+(\d{1,2}[lrc]?)\b", low)]
    v["length_m"] = [int(_num(m.group(1))) for m in re.finditer(_NUM + r"\s*(?:metres|meters|m)\b(?!\w)", low)]
    m = re.search(r"\b(?:is|aged|age)\s+(\d{2})\b|\b(\d{2})-year-old\b|\((\d{2})\)", low)
    v["age"] = int(next(g for g in m.groups() if g)) if m else None
    # 'from 3.1 billion dollars to one billion': a change, the unit of the first carried to the second
    for m in re.finditer(r"\bfrom\s+(\$)?" + _NUM + r"\s*(trillion|billion|bn|million|thousand)?\s*(dollars?|euros?|pounds)?\s+to\s+(\$)?"
                         + _NUM + r"\s*(trillion|billion|bn|million|thousand)?", dlow):
        m1 = _MULT.get(m.group(3) or "", 1.0)
        m2 = _MULT.get(m.group(7) or "", m1)
        cur = "USD" if (m.group(1) or m.group(5) or (m.group(4) or "").startswith("dollar")) else \
            ("EUR" if (m.group(4) or "").startswith("euro") else ("GBP" if (m.group(4) or "").startswith("pound") else ""))
        v["changes"].append((cur, round(_num(m.group(2)) * m1, 2), round(_num(m.group(6)) * m2, 2)))

    for m in re.finditer(r"(us\$|\$|€|£)\s?" + _NUM + r"(?:\s*(trillion|billion|bn|million|m|thousand)\b)?", low):
        mult = _MULT.get(m.group(3) or "", 1.0)
        v["money"].append((_CUR_SYM[m.group(1)], round(_num(m.group(2)) * mult, 2)))
    for m in re.finditer(r"(?<![$€£\d.,])" + _NUM + r"\s*(trillion|billion|bn|million|thousand)?\s*(dollars?|usd|euros?|eur|pounds|gbp)\b", low):
        mult = _MULT.get(m.group(2) or "", 1.0)
        v["money"].append((_CUR_WORD[m.group(3)], round(_num(m.group(1)) * mult, 2)))

    for m in re.finditer(_NUM + r"\s*(%|percent\b|per cent\b)", low):
        v["percent"].append(_num(m.group(1)))

    aircraft_spans = [(a.start, a.end) for a in C.find_aircraft(t)]
    for a in C.find_airlines(t):
        # 'Vistara 611' or the spoken form 'Vistara 6-1-1' / 'Vistara 6 1 1'
        m = re.match(r"\s+(\d{2,4}|\d(?:[\- ]\d){1,3})\b(?![\-\w])", t[a.end:])
        if m and not any(s <= a.end + m.start(1) < e for s, e in aircraft_spans):
            number = re.sub(r"[\- ]", "", m.group(1))
            v["flights"].append(f"{a.entry['name'] if a.matched.isupper() else a.matched} {number}")
    for m in re.finditer(r"\b([A-Z]{2}|[A-Z]\d|\d[A-Z])(\d{2,4})\b", t):
        if m.group(1) not in _CODE_EXCLUDE and not any(s <= m.start() < e for s, e in aircraft_spans):
            v["flights"].append(m.group(0))

    dates: List[Tuple[int, str]] = []
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_RE + r",?\s+(\d{4})\b", low):
        dates.append((m.start(), f"{int(m.group(3)):04d}-{_MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"))
    for m in re.finditer(_MONTH_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", low):
        dates.append((m.start(), f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"))
    v["dates"] = [d for _, d in sorted(dates)]
    return v


# ---------------------------------------------------------------------------------------------------------------- classify

@dataclass
class Classification:
    text: str
    mode: str
    scores: Dict[str, float]
    reasons: List[str]
    values: Dict[str, Any]
    airlines: List[dict] = field(default_factory=list)
    aircraft: List[dict] = field(default_factory=list)
    airports: List[dict] = field(default_factory=list)
    radio: bool = False
    neutral: bool = False
    state: Dict[str, Any] = field(default_factory=dict)


def _is_radio(text: str, airlines: Sequence[C.Match]) -> bool:
    t = text.strip()
    quoted = bool(re.match(r"^[\"“'‘]", t)) or bool(re.search(r"[\"“][^\"”]{6,}[\"”]", t))
    callsign = any(a.start < 40 for a in airlines) and bool(re.search(r"\b\d{2,4}\s*,", t))
    return (quoted or callsign) and bool(re.search(_RADIO_PHRASES, t.lower()))


def classify(text: str) -> Classification:
    t = str(text or "")
    low = t.lower()
    scores = {m: 0.0 for m in MODES}
    reasons: List[str] = []

    def add(mode: str, pts: float, why: str) -> None:
        scores[mode] += pts
        reasons.append(f"{mode} +{pts:g} {why}")

    words_text = re.sub(r"\s+", " ", low)
    for a, b in _COMPOUNDS:
        words_text = words_text.replace(a, b)
    for mode, w, pats in _COMPILED:
        for phrase, rx in pats:
            if rx.search(words_text):
                add(mode, w, f"'{phrase.rstrip('*')}'")

    vals = extract_values(t)
    airlines = C.find_airlines(t)
    aircraft = C.find_aircraft(t)
    airports = C.find_airports(t)
    if vals["times"]:
        add("flight", 1.0, "clock time")
    if vals["fuel_kg"]:
        add("flight", 2.0, "fuel amount")
    if vals["altitude_ft"]:
        add("flight", 1.5, "altitude")
    if vals["speed_kt"]:
        add("flight", 1.0, "speed")
    if vals["distance_km"]:
        add("flight", 0.5, "distance")
    if vals["flights"]:
        add("flight", 2.0, "flight number")
    if vals["money"]:
        add("numbers", 2.0, "money")
    if vals["percent"]:
        add("numbers", 2.0, "percentage")
    if vals["dates"]:
        add("news", 1.0, "full date")
    if any(n == "seats" for _, n in vals["counts"]):
        add("fleet", 1.0, "seat count")
    if any(n in ("cabin crew", "crew", "pilots", "passengers", "flight attendants") for _, n in vals["counts"]):
        add("people", 1.5, "count of people on board")
    specific_types = [a for a in aircraft if a.entry is not None]
    if specific_types:
        add("fleet", 1.5, "aircraft type " + specific_types[0].matched)
    if airlines:
        add("news", 0.5, "airline " + airlines[0].matched)
    if airports:
        add("flight", 0.5 * min(len(airports), 2), "airport " + airports[0].matched)
    radio = _is_radio(t, airlines)
    if radio:
        add("flight", 3.0, "radio call")

    top = max(scores.values())
    neutral = top < NEUTRAL_BELOW
    # ties keep MODES order (news first), so a neutral line is 'news'
    mode = "news" if neutral else max(MODES, key=lambda m: (scores[m], -MODES.index(m)))
    return Classification(t, mode, scores, reasons, vals, [a.entry for a in airlines if a.entry],
                          [a.entry for a in specific_types], [a.entry for a in airports if a.entry], radio, neutral)


# ---------------------------------------------------------------------------------------------------------------- script

def route_script(lines: Sequence[str]) -> List[Classification]:
    out = [classify(s) for s in lines]
    # neutral lines take the previous decided mode (or the next one at the start of the script)
    for i, c in enumerate(out):
        if not c.neutral:
            continue
        prev = next((out[j].mode for j in range(i - 1, -1, -1) if not out[j].neutral), None)
        nxt = next((out[j].mode for j in range(i + 1, len(out)) if not out[j].neutral), None)
        c.mode = prev or nxt or "news"
        c.reasons.append(f"neutral -> {c.mode} from {'previous' if prev else 'next' if nxt else 'default'} line")
    state: Dict[str, Any] = {"flight": None, "time": None, "fuel_kg": None, "altitude_ft": None, "airport": None}
    for c in out:
        v = c.values
        if v["flights"]:
            state["flight"] = v["flights"][-1]
        if v["times"]:
            state["time"] = v["times"][-1]
        if v["fuel_kg"]:
            state["fuel_kg"] = v["fuel_kg"][-1]
        if v["altitude_ft"]:
            state["altitude_ft"] = v["altitude_ft"][-1]
        if c.airports:
            state["airport"] = c.airports[-1]["id"]
        c.state = dict(state)
    return out
