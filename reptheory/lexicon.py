"""Fitness concepts the planner can recognise in narration, and which art / treatment each one gets. A concept with no art in the library is simply shown as a callout on the
trainee (never a made-up illustration). Regexes run on the sentence text; `art` ids refer to reptheory/art.py's ART."""
from __future__ import annotations
import re

# id -> dict(rx, label, art, kind). kind: prop | anatomy | pose
CONCEPTS = {
    "bottle": dict(rx=r"\bbottles?\b", label="BOTTLE", art="prop_bottle_2l_v1", kind="prop", rings=(("neck", (0.5, 0.085, 0.075)), ("", (0.5, 0.04, 0.07)))),   # rings = (word, (x, y, radius)) as fractions of the picture's width/height/width; first word found in the sentence wins, "" is the default
    "forearm": dict(rx=r"\bforearms?\b", label="FOREARM", art="anat_forearm_v1", kind="anatomy", glow=((0.27, 0.26, 0.26, 0.42), (0.73, 0.26, 0.26, 0.42))),   # glow = ellipses (cx, cy, rx, ry) as fractions
    "cap": dict(rx=r"\bcap\b", label="CAP ON TIGHT", art="prop_bottle_2l_v1", kind="prop", rings=(("", (0.5, 0.04, 0.07)),)),
    "hang": dict(rx=r"\b(hang|hanging|pull-?up bar|dead hang)\b", label="BAR HANG", art="rep_hang_v1", kind="pose"),
}
NEGATION = re.compile(r"\b(no|not|don'?t|do not|without|nothing|never)\b", re.I)
CHIP_RULES = [   # (regex, builder) -> chip text; the captured words come straight from the narration
    (re.compile(r"\ball you need is (?:a |an |the )?(.+?)(?: of [a-z ]+)?[.,;]?$", re.I), lambda m: _clip(m.group(1), 4)),
    (re.compile(r"\bby the (\w+)", re.I), lambda m: f"BY THE {m.group(1).upper()}"),
    (re.compile(r"\bfor as long as you can\b", re.I), lambda m: "AS LONG AS YOU CAN"),
    (re.compile(r"\bbeginner (\w+)", re.I), lambda m: f"BEGINNER {m.group(1).upper()}"),
    (re.compile(r"\bwhere you(?:'ll| will) feel it\b", re.I), lambda m: "WHERE YOU FEEL IT"),
    (re.compile(r"\bwith both hands\b", re.I), lambda m: "BOTH HANDS"),
    (re.compile(r"\b(?:with|using)\s+(?:just |only )?(?:your )?(fingers? and thumbs?)\b", re.I), lambda m: m.group(1).upper()),
]
TIER_RX = re.compile(r"\b(?:lands?|goes|ranks?|ranked|placed?|sits?|comes?)\s+(?:in|at|on)\s+(?:the\s+)?([SABCDF])[\s-]*tier\b|\b(?:is|are)\s+(?:an?\s+)?([SABCDF])[\s-]tier\b", re.I)   # a placement; "from S tier at the top down to F tier" only describes the scale
TIER_TALK_RX = re.compile(r"\b(?:rank|ranks|ranking|tier list|tiers?)\b", re.I)
NUMBER_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
NUMBER_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100})
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"; _ONES = "one|two|three|four|five|six|seven|eight|nine"
_SPOKEN = (rf"(?:{_ONES}|zero)\s+point\s+(?:{_ONES}|zero)|(?:{_ONES}|ten)\s+(?:hundred|thousand)|(?:{_ONES}|{_TENS})\s+and\s+a\s+half|")      # "one point six", "three hundred", "one and a half"
NUM = r"(\d+(?:\.\d+)?|" + _SPOKEN + r"(?:" + _TENS + r")[\s-](?:" + _ONES + r")|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"      # "sixty eight" / "sixty-eight" read as one number
PCT_RX = re.compile(rf"\b{NUM}\s*(?:%|percent\b|per cent\b)", re.I)
EQ_RX = re.compile(rf"\b{NUM}\s*(?:l|litres?|liters?)\b.{{0,40}}?\b{NUM}\s*(?:kg|kilograms?|kilos?)\b", re.I)

def _clip(text: str, n: int) -> str: return " ".join(text.upper().split()[:n])
def num(tok: str) -> str:
    t = tok.lower(); parts = t.replace("-", " ").split()
    if len(parts) == 3 and parts[1] == "point" and parts[0] in NUMBER_WORDS and parts[2] in NUMBER_WORDS: return f"{NUMBER_WORDS[parts[0]]}.{NUMBER_WORDS[parts[2]]}"
    if len(parts) == 2 and parts[1] in ("hundred", "thousand") and parts[0] in NUMBER_WORDS: return str(NUMBER_WORDS[parts[0]] * (100 if parts[1] == "hundred" else 1000))
    if len(parts) == 4 and parts[1:] == ["and", "a", "half"] and parts[0] in NUMBER_WORDS: return f"{NUMBER_WORDS[parts[0]]}.5"
    if len(parts) == 2 and parts[0] in NUMBER_WORDS and parts[1] in NUMBER_WORDS: return str(NUMBER_WORDS[parts[0]] + NUMBER_WORDS[parts[1]])
    return str(NUMBER_WORDS[t]) if t in NUMBER_WORDS else tok

def concepts_in(text: str) -> list:
    return [cid for cid, c in CONCEPTS.items() if re.search(c["rx"], text, re.I)]

IMPERATIVES = {"stand", "keep", "hold", "squeeze", "pinch", "rest", "switch", "breathe", "stay", "grip", "pull", "push", "lift", "lower", "hang", "brace", "relax", "screw"}
QTY_RX = re.compile(rf"\b{NUM}\s*(litres?|liters?|kilograms?|kilos?|kg|seconds?|reps?|sets?|weeks?|minutes?|days?|times|grams?|g|calories|kcal|steps|hours?|degrees|beats)\b", re.I)
UNIT_ABBR = {"litre": "L", "liter": "L", "kilogram": "KG", "kilo": "KG", "kg": "KG", "second": "S", "rep": "REPS", "week": "WEEKS", "minute": "MIN", "day": "DAYS", "set": "SETS", "time": "TIMES",
             "gram": "G", "g": "G", "calorie": "KCAL", "kcal": "KCAL", "step": "STEPS", "hour": "H", "degree": "°", "beat": "BEATS"}
def quantity(text: str):
    """'2 L' for the first quantity the narration states (number words understood), else ''. Only what is said is shown."""
    m = QTY_RX.search(text)
    if not m: return ""
    u = m.group(2).lower().rstrip("s") if m.group(2).lower() not in ("kg",) else "kg"
    return f"{num(m.group(1))} {UNIT_ABBR.get(u, u.upper())}"
HOLD_RX = re.compile(r"\b(hold|holding|pinch|pinching|squeez\w*|grip|slip|switch)\b", re.I)      # the bottle is being used, not just shown
HOLD_HEAD = (("pinch", "PINCH GRIP"), ("squeez", "SQUEEZE"), ("hold", "HOLD"))
SQUEEZE_RX = r"^(pinch|squeez\w*)$"
