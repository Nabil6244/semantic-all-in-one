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
# part -> (words that name it, label, ellipses (cx, cy, w, h) as fractions of the FULL standing-figure picture: front view, arms down; scenes.py maps them onto the cut-out it draws)
BODY: Dict[str, tuple] = {
    "neck": (r"neck", "NECK", ((0.500, 0.225, 0.030, 0.050),)),
    "shoulders": (r"shoulders?|delts?|deltoids?|traps?|trapezius", "SHOULDERS", ((0.442, 0.290, 0.050, 0.070), (0.558, 0.290, 0.050, 0.070))),
    "chest": (r"chest|pecs?|pectorals?", "CHEST", ((0.500, 0.335, 0.090, 0.075),)),
    "heart": (r"heart|blood pressure", "HEART", ((0.522, 0.330, 0.035, 0.050),)),
    "lungs": (r"lungs?|breath(?:e|ing)?", "LUNGS", ((0.475, 0.335, 0.035, 0.070), (0.525, 0.335, 0.035, 0.070))),
    "arms": (r"arms?|biceps?|triceps?|elbows?", "ARMS", ((0.438, 0.400, 0.024, 0.105), (0.566, 0.400, 0.024, 0.105))),
    "forearms": (r"forearms?|wrists?|grip", "FOREARMS", ((0.428, 0.525, 0.020, 0.100), (0.572, 0.525, 0.020, 0.100))),
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
NOT_A_PART = re.compile(r"\b(?:back (?:to|down|up|in|out|off|on|into|and)|(?:come|go|get|bring|lie on your|on your) back|set ?back|back then|hands?[- ]on|hand dynamometer|arms? race|arm[- ]?wrestl\w*|mind(?:set|ful))\b", re.I)      # "arm wrestling" names a sport, not the arm (render 053: ARMS lit on every arm-wrestling line)
DANGER_RX = re.compile(r"\b(?:mistakes?|wrong|danger\w*|risk\w*|injur\w*|pain\w*|hurts?|quit\w*|fail\w*|warning|stop(?:\s+(?:if|when|immediately|right away|straight away|at once|before)\b|\s+(?:doing|training|the (?:exercise|set|movement))\b)|never|on fire|damage\w*|worse)\b", re.I)
ICE_RX = re.compile(r"\b(?:relax\w*|rest(?:s|ing)?|cool\w*|calm\w*|loosen\w*|release[sd]?|switch(?:es|ed)? off|recover\w*)\b", re.I)
FIRE_RX = re.compile(r"\b(?:burn\w*|on fire|fir(?:e|es|ing)|pump\w*|shak\w*|squeez\w*|work(?:s|ing)? hard|all out|max(?:imum)? effort)\b", re.I)
SIGNAL_RX = re.compile(r"\b(?:signals?|tells?|sends?|fires?|commands?|wakes? up|switch(?:es)? on|recruits?|drives?|reach(?:es)?|travels? (?:to|through|into|down)|gets? (?:it |the force )?(?:there|to|into)|passes? (?:to|through)|carr(?:y|ies) (?:it|the force) to)\b", re.I)      # a signal or a force going from one part to another (render 053: 0 beams in 14 scripts with the old list)
GAIN_RX = re.compile(r"\b(?:gain(?:s|ed|ing)? (?:weight|muscle|size|mass|\w+ (?:of )?muscle)|bulk(?:s|ing|ed)?|put(?:s|ting)? on (?:weight|muscle|size)|get(?:s|ting)? bigger|grow(?:s|ing)? bigger|fill(?:s|ing)? out|build(?:s|ing)? muscle)\b", re.I)
LEAN_RX = re.compile(r"\b(?:los(?:e|es|ing) (?:weight|fat|belly fat|\w+ of fat)|lean(?:s|ing)? out|burn(?:s|ing)? fat|slim(?:s|ming)? down|smaller waist|waist (?:looks? )?smaller)\b", re.I)
GAIN_TO, LEAN_TO = 0.16, -0.10
NEG_RX = re.compile(r"\b(?:not|no|never|isn'?t|aren'?t|won'?t|can'?t|cannot|don'?t|doesn'?t|without)\b", re.I)      # how much wider the shoulders get / narrower the waist gets
TONES = {"ice": (90, 190, 255), "fire": (232, 64, 52)}      # a relaxed part turns icy blue, a part working hard red; otherwise the orange highlight
GLOW_MAX = 3      # parts lit in one scene, in the order they are said

def _norm(w: str) -> str: return re.sub(r"[^a-z0-9'-]", "", w.lower())

def parts_named_words(words: List[dict], text: str) -> List[tuple]:
    """[(part, time of its word, the word as said, upper-case)] in the order said; a phrase that only looks like a part ("come back", "hands-on", "arm wrestling") is ignored."""
    clean = NOT_A_PART.sub(" ", text); out: List[tuple] = []; seen = set()
    for part, rx in BODY_RX.items():
        m = rx.search(clean)
        if not m: continue
        w = next((w for w in words if rx.fullmatch(_norm(w["w"]).strip("'-"))), None); said = _norm(w["w"]).strip("'-") if w is not None else ""
        if w is None and len(text.split()) == len(words):      # a part named in two words ("nervous system", "hip flexors"): the word its match starts on
            w = words[min(len(words) - 1, len(text[:m.start()].split()))]; said = m.group(0)
        if w is not None and part not in seen: out.append((part, float(w["t0"]), (said or m.group(0)).upper())); seen.add(part)
    return sorted(out, key=lambda x: x[1])[:GLOW_MAX]

def parts_named(words: List[dict], text: str) -> List[tuple]:
    """[(part, time of its word)] in the order said (see parts_named_words)."""
    return [(p, t) for p, t, _w in parts_named_words(words, text)]

def _tone(text: str, t: float, ws: List[dict]) -> str:
    """The state a named part is in, from the clause it is named in: icy when it relaxes or rests, red when it burns or works hard."""
    i = next((k for k, w in enumerate(ws) if float(w["t0"]) >= t - 1e-6), 0); a = i
    while a > 0 and not re.search(r"[,.;:!?]", ws[a - 1].get("p", "")): a -= 1
    b = i
    while b < len(ws) - 1 and not re.search(r"[,.;:!?]", ws[b].get("p", "")): b += 1
    clause = " ".join(w["w"] for w in ws[a:b + 1]) if ws else text
    return "ice" if ICE_RX.search(clause) else "fire" if FIRE_RX.search(clause) else ""

def _beam(ws: List[dict], text: str) -> Optional[dict]:
    """A signal or force that travels between two parts the sentence names ("your brain tells your legs to stop", "their force reaches your fingers through tendons"): from the brain
    when it is named, else from the first part named, to the next different part; on the later of the two words. None without a travel word or two parts."""
    if not SIGNAL_RX.search(text): return None
    named = parts_named(ws, text); src = next(((p, t) for p, t in named if p == "brain"), named[0] if named else None)
    dst = next(((p, t) for p, t in named if src and p != src[0] and t >= src[1] - 1e-6), None) or next(((p, t) for p, t in named if src and p != src[0]), None)
    if not (src and dst): return None
    return {"from": BODY[src[0]][2][0][:2], "to": BODY[dst[0]][2][0][:2], "at": max(src[1], dst[1]), "parts": [src[0], dst[0]]}

def apply(scenes: List[dict], art_ok: Callable[[str], bool], log: Callable[[str], None] = lambda m: None) -> Dict[str, int]:
    """Puts the state tracks on the scenes (in place). Returns counts."""
    n = {"body_glows": 0, "figure_added": 0, "tints": 0}
    from . import poses as PZ
    for sc in scenes:
        ws = sc.get("words") or []; text = sc.get("text", "")
        pk = PZ.pick(text, art_ok) if sc["kind"] in ("trainee", "callout") and not sc.get("directed_look") and sc.get("art") in ("", None, FIGURE) and not GAIN_RX.search(text) and not LEAN_RX.search(text) else None
        if pk:      # the sentence names an action the pose library shows (Step 5): offered to the variety director as a look (variety.evidence "pose"), with the named part lit on that pose
            pid, pos = pk; n["poses"] = n.get("poses", 0) + 1; i = len(text[:pos].split())
            lit = [(p, t, w) for p, t, w in parts_named_words(ws, text) if PZ.regions(pid, p)]
            sc["pose_pick"] = {"art": pid, "at": float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"]), "glows": [{"regions": PZ.regions(pid, p), "at": t, "label": BODY[p][1], "word": w, "body": True, "tone": _tone(text, t, ws)} for p, t, w in lit]}
        if sc["kind"] in ("trainee", "callout") and not sc.get("directed_look") and art_ok(FIGURE) and (sc["kind"] == "callout" or sc.get("art") == FIGURE):
            named_w = parts_named_words(ws, text); named = [(p, t) for p, t, _w in named_w]
            if named:
                if sc["kind"] == "callout": sc.update(kind="trainee", art=FIGURE); n["figure_added"] += 1; sc["decisions"].append("names a body part: the figure, with it lit")
                sc["glows"] = [{"regions": BODY[p][2], "at": t, "label": BODY[p][1], "word": w, "body": True, "tone": _tone(text, t, ws)} for p, t, w in named_w]; n["body_glows"] += len(named)      # word: the part as said (FOREARM, BICEP), shown on pictures

        bm = _beam(ws, text)
        if bm and sc["kind"] not in ("tier", "equation"): sc["beam"] = bm; n["beams"] = n.get("beams", 0) + 1      # on any scene: the figure draws it, a picture draws it between the parts it shows
        g = next((m for rx in (GAIN_RX, LEAN_RX) for m in rx.finditer(text) if not NEG_RX.search(re.split(r"[,.;:!?]", text[:m.start()])[-1])), None)      # "the gym isn't where you build muscle" changes nothing
        if g and not sc.get("directed_look") and art_ok(FIGURE) and (sc["kind"] == "callout" or (sc["kind"] == "trainee" and sc.get("art") == FIGURE)):      # the body changes on the word: the same figure gains or leans out
            if sc["kind"] == "callout": sc.update(kind="trainee", art=FIGURE); n["figure_added"] += 1
            i = len(text[:g.start()].split()); sc["morph"] = {"to": GAIN_TO if GAIN_RX.search(g.group(0)) else LEAN_TO, "at": float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"]) + 0.3}
            n["morphs"] = n.get("morphs", 0) + 1; sc["decisions"].append(f"body {'gains' if sc['morph']['to'] > 0 else 'leans out'} on '{g.group(0)}'")
        m = DANGER_RX.search(text)
        if m and sc["kind"] not in ("tier", "equation"):
            at = next((float(w["t0"]) for w in ws if DANGER_RX.fullmatch(_norm(w["w"]).strip("'-"))), float(sc["start"]) + 0.3)
            sc["tint"] = {"at": max(float(sc["start"]), at)}; n["tints"] += 1
    return n

# ---------------------------------------------------------------- cadence (Step 3)
FILL_GAP_S, EDGE_S = 3.0, 0.6      # a scene never goes this long without something new; a new phrase never lands this close to the change before or after it
PAGE_KINDS = {"callout", "trainee", "pose", "prop", "hold", "sketch", "illus", "stat", "clip3d", "versus", "steps", "timeline", "mistake", "slider", "dial", "study", "graph", "bars", "calendar", "result", "warning", "engage", "myth", "question", "checklist", "slots", "race", "formula", "mechanism", "promise", "tokens", "share", "lever", "seesaw", "gap", "split", "panels", "tearoff", "battery", "clipboard", "road"}      # versus / steps show a page as a caption strip under the card      # kinds whose callout column shows a page's headline

def _clauses(ws: List[dict]) -> List[List[dict]]:
    out, cur = [], []
    for w in ws:
        cur.append(w)
        if re.search(r"[,.;:?!]", w.get("p", "")): out.append(cur); cur = []
    return out + ([cur] if cur else [])

JOINS = {"and", "but", "because", "while", "so", "or", "until", "unless"}

def _parts(ws: List[dict]) -> List[List[dict]]:
    """The clauses, and for a long one (9+ words) also its parts after a joining word ("... at breakfast | and trying to make it all up at night"), the joining word dropped."""
    from . import narrative as N
    out = []
    for cl in _clauses(ws):
        out.append(cl)
        if len(cl) < 9: continue
        cuts = [i for i in range(3, len(cl) - 2) if N._nw(cl[i]["w"]) in JOINS]
        for a, b in zip([0] + cuts, cuts + [len(cl)]):
            part = cl[a + (1 if a else 0):b]
            if len(part) >= 3 and part != cl: out.append(part)
    return out

def _tail(cl: List[dict], n: int = 4) -> str:
    """The clause's own ending, from its first content word ("TRAINING IS WASTED"): what a long clause comes to."""
    from . import narrative as N
    a = max(0, len(cl) - n)
    while a < len(cl) and N._nw(cl[a]["w"]) in N.DANGLING: a += 1
    return N._shown(cl, a, len(cl)) if len(cl) - a >= 2 else ""

STAMP_GAP_S, STAMP_HOLD_S = 20.0, 2.4      # the reference stamps about once a minute; never two within 20 s
NO_STAMP = {"takeaway", "tier", "equation", "engage", "slots", "race", "formula", "mechanism", "promise", "checklist", "steps", "versus", "mistake", "myth", "question", "timeline", "calendar", "result", "warning"}      # a card that spells its own words out: a stamp on top would cover it (final 3: "THE WRIST" over the four moments)
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

CLOCK_START = re.compile(r"\b(?:hold (?:it|that|this|them) (?:there|still|as long as you can)|as long as you can|start (?:the|a|your) (?:clock|timer|stopwatch)|time (?:how long|yourself)|hold for (?:\w+ )?seconds)\b", re.I)
CLOCK_STOP = re.compile(r"\bstop (?:the|your) (?:clock|timer|stopwatch)\b", re.I)
TARGET_RX = re.compile(r"\b(?:for|hold(?: it)?(?: for)?|aim for|reach|up to)\s+(\d+|ten|fifteen|twenty|thirty|forty|forty-five|sixty)\s*(?:seconds?|secs?|s)\b", re.I)
_SECW = {"ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "sixty": 60}
def _secs(w: str) -> int: return int(w) if w.isdigit() else _SECW.get(w.lower(), 0)
CLOCK_MAX_S = 40.0      # a stopwatch with no "stop the clock" runs at most this long

def _word_time(sc: dict, pos: int) -> float:
    ws = sc.get("words") or []; i = len(sc.get("text", "")[:pos].split())
    return float(ws[min(i, len(ws) - 1)]["t0"]) if ws else float(sc["start"])

def stopwatch(scenes: List[dict]) -> int:
    """A timed hold the viewer does ("hold it there ... the moment your knuckles drop, stop the clock"): a stopwatch top right from the start words, counting real seconds,
    frozen red on "stop the clock" (the reference runs one through every test). Every scene in between carries it. Returns how many stopwatches were started."""
    n = 0; i = 0
    while i < len(scenes):
        m = CLOCK_START.search(scenes[i].get("text", ""))
        if not m: i += 1; continue
        t0 = _word_time(scenes[i], m.start()); t1 = None
        for sc in scenes[i:]:
            if sc["start"] > t0 + CLOCK_MAX_S: break
            ms = CLOCK_STOP.search(sc.get("text", ""))
            if ms and _word_time(sc, ms.start()) > t0: t1 = _word_time(sc, ms.start()); break
        end = (t1 + 1.6) if t1 else t0 + min(CLOCK_MAX_S, 12.0); k = i
        tm = TARGET_RX.search(" ".join(x.get("text", "") for x in scenes[max(0, i - 1):i + 2])); target = _secs(tm.group(1)) if tm else 0      # the hold's stated target ("hold for 30 seconds")
        while k < len(scenes) and scenes[k]["start"] < end: scenes[k]["stopwatch"] = {"start": t0, "stop": t1, "end": end, "target": target}; k += 1
        n += 1; i = k
    return n

IMPERATIVE = set("rest hold curl sit stand pull push squeeze keep lift drop grab grip loop place put lean press brace breathe face turn lower raise bend straighten tuck fill add try start stop count repeat do take walk run".split())
KICK_RX = (("TEST", re.compile(r"\b(?:a (?:quick )?test|try (?:it|this)|test yourself|time yourself)\b", re.I)), ("MISTAKE", re.compile(r"\b(?:mistakes?|wrong)\b|^\W*(?:never|don'?t|do not)\b", re.I)),      # "Don't lock your elbows" is a mistake; "the muscles don't sit in your hand" is not
           ("STUDY", re.compile(r"\b(?:study|studies|researchers?|scientists?|trial|review)\b", re.I)))

def picture_text(scenes: List[dict]) -> Dict[str, int]:
    """The words beside a picture say what kind of line it is: a small kicker from the sentence's shape when its pages have none (an instruction -> CUE, a try-it -> TEST,
    a mistake / never / don't -> MISTAKE, research -> STUDY, a stated number -> KEY), and the number with its unit as the page's big value when the headline does not already
    carry it and no number card shows it. Picture scenes only (kind illus or look flow); run after the pages are final. Returns counts."""
    from . import narrative as N
    n = {"kickers": 0, "values": 0}
    for sc in scenes:
        if not (sc["kind"] == "illus" or sc.get("look") == "flow") or not sc.get("pages"): continue
        text = sc.get("script_text") or sc.get("text", ""); ws = text.split(); first = next((N._nw(w) for w in ws if N._nw(w) not in ("now", "then", "so", "and", "next", "just", "first")), "")
        nums = N.entities(text)["numbers"] if sc["kind"] not in ("stat", "dial", "study", "bars") else []
        kick = next((k for k, rx in KICK_RX if rx.search(text)), "") or ("CUE" if first in IMPERATIVE else "") or ("KEY" if nums else "")
        for pg in sc["pages"]:
            if kick and not pg.get("kicker") and (pg.get("headline") or pg.get("value")): pg["kicker"] = kick; n["kickers"] += 1      # never a kicker over nothing
        if nums and not any(pg.get("value") for pg in sc["pages"]):
            e = nums[0]; v = e["value"]; v = (f"{float(v):g}" if not isinstance(v, str) else v); val = f"{v}%" if e["unit"] == "%" else f"{v} {e['unit']}"
            sw = sc.get("words") or []; i = len(text[:e["pos"]].split()); at = float(sw[min(i, len(sw) - 1)]["t0"]) if sw else float(sc["start"])
            pg = ([p for p in sc["pages"] if float(p.get("at", sc["start"])) <= at + 1e-6] or sc["pages"])[-1]
            if v not in (pg.get("headline") or "") and e["text"].upper() not in (pg.get("headline") or "").upper(): pg["value"] = val; pg["value_at"] = at; n["values"] += 1
    return n

def develop(scenes: List[dict]) -> int:
    """Run after the looks are chosen. Where a scene would hold more than FILL_GAP_S with nothing new, the clause said in that gap arrives as a new page
    (its own words, a phrase of the script: narrative.phrase rules) at its first word. Returns how many were added."""
    from . import cadence as C, narrative as N
    stamps(scenes); stopwatch(scenes); added = 0
    for i, sc in enumerate(scenes):
        kind = "illus" if sc.get("look") == "flow" else sc["kind"]      # a scene the director gave a Flow picture shows its words beside that picture, whatever it was planned as
        if kind not in PAGE_KINDS or (not sc.get("pages") and kind not in ("versus", "steps", "timeline", "mistake", "slider", "calendar", "result", "warning", "engage", "myth", "question", "checklist", "slots", "race", "formula", "mechanism", "promise")): continue
        sc.setdefault("pages", [])
        ws = sc.get("words") or []; shown = {pg["headline"] for x in scenes[max(0, i - 2):i + 1] for pg in x.get("pages", [])}      # never a headline seen in this scene or the two before
        for _ in range(8):
            ev = sorted({float(sc["start"]), float(sc["end"])} | {e["t"] for e in C.events([dict(sc, no=0)]) if e["meaningful"] and sc["start"] <= e["t"] <= sc["end"]})
            gaps = [(a, b) for a, b in zip(ev, ev[1:]) if b - a > FILL_GAP_S]
            pick = None
            for a, b in gaps:
                for cl in _parts(ws):
                    if float(cl[-1]["t1"]) < a + EDGE_S or float(cl[0]["t0"]) > b - EDGE_S: continue
                    for head in (N.short_clause(cl), N.phrase(N.key_phrase(" ".join(w["w"] for w in cl))[0], cl), _tail(cl)):
                        if not head or head in shown or len(head.split()) < 2: continue
                        if not {N._nw(h) for h in head.split()} <= {N._nw(w["w"]) for w in cl}: continue      # every word shown is a whole word said ("5K" never becomes "K")
                        first = N._nw(head.split()[0]); t0 = next((float(w["t0"]) for w in cl if N._nw(w["w"]) == first), float(cl[0]["t0"]))      # it lands on its own first word
                        if a + EDGE_S <= t0 <= b - EDGE_S: pick = (abs(t0 - (a + b) / 2), t0, head); break
                    if pick: break
                if pick: break
            if not pick: break
            _d, t0, head = pick; shown.add(head); added += 1
            sc["pages"].append({"at": t0, "headline": head, "headline_at": t0, "value": "", "chips": [], "kicker": "", "src": "cadence"}); sc["pages"].sort(key=lambda p: p["at"])
            sc["decisions"].append(f"held {FILL_GAP_S:.0f} s with nothing new: '{head}' arrives at its word")
    picture_text(scenes)
    return added
