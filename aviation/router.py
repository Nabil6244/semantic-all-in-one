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
    story     founded, formed, split, merged, owned, government, renamed, national airline; or (route_script) a year more than
              15 years before the latest year of the script -> sticker stage. Words weigh 2.5 so a story line beats the news words it
              shares (merger, rebrand), but never a clear flight / weather / evidence line. values['years'] = the years named.
Pure rules and word lists: no network, no model calls (a CSV run must make zero Gemini calls). Every point is logged in .reasons.
A sentence that scores nothing is neutral: alone it is 'news'; inside route_script it takes its neighbours' mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import catalog as C

MODES = ("news", "flight", "weather", "fleet", "numbers", "evidence", "people", "story")
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
    ("story", 2.5, ("founded", "formed", "established", "split", "splits", "merged", "merger", "joint venture", "owned", "owner*",
                    "ownership", "stake", "shares", "independence", "renamed", "rebrand*", "flag carrier", "national airline",
                    "national carrier", "spun off", "sold off")),
    ("story", 1.5, ("government", "governments")),
    ("story", 2.5, ("independent", "inherited", "inherit", "divided", "divide", "kept the", "took over", "handed over",
                    "colony", "federation", "nationalised", "nationalized", "privatised", "privatized")),
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
                                         "percent", "flights", "dates", "changes", "years")}

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
    # years: a bare 4-digit 1900-2099 ('in 1966'), not part of a bigger number and not a measure ('1950 feet', '2000 kg')
    unit = r"(?!\s*(?:feet|foot|ft|kg|kgs|km|nm|miles?|metres|meters|m\b|knots|kts?|%|percent|per\s+cent|seats|passengers|fpm|"
    unit += r"jobs|aircraft|crew|employees|staff|flights|hours))"
    yrs = [(m.start(), int(m.group(1))) for m in re.finditer(r"(?<![\d,.$€£:\-])(19\d\d|20\d\d)(?![\d,]|\.\d)" + unit, t)]
    yrs += [(0, int(d[:4])) for d in v["dates"]]
    seen_y: List[int] = []
    for _, y in sorted(yrs):
        if y not in seen_y:
            seen_y.append(y)
    v["years"] = seen_y
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


def _decide(scores: Dict[str, float]) -> Tuple[str, bool]:
    neutral = max(scores.values()) < NEUTRAL_BELOW
    # ties keep MODES order (news first), so a neutral line is 'news'
    return ("news" if neutral else max(MODES, key=lambda m: (scores[m], -MODES.index(m)))), neutral


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

    mode, neutral = _decide(scores)
    return Classification(t, mode, scores, reasons, vals, [a.entry for a in airlines if a.entry],
                          [a.entry for a in specific_types], [a.entry for a in airports if a.entry], radio, neutral)


# ---------------------------------------------------------------------------------------------------------------- script

_HISTORY = re.compile(r"\bfounded\b|\bformed\b|\bestablished\b|\brenamed\b|\brebrand\w*|\bsplit\w*|\bmerged\b|\bmerger\b|"
                      r"\bjoint venture\b|\bindependen\w*|\bflag carrier\b|\bnational airline\b|\bcreated\b|\bfirst (?:aircraft|flight)\b|"
                      r"\bbegan\b|\bdecades?\b|\bcentury\b|\bhistory\b|\bcolon\w*", re.I)
_FLIGHT_ACT = re.compile(r"\btook off\b|\btakes? off\b|\btaking off\b|\blanded\b|\btouch(?:ed|es)? down\b|\bdescend\w*|"
                         r"\bon approach\b|\bthe crew\b|\bthe captain\b|\bfirst officer\b|\bair traffic\b|\batc\b|\bdiverted\b|"
                         r"\bholding pattern\b|\bcruising altitude\b|\bmayday\b", re.I)


def has_flight_story(cls: Sequence["Classification"]) -> bool:
    """True when the script tells a flight: a flight number, a clock time, fuel or an altitude, or at least two lines of what an
    aircraft / crew is doing (take-off, landing, descent, ATC ...)."""
    if any(c.values.get(k) for c in cls for k in ("flights", "times", "fuel_kg", "altitude_ft")):
        return True
    return sum(1 for c in cls if _FLIGHT_ACT.search(c.text)) >= 2


# a place line in a script that tells no flight: the map shows WHERE (a route network, a region the airline serves). 'hub' alone
# ('Lisbon is about to become a fortress hub') is a strategy line, not a map: with one place it needs a route / geography word
_GEO = re.compile(r"\bmap\b|\broutes?\b|\bnetwork\b|\bdestinations?\b|\bconnect\w*|\blink\w*|\bserv(?:e|es|ed|ing)\b|"
                  r"\bflights? (?:to|from|between)\b|\bflew to\b|\bfl(?:y|ies) to\b|\bcrossing\b|\bacross the\b|\bocean\b|\batlantic\b|"
                  r"\bpacific\b|\bcontinents?\b|\bedge of\b|\bgateway\b|\bjumping-off\b|\bcoast\b|\bislands?\b", re.I)
# regions a narration names without an airport -> the main airport(s) that stand for them on the map (only ids the catalog has are used)
_REGIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (r"\bsouth atlantic\b", ("GIG",)), (r"\bbrazil\w*", ("GRU",)), (r"\bsouth(?: and central)? america\b", ("BOG",)),
    (r"\blatin america\b", ("BOG",)), (r"\bnorth atlantic\b", ("JFK",)), (r"\bnorth america\b", ("ORD",)),
    (r"\bunited states\b|\bthe us\b|\bamerica\b", ("JFK",)),
    (r"\bportuguese-speaking africa\b|\blusophone africa\b|\bangola\b|\bmozambique\b", ("LAD", "MPM")), (r"\bafrica\w*", ("NBO",)),
    (r"\bmiddle east\b|\bthe gulf\b", ("DXB",)), (r"\basia\w*", ("SIN",)), (r"\bchina\b", ("PEK",)),
    (r"\bjapan\b", ("HND",)), (r"\bindia\b", ("DEL",)), (r"\baustralia\b", ("SYD",)))


def region_airports(text: str) -> List[str]:
    """Anchor airports for the regions a line names ('Brazil', 'the South Atlantic', 'Africa'), in order of mention, once each."""
    hits = []
    # 'Instead of Asia and the North Atlantic, its strength is ...': a region the line turns away from is not on the map
    skip = [(m.start(), m.end()) for m in re.finditer(r"\b(?:instead of|rather than|unlike|apart from|not)\b[^,.;]*", text, re.I)]
    for pat, ids in _REGIONS:
        for m in re.finditer(pat, text, re.I):
            if any(a <= m.start() < b for a, b in skip):
                continue
            hits.append((m.start(), m.end(), [i for i in ids if C.get_airport(i)]))
    out: List[str] = []
    spans: List[Tuple[int, int]] = []
    for a, b, ids in sorted(hits, key=lambda h: (h[0], -(h[1] - h[0]))):      # the longest name wins ('North America' over 'America')
        if any(a < y and x < b for x, y in spans):
            continue
        spans.append((a, b))
        out += [i for i in ids if i not in out]
    return out


def plain_years(text: str) -> List[int]:
    """Every 1900-2099 year in the text, also one before a comma ('in 1946, it went'), which extract_values leaves out."""
    return [int(y) for y in re.findall(r"(?<![\d,.$€£:\-])\b(19\d\d|20\d\d)\b(?!\.\d|,\d)", text)]


def is_place_line(c: "Classification") -> bool:
    """A line about places, not a flight: two or more airports / cities, or a place or region with route / geography words
    ('a natural jumping-off point for the Atlantic', 'routes to the United States', 'a small hub with a big map')."""
    aps = {a["id"] for a in c.airports}
    if len(aps) >= 2:
        return True
    return bool((aps or region_airports(c.text)) and _GEO.search(c.text))


def route_script(lines: Sequence[str]) -> List[Classification]:
    out = [classify(s) for s in lines]
    # story: a line about a year far (> 15 years) before the latest year of the script, unless it is clearly flight / weather / evidence
    all_years = [y for c in out for y in c.values.get("years", ())]
    if all_years:
        latest = max(all_years)
        for c in out:
            old = [y for y in c.values.get("years", ()) if latest - y > 15]
            if old and max(c.scores[m] for m in ("flight", "weather", "evidence")) < 3.0:
                c.scores["story"] += 3.0
                c.reasons.append(f"story +3 year {old[0]} is {latest - old[0]} years before {latest}")
                c.mode, c.neutral = _decide(c.scores)
    # story is history: on a line about the present (no year > 15 years back, no founding / renaming / split / merger words)
    # ownership and government words ('stake', 'owned', 'government', 'majority') describe today's deal, a news line
    if all_years:
        for c in out:
            if c.mode != "story":
                continue
            old = [y for y in c.values.get("years", ()) if latest - y > 15]
            if not old and not _HISTORY.search(c.text):
                c.scores["story"] = min(c.scores.get("story", 0.0), 1.0)
                c.mode, c.neutral = _decide(c.scores)
                c.reasons.append("story 1: a present-day line (no old year, no history words)")
    # flight needs a flight: a script that never tells one (no flight number, clock time, fuel, altitude, take-off / landing /
    # ATC words) is a business or history story; its 'runway', 'airport', 'climbed back' lines are not a flight sequence
    # ... but a PLACE line (two airports, or a place / region with route words) still gets the map: where the airline flies, its hub,
    # its network - the map look without a flight on it (no clock / fuel HUD: those need the script's own times and fuel)
    if not has_flight_story(out):
        # years read plainly here ('in 1946, it went ...' is a year too; extract_values skips a year before a comma)
        yrs = [plain_years(c.text) for c in out]
        top = max([y for ys in yrs for y in ys] or [0])
        # each line's look with no flight score: a place line that would be (or sit inside) a story line is history - it keeps the
        # sticker stage, which draws its own route card ('Malaysia-Singapore Airlines flew its 707 to London that year')
        bare = [_decide(dict(c.scores, flight=0.0)) for c in out]

        def story_around(k: int) -> bool:
            if bare[k][0] == "story" and not bare[k][1]:
                return True
            if max(v for m, v in out[k].scores.items() if m != "flight") >= 3.0:
                return False                        # a strong line of its own (news, numbers ...) is not pulled into the story
            # a weak or neutral line right after a story line joins the stage (planner._story_join does the same)
            return k > 0 and bare[k - 1][0] == "story" and not bare[k - 1][1]

        for k, c in enumerate(out):
            history = any(top - y > 15 for y in yrs[k]) or c.mode == "story" or story_around(k)
            if is_place_line(c) and not history:
                c.scores["flight"] = max(c.scores.get("flight", 0.0), 3.0, max(c.scores.values()) + 0.5)
                c.mode, c.neutral = _decide(c.scores)
                c.values["place_map"] = True
                c.reasons.append("map: a place line (airports / regions with route words) in a script with no flight")
            elif c.mode == "flight" or c.scores.get("flight", 0) > 0:
                c.scores["flight"] = 0.0
                c.mode, c.neutral = _decide(c.scores)
                c.reasons.append("flight 0: the script tells no flight")
    # neutral lines take the previous decided mode (or the next one at the start of the script)
    for i, c in enumerate(out):
        if not c.neutral:
            continue
        # a place-map line lends its look to no one: 'It is the runway.' after a route line is a business line, not more map
        prev = next((out[j].mode for j in range(i - 1, -1, -1) if not out[j].neutral and not out[j].values.get("place_map")), None)
        nxt = next((out[j].mode for j in range(i + 1, len(out)) if not out[j].neutral and not out[j].values.get("place_map")), None)
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
