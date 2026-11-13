"""Variety director for long Rep Theory videos (30 minutes and more): decides, scene by scene, which LOOK the narration gets so the viewer is not shown the same kind of picture for minutes on end.
Looks: stock (the planner's own: library figure, callout), 3d (a muscle clip of the 3D body, clip3d.py), flow (a manga picture generated from the beat, beat_art.py) and four code-drawn cards that need no
assets (cards.py): stat (a stated number in a ring), steps (a spoken sequence), versus (a stated comparison), takeaway (the key line, word by word).
Rules, all measured by `metrics`: a look is only offered where the beat's own words support it (a number, a muscle, a comparison, a sequence, a key line); the same look never runs more than twice in a row;
a look not used in the last scenes is preferred; 3D clips keep a minimum spacing; a 3D scene is never followed by another.
Flow pictures have no budget (docs/rep_theory/STUDY_tendons_arm_wrestling.md: the reference is ~41% drawn pictures and never shows a text-only screen): each one is a new picture, so runs of them are allowed.
The opening scene is always a picture (the hook). Grounded scenes (tier boards, equations, held props) are never replaced; an anatomy plate is, once it has been on screen in the last PLATE_GAP_S.
Chapter banners mark each new part of a long video."""
from __future__ import annotations
import re
from typing import Dict, List, Optional

from . import clip3d as C3, diagrams as DG, qa as QA, lexicon as LX, meters as M, narrative as N, planner as P
from .beat_art import SYNTH_RX
from . import health as HE

FULL_CARDS = ("steps", "versus", "takeaway", "timeline", "mistake", "slider", "calendar", "result", "warning", "engage", "myth", "question", "checklist", "slots", "race", "formula", "mechanism", "promise") + DG.KINDS      # cards that fill the frame (DG: the Phase 3 diagrams, diagrams.py); the narration's next phrase follows in a caption strip
SIDE_CARDS = ("stat", "dial", "study", "graph", "bars", "tokens", "share") + HE.KINDS      # HE: Elder Health Theory's health cards (health.py), offered only in that theme      # cards on the left, the beat's words as callouts on the right
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

CHANGE_RX = re.compile(r"\b(?:dropp?(?:ed|s)?|fell|lower|higher|thicker|stronger|faster|slower|increase[sd]?|decrease[sd]?|jump(?:ed|s)?|grew|gain(?:ed)?|lost|cut|rose|more|less|reduc\w+|improv\w+|boost\w*|by)\b", re.I)

def result_number(text: str) -> Optional[dict]:
    """The number a sentence is about: a percentage or amount next to what changed ("dropped by about 60%", "60% lower mortality", "crossed 42 kilograms") before a
    count that only sets the scene ("across 28 countries"); else the first number. None without a number."""
    nums = [n for n in N.entities(text)["numbers"] if not re.match(r"\s*-", text[n["pos"] + len(n["text"]):n["pos"] + len(n["text"]) + 1])]      # "90-degree", "4-second" name a thing, not a result
    if not nums: return None
    def score(n):
        near = text[max(0, n["pos"] - 28):n["pos"] + len(n["text"]) + 22]
        return (2 if n["unit"] == "%" else 1 if n["unit"].upper() in ("KG", "KILOGRAM", "KILO", "POINT", "LB", "POUND") else 0) + (2 if CHANGE_RX.search(near) else 0)
    best = max(nums, key=score)
    return best if score(best) > 0 else nums[0]

def _stat(sc: dict, text: str) -> Optional[dict]:
    n = result_number(text)
    if not n: return None
    u = n["unit"].upper(); v = float(n["value"]) if not isinstance(n["value"], str) else float(re.sub(r"[^\d.]", "", n["value"]) or 0)
    if v <= 0: return None
    mode = "fill" if u == "%" and v <= 100 else "dots" if (u.rstrip("S") in COUNT_UNITS and float(v).is_integer() and 1 <= v <= 12) else "full"
    return {"value": v, "unit": n["unit"].upper() if u != "%" else "%", "mode": mode, "at": _at(sc, text, n["pos"])}

def _versus(sc: dict, text: str) -> Optional[dict]:
    for rx in VS_RX:
        m = rx.search(text); k = 4 if rx is VS_BEATS else 5 if rx is VS_NOT else -1
        if m and k == 4:      # "consistency beats intensity": the phrase each side starts with; "No workout beats a bad diet" says the opposite, "your heart beats faster" is not a comparison
            b0 = m.group(2).split()[0].lower()
            if re.match(r"\s*(?:no|nothing|never|not)\b", m.group(1), re.I) or b0.endswith(("er", "ly")) or b0 in ("per", "at", "every", "in", "up", "down", "more", "less", "faster", "about", "around", "nearly", "roughly", "almost", "over", "some", "only", "just") or b0[:1].isdigit() or b0 in LX.NUMBER_WORDS or re.search(r"\b(?:heart|hearts|pulse)\s*$", m.group(1), re.I): continue      # "your heart beats about 100,000 times" is a heartbeat, not A beats B
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

STUDY_LOOSE_RX = (re.compile(rf"\b(review|study|trial|analysis|survey)\s+of\s+{LX.NUM}\s+(?:[a-z-]+\s+){{0,2}}(studies|trials|papers|people|adults|men|women|participants|athletes|runners|lifters|patients|players)\b", re.I),
                  re.compile(rf"\b(researchers?|scientists?|a team|doctors)\s+(?:watched|tested|followed|studied|analy[sz]ed|looked at|measured|tracked|reviewed)\s+{LX.NUM}\s+(\w+)", re.I))      # "a study of 16 trained men", "researchers watched 74 of them"

def _study(sc: dict, text: str) -> Optional[dict]:
    m = STUDY_RX.search(text)
    if not m:
        for k, rx in enumerate(STUDY_LOOSE_RX):
            m2 = rx.search(text)
            if m2:
                v = _num_of(m2.group(2)); noun = m2.group(3).upper() if m2.group(3).lower() not in ("of", "them", "these", "those") else ""      # only words that were said: "74 of them" shows the number alone
                if v >= 2: return {"kind": "RESEARCH" if k else m2.group(1).upper(), "value": v, "noun": noun, "at": _at(sc, text, m2.start())}
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
TIER_RX = re.compile(rf"\b(?:(?P<lo>under|less than|below|fewer than)\s+{LX.NUM}|{LX.NUM}\s*(?:to|-)\s*{LX.NUM}|(?P<hi>over|more than|above|beyond)\s+{LX.NUM}|{LX.NUM}\s*(?:or more|\+|and up|and over))\s*(seconds?|secs?|minutes?|mins?|reps?|kg|%|percent)?\s*[,:]", re.I)      # "under 25 seconds:" as well as "under 25 seconds,"
ELDER_HURT_RX = re.compile(r"\b(?:tight\w*|chest|breath\w*|blurr\w*|confus\w*|fall\w*|bleed\w*|irregular|racing|pounding|weak\w*|vision)\b", re.I)      # Elder Health Theory: signs to see a doctor about
HURT_RX = re.compile(r"\b(?:hurts?|pain\w*|sharp|dizzy|dizziness|injur\w*|numb\w*|tingl\w*|doctor|physio\w*|swell\w*|swollen|unsafe|safely|faint)\b", re.I)
RULE_RX = re.compile(r"(?:^|[,;]\s*)((?:stop|never|don'?t|do not|avoid|rest|take|see|check|talk to|ask|ease off|back off|skip|sit down|lie down|call|seek|get help)\b[^,.;!?]*)", re.I)
CTA_RX = (("link", re.compile(r"\b(?:link(?:ed)? (?:is )?(?:below|in the description)|in the description|link below)\b", re.I)), ("comment", re.compile(r"\b(comment|let me know|tell me)\b", re.I)), ("like", re.compile(r"\b(?:tap|hit|smash|press|leave|give (?:it|this|the video))\s+(?:the\s+|a\s+)?like\b", re.I)), ("subscribe", re.compile(r"\bsubscribe\b", re.I)))

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
    tiers = _tiers(sc, text)
    return {"tiers": tiers[:4]} if len(tiers) >= 2 else None

def _tiers(sc: dict, text: str) -> list:
    tiers = []
    for m in TIER_RX.finditer(text):
        g = [x for x in m.groups() if x]; nums = [f"{_num_of(x):g}" for x in g if re.match(LX.NUM + "$", x, re.I)]; unit = (m.groups()[-1] or "").lower()
        u = "S" if unit.startswith("s") else " MIN" if unit.startswith("m") else "%" if unit in ("%", "percent") else ""
        mark = (f"UNDER {nums[0]}{u}" if m.group("lo") else f"{nums[0]}{u}+" if m.group("hi") or len(nums) == 1 else f"{nums[0]}-{nums[1]}{u}")
        meaning = _words_after(text, m.end(), 4)
        if meaning: tiers.append({"mark": mark, "text": meaning, "at": _at(sc, text, m.start())})
    return tiers

BAND_FOLLOW_S, BAND_BOARD_BASE = 40.0, 1.4
NAMED_TIER_RX = re.compile(rf"\b(?P<kind>tier|level|stage|rank)\s+(?P<n>{LX.NUM})\s*[,:.-]\s*(?P<name>[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){{0,3}})\s*:", re.I)

def bands_across(scenes: List[dict]) -> int:
    """Result bands said one per sentence ("Under 25 seconds: ... 25 to 45 seconds: ... Over 75 seconds: ..."), which no single scene holds two of: the first band's scene gets
    the whole result board (every band, in turn), each later band's scene a chip with its band lit (render 054 showed a ring, a calendar, slots and an empty tier board instead).
    Returns how many band scenes were found."""
    found = []
    for i, sc in enumerate(scenes):
        text = sc.get("script_text") or sc.get("text", "")
        m = TIER_RX.search(text)
        if m and m.start() <= 3:
            ts = _tiers(sc, text)
            if ts: found.append((i, dict(ts[0], at=float(sc["start"]) + 0.2)))
            continue
        for nm in NAMED_TIER_RX.finditer(text):      # "Tier 1, Starter Cable: ...", "Level two - Solid Frame: ..." (the script names its own levels)
            found.append((i, {"mark": f"{nm.group('kind').upper()} {_num_of(nm.group('n')):g}", "text": re.sub(r"\s+", " ", nm.group('name')).strip().upper(), "at": _at(sc, text, nm.start())}))
    runs, cur = [], []
    for i, tr in found:
        if cur and (i - cur[-1][0] > 3 or scenes[i]["start"] - scenes[cur[-1][0]]["end"] > BAND_FOLLOW_S): runs.append(cur); cur = []
        cur.append((i, tr))
    if cur: runs.append(cur)
    n = 0
    for run in runs:
        if len(run) < 2: continue
        first = scenes[run[0][0]]; t0 = float(first["start"])
        tiers = [dict(tr, at=t0 + 0.3 + 0.35 * k) for k, (_i, tr) in enumerate(run)][:4]
        first["band_card"] = {"tiers": tiers}; first["decisions"].append(f"result bands said one per sentence: the board with all {len(tiers)} bands")
        for k, (i, tr) in enumerate(run[1:], 1):
            scenes[i]["band"] = {"text": f"YOUR RESULT · {tr['mark']}", "at": float(scenes[i]["start"]) + 0.15}; scenes[i]["decisions"].append(f"result band {tr['mark']}: chip")
        n += len(run)
    return n

def _warning(sc: dict, text: str) -> Optional[dict]:
    """Safety rules stacked as warning cards: each sentence that names a sign of harm (pain, dizziness, an injury) and says what to do about it."""
    rules, pos = [], 0
    for s in re.split(r"(?<=[.!?])\s+", text):
        if HURT_RX.search(s) or (_elder() and ELDER_HURT_RX.search(s)):
            m = RULE_RX.search(s)
            if m:
                r = _words_after(m.group(1), 0, 6, lead=False)
                if len(r.split()) >= 2: rules.append({"text": r, "at": _at(sc, text, pos + m.start(1))})
        pos += len(s) + 1
    return {"rules": rules[:3]} if rules else None

LATE_FULL_PENALTY, LIB_BOOST = 0.9, 0.0
ENGAGE_LATE_S, ENGAGE_LONG_S = 1.5, 5.0      # a line that is mostly about something else, asking at its end

def _engage(sc: dict, text: str) -> Optional[dict]:
    """The call to action as the screen it asks for: the comment being typed in, the like button pressed, the subscribe button and its bell."""
    for kind, rx in CTA_RX:
        m = rx.search(text)
        if not m: continue
        at = _at(sc, text, m.start())
        dur = float(sc.get("end", at)) - float(sc["start"])
        if kind != "comment" and dur > ENGAGE_LONG_S and at - float(sc["start"]) > max(ENGAGE_LATE_S, 0.4 * dur): return None      # render 054: a LIKE button alone after 7 s of an empty screen; tricks.py puts a chip on the picture instead
        return {"kind": kind, "text": _words_after(text, m.start(), 5, lead=False) if kind == "comment" else "", "at": at}
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
    if not 3 <= len(ws) <= 16: return None      # a pick-a-side question ("Which one would you trust on a dark trail, the blaze or the look back?") runs past 12 words; the bubble wraps
    key = N.key_phrase(q, 3)[0].upper(); return {"text": q.upper(), "key": key, "at": _at(sc, text, m.start(1))}

LEAD_STOP = N.STOP - set(LX.NUMBER_WORDS)      # "one more rep" is an item; "while you eat" is not

COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
SLOTS_RX = re.compile(r"\b(two|three|four|five|six|[2-6])\s+(?:key\s+|main\s+|big\s+|simple\s+|crucial\s+)?(moments|things|mistakes|moves|rules|steps|reasons|exercises|holds|parts|signs|phases|levels|tips|habits|ways|stages|pillars|tricks|items|hacks|skills|tools|foods|places|states|methods)\b", re.I)

def _slots(sc: dict, text: str) -> Optional[dict]:
    """A spoken count ("every match comes down to four moments. The go. The wrist...") as N slots that fill as each item is named; the short fragments that follow are the items."""
    m = SLOTS_RX.search(text)
    if not m: return None
    n = COUNT_WORDS.get(m.group(1).lower()) or int(m.group(1)); noun = m.group(2).upper()
    head = re.split(r"[.!?]", text[:m.start()])[-1]; kick = [w for w in re.findall(r"[A-Za-z0-9'%-]+", head)][-6:]
    items, pos = [], m.end()
    for frag in re.finditer(r"[^.!?]+[.!?]?", text[m.end():]):
        ws = re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", frag.group(0))
        while ws and ws[0].lower() in ("and", "then", "or"): ws.pop(0)
        if 1 <= len(ws) <= 4 and len(items) < n: items.append({"text": " ".join(ws).upper(), "at": _at(sc, text, m.end() + frag.start() + frag.group(0).find(ws[0]))})
        elif ws and items: break
    at = _at(sc, text, m.start())
    if len(items) < 2: items = []
    while len(items) < n: items.append({"text": "", "at": at + 0.25 * len(items)})
    return {"title": f"{m.group(1).upper() if not m.group(1).isdigit() else m.group(1)} {noun}".replace("FOUR", "4").replace("THREE", "3").replace("FIVE", "5").replace("TWO", "2").replace("SIX", "6"), "kicker": " ".join(kick).upper(), "noun": noun.rstrip("S"), "items": items, "at": at}

FAST_RX = re.compile(r"\b(fast(?:er)?|first|quick(?:er|ly)?|early|sooner|instantly)\b", re.I); SLOW_RX = re.compile(r"\b(late|later|slow(?:er)?|behind|loses?)\b", re.I)
OPPOSITE = {"stiff": "STRETCHY", "stiffer": "STRETCHIER", "strong": "WEAK", "stronger": "WEAKER", "trained": "UNTRAINED", "heavy": "LIGHT", "fast": "SLOW", "trained,": "UNTRAINED"}

def _race(sc: dict, text: str) -> Optional[dict]:
    """Fast against late in one scene ("stiff tendons get it there fast. In an arm wrestle, late loses"): a race to a finish line."""
    f, sl = FAST_RX.search(text), SLOW_RX.search(text)
    if not f: return None
    clause = re.split(r"[,.;:!?]", text[:f.start()])[-1]; ws = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", clause) if w.lower() not in N.STOP][:2]
    named = bool(ws) and ws[0].lower() in OPPOSITE; wins = re.search(r"\b(?:wins?|takes?|beats?|gets? there)\b", text[f.start():], re.I)
    if not ((sl and re.search(r"\blate\b|\bslow", text, re.I) and ws) or (named and re.search(r"\bget(?:s)? (?:it )?there\b|\barrives?\b", text, re.I)) or wins):      # a race: fast vs late said, or "stiff X gets there fast", or "whoever ... first takes / wins"
        return None
    if named: fast = " ".join(ws).upper(); slow = OPPOSITE[ws[0].lower()] + ("" if len(ws) < 2 else " " + ws[1].upper())
    else: fast, slow = ("FIRST" if f.group(1).lower() == "first" else "FAST"), "LATE"
    sl_at = _at(sc, text, sl.start()) if sl else _at(sc, text, f.start()) + 1.0
    return {"fast": {"text": fast, "at": _at(sc, text, f.start())}, "slow": {"text": slow, "at": sl_at}, "at": _at(sc, text, max(0, f.start() - len(clause))), "title": "", "finish": ""}

FORMULA_RX = ((re.compile(r"(?:^|[,.;:!?]\s*)(?:a |an |the |your )?([A-Za-z][A-Za-z' -]{2,30}?)\s+(?:is not|isn't|are not|aren't|doesn't mean|does not mean|never means)\s+(?:a |an |the )?([A-Za-z][A-Za-z' -]{2,28}?)(?=[,.;:!?]|$)", re.I), "≠"),
              (re.compile(r"(?:^|[,.;:!?]\s*)(?:a |an |the |your )?([A-Za-z][A-Za-z' -]{2,30}?)\s+(?:means|equals|is like|is basically)\s+(?:a |an |the )?([A-Za-z][A-Za-z' -]{2,28}?)(?=[,.;:!?]|$)", re.I), "="))

def _formula(sc: dict, text: str) -> Optional[dict]:
    """A short "X is not Y" / "X means Y" / "X is like Y" as a big formula, both sides the sentence's own words (at most 3 each)."""
    for rx, sign in FORMULA_RX:
        m = rx.search(text)
        if not m: continue
        trim = lambda ws: ws[next((i for i, w in enumerate(ws) if w.lower() not in N.STOP), len(ws)):len(ws) - next((i for i, w in enumerate(reversed(ws)) if w.lower() not in N.STOP), len(ws))]      # function words only at the ends go
        a, b = trim(m.group(1).split()), trim(m.group(2).split())
        if 1 <= len(a) <= 3 and 1 <= len(b) <= 4 and a != b: return {"a": {"text": " ".join(a).upper(), "at": _at(sc, text, m.start(1))}, "b": {"text": " ".join(b).upper(), "at": _at(sc, text, m.start(2))}, "sign": sign}
    return None

MECH_PULL = re.compile(r"\b(pulls?|pulling|reaches|travels|transfers?|passes)\b", re.I)

def _mechanism(sc: dict, text: str) -> Optional[dict]:
    """Muscle -> tendon -> bone when the sentence names at least two of them and the pull between them."""
    parts = {k: re.search(rf"\b{k}s?\b", text, re.I) for k in ("muscle", "tendon", "bone")}; pull = MECH_PULL.search(text)
    if sum(1 for v in parts.values() if v) < 2 or not pull: return None
    labels = {k: _at(sc, text, v.start()) for k, v in parts.items() if v}
    return {"labels": labels, "pull_at": _at(sc, text, pull.start()), "at": min(labels.values()), "stretchy": bool(re.search(r"\b(stretchy|slack|loose|soft)\b", text, re.I))}

PROMISE_RX = re.compile(r"\b(?:i'?ll|i will|we'?ll|we will)\s+(?:show|tell|reveal)\s+you\b[^.!?]*?\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:out of|in)\s+(\d+|ten|twenty|a hundred|100)\b([^.!?]*)", re.I)

def _promise(sc: dict, text: str) -> Optional[dict]:
    """A payoff promised for later with a share ("I'll show you what 8 out of 10 had in common"): N of M cells turn into question marks and lock."""
    m = PROMISE_RX.search(text)
    if not m:      # a payoff promised for later without a share ("at the end, I'll tell you what your time means"): the locked board with what is promised
        m2 = re.search(r"\b(?:at the end|later|in a (?:minute|moment)|before we finish)\b[^.!?]{0,20}\b(?:i'?ll|i will|we'?ll|we will)\s+(?:show|tell|reveal|explain)\s+(?:you\s+)?([^,.!?]{3,60})", text, re.I) or \
             re.search(r"\b(?:i'?ll|i will|we'?ll|we will)\s+(?:show|tell|reveal|explain)\s+(?:you\s+)?([^,.!?]{3,60}?)\s+(?:at the end|later|in a (?:minute|moment))\b", text, re.I)
        if not m2: return None
        tail = re.findall(r"[A-Za-z0-9'%-]+", m2.group(1))[:6]
        while tail and tail[-1].lower() in N.DANGLING | {"what", "which", "your", "my", "our", "how"}: tail.pop()      # render 054: "THE EXACT SCORECARD FOR WHAT YOUR"
        return {"n": 0, "of": 0, "at": _at(sc, text, m2.start()), "label": " ".join(tail).upper()}
    n, of = int(_num_of(m.group(1)) or 0), int(_num_of(m.group(2)) or 0)
    if not (0 < n <= of <= 20): return None
    tail = re.findall(r"[A-Za-z0-9'%-]+", m.group(3)); return {"n": n, "of": of, "at": _at(sc, text, m.start(1)), "label": " ".join(tail).upper() if len(tail) <= 5 else ""}

SHORT_LIST_RX = re.compile(r"(?:^|(?<=[.!?])\s+)((?:[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,2},\s+){2,4}[A-Za-z][\w'-]*(?:\s+[A-Za-z][\w'-]*){0,2})[.!?]", re.I)      # "Every hold, how heavy, how long."

TIP_STOP = {"if", "when", "because", "but", "so", "that", "which", "who", "while", "although", "since", "unless", "then", "it", "this", "these", "those"}

def _elder() -> bool:
    from . import theme as T
    return T.THEME == "elder"

def _long_list(sc: dict, text: str) -> Optional[dict]:
    """Elder Health Theory: a spoken list of 3-5 tips of up to 8 words each ("walk after every meal, drink a glass of water each morning, and sleep before eleven"):
    the sentence cut at its commas / final "and", every part 2-8 words and none opening a clause (if, when, because...)."""
    body = re.sub(r"^[^,]*?:\s*", "", text.strip().rstrip(".!?"))
    parts = [p.strip() for p in re.split(r",\s*(?:and\s+|or\s+)?|\s+and\s+(?=[a-z]+\s)", body) if p.strip()]
    if not 3 <= len(parts) <= 5 or any(not 2 <= len(p.split()) <= 8 or p.split()[0].lower() in TIP_STOP for p in parts): return None
    items, pos = [], 0
    for p in parts: i = text.find(p, pos); pos = i + len(p); items.append({"text": p[0].upper() + p[1:], "at": _at(sc, text, max(0, i))})
    return {"items": items, "ticks": True}

def _checklist(sc: dict, text: str) -> Optional[dict]:
    """A spoken list of three or more short items ("eat, sleep and recover", "every hold, how heavy, how long") ticked off one by one as each is said."""
    if _elder():
        got = _long_list(sc, text)
        if got: return got
    m = LIST_RX.search(text)
    if not m:
        m3 = SHORT_LIST_RX.search(text)
        if not m3: return None
        parts = [p.strip() for p in m3.group(1).split(",") if p.strip()]; out = []; base = m3.start(1)
        for p_ in parts: out.append({"text": p_.upper(), "at": _at(sc, text, base + m3.group(1).find(p_))})
        return {"items": out, "ticks": True} if 3 <= len(out) <= 5 else None
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

ELDER_FLOW_BOOST = 0.9      # Elder Health Theory: a picture beats any card unless the last two scenes were pictures (about two pictures to every card)
RESULT_STAT_BASE, RESULT_LATE_S = 1.2, 4.5      # above a fresh picture (0.82 + 0.3 rotation): the measured result is what the viewer must see
FLOW_BASE = 0.82      # a picture drawn for this sentence: a card with a real shape in the words (0.85-0.95) still wins, a bare headline never does
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

SKETCH_BASE = 0.84      # a line figure doing the exercise: above a picture of the same line (0.82), below a fresh pose (0.8 + rotation)
SKETCH_VARIANTS = {"wall", "incline", "knee", "onearm"}

def _sketch(text: str) -> Optional[dict]:
    """The line-figure scene for a sentence that names an exercise or setting the figure can do (sketch.py; beats.sketch_spec reads it), else None."""
    from .beats import sketch_spec
    try: return sketch_spec({"text": text, "entities": N.entities(text)})
    except Exception: return None

EQ_UNITS = {"gram": "G", "grams": "G", "g": "G", "kilo": "KG", "kilos": "KG", "kilogram": "KG", "kilograms": "KG", "kg": "KG", "pound": "LB", "pounds": "LB", "lb": "LB", "lbs": "LB",
            "litre": "L", "litres": "L", "liter": "L", "liters": "L", "calorie": "KCAL", "calories": "KCAL", "kcal": "KCAL", "minute": "MIN", "minutes": "MIN", "second": "S", "seconds": "S",
            "hour": "H", "hours": "H", "mile": "MI", "miles": "MI", "kilometre": "KM", "kilometres": "KM", "kilometer": "KM", "kilometers": "KM", "km": "KM", "rep": "REPS", "reps": "REPS", "set": "SETS", "sets": "SETS",
            "percent": "%", "%": "%", "step": "STEPS", "steps": "STEPS", "egg": "EGGS", "eggs": "EGGS", "cup": "CUPS", "cups": "CUPS"}
EQ_RX = re.compile(rf"\b(an?|{LX.NUM[1:-1]})\s*([a-z%]+)(?:\s+of\s+[a-z-]+)?\s+(?:is|are|equals?|=|makes?|gives? you)\s+(?:about|roughly|around|nearly|almost|just|the same as|equal to|like|close to)?\s*{LX.NUM}\s*([a-z%]+)(?:\s+([a-z-]+))?", re.I)
EQ_MAX_CHARS = 12      # both sides together: the lockup is drawn very large

def _equation(sc: dict, text: str) -> Optional[list]:
    """An equality or conversion said in one sentence with a number on both sides ("one kilo is about two pounds", "30 grams of protein is about one chicken breast"): the equation
    lockup, each side "<number> <unit>" with the unit shortened (KG, LB, G, KCAL ...) or a short noun, each term on its own word. None when the two sides would not fit."""
    m = EQ_RX.search(text)
    if not m: return None
    def side(num: str, unit: str, extra: str = "") -> str:
        if unit.lower() in LX.NUMBER_WORDS: return ""      # "twenty five." is one number with no unit, not "20 FIVE"
        u = EQ_UNITS.get(unit.lower()); n = 1 if num.lower() in ("a", "an") else LX.num(num)
        if u: return f"{n:g} {u}" if isinstance(n, float) else f"{n} {u}"
        noun = (extra if extra and unit.lower() in ("chicken", "big", "small", "large", "medium") else unit).upper()
        return f"{n} {noun}" if len(noun) <= 6 else ""
    lhs, rhs = side(m.group(1), m.group(2)), side(m.group(3), m.group(4), m.group(5) or "")
    if not lhs or not rhs or lhs == rhs or len(lhs) + len(rhs) > EQ_MAX_CHARS: return None
    return [{"lhs": lhs, "rhs": rhs, "at_l": _at(sc, text, m.start(1)), "at_r": max(_at(sc, text, m.start(3)), _at(sc, text, m.start(1)) + 0.4)}]

BONE_RX = re.compile(r"\b(?:bones?|bone density|cortical|skeleton|x-?ray|marrow)\b", re.I)

def evidence(sc: dict, last: bool = False, role: str = "") -> Dict[str, tuple]:
    """look -> (support 0..1, payload) for what this scene's own words can honestly show."""
    text = sc.get("text", ""); ev: Dict[str, tuple] = {}
    if not text.strip() or SYNTH_RX.search(text): return ev
    g, by_ex = C3.groups_for(LX.affirmed(text))      # "there is zero muscle belly" is not a muscle clip
    if g and not BONE_RX.search(text): ev["3d"] = (0.7 if by_ex else 0.9, None)      # the 3D body is muscles: a line about bone or an x-ray gets a picture (render 054: x-ray bone shown as a muscle clip)
    from . import assets as AS
    lib = AS.match(text)
    for look, fn, base in (("timeline", lambda: _timeline(sc, text), 0.95), ("mistake", lambda: _mistake(sc, text), 0.9), ("slider", lambda: _slider(sc, text), 0.9),
                           ("dial", lambda: _dial(sc, text), 0.9), ("study", lambda: _study(sc, text), 0.88), ("result", lambda: _result(sc, text), 0.95), ("calendar", lambda: _calendar(sc, text), 0.9),
                           ("warning", lambda: _warning(sc, text), 0.85), ("bars", lambda: _bars(sc, text), 0.86), ("graph", lambda: _graph(sc, text), 0.82), ("engage", lambda: _engage(sc, text), 0.8), ("myth", lambda: _myth(sc, text), 0.92), ("question", lambda: _question(sc, text), 0.78), ("tokens", lambda: M.tokens(sc, text), 0.91), ("share", lambda: M.share(sc, text), 0.92), ("slots", lambda: _slots(sc, text), 0.93), ("race", lambda: _race(sc, text), 0.9), ("formula", lambda: _formula(sc, text), 0.86), ("mechanism", lambda: _mechanism(sc, text), 0.92), ("promise", lambda: _promise(sc, text), 0.94), ("checklist", lambda: _checklist(sc, text), 0.8), ("stat", lambda: _stat(sc, text), 0.85), ("versus", lambda: _versus(sc, text), 0.8), ("steps", lambda: _steps(sc, text), 0.8), ("takeaway", lambda: _takeaway(sc, text, last, role), 0.9 if last else 0.6)):
        got = fn()
        if got:
            late = look not in OPEN_AT_START and _first_at(got) - float(sc["start"]) > LATE_CARD_S
            ev[look] = (base - ((LATE_FULL_PENALTY if look in FULL_CARDS else 0.6) if late else 0.0), got)      # render 054: a warning card empty for 6 s of 8: a full-frame card that would sit empty is the last resort      # a side card whose first element comes late keeps the scene's words beside it, at a lower score
    for look, (base, got) in DG.evidence(sc, text).items():      # the diagrams that explain why (diagrams.py)
        ev[look] = (base - (0.6 if _first_at(got) - float(sc["start"]) > LATE_CARD_S else 0.0), got)
    if sc.get("band_card"): ev["result"] = (BAND_BOARD_BASE, sc["band_card"])      # the whole ladder the script is about to walk through: nothing else on this line says as much      # the bands said across sentences (bands_across)
    if sc.get("pose_pick"): ev["pose"] = (POSE_BASE, sc["pose_pick"])      # the character doing what the sentence names (poses.py)
    sk = _sketch(text)
    if sk and (not sc.get("pose_pick") or sk.get("variant") in SKETCH_VARIANTS): ev["sketch"] = (SKETCH_BASE, sk)      # the exercise drawn as a moving line figure: when no pose shows it, or the sentence names a variant only the line figure has (wall / incline / knee push-up)
    eq = _equation(sc, text)
    if eq: ev["equation"] = (0.88, eq)
    ev.update(HE.evidence(sc, text, _at))      # Elder Health Theory: heart monitor, blood-pressure gauge, sugar meter, body map, water glasses, sleep dial (empty in other themes)
    if "engage" in ev: ev.pop("takeaway", None)      # a call to action is shown as the screen it asks for, not as a key line
    if N.key_phrase(text, 3)[0] or len(text.split()) >= 4: ev["flow"] = (FLOW_BASE + (LIB_BOOST if lib else 0.0), None)      # any sentence can be drawn; one naming a library asset (nervous system, shoulder blades, x-ray) is drawn as it (render 054 showed the plain figure)
    if "takeaway" not in ev and not any(pg.get("headline") or pg.get("value") or pg.get("chips") for pg in sc.get("pages", [])):      # a scene with nothing written on it would be a bare figure: its own words, lit as they are spoken, are the fallback
        ws = sc.get("words") or []
        if 4 <= len(ws) <= 22 and sc["end"] - sc["start"] >= 3.0: ev["takeaway"] = (0.55, {"words": [{"w": re.sub(r"[^\w'-]", "", w["w"]).upper() or w["w"].upper(), "t0": float(w["t0"])} for w in ws]})
    if "stat" in ev:      # a result the script measured ("dropped by about 60%", "a 54% increase"): the number is the picture, it wins over a drawing or the figure
        rn = result_number(text); late = _first_at(ev["stat"][1]) - float(sc["start"])
        if rn and rn["unit"] == "%" and CHANGE_RX.search(text[max(0, rn["pos"] - 28):rn["pos"] + len(rn["text"]) + 22]) and late <= RESULT_LATE_S:      # the beat's words stand beside the ring until the number is said
            ev["stat"] = (RESULT_STAT_BASE - (0.25 if late > LATE_CARD_S else 0.0), ev["stat"][1])
    if "equation" in ev: ev.pop("stat", None); ev.pop("bars", None)      # the lockup already shows both numbers: one of them alone in a ring would say less
    return ev

SPLIT_MIN_S, SPLIT_CARD, Q_SPLIT_MIN_S = 2.5, 0.85, 1.5      # each half of a split scene lasts at least this long; only a strong card shape is worth a cut
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

def _names_part(text: str) -> bool:
    from .states import BODY_RX
    return any(rx.search(text) for rx in BODY_RX.values())

LONG_S, LONG_PART_S = 6.0, 2.0      # the reference changes shot every ~3.6 s (one clause): a scene joining sentences past 6 s is cut at its sentence ends
LONG_KINDS = {"callout", "trainee", "anatomy"}

def split_long(scenes: List[dict]) -> int:
    """A scene of the app's own (not a CSV row, not a board or equation) that joins sentences and runs past LONG_S is cut at the sentence end nearest its middle, again until
    every part is under LONG_S or has no sentence end left with LONG_PART_S on each side. Each part then gets the look its own words support. Returns how many cuts were made."""
    n = 0; i = 0
    while i < len(scenes):
        sc = scenes[i]; ws = sc.get("words") or []
        if sc["kind"] not in LONG_KINDS or sc.get("directed_look") or sc["end"] - sc["start"] <= LONG_S or len(ws) < 6: i += 1; continue
        tx = sc.get("text", "").split(); punct = [tok for tok in tx] if len(tx) == len(ws) else [w["w"] + w.get("p", "") for w in ws]
        mid = (sc["start"] + sc["end"]) / 2; best = None
        for k in range(1, len(ws)):
            if not re.search(r"[.!?]$", punct[k - 1]): continue
            t = float(ws[k]["t0"])
            if t - sc["start"] >= LONG_PART_S and sc["end"] - t >= LONG_PART_S and (best is None or abs(t - mid) < abs(best - mid)): best = t
        if best is None: i += 1; continue
        a, b = _cut(sc, best); a["decisions"][-1] = b["decisions"][-1] = "variety: a long scene cut at a sentence end (one shot per clause)"
        for part in (a, b):      # a part whose own words name no body part does not keep the plate or the lit figure: it is a plain text scene, free for any look
            if part["kind"] == "anatomy" and not _names_part(part.get("text", "")) or part["kind"] == "trainee" and not part.get("glows"):
                part["was_kind"] = part["kind"]; part["kind"] = "callout"; part["art"] = ""; part["glows"] = []; part.pop("glow", None)
        scenes[i:i + 1] = [a, b]; n += 1
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

PIC_LONG_S, PIC_PART_S = 8.0, 3.0      # a picture held longer than this is cut at a clause; each part at least this long

def reframe_long(scenes: List[dict]) -> int:
    """A picture scene held past PIC_LONG_S (render 054: one picture for 16.5 s, the reference changes shot every ~3.8 s) is cut at the sentence end or comma nearest its
    middle. A CSV row's picture is shown again, re-framed (same picture, another camera: nothing new to generate); the app's own picture scenes get a picture of their own
    half. Returns how many cuts were made."""
    n = 0; i = 0
    while i < len(scenes):
        sc = scenes[i]; ws = sc.get("words") or []
        if sc.get("look") != "flow" or sc.get("hook") or sc["end"] - sc["start"] <= PIC_LONG_S or len(ws) < 6: i += 1; continue
        punct = _punct(sc); mid = (sc["start"] + sc["end"]) / 2; best = None
        for strong in (True, False):
            for k in range(1, len(ws)):
                if not re.search(r"[.!?]$" if strong else r"[,;:]$", punct[k - 1]): continue
                t = float(ws[k]["t0"])
                if t - sc["start"] >= PIC_PART_S and sc["end"] - t >= PIC_PART_S and (best is None or abs(t - mid) < abs(best - mid)): best = t
            if best is not None: break
        if best is None: i += 1; continue
        a, b = _cut(sc, best)
        if sc.get("flow_prompt") or sc.get("asset"):
            b["same_picture"] = True; b["camera"] = "wide" if str(a.get("camera") or "").lower().startswith("close") else "close"
            a["decisions"][-1] = b["decisions"][-1] = "variety: a long picture cut at a clause, the second part the same picture re-framed"
        else: a["decisions"][-1] = b["decisions"][-1] = "variety: a long picture cut at a clause, each part its own picture"
        scenes[i:i + 1] = [a, b]; n += 1
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

SLOT_FOLLOW_S = 10.0      # how far after a count the short rows that name its items may come

def fill_slots(scenes: List[dict]) -> int:
    """A count card ("Every match comes down to four moments.") whose items are said as short sentences of their own ("The go." "The wrist." ...: separate rows in the scenes CSV,
    as its prompt suggests) takes those as its slot names: each short scene that follows (4 words or fewer, no look of its own) fills the next empty slot at its own time and is joined
    into the card, which stays on screen while the items are named. Returns how many slots were named."""
    n = 0; i = 0
    while i < len(scenes):
        sc = scenes[i]; sl = sc.get("slots")
        if sc.get("kind") != "slots" or not sl or all(it["text"] for it in sl["items"]): i += 1; continue
        j = i + 1
        while j < len(scenes) and any(not it["text"] for it in sl["items"]):
            nx = scenes[j]; ws = re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", nx.get("text", ""))
            while ws and ws[0].lower() in ("and", "then", "or"): ws.pop(0)
            if nx["start"] - sc["end"] > SLOT_FOLLOW_S or not 1 <= len(ws) <= 4 or (nx.get("directed_look") and nx.get("look") not in (None, "", "stock")) or nx["kind"] in ("tier", "equation"): break
            k = next(x for x, it in enumerate(sl["items"]) if not it["text"]); sl["items"][k] = {"text": " ".join(ws).upper(), "at": float(nx["start"])}
            sc["end"] = nx["end"]; sc["words"] = (sc.get("words") or []) + (nx.get("words") or []); sc["text"] = (sc.get("text", "") + " " + nx.get("text", "")).strip()
            sc["decisions"].append(f"slot {k + 1} named by the short sentence that follows: {sl['items'][k]['text']}"); del scenes[j]; n += 1
        if any(not it["text"] for it in sl["items"]):      # "these four holds build ...": the units the script announced give the names (render 054 showed four blank slots)
            from .chain import STEP_RX
            names = []
            for x in scenes:
                mm = STEP_RX.match(x.get("section") or "")
                if mm and mm.group(1).upper().startswith(sl["noun"].upper().rstrip("S")[:4]) and mm.group(3).strip() and mm.group(3).strip().upper() not in names: names.append(mm.group(3).strip().upper())
            if len(names) == len(sl["items"]):
                for x, it in enumerate(sl["items"]):
                    if not it["text"]: it["text"] = names[x]
                sc["decisions"].append("slots named after the units they count: " + ", ".join(names))
        for x, it in enumerate(sl["items"]):      # slots still unnamed stay numbered, appearing in turn after the named ones
            if not it["text"]: it["at"] = max(it["at"], max((y["at"] for y in sl["items"] if y["text"]), default=it["at"]) + 0.25 * (x + 1))
        i += 1
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

SLOT_ITEM_MAX_W, SLOT_REST_MIN_S = 4, 0.8      # a slot name is a sentence of at most 4 words; a remainder shorter than this joins the count card too

def _punct(sc: dict) -> List[str]:
    """Each word of the scene with its own punctuation: from the scene's text when its tokens line up with the words, else the words' own `p`."""
    ws = sc.get("words") or []; tx = sc.get("text", "").split()
    return tx if len(tx) == len(ws) else [w["w"] + w.get("p", "") for w in ws]

def absorb_slot_items(scenes: List[dict]) -> int:
    """A count ("Every match comes down to four moments.") whose item names were joined by the planner into the next scene ("the go. the wrist. the squeeze. and the line.
    you've seen it happen.": blank CSV rows, render final 3): the leading short sentences of that scene (1-4 words each, up to the count) are cut off and joined into the
    count scene, so its card names its slots; the rest keeps its own scene. Runs before the looks are chosen. Returns how many item sentences were joined."""
    n = 0; i = 0
    while i + 1 < len(scenes):
        sc, nx = scenes[i], scenes[i + 1]; m = SLOTS_RX.search(sc.get("text", ""))
        if not (m or (sc.get("directed_look") and sc.get("look") == "slots")) or nx["kind"] in ("tier", "equation") or nx.get("directed_look"): i += 1; continue
        count = (COUNT_WORDS.get(m.group(1).lower()) or int(m.group(1))) if m else 6; ws = nx.get("words") or []; punct = _punct(nx); k = 0; items = 0; start = 0
        while k < len(ws) and items < count:      # sentence by sentence from the start of the next scene
            j = k
            while j < len(ws) and not re.search(r"[.!?]$", punct[j]): j += 1
            if j >= len(ws) or not 1 <= len([w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", " ".join(punct[k:j + 1])) if w.lower() not in ("and", "then", "or")]) <= SLOT_ITEM_MAX_W: break
            items += 1; k = j + 1
        if not items: i += 1; continue
        if k < len(ws) and float(ws[k]["t0"]) < nx["end"] - SLOT_REST_MIN_S: part, rest = _cut(nx, float(ws[k]["t0"]))
        else: part, rest = nx, None
        sc["end"] = part["end"]; sc["words"] = (sc.get("words") or []) + (part.get("words") or []); sc["text"] = (sc.get("text", "") + " " + part.get("text", "")).strip()
        sc["decisions"].append(f"the {items} item name(s) said right after the count joined into it (slot names)"); sc["slot_names"] = True; n += items
        if rest is not None: rest["decisions"][-1] = "variety: the item names before it joined the count card"; scenes[i + 1:i + 2] = [rest]
        else: del scenes[i + 1]
        if sc.get("directed_look") and sc.get("look") == "slots": sc["look_payload"] = _slots(sc, sc["text"]) or sc.get("look_payload")      # the CSV asked for the count card: it is rebuilt with the names
        if rest is not None or (_slots(sc, sc["text"]) or {}).get("items", [{}])[-1].get("text"): i += 1      # items said as separate scenes: the next one may be an item too
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

CARD_HOLD_S, NEXT_MIN_S, NEXT_MIN_SHARE = 0.5, 1.5, 0.4      # a card stays this long once its animation is done; the scene after it keeps at least this much of its time

def let_cards_finish(scenes: List[dict]) -> int:
    """A card whose animation needs longer than its scene (render final 3: a race cut 2.1 s early, slots 1.1 s, the comment typing 0.2 s) keeps the screen into the next scene's
    time, as long as that scene keeps NEXT_MIN_S and NEXT_MIN_SHARE of its own length; the words are not moved. Returns how many scenes were extended."""
    from . import cards as K
    done_at = getattr(K, "CARD_DONE", {}); n = 0
    for sc, nx in zip(scenes, scenes[1:]):
        f = done_at.get(sc["kind"])
        if f is None or not sc.get(sc["kind"]): continue
        try: need = float(f(sc[sc["kind"]])) + CARD_HOLD_S
        except Exception: continue
        nlen = nx["end"] - nx["start"]; b = min(need - sc["end"], nlen - max(NEXT_MIN_S, NEXT_MIN_SHARE * nlen))
        if need <= sc["end"] or b <= 0.05: continue
        sc["end"] += b; nx["start"] += b; n += 1
        sc["decisions"].append(f"its card needs {need - sc['start']:.1f} s: it keeps the screen {b:.1f} s longer"); nx["decisions"].append(f"starts {b:.1f} s later so the card before it can finish")
    return n

CONCRETE_RX = re.compile(r"\b(table|bar|towel|hammer|bucket|backpack|book|books|dumbbell|kettlebell|barbell|band|bench|rope|chair|wall|floor|ball|scale|clock|bottle|plate|bed|weights?|ref(?:eree)?|rival|opponent|guy|man|woman|coach|gym)\b", re.I)

def _vague(sc: dict) -> bool:
    """A line with nothing of its own to draw: no body part, no exercise or action pose, no object or person ("But first, a quick test.", "So let's start.")."""
    from .states import BODY_RX
    text = sc.get("text", "")
    return not (any(rx.search(text) for rx in BODY_RX.values()) or sc.get("pose_pick") or CONCRETE_RX.search(text) or C3.groups_for(text)[0] or N.key_phrase(text, 3)[0] and len(text.split()) > 9)

def _neighbour_picture(scenes: List[dict], i: int) -> Optional[dict]:
    """For a vague line given a Flow picture: the picture of the scene just before (or just after) in the same part, when it has a described picture, so the shot is that
    picture re-framed (the reference shows each picture for 2-4 lines) instead of a new picture of nothing. At most two lines in a row borrow the same picture."""
    sc = scenes[i]
    if not _vague(sc): return None
    for j in (i - 1, i + 1):
        if not 0 <= j < len(scenes): continue
        nb = scenes[j]
        if nb.get("section") != sc.get("section") or not nb.get("flow_prompt") or (j > i and not (nb.get("directed_look") and nb.get("look") == "flow")) or (j < i and nb.get("look") != "flow"): continue
        if j < i and nb.get("reuses_picture") and i >= 2 and scenes[i - 2].get("reuses_picture"): continue
        return nb
    return None

UNIT_RX = re.compile(r"^(LINK|MOVE|MOMENT|STEP|LEVEL|HOLD|PHASE|STAGE|EXERCISE|DRILL)\s+(\d+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\b", re.I)
WHY_RX = re.compile(r"\b(because|the reason|that's why|which is why|physics|lever|researchers?|stud(?:y|ies)|in plain words|works like|it's like|means that|depends on)\b", re.I)
WARN_PART_RX = re.compile(r"\b(warning|injur\w*|hurts?|pain|tendons? (?:can|get)|danger\w*|careful|too fast|too soon)\b", re.I)
PLAN_RX = re.compile(r"\b(plan|schedule|routine|days? a week|times a week|each session|every session|your week|program(?:me)?)\b", re.I)
RESULT_RX = re.compile(r"\b(your (?:result|score|time|number)|if you (?:held|got|managed)|under \d+|start (?:at|on) (?:link|level|step|move))\b", re.I)
SECTION_BOOST = {      # look -> score nudge per part of the video
    "howto": {"seesaw": 0.05, "pose": 0.15, "flow": 0.10, "stock": 0.10, "sketch": 0.10, "timeline": 0.05, "stat": 0.05},
    "why": {"lever": 0.15, "gap": 0.15, "seesaw": 0.10, "split": 0.10, "panels": 0.10, "graph": 0.15, "bars": 0.15, "formula": 0.15, "mechanism": 0.15, "study": 0.10, "versus": 0.10, "race": 0.10, "equation": 0.10, "dial": 0.05, "flow": -0.10},
    "warning": {"gap": 0.10, "warning": 0.15, "mistake": 0.15, "3d": 0.10, "myth": 0.10, "flow": -0.05},
    "plan": {"clipboard": 0.15, "battery": 0.10, "tearoff": 0.10, "road": 0.05, "calendar": 0.15, "checklist": 0.15, "steps": 0.15, "stat": 0.10, "slots": 0.10},
    "result": {"result": 0.15, "engage": 0.10, "stat": 0.10},
}

def section_kind(sc: dict) -> str:
    """Which part of the video a scene is in: a how-to unit (its section is a numbered link / move / step ...), else by what its sentence does: why it works,
    a warning, the plan, the result; "" when it is none of them."""
    if sc.get("section_csv") in SECTION_BOOST: return sc["section_csv"]      # the CSV said so
    text = sc.get("script_text") or sc.get("text", ""); sec = (sc.get("section") or "").strip()
    if WARN_PART_RX.search(text) or "WARNING" in sec.upper(): return "warning"
    if RESULT_RX.search(text) or "RESULT" in sec.upper(): return "result"
    if PLAN_RX.search(text) or re.search(r"\bPLAN\b|\bWEEK\b|SCHEDULE", sec, re.I): return "plan"
    if WHY_RX.search(text): return "why"
    if UNIT_RX.match(sec): return "howto"
    return ""

JOIN_MAX_S = 8.0
SHORT_S = 1.6
SHORT_RX = re.compile(r":\s*$|\b(?:that'?s|it'?s|this is|that is|it is)\s+not\b", re.I)

def join_short(scenes: List[dict]) -> int:
    """A scene too short to read (under SHORT_S) that only labels what follows ("the towel ring hold:") or denies what the next line answers ("that's not muscle." / "it's their
    tendons") joins the next scene, which keeps its own look (render 054 had 1.0-1.2 s shots). Short emphatic lines ("you're right.") stay: they are stamped. Returns the joins."""
    n = 0; i = 1
    while i < len(scenes) - 1:
        a, b = scenes[i], scenes[i + 1]
        if a["end"] - a["start"] >= SHORT_S or not SHORT_RX.search(a.get("text", "")) or a.get("section") != b.get("section") or a["kind"] in ("tier", "equation"): i += 1; continue
        m = dict(b, start=a["start"], words=(a.get("words") or []) + (b.get("words") or []), text=a["text"].rstrip() + " " + b["text"].lstrip())
        if a.get("script_text") or b.get("script_text"): m["script_text"] = ((a.get("script_text") or a["text"]) + " " + (b.get("script_text") or b["text"])).strip()
        for k, v in a.items():
            if isinstance(v, list) and k != "words" and isinstance(b.get(k), list): m[k] = v + b[k]
        m["decisions"] = list(b["decisions"]) + [f"joined the {a['end'] - a['start']:.1f} s line before it: '{a['text'][:40]}'"]
        scenes[i:i + 2] = [m]; n += 1
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

def join_for_diagrams(scenes: List[dict]) -> int:
    """Two text scenes that are one sentence cut at a comma ("Some people get it in a few months, | others take one to two years, some never.") are joined back when the
    whole sentence gives a diagram more parts than either half (first render: the tear-off pages lost "FEW MONTHS"). Returns how many joins were made."""
    n = 0; i = 0
    while i < len(scenes) - 1:
        a, b = scenes[i], scenes[i + 1]
        if any(x["kind"] != "callout" or x.get("directed_look") or x.get("art") for x in (a, b)) or not a.get("text", "").rstrip().endswith(",") or b["end"] - a["start"] > JOIN_MAX_S: i += 1; continue
        m = dict(a, end=b["end"], words=(a.get("words") or []) + (b.get("words") or []), text=a["text"].rstrip() + " " + b["text"].lstrip())
        parts = lambda sc: {k: len(v[1]["marks"]) for k, v in DG.evidence(sc, sc["text"]).items()}
        whole, pa, pb = parts(m), parts(a), parts(b); gain = [k for k, v in whole.items() if v > max(pa.get(k, 0), pb.get(k, 0))]
        if not gain: i += 1; continue
        for k, v in b.items():
            if isinstance(v, list) and k != "words" and isinstance(a.get(k), list): m[k] = a[k] + v
        m["decisions"] = list(a["decisions"]) + [f"variety: joined with the next clause so the {gain[0]} diagram shows the whole sentence"]
        scenes[i:i + 2] = [m]; n += 1
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

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
            t = float(ws[k]["t0"]); is_q = bool(QA.MARK_RX.match(" ".join(w["w"] for w in ws[k:k + 6])))      # a viewer question starts its own scene (first render: "Question one" was joined into the road scene)
            if min(t - sc["start"], sc["end"] - t) < (Q_SPLIT_MIN_S if is_q else SPLIT_MIN_S): continue
            if is_q: cut = t; break
            head = {"start": sc["start"], "words": ws[:k]}; tail = {"start": t, "words": ws[k:]}; tx = sc["text"].split(); text_h, text_t = (" ".join(tx[:k]), " ".join(tx[k:])) if len(tx) == len(ws) else (" ".join(w["w"] + w.get("p", "") for w in ws[:k]), " ".join(w["w"] + w.get("p", "") for w in ws[k:]))
            ev_t = {l: v for l, v in evidence(dict(sc, **tail, text=text_t, pages=[])).items() if l in SPLIT_LOOKS and v[0] >= SPLIT_CARD}
            ev_h = {l for l, v in evidence(dict(sc, **head, text=text_h, end=t)).items() if l in SPLIT_LOOKS and v[0] >= SPLIT_CARD}
            if ev_t and not (set(ev_t) <= ev_h): cut = t; break      # the later sentence brings a card the earlier part cannot show
        if cut is None: i += 1; continue
        a, b = _cut(sc, cut); scenes[i:i + 1] = [a, b]; n += 1; i += 1
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

def results_on_stats(scenes: List[dict]) -> int:
    """After every cut: a picture or plain-figure shot whose own words say a measured result ("dropped by about 60%", "a 54% increase") within RESULT_LATE_S of
    its start shows it as the stat ring (a picture cut at a clause after the looks were chosen could still hold it). The hook picture and CSV looks stay. Returns how many."""
    n = 0
    for i, sc in enumerate(scenes):
        if sc.get("hook") or sc.get("directed_look") or (sc.get("look") or sc["kind"]) not in ("flow", "stock", "trainee", "callout") or sc["kind"] not in UPGRADABLE: continue
        text = sc.get("text", ""); rn = result_number(text)
        if not rn or rn["unit"] != "%" or not CHANGE_RX.search(text[max(0, rn["pos"] - 28):rn["pos"] + len(rn["text"]) + 22]): continue
        st = _stat(sc, text)
        if not st or st["at"] - float(sc["start"]) > RESULT_LATE_S or sc["end"] - st["at"] < 1.2: continue
        for k in ("flow_prompt", "reuses_picture", "want3d", "cam3d"): sc.pop(k, None)
        sc["stat"] = st; sc["was_kind"] = sc["kind"]; sc["kind"] = "stat"; sc["look"] = "stat"
        for pg in sc.get("pages", []): pg["value"] = ""
        sc["decisions"].append(f"variety: measured result {st['value']:g}{st['unit']} shown as the stat ring"); n += 1
    return n

def split_for_numbers(scenes: List[dict]) -> int:
    """A long text / figure scene whose result number ("dropped by about 60%") is said late is cut where the clause holding that number starts, so the number gets
    its own stat card when it is said instead of a card that would open empty (or none at all). Returns how many cuts were made."""
    n = 0; i = 0
    while i < len(scenes):
        sc = scenes[i]; ws = sc.get("words") or []; text = sc.get("text", "")
        num = result_number(text) if sc["kind"] in UPGRADABLE and not sc.get("directed_look") and len(ws) >= 8 and sc["end"] - sc["start"] >= 2 * SPLIT_MIN_S else None
        if not num or num["unit"] != "%" or not CHANGE_RX.search(text[max(0, num["pos"] - 28):num["pos"] + len(num["text"]) + 22]): i += 1; continue      # a measured % result only: "170 cm and 70 kg" is a measurement (tricks.measure), not a result
        k_num = min(len(text[:num["pos"]].split()), len(ws) - 1); k = k_num
        while k > 0 and not re.search(r"[,.;:!?]", ws[k - 1].get("p", "")): k -= 1      # back to the start of the number's clause
        clean = lambda c: N._nw(ws[c - 1]["w"]) not in N.STOP and not LX.num(N._nw(ws[c - 1]["w"])).isdigit() and not LX.num(N._nw(ws[c]["w"])).isdigit() and N._nw(ws[c]["w"]) not in ("half", "quarter", "percent")      # never inside "five and a | half hours"
        cands = [c for c in [k] + list(range(k_num - 1, k_num - 7, -1)) if 1 <= c < len(ws) and (c == k or clean(c))]      # the clause start, else the nearest clean word boundary before the number
        t = next((float(ws[c]["t0"]) for c in cands if float(ws[c]["t0"]) - sc["start"] >= SPLIT_MIN_S and sc["end"] - float(ws[c]["t0"]) >= SPLIT_MIN_S and float(ws[k_num]["t0"]) - float(ws[c]["t0"]) <= LATE_CARD_S), None)
        if t is None or float(ws[k_num]["t0"]) - sc["start"] <= LATE_CARD_S: i += 1; continue      # the number is said early already: no cut needed
        a, b = _cut(sc, t); scenes[i:i + 1] = [a, b]; b["decisions"] = list(b.get("decisions", [])) + ["variety: cut where its number is said (stat card on the number)"]; n += 1; i += 2
    for k, sc in enumerate(scenes): sc["no"] = k + 1 if scenes and scenes[0].get("no", 1) == 1 else k
    return n

PLATE_GAP_S = 120.0      # was 30 s: one plate every half minute still filled a 15-minute video with the same forearm
PLATE_PARTS = {"anat_forearm_v1": re.compile(r"\b(forearms?|wrists?|hands?|fingers?|grip|palms?|flexors?|pulleys?)\b", re.I)}      # a plate shows only the part it is a picture of      # an anatomy plate shown in the last 30 s is not shown again as it was: the scene gets a new look (render 053: one forearm plate filled 36% of the video)
TEXT_LOOKS = {"stock", "takeaway", "figure", "callout", "stat"}      # an opening shown as words or a ring: replaced by the hook picture
RECENT_W = 0.25      # per recent video that had this look at this place in its opening (channel memory, Rule 3)
JITTER = 0.5      # how far a script's own seed moves a look's score: enough to change close calls, never to pick a look the words do not support

def direct(scenes: List[dict], *, total_s: Optional[float] = None, three_d: bool = True, flow: bool = True, budget: Optional[dict] = None, roles: Optional[Dict[int, str]] = None, history: Optional[List[str]] = None, recent: Optional[List[List[str]]] = None) -> dict:
    """Assigns `look` to every scene (and the payload of a card look, `want3d` + `cam3d` for a 3D clip, `chapter_card` for a new part). Returns the summary."""
    join_for_diagrams(scenes); join_short(scenes); bands_across(scenes); split = split_for_cards(scenes) + split_long(scenes) + split_for_numbers(scenes); absorb_slot_items(scenes)
    total = float(total_s or (scenes[-1]["end"] if scenes else 0)); b = budget or {}; gap3 = b.get("three_d_gap_s", min(20.0, max(6.0, total / 4))); max_flow = b.get("max_flow") or 10 ** 9      # no picture limit unless a caller sets one
    plate_seen: Dict[str, float] = {}; keyline_parts: set = set()      # chapters that already had their one key-line card
    hist: List[str] = list(history or []); last3 = -1e9; flows = 0; style_i = 0; roles = roles or {}; n0 = len(hist)
    import zlib; seed = zlib.crc32(" ".join(sc.get("text", "") for sc in scenes).encode())      # each script its own mix (same script, same video)
    jit = lambda i, look: ((zlib.crc32(f"{seed}:{i}:{look}".encode()) % 1000) / 1000 - 0.5) * JITTER
    for i, sc in enumerate(scenes):
        k = sc["kind"]
        if i == 0 and flow and not (sc.get("directed_look") and sc.get("look") in ("flow", "3d")) and k not in ("tier", "equation") and not SYNTH_RX.search(sc.get("text", "")):      # the opening is the hook picture, never words (a CSV text look on row 1 included)
            if sc.get("directed_look"): sc["decisions"].append(f"opening: CSV look {sc.get('look')} replaced by the hook picture")
            sc["directed_look"] = True; sc["look"] = "flow"; sc["hook"] = True; sc.pop("look_payload", None); flows += 1; hist.append("flow"); sc["decisions"].append("variety: the opening is the hook picture"); continue
        if sc.get("directed_look"):      # the scenes CSV chose this scene's look (reptheory/direction.py): it is used as asked and counts toward the spacing of the others
            look = sc["look"]; hist.append(look)
            if look == "3d": sc["want3d"] = True; sc["cam3d"] = C3.STYLES[style_i % len(C3.STYLES)]; style_i += 1; last3 = sc["end"]
            elif look == "flow": flows += 1
            else:
                from .direction import build_card
                build_card(sc)
            continue
        off_part = k == "anatomy" and sc.get("art") in PLATE_PARTS and not PLATE_PARTS[sc["art"]].search(sc.get("text", ""))      # the forearm plate on a line about knees, the waist or the comments (tendon video: 16 times, 102 s)
        stale = k == "anatomy" and sc.get("art") and (off_part or sc["start"] - plate_seen.get(sc["art"], -1e9) < PLATE_GAP_S)
        if k == "anatomy" and sc.get("art") and not stale: plate_seen[sc["art"]] = sc["end"]
        free = (k in UPGRADABLE or stale) and not (k == "trainee" and sc.get("art") not in ("", None, "rep_stand_v1")) and not SYNTH_RX.search(sc.get("text", ""))
        if not free: hist.append(k); sc["look"] = k; continue
        ev = evidence(sc, last=i == len(scenes) - 1, role=roles.get(i, ""))
        if sc.get("slot_names") and "slots" in ev: ev = {"slots": ev["slots"]}      # the item names were joined in to be shown on the count card: nothing else shows them
        if not three_d or sc["start"] - last3 < gap3 or hist[-1:] == ["3d"]: ev.pop("3d", None)
        if not flow or flows >= max_flow: ev.pop("flow", None)
        elif "flow" in ev and (i == 0 or roles.get(i, "") not in ("claim", "hook") or sc.get("section") in keyline_parts or not 3 <= len(sc.get("words") or []) <= 10 or sc["end"] - sc["start"] > 4.0):      # with pictures on, words alone
            ev.pop("takeaway", None)      # only as one short key line a chapter (never the opening, never long enough to sit still); without Flow the takeaway card stays as it was
        ev["stock"] = (0.1 if stale else 0.75 if k == "trainee" and sc.get("glows") else 0.3, None); scored = []
        if _elder() and "flow" in ev: ev.pop("stock")      # Elder: the plain figure never takes a scene a picture can show (its novelty bonus beat the picture)
        if any(lk in DG.KINDS and len((v[1] or {}).get("marks", [])) >= 3 for lk, v in ev.items()): ev.pop("stock", None)      # a sentence that acts out a whole diagram (3+ parts) never shows the plain figure instead (1-minute render: the plan clipboard lost to the figure with "wrist" lit)
        part = section_kind(sc)
        if part:      # the part of the video decides what kind of graphic suits it (docs/rep_theory/HOW_THE_CHANNEL_EDITS.md section 2): a small nudge, never a ban
            for lk, b in SECTION_BOOST[part].items():
                if lk in ev: ev[lk] = (ev[lk][0] + b, ev[lk][1])
            sc["section_kind"] = part      # the figure with the named part lit already shows the words; a plate just seen is the last resort
        if stale: sc["decisions"].append(f"anatomy plate {sc['art']} " + ("does not show what this line names" if off_part else f"was on screen in the last {PLATE_GAP_S:.0f} s") + ": a new look")
        for look, (base, payload) in ev.items():
            if look == "flow":      # a new picture each time, so a run of them is allowed, but it is one look in the rotation: a pose for the action, the figure with the part lit,
                # the plate and the cards still win where the words support them and were not just used (render final 2 lost them all to pictures)
                score = base + (0.3 if "flow" not in hist[-2:] else 0.05) - (0.25 if hist[-3:] == ["flow"] * 3 else 0.0) + jit(i, look)
                if _elder() and hist[-2:] != ["flow", "flow"]: score += ELDER_FLOW_BOOST      # Elder: pictures carry the video, a card only after two pictures (1-minute render 2026-11-11: 2 pictures in 14 scenes)
                scored.append((score, -list(ev).index(look), look, payload)); continue
            if hist[-2:] == [look, look] or (look == "sketch" and hist[-1:] == ["sketch"]): continue      # never a third in a row; a line figure never twice running
            score = base + (0.5 if look not in hist[-3:] else 0.0) + (0.2 if look not in hist[-6:] else 0.0) - (0.8 if hist[-1:] == [look] else 0.0) + jit(i, look) - RECENT_W * sum(1 for op in (recent or []) if i < len(op) and op[i] == look); scored.append((score, -list(ev).index(look), look, payload))
        if not scored: scored = [(0, 0, "stock", None)]
        _, _, look, payload = max(scored); sc["look"] = look; hist.append(look)
        if look == "3d": sc["want3d"] = True; sc["cam3d"] = C3.STYLES[style_i % len(C3.STYLES)]; style_i += 1; last3 = sc["end"]; sc["decisions"].append("variety: 3D body clip")
        elif look == "flow":
            flows += 1; nb = _neighbour_picture(scenes, i)
            if nb: sc["flow_prompt"] = nb["flow_prompt"]; sc["reuses_picture"] = nb["no"]; sc["decisions"].append(f"variety: a vague line keeps the picture of scene {nb['no']}, re-framed (no new picture drawn from it)")
            else: sc["decisions"].append("variety: Flow picture from the narration")
        elif look == "pose":
            pp = payload; sc["was_kind"] = k; sc["kind"] = "pose"; sc["art"] = pp["art"]; sc["glows"] = pp["glows"]; sc.pop("morph", None); sc.pop("beam", None); sc["decisions"].append(f"variety: pose {pp['art']}")
        elif look == "sketch": sc["was_kind"] = k; sc["kind"] = "sketch"; sc["sketch"] = payload; sc["art"] = ""; sc["decisions"].append(f"variety: line figure doing it ({payload['move']} {payload.get('variant', '')})".rstrip())
        elif look == "equation": sc["was_kind"] = k; sc["kind"] = "equation"; sc["art"] = "rep_stand_v1"; sc["equations"] = payload; sc["decisions"].append(f"variety: equation lockup {payload[0]['lhs']} = {payload[0]['rhs']}")
        elif look in CARD_LOOKS:
            sc[look] = payload; sc["was_kind"] = k; sc["kind"] = look; sc["decisions"].append(f"variety: {look} card ({k} -> {look})")
            if look in ("stat", "bars") + HE.NUMBER_KINDS:
                for pg in sc["pages"]: pg["value"] = ""      # the ring / health card shows the number: the callout column does not repeat it
            if look in FULL_CARDS: sc["pages"] = []      # the card fills the frame (a caption strip follows the narration: states.develop)
            if look == "takeaway": keyline_parts.add(sc.get("section"))
        elif stale and k == "anatomy": sc["was_kind"] = k; sc["kind"] = "trainee"; sc["art"] = "rep_stand_v1"; sc["look"] = "trainee"; hist[-1] = "trainee"; sc["decisions"].append("variety: the figure with the part lit instead of the plate")      # the plate is what had to go
        else: sc["decisions"].append("variety: stock look kept")
    fill_slots(scenes); let_cards_finish(scenes); reframe_long(scenes); results_on_stats(scenes)
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
