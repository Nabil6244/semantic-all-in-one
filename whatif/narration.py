"""What If: reading the narration. The narrator's own words (Whisper, aligned back to the script so "4.2" and "96.5%" stay
exact) become spoken measurements, ratios, light-time distances, survival / descent / light-speed acts and the cut points
(clause ends) the planner uses. Nothing here invents a fact: every number shown is a number the narrator says.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple




LEAD_S = 0.1                 # a graphic lands this far ahead of the word it shows (the eye before the ear)
METRIC_MIN_S, METRIC_MAX_S = 2.5, 4.6
METRIC_GAP_S = 2.4           # two automatic callouts never closer than this
PLATE_MIN_S, PLATE_MAX_S = 3.5, 6.2
PLATE_SHARE_MAX = 0.35       # diagram plates never take more than this share of the video
MAX_HOLD_S = 6.5             # the longest stretch without a visual change (a cut, a callout, a plate, footage)
FADE_MAX = 3
LOOK = {"glow": 0.22, "vignette": 0.38, "grain": 0.03, "saturate": 0.8, "contrast": 1.04, "lift": "#080B10", "footage_credit": False}
STILL_DRIFT = {"from": [0.5, 0.5, 1.0], "to": [0.5, 0.48, 1.04]}
# telemetry shot cutting (compile.build_camera): shots of about this length, none shorter than the minimum
PACE = {"cut_min_s": 3.0, "shot_s": 4.6}


# ---- words ---------------------------------------------------------------------------------------------------------------
@dataclass
class Word:
    text: str           # as spoken, punctuation kept
    norm: str           # lower case, punctuation stripped
    start: float
    end: float


def _script_tokens(script: str) -> List[Tuple[str, str]]:
    """The script as (normalized like the app's transcript, as written) pairs: the app's tokenizer (video_generator.split_words)
    drops decimals and punctuation ("4.2" -> "42"), so the written form is kept beside it to put back on screen."""
    try:
        from video_generator import split_words
    except Exception:                                   # no app around (a bare engine test): a plain stand-in
        split_words = lambda t: [x for x in re.split(r"[-\s]+", re.sub(r"[^\w\s-]", "", t.lower())) if x]   # noqa: E731
    out: List[Tuple[str, str]] = []
    for tok in (script or "").split():
        parts = split_words(tok)
        if len(parts) == 1:
            out.append((parts[0], tok))
        elif parts:
            tail = re.search(r"[,;:.?!]+$", tok)
            out += [(p, p + (tail.group(0) if tail and k == len(parts) - 1 else "")) for k, p in enumerate(parts)]
    return out


def words_of(raw: Sequence[Any], script: str = "") -> List[Word]:
    """The narration's timed words; with the script, each word matched to it is shown as written ("4.2", "Venus."). The
    transcript splits a spoken decimal in two ("96" "5") and drops a "%": the pair is joined back when the script writes that
    decimal, and a script word the transcript lost between two matched words is put back (zero length, at the gap)."""
    words = _raw_words(raw)
    toks = _script_tokens(script) if script else []
    decimals = {t[0] for t in toks if re.fullmatch(r"-?\d+\.\d+%?[,;:.?!]*", t[1])}
    joined: List[Word] = []
    for w in words:
        prev = joined[-1] if joined else None
        if prev is not None and prev.text.isdigit() and w.text.isdigit() and prev.text + w.text in decimals and w.start - prev.end < 0.9:
            joined[-1] = Word(prev.text + w.text, prev.norm + w.norm, prev.start, w.end)
        elif prev is not None and prev.text.isdigit() and w.text.isdigit() and w.start - prev.end < 0.05:
            # one spoken number the transcript cut in two, back to back with its separator gone: "384" "0" was 384,000 and "6" "800"
            # 6,800 (a lone 0 or three digits after it: thousands); "4" "37" was 4.37, "9" "5" 9.5 (anything else: a decimal). The
            # script spelling the number out ("four point three seven") gives no digits to match, so this is the fallback.
            thousands = w.text == "0" or len(w.text) == 3
            x = f"{int(prev.text):,},{'000' if w.text == '0' else w.text}" if thousands else f"{prev.text}.{w.text}"
            joined[-1] = Word(x, x, prev.start, w.end)
        else:
            joined.append(w)
    words = joined
    if not (script and words):
        return words
    import difflib

    sm = difflib.SequenceMatcher(None, [t[0] for t in toks], [w.text.lower() for w in words], autojunk=False)
    out: List[Word] = []
    written = lambda w, x: (setattr(w, "text", x), setattr(w, "norm", re.sub(r"[^\w%°.\-/']+", "", x.lower()).strip(".-'")))  # noqa: E731
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and a1 - a0 == b1 - b0):
            for k in range(b1 - b0):
                written(words[b0 + k], toks[a0 + k][1])
            out += words[b0:b1]
        elif op == "delete" and out and a1 - a0 <= 2:
            at = out[-1].end
            for k in range(a0, a1):
                w = Word("", "", at, at)
                written(w, toks[k][1])
                out.append(w)
        elif op in ("insert", "replace"):
            out += words[b0:b1]
    return out


def find_anchor(words: List[Word], anchor: str, t0: float, t1: float) -> Optional[float]:
    """When the narrator says `anchor` (its written words in order) between t0 and t1, on the script-aligned words."""
    want = [re.sub(r"[^\w%°.\-/']+", "", x.lower()).strip(".-'") for x in (anchor or "").split()]
    want = [x for x in want if x]
    if not want:
        return None
    for i, w in enumerate(words):
        if w.start < t0 - 1e-6 or w.start > t1:
            continue
        if [x.norm for x in words[i:i + len(want)]] == want:
            return w.start
    return None


def _raw_words(raw: Sequence[Any]) -> List[Word]:
    out = []
    for w in raw or ():
        if isinstance(w, (list, tuple)):
            text, s, e = str(w[0]), float(w[1]), float(w[2] if len(w) > 2 else w[1])
        else:
            text = str(getattr(w, "word", getattr(w, "text", "")))
            s, e = float(getattr(w, "start", 0.0)), float(getattr(w, "end", getattr(w, "start", 0.0)))
        text = text.strip()
        if text:
            out.append(Word(text, re.sub(r"[^\w%°.\-/]+", "", text.lower()).strip(".-"), s, e))
    return out


def clauses(words: List[Word], pause_s: float = 0.35) -> List[Tuple[int, int]]:
    """(first, last) word indexes of each clause: ends at , ; : . ? ! or a pause of pause_s."""
    out, a = [], 0
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        if re.search(r"[,;:.?!—]$", w.text) or nxt is None or nxt.start - w.end >= pause_s:
            out.append((a, i))
            a = i + 1
    return out


def sentences(words: List[Word]) -> List[Tuple[int, int]]:
    out, a = [], 0
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        if re.search(r"[.?!]$", w.text) or nxt is None or nxt.start - w.end >= 0.9:
            out.append((a, i))
            a = i + 1
    return out


def span_text(words: List[Word], a: int, b: int) -> str:
    return " ".join(w.text for w in words[a:b + 1])


# ---- numbers -------------------------------------------------------------------------------------------------------------
SMALL = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                    "sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
SCALES = {"hundred": 100, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
SCALE_WORD = {1e6: "MILLION", 1e9: "BILLION", 1e12: "TRILLION"}


def _digits(tok: str) -> Optional[float]:
    m = re.fullmatch(r"[-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-−]?\d+(?:\.\d+)?", tok.replace("%", ""))
    return float(m.group(0).replace(",", "").replace("−", "-")) if m else None


def parse_number(words: List[Word], i: int) -> Optional[Tuple[float, int, str, float]]:
    """A number starting at word i -> (value, words used, as written for the screen, scale shown as a word or 1)."""
    n = len(words)
    tok = words[i].norm
    v = _digits(tok)
    used, shown = 1, None
    if v is None:
        if tok in ("a", "an") and i + 1 < n and words[i + 1].norm in ("hundred", "thousand", "million", "billion"):
            v, used = 1.0, 1
        elif tok == "half" or tok in SMALL or tok in TENS or re.fullmatch(r"(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)-\w+", tok):
            v, used = 0.0, 0
            total = 0.0
            j = i
            while j < n:
                t = words[j].norm
                if t in SMALL:
                    v += SMALL[t]
                elif t in TENS:
                    v += TENS[t]
                elif "-" in t and t.split("-")[0] in TENS and t.split("-")[1] in SMALL:
                    v += TENS[t.split("-")[0]] + SMALL[t.split("-")[1]]
                elif t == "half" and j == i:
                    v = 0.5
                elif t == "and" and j > i and [x.norm for x in words[j + 1:j + 3]] == ["a", "half"]:
                    v += 0.5                   # "one and a half light-years" is 1.5, not a half
                    j += 3
                    break
                elif t == "hundred" and j > i:
                    v = max(v, 1) * 100
                elif t == "thousand" and j > i:
                    total += max(v, 1) * 1000
                    v = 0
                elif t == "and" and j > i and j + 1 < n and (words[j + 1].norm in SMALL or words[j + 1].norm in TENS):
                    pass
                else:
                    break
                j += 1
            used = j - i
            v = total + v
            if used == 0:
                return None
        else:
            return None
    else:
        shown = words[i].text.strip(",.;:!?").rstrip("%")
    scale = 1.0
    j = i + used
    if j < n and words[j].norm in ("million", "billion", "trillion"):
        scale = SCALES[words[j].norm]
        used += 1
    elif j < n and words[j].norm in ("hundred", "thousand") and shown is not None:
        v *= SCALES[words[j].norm]
        used += 1
        shown = None
    if shown is None:
        shown = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}".rstrip("0").rstrip(".")
    return v * scale, used, shown, scale


# unit words -> (kind, unit on screen, factor to the kind's base unit) -- base units: °C, bar, km, s, km/h, %, kg, W
UNITS: List[Tuple[Tuple[str, ...], str, str, float]] = [
    (("degrees", "celsius"), "temperature", "°C", 1), (("degrees", "fahrenheit"), "temperature", "°F", 1),
    (("degrees", "c"), "temperature", "°C", 1), (("°c",), "temperature", "°C", 1), (("kelvin",), "temperature", "K", 1),
    (("degrees",), "temperature", "°C", 1),
    (("millibars",), "pressure", "mbar", 0.001), (("millibar",), "pressure", "mbar", 0.001), (("mbar",), "pressure", "mbar", 0.001),
    (("bar",), "pressure", "BAR", 1), (("bars",), "pressure", "BAR", 1),
    (("atmospheres",), "pressure", "ATM", 1.013), (("atmosphere",), "pressure", "ATM", 1.013),
    (("kilometres", "an", "hour"), "speed", "KM/H", 1), (("kilometers", "an", "hour"), "speed", "KM/H", 1),
    (("kilometres", "per", "hour"), "speed", "KM/H", 1), (("kilometers", "per", "hour"), "speed", "KM/H", 1),
    (("kilometres", "a", "second"), "speed", "KM/S", 3600), (("kilometers", "a", "second"), "speed", "KM/S", 3600),
    (("kilometres", "per", "second"), "speed", "KM/S", 3600), (("kilometers", "per", "second"), "speed", "KM/S", 3600),
    (("miles", "an", "hour"), "speed", "MPH", 1.609), (("miles", "per", "hour"), "speed", "MPH", 1.609), (("mph",), "speed", "MPH", 1.609),
    (("km/h",), "speed", "KM/H", 1), (("km", "h"), "speed", "KM/H", 1), (("km/s",), "speed", "KM/S", 3600),
    (("light-seconds",), "light", "LIGHT-SECONDS", 1), (("light-second",), "light", "LIGHT-SECOND", 1),
    (("light", "seconds"), "light", "LIGHT-SECONDS", 1), (("light", "second"), "light", "LIGHT-SECOND", 1),
    (("light-minutes",), "light", "LIGHT-MINUTES", 60), (("light-minute",), "light", "LIGHT-MINUTE", 60),
    (("light", "minutes"), "light", "LIGHT-MINUTES", 60), (("light", "minute"), "light", "LIGHT-MINUTE", 60),
    (("light-hours",), "light", "LIGHT-HOURS", 3600), (("light-hour",), "light", "LIGHT-HOUR", 3600),
    (("light", "hours"), "light", "LIGHT-HOURS", 3600), (("light", "hour"), "light", "LIGHT-HOUR", 3600),
    (("light-days",), "light", "LIGHT-DAYS", 86400), (("light-day",), "light", "LIGHT-DAY", 86400),
    (("light", "days"), "light", "LIGHT-DAYS", 86400), (("light", "day"), "light", "LIGHT-DAY", 86400),
    (("light-years",), "light", "LIGHT-YEARS", 31557600), (("light-year",), "light", "LIGHT-YEAR", 31557600),
    (("light", "years"), "light", "LIGHT-YEARS", 31557600), (("light", "year"), "light", "LIGHT-YEAR", 31557600),
    (("kilometres",), "distance", "KM", 1), (("kilometers",), "distance", "KM", 1), (("kilometre",), "distance", "KM", 1),
    (("kilometer",), "distance", "KM", 1), (("km",), "distance", "KM", 1), (("miles",), "distance", "MILES", 1.609),
    (("metres",), "distance", "METRES", 0.001), (("meters",), "distance", "METRES", 0.001),
    (("astronomical", "units"), "distance", "AU", 1.496e8), (("au",), "distance", "AU", 1.496e8),
    (("seconds",), "duration", "SECONDS", 1), (("second",), "duration", "SECOND", 1),
    (("minutes",), "duration", "MINUTES", 60), (("minute",), "duration", "MINUTE", 60),
    (("hours",), "duration", "HOURS", 3600), (("hour",), "duration", "HOUR", 3600),
    (("days",), "duration", "DAYS", 86400), (("day",), "duration", "DAY", 86400),
    (("weeks",), "duration", "WEEKS", 604800), (("months",), "duration", "MONTHS", 2629800),
    (("years",), "duration", "YEARS", 31557600), (("year",), "duration", "YEAR", 31557600),
    (("percent",), "percent", "%", 1), (("per", "cent"), "percent", "%", 1),
    (("kilograms",), "mass", "KG", 1), (("kilogram",), "mass", "KG", 1), (("kg",), "mass", "KG", 1),
    (("tonnes",), "mass", "TONNES", 1000), (("tons",), "mass", "TONS", 907),
    (("watts",), "power", "WATTS", 1), (("watt",), "power", "WATT", 1),
    (("times",), "ratio", "×", 1),
]
UNITS.sort(key=lambda u: -len(u[0]))          # the longest unit phrase first ("light years" before "years")
ABBR = {"SECONDS": "S", "SECOND": "S", "MINUTES": "MIN", "MINUTE": "MIN", "HOURS": "H", "HOUR": "H", "DAYS": "D", "DAY": "D"}
TAIL_WORDS = {"between", "from", "in", "on", "at", "with", "by", "for", "into", "two", "its", "their", "our", "every", "each", "all", "as"}
FILLER = {"about", "around", "roughly", "nearly", "almost", "over", "under", "just", "only", "some", "more", "less", "than", "and",
          "the", "a", "an", "of", "to", "it", "its", "it's", "is", "was", "that", "this", "later", "so", "but", "then", "which"}


@dataclass
class Metric:
    kind: str
    value: float                  # in the kind's base unit
    shown: str                    # "1.3", "464", "6"
    unit: str                     # "SECONDS", "°C", "BILLION KM"
    i0: int                       # first and last word index (the number .. the unit)
    i1: int
    t: float                      # when the number is heard
    t_end: float
    approx: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.shown}{'' if self.unit.startswith('%') else ' '}{self.unit}" if self.unit != "×" else f"×{self.shown}"


def extract_metrics(words: List[Word]) -> List[Metric]:
    out: List[Metric] = []
    i, n = 0, len(words)
    while i < n:
        num = parse_number(words, i)
        if num is None:
            i += 1
            continue
        v, used, shown, scale = num
        j = i + used
        attached = "%" in words[j - 1].text
        unit = None
        if attached:
            unit = (("%",), "percent", "%", 1.0)
            j -= 1
        else:
            for u in UNITS:
                k = len(u[0])
                if [w.norm for w in words[j:j + k]] == list(u[0]):
                    unit = u
                    break
                # "1.3-light-seconds"/"light-years," as one token with a hyphen
                if k == 1 and j < n and words[j].norm.replace("–", "-") == u[0][0]:
                    unit = u
                    break
        if unit is None:
            i += max(1, used)
            continue
        words_used = len(unit[0]) if not attached else 0
        kind, ushow, factor = unit[1], unit[2], unit[3]
        if kind == "ratio":
            # "times" counts only as a comparison: "ninety times harder than", "twice"/"times more"
            nxt = " ".join(w.norm for w in words[j + 1:j + 5])
            if not re.search(r"\b(more|less|harder|bigger|larger|smaller|faster|slower|heavier|hotter|colder|thicker|denser|further|farther|brighter|stronger|weaker|as)\b", nxt):
                i = j + 1
                continue
        approx = i > 0 and words[i - 1].norm in ("about", "around", "roughly", "nearly", "almost", "some")
        if scale > 1 and kind not in ("ratio", "percent"):
            ushow = f"{SCALE_WORD.get(scale, '')} {ushow}".strip()
        last = j + words_used - 1 if words_used else i + used - 1      # "96.5%": the number is its own unit
        if kind == "distance" and last + 1 < n and words[last + 1].norm in ("up", "high", "down", "deep", "below", "above"):
            ushow = f"{ushow} {words[last + 1].norm.upper()}"
            last += 1
        m = Metric(kind, v * factor, shown, ushow, i, last, words[i].start, words[last].end, approx)
        # "eight minutes and twenty seconds": one duration on screen, "8 MIN 20 S"
        if out and kind == "duration" and out[-1].kind == "duration" and out[-1].i1 + 2 >= i and out[-1].value > m.value \
                and "MIN" not in out[-1].unit[4:]:
            p = out.pop()
            m = Metric("duration", p.value + m.value, f"{p.shown} {ABBR.get(p.unit, p.unit)} {shown}", ABBR.get(ushow, ushow),
                       p.i0, last, p.t, m.t_end, p.approx)
        out.append(m)
        i = last + 1
    return out


def sub_line(words: List[Word], m: Metric, cl: List[Tuple[int, int]]) -> str:
    """A few words that say what the number is about: the rest of its clause, else the next clause (as the references
    put "AT THE SPEED OF LIGHT" under "1.4 SECONDS")."""
    idx = next((k for k, (a, b) in enumerate(cl) if a <= m.i0 <= b), None)
    if idx is None:
        return ""
    cands = []
    a, b = cl[idx]
    cands.append([w for w in words[m.i1 + 1:b + 1]])
    cands.append([w for w in words[a:m.i0]])
    if idx + 1 < len(cl) and not re.search(r"[.?!]$", words[b].text):      # the next clause, never the next sentence
        a2, b2 = cl[idx + 1]
        cands.append(words[a2:b2 + 1])
    for c in cands:
        toks = [re.sub(r"[^\w'°%\-]", "", w.text) for w in c]
        toks = [t for t in toks if t]
        while toks and toks[0].lower() in FILLER:
            toks.pop(0)
        while toks and toks[-1].lower() in FILLER:
            toks.pop()
        content = [t for t in toks if t.lower() not in FILLER]
        if any(re.search(r"\d", t) for t in toks):
            continue                                   # another number: it gets its own callout
        if len(content) >= 2 and len(toks) <= 7:
            return " ".join(toks).upper()
        if len(content) >= 2:
            return " ".join(toks[:6]).upper()
    return ""


# ---- the pass ------------------------------------------------------------------------------------------------------------
LANDMARKS = [(1.28, "MOON", "1.3 LIGHT-SECONDS"), (499.0, "SUN", "8 LIGHT-MINUTES"), (15000.0, "NEPTUNE", "4 LIGHT-HOURS"),
             (1.338e8, "PROXIMA CENTAURI", "4.2 LIGHT-YEARS")]
HAZARDS = {
    "AIR": r"\b(oxygen|breath\w*|suffocat\w*|carbon dioxide|no air|the air|asphyxia\w*)\b",
    "TEMPERATURE": r"\b(degrees|hot|hotter|heat|melt\w*|boil\w*|cook\w*|burn\w*|scorch\w*|oven|lead)\b",
    "PRESSURE": r"\b(pressure|crush\w*|squeez\w*|atmospheres|bar)\b",
    "ACID": r"\bacid\w*\b",
    "RADIATION": r"\bradiation\b",
    "COLD": r"\b(freez\w*|frozen|cold|minus)\b",
}
LETHAL = r"\b(kill\w*|die|dies|died|dead|death|lethal|deadly|fatal|melt\w*|crush\w*|boil\w*|cook\w*|burn\w*|no oxygen|can'?t breathe|suffocat\w*|unprotected|seconds|instantly|wouldn'?t (last|survive)|not survive|destroy\w*|dissolv\w*)\b"
SAFE = r"\b(safe|comfortable|survivable|room temperature|summer day|like (on )?earth|same as earth|earth-like|just right|breathable|pleasant)\b"
SURVIVAL = r"\b(surviv\w*|unprotected|spacesuit|you'?d last|how long could you|suffocat\w*|lethal|kill you|you'?d die|you would die)\b"
ALTITUDE = r"\b(up|above|altitude|high|descen\w*|fall\w*|drop\w*|parachute|to the ground|from the ground|cloud\w*|down)\b"
SILENCE = (r"\b(went|goes|fell|go|falls) (silent|dark|quiet)\b|\bblack(ed|s)? out\b|\bpass(ed|es)? out\b|\blost contact\b|"
           r"\bstopped (transmitting|working|talking)\b|\bsignal (was |is )?lost\b|\byou'?d die\b|\b(it|you) died\b|\bflatline\w*\b")


def _clamp_end(t0: float, t1: float, lo: float, hi: float) -> float:
    return t0 + max(lo, min(hi, t1 - t0))


def _busy(spans: List[Tuple[float, float]], a: float, b: float, pad: float = 0.0) -> bool:
    return any(a < y + pad and x - pad < b for x, y in spans)


def _title_lines(title: str) -> Dict[str, str]:
    """A title split for the card: the last few words (the question's point) in the accent line."""
    w = str(title).upper().split()
    if len(w) <= 3:
        return {"line1": "", "line2": " ".join(w), "accent": "amber"}
    k = max(1, min(len(w) - 2, (len(w) + 1) // 2))
    for i, x in enumerate(w):              # "WHAT IF YOU TRAVELED AT | THE SPEED OF LIGHT?"
        if i >= 2 and x in ("THE", "ONE", "A", "TO", "ON", "IN") and len(w) - i <= 5:
            k = i
            break
    return {"line1": " ".join(w[:k]), "line2": " ".join(w[k:]), "accent": "amber"}


def _subject(sentence: str, beats: List[Any], t: float, exclude: str = "") -> str:
    """The world a sentence is about: one it names (not `exclude`, the other side of a comparison), else its beat's place."""
    for m in re.finditer(r"\b(Mercury|Venus|Earth|Mars|Jupiter|Saturn|Uranus|Neptune|Pluto|the Moon|Titan|Europa|the Sun)\b", sentence):
        name = m.group(1).replace("the ", "").upper()
        if name != exclude.upper():
            return name
    b = next((x for x in beats if x.start <= t < x.end), None)
    raw = str(getattr(b, "place", "") or "")
    if "+" in raw and not exclude:                         # a pair of worlds: both, in the order the beat names them
        return " TO ".join(x.strip().replace("_", " ").upper() for x in raw.split("+")[:2])
    place = re.split(r"[;+@]", raw)[0].replace("_", " ").upper()
    return "" if place == exclude.upper() else place


def _warm(sentence: str, beats: List[Any], t: float) -> bool:
    """A warm (amber-brown) plate on a hot world, a cool slate one elsewhere -- as the references tint by subject."""
    return bool(re.search(r"\b(venus|sun|mercury|lava|heat|hot)\b", sentence + " " + _subject(sentence, beats, t), re.I))


def _survival_wanted(text: str) -> bool:
    return len(re.findall(SURVIVAL, text, re.I)) >= 3


def _survival(words: List[Word], sn, metrics: List[Metric], dur: float, notes: List[str], beat_end=None) -> List[Dict[str, Any]]:
    text = " ".join(w.text for w in words)
    chips = ["AIR", "TEMPERATURE", "PRESSURE"]
    for extra in ("ACID", "RADIATION", "COLD"):
        if re.search(HAZARDS[extra], text, re.I):
            chips.append(extra)
            break
    first = next((words[a].start for a, b in sn if re.search(SURVIVAL, span_text(words, a, b), re.I)), None)
    if first is None:
        return []
    lethal: set = set()
    states = [{"t": round(max(0.0, first - LEAD_S), 3), "verdict": "—", "sub": "UNPROTECTED", "lethal": []}]
    for a, b in sn:
        s = span_text(words, a, b)
        t = round(words[a].start - LEAD_S, 3)
        if t < first - 0.2:
            continue
        named = [c for c in chips if re.search(HAZARDS[c], s, re.I)]
        if not named:
            continue
        before = set(lethal)
        sm = [m for m in metrics if a <= m.i0 <= b]
        extreme = {"TEMPERATURE": any(m.kind == "temperature" and (m.value > 60 or m.value < -40) for m in sm),
                   "PRESSURE": any(m.kind == "pressure" and (m.value > 5 or m.value < 0.3) for m in sm)}
        if re.search(SAFE, s, re.I):
            lethal -= set(named)
        elif re.search(LETHAL, s, re.I) or any(extreme.get(c) for c in named):
            lethal |= {c for c in named if c not in ("TEMPERATURE", "PRESSURE") or extreme.get(c) or re.search(LETHAL, s, re.I)}
        said = re.search(r"\b(?:last|survive)\w*\s+(?:for\s+)?(?:only\s+)?(?:about\s+|around\s+|maybe\s+)?(\S+)\s+(seconds|minutes|hours|days)\b", s, re.I)
        verdict = said.group(2).upper() if said else ("SECONDS" if len(lethal) >= 2 else "MINUTES" if lethal else "—")
        if lethal != before or said:
            states.append({"t": t, "verdict": verdict, "sub": "UNPROTECTED", "color": "red" if lethal or said else "white", "lethal": sorted(lethal)})
    # the act lasts while the narration talks about surviving or the hazards: to the end of the beat of the last such sentence
    last = max([words[b].end for a, b in sn if words[a].start >= first and (re.search(SURVIVAL, span_text(words, a, b), re.I) or
                any(re.search(HAZARDS[c], span_text(words, a, b), re.I) for c in chips))] or [dur])
    end = min(dur, beat_end(last - 0.01) if beat_end else dur)
    if words and words[-1].end - 25 < last and re.search(r"\bsurviv|\blive\b", " ".join(w.text for w in words[-40:]), re.I):
        end = dur                                   # a survival question to the very end
    notes.append(f"telemetry: survival clock {first:.1f}-{end:.1f}s ({len(states) - 1} state change(s))")
    return [{"type": "tm_survival", "chips": chips, "states": states, "start": round(max(0.0, first - LEAD_S), 3), "end": round(end, 3),
             "fade_in": 0.05, "fade_out": 0.4, "z": 10}]


def _gauge(words: List[Word], sn, metrics: List[Metric], dur: float, notes: List[str], beat_end=None, foot=()) -> List[Dict[str, Any]]:
    alt = []
    for m in metrics:
        if m.kind != "distance" or m.value > 1000 or m.value <= 0:
            continue
        a, b = next(((a, b) for a, b in sn if a <= m.i0 <= b), (m.i0, m.i1))
        if re.search(ALTITUDE, span_text(words, a, b), re.I):
            alt.append((m, a, b))
    if len(alt) < 3:
        return []
    top = max(m.value for m, _, _ in alt)
    step = next(x for x in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250) if top * 1.15 / x <= 9)     # round ticks, at most 9
    mx = math.ceil(top * 1.15 / step) * step
    keys = []
    for m, a, b in alt:
        other = [x.label for x in metrics if a <= x.i0 <= b and x.kind in ("temperature", "pressure")]
        keys.append({"t": round(m.t - LEAD_S, 3), "v": m.value, "text": f"{m.shown} km", "sub": " · ".join(other)})
    t0 = keys[0]["t"]
    t1 = min(dur, keys[-1]["t"] + 12.0, beat_end(keys[-1]["t"] + LEAD_S) if beat_end else dur,
             min([a for a, _ in foot if a > keys[-1]["t"]] or [dur]))
    notes.append(f"telemetry: altitude gauge {t0:.1f}-{t1:.1f}s ({len(keys)} altitudes)")
    layer = {"type": "tm_gauge", "label": "ALTITUDE", "min": 0, "max": mx, "step": step, "keys": keys,
             "start": round(t0, 3), "end": round(t1, 3), "fade_in": 0.3, "fade_out": 0.4, "z": 9}
    zones = gauge_zones(words, sn)
    if zones:
        layer["zones"] = zones
        layer["max"] = max(mx, math.ceil(max(z["to"] for z in zones) * 1.05 / step) * step)
        notes.append(f"telemetry: altitude zones from the narration: {', '.join(z['label'] for z in zones)}")
    return [layer]


ZONE = re.compile(r"((?:[a-z]+ ){0,2}(?:clouds?|haze|air|atmosphere|layer))\b[^.?!]{0,50}?\b(?:from|between)\s+(\d+(?:\.\d+)?)\s*(?:to|and)\s*(\d+(?:\.\d+)?)\s*(?:km|kilomet\w+)", re.I)
ZONE_COLOURS = ("amber", "#5B8DEF", "#E2552B", "#2EE6A8")


def gauge_zones(words: List[Word], sn) -> List[Dict[str, Any]]:
    """Altitude zones the narration itself states ("the acid clouds run from 48 to 70 kilometres"): a labelled band on the gauge. Nothing is
    invented -- no statement, no zone."""
    out: List[Dict[str, Any]] = []
    for a, b in sn:
        for m in ZONE.finditer(span_text(words, a, b)):
            label = re.sub(r"^(the|a|an|of|in|and)\s+", "", m.group(1).strip(), flags=re.I).upper()
            lo, hi = sorted((float(m.group(2)), float(m.group(3))))
            if label and hi > lo and not any(z["label"] == label for z in out):
                out.append({"from": lo, "to": hi, "label": label, "color": ZONE_COLOURS[len(out) % len(ZONE_COLOURS)]})
    return out


LIGHT_SECONDS = 299792.458          # km per second


def light_clock(words: List[Word], sn, metrics: List[Metric], dur: float, text: str, notes: List[str]) -> List[Dict[str, Any]]:
    """V3's "LIGHT FROM EARTH TO YOU" clock: a dial and an HH:MM:SS that follows how long light needs to reach the traveller from home, with
    the year underneath. Built only from distances and light-times the narrator says, on a journey told in the second person."""
    if not re.search(r"\b(you|your ship|voyager|the probe|the ship)\b", text, re.I):
        return []
    pts = []
    for m in metrics:
        sent = span_text(words, *next(((a, b) for a, b in sn if a <= m.i0 <= b), (m.i0, m.i1)))
        if m.kind == "light":
            secs = m.value
        elif m.kind == "distance" and m.value >= 1e6 and re.search(r"\b(away|from (earth|home|the sun)|out)\b", sent, re.I):
            secs = m.value / LIGHT_SECONDS
        elif m.kind == "duration" and re.search(r"\blight\b.{0,40}\b(takes?|needs?|reach\w*)\b", sent, re.I):
            secs = m.value
        else:
            continue
        pts.append((m.t - LEAD_S, secs))
    keys, last = [], -1.0
    for t, sec in sorted(pts):
        if sec >= last:                                   # light from home only grows on an outward journey
            keys.append({"t": round(t, 3), "seconds": round(sec, 2)})
            last = sec
    if len(keys) < 2:
        return []
    start = max(0.0, keys[0]["t"] - 2.0)
    keys.insert(0, {"t": round(start, 3), "seconds": 0})
    years = [{"t": round(w.start - LEAD_S, 3), "text": w.norm} for w in words if re.fullmatch(r"(19[5-9]\d|20\d\d)", w.norm)]
    notes_ = [{"t": y["t"], "text": y["text"]} for y in years if y["t"] >= start]
    end = min(dur, keys[-1]["t"] + 10.0)
    notes.append(f"telemetry: light-from-Earth clock {start:.1f}-{end:.1f}s ({len(keys) - 1} readings)")
    return [{"type": "tm_clock", "mode": "light", "label": "LIGHT FROM EARTH TO YOU", "color": "amber", "keys": keys, "notes": notes_,
             "start": round(start, 3), "end": round(end, 3), "fade_in": 0.3, "fade_out": 0.4, "z": 10}]


def _dual_clocks(words: List[Word], sn, metrics: List[Metric], dur: float, text: str, notes: List[str]) -> List[Dict[str, Any]]:
    if not (re.search(r"\bspeed of light\b", text, re.I) and re.search(r"\b(travell?er|for you|your (watch|clock|time)|time on earth|earth time|back home)\b", text, re.I)):
        return []
    first = next((words[a].start for a, b in sn if re.search(r"\b(clock|travell?er|time on earth|for you)\b", span_text(words, a, b), re.I)), None)
    if first is None:
        return []
    earth = [{"t": round(first - LEAD_S, 3), "text": "0", "unit": "SECONDS", "note": "BACK HOME"}]
    you = [{"t": round(first - LEAD_S, 3), "text": "0", "unit": "SECONDS", "note": "AT THE SPEED OF LIGHT"}]
    best_e, best_y = 0.0, 0.0
    for m in metrics:
        if m.kind != "duration" or m.t < first:
            continue
        a, b = next(((a, b) for a, b in sn if a <= m.i0 <= b), (m.i0, m.i1))
        s = span_text(words, a, b)
        mine = re.search(r"\b(for you|your (watch|clock|time)|travell?er|you'?d age|you age)\b", s, re.I)
        side, best = (you, best_y) if mine else (earth, best_e)
        if m.value <= best:
            continue
        side.append({"t": round(m.t - LEAD_S, 3), "text": m.shown, "unit": m.unit.split()[-1], "note": side[0]["note"]})
        if mine:
            best_y = m.value
        else:
            best_e = m.value
    notes.append(f"telemetry: dual clocks from {first:.1f}s (Earth {len(earth) - 1}, traveller {len(you) - 1} reading(s))")
    return [{"type": "tm_clock", "mode": "dual", "left": {"label": "EARTH TIME", "color": "amber", "keys": earth},
             "right": {"label": "TRAVELLER", "color": "cyan", "keys": you}, "start": round(first - LEAD_S, 3), "end": round(dur, 3),
             "fade_in": 0.05, "fade_out": 0.4, "z": 10}]


def _credit_kind(credit: str) -> str:
    c = credit.lower()
    if "ai " in c or c.startswith("ai") or "flow" in c:
        return "AI ILLUSTRATION"
    if any(x in c for x in ("pexels", "pixabay", "stock", "storyblocks")):
        return "FOOTAGE"
    return "REAL IMAGE" if c else "IMAGE"


def _credit_text(credit: str) -> str:
    return re.sub(r"^(photo|image|credit|footage)\s*:\s*", "", credit.strip(), flags=re.I)[:90]


# ---- CSV rows (beat_csv layer types metric / diagram / hud) --------------------------------------------------------------
DIAGRAMS = ("logaxis", "bars", "curve", "compare", "particles", "composition", "timeline", "discmap")
HUDS = ("survival", "dual_clock", "light_clock", "gauge", "date", "mission")
MISSION_STAGES = ["APPROACH", "PHOTON SPHERE", "EDGE", "INSIDE", "SINGULARITY"]


def _pairs(text: str) -> List[Tuple[str, str]]:
    """"VENERA 7=23 MIN; VENERA 13=127 MIN*" -> [(label, value)]"""
    out = []
    for part in (text or "").split(";"):
        if part.strip():
            k, _, v = part.partition("=")
            out.append((k.strip(), v.strip()))
    return out


def _num(s: str) -> float:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", s or "")
    return float(m.group(0).replace(",", "")) if m else 0.0


def layers_from_row(it: Any, start: float, end: float) -> List[Dict[str, Any]]:
    """A CSV layer row of type metric / diagram / hud -> engine layers (raises ValueError with what the row should say)."""
    timing = {"start": start, "end": end}
    ty = it.type
    if ty == "metric":
        if not (it.label or it.text or it.value_to is not None):
            raise ValueError("a metric needs label (the number as shown, e.g. 464 °C) or value_to + format")
        big = it.label or it.text or (f"{it.value_to:g} {it.format}".strip())
        return [{"type": "tm_metric", "text": big, "sub": it.sub, "anchor": it.anchor if it.anchor in
                 ("center", "top", "upper_left", "left", "right", "upper_right", "low") else "top", "size": it.extra.get("size", "large"),
                 **timing, "fade_in": 0.05, "fade_out": 0.3, "z": 5}]
    if ty == "diagram":
        kind = (it.id or "").lower()
        if kind not in DIAGRAMS:
            raise ValueError(f"a diagram's id is its kind: {', '.join(DIAGRAMS)} (got {it.id!r})")
        plate = {"type": "tm_plate", "covers": True, "tint": it.extra.get("tint", "cool"), "title": it.label, "sub": it.sub, **timing,
                 "fade_in": 0.05, "fade_out": 0.05, "z": -5, "cite": ["DIAGRAM", it.extra.get("cite", "")]}
        pairs = _pairs(it.text)
        if kind == "bars":
            d = {"type": "tm_bars", "rows": [{"label": k.rstrip("*"), "value": _num(v), "text": v.rstrip("*"),
                                              "highlight": k.endswith("*") or v.endswith("*")} for k, v in pairs]}
        elif kind == "logaxis":
            marks = [{"v": _light_s(v), "label": k, "sub": v} for k, v in pairs]
            d = {"type": "tm_logaxis", "marks": marks, "keys": [{"t": start + 0.4, "v": marks[-1]["v"]}] if marks else []}
        elif kind == "curve":
            d = {"type": "tm_curve", "shape": it.extra.get("shape", "decay"), "x_label": it.extra.get("x", "SPEED →"),
                 "y_label": it.extra.get("y", ""), "limit_label": it.extra.get("limit", ""), "keys": [{"t": start + 0.6, "x": 0.5}, {"t": start + 2.2, "x": 0.98}]}
        elif kind in ("compare", "particles"):
            if len(pairs) != 2:
                raise ValueError("a compare diagram needs text with two sides: LEFT=value; RIGHT=value")
            (lk, lv), (rk, rv) = pairs
            a, b = _num(lv) or 1, _num(rv) or 1
            d = {"type": "tm_compare", "mode": "particles" if kind == "particles" else it.extra.get("mode", "cards"),
                 "left": {"label": lk, "value": lv, "amount": a, "n": int(min(900, 600 * a / max(a, b))) or 3, "color": "amber"},
                 "right": {"label": rk, "value": rv, "amount": b, "n": int(min(900, 600 * b / max(a, b))) or 3, "color": "cyan"}}
        elif kind == "discmap":
            d = {"type": "tm_discmap", "earth": it.label or "EARTH"}
            if it.text:
                plate["asset"] = it.text                      # the photograph in the disc: nasa_image:<what>
            plate["cite"] = ["DIAGRAM", str(it.extra.get("cite", "GALAXIES: NASA, ESA, CSA, STSCI"))]
        elif kind == "composition":
            d = {"type": "tm_composition", "parts": [{"label": k, "pct": _num(v)} for k, v in pairs]}
            if it.extra.get("note"):
                d["note"] = {"text": it.extra["note"], "color": "red"}
        else:
            ev = [{"year": int(_num(v)), "label": k, "t": start + 0.4 + 0.5 * i} for i, (k, v) in enumerate(pairs)]
            years = [e["year"] for e in ev] or [2000]
            d = {"type": "tm_timeline", "events": ev, "from": int(it.value_from or min(years) - 2), "to": int(it.value_to or max(years) + 2),
                 "step": 10 if max(years) - min(years) > 30 else 5}
        return [plate, {**d, **timing, "fade_in": 0.05, "fade_out": 0.05}]
    if ty == "hud":
        kind = (it.id or "").lower()
        if kind not in HUDS:
            raise ValueError(f"a hud's id is its kind: {', '.join(HUDS)} (got {it.id!r})")
        if kind == "mission":
            # one beat of the mission card (V4): value_to + format = the number ("6.3" "MILLION KM"), label = what it measures, sub = the status
            # line, text = the stage (a name from extra "stages", or its number); every mission row joins one card (shot_csv._merge_missions)
            if it.value_to is None and not it.label:
                raise ValueError("a mission row needs value_to (the number) and format (its unit), e.g. 6.3 + MILLION KM")
            stages = [x.strip().upper() for x in str(it.extra.get("stages", "")).split(";") if x.strip()] or MISSION_STAGES
            st = (it.text or "").strip().upper()
            idx = stages.index(st) if st in stages else int(_num(st)) if _num(st) is not None else 0
            key = {"t": round(start, 3), "value": it.value_to if it.value_to is not None else 0, "unit": (it.format or "").upper(),
                   "label": (it.label or "DISTANCE").upper(), "status": (it.sub or "").upper(), "stage": max(0, min(len(stages) - 1, idx))}
            until = it.extra.get("until")
            return [{"type": "tm_mission", "kicker": str(it.extra.get("kicker", "MISSION")).upper(), "stages": stages, "keys": [key],
                     "start": start, "end": float(until) if until is not None else max(end, start + 600.0), "z": 11}]
        if kind == "survival":
            chips = [c.strip().upper() for c in (it.text or "AIR;TEMPERATURE;PRESSURE").split(";") if c.strip()]
            lethal = [c.strip().upper() for c in str(it.extra.get("lethal", "")).split(";") if c.strip()]
            return [{"type": "tm_survival", "chips": chips, "states": [{"t": start, "verdict": it.label or "—", "sub": it.sub,
                     "color": "red" if lethal or it.label else "white", "lethal": lethal}], **timing, "z": 10}]
        if kind == "gauge":
            keys = [{"t": start + 0.3, "v": _num(v), "text": v, "sub": k} for k, v in _pairs(it.text)]
            return [{"type": "tm_gauge", "label": it.label or "ALTITUDE", "min": it.value_from or 0, "max": it.value_to or 100, "keys": keys, **timing, "z": 9}]
        if kind == "dual_clock":
            (lk, lv), (rk, rv) = (_pairs(it.text) + [("EARTH TIME", "0"), ("TRAVELLER", "0")])[:2]
            side = lambda lab, v, c: {"label": lab, "color": c, "keys": [{"t": start, "text": v.split()[0] if v else "0",   # noqa: E731
                                                                          "unit": " ".join(v.split()[1:]) or "SECONDS"}]}
            return [{"type": "tm_clock", "mode": "dual", "left": side(lk, lv, "amber"), "right": side(rk, rv, "cyan"), **timing, "z": 10}]
        if kind == "light_clock":
            return [{"type": "tm_clock", "mode": "light", "label": it.label or "LIGHT FROM EARTH",
                     "keys": [{"t": start, "seconds": (it.value_from or 0)}, {"t": end, "seconds": it.value_to or it.value_from or 0}],
                     "notes": [{"t": start, "text": it.sub}] if it.sub else [], **timing, "z": 10}]
        return [{"type": "tm_clock", "mode": "date", "keys": [{"t": start, "text": it.label or it.text}], **timing, "z": 9}]
    raise ValueError(f"unknown telemetry row type {ty!r}")


def _light_s(v: str) -> float:
    """A logaxis value in light-travel seconds: "1.3 light-seconds", "8 light-minutes", "4.2 light-years", and plain distances too
    ("400,000 km", "9.5 trillion km", "1 AU", "93 million miles"), which an AI-written CSV gives as often."""
    low = (v or "").lower()
    n = (_num(v) or 1.0) * next((f for k, f in (("thousand", 1e3), ("million", 1e6), ("billion", 1e9), ("trillion", 1e12)) if k in low), 1.0)
    if "light" in low or re.search(r"\b(seconds?|minutes?|hours?|days?|years?)\b", low):
        for k, f in (("second", 1), ("minute", 60), ("hour", 3600), ("day", 86400), ("year", 31557600)):
            if k in low:
                return n * f
    if re.search(r"\b(au|astronomical units?)\b", low):
        return n * 499.0
    if re.search(r"\b(km|kilomet\w*)\b", low):
        return n / 299792.458
    if re.search(r"\bmiles?\b", low):
        return n * 1.609344 / 299792.458
    return n
