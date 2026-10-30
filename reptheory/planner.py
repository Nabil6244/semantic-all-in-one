"""Narration -> scenes. Each sentence is read for what it is ABOUT (a ranking, an equation, a named body part, a prop in use, a pose, or just the trainee) and gets the visual treatment that
fits; adjacent sentences about the same thing share one scene, and each sentence keeps its own callout "page" so a long scene still changes state with the narration. Callout text, numbers,
equation terms and tier letters are copied from the narration, never invented, and every animated element is timed to the word it comes from. A sentence dict may carry its own `headline`,
`value`, `chips`, `chapter` (a scenes file can direct the visuals); those win."""
from __future__ import annotations
import difflib, re
from typing import Dict, List

from . import lexicon as LX, library as L, narrative as N

MIN_SCENE_S, MAX_MERGE_S = 2.6, 10.0
BOTTLE = "prop_bottle_2l_v1"

def respell(text: str, words: List[dict]) -> List[dict]:
    """The transcript's words with the script's own spelling ("can't", "spot-reduce" where the voice matched them) and the script's punctuation after each word as `p`: what is shown
    comes from the script, the timing from the voice. Words the script does not have keep the transcript's spelling; the number and times of words never change."""
    ws = [dict(w) for w in words]; st = text.split(); norm = lambda t: re.sub(r"[^a-z0-9%]", "", t.lower())
    for blk in difflib.SequenceMatcher(None, [norm(t) for t in st], [norm(w["w"]) for w in ws], autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            tok, w = st[blk.a + k], ws[blk.b + k]; m = re.match(r"^([^\w%]*)(.*?)([^\w%]*)$", tok); core = m.group(2) or tok
            w["w"] = core.lower() if w["w"] == w["w"].lower() else core; w["p"] = m.group(3)
    return ws

def words_of(s: dict) -> List[dict]:
    """[{w, t0, t1, p}] for a sentence: its own word times when given (spelled as the script spells them), else spread over the sentence by character count."""
    if s.get("words"): return respell(s.get("text", ""), s["words"])
    toks = s["text"].split(); t0, t1 = float(s["start"]), float(s["end"]); wts = [max(1, len(re.sub(r"\W", "", t))) for t in toks]; tot = sum(wts) or 1; out, c = [], t0
    for t, w in zip(toks, wts): d = (t1 - t0) * w / tot; out.append({"w": t, "t0": c, "t1": c + d}); c += d
    return respell(s["text"], out)

def time_of(words: List[dict], rx: str, default: float, which: str = "t0") -> float:
    """Start of the first word matching rx (so an element appears as the word is said); `default` when the narration never says it."""
    for w in words:
        if re.search(rx, re.sub(r"[^\w-]", "", w["w"]), re.I): return float(w[which])
    return default

def _clauses(text: str, ws: List[dict], t0: float):
    """Short imperative clauses ("Stand tall", "rest", "switch to the other hand") as (TEXT, time of their first word), in the order they are said."""
    out = []
    for clause in re.split(r"[,.;]|\band\b|\bthen\b", text):
        toks = re.findall(r"[A-Za-z'-]+", clause)
        if toks and len(toks) <= 5 and toks[0].lower() in LX.IMPERATIVES: out.append((" ".join(toks).upper(), time_of(ws, rf"^{re.escape(toks[0])}$", t0 + 0.8)))
    return out

def _page(s: dict, text: str, ws: List[dict], t0: float, kind: str, label: str, rule_chips: list) -> dict:
    """The callout for one sentence: headline (+ when), value, up to two chips, optional small kicker."""
    cl = _clauses(text, ws, t0); head, head_at = "", t0 + 0.35
    if re.search(r"\ball you need\b", text, re.I) and kind == "prop": head, head_at = "ALL YOU NEED", time_of(ws, r"^need$", t0 + 0.3)
    elif re.search(r"\bgym\b", text, re.I) and kind == "trainee": head, head_at = ("NO GYM" if LX.NEGATION.search(text) else "GYM"), time_of(ws, r"^gym$", t0 + 0.3)
    elif kind == "hold":
        verb = next((h for k, h in LX.HOLD_HEAD if re.search(k, text, re.I)), ""); 
        if verb and not cl: head, head_at = verb, time_of(ws, rf"^{verb.split()[0].lower()[:5]}", t0 + 0.3)
    elif label: head, head_at = label, t0 + 0.35
    chips = [dict(text=c, at=a) for c, a in rule_chips]
    first = next(((c, a) for c, a in cl if len(c.split()) <= 2), None)
    if not head and first: head, head_at = first; cl = [x for x in cl if x != first]
    for c, a in cl:
        if c not in [x["text"] for x in chips]: chips.append({"text": c, "at": a})
    value = LX.quantity(text) if kind in ("trainee", "prop", "pose", "hold") else ""
    chips = [c for c in chips if not (head and (head in c["text"] or c["text"] in head))]      # a chip that only repeats the headline adds nothing
    page = {"at": t0, "headline": head, "headline_at": head_at, "value": value, "chips": sorted(chips, key=lambda c: c["at"])[:2], "kicker": "NEXT UP" if re.match(r"\s*next\b", text, re.I) else ""}
    for k in ("headline", "value"):
        if s.get(k): page[k] = s[k]
    if s.get("chips"): page["chips"] = [{"text": c.upper(), "at": t0 + 0.6 + i * 0.5} for i, c in enumerate(s["chips"])]
    if s.get("headline") or s.get("chips"): page["given"] = True      # written in the scenes file: shown as written
    return page

def _scene_of(s: dict, art_ok) -> dict:
    text, ws = s["text"], words_of(s); t0 = float(s["start"]); d: List[str] = []
    sc = {"start": t0, "end": float(s["end"]), "text": text, "sentences": [s["text"]], "kind": "trainee", "art": "rep_stand_v1", "prop": "", "pages": [], "equations": [], "rings": [], "glow": None, "tier": None,
          "decisions": d, "words": ws, "tier_marks": [], "squeezes": [], "flip_at": None, "grip_at": None}
    cons = LX.concepts_in(text); tier = LX.TIER_RX.search(text); eqs = list(LX.EQ_RX.finditer(text)); label = ""
    sc["tier_marks"] = [{"letter": w["w"].strip(".,;:!?"), "at": w["t0"]} for w, nx in zip(ws, ws[1:]) if re.fullmatch(r"[SABCDF]", w["w"].strip(".,;:!?")) and re.fullmatch(r"tier", nx["w"].strip(".,;:!?"), re.I)]   # "from S tier ... down to F tier": the rows light up as they are named
    if tier:
        letter = (tier.group(1) or tier.group(2)).upper(); subj = re.split(r"\b(?:is|are|lands?|goes|ranks?|sits?|needs?|asks?|requires?|takes?|has|have|comes?)\b", text, maxsplit=1, flags=re.I)[0]; item = s.get("item") or LX._clip(re.sub(r"[^\w\s-]", "", subj), 4)
        sc.update(kind="tier", art=BOTTLE if "bottle" in cons else "", tier={"letter": letter, "item": item, "at": time_of(ws, r"^(lands?|goes|ranks?|ranked|placed?|sits?|comes?)$", time_of(ws, r"^tier$", t0 + 1.0) - 0.4), "total": s.get("tier_total")}); d.append(f"narration ranks the item {letter} tier: tier-list scene")
    elif LX.TIER_TALK_RX.search(text) and not eqs:
        sc.update(kind="tier", art="", tier={"letter": None, "item": "", "at": t0 + 99, "total": s.get("tier_total")}); d.append("narration introduces the ranking: empty tier board")
    elif eqs:
        cur = t0
        for m in eqs:      # terms appear as their words are said: the litres word, then the kilograms word after it; the cursor moves on so a second pair finds ITS words
            lhs, rhs = f"{LX.num(m.group(1))} L", f"{LX.num(m.group(2))} KG"
            a = time_of([w for w in ws if w["t0"] >= cur], r"^(litres?|liters?)$", cur); b = time_of([w for w in ws if w["t0"] > a], r"^(kilograms?|kilos?|kg)$", a + 0.8)
            sc["equations"].append({"lhs": lhs, "rhs": rhs, "at_l": a, "at_r": max(b, a + 0.4)}); cur = b + 0.01
        sc.update(kind="equation", art=BOTTLE if "bottle" in cons else ""); d.append(f"{len(eqs)} number pair(s) in the narration: equation lockup")
    elif cons:
        c = LX.CONCEPTS[cons[0]]; sc.update(kind=c["kind"], art=c["art"]); label = c["label"]; d.append(f"narration names '{cons[0]}': {c['kind']} scene")
        if c["kind"] == "prop" and cons[0] != "cap" and LX.HOLD_RX.search(text) and art_ok("rep_stand_v1"):      # the bottle is in use: the trainee holds it
            sc.update(kind="hold", art="rep_stand_v1", prop=c["art"]); label = ""; d.append("the bottle is being held or squeezed: trainee holds it")
        if c["kind"] == "prop":
            ring = next((r for w, r in c["rings"] if w and re.search(rf"\b{w}\b", text, re.I)), dict(c["rings"])[""]); sc["rings"].append({"x": ring[0], "y": ring[1], "r": ring[2], "at": time_of(ws, r"^(bottles?|neck|cap)$", t0 + 0.6)})
        if c["kind"] == "anatomy": sc["glow"] = {"regions": c["glow"], "at": time_of(ws, r"^forearms?$", t0 + 0.3)}
        if c["kind"] == "pose": sc["grip_at"] = time_of(ws, r"^(hands?|hang)$", t0 + 0.5)
    if sc["kind"] == "hold":
        sc["squeezes"] = [w["t0"] for w in ws if re.search(LX.SQUEEZE_RX, re.sub(r"\W", "", w["w"]), re.I)]
        if re.search(r"\bswitch\b", text, re.I) and re.search(r"\bhand\b", text, re.I): sc["flip_at"] = time_of(ws, r"^switch$", t0 + 1.0)
    if sc["kind"] in ("trainee", "prop", "pose", "hold", "anatomy"):
        rule = []
        for rx, build in LX.CHIP_RULES:
            m = rx.search(text)
            if m: chip = build(m); first = chip.split()[0].lower(); rule.append((chip, time_of(ws, rf"^{re.escape(first)}$|^{re.escape(m.group(1).split()[0] if m.groups() and m.group(1) else first)}$", t0 + 0.8)))
        sc["pages"] = [_page(s, text, ws, t0, sc["kind"], label, rule)]
    if s.get("chapter"): sc["chapter"] = s["chapter"]
    if sc["art"] and not art_ok(sc["art"]):      # no picture for it yet: show the concept as a callout on the trainee instead of a made-up image
        d.append(f"art '{sc['art']}' is not in the library: shown as a callout on the trainee"); sc["missing_art"] = sc["art"]; sc["art"] = "rep_stand_v1" if sc["kind"] in ("prop", "anatomy", "pose") else sc["art"]
        if sc["kind"] in ("prop", "anatomy", "pose"): sc["kind"] = "trainee"
    if sc["kind"] == "hold" and not art_ok(sc["prop"]): sc.update(kind="trainee", prop="")
    return sc

def _empty(sc: dict) -> bool: return not any(p["headline"] or p["chips"] or p["value"] for p in sc["pages"])
def _chips_only(sc: dict) -> bool: return bool(sc["pages"]) and not any(p["headline"] or p["value"] for p in sc["pages"])      # a sentence that adds only chips (e.g. "with just your fingers and thumb")

def _absorb(prev: dict, sc: dict, why: str) -> None:
    prev["end"] = sc["end"]; prev["text"] += " " + sc["text"]; prev["sentences"] += sc["sentences"]; prev["words"] += sc["words"]; prev["pages"] += sc["pages"]; prev["rings"] += sc["rings"]; prev["tier_marks"] += sc["tier_marks"]
    prev["squeezes"] += sc["squeezes"]; prev["flip_at"] = prev["flip_at"] or sc["flip_at"]; prev["decisions"] += [why] + sc["decisions"]

def plan(sentences: List[dict], title: str = "", art_ok=None) -> List[dict]:
    art_ok = art_ok or (lambda a: L.find(a) is not None)
    ss = sorted((dict(s) for s in sentences), key=lambda s: float(s["start"])); scenes: List[dict] = []
    for s in ss:
        sc = _scene_of(s, art_ok); prev = scenes[-1] if scenes else None
        if prev and sc["kind"] == "trainee" and prev["kind"] == "hold" and not _empty(sc) and prev["prop"]: sc.update(kind="hold", prop=prev["prop"]); sc["decisions"].append("instruction after the bottle was picked up: trainee keeps holding it")
        if prev and prev["kind"] == "tier" and sc["kind"] == "tier":      # the intro and the placement are one board
            if sc["tier"]["letter"]: prev["tier"] = sc["tier"]
            prev["art"] = prev["art"] or sc["art"]; _absorb(prev, sc, "merged with the ranking intro"); continue
        carry = prev and sc["kind"] == "trainee" and (_empty(sc) or (prev["kind"] == "equation" and _chips_only(sc))) and prev["kind"] in ("equation", "prop", "anatomy", "hold", "pose") and sc["end"] - prev["start"] <= 11.0 and sc["end"] - sc["start"] < 6.0
        same = prev and prev["kind"] == sc["kind"] and prev["art"] == sc["art"] and prev["prop"] == sc["prop"] and sc["kind"] in ("trainee", "prop", "anatomy", "pose", "hold") and not sc["equations"] and sc["end"] - prev["start"] <= MAX_MERGE_S
        short = prev and sc["end"] - sc["start"] < MIN_SCENE_S and prev["kind"] != "tier" and sc["kind"] != "tier" and sc["end"] - prev["start"] <= MAX_MERGE_S
        if same or short or carry: _absorb(prev, sc, "merged with the previous sentence"); continue
        scenes.append(sc)
    return _finish(scenes, title, art_ok)

LABELS = frozenset({w for _k, lab in LX.HOLD_HEAD for w in lab.split()} | {w for c in LX.CONCEPTS.values() for w in c["label"].split()} | {"NO", "GYM", "ALL", "YOU", "NEED", "NEXT", "UP"})

def shape_text(sc: dict, keep: frozenset = LABELS) -> None:
    """Every headline and chip of the scene made a phrase of the script (narrative.phrase); a headline dropped for being no phrase gives way to the page's first chip."""
    ws = sc.get("words") or []
    for pg in sc["pages"]:
        if pg.get("src") == "overview" or pg.get("given"): continue
        before = (pg["headline"], [c["text"] for c in pg["chips"]])
        pg["headline"] = N.phrase(pg["headline"], ws, keep) if pg["headline"] else ""
        pg["chips"] = [dict(c, text=t) for c in pg["chips"] for t in [N.phrase(c["text"], ws, keep)] if t and t != pg["headline"]]
        if before[0] and not pg["headline"] and not pg["value"] and pg["chips"]: pg["headline"], pg["headline_at"] = pg["chips"][0]["text"], pg["chips"][0]["at"]; pg["chips"] = pg["chips"][1:]
        if before != (pg["headline"], [c["text"] for c in pg["chips"]]): sc["decisions"].append(f"on-screen text kept to phrases of the script: {before[0]!r} -> {pg['headline']!r}")

def never_empty(scenes: List[dict]) -> List[dict]:
    """Run last, after every look is chosen: a text-only scene with nothing on it gets the opening phrase of its own words; with none it joins the scene before. Never an empty frame."""
    out: List[dict] = []
    for sc in scenes:
        if sc["kind"] == "callout" and (not sc["pages"] or _empty(sc)):
            head = N.short_clause(sc.get("words") or [], min_content=0) or N.lead_phrase(sc.get("words") or [])
            if head:
                pg = sc["pages"][0] if sc["pages"] else {"at": sc["start"], "value": "", "chips": [], "kicker": ""}; pg.update(headline=head, headline_at=sc["start"] + 0.2)
                sc["pages"] = sc["pages"] or [pg]; sc["headline"] = head; sc["decisions"].append("nothing to show: its opening phrase is its headline")
            elif out: out[-1]["end"] = sc["end"]; out[-1]["decisions"].append(f"scene {sc.get('no')} had nothing to show: this one continues"); continue
        out.append(sc)
    for i, sc in enumerate(out): sc["no"] = i + 1
    return out

def _finish(scenes: List[dict], title: str, art_ok, keep: frozenset = LABELS) -> List[dict]:
    """Everything after the merge: on-screen texts kept to phrases of the script, repeated headlines and chips dropped, art carried into equations, section/topic/numbering, scene ends,
    tier board hold. Shared by the legacy planner and the beat planner."""
    seen_head: List[str] = []; seen_chip: set = set(); recent: List[set] = []
    for i, sc in enumerate(scenes):      # every scene adds something new: a headline already used in the last scenes (or in either of the two before, whatever their section), or a chip already shown, is dropped
        shape_text(sc, keep)
        for pg in sc["pages"]:
            if pg["headline"] and ((sc.get("_sec", ""), pg["headline"]) in seen_head or any(pg["headline"] in r for r in recent[-2:])): pg["headline"] = ""; sc["decisions"].append("repeated headline dropped")
            if pg["headline"]: seen_head.append((sc.get("_sec", ""), pg["headline"]))      # per section: a routine may name the same exercise again in its next week
            pg["chips"] = [c for c in pg["chips"] if c["text"] not in seen_chip]; seen_chip.update(c["text"] for c in pg["chips"])
        recent.append({pg["headline"] for pg in sc["pages"] if pg["headline"]})
        if sc["pages"] and _empty(sc) and i and sc["kind"] in ("trainee", "pose", "hold", "prop") and sc["end"] - sc["start"] < 6.0: sc["_drop"] = True      # nothing new to show: the previous picture simply goes on
    out: List[dict] = []
    for sc in scenes:
        if sc.pop("_drop", False) and out: _absorb(out[-1], sc, "nothing new to show: previous scene continues")
        else: out.append(sc)
    scenes = out
    for i, sc in enumerate(scenes):
        if sc["kind"] == "equation" and not sc["art"]: sc["art"] = next((p["art"] or p["prop"] for p in reversed(scenes[:i]) if p["kind"] in ("prop", "hold") and (p["art"] or p["prop"])), "")
        if sc["kind"] == "equation" and sc["art"] == "rep_stand_v1": sc["art"] = BOTTLE if art_ok(BOTTLE) else ""
        if sc["kind"] == "anatomy" and any(p["kind"] == "hold" for p in scenes[:i]): sc["inset"] = next(p["prop"] for p in reversed(scenes[:i]) if p["kind"] == "hold")
        sc["no"] = i + 1; sc["section"] = (sc.get("chapter") or ("TIER LIST" + (f" · {title.split(chr(183))[0].strip().upper()}" if title else "") if sc["kind"] == "tier" else title.upper())).strip()
        if i + 1 < len(scenes): sc["end"] = scenes[i + 1]["start"] if scenes[i + 1]["start"] > sc["start"] else sc["end"]
        sc["topic"] = title.split(chr(183))[0].strip().upper()
        first = sc["pages"][0] if sc["pages"] else {"headline": "", "value": "", "chips": []}; sc["headline"], sc["value"], sc["chips"] = first["headline"], first["value"], first["chips"]      # first page, for readers of the report
    for i, sc in enumerate(scenes):      # the ranked item must be SEEN in its row before the next scene pushes in: hold the board ~1 s after the placement lands, taken from the next scene
        if sc["kind"] == "tier" and sc["tier"] and sc["tier"]["letter"] and i + 1 < len(scenes):
            want = sc["tier"]["at"] + 0.8 + 1.0; nxt = scenes[i + 1]
            if want > sc["end"] and nxt["end"] - want >= 2.5: sc["end"] = want; nxt["start"] = want; sc["decisions"].append("board held after the placement so the final ranking is visible")
    if scenes: scenes[0]["start"] = 0.0
    for a, b in zip(scenes, scenes[1:]): b["start"] = a["end"]
    return scenes

def plan_beats(sentences: List[dict], title: str = "", art_ok=None) -> List[dict]:
    """Scenes from the narrative beat planner (reptheory.beats); `plan` stays the legacy sentence planner and the fallback."""
    from . import beats as B
    return B.plan(sentences, title=title, art_ok=art_ok)["scenes"]
