"""State changes on the picture already on screen (docs/rep_theory/UPGRADE_LIST.md section 5b): the picture stays, its state changes on the word.
Run once on the plan, after the planner and before the looks are chosen. Everything is read from each scene's own words, so any topic gets them:
  body glows   a body part the narration names lights up on the standing figure at its word (a text-only scene that names one gets the figure)
  tint         a warning, a mistake, pain or quitting warms the background red from its word to the end of the scene
The drawing side (scenes.py, cards.py, draw.py) also gives every stat a flip + pulse when its number lands, dims the earlier items of steps / versus,
sweeps a light across an anatomy plate as it is revealed, and swipes a marker behind a question headline."""
from __future__ import annotations
import re
from typing import Callable, Dict, List, Optional

FIGURE = "rep_stand_v1"
# part -> (words that name it, label, ellipses (cx, cy, w, h) as fractions of the standing-figure picture: front view, arms down)
BODY: Dict[str, tuple] = {
    "neck": (r"neck", "NECK", ((0.500, 0.225, 0.030, 0.050),)),
    "shoulders": (r"shoulders?|delts?|deltoids?|traps?|trapezius", "SHOULDERS", ((0.442, 0.290, 0.050, 0.070), (0.558, 0.290, 0.050, 0.070))),
    "chest": (r"chest|pecs?|pectorals?", "CHEST", ((0.500, 0.335, 0.090, 0.075),)),
    "heart": (r"heart|blood pressure", "HEART", ((0.522, 0.330, 0.035, 0.050),)),
    "lungs": (r"lungs?|breath(?:e|ing)?", "LUNGS", ((0.475, 0.335, 0.035, 0.070), (0.525, 0.335, 0.035, 0.070))),
    "arms": (r"arms?|biceps?|triceps?|elbows?", "ARMS", ((0.426, 0.400, 0.030, 0.105), (0.574, 0.400, 0.030, 0.105))),
    "forearms": (r"forearms?|wrists?|grip", "FOREARMS", ((0.414, 0.525, 0.026, 0.100), (0.586, 0.525, 0.026, 0.100))),
    "hands": (r"hands?|fingers?|thumbs?|palms?", "HANDS", ((0.409, 0.615, 0.030, 0.060), (0.591, 0.615, 0.030, 0.060))),
    "core": (r"core|abs|abdominals?|stomach|belly|waist|obliques?|six[- ]pack", "CORE", ((0.500, 0.420, 0.060, 0.090),)),
    "back": (r"back|lats?|latissimus|spine|spinal|shoulder blades?", "BACK", ((0.462, 0.370, 0.030, 0.090), (0.538, 0.370, 0.030, 0.090))),
    "hips": (r"hips?|hip flexors?|glutes?|pelvis", "HIPS", ((0.500, 0.480, 0.090, 0.050),)),
    "legs": (r"legs?|thighs?|quads?|quadriceps|hamstrings?", "LEGS", ((0.468, 0.630, 0.040, 0.150), (0.532, 0.630, 0.040, 0.150))),
    "knees": (r"knees?", "KNEES", ((0.466, 0.770, 0.030, 0.040), (0.534, 0.770, 0.030, 0.040))),
    "calves": (r"calf|calves|shins?|ankles?|achilles", "CALVES", ((0.466, 0.865, 0.026, 0.080), (0.534, 0.865, 0.026, 0.080))),
    "feet": (r"feet|foot|toes?|heels?", "FEET", ((0.464, 0.955, 0.034, 0.030), (0.536, 0.955, 0.034, 0.030))),
    "brain": (r"brain|nervous system|nerves?|mind", "BRAIN", ((0.500, 0.110, 0.050, 0.060),)),
}
BODY_RX = {k: re.compile(rf"\b(?:{v[0]})\b", re.I) for k, v in BODY.items()}
NOT_A_PART = re.compile(r"\b(?:back (?:to|down|up|in|out|off|on|into|and)|(?:come|go|get|bring|lie on your|on your) back|set ?back|back then|hands?[- ]on|hand dynamometer|arms? race|mind(?:set|ful))\b", re.I)
DANGER_RX = re.compile(r"\b(?:mistakes?|wrong|danger\w*|risk\w*|injur\w*|pain\w*|hurts?|quit\w*|fail\w*|warning|stop|never|on fire|damage\w*|worse)\b", re.I)
GLOW_MAX = 3      # parts lit in one scene, in the order they are said

def _norm(w: str) -> str: return re.sub(r"[^a-z0-9'-]", "", w.lower())

def parts_named(words: List[dict], text: str) -> List[tuple]:
    """[(part, time of its word)] in the order said; a phrase that only looks like a part ("come back", "hands-on") is ignored."""
    clean = NOT_A_PART.sub(" ", text); out: List[tuple] = []; seen = set()
    for part, rx in BODY_RX.items():
        if not rx.search(clean): continue
        w = next((w for w in words if rx.fullmatch(_norm(w["w"]).strip("'-"))), None)
        if w is not None and part not in seen: out.append((part, float(w["t0"]))); seen.add(part)
    return sorted(out, key=lambda x: x[1])[:GLOW_MAX]

def apply(scenes: List[dict], art_ok: Callable[[str], bool], log: Callable[[str], None] = lambda m: None) -> Dict[str, int]:
    """Puts the state tracks on the scenes (in place). Returns counts."""
    n = {"body_glows": 0, "figure_added": 0, "tints": 0}
    for sc in scenes:
        ws = sc.get("words") or []; text = sc.get("text", "")
        if sc["kind"] in ("trainee", "callout") and not sc.get("directed_look") and art_ok(FIGURE) and (sc["kind"] == "callout" or sc.get("art") == FIGURE):
            named = parts_named(ws, text)
            if named:
                if sc["kind"] == "callout": sc.update(kind="trainee", art=FIGURE); n["figure_added"] += 1; sc["decisions"].append("names a body part: the figure, with it lit")
                sc["glows"] = [{"regions": BODY[p][2], "at": t, "label": BODY[p][1], "body": True} for p, t in named]; n["body_glows"] += len(named)
        m = DANGER_RX.search(text)
        if m and sc["kind"] not in ("tier", "equation"):
            at = next((float(w["t0"]) for w in ws if DANGER_RX.fullmatch(_norm(w["w"]).strip("'-"))), float(sc["start"]) + 0.3)
            sc["tint"] = {"at": max(float(sc["start"]), at)}; n["tints"] += 1
    return n

# ---------------------------------------------------------------- cadence (Step 3)
FILL_GAP_S, EDGE_S = 3.0, 0.6      # a scene never goes this long without something new; a new phrase never lands this close to the change before or after it
PAGE_KINDS = {"callout", "trainee", "pose", "prop", "hold", "sketch", "illus", "stat", "clip3d", "versus", "steps", "timeline", "mistake", "slider", "dial", "study", "graph", "bars", "calendar", "result", "warning", "engage"}      # versus / steps show a page as a caption strip under the card      # kinds whose callout column shows a page's headline

def _clauses(ws: List[dict]) -> List[List[dict]]:
    out, cur = [], []
    for w in ws:
        cur.append(w)
        if re.search(r"[,.;:?!]", w.get("p", "")): out.append(cur); cur = []
    return out + ([cur] if cur else [])

def _tail(cl: List[dict], n: int = 4) -> str:
    """The clause's own ending, from its first content word ("TRAINING IS WASTED"): what a long clause comes to."""
    from . import narrative as N
    a = max(0, len(cl) - n)
    while a < len(cl) and N._nw(cl[a]["w"]) in N.DANGLING: a += 1
    return N._shown(cl, a, len(cl)) if len(cl) - a >= 2 else ""

STAMP_GAP_S, STAMP_HOLD_S = 20.0, 2.4      # the reference stamps about once a minute; never two within 20 s
NO_STAMP = {"takeaway", "tier", "equation", "engage"}
SIGNPOST = {"here", "heres", "here's", "let's", "lets", "first", "next", "now", "so", "then", "and", "but", "after", "before", "this", "that", "it", "its", "it's",
            "part", "step", "tip", "number", "week", "day", "phase", "level", "round", "second", "third", "fourth", "fifth", "last", "finally"}      # unit titles ("Part one, chin tucks.") are the chapter's job      # the words are already the picture, or the board is too busy

def stamps(scenes: List[dict]) -> int:
    """A short whole sentence said for emphasis (2 to 4 words: "That's normal.", "Every single day.") is stamped on the screen at its first word.
    Its own words, never a part of a longer sentence; red when it is a warning. At most one per scene and one every STAMP_GAP_S."""
    from . import narrative as N
    last = -1e9; n = 0
    for sc in scenes:
        if sc["kind"] in NO_STAMP: continue
        heads = {pg.get("headline") for pg in sc.get("pages", [])}; cur: List[dict] = []
        for w in sc.get("words") or []:
            cur.append(w)
            if not re.search(r"[.!?]", w.get("p", "")): continue
            sent, cur = cur, []
            if not 2 <= len(sent) <= 4 or "?" in sent[-1].get("p", "") or float(sent[0]["t0"]) - last < STAMP_GAP_S or float(sent[0]["t0"]) > sc["end"] - 1.0: continue
            txt = N._shown(sent, 0, len(sent)); first, end = N._nw(sent[0]["w"]), N._nw(sent[-1]["w"])
            if not txt or txt in heads or first in SIGNPOST or end in N.DANGLING: continue      # "Here are three." announces, "It is not." trails: neither is said for emphasis
            sc["stamp"] = {"text": txt, "at": float(sent[0]["t0"]), "red": bool(DANGER_RX.search(txt))}; last = sc["stamp"]["at"]; n += 1; sc["decisions"].append(f"stamp: '{txt}'"); break
    return n

def develop(scenes: List[dict]) -> int:
    """Run after the looks are chosen. Where a scene would hold more than FILL_GAP_S with nothing new, the clause said in that gap arrives as a new page
    (its own words, a phrase of the script: narrative.phrase rules) at its first word. Returns how many were added."""
    from . import cadence as C, narrative as N
    stamps(scenes); added = 0
    for i, sc in enumerate(scenes):
        if sc["kind"] not in PAGE_KINDS or (not sc.get("pages") and sc["kind"] not in ("versus", "steps", "timeline", "mistake", "slider", "calendar", "result", "warning", "engage")): continue
        sc.setdefault("pages", [])
        ws = sc.get("words") or []; shown = {pg["headline"] for x in scenes[max(0, i - 2):i + 1] for pg in x.get("pages", [])}      # never a headline seen in this scene or the two before
        for _ in range(8):
            ev = sorted({float(sc["start"]), float(sc["end"])} | {e["t"] for e in C.events([dict(sc, no=0)]) if e["meaningful"] and sc["start"] <= e["t"] <= sc["end"]})
            gaps = [(a, b) for a, b in zip(ev, ev[1:]) if b - a > FILL_GAP_S]
            pick = None
            for a, b in gaps:
                for cl in _clauses(ws):
                    if float(cl[-1]["t1"]) < a + EDGE_S or float(cl[0]["t0"]) > b - EDGE_S: continue
                    for head in (N.short_clause(cl), N.phrase(N.key_phrase(" ".join(w["w"] for w in cl))[0], cl), _tail(cl)):
                        if not head or head in shown or len(head.split()) < 2: continue
                        first = N._nw(head.split()[0]); t0 = next((float(w["t0"]) for w in cl if N._nw(w["w"]) == first), float(cl[0]["t0"]))      # it lands on its own first word
                        if a + EDGE_S <= t0 <= b - EDGE_S: pick = (abs(t0 - (a + b) / 2), t0, head); break
                    if pick: break
                if pick: break
            if not pick: break
            _d, t0, head = pick; shown.add(head); added += 1
            sc["pages"].append({"at": t0, "headline": head, "headline_at": t0, "value": "", "chips": [], "kicker": "", "src": "cadence"}); sc["pages"].sort(key=lambda p: p["at"])
            sc["decisions"].append(f"held {FILL_GAP_S:.0f} s with nothing new: '{head}' arrives at its word")
    return added
