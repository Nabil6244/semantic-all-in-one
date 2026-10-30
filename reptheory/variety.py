"""Variety director for long Rep Theory videos (30 minutes and more): decides, scene by scene, which LOOK the narration gets so the viewer is not shown the same kind of picture for minutes on end.
Looks: stock (the planner's own: library figure, callout), 3d (a muscle clip of the 3D body, clip3d.py), flow (a manga picture generated from the beat, beat_art.py) and four code-drawn cards that need no
assets (cards.py): stat (a stated number in a ring), steps (a spoken sequence), versus (a stated comparison), takeaway (the key line, word by word).
Rules, all measured by `metrics`: a look is only offered where the beat's own words support it (a number, a muscle, a comparison, a sequence, a key line); the same look never runs more than twice in a row;
a look not used in the last scenes is preferred; 3D clips keep a minimum spacing and Flow pictures a budget (a 30-minute video must not cost 200 generations); a 3D scene is never followed by another.
Grounded scenes (tier boards, equations, held props, anatomy) are never replaced. Chapter banners mark each new part of a long video."""
from __future__ import annotations
import re
from typing import Dict, List, Optional

from . import clip3d as C3, narrative as N, planner as P
from .beat_art import SYNTH_RX

UPGRADABLE = {"callout", "trainee"}      # text-only or generic-figure scenes: the ones that look the same from minute to minute
TIME_UNITS = {"S", "SEC", "MIN", "H", "HR"}; COUNT_UNITS = {"SET", "REP", "WEEK", "DAY", "TIME", "ROUND", "X"}
VS_RX = (re.compile(r"(.{3,48}?)\s+(?:versus|vs\.?|rather than|instead of|compared (?:to|with))\s+(.{3,48})", re.I), re.compile(r"\bnot\s+(.{3,32}?),?\s+but\s+(.{3,32})", re.I),
         re.compile(r"(.{3,48}?)\s*,?\s+whereas\s+(.{3,48})", re.I), re.compile(r"(.{3,40}?)\s+(?:is|are)\s+(?:much |far |a lot )?(?:harder|easier|better|worse|stronger|weaker|safer|slower|faster)\s+than\s+(.{3,40})", re.I))
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
        m = rx.search(text)
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

def _takeaway(sc: dict, text: str, last: bool, role: str) -> Optional[dict]:
    ws = sc.get("words") or []; dur = sc["end"] - sc["start"]
    if not (4 <= len(ws) <= 20 and 2.5 <= dur <= 10.0): return None
    if not (last or role in ("hook", "claim", "cta", "mistake")): return None
    return {"words": [{"w": re.sub(r"[^\w'-]", "", w["w"]).upper() or w["w"].upper(), "t0": float(w["t0"])} for w in ws]}

def evidence(sc: dict, last: bool = False, role: str = "") -> Dict[str, tuple]:
    """look -> (support 0..1, payload) for what this scene's own words can honestly show."""
    text = sc.get("text", ""); ev: Dict[str, tuple] = {}
    if not text.strip() or SYNTH_RX.search(text): return ev
    g, by_ex = C3.groups_for(text)
    if g: ev["3d"] = (0.7 if by_ex else 0.9, None)
    for look, fn, base in (("stat", lambda: _stat(sc, text), 0.85), ("versus", lambda: _versus(sc, text), 0.8), ("steps", lambda: _steps(sc, text), 0.8), ("takeaway", lambda: _takeaway(sc, text, last, role), 0.9 if last else 0.6)):
        got = fn()
        if got: ev[look] = (base, got)
    if N.key_phrase(text, 3)[0]: ev["flow"] = (0.5, None)
    if "takeaway" not in ev and not any(pg.get("headline") or pg.get("value") or pg.get("chips") for pg in sc.get("pages", [])):      # a scene with nothing written on it would be a bare figure: its own words, lit as they are spoken, are the fallback
        ws = sc.get("words") or []
        if 4 <= len(ws) <= 22 and sc["end"] - sc["start"] >= 3.0: ev["takeaway"] = (0.55, {"words": [{"w": re.sub(r"[^\w'-]", "", w["w"]).upper() or w["w"].upper(), "t0": float(w["t0"])} for w in ws]})
    return ev

def direct(scenes: List[dict], *, total_s: Optional[float] = None, three_d: bool = True, flow: bool = True, budget: Optional[dict] = None, roles: Optional[Dict[int, str]] = None) -> dict:
    """Assigns `look` to every scene (and the payload of a card look, `want3d` + `cam3d` for a 3D clip, `chapter_card` for a new part). Returns the summary."""
    total = float(total_s or (scenes[-1]["end"] if scenes else 0)); b = budget or {}; gap3 = b.get("three_d_gap_s", min(20.0, max(6.0, total / 4))); max_flow = b.get("max_flow", max(2, int(total / 30)))
    hist: List[str] = []; last3 = -1e9; flows = 0; style_i = 0; roles = roles or {}
    for i, sc in enumerate(scenes):
        k = sc["kind"]; free = k in UPGRADABLE and not (k == "trainee" and sc.get("art") not in ("", None, "rep_stand_v1")) and not SYNTH_RX.search(sc.get("text", ""))
        if not free: hist.append(k); sc["look"] = k; continue
        ev = evidence(sc, last=i == len(scenes) - 1, role=roles.get(i, ""))
        if not three_d or sc["start"] - last3 < gap3 or hist[-1:] == ["3d"]: ev.pop("3d", None)
        if not flow or flows >= max_flow or hist[-2:] == ["flow", "flow"]: ev.pop("flow", None)
        ev["stock"] = (0.3, None); scored = []
        for look, (base, payload) in ev.items():
            if hist[-2:] == [look, look]: continue      # never a third in a row
            score = base + (0.5 if look not in hist[-3:] else 0.0) + (0.2 if look not in hist[-6:] else 0.0) - (0.8 if hist[-1:] == [look] else 0.0); scored.append((score, -list(ev).index(look), look, payload))
        if not scored: scored = [(0, 0, "stock", None)]
        _, _, look, payload = max(scored); sc["look"] = look; hist.append(look)
        if look == "3d": sc["want3d"] = True; sc["cam3d"] = C3.STYLES[style_i % len(C3.STYLES)]; style_i += 1; last3 = sc["end"]; sc["decisions"].append("variety: 3D body clip")
        elif look == "flow": flows += 1; sc["decisions"].append("variety: Flow picture from the narration")
        elif look in ("stat", "steps", "versus", "takeaway"):
            sc[look] = payload; sc["was_kind"] = k; sc["kind"] = look; sc["decisions"].append(f"variety: {look} card ({k} -> {look})")
            if look == "stat":
                for pg in sc["pages"]: pg["value"] = ""      # the ring shows the number: the callout column does not repeat it
            if look in ("steps", "versus", "takeaway"): sc["pages"] = []
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
    return metrics(scenes)

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
