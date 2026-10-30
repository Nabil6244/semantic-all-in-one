"""Narrative analysis for Rep Theory R1: what each stretch of narration IS (role), what it names (entities), where the units / hook / roadmap / benchmark are. Everything is read from the
spoken words with rules and nothing is invented: an element the script does not contain stays absent, and every entity carries the words it came from (its `span`), which is what the planning
report and the grounding checks use. Pure functions over text; no rendering, no assets."""
from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple

from . import lexicon as LX

ROLES = ("hook", "claim", "mechanism", "evidence", "cue", "mistake", "progression", "number", "routine", "benchmark", "cta", "statement")

ROLE_RULES: List[Tuple[str, "re.Pattern"]] = [      # first match wins; a role is a hypothesis with the cue words that supported it
    ("cta", re.compile(r"\b(comment|subscribe|link (?:is )?in (?:the )?description|telegram|join (?:the|our)|follow along)\b", re.I)),
    ("evidence", re.compile(r"\b(studies|study|researchers?|research|review|paper|trial|scientists?|et al)\b", re.I)),
    ("benchmark", re.compile(r"\b(tier|benchmark|scorecard|rank(?:ed|ing)?|your level|test yourself|(?:the|this|a) (?:simple |quick |beginner )?test)\b", re.I)),
    ("mistake", re.compile(r"\b(mistake|wrong|avoid|never|common error|most people|stop)\b|\b(won'?t|will not|can'?t|cannot)\s+(?:fix|work|help|build|grow|change)", re.I)),
    ("progression", re.compile(r"\b(progress\w*|harder|easier|next level|too easy|add (?:weight|more)|then move|level up|drop to|scale it)\b", re.I)),
    ("routine", re.compile(r"\b(times? a week|days? a week|per week|each week|every (?:day|week|morning)|sets?|reps?|routine|schedule|plan|(?:measure|test) again)\b", re.I)),
]
MECH_RX = re.compile(r"\b(because|which is why|that is why|so that|means|works|is made of|is bone|bone and|nervous|fib(?:re|er)s?|anatomy|blood|joint|there is no|almost no)\b", re.I)

BODY = {      # canonical part -> words that name it
    "wrist": ("wrist", "wrists"), "forearm": ("forearm", "forearms"), "hand": ("hand", "hands"), "finger": ("finger", "fingers", "thumb", "thumbs"), "grip": ("grip",),
    "tendon": ("tendon", "tendons"), "bone": ("bone", "bones"), "muscle": ("muscle", "muscles"), "calf": ("calf", "calves"), "shoulder": ("shoulder", "shoulders"), "chest": ("chest",),
    "back": ("back",), "leg": ("leg", "legs"), "knee": ("knee", "knees"), "core": ("core", "abs"), "arm": ("arm", "arms"),
    "lat": ("lat", "lats", "latissimus"), "scapula": ("scapula", "scapulae", "scapular", "shoulder blade", "shoulder blades"), "trapezius": ("trapezius", "traps"), "spine": ("spine", "spinal"),
    "hip": ("hip", "hips"), "glute": ("glute", "glutes"), "neck": ("neck",), "ankle": ("ankle", "ankles"), "elbow": ("elbow", "elbows"),
}
PROPS = ("bottle", "cap", "book", "books", "hammer", "towel", "backpack", "chair", "wall", "bar", "doorway", "tape", "weight", "plate", "step", "rope")
EXERCISES = (r"pinch hold", r"pinch(?:ing)?", r"hammer rotations?", r"wrist curls?", r"dead hang|bar hang|hang(?:ing)?", r"push[- ]?ups?", r"pull[- ]?ups?", r"squats?", r"planks?", r"finger curls?", r"rotations?", r"squeez\w+")
ORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "zero": 0}
UNIT_RX = re.compile(r"\b(move|hold|reason|phase|level|step|exercise|rule|tip|week|part|chapter|section)\s+(one|two|three|four|five|six|seven|eight|nine|ten|zero|\d+)\b", re.I)
ORDINAL_RX = re.compile(r"^\s*(first|second|third|fourth|fifth|finally|lastly)\b[,:]?", re.I)
HEADING_RX = re.compile(r"^\s*(?:here is|here's|this is)\s+the\s+(catch|limit|rule|plan|fix|trick|problem|test|science|truth)\b", re.I)
HOOK_RULES = [      # (type, regex) on the opening beats only
    ("test", re.compile(r"\b(as many .{0,30} as you can|do this now|right now|keep (?:that|this) number|at the end of this video|try this)\b", re.I)),
    ("story", re.compile(r"\b(in (?:1[0-9]{3}|20[0-2][0-9])|called him|nicknamed|weighed .{0,20} lifted)\b", re.I)),
    ("myth", re.compile(r"\b(won'?t|will not|can'?t|cannot|myth|you can'?t change|not muscle|everything you know|wrong)\b", re.I)),
    ("claim", re.compile(r"\b(have you ever noticed|ever noticed|stronger than|(?:do not|don'?t|never) need|nobody tells you|the truth about)\b", re.I)),
]
ROADMAP_RX = re.compile(rf"\b({LX.NUM})\s+(moves?|holds?|reasons?|steps?|phases?|exercises?|levels?|things?|rules?|mistakes?)\b", re.I)
TEST_PROMISE_RX = re.compile(r"\b(keep (?:that|this) number|at the end of this video|i(?:'ll| will) tell you what it says|what it says about you)\b", re.I)

def _num(tok: str) -> Optional[int]:
    v = LX.num(tok)
    return int(v) if v.isdigit() else None

def _tokens(text: str) -> List[str]: return re.findall(r"[A-Za-z0-9'%-]+", text)

def entities(text: str) -> Dict[str, list]:
    """Everything the narration names, each with the matched words: {numbers, body, props, exercises, tiers, study}."""
    out: Dict[str, list] = {"numbers": [], "body": [], "props": [], "exercises": [], "tiers": [], "study": []}
    for m in LX.QTY_RX.finditer(text):
        u = m.group(2).lower(); u = u.rstrip("s") if u != "kg" else u; n = _num(m.group(1))
        out["numbers"].append({"value": LX.num(m.group(1)), "unit": LX.UNIT_ABBR.get(u, u.upper()), "text": m.group(0), "pos": m.start()})
    for m in LX.PCT_RX.finditer(text): out["numbers"].append({"value": LX.num(m.group(1)), "unit": "%", "text": m.group(0), "pos": m.start()})
    out["numbers"].sort(key=lambda e: e["pos"])
    low = text.lower()
    for part, words in BODY.items():
        for w in words:
            m = re.search(rf"\b{w}\b", low)
            if m: out["body"].append({"part": part, "text": w, "pos": m.start()}); break
    out["body"].sort(key=lambda e: e["pos"])
    for p in PROPS:
        m = re.search(rf"\b{p}\b", low)
        if m: out["props"].append({"prop": p, "text": p, "pos": m.start()})
    for rx in EXERCISES:
        m = re.search(rf"\b(?:{rx})\b", low)
        if m and not any(m.start() >= e["pos"] and m.end() <= e["pos"] + len(e["text"]) for e in out["exercises"]): out["exercises"].append({"exercise": m.group(0), "text": m.group(0), "pos": m.start()})
    for m in re.finditer(r"\b([SABCDF])[\s-]*tier\b", text): out["tiers"].append({"letter": m.group(1).upper(), "text": m.group(0), "pos": m.start()})
    sm = re.search(r"\b(?:in|from)\s+(?:one|a|the)\s+(?:study|review|trial|paper)[,:]?\s+(.{3,60}?)\s+(?:had|showed|found|were|was|gained|built|grew|lost|made)\b", text, re.I)
    if sm and out["numbers"]: out["study"].append({"subject": sm.group(1).strip(), "text": sm.group(0), "pos": sm.start()})
    return out

def unit_marker(text: str) -> Optional[dict]:
    """A numbered unit start in the text ("Move one is the pinch hold." -> label MOVE 1, title PINCH HOLD), or an ordinal / "Here is the catch" heading. None when the text has no marker."""
    m = UNIT_RX.search(text)
    if m and m.start() <= 12:
        n = _num(m.group(2)); label = f"{m.group(1).upper()} {n if n is not None else m.group(2).upper()}"
        t = re.search(r"(?:\b(?:is|are)\b|:)\s+(?:the |a |an )?(.{2,40}?)(?:[.,;:]|$)", text[m.end():], re.I)
        title = " ".join(t.group(1).upper().split()[:4]) if t else ""
        return {"label": label, "title": title, "kind": "numbered"}
    h = HEADING_RX.match(text)
    if h: return {"label": f"THE {h.group(1).upper()}", "title": "", "kind": "heading"}
    o = ORDINAL_RX.match(text)
    if o: return {"label": o.group(1).upper(), "title": "", "kind": "ordinal"}
    return None

def classify(text: str, t0: float = 0.0) -> Tuple[str, float, List[str]]:
    """(role, confidence, the words that decided it). Confidence is how many independent cue words agree, capped; `statement` is the honest default, never a guess."""
    for role, rx in ROLE_RULES:
        hits = [m.group(0) for m in rx.finditer(text)]
        if hits: return role, min(0.95, 0.6 + 0.15 * len(hits)), hits
    toks = _tokens(text)
    if toks and toks[0].lower() in LX.IMPERATIVES: return "cue", 0.7, [toks[0]]
    if re.search(r"\b(?:then|and)\s+(?:" + "|".join(sorted(LX.IMPERATIVES)) + r")\b", text, re.I): return "cue", 0.55, ["imperative clause"]
    if MECH_RX.search(text): return "mechanism", 0.6, [m.group(0) for m in MECH_RX.finditer(text)]
    e = entities(text)
    if e["numbers"]: return "number", 0.55, [n["text"] for n in e["numbers"]]
    if re.search(r"\b(is|are|can|will|do not|does not|need)\b", text, re.I): return "claim", 0.4, []
    return "statement", 0.3, []

def hook_type(text: str) -> Optional[Tuple[str, str]]:
    for kind, rx in HOOK_RULES:
        m = rx.search(text)
        if m: return kind, m.group(0)
    return None

def analyze(items: List[dict], title: str = "") -> dict:
    """Narrative elements over a list of beat-like dicts [{id, text, t0, t1, role, ...}] in time order. Returns {hook, roadmap, units, benchmark, cta, format}. Each element appears only when found."""
    nar: dict = {"hook": None, "roadmap": None, "units": [], "benchmark": None, "cta": None, "format": "auto"}
    for it in items[:4]:      # the hook lives in the first beats, and only counts when a hook pattern is actually there
        h = hook_type(it["text"])
        if h and it["t0"] < 25: nar["hook"] = {"type": h[0], "beat": it["id"], "words": h[1]}; break
    for it in items:
        if it["t0"] > 60: break
        m = ROADMAP_RX.search(it["text"])
        if m and not UNIT_RX.search(it["text"]): nar["roadmap"] = {"beat": it["id"], "count": LX.num(m.group(1)), "noun": m.group(2).upper(), "text": m.group(0)}; break
    cur = None
    for it in items:
        mk = unit_marker(it["text"])
        if mk: cur = {"id": f"u{len(nar['units']) + 1}", "t0": it["t0"], "t1": it["t1"], "beats": [], **mk}; nar["units"].append(cur)
        if it.get("role") in ("routine", "cta", "benchmark") and cur is not None and not mk: cur = None      # a plan, a call to action or a scorecard closes the unit; it is not part of it
        if cur is not None: cur["beats"].append(it["id"]); cur["t1"] = it["t1"]; it["unit"] = cur["id"]
        else: it["unit"] = None
    promise = next((it for it in items if TEST_PROMISE_RX.search(it["text"])), None)
    if promise:
        payoff = next((it for it in items if it["t0"] > promise["t1"] + 20 and (entities(it["text"])["tiers"] or re.search(r"\bunder \d+|\bwhat it says\b|\bscore\b", it["text"], re.I))), None)
        nar["benchmark"] = {"test_beat": promise["id"], "payoff_beat": payoff["id"] if payoff else None}      # no payoff beat: no scorecard is invented
    cta = next((it for it in reversed(items) if it.get("role") == "cta"), None)
    if cta: nar["cta"] = {"beat": cta["id"]}
    total = items[-1]["t1"] if items else 0
    tiers = sum(1 for it in items if it.get("role") == "benchmark" and entities(it["text"])["tiers"])
    nar["format"] = "tierlist" if tiers >= 1 and any("rank" in it["text"].lower() for it in items) else ("roadmap" if re.search(r"\broadmap|\b\d+[- ]day\b|\bphase\b", " ".join(i["text"] for i in items[:6]), re.I) else ("short" if total < 300 else "guide"))
    return nar


# ---------------------------------------------------------------- discourse relations and unknown terms
REL_RULES: List[Tuple[str, "re.Pattern"]] = [      # what the clause DOES in the argument (not what it names); several can hold at once
    ("contrast", re.compile(r"^\s*(?:but|however|yet|although|instead)\b|,\s*but\b", re.I)),
    ("cause", re.compile(r"\b(?:because|since|which is why|that is why|so that(?!\s+(?:is|was|are|were|will|would))|as a result)\b", re.I)),
    ("comparison", re.compile(r"\b(?:while|whereas|compared (?:to|with)|versus|rather than|compare)\b", re.I)),
    ("negation", re.compile(r"\b(?:almost no|hardly any|barely any|no|not|never|without|cannot|can'?t|does not|do not|will not)\s+\w+", re.I)),
    ("limitation", re.compile(r"\b(?:the limit|limitation|the catch|downside|ceiling|is fixed|are fixed|does not make|cannot change)\b", re.I)),
    ("warning", re.compile(r"\b(?:stop|avoid|hurts?|pain|injur\w*|unless|if (?:it|you) (?:hurts?|feel))\b", re.I)),
    ("disclosure", re.compile(r"\b(?:synthetic|made[- ]up|fictional|invented|for testing|only to test)\b", re.I)),
    ("criteria", re.compile(r"\b(?:judge|rate|score|measure|compare|rank)\w*\s+(?:each|every|them|it)\b.{0,30}\b(?:on|by)\b|\bon (?:two|three|four|five) (?:things|criteria|factors)\b", re.I)),
    ("sequence", re.compile(r"^\s*(?:first|second|third|next|then|finally|step \w+|week \w+|day \w+)\b", re.I)),
]
STOP = set("""a an the and or but so if of to in on at by for with from as is are was were be been being am do does did done not no nor it its this that these those they them their there here you your yours we our us i me my he she his her
will would can could should may might must shall have has had having than then too very just also only more most less least much many some any each every all both either neither one ones such own same other another into onto over under up down out off about above below
between through during before after while when where why how what which who whom whose because since until unless though although yet get gets got make makes made let us lets keep keeps need needs want wants take takes put puts go goes going come comes use uses used using say says said
like around again once away back still even ever often always never now soon almost really something anything nothing everything someone anyone everyone happens happen happened later earlier thing stuff way idea""".split())

def relations(text: str) -> List[str]:
    return [name for name, rx in REL_RULES if rx.search(text)]

def key_phrase(text: str, n: int = 3) -> Tuple[str, int]:
    """The most specific noun-like run in the words (<= n words) and its position, for a subject the lexicon does not know. Runs are cut at function words; runs that follow a determiner (the / your / an)
    are the likely noun phrases; the longest by letters wins. Returns ("", -1) when the text has no content words."""
    toks = re.findall(r"[A-Za-z][A-Za-z'-]*", text); runs: List[Tuple[int, List[str], bool]] = []; cur: List[str] = []; start = 0; after_det = False; det_flag = False
    for i, t in enumerate(toks + ["."]):
        low = t.lower()
        if low in STOP or t == ".":
            if cur: runs.append((start, cur, det_flag)); cur = []
            det_flag = low in ("the", "your", "an", "a", "this", "these", "our", "my")
        elif not cur: start = i; cur = [t]
        else: cur.append(t)
    best = None
    for pos, run, det in runs:
        run = run[:n]; score = sum(len(w) for w in run) + (4 if det else 0) + (2 if len(run) > 1 else 0)
        if best is None or score > best[0]: best = (score, pos, run)
    return (" ".join(best[2]).upper(), best[1]) if best else ("", -1)
