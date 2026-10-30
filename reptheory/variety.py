"""Variety director for long Rep Theory videos (30 minutes and more): decides, scene by scene, which LOOK the narration gets so the viewer is not shown the same kind of picture for minutes on end.
Looks: stock (the planner's own: library figure, callout), 3d (a muscle clip of the 3D body, clip3d.py), flow (a manga picture generated from the beat, beat_art.py) and four code-drawn cards that need no
assets (cards.py): stat (a stated number in a ring), steps (a spoken sequence), versus (a stated comparison), takeaway (the key line, word by word).
Rules, all measured by `metrics`: a look is only offered where the beat's own words support it (a number, a muscle, a comparison, a sequence, a key line); the same look never runs more than twice in a row;
a look not used in the last scenes is preferred; 3D clips keep a minimum spacing and Flow pictures a budget (a 30-minute video must not cost 200 generations); a 3D scene is never followed by another.
Grounded scenes (tier boards, equations, held props, anatomy) are never replaced. Chapter banners mark each new part of a long video."""
from __future__ import annotations
import re
from typing import Dict, List, Optional

from . import clip3d as C3, lexicon as LX, narrative as N, planner as P
from .beat_art import SYNTH_RX

FULL_CARDS = ("steps", "versus", "takeaway", "timeline", "mistake", "slider", "calendar", "result", "warning", "engage", "myth", "question", "checklist")      # cards that fill the frame; the narration's next phrase follows in a caption strip
SIDE_CARDS = ("stat", "dial", "study", "graph", "bars")      # cards on the left, the beat's words as callouts on the right
CARD_LOOKS = SIDE_CARDS + FULL_CARDS
UPGRADABLE = {"callout", "trainee"}      # text-only or generic-figure scenes: the ones that look the same from minute to minute
TIME_UNITS = {"S", "SEC", "MIN", "H", "HR"}; COUNT_UNITS = {"SET", "REP", "WEEK", "DAY", "TIME", "ROUND", "X"}
VS_RX = (re.compile(r"(.{3,48}?)\s+(?:versus|vs\.?|rather than|instead of|compared (?:to|with))\s+(.{3,48})", re.I), re.compile(r"\bnot\s+(.{3,32}?),?\s+but\s+(.{3,32})", re.I),
         re.compile(r"(.{3,48}?)\s*,?\s+whereas\s+(.{3,48})", re.I), re.compile(r"(?:^|(?<=[,.;:!?])\s*)([A-Za-z][^,.;:!?]{2,50}?)\s+(?:beats|(?:will |can )?(?:outperforms?|outweighs?|outlasts?|trumps?)|matters more than)\s+(?:a |an |the )?([^,.;:!?]{3,60})", re.I),
         re.compile(r"([^,.;!?]{6,40}),\s+not\s+([^,.;!?]{3,32})", re.I), re.compile(r"(.{3,40}?)\s+(?:is|are)\s+(?:much |far |a lot )?(?:harder|easier|better|worse|stronger|weaker|safer|slower|faster)\s+than\s+(.{3,40})", re.I))
VS_BEATS, VS_NOT = VS_RX[3], VS_RX[4]
VS_GOALS = re.compile(r"\b(?:want to|if you want to|trying to)\s+([^?.,]{3,30})[?,]\s*[^.!?]{3,60}[.!?]\s*(?:and\s+)?(?:want to|if you want to|trying to)\s+([^?.,]{3,30})[?,]", re.I)      # "Want to lose fat? ... Want to build? ...": two goals, two answers
VS_RX = (VS_GOALS,) + VS_RX
STEP_RX = re.compile(r"\b(?:first|second|third|then|next|after that|finally|and then)\b,?", re.I)

def _widx(text: str, pos: int) -> int: return len(text[:pos].split())
def _at(sc: dict, text: str, pos: int) -> float:
    ws = sc.get("words") or []; i = _widx(text, pos)
    return float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"]) + 0.3

def _phrase(s: str) -> str:
    k, _ = N.key_phrase(s, 3); return k.upper()

def _stat(sc: dict, text: str) -> Optional[dict]:
    nums = N.entities(text)["numbers"]
    if not nums: return None
    n = nums[0]; u = n["unit"].upper(); v = float(n["value"]) if not isinstance(n["value"], str) else float(re.sub(r"[^\d.]", "", n["value"]) or 0)
    if v <= 0: return None
    mode = "fill" if u == "%" and v <= 100 else "dots" if (u.rstrip("S") in COUNT_UNITS and float(v).is_integer() and 1 <= v <= 12) else "full"
    return {"value": v, "unit": n["unit"].upper() if u != "%" else "%", "mode": mode, "at": _at(sc, text, n["pos"])}

def _versus(sc: dict, text: str) -> Optional[dict]:
    for rx in VS_RX:
        m = rx.search(text); k = 4 if rx is VS_BEATS else 5 if rx is VS_NOT else -1
        if m and k == 4:      # "consistency beats intensity": the phrase each side starts with; "No workout beats a bad diet" says the opposite, "your heart beats faster" is not a comparison
            b0 = m.group(2).split()[0].lower()
            if re.match(r"\s*(?:no|nothing|never|not)\b", m.group(1), re.I) or b0.endswith(("er", "ly")) or b0 in ("per", "at", "every", "in", "up", "down", "more", "less", "faster"): continue
            a, b = _words_after(re.split(r"\b(?:is|are|that)\b", m.group(1))[-1], 0, 3), _words_after(m.group(2), 0, 3)      # "rule five is that consistency" -> CONSISTENCY
            if a and b and a != b: return {"a": {"text": a, "at": _at(sc, text, m.start(1))}, "b": {"text": b, "at": _at(sc, text, m.start(2))}}
            continue
        if m and k == 5:      # "X, not Y": the two sides are parallel ("INTO YOUR MUSCLES" / "UNDER YOUR SKIN"), so A is as long as B
            b = _words_after(m.group(2), 0, 4, lead=False); bw = b.split(); aw = re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", m.group(1))[-max(1, len(bw)):]
            a = " ".join(aw).upper()
            if a and b and a != b and len(bw) <= 4 and aw[0].lower() not in ("and", "but", "or"): return {"a": {"text": a, "at": _at(sc, text, m.start(1) + m.group(1).rfind(aw[0]))}, "b": {"text": b, "at": _at(sc, text, m.start(2))}}
            continue
        if m and rx is VS_GOALS:
            a, b = _words_after(m.group(1), 0, 3, lead=False), _words_after(m.group(2), 0, 3, lead=False)
            if a and b and a != b: return {"a": {"text": a, "at": _at(sc, text, m.start(1))}, "b": {"text": b, "at": _at(sc, text, m.start(2))}}
            continue
        if m:
            a, b = _phrase(m.group(1)), _phrase(m.group(2))
            if a and b and a != b: return {"a": {"text": a, "at": _at(sc, text, m.start(1))}, "b": {"text": b, "at": _at(sc, text, m.start(2))}}
    return None

def _steps(sc: dict, text: str) -> Optional[List[dict]]:
    marks = [m for m in STEP_RX.finditer(text)]
    if len(marks) < 2: return None
    cuts = [m.end() for m in marks] + [len(text)]; items = []
    for i, m in enumerate(marks):
        piece = text[cuts[i]:marks[i + 1].start() if i + 1 < len(marks) else len(text)]; ws = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", piece)]
        while ws and ws[-1].lower() in N.STOP: ws.pop()
        if len(ws) >= 1: items.append({"text": " ".join(ws[:5]).upper(), "at": _at(sc, text, cuts[i])})
    return items[:4] if len(items) >= 2 else None

# ---------------------------------------------------------------- Step 4 cards: each needs its sentence shape, never a topic word
TIME_MARK_RX = re.compile(rf"\b{LX.NUM}\s*(seconds?|secs?|minutes?|mins?)?\s*(?:in\b|,)", re.I)
MISTAKE_RX = re.compile(r"\bmistakes?\b(?:\s+\w+){0,4}?\s+(?:is|are|was)\s+(.+?)(?=[.!?;]|$)", re.I)
FIX_RX = re.compile(r"(?:^|[.!?]\s+)(?:instead,?\s+)?((?:keep|stay|squeeze|pull|push|breathe|go|use|do|try|leave|hold|start|count|lock|press|stand|sit)\b[^.!?]*)", re.I)
EASY_RX = re.compile(r"\btoo (?:hard|difficult|heavy)\?\s*([^.!?]+)", re.I); HARD_RX = re.compile(r"\btoo (?:easy|light)\?\s*([^.!?]+)", re.I)
DIAL_RX = re.compile(rf"\b{LX.NUM}\s+out of\s+(?:10|ten)\b", re.I); EFFORT_PCT_RX = re.compile(rf"\b{LX.NUM}\s*(?:%|percent)\s+(?:of your )?(?:effort|intensity|max\w*)", re.I)
STUDY_RX = re.compile(rf"\b(review|study|trial|analysis|meta-analysis|survey)\s+of\s+{LX.NUM}\s+(studies|trials|papers|people|adults|men|women|participants|athletes|runners|lifters)\b", re.I)

def _words_after(text: str, pos: int, n: int = 4, lead: bool = True) -> str:
    """Up to n words from pos to the end of its clause, without leading / trailing function words."""
    piece = re.split(r"[,.;:!?]", text[pos:].lstrip(" ,;:"), maxsplit=1)[0]; ws = re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", piece)
    while lead and ws and ws[0].lower() in N.STOP | {"in"}: ws.pop(0)      # an instruction keeps its verb (lead=False)
    if len(ws) <= n + 2: return " ".join(ws).upper()      # a short whole clause is shown whole ("BRAIN STARTS ASKING YOU TO QUIT")
    ws = ws[:n]
    while ws and ws[-1].lower() in N.DANGLING: ws.pop()
    return " ".join(ws).upper()

def _num_of(s: str) -> float:
    try: return float(LX.num(s))
    except Exception: return 0.0

def _timeline(sc: dict, text: str) -> Optional[dict]:
    marks = []
    for m in TIME_MARK_RX.finditer(text):
        v = _num_of(m.group(1)); unit = (m.group(2) or "").lower()
        if v <= 0 or (not marks and not (unit and m.group(0).rstrip().lower().endswith("in"))): continue      # it starts with "N seconds in"; later marks may drop the unit ("20, ...")
        v = v * 60 if unit.startswith("min") else v; feel = _words_after(text, m.end())
        if feel and (not marks or v > marks[-1]["value"]): marks.append({"value": v, "mark": f"{v:g}S" if v < 60 else f"{v / 60:g} MIN", "text": feel, "at": _at(sc, text, m.start())})
    return {"items": marks[:4]} if len(marks) >= 2 else None

def _mistake(sc: dict, text: str) -> Optional[dict]:
    m = MISTAKE_RX.search(text)
    if not m: return None
    wrong = _words_after(m.group(1), 0, 7)
    if len(wrong.split()) < 2: return None
    out = {"wrong": {"text": wrong, "at": _at(sc, text, m.start(1))}}
    f = FIX_RX.search(text, m.end())
    if f: right = _words_after(f.group(1), 0, 5, lead=False); out["right"] = {"text": right, "at": _at(sc, text, f.start(1))} if len(right.split()) >= 2 else None
    return out

def _slider(sc: dict, text: str) -> Optional[dict]:
    e, h = EASY_RX.search(text), HARD_RX.search(text)
    if not (e or h): return None
    out = {"easier": {"text": _words_after(e.group(1), 0, 4, lead=False), "at": _at(sc, text, e.start(1))} if e else None, "harder": {"text": _words_after(h.group(1), 0, 4, lead=False), "at": _at(sc, text, h.start(1))} if h else None}
    return out if any(v and v["text"] for v in out.values()) else None

def _dial(sc: dict, text: str) -> Optional[dict]:
    m = DIAL_RX.search(text)
    if m: v = _num_of(m.group(1)); return {"value": v, "max": 10, "label": "EFFORT" if re.search(r"\beffort|intensity|hard\b", text, re.I) else "OUT OF 10", "at": _at(sc, text, m.start())} if 0 < v <= 10 else None
    m = EFFORT_PCT_RX.search(text)
    if m: v = _num_of(m.group(1)); return {"value": v / 10, "max": 10, "label": f"{v:g}% EFFORT", "at": _at(sc, text, m.start())} if 0 < v <= 100 else None
    return None

YEAR_RX = (re.compile(r"\b(?:a|an|one|the)\s+((?:19[5-9]|20[0-3])\d)\s+(study|review|trial|paper|analysis|survey)\b", re.I), re.compile(r"\b(?:in|back in|since)\s+((?:19[5-9]|20[0-3])\d)\b,?\s+(?:a\s+)?(?:researchers?|scientists?|a study|a review|a trial|studies)\b", re.I),
           re.compile(r"\bback in the\s+((?:19)?[5-9]0)'?s\b", re.I))

def _study(sc: dict, text: str) -> Optional[dict]:
    m = STUDY_RX.search(text)
    if not m:      # no count, but a year: the research card rolls back to it ("a 2019 study", "back in the 70s")
        for rx in YEAR_RX:
            y = rx.search(text)
            if y: v = int(y.group(1)); v = 1900 + v if v < 100 else v; return {"kind": (y.group(2) if y.lastindex and y.lastindex >= 2 else "RESEARCH").upper(), "value": float(v), "noun": "", "year": True, "at": _at(sc, text, y.start())}
        return None
    v = _num_of(m.group(2)); return {"kind": m.group(1).upper(), "value": v, "noun": m.group(3).upper(), "at": _at(sc, text, m.start())} if v >= 2 else None

TREND = {"up": r"rises?|rising|rose|climbs?|climbing|goes up|go up|increases?|increasing|jumps?|doubles?|spikes?|peaks?|soars?|adds? up|builds? up|stacks? up|improves?|improving|rebuilds?|rebuilding|bounces? back|grows? back|recovers? stronger", "down": r"drops?|dropping|dropped|falls?|falling|fell|goes down|go down|decreases?|declines?|crashes|dips?|shrinks?|breaks? down|breaking down",
         "flat": r"levels? off|plateaus?|flattens?|stays? flat|stalls?"}
TREND_RX = re.compile(r"\b(?:" + "|".join(f"(?P<{k}>{v})" for k, v in TREND.items()) + r")\b", re.I)
OVER_TIME_RX = re.compile(r"\b(?:over|after|within|for|by|each|every|per|in|across)\s+(?:the\s+|a\s+|an\s+|more than\s+(?:a\s+)?|the next\s+|\w+\s+)?(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?|night|time|sessions?|workouts?)\b", re.I)
FROM_TO_RX = re.compile(rf"\bfrom\s+(?:about\s+)?{LX.NUM}\s*(%|\w+)?\s+to\s+{LX.NUM}\s*(%|\w+)?", re.I)
PEOPLE = r"people|adults|men|women|lifters|runners|athletes|beginners|participants|of us|patients|kids|children|players"
DOTS_RX = (re.compile(rf"\b{LX.NUM}\s+(?:in|out of)\s+(?:every\s+)?{LX.NUM}\s+({PEOPLE})\b", re.I), re.compile(rf"\b{LX.NUM}\s*(?:%|percent)\s+of\s+(?:all\s+)?({PEOPLE})\b", re.I))
DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAYS_RX = re.compile(r"\b(" + "|".join(DAY_NAMES) + r")s?\b", re.I); PER_WEEK_RX = re.compile(rf"\b{LX.NUM}\s+(days?|times|sessions?|workouts?|runs?)\s+(?:a|per|each|every)\s+week\b", re.I)
SPREAD = {2: (0, 3), 3: (0, 2, 4), 4: (0, 1, 3, 4), 5: (0, 1, 2, 3, 4), 6: (0, 1, 2, 3, 4, 5), 7: (0, 1, 2, 3, 4, 5, 6)}      # n sessions in a week, rest days between them
TIER_RX = re.compile(rf"\b(?:(?P<lo>under|less than|below|fewer than)\s+{LX.NUM}|{LX.NUM}\s*(?:to|-)\s*{LX.NUM}|(?P<hi>over|more than|above|beyond)\s+{LX.NUM}|{LX.NUM}\s*(?:or more|\+|and up|and over))\s*(seconds?|secs?|minutes?|mins?|reps?|kg|%|percent)?\s*,", re.I)
HURT_RX = re.compile(r"\b(?:hurts?|pain\w*|sharp|dizzy|dizziness|injur\w*|numb\w*|tingl\w*|doctor|physio\w*|swell\w*|swollen|unsafe|safely|faint)\b", re.I)
RULE_RX = re.compile(r"(?:^|[,;]\s*)((?:stop|never|don'?t|do not|avoid|rest|take|see|check|talk to|ask|ease off|back off|skip)\b[^,.;!?]*)", re.I)
CTA_RX = (("comment", re.compile(r"\b(comment|let me know|tell me)\b", re.I)), ("like", re.compile(r"\b(?:tap|hit|smash|press|leave|give (?:it|this|the video))\s+(?:the\s+|a\s+)?like\b", re.I)), ("subscribe", re.compile(r"\bsubscribe\b", re.I)))

def _graph(sc: dict, text: str) -> Optional[dict]:
    """A change over time drawn as a line: each rise / drop / levelling-off the sentence names bends the curve on its word ("your strength drops for a week, then climbs past where it was")."""
    segs = [{"dir": next(k for k in TREND if m.group(k)), "at": _at(sc, text, m.start())} for m in TREND_RX.finditer(text)]
    if not segs or not (len(segs) >= 2 or OVER_TIME_RX.search(text) or FROM_TO_RX.search(text)): return None
    pre = text[:TREND_RX.search(text).start()]; subj = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", re.split(r"[,.;:!?]", pre)[-1]) if w.lower() not in N.STOP and w.lower() not in N.DANGLING][-2:]
    if not subj: return None      # a rise of nothing named ("it goes up") has no axis to label
    ft = FROM_TO_RX.search(text); out = {"label": " ".join(subj).upper(), "segs": segs[:4]}
    if ft: out["from"], out["to"] = [f"{_num_of(ft.group(i)):g}{'%' if (ft.group(i + 1) or '').lower() in ('%', 'percent') else ''}" for i in (1, 3)]
    return out

def _noun_after(text: str, pos: int) -> str:
    """The content words right after a number, up to the first function word ("20% MORE STRENGTH", "8 HOURS" -> ""): a bar's label, never a cut clause."""
    out = []
    for w in re.findall(r"[A-Za-z][A-Za-z'-]*|\S", re.split(r"[,.;:!?]", text[pos:], maxsplit=1)[0])[:3]:
        if not w[0].isalpha() or w.lower() in N.STOP or w.lower() in N.DANGLING: break
        out.append(w)
    return " ".join(out).upper()

def _bars(sc: dict, text: str) -> Optional[dict]:
    """Stated shares as a grid of dots ("1 in 3 adults", "40% of lifters"), or two or more numbers of one unit as bars, each labelled with its own words."""
    for rx in DOTS_RX:
        m = rx.search(text)
        if m:
            g = m.groups(); lit = _num_of(g[0]); of = _num_of(g[1]) if len(g) == 3 else 100.0
            if 0 < lit < of <= 100: return {"mode": "dots", "lit": lit, "of": of, "label": f"{lit:g} IN {of:g}" if of != 100 else f"{lit:g}%", "noun": g[-1].upper(), "at": _at(sc, text, m.start())}
    nums = [n for n in N.entities(text)["numbers"] if n["unit"]]
    if len(nums) < 2 or len({n["unit"].lower() for n in nums[:3]}) != 1: return None
    items = []
    for n in nums[:3]:
        v = _num_of(str(n["value"]))
        if v <= 0: return None
        items.append({"value": v, "text": f"{v:g}{'%' if n['unit'] == '%' else ' ' + n['unit'].upper()}", "label": _noun_after(text, n["pos"] + len(n["text"])), "at": _at(sc, text, n["pos"])})
    return {"mode": "bars", "items": items} if len({i["value"] for i in items}) >= 2 else None

def _calendar(sc: dict, text: str) -> Optional[dict]:
    """A week that fills in: the days the sentence names (three or more), or "N days a week" spread with rest days between."""
    named = []
    for m in DAYS_RX.finditer(text):
        d = DAY_NAMES.index(m.group(1).lower())
        if d not in [x["day"] for x in named]: named.append({"day": d, "at": _at(sc, text, m.start())})
    if len(named) >= 3: return {"days": named, "total": f"{len(named)} DAYS A WEEK"}
    m = PER_WEEK_RX.search(text)
    if not m: return None
    n = int(_num_of(m.group(1)))
    if n not in SPREAD: return None
    at = _at(sc, text, m.start()); return {"days": [{"day": d, "at": at + 0.22 * i} for i, d in enumerate(SPREAD[n])], "total": f"{n} {m.group(2).upper().rstrip('S')}S A WEEK"}

def _result(sc: dict, text: str) -> Optional[dict]:
    """A result board: the bands the sentence states ("under 20 seconds, ... 20 to 40, ... over 40, ..."), each revealed with what it means as it is said."""
    tiers = []
    for m in TIER_RX.finditer(text):
        g = [x for x in m.groups() if x]; nums = [f"{_num_of(x):g}" for x in g if re.match(LX.NUM + "$", x, re.I)]; unit = (m.groups()[-1] or "").lower()
        u = "S" if unit.startswith("s") else " MIN" if unit.startswith("m") else "%" if unit in ("%", "percent") else ""
        mark = (f"UNDER {nums[0]}{u}" if m.group("lo") else f"{nums[0]}{u}+" if m.group("hi") or len(nums) == 1 else f"{nums[0]}-{nums[1]}{u}")
        meaning = _words_after(text, m.end(), 4)
        if meaning: tiers.append({"mark": mark, "text": meaning, "at": _at(sc, text, m.start())})
    return {"tiers": tiers[:4]} if len(tiers) >= 2 else None

def _warning(sc: dict, text: str) -> Optional[dict]:
    """Safety rules stacked as warning cards: each sentence that names a sign of harm (pain, dizziness, an injury) and says what to do about it."""
    rules, pos = [], 0
    for s in re.split(r"(?<=[.!?])\s+", text):
        if HURT_RX.search(s):
            m = RULE_RX.search(s)
            if m:
                r = _words_after(m.group(1), 0, 6, lead=False)
                if len(r.split()) >= 2: rules.append({"text": r, "at": _at(sc, text, pos + m.start(1))})
        pos += len(s) + 1
    return {"rules": rules[:3]} if rules else None

def _engage(sc: dict, text: str) -> Optional[dict]:
    """The call to action as the screen it asks for: the comment being typed in, the like button pressed, the subscribe button and its bell."""
    for kind, rx in CTA_RX:
        m = rx.search(text)
        if m: return {"kind": kind, "text": _words_after(text, m.start(), 5, lead=False) if kind == "comment" else "", "at": _at(sc, text, m.start())}
    return None

MYTH_RX = re.compile(r"\bmyth(?:\s+(?:number\s+)?\w+)?\s*:\s*([^.!?]+)[.!?]?\s*([^.!?]*)", re.I)
QUESTION_RX = re.compile(r"(?:^|(?<=[.!?])\s+)((?:so\s+)?(?:what|how|why|which|when|is|are|do|does|can|should|will)\b[^.!?]{6,70}\?)", re.I)
LIST_RX = re.compile(r"\b((?:[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,3},\s+){1,4}(?:[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,3},?\s+)?(?:and|or)\s+[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,3})\b", re.I)

def _myth(sc: dict, text: str) -> Optional[dict]:
    """A myth the narration names ("Myth two: it damages your kidneys.") in a grey panel that is struck out, and the fact that answers it in a green one."""
    m = MYTH_RX.search(text)
    if not m: return None
    myth = _words_after(m.group(1), 0, 7, lead=False)
    if len(myth.split()) < 2: return None
    out = {"wrong": {"text": myth, "at": _at(sc, text, m.start(1))}, "labels": ("MYTH", "FACT")}
    fact = _words_after(m.group(2), 0, 6, lead=False) if m.group(2) else ""
    ok = len(fact.split()) >= 2 and (fact.split()[-1].lower() not in N.DANGLING or fact.split()[-1].lower() in ("not", "no", "never"))      # "IT IS NOT" answers the myth
    out["right"] = {"text": fact, "at": _at(sc, text, m.start(2))} if ok else None
    return out

def _question(sc: dict, text: str) -> Optional[dict]:
    """A question asked for the viewer ("What about ice baths?", "So how much should you drink?") in a chat bubble that types in, its key words marked."""
    m = QUESTION_RX.search(text)
    if not m or EASY_RX.search(m.group(1)) or HARD_RX.search(m.group(1)): return None
    q = re.sub(r"^so\s+", "", m.group(1).strip(), flags=re.I); ws = q.split()
    if not 3 <= len(ws) <= 12: return None
    key = N.key_phrase(q, 3)[0].upper(); return {"text": q.upper(), "key": key, "at": _at(sc, text, m.start(1))}

LEAD_STOP = N.STOP - set(LX.NUMBER_WORDS)      # "one more rep" is an item; "while you eat" is not

def _checklist(sc: dict, text: str) -> Optional[dict]:
    """A spoken list of three or more short items ("eat, sleep and recover") ticked off one by one as each is said."""
    m = LIST_RX.search(text)
    if not m: return None
    raw = [p.strip() for p in re.split(r",\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+", m.group(1)) if p.strip()]; parts = [raw[-1]]
    for p in reversed(raw[:-1]):      # from the last item back: an item longer than the list's own items is a clause that runs into it ("while you eat, sleep and recover" -> EAT)
        w = p.split(); single = all(len(x.split()) == 1 for x in parts)
        if len(w) <= 4 and w[0].lower() not in LEAD_STOP and not (single and len(w) > 1): parts.insert(0, p); continue
        tail = w[-len(parts[0].split()):]
        if tail[0].lower() not in LEAD_STOP: parts.insert(0, " ".join(tail))
        break
    if not 3 <= len(parts) <= 5 or parts[-1].split()[0].lower() in LEAD_STOP: return None
    m = re.search(re.escape(parts[0]), text) or m
    items, pos = [], m.start()
    for p in parts:
        i = text.find(p, pos); pos = i + len(p); items.append({"text": p.upper(), "at": _at(sc, text, i)})
    return {"items": items, "ticks": True}

def _takeaway(sc: dict, text: str, last: bool, role: str) -> Optional[dict]:
    ws = sc.get("words") or []; dur = sc["end"] - sc["start"]
    if not (4 <= len(ws) <= 20 and 2.5 <= dur <= 10.0): return None
    if not (last or role in ("hook", "claim", "cta", "mistake")): return None
    return {"words": [{"w": re.sub(r"[^\w'-]", "", w["w"]).upper() or w["w"].upper(), "t0": float(w["t0"])} for w in ws]}

POSE_BASE = 0.8      # a pose shows the sentence's action: as strong as a card, rotated with them by the director
LATE_CARD_S = 3.0
OPEN_AT_START = {"engage", "question"}      # the comment box / chat bubble is on screen (typing dots) from the scene's first frame

def _first_at(p) -> float:
    """The earliest word time anywhere in a card payload."""
    if isinstance(p, dict): xs = [float(p["at"])] if "at" in p else []; xs += [_first_at(v) for v in p.values() if isinstance(v, (dict, list))]
    elif isinstance(p, list): xs = [_first_at(v) for v in p]
    else: return 1e9
    xs = [x for x in xs if x < 1e9] + ([float(p[0]["t0"])] if isinstance(p, list) and p and isinstance(p[0], dict) and "t0" in p[0] else [])
    return min(xs) if xs else 1e9

def evidence(sc: dict, last: bool = False, role: str = "") -> Dict[str, tuple]:
    """look -> (support 0..1, payload) for what this scene's own words can honestly show."""
    text = sc.get("text", ""); ev: Dict[str, tuple] = {}
    if not text.strip() or SYNTH_RX.search(text): return ev
    g, by_ex = C3.groups_for(text)
    if g: ev["3d"] = (0.7 if by_ex else 0.9, None)
    for look, fn, base in (("timeline", lambda: _timeline(sc, text), 0.95), ("mistake", lambda: _mistake(sc, text), 0.9), ("slider", lambda: _slider(sc, text), 0.9),
                           ("dial", lambda: _dial(sc, text), 0.9), ("study", lambda: _study(sc, text), 0.88), ("result", lambda: _result(sc, text), 0.95), ("calendar", lambda: _calendar(sc, text), 0.9),
                           ("warning", lambda: _warning(sc, text), 0.85), ("bars", lambda: _bars(sc, text), 0.86), ("graph", lambda: _graph(sc, text), 0.82), ("engage", lambda: _engage(sc, text), 0.8), ("myth", lambda: _myth(sc, text), 0.92), ("question", lambda: _question(sc, text), 0.78), ("checklist", lambda: _checklist(sc, text), 0.8), ("stat", lambda: _stat(sc, text), 0.85), ("versus", lambda: _versus(sc, text), 0.8), ("steps", lambda: _steps(sc, text), 0.8), ("takeaway", lambda: _takeaway(sc, text, last, role), 0.9 if last else 0.6)):
        got = fn()
        if got: ev[look] = (base - (0.6 if look not in OPEN_AT_START and _first_at(got) - float(sc["start"]) > LATE_CARD_S else 0.0), got)      # a card whose first element comes late would sit empty on screen
    if sc.get("pose_pick"): ev["pose"] = (POSE_BASE, sc["pose_pick"])      # the character doing what the sentence names (poses.py)
    if "engage" in ev: ev.pop("takeaway", None)      # a call to action is shown as the screen it asks for, not as a key line
    if N.key_phrase(text, 3)[0]: ev["flow"] = (0.5, None)
    if "takeaway" not in ev and not any(pg.get("headline") or pg.get("value") or pg.get("chips") for pg in sc.get("pages", [])):      # a scene with nothing written on it would be a bare figure: its own words, lit as they are spoken, are the fallback
        ws = sc.get("words") or []
        if 4 <= len(ws) <= 22 and sc["end"] - sc["start"] >= 3.0: ev["takeaway"] = (0.55, {"words": [{"w": re.sub(r"[^\w'-]", "", w["w"]).upper() or w["w"].upper(), "t0": float(w["t0"])} for w in ws]})
    return ev

SPLIT_MIN_S, SPLIT_CARD = 2.5, 0.85      # each half of a split scene lasts at least this long; only a strong card shape is worth a cut
SPLIT_LOOKS = set(CARD_LOOKS) - {"takeaway", "stat"}

def _t(x: dict) -> float:
    for k in ("at", "t0", "start"):
        if k in x: return float(x[k])
    return -1.0

def _cut(sc: dict, t: float) -> tuple:
    """Two scenes from one text scene at time t (a sentence's first word): every timed item goes to the half it is said in."""
    a, b = dict(sc), dict(sc); ws = sc.get("words") or []; i = next(k for k, w in enumerate(ws) if float(w["t0"]) >= t - 1e-6)
    a["end"], b["start"] = t, t; a["words"], b["words"] = ws[:i], ws[i:]; tx = sc.get("text", "").split(); a["text"], b["text"] = (" ".join(tx[:i]), " ".join(tx[i:])) if len(tx) == len(ws) else (" ".join(w["w"] + w.get("p", "") for w in ws[:i]), " ".join(w["w"] + w.get("p", "") for w in ws[i:]))      # the script's own text, punctuation kept
    for k, v in sc.items():
        if isinstance(v, list) and k != "words" and v and isinstance(v[0], dict) and _t(v[0]) >= 0: a[k] = [x for x in v if _t(x) < t]; b[k] = [x for x in v if _t(x) >= t]
    for k in ("tint",):
        if sc.get(k): (a if _t(sc[k]) < t else b)[k] = sc[k]; (b if _t(sc[k]) < t else a)[k] = None
    a["decisions"], b["decisions"] = list(sc["decisions"]) + ["variety: split before a sentence with its own card"], list(sc["decisions"]) + ["variety: split off to show its own card"]
    if not b["pages"]: b["pages"] = []
    return a, b

def split_for_cards(scenes: List[dict]) -> int:
    """A text scene that joins several sentences, where a later sentence has a card of its own ("The most common mistake is ...") that would otherwise show late or not at all,
    is cut at that sentence's first word, so each part gets the picture its own words support. Returns how many cuts were made."""
    n = 0; i = 0
    while i < len(scenes):
        sc = scenes[i]; ws = sc.get("words") or []
        if sc["kind"] != "callout" or sc.get("directed_look") or sc.get("art") or len(ws) < 8 or sc["end"] - sc["start"] < 2 * SPLIT_MIN_S: i += 1; continue
        cut = None
        for k in range(1, len(ws)):
            if not re.search(r"[.!?]", ws[k - 1].get("p", "")): continue
            t = float(ws[k]["t0"])
            if t - sc["start"] < SPLIT_MIN_S or sc["end"] - t < SPLIT_MIN_S: continue
            head = {"start": sc["start"], "words": ws[:k]}; tail = {"start": t, "words": ws[k:]}; tx = sc["text"].split(); text_h, text_t = (" ".join(tx[:k]), " ".join(tx[k:])) if len(tx) == len(ws) else (" ".join(w["w"] + w.get("p", "") for w in ws[:k]), " ".join(w["w"] + w.get("p", "") for w in ws[k:]))
            ev_t = {l: v for l, v in evidence(dict(sc, **tail, text=text_t, pages=[])).items() if l in SPLIT_LOOKS and v[0] >= SPLIT_CARD}
            ev_h = {l for l, v in evidence(dict(sc, **head, text=text_h, end=t)).items() if l in SPLIT_LOOKS and v[0] >= SPLIT_CARD}
            if ev_t and not (set(ev_t) <= ev_h): cut = t; break      # the later sentence brings a card the earlier part cannot show
        if cut is None: i += 1; continue
        a, b = _cut(sc, cut); scenes[i:i + 1] = [a, b]; n += 1; i += 1
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

RECENT_W = 0.25      # per recent video that had this look at this place in its opening (channel memory, Rule 3)
JITTER = 0.5      # how far a script's own seed moves a look's score: enough to change close calls, never to pick a look the words do not support

def direct(scenes: List[dict], *, total_s: Optional[float] = None, three_d: bool = True, flow: bool = True, budget: Optional[dict] = None, roles: Optional[Dict[int, str]] = None, history: Optional[List[str]] = None, recent: Optional[List[List[str]]] = None) -> dict:
    """Assigns `look` to every scene (and the payload of a card look, `want3d` + `cam3d` for a 3D clip, `chapter_card` for a new part). Returns the summary."""
    split = split_for_cards(scenes)
    total = float(total_s or (scenes[-1]["end"] if scenes else 0)); b = budget or {}; gap3 = b.get("three_d_gap_s", min(20.0, max(6.0, total / 4))); max_flow = b.get("max_flow", max(2, int(total / 30)))
    hist: List[str] = list(history or []); last3 = -1e9; flows = 0; style_i = 0; roles = roles or {}; n0 = len(hist)
    import zlib; seed = zlib.crc32(" ".join(sc.get("text", "") for sc in scenes).encode())      # each script its own mix (same script, same video)
    jit = lambda i, look: ((zlib.crc32(f"{seed}:{i}:{look}".encode()) % 1000) / 1000 - 0.5) * JITTER
    for i, sc in enumerate(scenes):
        k = sc["kind"]
        if sc.get("directed_look"):      # the scenes CSV chose this scene's look (reptheory/direction.py): it is used as asked and counts toward the spacing of the others
            look = sc["look"]; hist.append(look)
            if look == "3d": sc["want3d"] = True; sc["cam3d"] = C3.STYLES[style_i % len(C3.STYLES)]; style_i += 1; last3 = sc["end"]
            elif look == "flow": flows += 1
            else:
                from .direction import build_card
                build_card(sc)
            continue
        free = k in UPGRADABLE and not (k == "trainee" and sc.get("art") not in ("", None, "rep_stand_v1")) and not SYNTH_RX.search(sc.get("text", ""))
        if not free: hist.append(k); sc["look"] = k; continue
        ev = evidence(sc, last=i == len(scenes) - 1, role=roles.get(i, ""))
        if not three_d or sc["start"] - last3 < gap3 or hist[-1:] == ["3d"]: ev.pop("3d", None)
        if not flow or flows >= max_flow or hist[-2:] == ["flow", "flow"]: ev.pop("flow", None)
        ev["stock"] = (0.75 if k == "trainee" and sc.get("glows") else 0.3, None); scored = []      # the figure with the named part lit already shows the words
        for look, (base, payload) in ev.items():
            if hist[-2:] == [look, look]: continue      # never a third in a row
            score = base + (0.5 if look not in hist[-3:] else 0.0) + (0.2 if look not in hist[-6:] else 0.0) - (0.8 if hist[-1:] == [look] else 0.0) + jit(i, look) - RECENT_W * sum(1 for op in (recent or []) if i < len(op) and op[i] == look); scored.append((score, -list(ev).index(look), look, payload))
        if not scored: scored = [(0, 0, "stock", None)]
        _, _, look, payload = max(scored); sc["look"] = look; hist.append(look)
        if look == "3d": sc["want3d"] = True; sc["cam3d"] = C3.STYLES[style_i % len(C3.STYLES)]; style_i += 1; last3 = sc["end"]; sc["decisions"].append("variety: 3D body clip")
        elif look == "flow": flows += 1; sc["decisions"].append("variety: Flow picture from the narration")
        elif look == "pose":
            pp = payload; sc["was_kind"] = k; sc["kind"] = "pose"; sc["art"] = pp["art"]; sc["glows"] = pp["glows"]; sc.pop("morph", None); sc.pop("beam", None); sc["decisions"].append(f"variety: pose {pp['art']}")
        elif look in CARD_LOOKS:
            sc[look] = payload; sc["was_kind"] = k; sc["kind"] = look; sc["decisions"].append(f"variety: {look} card ({k} -> {look})")
            if look in ("stat", "bars"):
                for pg in sc["pages"]: pg["value"] = ""      # the ring shows the number: the callout column does not repeat it
            if look in FULL_CARDS: sc["pages"] = []      # the card fills the frame (a caption strip follows the narration: states.develop)
        else: sc["decisions"].append("variety: stock look kept")
    chap = lambda sc: sc["section"] if sc.get("section") and sc["section"] != sc.get("topic") and not sc["section"].startswith("TIER LIST") else ""      # a part of the video = a unit the narration announced (Part one, Week two ...)
    chapters: List[str] = []
    for sc in scenes:
        c = chap(sc)
        if c and (not chapters or chapters[-1] != c): chapters.append(c)
    if len(set(chapters)) >= 3:
        seen: List[str] = []
        for sc in scenes:
            c = chap(sc)
            if c and c not in seen:
                seen.append(c)
                if len(seen) > 1: sc["chapter_card"] = {"n": len(seen), "of": len(set(chapters)), "title": c.upper()}
    return dict(metrics(scenes), split=split)

def metrics(scenes: List[dict]) -> dict:
    """What the viewer sees across the video: looks used, the longest run of one look (scenes and seconds), and how many different looks each 5-minute window has."""
    looks = [sc.get("look") or sc["kind"] for sc in scenes]; hist: Dict[str, int] = {}
    for l in looks: hist[l] = hist.get(l, 0) + 1
    run = best = 1; run_s = best_s = 0.0; seg0 = scenes[0]["start"] if scenes else 0.0
    for i in range(len(scenes)):
        if i and looks[i] == looks[i - 1]: run += 1
        else: run = 1; seg0 = scenes[i]["start"]
        best = max(best, run); best_s = max(best_s, scenes[i]["end"] - seg0)
    wins: List[int] = []; total = scenes[-1]["end"] if scenes else 0.0; w = 0.0
    while w < total: wins.append(len({l for l, sc in zip(looks, scenes) if sc["start"] < w + 300 and sc["end"] > w})); w += 300
    return {"looks": hist, "scenes": len(scenes), "longest_run_scenes": best, "longest_same_look_s": round(best_s, 1), "distinct_per_5min": wins, "chapters": len({sc["section"] for sc in scenes if sc.get("chapter_card")}) + (1 if any(sc.get("chapter_card") for sc in scenes) else 0)}
