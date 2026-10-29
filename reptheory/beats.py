"""Rep Theory R1 beat planner: narration -> beats -> compositions (scenes), with every choice recorded. Two levels:
  beat        = one spoken idea (a clause, a short sentence, or a whole atomic sentence such as an equation or a tier placement). Carries role, entities, timing source, the visual chosen and why.
  composition = consecutive beats that share one visual; becomes one scene dict for the existing renderer (primary development = a new composition, secondary = anything that develops inside it).
Rules: no spoken word is lost, reordered or added (checked); a visual is only called `grounded` when it comes from the beat's own words; when nothing fits the beat is reported as `continued`
(the previous composition simply goes on), `weak_callout` or `generic_fallback`, never counted as a relevant visual. Reuses the legacy detectors in planner._scene_of for the bottle / forearm /
hang / equation / tier treatments so those scenes stay as they were."""
from __future__ import annotations
import copy, re
from typing import Dict, List, Optional, Tuple

from . import cadence as C, lexicon as LX, library as L, narrative as N, planner as P

MIN_BEAT_S, SPLIT_MIN_S, MIN_CLAUSE_WORDS, MIN_CLAUSE_S = 1.8, 4.0, 3, 1.2
MERGE_MAX_S, COMP_MAX_S, DEVELOP_MAX_S = 9.0, 11.0, 14.0
ANATOMY_ART = "anat_forearm_v1"
FOCUS = {      # body part -> (label, glow ellipses (cx, cy, w, h) as fractions of the forearm plate). The plate is a generic forearm / hands illustration: parts other than the forearm are approximations
    "forearm": ("FOREARM", ((0.27, 0.26, 0.26, 0.42), (0.73, 0.26, 0.26, 0.42)), False),
    "wrist": ("WRIST", ((0.27, 0.52, 0.30, 0.10), (0.73, 0.52, 0.30, 0.10)), True),
    "hand": ("HANDS", ((0.27, 0.74, 0.30, 0.26), (0.73, 0.74, 0.30, 0.26)), True),
    "finger": ("FINGERS", ((0.27, 0.84, 0.26, 0.14), (0.73, 0.84, 0.26, 0.14)), True),
    "muscle": ("MUSCLE", ((0.27, 0.26, 0.26, 0.42), (0.73, 0.26, 0.26, 0.42)), True),
    "tendon": ("TENDONS", ((0.27, 0.38, 0.14, 0.34), (0.73, 0.38, 0.14, 0.34)), True),
    "bone": ("BONE", ((0.27, 0.50, 0.18, 0.12), (0.73, 0.50, 0.18, 0.12)), True),
}
OFF_PLATE = {"back", "leg", "knee", "core", "shoulder", "chest", "calf", "lat", "scapula", "trapezius", "spine", "hip", "glute", "neck", "ankle", "elbow"}      # regions the forearm / hands plate does not show: it must never stand in for them
KICKER = {"evidence": "STUDY", "mistake": "MISTAKE", "progression": "PROGRESSION", "routine": "ROUTINE", "benchmark": "TEST", "cue": "CUE"}
REL_KICKER = {"limitation": "LIMIT", "comparison": "COMPARE", "attribution": "BELIEF", "warning": "WARNING"}      # the argument's own move, labelled; only used where the beat has no better label
LABEL_WORDS = {w for _k, lab in LX.HOLD_HEAD for w in lab.split()} | {w for c in LX.CONCEPTS.values() for w in c["label"].split()}      # words of the fixed treatment labels (PINCH GRIP, BAR HANG, CAP ON TIGHT ...)
STRUCTURAL = {"NEXT UP", "SYNTHETIC DATA", "SYNTHETIC", "MYTH"} | set(KICKER.values()) | set(REL_KICKER.values())      # labels the planner adds for a role; any other on-screen word must come from the narration
INTRO_WORDS = {"in", "when", "if", "after", "before", "because", "since", "while", "as", "once", "during", "for", "with", "at", "by"}
POSTURE_RX = re.compile(r"\b(gym|posture|stand(?:ing)? tall|bodyweight|body weight|calisthenics|push-?ups?|pull-?ups?|squats?)\b", re.I)
SYNTH_RX = re.compile(r"\b(synthetic|made[- ]up|fictional|invented)\b", re.I)
ATTRIB_RX = re.compile(r"\b(?:many people|most people|everyone|people|lots of people|they|some)\s+(?:believe|think|say|claim|assume|swear)\s+(?:that\s+)?(.+)", re.I)

def _clean(tok: str) -> str: return re.sub(r"[^\w%-]", "", tok)
def _toks(text: str) -> List[str]: return text.split()

# ---------------------------------------------------------------- beats
def _spans(ws: List[dict]) -> List[List[int]]:
    """Clause spans [i0, i1) over a sentence's words: cut after , ; : . ? !, then clauses that are too short (words or seconds) fold into their neighbour."""
    n = len(ws); cuts = [i + 1 for i, w in enumerate(ws[:-1]) if re.search(r"[,;:.!?]$", w["w"])]; spans: List[List[int]] = []; a = 0
    for c in cuts + [n]: spans.append([a, c]); a = c
    dur = lambda sp: ws[sp[1] - 1]["t1"] - ws[sp[0]]["t0"]
    k = 0
    while k < len(spans) - 1:      # an introductory phrase ("In one study,", "When the bottle starts to slip,") belongs to the clause it introduces
        first = re.sub(r"[^a-z]", "", ws[spans[k][0]]["w"].lower())
        if first in INTRO_WORDS and spans[k][1] - spans[k][0] <= 7: spans[k][1] = spans[k + 1][1]; del spans[k + 1]
        else: k += 1
    while len(spans) > 1:
        k = next((k for k, sp in enumerate(spans) if sp[1] - sp[0] < MIN_CLAUSE_WORDS or dur(sp) < MIN_CLAUSE_S), None)
        if k is None: break
        j = k - 1 if k else k + 1
        if j < k: spans[j][1] = spans[k][1]
        else: spans[j][0] = spans[k][0]
        del spans[k]
    return spans

def make_beats(sentences: List[dict], art_ok) -> List[dict]:
    """Beats in time order. Splitting and merging only regroup the sentence's own words; `check_words` verifies nothing was lost, reordered or added."""
    ss = sorted((dict(s) for s in sentences), key=lambda s: float(s["start"])); beats: List[dict] = []
    for si, s in enumerate(ss):
        ws = P.words_of(s); timing = "word" if s.get("words") else "estimated"; leg = P._scene_of(s, art_ok); atomic = leg["kind"] in ("tier", "equation"); t_s, t_e = float(s["start"]), float(s["end"])
        spans = [[0, len(ws)]] if (atomic or t_e - t_s < SPLIT_MIN_S or len(ws) < 2 * MIN_CLAUSE_WORDS) else _spans(ws)
        for k, (a, b) in enumerate(spans):
            w = ws[a:b]; t0 = t_s if k == 0 else float(w[0]["t0"]); t1 = t_e if k == len(spans) - 1 else float(ws[spans[k + 1][0]]["t0"])
            beats.append({"sentence": si, "t0": t0, "t1": t1, "text": " ".join(x["w"] for x in w), "words": w, "timing": timing, "atomic": atomic, "src": s if atomic else None})
    out: List[dict] = []      # short beats join the previous one when they belong together (same continuous demonstration), never across a unit marker or an atomic structure
    for b in beats:
        p = out[-1] if out else None
        if p and b["t1"] - b["t0"] < MIN_BEAT_S and not (p["atomic"] or b["atomic"]) and not N.unit_marker(b["text"]) and b["t1"] - p["t0"] <= MERGE_MAX_S and p["timing"] == b["timing"]:
            p["t1"] = b["t1"]; p["text"] += " " + b["text"]; p["words"] = p["words"] + b["words"]; p["sentence"] = b["sentence"]; p.setdefault("merged", []).append("short beat joined the previous one")
        else: out.append(b)
    fwd: List[dict] = []      # a very short transition ("Next, a harder one.") belongs to the demonstration it announces
    for b in out:
        p = fwd[-1] if fwd else None
        if p and p.get("_hold") and not (b["atomic"] or p["atomic"]) and p["timing"] == b["timing"]:
            b["t0"] = p["t0"]; b["text"] = p["text"] + " " + b["text"]; b["words"] = p["words"] + b["words"]; b.setdefault("merged", []).append("transition joined the beat it announces"); fwd.pop()
        if len(_toks(b["text"])) <= 4 and b["t1"] - b["t0"] < 2.6 and not b["atomic"] and re.match(r"(next|now|then|so|okay|first|finally|here)\b", b["text"], re.I) and b is not out[-1]: b["_hold"] = True
        fwd.append(b)
    out = fwd
    for i, b in enumerate(out): b["id"] = f"b{i + 1:02d}"; b.pop("_hold", None)
    return out

def check_words(sentences: List[dict], beats: List[dict]) -> List[str]:
    """Problems (empty list = fine): the beats' words, in order, must equal the sentences' words in order."""
    want = [t for s in sorted(sentences, key=lambda s: float(s["start"])) for t in _toks(s["text"])]; got = [t for b in beats for t in _toks(b["text"])]
    if want == got: return []
    return [f"narration differs: {len(want)} words in, {len(got)} words in beats" + (f"; first difference at word {next(i for i, (a, c) in enumerate(zip(want, got)) if a != c)}" if len(want) == len(got) or want[:len(got)] != got else "")]

# ---------------------------------------------------------------- callouts
def _word_t(ws: List[dict], token: str, default: float) -> float:
    return P.time_of(ws, rf"^{re.escape(_clean(token.split()[0]))}$", default) if token else default

_STOP_BEFORE = {"the", "a", "an", "is", "are", "for", "of", "and", "to", "by", "in", "on", "your", "it", "that", "this", "mistake", "hold", "do", "these", "then", "but", "with"}

def _at_pos(ws: List[dict], text: str, part: str, default: float) -> float:
    """Time of the first word of `part` at its own place in `text` (not its first occurrence anywhere in the beat)."""
    pos = text.find(part)
    if pos < 0: return default
    k = len(text[:pos].split()); return float(ws[k]["t0"]) if k < len(ws) else default

def _clip(text: str, n: int) -> str:
    """The first n words in capitals, never ending on a function word ("START AT THE TOP OF" -> "START AT THE TOP")."""
    toks = re.sub(r"[^\w\s%'-]", "", text).upper().split()[:n]
    while len(toks) > 1 and toks[-1].lower() in N.STOP: toks.pop()
    return " ".join(toks)
STOP_LEAD = {"the", "a", "an", "your", "this", "that", "these", "those"}

def _tail_after(text: str, rx: str, n: int) -> Tuple[str, str]:
    """(UPPER words after the match clipped to n, first word) -- a clause's own words, no leading determiner."""
    m = re.search(rx, text, re.I)
    if not m: return "", ""
    toks = [_clean(t) for t in text[m.end():].split()]; toks = [t for t in toks if t]
    while toks and toks[0].lower() in STOP_LEAD: toks = toks[1:]
    return (_clip(" ".join(toks[:n]), n), toks[0] if toks else "")

def _lead_in(b: dict, ws: List[dict], first_entity_at: float) -> Optional[dict]:
    """Words spoken before the beat's first named entity ("Here is the MECHANISM: a muscle ..."): their key phrase, shown while they are said, so the picture does not sit unchanged until the entity is named."""
    if first_entity_at - b["t0"] < 1.5: return None
    lead = [w for w in ws if w["t0"] < first_entity_at - 0.05]; kp, _p = N.key_phrase(" ".join(w["w"] for w in lead))
    return {"text": kp, "at": _word_t(lead, kp.split()[0].lower(), b["t0"] + 0.2)} if kp else None

def caption(b: dict, ws: List[dict]) -> Optional[dict]:
    """A beat's own key words as a caption chip, for a beat that carries an argument move (contrast, cause, negation, attribution ...) rather than a thing to draw. None when it has none."""
    text, rels, t0 = b["text"], b.get("relations", []), b["t0"]; cap, first = "", ""
    if "negation" in rels:
        wn = re.search(r"\b(?:will not|cannot|can't|does not|do not|won't)\s+\w+\b", text, re.I)      # a negated claim ("will not make your wrists thicker"): what it is about is the words after the verb
        m = re.search(r"\b((?:almost |hardly |barely )?no|without)\s+([A-Za-z'-]+)(?:\s+([A-Za-z'-]+))?", text, re.I)      # quantifier negation ("almost no muscle")
        if not m and wn:
            tail, first = _tail_after(text[:text.find(".", wn.end()) + 1 or None] if "." in text[wn.end():] else text, re.escape(wn.group(0)), 3); cap = tail
            if cap: return {"text": cap, "at": _word_t(ws, first, t0 + 0.3)}
        if m: words = [m.group(1), m.group(2)] + ([m.group(3)] if m.group(3) and m.group(3).lower() not in N.STOP else []); cap, first = " ".join(words).upper(), m.group(1).split()[0]
    if not cap and "contrast" in rels:
        cap, first = _tail_after(text, r"\b(?:what|which)\b", 5); cap, first = (("WHAT " + cap) if cap else ""), "what"      # "but you can change WHAT SITS AROUND IT"
    if not cap and "cause" in rels: cap, first = _tail_after(text, r"\b(?:because|since|so that(?!\s+(?:is|was|are|were|will|would)))\b", 8)
    if not cap: cap, pos = N.key_phrase(text); first = cap.split()[0].lower() if cap else ""
    return {"text": cap, "at": _word_t(ws, first, t0 + 0.3) if cap else t0} if cap else None

def callout_page(b: dict, ws: List[dict], e: dict, mark: Optional[dict], overview: Optional[dict] = None) -> Tuple[dict, bool]:
    """(page, has_content). Headline / value / chips are copied from the beat's own words; the kicker is a role label (or SYNTHETIC DATA when the narration says so)."""
    t0 = b["t0"]; text = b["text"]; rels = b.get("relations", []); head, head_at, value, value_at, chips, kicker_rel = "", t0 + 0.35, "", t0 + 0.6, [], ""; src = ""
    if mark and mark.get("title"): head = mark["title"]; head_at = _word_t(ws, mark["title"].lower(), t0 + 0.35); src = "unit title"
    elif e["exercises"]: ex = e["exercises"][0]["text"]; head = LX._clip(ex, 3); head_at = _word_t(ws, ex, t0 + 0.35); src = "exercise name"
    nums = e["numbers"]
    if nums:
        src = src or "number"; n = nums[0]; value = f"{n['value']}%" if n["unit"] == "%" else f"{n['value']} {n['unit']}"; value_at = _word_t(ws, n["text"], t0 + 0.6)
        if not head:      # what the number is a number OF: the few words right after it ("68% GRIP STRENGTH", "4 TIMES / WEEK")
            after = [_clean(t) for t in text[text.lower().find(n["text"].lower()) + len(n["text"]):].replace(",", " , ").split()]; sub: List[str] = []
            for t in after:
                if t in ("for", "and", "in", "on", "with", "to", "by", "then", "but", ",") or not t: break
                if not sub and t.lower() in ("a", "an", "the", "of", "per", "each"): continue
                sub.append(t)
                if len(sub) == 3: break
            if sub: head = " ".join(sub).upper(); head_at = _word_t(ws, sub[0], t0 + 0.35)
            elif e["body"]: head = FOCUS.get(e["body"][0]["part"], (e["body"][0]["part"].upper(),))[0]; head_at = _word_t(ws, e["body"][0]["text"], t0 + 0.35)
        for extra in nums[1:3]:      # "twenty seconds, three times, with one minute of rest": every stated quantity is shown, in the order it is said
            chips.append({"text": (f"{extra['value']}%" if extra["unit"] == "%" else f"{extra['value']} {extra['unit']}"), "at": _word_t(ws, extra["text"], t0 + 0.9)})
    if value and not head:      # a number with nothing naming it leaves the column bare: name it from the beat's own words (a prop it mentions, else the content words just before it)
        if e["props"]: pr = e["props"][0]["text"]; head, head_at = pr.upper(), _word_t(ws, pr, t0 + 0.35); src = "number"
        else:
            before = [_clean(t) for t in text[:text.lower().find(nums[0]["text"].lower())].split()]; keep = [t for t in before if t and t.lower() not in N.STOP and t.lower() not in ("mistake", "common")][-2:]
            if keep: head, head_at = " ".join(keep).upper(), _word_t(ws, keep[0], t0 + 0.35); src = "number"
    if "disclosure" in rels and not head:      # data the narration itself calls made up / synthetic: said plainly, with its stated purpose
        m = re.search(r"(made[- ]up|synthetic|fictional|invented)(?:\s+\w+)?", text, re.I)
        if m: head = _clip(m.group(0), 3); head_at = _word_t(ws, m.group(1).split()[0], t0 + 0.35); kicker_rel = "SYNTHETIC DATA"; src = "disclosure"
        pm = re.search(r"\bused\s+(.{3,60})$", text, re.I)
        if pm and not nums: chips.append({"text": _clip(pm.group(1), 6), "at": _word_t(ws, pm.group(1).split()[0], t0 + 1.0)})
    if "cause" in rels and not head and not value:      # "..., because bone size is fixed": the reason itself is what the beat adds
        tail, first = _tail_after(text, r"\b(?:because|since|so that(?!\s+(?:is|was|are|were|will|would)))\b", 8)
        if tail: head, head_at = tail, _word_t(ws, first, t0 + 0.35); src = "stated reason"
        if "limitation" in rels or re.search(r"\bthe limit\b", text, re.I): kicker_rel = "LIMIT"
    if "comparison" in rels and not head and not value:
        cm = re.search(r"\bcompare\s+(?:the\s+)?(.{2,30}?)\s*[:.]?$", text, re.I)
        if cm: head, head_at, kicker_rel = _clip(cm.group(1), 3), _word_t(ws, cm.group(1).split()[0], t0 + 0.35), "COMPARE"; src = "comparison"
    am = ATTRIB_RX.search(text) if not head and not value else None
    if am: head = _clip(am.group(1), 5); head_at = _word_t(ws, am.group(1).split()[0], t0 + 0.35); kicker_rel = "BELIEF"; src = "attributed belief"
    cl = P._clauses(text, ws, t0)
    for c, a in cl:
        if len(chips) < 2 and c != head and c not in head: chips.append({"text": c, "at": a})
    if not head and not value and b["role"] in ("claim", "statement", "mechanism") and not chips:      # two coordinate clauses ("how much control it needs, and how long you can hold it"): both sides, each in its own words
        sides = [x.strip(" ,.;:") for x in re.split(r",?\s+\band\b\s+|\s+(?:while|whereas)\s+", text, maxsplit=1)]
        if len(sides) == 2 and all(len(x.split()) >= 3 for x in sides): src = "coordinate clauses"; chips = [{"text": _clip(x, 5), "at": _at_pos(ws, text, x, t0 + 0.4 + 0.5 * i)} for i, x in enumerate(sides)]
    if not head and not value and not chips:      # a subject the lexicon does not know ("latissimus dorsi", "scapular retraction"): its own words, as text, and reported as text only
        kp, pos = N.key_phrase(text)
        if kp and len(kp.split()) >= 2: head, head_at = kp, _word_t(ws, kp.split()[0], t0 + 0.35); src = "key phrase"
    if not head and not value and chips: head, head_at = chips[0]["text"], chips[0]["at"]; chips = chips[1:]
    if head and not chips and b["role"] in ("cue", "mistake"):      # "Keep your elbow straight, AND DO NOT LET THE BOOK SLIP": the second instruction is its own development
        sides = [x.strip(" ,.;:") for x in re.split(r",?\s+\band\b\s+", text, maxsplit=1)]
        if len(sides) == 2 and len(sides[1].split()) >= 3 and _clip(sides[1], 6) not in head: chips.append({"text": _clip(sides[1], 6), "at": _at_pos(ws, text, sides[1], t0 + 1.0)}); src = src or "imperative cues"
    sm = re.search(r"\b(?:in|from)\s+(?:one|a|the)\s+([\w\s-]{3,40}?(?:study|review|trial|paper))\b", text, re.I)
    if sm and value and len(chips) < 2: chips.append({"text": _clip(sm.group(1), 4), "at": _word_t(ws, "in", t0 + 0.3)})      # where the number comes from, named at its words
    if (head or chips) and not src: src = "imperative cues"
    if overview and not value:      # the roadmap beat: the structure the narration is about to walk through, when its parts are known
        src = "overview"; head, head_at = overview["head"], t0 + 0.1; chips = [{"text": c, "at": t0 + 0.25 + 0.3 * i} for i, c in enumerate(overview["items"][:3])]
    if (b["t1"] - t0) > 3.4 and len(ws) >= 8 and (head or value) and len(chips) < 2:      # a long beat with one idea: the key words of its second half arrive when they are said
        half = ws[len(ws) // 2:]; kp, _pos = N.key_phrase(" ".join(w["w"] for w in half))
        if kp and kp not in head and not any(kp in c["text"] for c in chips): chips.append({"text": kp, "at": _at_pos(ws, text, kp.split()[0].lower(), half[0]["t0"]) if False else _word_t(half, kp.split()[0].lower(), half[0]["t0"])})
    head_at = min(head_at, t0 + 0.9); value_at = min(value_at, t0 + 0.0) if not head else value_at      # the page's main element is up from its first frame (what is planned is what is rendered); a number or chip that comes with a headline keeps the word it is said on
    kicker = "SYNTHETIC DATA" if SYNTH_RX.search(text) else (KICKER.get(b["role"], "") or kicker_rel or next((REL_KICKER[r] for r in rels if r in REL_KICKER), ""))
    if kicker_rel and not KICKER.get(b["role"]): kicker = kicker_rel if not SYNTH_RX.search(text) else kicker
    page = {"at": t0, "headline": head, "headline_at": head_at, "value": value, "value_at": value_at, "chips": chips, "kicker": kicker, "src": src}
    return page, bool(head or value or chips)

def grounding_violations(sc: dict, narration: str) -> List[str]:
    """On-screen words that are neither in the narration nor a structural role label. Empty list = every word shown comes from the narration."""
    have = {_clean(t).upper() for t in _toks(narration.replace("-", " "))} | {_clean(t).upper() for t in _toks(narration)}; bad: List[str] = []
    for pg in sc.get("pages", []):
        shown = [pg.get("headline", "")] + [c["text"] for c in pg.get("chips", [])] + [pg.get("value", "")]
        for s in shown:
            for tok in _toks(s.upper().replace("-", " ")):
                t = _clean(tok)
                if not t or t in have or t.rstrip("S") in {h.rstrip("S") for h in have} or re.fullmatch(r"[\d.%]+", t) or t in LABEL_WORDS or t in {"L", "KG", "S", "MIN", "REPS", "SETS", "DAYS", "WEEKS", "TIMES", "NO"}: continue
                bad.append(t)
        k = pg.get("kicker", "")
        if k and k not in STRUCTURAL: bad.append(k)
    return sorted(set(bad))

# ---------------------------------------------------------------- selection
def _cand(key: str, kind: str, rel: float, why: str, grounded: bool, build, art: str = "", prop: str = "", approx: str = "") -> dict:
    return {"key": key, "kind": kind, "art": art, "prop": prop, "relevance": rel, "why": why, "grounded": grounded, "build": build, "approx": approx}

def candidates(b: dict, leg: dict, mark: Optional[dict], art_ok, last_part: str = "", comp_labels: Optional[set] = None, overview: Optional[dict] = None) -> List[dict]:      # leg = the legacy detector's reading of this beat
    e, text, ws = b["entities"], b["text"], b["words"]; out: List[dict] = []
    if leg["kind"] == "tier": out.append(_cand("tier", "tier", 1.0, "the narration places or introduces a tier ranking", True, lambda: leg, art=leg["art"]))
    elif leg["kind"] == "equation": out.append(_cand("equation", "equation", 1.0, "the narration states a litres / kilograms pair", True, lambda: leg, art=leg["art"]))
    elif leg["kind"] in ("prop", "hold", "pose", "anatomy") and not leg.get("missing_art"):
        out.append(_cand(f"{leg['kind']}:{leg['art']}:{leg['prop']}", leg["kind"], 0.95, f"the narration names {', '.join(LX.concepts_in(text))}: existing {leg['kind']} treatment", True, lambda: leg, art=leg["art"], prop=leg["prop"]))
    elif leg.get("missing_art"): out.append(_cand("none", "trainee", 0.0, f"the narration names a concept whose art ('{leg['missing_art']}') is not in the library", False, lambda: leg))
    parts = [x["part"] for x in e["body"] if x["part"] in FOCUS]; off = [x for x in e["body"] if x["part"] in OFF_PLATE]
    if b["role"] in ("cue", "progression", "routine") and (e["props"] or e["exercises"] or parts[:1] == ["hand"]): parts = []      # "switch to the other hand" is an instruction, not a lesson about the hand
    if off and parts and leg["kind"] != "anatomy": out.append(_cand("none", "trainee", 0.0, f"the narration names the {off[0]['text']}, which the forearm / hands plate does not show: that picture is not used for it", False, lambda: leg))
    elif parts and leg["kind"] != "anatomy" and art_ok(ANATOMY_ART) and not off:
        seq = parts[:3]; labels = {FOCUS[p][0] for p in seq}; named = [p for p in seq if p not in ("muscle", "tendon", "bone") or True]
        def build(leg=leg, seq=seq):
            sc = dict(leg); gl = []
            for pt in seq:
                label, regions, _ap = FOCUS[pt]; word = next(x["text"] for x in e["body"] if x["part"] == pt); gl.append({"regions": regions, "at": _word_t(ws, word, b["t0"] + 0.3), "label": label})
            gl.sort(key=lambda g: g["at"]); sc.update(kind="anatomy", art=ANATOMY_ART, prop="", glow=gl[0], more_glows=gl[1:], missing_art=None); sc.pop("missing_art", None)
            pg = P._page(b["src"] or {"text": text}, text, ws, b["t0"], "anatomy", gl[0]["label"], []); cap = caption(dict(b, relations=["negation"]), ws) if re.search(r"\b(?:almost no|hardly any|barely any|no|without|will not|cannot|can't|does not|do not|won't)\s+\w+", text, re.I) else None
            if cap: pg["chips"] = [cap]
            elif _lead_in(b, ws, gl[0]["at"]): pg["chips"] = [_lead_in(b, ws, gl[0]["at"])]
            elif e["exercises"] and b["role"] not in ("cue",) and len(e["exercises"][0]["text"].split()) > 1:      # the exercise the beat is about, named at its word ("WRIST CURLS")
                ex = e["exercises"][0]["text"]; pg["chips"] = [{"text": _clip(ex, 3), "at": _word_t(ws, ex, b["t0"] + 0.4)}]
            sc["pages"] = [pg]; return sc
        approx_parts = [p for p in seq if FOCUS[p][2]]
        out.append(_cand(f"anatomy:{ANATOMY_ART}:", "anatomy", 0.85, f"the narration names the {', '.join(seq)}: forearm / hands plate with {'it' if len(seq) == 1 else 'each in turn'} highlighted", True, build, art=ANATOMY_ART,
                         approx=("generic forearm and hands plate, no dedicated " + "/".join(approx_parts) + " illustration (R2)") if approx_parts else ""))
        out[-1]["develops"] = comp_labels is None or bool(labels - comp_labels)
        if not any(x in ("forearm", "wrist", "hand", "finger", "grip") for x in [y["part"] for y in e["body"]]): out[-1]["approx"] = (out[-1]["approx"] + "; narration names no limb region, the plate is only a stand-in for the tissue").strip("; ")
    if overview:      # the roadmap beat: the parts of the structure the narration goes on to establish
        op, _c = callout_page(b, ws, e, mark, overview=overview)
        out.append(_cand("overview", "callout", 0.92 if overview["complete"] else 0.6, f"the narration announces {overview['head'].lower()}: overview of the {len(overview['items'])} {'parts it goes on to name' if overview['complete'] else 'part(s) found so far (the narration names fewer than it announces)'}",
                         True, lambda leg=leg, page=op: dict(leg, kind="callout", art="", prop="", rings=[], glow=None, grip_at=None, flip_at=None, squeezes=[], equations=[], tier=None, tier_marks=[], pages=[page]), approx="" if overview["complete"] else "partial overview"))
        out[-1]["develops"] = True; out[-1]["foreshadow"] = True
    page, content = callout_page(b, ws, e, mark)
    keyword = False
    if page.get("src") == "key phrase": keyword = True
    if not content and e["body"] and b["role"] not in ("cue",):      # only a body word to show (e.g. BONE): a keyword callout, text only, reported as such
        word = e["body"][0]; page = dict(page, headline=word["text"].upper(), headline_at=_word_t(ws, word["text"], b["t0"] + 0.35), src="body word"); content = keyword = True
    if content:
        strong = bool(mark and mark.get("title")) or any(" " in x["text"] or x["text"].endswith("ups") for x in e["exercises"]) or bool(e["numbers"]) or page.get("src") in ("disclosure", "stated reason", "comparison", "attributed belief", "coordinate clauses")      # a bare verb ("squeeze") is not an exercise name
        rel = 0.85 if strong else (0.55 if keyword else 0.6)
        if e["numbers"] and b["role"] in ("evidence", "number", "routine"): rel = 0.95
        what = {"key phrase": "key phrase (a subject the lexicon does not know; text only)", "body word": "body keyword (text only)"}.get(page.get("src"), page.get("src") or "imperative cues")
        def build_c(leg=leg, page=page):
            sc = dict(leg); sc.update(kind="callout", art="", prop="", rings=[], glow=None, grip_at=None, flip_at=None, squeezes=[], equations=[], tier=None, tier_marks=[]); sc.pop("missing_art", None); sc["pages"] = [page]; return sc
        out.append(_cand("callout", "callout", rel, f"callout built from the beat's own {what}", True, build_c)); out[-1]["develops"] = True; out[-1]["text_only"] = True
    elif b["role"] in KICKER or mark:
        out.append(_cand("callout", "callout", 0.35, "only a role label could be shown: the narration gives nothing to put on screen", False, lambda leg=leg, page=page: dict(leg, kind="callout", art="", prop="", rings=[], glow=None, pages=[page])))
    if POSTURE_RX.search(text) and art_ok("rep_stand_v1") and leg["kind"] in ("trainee",):
        out.append(_cand("trainee:rep_stand_v1:", "trainee", 0.9, "the narration is about gym / posture / body-weight training: the trainee is relevant here", True, lambda: leg, art="rep_stand_v1"))
    out.append(_cand("trainee:rep_stand_v1:", "trainee", 0.15, "generic trainee: the beat names nothing the library can show", False, lambda: dict(leg, kind="trainee", art="rep_stand_v1", prop="", pages=[]), art="rep_stand_v1"))
    return out

def choose(cands: List[dict], comp: Optional[dict], recent: List[str], b: dict) -> Tuple[dict, List[dict]]:
    """Best candidate by relevance + novelty - repeat penalty (the penalty grows with how long the previous composition has already been on screen). Returns (choice, ranked alternatives)."""
    ranked = []
    for c in cands:
        s = c["relevance"]
        if c["key"] not in recent[-3:]: s += 0.05
        if comp and c["key"] == comp["key"] and c["kind"] not in ("tier", "equation", "callout") and not c.get("develops"):      # (a text callout carries its own new words, so a second one is a new page, not a repeated picture) a picture already on screen for a while gives way to an equally relevant different one; a board / lockup that is still building never does
            age = b["t0"] - comp["start"]; s -= 0.0 if (b.get("continuity") and age < 8) else (0.0 if age < 6 else 0.2 if age < 8 else 0.45)
        ranked.append(dict(c, score=round(s, 3)))
    ranked.sort(key=lambda c: (-c["score"], -c["relevance"])); return ranked[0], ranked

# ---------------------------------------------------------------- planning
def _entity_summary(e: dict) -> List[str]:
    out = [f"num:{n['text']}" for n in e["numbers"]] + [f"body:{x['text']}" for x in e["body"]] + [f"prop:{x['text']}" for x in e["props"]] + [f"exercise:{x['text']}" for x in e["exercises"]] + [f"tier:{x['letter']}" for x in e["tiers"]]
    return out + (["study"] if e["study"] else [])

def _merge_scene(comp: dict, sc: dict, why: str, keep_pages: bool = True) -> None:
    pages = sc["pages"] if keep_pages else []
    if comp["kind"] in ("equation", "tier") and not (comp["kind"] == "equation" and pages): pages = []
    sc = dict(sc, pages=pages); P._absorb(comp, sc, why)
    gl = ([sc["glow"]] if sc.get("glow") else []) + list(sc.get("more_glows") or [])
    if gl:
        comp.setdefault("glows", ([comp["glow"]] + list(comp.get("more_glows") or [])) if comp.get("glow") else []); comp["glows"] += gl; comp["glow"] = comp["glow"] or gl[0]
    comp["rings"] = sorted(comp["rings"], key=lambda r: r["at"])

def evaluate(b: dict) -> dict:
    """Semantic record of one beat, from the plan itself: what it means, what is shown, why that represents it, which spoken entities support it, how exact it is, what the picture adds that the narration did not say,
    and (when it is not resolved) what kind of failure it is. `exactness`: exact | approximate | text_only | caption | generic | unresolved."""
    v, st, e = b["visual"], b["status"], b["entities"]; ents = [x["text"] for k in ("numbers", "body", "props", "exercises") for x in e[k]] + [f"{t['letter']} tier" for t in e["tiers"]]
    kind = v["kind"]; unsupported: List[str] = []; approx = v.get("approximation", "")
    if st == "continued": ex = "unresolved"
    elif st == "generic_fallback": ex = "generic"
    elif st == "captioned": ex = "caption"
    elif kind == "callout": ex = "text_only"
    elif approx: ex = "approximate"
    else: ex = "exact"
    if kind == "anatomy" and approx: unsupported.append("the plate is a generic forearm / hands illustration: it shows more anatomy than the narration names")
    if v.get("key") == "overview": unsupported.append("part titles are shown at the announcement, before the narration speaks them (taken from the narration's own later words)")
    if kind == "trainee" and ex == "generic": unsupported.append("a character the narration does not mention")
    meaning = f"{b['role']}" + (f" ({', '.join(b.get('relations', []))})" if b.get("relations") else "") + (f": {', '.join(ents[:4])}" if ents else ": no named entity")
    fail = ""
    if ex in ("unresolved", "generic", "caption"):
        fail = "missing_asset" if (e["body"] or e["props"]) and ex != "caption" else "architectural" if b.get("relations") else "ambiguity" if not ents else "architectural"
    return {"meaning": meaning, "supported_by": ents[:6], "exactness": ex, "unsupported_information": unsupported, "failure_class": fail}

def plan(sentences: List[dict], title: str = "", art_ok=None, workdir=None) -> dict:
    """The beat plan: {scenes, beats, narrative, metrics, summary, problems}. Raises nothing for odd narration: beats that cannot be resolved are reported, not hidden."""
    art_ok = art_ok or (lambda a: L.find(a) is not None); ss = sorted((dict(s) for s in sentences), key=lambda s: float(s["start"]))
    beats = make_beats(ss, art_ok); problems = check_words(ss, beats)
    for b in beats:
        b["role"], b["confidence"], b["role_cues"] = N.classify(b["text"]); b["entities"] = N.entities(b["text"]); b["relations"] = N.relations(b["text"]) + (["attribution"] if ATTRIB_RX.search(b["text"]) else [])
    nar = N.analyze(beats, title)
    if nar["hook"]: hb = next(b for b in beats if b["id"] == nar["hook"]["beat"]); hb["role"], hb["confidence"], hb["role_cues"] = "hook", max(hb["confidence"], 0.8), [nar["hook"]["words"]]
    if nar["roadmap"]: rb = next(b for b in beats if b["id"] == nar["roadmap"]["beat"]); rb.setdefault("flags", []).append("roadmap")
    units = {u["id"]: u for u in nar["units"]}
    comps: List[dict] = []; recent: List[str] = []; comp: Optional[dict] = None; last_part = ""
    for i, b in enumerate(beats):
        pseudo = b["src"] or {"text": b["text"], "start": b["t0"], "end": b["t1"], "words": b["words"]}; leg = P._scene_of(pseudo, art_ok)
        leg["start"], leg["end"] = b["t0"], b["t1"]; mark = N.unit_marker(b["text"]); prev_b = beats[i - 1] if i else None
        if comp is not None and comp["kind"] == "hold" and comp.get("prop") and leg["kind"] == "trainee" and leg["pages"] and not P._empty(leg) and art_ok(comp["prop"]):      # same rule as the legacy planner: an instruction after the bottle was picked up
            leg.update(kind="hold", art="rep_stand_v1", prop=comp["prop"]); leg["squeezes"] = [w["t0"] for w in leg["words"] if re.search(LX.SQUEEZE_RX, re.sub(r"\W", "", w["w"]), re.I)]
            if re.search(r"\bswitch\b", b["text"], re.I) and re.search(r"\bhand\b", b["text"], re.I): leg["flip_at"] = P.time_of(leg["words"], r"^switch$", b["t0"] + 1.0)
            leg["decisions"].append("instruction after the bottle was picked up: trainee keeps holding it")
        b["continuity"] = bool(prev_b and prev_b["sentence"] == b["sentence"] and comp is not None and not mark)      # clauses of one sentence belong to one demonstration unless something new is named
        labels = {g.get("label") for g in ((comp.get("glows") or ([comp["glow"]] + list(comp.get("more_glows") or []) if comp.get("glow") else [])) if comp else [])} - {None} if comp and comp["kind"] == "anatomy" else None
        ov = None
        if "roadmap" in b.get("flags", []) and nar["units"]:
            items = [(u["label"] + (f" · {u['title']}" if u["title"] else "")).strip() for u in nar["units"]]; ov = {"head": nar["roadmap"]["text"].upper(), "items": items[:3], "complete": str(len(nar["units"])) == str(nar["roadmap"]["count"]) and len(items) <= 3}
        cands = candidates(b, leg, mark, art_ok, last_part, comp_labels=labels, overview=ov); best, ranked = choose(cands, comp, recent, b)
        why = best["why"]; status = "grounded" if best["grounded"] else "unresolved"; sc_new = None; reason = ""
        carry_chips = comp and comp["kind"] == "equation" and leg["kind"] == "trainee" and P._chips_only(leg)      # "with just your fingers and thumb" after the equation: chips for it
        if carry_chips: best = _cand("equation", "equation", 0.9, "chips that belong to the equation just stated", True, lambda: leg); status, why = "grounded", best["why"]
        weak_ctx = bool(b["continuity"] and comp is not None and comp["kind"] in ("prop", "hold", "pose", "anatomy", "trainee") and best["kind"] == "callout" and best["relevance"] < 0.7)      # a clause of the same sentence with only a thin text cue: the demonstration just goes on
        if weak_ctx: best = dict(best, grounded=False)
        if carry_chips: pass
        elif not best["grounded"]:
            if comp:
                status, why = "continued", "nothing in this beat can be shown on its own; the previous composition continues"; reason = "no visual could be grounded in this beat's own words" + (f" (best candidate was: {ranked[0]['why']})" if ranked[0] is not best else f" ({best['why']})")
            elif best["key"] == "callout": status, reason = "weak_callout", best["why"]
            else: status, reason = "generic_fallback", best["why"]
        sc = copy.deepcopy(best["build"]()); snap = copy.deepcopy(sc)
        cap = caption(b, b["words"]) if (status == "continued" and comp is not None and comp["kind"] in ("prop", "hold", "pose", "anatomy", "trainee", "callout") and ((set(b["relations"]) & {"negation", "contrast", "cause", "limitation", "warning", "comparison", "attribution"}) or (comp["kind"] == "callout" and b["t1"] - b["t0"] >= 1.8))) else None
        if cap and cap["text"]:      # an argument move with nothing to draw: its own key words as a caption on the picture that is already there (labelled `captioned`, never counted as a grounded picture)
            sc = dict(copy.deepcopy(sc), pages=[{"at": b["t0"], "headline": "", "headline_at": b["t0"], "value": "", "chips": [cap], "kicker": ""}], glow=None, more_glows=[]); snap = copy.deepcopy(sc); status = "captioned"; reason = f"no picture for this beat's meaning ({'/'.join(b['relations'])}); its own words are captioned on the picture that is already on screen"; why = "caption of the beat's own words over the previous composition"
            best = dict(best, approx="caption only: the argument move is stated in words, not drawn")
        if status in ("continued", "captioned") or carry_chips:
            if comp is not None: _merge_scene(comp, sc, "beat continues the previous composition", keep_pages=bool(carry_chips) or comp["kind"] in ("prop", "hold", "pose", "anatomy", "trainee", "callout")); comp["beats"].append(b["id"])
            b["visual"] = {"key": comp["key"] if comp else best["key"], "kind": comp["kind"] if comp else best["kind"], "relevance": 0.0 if status == "continued" else 0.4 if status == "captioned" else best["relevance"], "rationale": why, "alternatives": [{"key": r["key"], "score": r["score"]} for r in ranked[:3]], "approximation": best["approx"] if status == "captioned" else ""}
            b["status"], b["reason"] = status, reason; b["scene_sc"] = snap; continue
        join = comp is not None and best["key"] == comp["key"] and best["kind"] not in ("equation",) and (b["t1"] - comp["start"]) <= (DEVELOP_MAX_S if best.get("develops") and best["kind"] == "anatomy" else COMP_MAX_S)
        if join:
            _merge_scene(comp, sc, "same composition continues"); comp["beats"].append(b["id"])
            if best["kind"] == "tier" and sc.get("tier") and sc["tier"].get("letter"): comp["tier"] = sc["tier"]; comp["art"] = comp["art"] or sc["art"]
            if best["kind"] == "tier": comp["decisions"].append("merged with the ranking intro")
        else:
            sc["key"] = best["key"]; sc["beats"] = [b["id"]]; comp = sc; comps.append(sc)
        b["visual"] = {"key": best["key"], "kind": best["kind"], "relevance": best["relevance"], "rationale": why, "alternatives": [{"key": r["key"], "score": r["score"]} for r in ranked[:3]], "approximation": best["approx"]}
        b["status"], b["reason"] = status, reason; b["scene_sc"] = snap; recent.append(best["key"])
        if best["kind"] == "anatomy" and sc.get("glow"): last_part = next((k for k, v in FOCUS.items() if tuple(v[1]) == tuple(map(tuple, sc["glow"]["regions"]))), last_part)
        if status != "grounded" and best["kind"] in ("trainee", "callout"): b["reason"] = reason
    for c in comps:      # the unit a composition belongs to decides where a repeated headline counts as a repeat (a new week may name the same exercise again)
        fb = next((b for b in beats if b["id"] == c["beats"][0]), None); c["_sec"] = (fb.get("unit") or "") if fb else ""
    scenes = P._finish(comps, title, art_ok)
    for c in scenes: c.pop("_sec", None)
    for sc in scenes:      # section tag: the unit the scene belongs to (first beat decides); beats before any unit keep the video title
        first = next((b for b in beats if b["id"] == sc["beats"][0]), None); u = units.get(first.get("unit")) if first else None
        if u: sc["section"] = (u["label"] + (f" · {u['title']}" if u["title"] else "")).strip()
        sc["glows"] = sc.get("glows") or (([sc["glow"]] + list(sc.get("more_glows") or [])) if sc.get("glow") else [])
    for sc in scenes: sc["beats"] = []
    for b in beats:      # beat -> scene by time, because the shared finish step can fold a scene that adds nothing new into the one before
        sc = next((x for x in scenes if x["start"] - 1e-6 <= b["t0"] < x["end"] - 1e-6), scenes[-1]); b["scene"] = sc["no"]; b["development"] = "primary" if not sc["beats"] else "secondary"; sc["beats"].append(b["id"])
        if sc.get("key") != b["visual"]["key"] and b["status"] == "grounded" and b["visual"]["key"] != "overview":
            b["status"], b["reason"] = "continued", f"its own composition added nothing new (headline already shown), so the previous composition ({sc.get('key')}) continues"; b["visual"]["relevance"] = 0.0
    for b in beats:
        part = dict(b.pop("scene_sc")); part.update(no=b.get("scene", 0), start=b["t0"], end=b["t1"]); ev = [e for e in C.events([part]) if e["type"] == "secondary"]
        b["cues"] = [{"what": e["what"], "at": round(e["t"], 2), "target": e.get("target", "")} for e in ev]; b["entity_summary"] = _entity_summary(b["entities"]); b["unit"] = b.get("unit")
        b["visual"]["mode"] = "continued" if b["status"] == "continued" else "caption" if b["status"] == "captioned" else "generic" if b["status"] == "generic_fallback" else "text" if b["visual"]["kind"] == "callout" else "depiction"
        b.update(evaluate(b))
        b["grounding_violations"] = grounding_violations(part, " ".join(x["text"] for x in ss) if b["visual"]["key"] == "overview" else b["text"]); b["words"] = [dict(w) for w in b["words"]]
        for k in ("src", "continuity"): b.pop(k, None)
    total = scenes[-1]["end"] if scenes else 0.0; met = C.metrics(scenes, total)
    stat: Dict[str, int] = {}
    for b in beats: stat[b["status"]] = stat.get(b["status"], 0) + 1
    n = len(beats) or 1; grounded = stat.get("grounded", 0)
    summary = {"beats": len(beats), "scenes": len(scenes), "grounded": f"{grounded}/{len(beats)} ({100 * grounded // n}%)", "status_counts": stat, "approximate_visuals": sum(1 for b in beats if b["visual"].get("approximation")), "visual_modes": {m: sum(1 for b in beats if b["visual"]["mode"] == m) for m in ("depiction", "text", "caption", "continued", "generic")},
               "exactness": {x: sum(1 for b in beats if b["exactness"] == x) for x in ("exact", "approximate", "text_only", "caption", "generic", "unresolved")}, "failure_classes": {c: sum(1 for b in beats if b["failure_class"] == c) for c in ("architectural", "missing_asset", "ambiguity") if any(b["failure_class"] == c for b in beats)},
               "timing_sources": sorted({b["timing"] for b in beats}), "narration_check": "ok" if not problems else problems, "grounding_violations": sum(len(b["grounding_violations"]) for b in beats),
               "consecutive_same_composition": met["consecutive_same_composition"], "unit_count": len(nar["units"]), "kind_counts": met["kind_counts"]}
    return {"title": title, "planner": "beats", "timing": "word" if all(b["timing"] == "word" for b in beats) else "estimated" if all(b["timing"] == "estimated" for b in beats) else "mixed",
            "scenes": scenes, "beats": beats, "narrative": nar, "metrics": met, "summary": summary, "problems": problems}
