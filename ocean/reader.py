"""Reads one narration sentence for the Ocean planner (docs/ocean/PATTERNS.md sections 5 + 7, step 5).

    read(text) -> Features    animals named, numbers (+ what kind), set hint, card hints, joke-prop hint, actions

Everything is read from the sentence's SHAPE (a number with a unit, "N of M", a percent, "N hours", "in 1997", "N meters
down", "researchers found", second person, a list ordinal, "X or Y?") plus the animals it names, so any new topic works;
there are no topic constants. Animals come from the sea-animal catalogue (ocean/species.py); an animal it does not know is
left out rather than drawn wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# (pattern, animal key, extra args): the sea-animal catalogue (ocean/species.py) + generic family words + props
from . import species as SP  # noqa: E402

ANIMALS: List[Tuple[str, str, Dict[str, Any]]] = SP.patterns()
_ANIMAL_RE = [(re.compile(r"\b(" + p + r")\b", re.I), n, a) for p, n, a in ANIMALS]

MONTHS = ("january february march april may june july august september october november december "
          "jan feb mar apr jun jul aug sep sept oct nov dec").split()
_NUM_RE = re.compile(
    r"(?P<pre>~|about |around |roughly |up to |over |nearly |almost |more than |less than |fewer than )?"
    r"(?P<num>\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?:\s*(?:-|to)\s*(?P<num2>\d+(?:\.\d+)?))?"
    r"\s*(?P<scale>%|percent\b|million\b|billion\b|thousand\b|hundred\b)?"
    r"\s*(?P<unit>[a-zA-Z/]+)?", re.I)
LENGTH_UNITS = {"m", "meter", "meters", "metre", "metres", "ft", "feet", "foot", "cm", "km", "mm", "inch", "inches",
                "millimeter", "millimeters", "millimetre", "millimetres", "centimeter", "centimeters", "centimetre", "centimetres",
                "mile", "miles"}
TIME_UNITS = {"hours", "hour", "hrs", "minutes", "minute", "mins", "seconds", "days", "weeks"}
MASS_UNITS = {"kg", "tons", "tonnes", "ton", "tonne", "lb", "lbs", "pounds", "pound", "kilograms", "kilos", "kilo"}

SETS = [  # (pattern, set) first match wins
    (r"\b(torch(?:beam)?|flashlight|murky|zero visibility|can'?t see|cannot see|in the dark|darkness|edge of the light)\b", "dark"),
    (r"\b(burrows?|dens?|underground|subterranean|tunnels?|dig(?:s|ging)? (?:down|into|through|under|a |out)|dug)\b", "burrow"),
    (r"\b(after dark|at night|at dusk|nocturnal|single night|moonlight)\b", "dark"),
    (r"\b(savann?ah?|bush|grasslands?|kalahari|serengeti|plains?|desert sand|scrubland|termite mound|acacia)\b", "savanna"),
    (r"\b(sea ice|under the ice|the ice above|ice above|hole in the ice|ice hole|ceiling of ice|through the ice)\b", "ice_hole"),
    (r"\b(abyss|abyssal|trench(es)?|midnight zone|hadal|pitch[- ]black|no light|deep sea|deep-sea|deepest)\b", "abyss"),
    (r"\b(kelp|seaweed|forest of)\b", "kelp"),
    (r"\b(twilight zone|(meters|metres|feet|m) (down|deep|below)|dive[sd]? to|depths?|sink(s|ing)?|deeper)\b", "depth_column"),
    (r"\b(sea ?floor|ocean floor|sand|sandy|bottom|beach|shore|shallows?|washed up|stranded|carcass(es)?)\b", "seafloor"),
    (r"\b(surface|island|islands|coast|coastline|horizon|bay|harbou?r|from a boat|above the water|breach(es|ed)?)\b",
     "surface"),
    (r"\b(everywhere else|around antarctica|warm water vs|on one side)\b", "split_columns"),

]
_SETS = [(re.compile(p, re.I), s) for p, s in SETS]

STUDY = re.compile(r"\b(researchers?|scientists?|biologists?|a study|the study|studies|published|paper|journal|"
                   r"tagged|tracked|survey(ed)?|recorded|footage shows|data)\b", re.I)
ORDINAL = re.compile(r"\b(the first|the second|the third|the fourth|the fifth|the next|the last|number one|number two|"
                     r"number three|first up|next up|first one|second one|third one)\b", re.I)
_ORD_INDEX = {"first": 0, "one": 0, "second": 1, "two": 1, "third": 2, "three": 2, "fourth": 3, "fifth": 4}
YOU = re.compile(r"\b(you|you're|you are|your|you'd|you'll|imagine)\b", re.I)
QUESTION_OR = re.compile(r"\b(?:do you|would you|should you|you could|you can|can you)\b(.+?)\?", re.I)
COMMENT = re.compile(r"\b(comments?|let (?:me|us) know|tell us|which animal|what do you think)\b", re.I)
GAGS = [  # (pattern, card) the joke prop a sentence's shape asks for
    (r"\b(blame|guilty|culprit|crime|criminal|wanted|suspect|murder(ed|er)?|evidence|caught red)\b", "wanted"),
    (r"\b(scene of|dead body|bodies|remains|no witnesses)\b", "crime_tape"),
    (r"\b(hero|heroes|rescue[sd]?|saves?|saved|protect(s|ed|ing)?|guard(s|ed|ing)?|bodyguards?|selfless|altruis\w*)\b", "halo"),
    (r"\b(birthday|celebrat\w*|party|newborn|calf|calves|baby|babies|pups?)\b", "bunting"),
    (r"\b(buy|bought|sell|sold|price|collectors?|for sale|online|\$\d)\b", "shop"),
    (r"\b(plan|strategy|tactics?|team ?work|coordinat\w*|play ?book|separate the|work together|cooperat\w*|in shifts|"
     r"take turns)\b", "playbook"),
    (r"\b(myth|misconception|people (?:think|assume)|everyone thinks|turns out|most people)\b", "quiz"),
    (r"\b(versus|vs\.?|against|rival(s|ry)?|fight(s|ing)?|showdown|clash(es|ed)?|face[sd]? off|predator|prey|victim)\b", "duel"),
]
_GAGS = [(re.compile(p, re.I), g) for p, g in GAGS]
FLEE = re.compile(r"\b(fle[de]|flees|fleeing|ran|run|runs|running|swam away|swim away|vanish(ed|es)?|escape[sd]?|"
                  r"left|abandon(ed|s)?|disappear(ed|s)?|backs? off|turned around)\b", re.I)
ATTACK = re.compile(r"\b(attack(s|ed|ing)?|bit|bite[sd]?|biting|hunt(s|ed|ing)?|chase[sd]?|charg(e|es|ed|ing)|"
                    r"ambush(ed|es)?|ram(s|med)?|kill(s|ed|ing)?|eat(s|ing)?|ate|grab(s|bed)?)\b", re.I)
GROUP = re.compile(r"\b(pods?|groups?|families|family|schools?|hundreds|thousands|dozens|colony|colonies|herds?|"
                   r"together|circle[sd]?|surround(s|ed)?)\b", re.I)
EXCEPT = re.compile(r"\b(except|one animal|something else|but one|there's one|only one)\b", re.I)


@dataclass
class Number:
    raw: str
    value: float
    kind: str                 # percent, time, year, depth, length, mass, money, count
    unit: str = ""
    pos: int = 0              # character offset in the sentence (for timing)
    end: int = 0              # where the number (+ its measuring unit) ends in the sentence
    pre: str = ""
    value2: Optional[float] = None


@dataclass
class Features:
    text: str
    animals: List[Tuple[str, bool, Dict[str, Any], int, str]] = field(default_factory=list)  # (kit, plural, args, pos, word)
    numbers: List[Number] = field(default_factory=list)
    set_hint: str = ""
    study: bool = False
    ordinal: Optional[int] = None
    you: bool = False
    choice: List[str] = field(default_factory=list)
    comment: bool = False
    gag: str = ""
    flee: Optional[int] = None
    attack: Optional[int] = None
    group: bool = False
    except_: bool = False
    month: str = ""
    question: bool = False
    rel: Any = None                 # ocean/relations.py: what the sentence says about its nouns

    @property
    def names(self) -> List[str]:
        return [a[0] for a in self.animals]


def _f(num: str) -> float:
    try:
        return float(num.replace(",", "").replace("$", ""))
    except ValueError:
        return 0.0


SPELLED = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                     "fifteen sixteen seventeen eighteen nineteen twenty".split())}
SPELLED.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90})


_UNITS_W = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                         "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS_W = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALE_W = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_NUMWORD = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|" \
           r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million)"
_RUN = re.compile(r"\b(?:an?\s+)?" + _NUMWORD + r"(?:(?:\s+and\s+|[\s\-]+)" + _NUMWORD + r")*\b", re.I)


def words_to_digits(text: str) -> str:
    """'four hundred and twenty pounds' -> '420 pounds', 'a thousand pounds' -> '1000 pounds', 'twenty-five-pound' ->
    '25-pound', 'fifteen hundred calories' -> '1500 calories'. A lone 'one' stays a word ('one of them', 'one afternoon')
    and a lone 'hundreds' / 'thousands' (no number before it) stays as it is."""
    def conv(m: "re.Match") -> str:
        raw = m.group(0)
        words = [w for w in re.split(r"[\s\-]+", raw.lower()) if w and w != "and"]
        lead_a = words and words[0] in ("a", "an")
        if lead_a:
            words = words[1:]
        keep_a = ""
        if lead_a and words and words[0] not in _SCALE_W:      # "a twenty-five-pound badger": the article stays a word
            keep_a, lead_a = raw[: raw.lower().index(" ") + 1], False
        if not words or (len(words) == 1 and words[0] == "one"):
            return raw
        if words[0] in _SCALE_W and not lead_a:
            return raw
        total, cur = 0, 1 if lead_a else 0
        for w in words:
            if w in _UNITS_W:
                cur += _UNITS_W[w]
            elif w in _TENS_W:
                cur += _TENS_W[w]
            elif w == "hundred":
                cur = max(1, cur) * 100
            else:
                total += max(1, cur) * _SCALE_W[w]
                cur = 0
        n = total + cur
        sep = "-" if raw.rstrip().endswith("-") else ""
        return keep_a + (f"{n:,}" if n >= 1000 else str(n)) + sep
    return _RUN.sub(conv, text)


def spelled_to_digits(text: str) -> str:
    """'seventeen of them' -> '17 of them', 'two hundred' -> '2 hundred' (same length is not kept; positions are re-read)."""
    def rep(m: "re.Match") -> str:
        w = m.group(0)
        lw = w.lower()
        if lw in ("one", "zero"):
            return w                                  # "one afternoon", "one of them": not a count card
        return str(SPELLED[lw])
    return re.sub(r"\b(" + "|".join(k for k in SPELLED) + r")\b(?=\s+[a-z])", rep, text, flags=re.I)


def _numbers(text: str) -> List[Number]:
    out: List[Number] = []
    text = re.sub(r"(\d)-(?=(meters?|metres?|foot|feet|ft|m|tons?|tonnes?|kg|pounds?|inch(?:es)?|(?:milli|centi)met(?:er|re)s?|"
                  r"miles?|years?|seconds?|minutes?|hours?|days?)\b)", r"\1 ", text, flags=re.I)   # "5-meter": same length
    for m in _NUM_RE.finditer(text):
        num, unit = m.group("num"), (m.group("unit") or "").lower()
        scale = (m.group("scale") or "").lower()
        v = _f(num)
        after = text[m.end(): m.end() + 24].lower()
        if scale in ("%", "percent"):
            kind = "percent"
        elif num.startswith("$"):
            kind = "money"
        elif unit in TIME_UNITS:
            kind = "time"
        elif unit in LENGTH_UNITS and re.match(r"\s*(down|deep|below|under)", after) or \
                (unit in LENGTH_UNITS and re.search(r"\b(depths? of|down to|dive[sd]? to|at)\s*$", text[:m.start()].lower())):
            kind = "depth"
        elif unit in LENGTH_UNITS:
            kind = "length"
        elif unit in MASS_UNITS:
            kind = "mass"
        elif 1500 <= v <= 2100 and not scale and "," not in num and (not unit or unit in ("and", "the", "a", "when", "off", "in")):
            kind = "year"
        else:
            kind = "count"
        shown = num + (f"-{m.group('num2')}" if m.group("num2") else "")
        if kind == "percent":
            shown += "%"
        elif scale:
            shown += " " + scale
        if kind in ("length", "depth", "mass", "time") and unit:
            shown += " " + unit
        pre = (m.group("pre") or "").strip().lower()
        raw = ("~" if pre in ("about", "around", "roughly", "~", "nearly", "almost") else "") + shown
        if kind in ("count", "year", "percent", "money") and unit in ("and", "the", "a", "of", "when", "off", "in", "it",
                                                                       "they", "to", "by", "were", "was", "are"):
            unit = ""
        if scale in ("million", "billion", "thousand", "hundred"):
            v *= {"million": 1e6, "billion": 1e9, "thousand": 1e3, "hundred": 1e2}[scale]
        keep_unit = kind in ("length", "depth", "mass", "time")
        end = m.end("unit") if (keep_unit and m.group("unit")) else max(m.end("num"), m.end("num2") if m.group("num2") else 0,
                                                                         m.end("scale") if m.group("scale") else 0)
        out.append(Number(raw=raw, value=v, kind=kind, unit=unit, pos=m.start(), end=end, pre=(m.group("pre") or "").strip(),
                          value2=_f(m.group("num2")) if m.group("num2") else None))
    return out


def read(text: str) -> Features:
    t = words_to_digits(str(text or ""))
    f = Features(text=t)
    taken: List[Tuple[int, int]] = []
    hits = [(m.start(), m.end(), i, name, args, m) for i, (rx, name, args) in enumerate(_ANIMAL_RE) for m in rx.finditer(t)]
    for a0, b0, _i, name, args, m in sorted(hits, key=lambda h: (-(h[1] - h[0]), h[2])):   # the longest name wins
        if any(a0 < b and a < b0 for a, b in taken):
            continue
        taken.append((a0, b0))
        word = m.group(1).lower()
        plural = word.endswith("s") and not word.endswith(("ss", "us")) or word.endswith("teeth")
        if name == "tooth" and not re.search(r"fossil|tooth\b", word):
            continue
        f.animals.append((name, plural, dict(args), a0, m.group(1)))
    f.animals.sort(key=lambda a: a[3])
    seen: List[str] = []
    uniq = []
    for a in f.animals:
        key = a[0] + str(a[2])
        if key not in seen:
            seen.append(key)
            uniq.append(a)
    f.animals = uniq
    f.numbers = _numbers(t)
    if not f.numbers:
        t2 = spelled_to_digits(t)
        if t2 != t:
            spelled = [m for m in re.finditer(r"\b(" + "|".join(SPELLED) + r")\b", t, re.I)
                       if m.group(1).lower() not in ("one", "zero")]
            for n, m in zip(_numbers(t2), spelled):  # each converted number sits where its word was
                n.end = m.end()
                n.pos = max(0, m.start() - (len(n.pre) + 1 if n.pre else 0))
                f.numbers.append(n)
    from . import relations as REL
    f.rel = REL.read(t, f.animals, f.numbers)
    spans = [m.span() for m in REL.SPEED_RE.finditer(t)] + ([f.rel.temp_span] if f.rel.temp else [])
    f.numbers = [n for n in f.numbers if not any(n.pos < b and n.end > a for a, b in spans)]   # speeds / temperatures have their own cards
    for rx, s in _SETS:
        if rx.search(t):
            f.set_hint = s
            break
    f.study = bool(STUDY.search(t))
    m = ORDINAL.search(t)
    if m:
        w = m.group(1).lower().split()[-1]
        f.ordinal = _ORD_INDEX.get(w, -1 if w in ("next", "last", "up") else None)
        if w == "one" and "first" in m.group(1).lower():
            f.ordinal = 0
    f.you = bool(YOU.search(t))
    q = QUESTION_OR.search(t)
    if q and " or " in q.group(1):
        parts = re.split(r",\s*|\s+or\s+", q.group(1))
        opts = []
        for p in parts:
            words = [w for w in re.findall(r"[A-Za-z']+", p) if w.lower() not in ("you", "do", "would", "the", "a", "an", "just")]
            if words:
                opts.append(" ".join(words[-3:]))
        f.choice = opts[-4:] if len(opts) >= 2 else []
    f.comment = bool(COMMENT.search(t))
    for rx, g in _GAGS:
        if rx.search(t):
            f.gag = g
            break
    m = FLEE.search(t)
    f.flee = m.start() if m else None
    m = ATTACK.search(t)
    f.attack = m.start() if m else None
    f.group = bool(GROUP.search(t))
    f.except_ = bool(EXCEPT.search(t))
    f.question = t.rstrip().endswith("?")
    for mo in MONTHS:
        if re.search(r"\b" + mo + r"\b", t, re.I) and (mo != "may" or re.search(r"\bmay\s+\d|\bin may\b", t, re.I)):
            if (len(mo) > 3 and mo != "march") or re.search(r"\b" + mo + r"\b\.?\s*\d", t, re.I):
                f.month = mo[:3].upper()
                break
    return f
