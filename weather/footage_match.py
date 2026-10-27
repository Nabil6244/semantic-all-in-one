"""Does a stock clip show what was asked for? (Weather's footage check, used by weather/footage_geo.py)

The stock providers rank a clip by how many words of the request its page shares, and when nothing matches they widen the request by
dropping its LAST words ("small hailstones bouncing off a car hood" -> "... off a car" -> "small"). That is how "person opening the
car hood" was chosen for hail, "cars on a bridge" for hail on a lawn, and a frozen lake for a drained one. The old Weather check never
compared a clip with its request: it asked only whether the description named some weather word (so "a person holding a bowl of
water" passed) and rejected every clip of a story that is not about weather (46 of 54 clips of a dam story).

The rule here compares the two, deterministically (no AI, no network), on the words the provider itself recorded for the clip (its
page title as written in the URL, plus alt text and tags when it has them):

  * the request is cut into units (a word, with its plural / tense / synonyms folded together: flood = flooded = floodwater);
    filler words (aerial, view, footage, close up ...) count a quarter and size / degree / colour words (small, heavy, dark ...)
    count a quarter, so "small hailstones bouncing off a car hood" is hail + bounce + car + hood;
  * the CORE words of the request (its hazard, its weather, and the things that can be filmed: dam, road, boat, car ...) are what
    count; the clip must show the request's MAIN subject (the hazard first, then the weather, then the first thing named) and at
    least half of the core words; every hazard named (hail, flood, tornado ...) must be in the clip, whatever else matches;
  * a request with no core word at all (a mood, an action) needs COVER (60 %) of its words;
  * opposites never match (a frozen lake for a drained one).

`simplify(request, keep)` gives the same request with only its `keep` most important units, for the next search when a clip fails:
a short request of what matters is what the stock sites index well. judge(request, text) -> (ok, why)."""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

COVER = 0.60          # of a request that names nothing filmable: the share of its words the clip must have
CORE_COVER = 0.60     # of a request's core words (hazard, weather, things)

STOP = set(("a an the of in on at with and or to for from by into onto over under near next beside along across through around against off "
            "up out as is are was were be being been it its this that these those his her their my your our while during after before "
            "then than so very more most some any each every one two three four five six").split())
FILLER = set(("aerial view views footage video videos shot shots clip clips close closeup up above overhead drone time lapse timelapse scene scenes "
              "slow motion wide angle high low background overhead birds eye cinematic").split())
PEOPLE = set("person people man men woman women someone group crowd".split())
DEGREE = set(("small large big huge tiny little heavy light strong violent severe hard intense extreme dark darkening bright old new "
              "vintage modern quaint beautiful scenic stunning dramatic majestic massive giant tall long short rural urban empty full "
              "calm busy quiet sturdy brown green blue grey gray white black red yellow golden mountain pea size sized").split())

# folded words: every word of a group is the first one
GROUPS = [
    "flood flooded flooding floods floodwater floodwaters flash overflow overflowing overflows inundated inundation submerged",
    "storm storms stormy thunderstorm thunderstorms thunder supercell",
    "hail hailstone hailstones hailstorm",
    "tornado tornadoes twister funnel",
    "lightning bolt bolts",
    "hurricane cyclone typhoon",
    "rain raining rainy rainfall downpour raindrop raindrops",
    "snow snowfall snowing snowy snowflake snowflakes blizzard",
    "wind winds windy gust gusts gusty gale",
    "cloud clouds cloudy overcast cumulonimbus",
    "car cars vehicle vehicles automobile suv",
    "house houses home homes residence residences housing",
    "road roads street streets highway highways roadway",
    "lake lakes reservoir pond",
    "river rivers stream streams creek creeks brook",
    "field fields farmland farm farms pasture pastures cropland crop crops meadow",
    "town towns village villages city cities downtown",
    "sunset dusk evening twilight",
    "sunrise dawn morning",
    "night nighttime",
    "phone phones smartphone smartphones cellphone",
    "bend bending bent sway swaying swayed blow blowing blown whip whipping thrash thrashing shake shaking",
    "debris wreckage rubble",
    "damage damaged destroyed destruction collapsed",
    "dam dams spillway",
    "bridge bridges footbridge",
    "boat boats ship yacht motorboat",
    "water waters",
    "beach beaches shore shoreline coast coastline coastal seashore seaside waterfront",
    "wave waves surf swell swells breaker breakers",
    "ocean sea oceans seas",
    "sand sandy sands",
    "document documents paper papers paperwork",
    "worker workers crew crews",
]
_GROUP: Dict[str, str] = {}
for _g in GROUPS:
    _w = _g.split()
    for _x in _w:
        _GROUP[_x] = _w[0]

# a hazard whose absence from a clip changes what it shows (hail is not a car hood); hurricane, drought ... are rarely named in a clip title
HAZARDS = {"flood", "hail", "tornado", "lightning", "snow", "wildfire", "earthquake", "tsunami"}
WEATHER_UNITS = HAZARDS | {"storm", "rain", "wind", "cloud", "fog", "ice", "frost", "heat", "hurricane", "drought"}
# the setting of a shot (where), counted half as much as its subject (what): "waves on the coast" is waves
SETTINGS = {"beach", "road", "town", "field", "lake", "river", "valley", "forest", "ocean", "neighborhood", "harbor", "water", "mountain", "city"}

_SUFFIX = ("ing", "ed", "es", "s", "ly")


def _plain(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", t)


def unit(word: str) -> str:
    """One word folded to its unit: plurals, tenses and synonyms together."""
    w = word.lower()
    if w in _GROUP:
        return _GROUP[w]
    for pre, canon in (("flood", "flood"), ("hail", "hail"), ("tornad", "tornado"), ("lightn", "lightning"), ("thunder", "storm"),
                       ("hurrican", "hurricane")):
        if w.startswith(pre):
            return canon
    if w.endswith("bridge") and len(w) > 6:
        return "bridge"
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    for suf in _SUFFIX:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[: -len(suf)]
            if base in _GROUP:
                return _GROUP[base]
            return base[:-1] if len(base) > 3 and base[-1] == base[-2] else base
    return w


def weight(word: str) -> float:
    if word in STOP:
        return 0.0
    if word in FILLER or word in DEGREE:
        return 0.25
    if word in PEOPLE:
        return 0.5
    return 1.0


def units(request: str) -> List[Tuple[str, float]]:
    """[(unit, weight)] of the request, in order, each unit once (its largest weight)."""
    out: Dict[str, float] = {}
    for w in _plain(request).split():
        wt = weight(w)
        if wt <= 0:
            continue
        u = unit(w)
        out[u] = max(out.get(u, 0.0), wt)
    return list(out.items())


def clip_units(text: str) -> Set[str]:
    return {unit(w) for w in _plain(text).split() if w not in STOP}


def hazard_units(request: str) -> List[str]:
    return [u for u, _w in units(request) if u in HAZARDS]


# things a camera can film (the same words weather.motion.FILMABLE uses, plus the rest of what a Weather story shows)
EXTRA_THINGS = set(("car truck tree trees bank door window roof hood lawn patio chair chairs sign phone laptop cash key clock calendar plan "
                    "blueprint vault excavator crane pumpjack mud ice waves wave debris hallway tractor bus train airport runway tower "
                    "capitol courthouse church barn silo levee dike canal culvert gauge fence trailer shed garage basement porch bulldozer loader piling "
                    "sandbag sandbags seawall boardwalk pier jetty lifeguard bulkhead "
                    "family famil desk table kitchen office window drone document policy insurance").split())
STATES = set("drained drain dry cracked crack frozen empty muddy mud stranded".split())
# people are never the main subject of a clip search (stock sites tag them loosely): they count, but a clip is judged on the rest
ACTORS = set("engineer inspector official mayor council worker crew resident family famil homeowner owner agent legislator".split())
# a setting that does not belong in the request (desert palms for a Texas storm): the clip is rejected unless the request names it
ALIEN = set("desert palm palms palmetto palmettos tropical arid cactus cacti jungle rainforest tundra arctic antarctic savanna safari "
            "mediterranean tuscan riviera santorini lagoon".split())
OPPOSITES = (({"frozen", "ice"}, {"drain", "dry", "crack", "mud"}),)


def _things() -> Set[str]:
    out = {unit(w) for w in EXTRA_THINGS}
    try:
        from .motion import FILMABLE

        out |= {unit(k) for k in FILMABLE if k not in ("people", "residents", "families", "money", "dollars", "visitors", "tourists", "tourism")}
    except Exception:
        pass
    return out


_THINGS: Optional[Set[str]] = None


def core_units(request: str) -> List[Tuple[str, float]]:
    """[(unit, weight)]: the words of the request that name something to film. A hazard, a weather word, a thing or a state weighs
    1; a setting (beach, road, town ...) half."""
    global _THINGS
    if _THINGS is None:
        _THINGS = _things()
    states = {unit(x) for x in STATES}
    keep = HAZARDS | WEATHER_UNITS | _THINGS | states | SETTINGS
    core = [(u, 0.5 if (u in SETTINGS and u not in WEATHER_UNITS and u not in states) else 1.0) for u, w in units(request) if u in keep and w >= 0.5]
    if any(u in HAZARDS for u, _w in core):   # "storm surge flooding": the flood is what the clip must show; the word "storm" is not required too
        core = [(u, w) for u, w in core if u in HAZARDS or u not in WEATHER_UNITS]
    return core


def main_unit(core: List[Tuple[str, float]]) -> Optional[str]:
    """The subject the clip must show: a hazard, else the first thing named (not a person, not the weather in general, not a setting)."""
    names = [u for u, _w in core]
    for u in names:
        if u in HAZARDS:
            return u
    actors = {unit(a) for a in ACTORS}
    for u in names:
        if u not in actors and u not in WEATHER_UNITS and u not in SETTINGS:
            return u
    for u in names:
        if u not in actors:
            return u
    return names[0] if names else None


def judge(request: str, described: str) -> Tuple[bool, str]:
    """(ok, why): does a clip described as `described` show `request`?"""
    want = units(request)
    if not want:
        return True, "nothing specific was asked for"
    have = clip_units(described)
    if not have:
        return False, "its record says nothing about what it shows"
    missing_hazard = [h for h in hazard_units(request) if h not in have]
    if missing_hazard:
        return False, f"asked for {', '.join(missing_hazard)}, which its description does not show"
    asked = {u for u, _w in want}
    alien = sorted(w for w in _plain(described).split() if w in ALIEN and w not in set(_plain(request).split()))
    if alien:
        return False, f"it shows a setting the request does not name ({', '.join(alien[:3])})"
    for a, b in OPPOSITES:
        if (asked & a) and (have & b) and not (have & a):
            return False, "its description shows the opposite of what was asked"
        if (asked & b) and (have & a) and not (have & b):
            return False, "its description shows the opposite of what was asked"
    core = core_units(request)
    if core:
        main = main_unit(core)
        if main not in have:
            return False, f"it does not show the main subject of the request ({main})"
        cover = sum(w for u, w in core if u in have) / sum(w for _u, w in core)
        if cover < CORE_COVER:
            lack = [u for u, _w in core if u not in have]
            return False, f"it shows something else: its description has {cover:.0%} of what the request names (missing {', '.join(lack[:4])})"
        return True, f"it shows the main subject ({main}) and {cover:.0%} of what the request names"
    total = sum(w for _u, w in want)
    got = sum(w for u, w in want if u in have)
    cover = got / total if total else 1.0
    if cover < COVER:
        lack = [u for u, w in want if u not in have and w >= 1.0]
        return False, f"it shows something else: its description covers {cover:.0%} of the request (missing {', '.join(lack[:4])})"
    return True, f"its description covers {cover:.0%} of the request"


# ---- the next, simpler request ----------------------------------------------------------------------------------------------------

def simplify(request: str, keep: int = 3) -> str:
    """The request cut to its `keep` most important words, in their original order: the hazard first, then the things that can be
    filmed, then the rest; fillers, degree words and verbs in -ing last. '' when nothing is left."""
    try:
        from .motion import FILMABLE

        things = {unit(k) for k in FILMABLE}
    except Exception:
        things = set()
    scored = []
    seen: Set[str] = set()
    for i, w in enumerate(_plain(request).split()):
        wt = weight(w)
        u = unit(w)
        if wt <= 0.25 or u in seen:
            continue
        seen.add(u)
        pri = 3.0 if u in HAZARDS else 2.0 if (u in WEATHER_UNITS or u in things) else 0.5 if w.endswith("ing") else 1.0
        scored.append((pri, -i, i, w))
    top = sorted(scored, reverse=True)[: max(1, keep)]
    return " ".join(w for _p, _n, _i, w in sorted(top, key=lambda t: t[2]))


def is_weather_request(request: str) -> bool:
    return any(u in WEATHER_UNITS for u, _w in units(request))
