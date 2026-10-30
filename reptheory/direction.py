"""Scene direction from the scenes CSV: the optional `look`, `prompt` and `muscle` columns (and `chapter`) put on the planned scenes.
The planner splits and joins sentences into scenes, so a row's direction goes to the scene its first word falls in; when two directed rows land in one scene the first
wins and the other is reported. A blank cell leaves that choice to the app. A directed scene is marked `directed_look`: the variety director, the 3D clips and the Flow pictures
then do what the row asks and nothing else on it. A look that cannot be built from the sentence (a stat card with no number in it) is reported and left to the app."""
from __future__ import annotations
import re
from typing import Callable, Dict, List

LOOKS = ("auto", "figure", "3d", "flow", "stat", "versus", "steps", "takeaway", "timeline", "mistake", "slider", "dial", "study", "graph", "bars", "calendar", "result", "warning", "engage")
ALIASES = {"": "auto", "app": "auto", "stock": "figure", "callout": "figure", "trainee": "figure", "body": "3d", "3d body": "3d", "muscle": "3d", "clip3d": "3d",
           "picture": "flow", "image": "flow", "illustration": "flow", "illus": "flow", "number": "stat", "vs": "versus", "compare": "versus", "comparison": "versus",
           "list": "steps", "sequence": "steps", "key line": "takeaway", "quote": "takeaway",
           "stopwatch": "timeline", "sensation": "timeline", "wrong right": "mistake", "wrong/right": "mistake", "difficulty": "slider", "easier harder": "slider",
           "effort": "dial", "gauge": "dial", "research": "study", "review": "study", "evidence": "study",
           "line graph": "graph", "curve": "graph", "chart": "bars", "bar chart": "bars", "dots": "bars", "dot grid": "bars", "week": "calendar", "schedule": "calendar", "plan": "calendar",
           "result board": "result", "tiers": "result", "score": "result", "safety": "warning", "warning card": "warning", "cta": "engage", "comment": "engage", "like": "engage", "subscribe": "engage"}
CARDS = ("stat", "versus", "steps", "takeaway", "timeline", "mistake", "slider", "dial", "study", "graph", "bars", "calendar", "result", "warning", "engage")
LOCKED = {"tier", "equation"}      # a ranking board or an equation is built from the sentence's own structure: a row cannot turn it into something else

def norm_look(v: str) -> str:
    v = re.sub(r"\s+", " ", str(v or "").strip().lower()); v = ALIASES.get(v, v)
    return v if v in LOOKS else ""

def has_direction(sentences: List[dict]) -> bool:
    return any(str(s.get(k) or "").strip() for s in sentences for k in ("look", "prompt", "muscle", "chapter"))

def check_rows(sentences: List[dict]) -> List[str]:
    """Problems a user can fix in the CSV, one line each (never fatal: the app's own choice is used for that row)."""
    from . import clip3d as C3
    out: List[str] = []
    for i, s in enumerate(sentences, 1):
        raw = str(s.get("look") or "").strip()
        if raw and not norm_look(raw): out.append(f"row {i}: look '{raw}' is not one of {', '.join(LOOKS)}; the app chooses")
        m = str(s.get("muscle") or "").strip()
        if m and not C3.groups_for(m)[0]: out.append(f"row {i}: muscle '{m}' is not a muscle or exercise the 3D body knows (e.g. lats, glutes, forearms, push-up); the sentence's own words are used")
    return out

def _row_look(s: dict) -> str:
    look = norm_look(s.get("look"))
    if look and look != "auto": return look
    if str(s.get("prompt") or "").strip(): return "flow"      # a picture described, no look named: it is a Flow picture
    if str(s.get("muscle") or "").strip(): return "3d"
    return ""

MIN_PART_S = 0.8      # a split never leaves a sliver shorter than this

def _split_at(scenes: List[dict], t: float) -> None:
    """Cuts the scene running at time t in two, so a directed row starts (or stops) its own scene. Words, sentences and callout pages go to the side they are spoken on."""
    import copy
    i = next((k for k, x in enumerate(scenes) if x["start"] + MIN_PART_S <= t <= x["end"] - MIN_PART_S), None)
    if i is None or scenes[i]["kind"] in LOCKED: return
    a = scenes[i]; b = copy.deepcopy(a); a["end"] = b["start"] = t
    ws = a.get("words") or []
    if ws:
        a["words"] = [w for w in ws if float(w["t0"]) < t] or ws[:1]; b["words"] = [dict(w) for w in ws if float(w["t0"]) >= t] or [dict(ws[-1])]
        a["text"] = " ".join(w["w"] + w.get("p", "") for w in a["words"]); b["text"] = " ".join(w["w"] + w.get("p", "") for w in b["words"])
    pa = [pg for pg in a.get("pages") or [] if float(pg.get("at", 0)) < t]; pb = [pg for pg in b.get("pages") or [] if float(pg.get("at", 0)) >= t]
    if a.get("pages"): a["pages"] = pa or a["pages"][:1]
    if b.get("pages"): b["pages"] = pb or [dict(b["pages"][-1] if not pa else pa[-1], at=t)]
    b["decisions"] = list(b.get("decisions") or []) + ["split so a scenes-CSV row has its own scene"]; b.pop("chapter_card", None)
    scenes.insert(i + 1, b)

def apply(scenes: List[dict], sentences: List[dict], log: Callable[[str], None] = lambda m: None) -> Dict[str, int]:
    """Puts each directed row on its scene: sc["look"] + sc["directed_look"], sc["flow_prompt"], sc["muscle"], and the chapter as the scene's section. Returns counts."""
    from . import clip3d as C3, planner as P, variety as V
    stat = {"directed": 0, "shared": 0, "not_buildable": 0, "locked": 0, "chapters": 0}
    if not scenes: return stat
    ss = sorted(sentences, key=lambda s: float(s["start"])); chapter = ""; claimed: Dict[int, int] = {}
    for s in ss:      # each directed row gets its own scene: the planner may have joined it to its neighbours
        if not _row_look(s): continue
        t0, t1 = float(s["start"]), float(s["end"]); _split_at(scenes, t0); _split_at(scenes, t1)
        for k in range(len(scenes) - 1, 0, -1):      # and the planner's own cuts inside the row are joined back: the row is one scene
            if t0 + 1e-6 < scenes[k]["start"] < t1 - 1e-6 and scenes[k - 1]["kind"] not in LOCKED and scenes[k]["kind"] not in LOCKED:
                P._absorb(scenes[k - 1], scenes[k], "joined: one scenes-CSV row is one scene"); del scenes[k]
    for n, sc in enumerate(scenes, 1): sc["no"] = n
    def scene_at(t0: float, t1: float) -> dict: return max(scenes, key=lambda x: (min(x["end"], t1) - max(x["start"], t0), -x["start"]))      # the scene that holds most of the row
    chap_at: List[tuple] = []
    for ri, s in enumerate(ss, 1):
        if str(s.get("chapter") or "").strip(): chapter = str(s["chapter"]).strip(); chap_at.append((float(s["start"]), chapter))
        look = _row_look(s)
        if not look: continue
        sc = scene_at(float(s["start"]), float(s["end"]))
        if sc["no"] in claimed: stat["shared"] += 1; log(f"[REP THEORY CSV] row {ri} shares scene {sc['no']} with row {claimed[sc['no']]}: row {claimed[sc['no']]}'s direction is used"); continue
        claimed[sc["no"]] = ri
        if sc["kind"] in LOCKED and look != "figure": stat["locked"] += 1; log(f"[REP THEORY CSV] row {ri}: scene {sc['no']} is a {sc['kind']} built from the sentence; it keeps that look"); continue
        muscle = str(s.get("muscle") or "").strip()
        if muscle and C3.groups_for(muscle)[0]: sc["muscle"] = muscle
        prompt = str(s.get("prompt") or "").strip()
        if prompt: sc["flow_prompt"] = prompt
        if look == "3d" and not C3.groups_for(sc.get("muscle") or sc.get("text", ""))[0]:
            stat["not_buildable"] += 1; log(f"[REP THEORY CSV] row {ri}: look 3d but neither the muscle column nor the sentence names a muscle or exercise; the app chooses"); continue
        if look in CARDS:
            ev = V.evidence(sc, last=True, role="claim") if look == "takeaway" else V.evidence(sc)
            payload = (ev.get(look) or (None, None))[1]
            if look == "takeaway" and payload is None and sc.get("words"):
                payload = {"words": [{"w": re.sub(r"[^\w'-]", "", w["w"]).upper() or w["w"].upper(), "t0": float(w["t0"])} for w in sc["words"][:22]]}
            if payload is None:
                stat["not_buildable"] += 1; log(f"[REP THEORY CSV] row {ri}: look {look} needs {'a number' if look == 'stat' else 'a comparison (A versus B, not A but B)' if look == 'versus' else 'two or more steps (first, then, finally)'} in the sentence; the app chooses"); continue
            sc["look_payload"] = payload
        sc["look"] = "stock" if look == "figure" else look; sc["directed_look"] = True; sc["decisions"].append(f"CSV row {ri}: look {look}" + (" with its own picture prompt" if prompt else "") + (f", muscle {muscle}" if sc.get("muscle") else "")); stat["directed"] += 1
    if chap_at:      # the CSV's chapters are the sections (top label, chapter cards); the first rows before any chapter keep the video title
        for sc in scenes:
            got = [c for t, c in chap_at if t <= sc["start"] + 1e-6]
            if got: sc["section"] = got[-1].upper(); stat["chapters"] += 1
    return stat

def build_card(sc: dict) -> None:
    """A directed card look becomes the scene's kind, the same way the variety director turns a scene into a card."""
    look = sc.get("look"); payload = sc.pop("look_payload", None)
    if look not in CARDS or payload is None: return
    sc[look] = payload; sc["was_kind"] = sc["kind"]; sc["kind"] = look
    from .variety import FULL_CARDS
    if look in ("stat", "bars"):
        for pg in sc["pages"]: pg["value"] = ""
    if look in FULL_CARDS: sc["pages"] = []
