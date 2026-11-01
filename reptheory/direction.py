"""Scene direction from the scenes CSV: the optional `look`, `prompt` and `muscle` columns (and `chapter`) put on the planned scenes.
The planner splits and joins sentences into scenes, so a row's direction goes to the scene its first word falls in; when two directed rows land in one scene the first
wins and the other is reported. A blank cell leaves that choice to the app. A directed scene is marked `directed_look`: the variety director, the 3D clips and the Flow pictures
then do what the row asks and nothing else on it. A look that cannot be built from the sentence (a stat card with no number in it) is reported and left to the app."""
from __future__ import annotations
import re
from typing import Callable, Dict, List

LOOKS = ("auto", "figure", "3d", "flow", "stat", "versus", "steps", "takeaway", "timeline", "mistake", "slider", "dial", "study", "graph", "bars", "calendar", "result", "warning", "engage", "myth", "question", "checklist", "slots", "race", "formula", "mechanism", "promise", "tokens", "share")
ALIASES = {"": "auto", "app": "auto", "stock": "figure", "callout": "figure", "trainee": "figure", "body": "3d", "3d body": "3d", "muscle": "3d", "clip3d": "3d",
           "picture": "flow", "image": "flow", "illustration": "flow", "illus": "flow", "number": "stat", "vs": "versus", "compare": "versus", "comparison": "versus",
           "list": "steps", "sequence": "steps", "key line": "takeaway", "quote": "takeaway",
           "stopwatch": "timeline", "sensation": "timeline", "wrong right": "mistake", "wrong/right": "mistake", "difficulty": "slider", "easier harder": "slider",
           "effort": "dial", "gauge": "dial", "research": "study", "review": "study", "evidence": "study",
           "line graph": "graph", "curve": "graph", "chart": "bars", "bar chart": "bars", "dots": "bars", "dot grid": "bars", "week": "calendar", "schedule": "calendar", "plan": "calendar",
           "result board": "result", "tiers": "result", "score": "result", "safety": "warning", "warning card": "warning", "cta": "engage", "comment": "engage", "like": "engage", "subscribe": "engage", "myths": "myth", "myth vs fact": "myth", "fact": "myth", "chat": "question", "viewer question": "question", "q&a": "question", "checklist": "checklist", "ticks": "checklist",
           "count": "slots", "slot": "slots", "list slots": "slots", "tracker": "slots", "speed": "race", "race bars": "race", "equation": "formula", "not equal": "formula", "pull": "mechanism", "muscle tendon bone": "mechanism", "lock": "promise", "curiosity": "promise", "teaser": "promise", "sets": "tokens", "reps": "tokens", "holds": "tokens", "weight share": "share", "share of weight": "share"}
CARDS = ("stat", "versus", "steps", "takeaway", "timeline", "mistake", "slider", "dial", "study", "graph", "bars", "calendar", "result", "warning", "engage", "myth", "question", "checklist", "slots", "race", "formula", "mechanism", "promise", "tokens", "share")
LOCKED = {"tier", "equation"}      # a ranking board or an equation is built from the sentence's own structure: a row cannot turn it into something else

NEEDS = {"stat": "a number", "versus": "a comparison (A versus B, not A but B)", "steps": "two or more steps (first, then, finally)", "takeaway": "words",
         "timeline": "two time marks (10 seconds in ... 20 seconds ...)", "mistake": "a mistake (the most common mistake is ...)", "slider": "too hard? ... too easy?", "dial": "N out of 10 or N% effort",
         "study": "a study with its count or year (a study of 16 men, researchers watched 74 ...)", "graph": "a change over time (rises, drops, levels off)", "bars": "two numbers of one unit or a share",
         "calendar": "three named days or N days a week", "result": "two or more bands (under 20 ... 20 to 40 ...)", "warning": "a sign of harm and what to do", "engage": "a comment / like / subscribe / link below",
         "myth": "Myth: ... and the fact", "question": "a question to the viewer", "checklist": "a list of three short items", "slots": "a count of things (four moments, three moves)",
         "race": "fast against late (stiff X gets there fast, whoever ... first wins)", "formula": "X is not Y / X means Y / X is like Y", "mechanism": "two of muscle, tendon, bone and the pull between them",
         "tokens": "sets and their length (three holds of 15 seconds, 6 x 2 s)", "share": "a share of your weight (half your weight, two thirds, 66% of your body weight)",
         "promise": "a payoff promised for later (I'll show you ... / at the end I'll tell you ...)"}      # what each card look needs, for the log

def norm_look(v: str) -> str:
    v = re.sub(r"\s+", " ", str(v or "").strip().lower()); v = ALIASES.get(v, v)
    return v if v in LOOKS else ""

def has_direction(sentences: List[dict]) -> bool:
    return any(str(s.get(k) or "").strip() for s in sentences for k in ("look", "prompt", "muscle", "chapter", "camera", "on_screen", "section", "graphic"))

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

ON_SCREEN_MAX = 6
SYMBOLS = {"=", "≠", "+", "→", "->", "vs", "x", "×", "/", "&", "<", ">"}

def on_screen_ok(v, text: str) -> str:
    """The CSV's on_screen words, upper-cased, when every word is the sentence's own (numbers and = ≠ + → may join them) and there are at most ON_SCREEN_MAX; else ""."""
    v = re.sub(r"\s+", " ", str(v or "").strip())
    if not v: return ""
    said = set(re.findall(r"[a-z0-9%]+", text.lower().replace("'", "")))
    toks = [p for w in v.split() if w.lower() not in SYMBOLS for p in w.split("-")]      # "SEVENTY-FOUR", "TWELVE-WEEK": each part must be said
    words = [re.sub(r"[^a-z0-9%]", "", w.lower().replace("'", "")) for w in toks]
    if not words or len(words) > ON_SCREEN_MAX or any(w and w not in said for w in words): return ""
    return v.upper().replace("->", "→")

SECTION_ALIASES = {"hook": "hook", "intro": "hook", "why": "why", "science": "why", "proof": "why", "unit": "howto", "how": "howto", "howto": "howto", "how-to": "howto", "step": "howto",
                   "warning": "warning", "safety": "warning", "mistakes": "warning", "mistake": "warning", "plan": "plan", "routine": "plan", "frequency": "plan", "result": "result", "test": "result", "close": "result", "cta": "result"}
GRAPHIC_KINDS = ("chain",)      # graphics the `graphic` column can spell out today; more come with docs/rep_theory/PLAN_NEXT_GRAPHICS.md

def parse_graphic(v, script: str):
    """The CSV's `graphic` cell, e.g. "chain: plank 30s | lean 3x15s | WARNING tendons | lift-off 6x2s": {kind, items: [{name, target, warn}]}; None when it is empty,
    not a kind the app builds, or names words the script never says (nothing is invented)."""
    v = str(v or "").strip()
    if ":" not in v: return None
    kind, rest = v.split(":", 1); kind = kind.strip().lower()
    if kind not in GRAPHIC_KINDS: return None
    said = set(re.findall(r"[a-z0-9%]+", script.lower().replace("'", ""))); items = []
    for part in [p.strip() for p in rest.split("|") if p.strip()]:
        warn = bool(re.match(r"(?i)warning\b", part)); part = re.sub(r"(?i)^warning\s*", "", part)
        m = re.search(r"(\d+\s*[x×]\s*\d+\s*(?:s|sec|reps?)?|\d+\s*(?:s|sec|seconds|reps?|min))\s*$", part, re.I); target = m.group(1).upper().replace("X", " × ").replace("  ", " ") if m else ""
        target = re.sub(r"(\d)\s*(S|SEC|SECONDS|REPS?|MIN)\b", r"\1 \2", target); name = (part[:m.start()] if m else part).strip(" -·:")
        if not name or any(w not in said for w in re.findall(r"[a-z0-9%]+", name.lower().replace("'", ""))): return None
        items.append({"name": name.upper(), "target": target.strip(), "warn": warn})
    return {"kind": kind, "items": items} if len(items) >= 2 else None

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
    ss = sorted(sentences, key=lambda s: float(s["start"])); chapter = ""; claimed: Dict[int, int] = {}; prev_prompt = ""
    for s in ss:      # each directed row gets its own scene: the planner may have joined it to its neighbours
        if not _row_look(s): continue
        t0, t1 = float(s["start"]), float(s["end"]); _split_at(scenes, t0); _split_at(scenes, t1)
        for k in range(len(scenes) - 1, 0, -1):      # and the planner's own cuts inside the row are joined back: the row is one scene
            if t0 + 1e-6 < scenes[k]["start"] < t1 - 1e-6 and scenes[k - 1]["kind"] not in LOCKED and scenes[k]["kind"] not in LOCKED:
                P._absorb(scenes[k - 1], scenes[k], "joined: one scenes-CSV row is one scene"); del scenes[k]
    for n, sc in enumerate(scenes, 1): sc["no"] = n
    def scene_at(t0: float, t1: float) -> dict: return max(scenes, key=lambda x: (min(x["end"], t1) - max(x["start"], t0), -x["start"]))      # the scene that holds most of the row
    per_scene: Dict[int, List[str]] = {}      # the CSV is the script: a scene one row covers keeps that row's own text, so a word the transcript dropped ("thirty percent") still counts
    for s in ss: per_scene.setdefault(id(scene_at(float(s["start"]), float(s["end"]))), []).append(str(s.get("text") or ""))
    for x in scenes:
        rows_here = per_scene.get(id(x), [])
        if len(rows_here) == 1 and rows_here[0].strip(): x["script_text"] = rows_here[0].strip()
    chap_at: List[tuple] = []; script = " ".join(str(x.get("text") or "") for x in ss)
    for ri, s in enumerate(ss, 1):
        if str(s.get("chapter") or "").strip(): chapter = str(s["chapter"]).strip(); chap_at.append((float(s["start"]), chapter))
        part = SECTION_ALIASES.get(str(s.get("section") or "").strip().lower(), "")
        if part:      # the CSV says which part of the video this row is in (variety.section_kind uses it first)
            ps = scene_at(float(s["start"]), float(s["end"])); ps["section_csv"] = part
        g = parse_graphic(s.get("graphic"), script)
        if g:
            gs = scene_at(float(s["start"]), float(s["end"])); gs["graphic_csv"] = g; log(f"[REP THEORY CSV] row {ri}: graphic {g['kind']} with {len(g.get('items', []))} item(s)")
        elif str(s.get("graphic") or "").strip(): log(f"[REP THEORY CSV] row {ri}: graphic '{s.get('graphic')}' is not one the app builds yet (or uses words the script does not say); the app chooses")
        look = _row_look(s)
        shown = on_screen_ok(s.get("on_screen"), s.get("text", ""))
        if str(s.get("on_screen") or "").strip() and not shown: log(f"[REP THEORY CSV] row {ri}: on_screen '{s.get('on_screen')}' uses words the sentence does not say (or more than {ON_SCREEN_MAX} words); the app picks the words")
        if shown:      # the words this row puts on screen, as its scene's first headline (never invented: every word is the sentence's own)
            hs = scene_at(float(s["start"]), float(s["end"]))
            if hs.get("pages"): hs["pages"][0]["headline"] = shown; hs["pages"][0]["headline_at"] = max(float(hs["pages"][0].get("at", hs["start"])), float(s["start"]))
            else: hs["pages"] = [{"at": float(s["start"]), "headline": shown, "headline_at": float(s["start"]), "value": "", "chips": []}]
            hs["on_screen"] = shown
        if not look: continue
        sc = scene_at(float(s["start"]), float(s["end"]))
        if sc["no"] in claimed: stat["shared"] += 1; log(f"[REP THEORY CSV] row {ri} shares scene {sc['no']} with row {claimed[sc['no']]}: row {claimed[sc['no']]}'s direction is used"); continue
        claimed[sc["no"]] = ri
        if sc["kind"] in LOCKED and look != "figure": stat["locked"] += 1; log(f"[REP THEORY CSV] row {ri}: scene {sc['no']} is a {sc['kind']} built from the sentence; it keeps that look"); continue
        muscle = str(s.get("muscle") or "").strip()
        if muscle and C3.groups_for(muscle)[0]: sc["muscle"] = muscle
        prompt = str(s.get("prompt") or "").strip()
        if prompt.lower() in ("same", "same picture", "previous", "same as above") and prev_prompt: prompt = prev_prompt      # the row before's picture again, re-framed (camera column)
        if prompt: sc["flow_prompt"] = prompt; prev_prompt = prompt
        cam = str(s.get("camera") or "").strip()
        if cam: sc["camera"] = cam
        if look == "3d" and not C3.groups_for(sc.get("muscle") or sc.get("text", ""))[0]:
            stat["not_buildable"] += 1; log(f"[REP THEORY CSV] row {ri}: look 3d but neither the muscle column nor the sentence names a muscle or exercise; the app chooses"); continue
        if look in CARDS:
            payload = None
            for txt in dict.fromkeys(x for x in (sc.get("script_text"), sc["text"]) if x):      # the row's own words first (the transcript may drop "percent"), then the transcript's ("twelve-week" -> "12 week")
                sv = dict(sc, text=txt); ev = V.evidence(sv, last=True, role="claim") if look == "takeaway" else V.evidence(sv)
                payload = (ev.get(look) or (None, None))[1]
                if payload is not None: break
            if look == "takeaway" and payload is None and sc.get("words"):
                payload = {"words": [{"w": re.sub(r"[^\w'-]", "", w["w"]).upper() or w["w"].upper(), "t0": float(w["t0"])} for w in sc["words"][:22]]}
            if payload is None:
                stat["not_buildable"] += 1; log(f"[REP THEORY CSV] row {ri}: look {look} needs {NEEDS.get(look, 'its shape')} in the sentence; the app chooses"); continue
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
