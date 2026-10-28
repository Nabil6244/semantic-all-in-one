"""Narration-aware scene planner for Health Cinema: sentences with times -> scenes (kind, visual, labels, sources, review flags, decision log).

Rules (small and explicit, no model calls):
  * scenes are sentence-aligned (never cut inside a spoken sentence) and grouped by topic up to the profile's max length; a group shorter than
    the profile's minimum is merged into a neighbour so on-screen text has reading time;
  * a statistic becomes a stat card only with a source attached (otherwise a plain text card + review flag; some profiles block the big number);
  * study/claim/myth wording becomes an evidence card (source shown, evidence level labelled);
  * a supported anatomy topic becomes a 3D scene (heart journey, chest journey); a topic with no anatomy asset (brain, pancreas, knee...) is NOT faked:
    it becomes a text card with the flag `no_anatomy_asset:<organ>`;
  * footage is used when the project has a clip for the scene (or the profile prefers it); otherwise a text card names what footage is wanted.
Profile weights break ties between eligible kinds; the planner never invents numbers, sources or anatomy.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional

from . import evidence, profiles as P

ANATOMY = {  # organ -> keywords; `template` is the journey the current asset supports (None = no asset yet)
    "heart": (["heart", "cardiac", "cardiovascular", "blood pressure", "artery", "arteries", "coronary", "ventricle", "atrium", "heartbeat", "circulation", "valve", "valves", "chambers", "pumping", "blood flow"], "heart_journey"),
    "lungs": (["lung", "lungs", "breathing", "breathe", "respiratory", "airway", "oxygen"], "chest_journey"),
    "brain": (["brain", "memory", "dementia", "alzheimer", "neuron", "cognitive"], None),
    "pancreas": (["pancreas", "insulin", "blood sugar", "glucose", "diabetes"], None),
    "joints": (["knee", "joint", "arthritis", "cartilage", "bone", "bones", "osteoporosis", "hip"], None),
    "liver": (["liver", "kidney", "kidneys"], None),
}
PEOPLE_RE = re.compile(r"\b(patients?|people|family|grandparents?|older adults?|walking|sleep|meal|diet|exercise|doctor|nurse|caregiver|morning|daily)\b", re.I)

@dataclass
class Scene:
    scene_no: int
    start: float
    end: float
    text: str
    kind: str = "text_card"
    profile: str = "medical_cinema"
    visual: dict = field(default_factory=dict)          # kind-specific: template/organ, card params, footage path ...
    labels: List[dict] = field(default_factory=list)
    sources: List[dict] = field(default_factory=list)
    flags: List[dict] = field(default_factory=list)
    evidence_level: str = "none"
    illustrative: str = ""
    chapter: str = ""
    decisions: List[str] = field(default_factory=list)
    sentences: List[dict] = field(default_factory=list)   # the timed narration sentences this scene covers (captions, timeline highlights)
    asset: dict = field(default_factory=dict)             # acquired footage provenance (source/provider/author/url/query), from the app's manifest
    dscene_ids: List[str] = field(default_factory=list)   # visual-director scene ids this scene was built from
    @property
    def duration(self) -> float: return max(0.0, self.end - self.start)
    def as_dict(self) -> dict: return asdict(self)

def detect_organ(text: str) -> Optional[str]:
    low = text.lower(); best, hit = None, 0
    for organ, (kw, _) in ANATOMY.items():
        n = sum(1 for k in kw if re.search(r"\b" + re.escape(k), low))
        if n > hit: best, hit = organ, n
    return best

def _choose(profile: P.Profile, sent: dict, ev: dict, organ: Optional[str], has_footage: bool, assets_ok: bool, log: List[str], history: Optional[List[str]] = None):
    w = profile.weights; sources = sent.get("sources") or []
    cands: Dict[str, float] = {}
    if ev["has_stat"]:
        if sources: cands["stat_card"] = w["stat_card"] + 1.5   # a sourced statistic is shown as one in every profile
        else: log.append("statistic without a source: no big-number card" + (" (profile blocks it)" if profile.block_unsourced_stats else "")); cands["text_card"] = w["text_card"] + 0.5
    if ev["has_study"] or ev["is_claim_or_myth"]:
        cands["evidence_card"] = w["evidence_card"] + (0.8 if sources else 0.2)   # without a source the card says "Source needed" and the scene is flagged
    if organ:
        tpl = ANATOMY[organ][1]
        if tpl and assets_ok: cands["anatomy_3d"] = w["anatomy_3d"] + 0.6
        elif tpl and not assets_ok: log.append(f"anatomy asset for {organ} unavailable here: 3D replaced by a text card"); cands["text_card"] = w["text_card"] + 0.4
        else: log.append(f"no anatomy asset for {organ}: not faked; text card instead"); cands["text_card"] = w["text_card"] + 0.4
    if has_footage: cands["footage"] = w["footage"] + 0.7
    elif PEOPLE_RE.search(sent["text"]) and w["footage"] >= 0.8: cands["footage"] = w["footage"] * 0.6
    if not cands: cands["text_card"] = w["text_card"] + 0.1
    if history is not None and profile.id in P.VARIETY_PROFILES:   # variety rule: favour kinds not used yet, avoid a third identical scene in a row
        for k in cands:
            if k not in history: cands[k] += 0.5
            if len(history) >= 2 and history[-1] == history[-2] == k: cands[k] -= 1.0
    kind = max(cands, key=lambda k: (cands[k], k)); return kind, cands

def plan(sentences: List[dict], profile_id: str = P.DEFAULT_PROFILE, *, assets_ok: bool = False, footage_for: Optional[Callable[[dict], Optional[str]]] = None,
         title: str = "") -> Dict:
    """sentences: [{text, start, end, sources?, chapter?, footage?}] -> {"scenes": [Scene], "log": [...], "profile": id}."""
    prof = P.get_profile(profile_id); log: List[str] = []; raw = []
    for i, s in enumerate(sentences):
        text = (s.get("text") or "").strip()
        if not text or float(s["end"]) <= float(s["start"]): continue
        ev = evidence.analyze(text, s.get("sources")); organ = detect_organ(text)
        fp = s.get("footage") or (footage_for(s) if footage_for else None)
        local: List[str] = []; kind, cands = _choose(prof, s, ev, organ, bool(fp), assets_ok, local, [r["kind"] for r in raw])
        raw.append({"s": s, "text": text, "ev": ev, "organ": organ, "kind": kind, "footage": fp, "log": local, "cands": cands})
    # group neighbours that share kind+organ (same visual idea), up to max_scene_s; keep anatomy/evidence/stat scenes single-sentence
    groups: List[List[dict]] = []
    for r in raw:
        g = groups[-1] if groups else None
        joinable = g and g[-1]["kind"] == r["kind"] == "text_card" or (g and g[-1]["kind"] == r["kind"] == "anatomy_3d" and g[-1]["organ"] == r["organ"]) or (g and g[-1]["kind"] == r["kind"] == "footage")
        if joinable and float(r["s"]["end"]) - float(g[0]["s"]["start"]) <= prof.max_scene_s: g.append(r)
        else: groups.append([r])
    # merge too-short groups into a neighbour (reading time) unless first/only
    merged: List[List[dict]] = []
    for g in groups:
        dur = float(g[-1]["s"]["end"]) - float(g[0]["s"]["start"])
        if merged and dur < prof.min_scene_s and merged[-1][-1]["kind"] != "anatomy_3d":
            merged[-1].extend(g); log.append(f"short scene ({dur:.1f}s) merged into the previous one")
        else: merged.append(g)
    scenes: List[Scene] = []
    for n, g in enumerate(merged, 1):
        first = g[0]; text = " ".join(r["text"] for r in g); start = float(g[0]["s"]["start"]); end = float(g[-1]["s"]["end"])
        sources = [x for r in g for x in (r["s"].get("sources") or [])]
        ev = evidence.analyze(text, sources); kind = first["kind"]
        sc = Scene(n, start, end, text, kind, prof.id, sources=sources, flags=list(ev["flags"]), evidence_level=ev["evidence_level"], chapter=first["s"].get("chapter", ""),
                   decisions=[f"{kind} (candidates {', '.join(f'{k}={v:.1f}' for k, v in sorted(first['cands'].items()))})"] + first["log"])
        if kind == "anatomy_3d":
            organ = first["organ"]; sc.visual = {"organ": organ, "template": ANATOMY[organ][1]}; sc.illustrative = evidence.illustrative_label(kind)
        elif kind == "footage": sc.visual = {"path": first["footage"] or "", "want": text[:90]}
        elif kind == "stat_card": sc.visual = {"number": (ev["numbers"] or [""])[0], "context": text}
        elif kind == "evidence_card": sc.visual = {"claim": text, "heading": prof.evidence_label}
        else: sc.visual = {"text": text, "beats": [{"text": r["text"], "t0": round(float(r["s"]["start"]) - start, 3)} for r in g]}
        if first["organ"] and ANATOMY[first["organ"]][1] is None:
            sc.flags.append({"code": f"no_anatomy_asset:{first['organ']}", "severity": "note", "message": f"No licensed 3D asset for the {first['organ']} yet; shown as text."})
        if kind == "footage" and not first["footage"]:
            sc.flags.append({"code": "footage_missing", "severity": "note", "message": "No footage matched; a text card is shown until a clip is attached."}); sc.kind = "text_card"; sc.visual = {"text": text, "want_footage": True}
        scenes.append(sc)
    if title and scenes and not scenes[0].chapter: scenes[0].chapter = title
    return {"scenes": scenes, "log": log, "profile": prof.id}


# ---- directed planning: the app's VisualDirector grouping + asset hints -> scene kinds -------------------------------------------------------
EVERY_RE = re.compile(r"\bevery\s+(\d+)\s+(second|minute|hour|day|week)s?\b", re.I)
PCT_RE = re.compile(r"(?:(up to|about|over|nearly|around|more than)\s+)?(\d+(?:\.\d+)?)\s?(?:%|percent)", re.I)
BRAIN_RE = re.compile(r"\b(brain|carotid|cerebral|head)\b", re.I)
EYE_RE = re.compile(r"\b(eyes?|vision|retina|optic|sight|eyesight)\b", re.I)
TIME_RE = re.compile(r"(\b(?:one|that|this)\s+(?:morning|afternoon|evening|night)\b|\b(?:\d+|one|two|three|four|five|six|several|a few)\s+(?:seconds?|minutes?|hours?|days?|weeks?|months?)(?:\s+(?:later|after))?\b|\b(?:\d+|one|two|three|four|five|six|several|a few)\s+years?\s+(?:later|after)\b)", re.I)
MIN_3D_S = {"heart_journey": 9.0, "chest_journey": 8.0, "brain_journey": 10.0, "eye_journey": 8.0}

def _sentences_text(g): return " ".join(x["text"].strip() for x in g)

def plan_directed(sentences: List[dict], profile_id: str, dscenes: List[dict], template_ready: Callable[[str], bool], *, allow_footage: bool = True, title: str = "") -> Dict:
    """Scenes from the director's grouping. Rules (first match wins): 'every N <unit>' -> counter; a percentage -> bar; brain/carotid -> brain journey; eye/vision -> eye
    journey; heart/lungs -> their journeys; director footage query -> footage; else a typographic card. Each 3D template is used at most once per video, 3D scenes are
    extended over the next scenes to reach a watchable length, and a run of time-marked story sentences becomes one timeline."""
    from . import direction
    prof = P.get_profile(profile_id); log: List[str] = []
    groups = direction.retime(dscenes, sentences); items = []
    for d, g in zip(dscenes, groups):
        if not g: continue
        ev_i = [i for i, x in enumerate(g) if EVERY_RE.search(x["text"])]; pc_i = [i for i, x in enumerate(g) if PCT_RE.search(x["text"])]
        parts = [g]
        if ev_i and pc_i and max(ev_i) < min(pc_i): parts = [g[:max(ev_i) + 1], g[max(ev_i) + 1:]]      # a frequency and a percentage are two different graphics
        for part in parts:
            if part: items.append({"d": d, "g": part, "start": float(part[0]["start"]), "end": float(part[-1]["end"]), "text": _sentences_text(part)})
    # a repeated frequency line ("Every 40 seconds.") belongs to the counter before it
    k = 1
    while k < len(items):
        if EVERY_RE.search(items[k]["text"]) and EVERY_RE.search(items[k - 1]["text"]) and not PCT_RE.search(items[k]["text"]):
            items[k - 1]["g"] += items[k]["g"]; items[k - 1]["end"] = items[k]["end"]; items[k - 1]["text"] += " " + items[k]["text"]; del items[k]
        else: k += 1
    used3d = set()
    def organ_template(text):
        low = text.lower()
        for rx, tpl in ((EYE_RE, "eye_journey"), (BRAIN_RE, "brain_journey")):
            if rx.search(text) and tpl not in used3d and template_ready(tpl): return tpl
        org = detect_organ(text)
        if org and ANATOMY[org][1] and ANATOMY[org][1] not in used3d and template_ready(ANATOMY[org][1]): return ANATOMY[org][1]
        return None
    for it in items:
        text, d, why = it["text"], it["d"], []
        m = EVERY_RE.search(text); pc = None
        for sent in it["g"]:
            pc = pc or PCT_RE.search(sent["text"])
        tpl = organ_template(text)
        if m:
            sent = next(x for x in it["g"] if EVERY_RE.search(x["text"])); ev = re.search(r"\b(?:has|have|suffers?|dies?)\s+an?\s+(\w+)", text, re.I)
            it["kind"] = "counter_card"; it["visual"] = {"interval": int(m.group(1)), "unit": m.group(2).lower() + "s", "context": sent["text"].strip(), "event": (ev.group(1) + "s") if ev else "events"}
            why.append("a stated frequency -> animated counter (compressed time, labelled)")
        elif pc:
            sent = next(x for x in it["g"] if PCT_RE.search(x["text"])); it["kind"] = "bar_card"
            it["visual"] = {"value": float(pc.group(2)), "qualifier": ((pc.group(1) or "")[:1].upper() + (pc.group(1) or "")[1:].lower()), "context": sent["text"].strip()}
            why.append("a percentage -> animated bar")
        elif tpl:
            it["kind"] = "anatomy_3d"; it["visual"] = {"template": tpl, "organ": {"brain_journey": "brain", "eye_journey": "eye", "heart_journey": "heart", "chest_journey": "lungs"}[tpl]}; used3d.add(tpl)
            why.append(f"anatomy topic -> {tpl}")
        elif allow_footage and d["asset_type"] in ("stock_video", "youtube_video", "archive_video", "nasa_video") and (d["queries"] or d["description"]):
            it["kind"] = "footage"; it["visual"] = {"scene_id": d["scene_id"], "query": (d["queries"] or [d["description"]])[0], "asset_type": d["asset_type"]}
            why.append(f"director asked for {d['asset_type']}: {it['visual']['query'][:50]}")
        else:
            it["kind"] = "text_card"; it["visual"] = {"text": text, "beats": [{"text": x["text"].strip(), "t0": round(float(x["start"]) - it["start"], 3)} for x in it["g"]]}
            why.append("no suitable footage or data graphic: typographic card")
        it["why"] = why
    # extend 3D scenes forward to a watchable length (never over a data graphic)
    i = 0
    while i < len(items):
        it = items[i]
        if it["kind"] == "anatomy_3d":
            need = MIN_3D_S[it["visual"]["template"]]
            while it["end"] - it["start"] < need and i + 1 < len(items) and items[i + 1]["kind"] in ("footage", "text_card", "anatomy_3d"):
                nx = items.pop(i + 1); it["g"] += nx["g"]; it["end"] = nx["end"]; it["text"] += " " + nx["text"]; it["d"] = it["d"]; it["why"].append("extended over the next scene for watchable length")
        i += 1
    # timeline: a story with time-ordered markers ("one afternoon ... 3 days later ... 4 months") becomes one timeline over the scenes from the first
    # "N <unit> later" marker to the last duration marker; earlier markers (even inside a 3D scene) appear first, as already-happened events
    marks = []
    for k, it in enumerate(items):
        for x in it["g"]:
            m = TIME_RE.search(x["text"])
            if m: marks.append((k, x, m.group(1)))
    later = [t for t in marks if re.search(r"\b(later|after)\b", t[2], re.I)]
    if later and len(marks) >= 3:
        k0 = later[0][0]; ks = [t[0] for t in marks if t[0] >= k0]; k1 = max(ks)
        if all(items[j]["kind"] in ("footage", "text_card") for j in range(k0, k1 + 1)):
            evs_src = [t for t in marks if t[0] >= max(0, k0 - 4)]
            merged = items[k0]
            for it2 in items[k0 + 1:k1 + 1]: merged["g"] += it2["g"]; merged["end"] = it2["end"]; merged["text"] += " " + it2["text"]
            del items[k0 + 1:k1 + 1]
            events = []; seen = set(); pre = 0
            for _, x, when in sorted(evs_src, key=lambda t: float(t[1]["start"])):
                key = when.strip().lower()
                if key in seen: continue
                seen.add(key); st = float(x["start"])
                if st < merged["start"]: t0 = round(0.15 + 0.3 * pre, 3); pre += 1
                else: t0 = round(max(st - merged["start"], 0.15 + 0.3 * pre), 3)       # never before the events that came earlier in the story
                w = when.strip(); events.append({"when": w[0].upper() + w[1:], "label": _short(x["text"].strip(), 64), "t0": t0})
            if len(events) >= 3:
                merged["kind"] = "timeline_card"; merged["visual"] = {"events": events}; merged["why"] = ["time-marked story sentences -> timeline of the narration's own events"]
    scenes: List[Scene] = []
    for n, it in enumerate(items, 1):
        sc_sources = []
        ev = evidence.analyze(it["text"], sc_sources)
        sc = Scene(n, it["start"], it["end"], it["text"], it["kind"], prof.id, visual=it["visual"], flags=list(ev["flags"]), evidence_level=ev["evidence_level"], decisions=it["why"],
                   sentences=[{"text": x["text"], "start": float(x["start"]), "end": float(x["end"])} for x in it["g"]], dscene_ids=[it["d"]["scene_id"]])
        if it["kind"] == "anatomy_3d": sc.illustrative = evidence.illustrative_label("anatomy_3d")
        if it["kind"] in ("counter_card", "bar_card") and not sc.sources: sc.flags.append({"code": "figure_unsourced", "severity": "review", "message": "This figure is shown with 'Source needed': attach the study, population and year before publishing."})
        scenes.append(sc)
    if scenes: scenes[0].chapter = title
    return {"scenes": scenes, "log": log, "profile": prof.id}

def _short(t: str, n: int) -> str: return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "\u2026"
