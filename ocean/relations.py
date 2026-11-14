"""What a narration sentence SAYS about its nouns, so the picture can follow it line by line (the reference channel's
habit: every sentence gets its own small scene built from its own words).

    read(text, animals) -> Rel

    Rel.inside      [animal keys] eaten / found inside the predator     "had two harp seals inside it"  -> stomach x-ray
    Rel.above       (top animal, bottom animal, surface word)            "seals sleep in the water away from polar bears
                                                                          up on the ice"                -> cross-section
    Rel.place       "Newfoundland"                                       "two men in Newfoundland"      -> map pin
    Rel.speed       [(label, km/h, shown)] + Rel.speed_title             "cruising speed 1.2 km an hour. You walk faster"
                                                                                                        -> speed bars
    Rel.air         (calm, panicking multiple)                           "panicking divers use air 3 times faster"
    Rel.temp        "-1.5 °C"                                            "the water is -1.5 degrees"    -> temperature tag
    Rel.era         (name, "94 million years ago", order 0..1)           "the Cretaceous"               -> time dial + title
    Rel.verdict     "rules" | "survives" | "dies"                        "it wouldn't survive"          -> verdict stamp
    Rel.part        "eye" | "mouth" | "tail" | ...                       "about those eyes"             -> anatomy close-up
    Rel.latin       True                                                 "its scientific name means"    -> Latin name card
    Rel.unverified  True                                                 "the 7 m monsters online were never verified"
    Rel.age         (year, event)                                        "before the United States existed" / "400 years
                                                                          old"                          -> year anchor
    Rel.fraction    (lit, of)                                            "a third of 45 sharks", "nine in 10"
    Rel.photo       True                                                 "pulled one out", "photographed", "weighed"
    Rel.question    True                                                 a plain question (no choices)  -> "?" over it

Shape words only, no topic constants: any animal, any place the map data knows, any year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

THIS_YEAR = 2026

INSIDE = re.compile(r"\b(inside (?:it|its|them|their|one|the)|in (?:its|their|the) (?:stomach|belly|gut)s?|stomachs?|"
                    r"swallowed|had eaten|found in (?:its|their)|bellies|belly)\b", re.I)
ON_TOP = re.compile(r"\b((?:up )?on (?:the )?(ice|sea ice|ice floes?|land|beach|shore|surface|rocks?|boat)|above (?:the )?water)\b",
                    re.I)
BELOW = re.compile(r"\b(in the water|below|beneath|under(?:neath)?|underwater|down there)\b", re.I)
UNVERIFIED = re.compile(r"\b(never (?:been )?(?:verified|confirmed|proven|measured properly)|unverified|unconfirmed|rumou?rs?|"
                        r"online|legends?|supposedly|reportedly|claimed|claims)\b", re.I)
LATIN = re.compile(r"\b(scientific name|latin name|its name means|name literally means|named it)\b", re.I)
PARTS = [  # (pattern, part) first wins
    (r"\beyes?\b|\bretinas?\b|\beyesight\b|\bblind\b", "eye"),
    (r"\b(teeth|tooth|jaws?|bite|mouth)\b", "mouth"),
    (r"\b(nose|snout|nostrils?|smell|scent)\b", "nose"),
    (r"\b(tail|tail ?fin|tail beats?|tail swept)\b", "tail"),
    (r"\b(gills?)\b", "gills"),
    (r"\b(liver)\b", "liver"),
    (r"\b(skin|scales|denticles)\b", "skin"),
    (r"\b(dorsal fin|fins?)\b", "fin"),
    (r"\b(brain)\b", "brain"),
    (r"\b(heart|heartbeat)\b", "heart"),
    (r"\b(electric(?:al)? fields?|electroreception|ampullae)\b", "sense"),
]
_PARTS = [(re.compile(p, re.I), n) for p, n in PARTS]
PART_ASK = re.compile(r"\b(those|its|their|the|his|her|this|that|an?)\s+\w*\s*(eyes?|teeth|jaws?|mouth|nose|snout|tail|gills?|"
                      r"liver|skin|fins?|brain|heart|retinas?|electric(?:al)? fields?)\b", re.I)
PHOTO = re.compile(r"\b(photograph(?:ed|s)?|photos?|pictures? of|pulled (?:one|it|a|out)|hauled|landed|caught (?:one|a|in)|"
                   r"washed up|weighed|on (?:the )?dock|in a net|bycatch)\b", re.I)
SPEED_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>km/h|kph|mph|knots?|(?:km|kilomet(?:er|re)s?|miles?)\s*(?:an|per|/)\s*hour)",
                      re.I)
TEMP_RE = re.compile(r"(?P<neg>-|−|minus\s+)?(?P<num>\d+(?:\.\d+)?(?:\s*1/2)?)\s*(?:°\s*(?P<u1>[CF])?|degrees?(?:\s+(?P<u2>celsius|"
                     r"fahrenheit|c\b|f\b))?)", re.I)
AIR = re.compile(r"\b(air|breath(?:ing)?|oxygen|tank)\b", re.I)
PANIC = re.compile(r"\b(panic\w*|stress\w*|scared|fear|frighten\w*)\b", re.I)
TIMES = re.compile(r"\b(\d+(?:\.\d+)?|two|three|four|five|twice)\s*(?:times|x)\b", re.I)
FRACTION = re.compile(r"\b(a third|one third|a half|half|a quarter|two thirds|(\d+|one|two|three|four|five|six|seven|eight|nine)"
                      r" (?:in|out of) (\d+|ten))\b", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "twice": 2}
VERDICTS = [
    (r"\b(rules?|ruled|top predator|king of|dominat\w+|apex|would win|wins)\b", "rules"),
    (r"\b((?:would|could|can|will) ?not (?:survive|last|make it)|can'?t survive|cannot survive|wouldn'?t (?:survive|last|make it)|would(?:n'?t)? die|dies|dead within|doomed|eaten alive|no chance|game over|"
     r"wouldn'?t stand a chance)\b", "dies"),
    (r"\b(survives?|would survive|makes it|holds? its own|gets by|could live)\b", "survives"),
]
_VERDICTS = [(re.compile(p, re.I), v) for p, v in VERDICTS]
ERAS = [  # (pattern, title, ago, order 0 = oldest .. 1 = today)
    (r"cambrian", "CAMBRIAN PERIOD", "500 million years ago", 0.04),
    (r"ordovician", "ORDOVICIAN PERIOD", "460 million years ago", 0.1),
    (r"silurian", "SILURIAN PERIOD", "430 million years ago", 0.15),
    (r"devonian", "DEVONIAN PERIOD", "380 million years ago", 0.24),
    (r"carboniferous", "CARBONIFEROUS PERIOD", "330 million years ago", 0.34),
    (r"permian", "PERMIAN PERIOD", "280 million years ago", 0.44),
    (r"triassic", "TRIASSIC PERIOD", "220 million years ago", 0.56),
    (r"jurassic", "JURASSIC PERIOD", "160 million years ago", 0.68),
    (r"cretaceous", "CRETACEOUS PERIOD", "94 million years ago", 0.8),
    (r"paleocene|eocene|paleogene", "PALEOGENE PERIOD", "45 million years ago", 0.9),
    (r"miocene|neogene|oligocene", "MIOCENE EPOCH", "15 million years ago", 0.95),
    (r"pliocene", "PLIOCENE EPOCH", "4 million years ago", 0.97),
    (r"pleistocene|ice age", "ICE AGE", "20,000 years ago", 0.99),
]
_ERAS = [(re.compile(r"\b(" + p + r")\b", re.I), t, a, o) for p, t, a, o in ERAS]
AGO = re.compile(r"\b(\d+(?:\.\d+)?)\s*(million|billion)\s+years\s+ago\b", re.I)
HISTORY = [  # (year, event) for "older than ..." / "N years old" anchors
    (1492, "Columbus reaches the Americas"), (1564, "Shakespeare is born"), (1607, "Jamestown is founded"),
    (1687, "Newton publishes his laws of motion"), (1776, "The United States declares independence"),
    (1789, "The French Revolution begins"), (1815, "The Battle of Waterloo"), (1859, "Darwin publishes On the Origin of Species"),
    (1865, "The American Civil War ends"), (1903, "The first powered flight"), (1912, "The Titanic sinks"),
    (1945, "World War II ends"), (1969, "Humans land on the Moon"),
]
HISTORY_WORDS = [
    (r"united states (?:existed|was founded|declared)|american independence|declaration of independence", 1776),
    (r"titanic", 1912), (r"columbus", 1492), (r"shakespeare", 1564), (r"french revolution", 1789), (r"moon landing", 1969),
    (r"civil war", 1865), (r"world war (?:ii|two|2)", 1945), (r"wright brothers|first (?:powered )?flight", 1903),
    (r"darwin", 1859), (r"newton", 1687),
]
_HIST = [(re.compile(r"\b(" + p + r")\b", re.I), y) for p, y in HISTORY_WORDS]
AGE = re.compile(r"\b(?:live[sd]? (?:for |to )?(?:over |more than |up to |about )?|(?:at least |over |about )?)(\d{2,3})\s*"
                 r"(?:\+\s*)?years?(?: old| of age)?\b", re.I)
PLACE = re.compile(r"\b(?:in|off|near|around|at|from|of|to)\s+(?:the\s+)?((?:St\.?\s)?[A-Z][a-zA-Z'\-]+(?:\s+(?:[A-Z][a-zA-Z'\-]+|of|"
                   r"and)){0,3})")
NOT_PLACE = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
             "December", "Earth", "God", "The", "This", "That", "One", "First", "But", "And", "It", "Its", "They", "We",
             "You", "Here", "There", "Now", "So", "Then", "Some", "Most", "Every", "Picture"}
PREDATORS = ("shark", "whale", "reptile", "fish", "squid", "bear", "seal")


@dataclass
class Rel:
    inside: List[str] = field(default_factory=list)
    above: Optional[Tuple[str, str, str]] = None
    place: str = ""
    place_pos: int = -1
    speed: List[Tuple[str, float, str]] = field(default_factory=list)
    speed_title: str = ""
    speed_pos: int = -1
    air: Optional[Tuple[float, float]] = None
    temp: str = ""
    temp_span: Tuple[int, int] = (-1, -1)
    era: Optional[Tuple[str, str, float]] = None
    verdict: str = ""
    part: str = ""
    latin: bool = False
    unverified: bool = False
    age: Optional[Tuple[int, str]] = None
    fraction: Optional[Tuple[int, int]] = None
    photo: bool = False
    question: bool = False


def _num(w: str) -> float:
    w = w.lower().strip()
    if w in WORDNUM:
        return float(WORDNUM[w])
    try:
        return float(w)
    except ValueError:
        return 0.0


def _kmh(v: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith(("mph", "mile")):
        return v * 1.609
    if u.startswith("knot"):
        return v * 1.852
    return v


SPEEDS = {  # km/h, rounded published top / cruising speeds, for the comparison bar when the narrator names one
    "walk": ("YOU, WALKING", 5.0), "swim": ("YOU, SWIMMING", 2.5), "seal": ("MOST SEALS", 30.0),
    "great_white": ("GREAT WHITE", 40.0), "orca": ("ORCA", 48.0), "dolphin": ("DOLPHIN", 35.0), "sailfish": ("SAILFISH", 100.0),
    "mako": ("SHORTFIN MAKO", 70.0), "tuna": ("TUNA", 70.0), "humpback": ("HUMPBACK", 25.0), "penguin": ("PENGUIN", 22.0),
    "car": ("A CAR IN TOWN", 50.0),
}


def read(text: str, animals: Sequence[Tuple] = (), numbers: Sequence[Any] = ()) -> Rel:
    t = str(text or "")
    r = Rel()
    names = [a[0] for a in animals]
    # stomach contents: the prey named in an "inside it" sentence (everything after the first animal / the predator)
    if INSIDE.search(t):
        from . import species as SP
        cast = [a[0] for a in animals if a[0] not in ("diver", "boat", "cage", "tooth")]
        if len(cast) >= 2 and SP.family(cast[0]) in ("shark", "whale", "reptile", "squid", "bear"):
            cast = cast[1:]                               # the first one named is the eater
        elif len(cast) == 1 and SP.family(cast[0]) in ("shark", "whale", "reptile") and not animals[0][1]:
            cast = []                                     # "inside it" about the shark alone: nothing named as eaten
        r.inside = list(dict.fromkeys(cast))[:4]
    m = ON_TOP.search(t)
    if m and len(animals) >= 1:
        surf = (m.group(2) or "surface").lower()
        surf = "ice" if "ice" in surf else ("land" if surf in ("land", "beach", "shore", "rocks", "rock") else surf)
        top = next((a[0] for a in animals if abs(a[3] - m.start()) < 40 and a[0] not in ("diver",)), None)
        bottom = next((a[0] for a in animals if a[0] != top), None)
        if top and (bottom or BELOW.search(t)):
            r.above = (top, bottom or "", surf)
    for pm in PLACE.finditer(t):
        cand = pm.group(1).strip()
        cand = re.sub(r"\s+(of|and)$", "", cand)
        if cand.split()[0] in NOT_PLACE or any(cand.lower().startswith(n.replace("_", " ")) for n in names):
            continue
        if place_known(cand):
            r.place, r.place_pos = cand, pm.start(1)
            break
    sp = list(SPEED_RE.finditer(t))
    if sp:
        r.speed_pos = sp[0].start()
        r.speed_title = "TOP SPEED" if re.search(r"\b(top|fastest|burst|max\w*)\b", t, re.I) else (
            "CRUISING SPEED" if re.search(r"\b(cruis\w*|normal|usual|average)\b", t, re.I) else "SPEED")
        who = next((a for a in animals if a[0] not in ("diver", "boat")), None)
        label = (who[4].upper() if who else "IT")
        for m2 in sp[:2]:
            v = _kmh(float(m2.group("num")), m2.group("unit"))
            u = m2.group("unit").lower()
            shown = f"{m2.group('num')} " + ("MPH" if u.startswith(("mph", "mile")) else "KNOTS" if u.startswith("knot") else "KM/H")
            r.speed.append((label, v, shown))
            label = "TOP BURST" if len(sp) > 1 else label
        if re.search(r"\byou (?:can )?swim\b|\bswimmer", t, re.I):
            r.speed.append(SPEEDS["swim"] + ("~2.5 KM/H",))
        elif len(r.speed) == 1:                  # one speed alone still gets a yardstick: you walking, or a car in town
            ref = "walk" if r.speed[0][1] < 15 else "car"
            r.speed.append(SPEEDS[ref] + (("~5 KM/H",) if ref == "walk" else ("~50 KM/H",)))
    elif re.search(r"\b(twice|\d+ times|three times) as fast\b|\bfaster than\b", t, re.I) and animals:
        mt = TIMES.search(t)
        mult = _num(mt.group(1)) if mt else 2.0
        a = next((x for x in animals if x[0] in SPEEDS), None)
        if a is not None:
            lab, v = SPEEDS[a[0]]
            r.speed = [(lab, v, f"ABOUT {mult:g}x"), ("IT", v / max(1.0, mult), "1x")]
            r.speed_title = "TOP SPEED"
            r.speed_pos = a[3]
    if AIR.search(t) and (PANIC.search(t) or TIMES.search(t)):
        mt = TIMES.search(t)
        r.air = (1.0, max(1.5, _num(mt.group(1)) if mt else 3.0))
    m = TEMP_RE.search(t)
    if m and (m.group("u1") or m.group("u2") or "°" in m.group(0) or re.search(r"degrees?", m.group(0), re.I)):
        num = m.group("num").replace(" 1/2", ".5").replace("1/2", "0.5")
        neg = "-" if m.group("neg") else ""
        u = (m.group("u1") or m.group("u2") or "C")[:1].upper()
        r.temp, r.temp_span = f"{neg}{num} °{u}", (m.start(), m.end())
    for rx, title, ago, order in _ERAS:
        if rx.search(t):
            r.era = (title, ago, order)
            break
    if r.era is None:
        m = AGO.search(t)
        if m:
            v = float(m.group(1)) * (1000 if m.group(2).lower() == "billion" else 1)
            r.era = ("", f"{m.group(1)} {m.group(2).lower()} years ago", max(0.0, min(1.0, 1 - v / 540.0)))
    for rx, v in _VERDICTS:
        if rx.search(t):
            r.verdict = v
            break
    if PART_ASK.search(t) or re.search(r"\b(about (?:those|its|their|the)|look at|those|zoom)\b", t, re.I):
        for rx, part in _PARTS:
            if rx.search(t):
                r.part = part
                break
    r.latin = bool(LATIN.search(t))
    r.unverified = bool(UNVERIFIED.search(t))
    for rx, y in _HIST:
        if rx.search(t):
            r.age = (y, dict(HISTORY)[y])
            break
    if r.age is None:
        m = AGE.search(t)
        if m and 80 <= int(m.group(1)) <= 600 and re.search(r"\b(old|live[sd]?|age|born|alive)\b", t, re.I):
            born = THIS_YEAR - int(m.group(1))
            y, ev = min(HISTORY, key=lambda h: abs(h[0] - born))
            r.age = (y, ev)
    m = FRACTION.search(t)
    if m:
        w = m.group(1).lower()
        if m.group(2):
            r.fraction = (int(_num(m.group(2))), int(_num(m.group(3))))
        else:
            r.fraction = {"a third": (1, 3), "one third": (1, 3), "a half": (1, 2), "half": (1, 2), "a quarter": (1, 4),
                          "two thirds": (2, 3)}[w]
    r.photo = bool(PHOTO.search(t))
    r.question = t.rstrip().endswith("?")
    return r


# ---------------------------------------------------------------------------------------------------------------- places

OCEAN_PLACES = {  # (lat, lon) for sea places the country / region data has no shape for
    "farallon islands": (37.70, -123.00), "baffin island": (69.0, -71.0), "baffin bay": (73.0, -66.0), "svalbard": (78.2, 15.6),
    "great barrier reef": (-18.3, 147.7), "mariana trench": (11.35, 142.2), "monterey bay": (36.8, -121.9),
    "gansbaai": (-34.6, 19.35), "false bay": (-34.2, 18.6), "galapagos": (-0.6, -90.5), "galapagos islands": (-0.6, -90.5),
    "seal island": (-34.14, 18.58), "guadalupe island": (29.0, -118.3), "st lawrence river": (48.0, -69.5),
    "st. lawrence river": (48.0, -69.5), "baie-comeau": (49.22, -68.15), "baie comeau": (49.22, -68.15),
    "bahamas": (24.7, -77.8), "cape cod": (41.7, -70.0), "bering sea": (58.0, -175.0), "arctic": (80.0, 0.0),
    "antarctica": (-75.0, 0.0), "north atlantic": (45.0, -40.0), "pacific": (0.0, -150.0), "atlantic": (20.0, -40.0),
    "indian ocean": (-15.0, 75.0), "mediterranean": (35.0, 18.0), "red sea": (20.0, 38.5), "gulf of mexico": (25.0, -90.0),
    "north sea": (56.0, 3.0), "hawaii": (20.8, -156.3), "florida": (27.8, -81.7), "california": (36.8, -121.0),
    "south africa": (-30.6, 22.9), "australia": (-25.3, 133.8), "new zealand": (-41.0, 174.0), "norway": (64.5, 11.0),
    "iceland": (64.9, -18.6), "greenland": (72.0, -40.0), "newfoundland": (49.0, -56.0), "nova scotia": (45.0, -63.0),
    "alaska": (63.6, -152.0), "japan": (36.2, 138.3), "mexico": (23.6, -102.5), "canada": (56.1, -106.3), "chile": (-35.7, -71.5),
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z .\-]", "", s.lower())).strip()


def place_known(name: str) -> bool:
    return place_latlon(name) is not None


def place_latlon(name: str) -> Optional[Tuple[float, float]]:
    """(lat, lon) of a place the narrator names: the sea-place list, then the app's own country / region shapes."""
    n = _norm(name)
    if not n:
        return None
    if n in OCEAN_PLACES:
        return OCEAN_PLACES[n]
    if n.startswith("the "):
        n = n[4:]
        if n in OCEAN_PLACES:
            return OCEAN_PLACES[n]
    try:
        from cinematic_explainer.war import geo_data as G
        f = G.find_country(name)
        if f is None:
            f = G.find_oblast(name)
        if f is not None and f.polys:
            lon, lat = f.centroid
            return (lat, lon)
    except Exception:  # noqa: BLE001 - no map data: no pin
        return None
    return None
