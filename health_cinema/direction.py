"""Narration-aware visual direction for Health Cinema, reusing the app's own planner.

The script-to-scene planning is the app's `visual_director.VisualDirector` (the same one Normal video uses: Gemini when the user has enabled it and
holds a key, otherwise its deterministic fallback; results are cached in the project's state folder). Health Cinema only reads its output:
scene grouping of the narration, `asset_type`, search queries and a visual description per scene. It never calls Flow or any generator here."""
from __future__ import annotations
import re
from typing import Callable, Dict, List, Optional

def _norm(t: str) -> str: return re.sub(r"[^a-z0-9% ]+", "", t.lower()).strip()

def plan_visuals(script: str, settings: Optional[dict], state_dir: Optional[str], log: Callable[[str], None] = lambda m: None) -> List[dict]:
    """-> [{scene_id, narration, asset_type, queries, description, goal}] from the app's VisualDirector."""
    from visual_director.director import VisualDirector
    llm = None
    try:
        from visual_director.llm import GeminiLLM, gemini_configured
        st = settings or {}
        if st.get("gemini_enabled", True) and gemini_configured(st): llm = GeminiLLM(settings=st)
    except Exception as exc:
        log(f"Gemini planner not available ({str(exc)[:80]}); using the app's deterministic planner")
    import time
    plan = None
    for attempt in range(3):      # Gemini sometimes answers "high demand": wait and ask again before accepting the planner's rule-based fallback
        plan = VisualDirector(llm=llm, settings=settings or {}).plan(script, state_dir=state_dir)
        failed = llm is not None and any("gemini_failure" in str(w) or "deterministic fallback" in str(w) for w in (plan.warnings or []))
        for w in (plan.warnings or [])[:3]: log(f"visual director: {str(w)[:140]}")
        if not failed: break
        if attempt < 2:
            log(f"visual director: Gemini unavailable, retrying in {10 * (attempt + 1)} s ({attempt + 1}/2)"); time.sleep(10 * (attempt + 1))
    plan_source = "gemini" if llm is not None and not failed else "deterministic-fallback"
    out = []
    for sc in plan.scenes:
        out.append({"scene_id": str(sc.scene_id), "narration": sc.narration, "asset_type": (sc.asset_type or "").lower(), "queries": list(sc.search_queries or []),
                    "description": (sc.visual_description or "").strip(), "goal": (sc.visual_goal or "").strip(), "scene": sc, "plan_source": plan_source})
    return out

def align_to_sentences(dscenes: List[dict], sentences: List[dict]) -> List[List[dict]]:
    """Group the timed sentences under each director scene by text containment, in order. Sentences the director dropped or reworded join the
    previous group, so the grouping always covers every sentence exactly once."""
    groups: List[List[dict]] = [[] for _ in dscenes]; di = 0
    for s in sentences:
        ns = _norm(s["text"])
        while di < len(dscenes) - 1 and ns and ns not in _norm(dscenes[di]["narration"]) and ns in _norm(dscenes[di + 1]["narration"]): di += 1
        groups[di].append(s)
        if di < len(dscenes) - 1 and ns and _norm(dscenes[di]["narration"]).rstrip().endswith(ns): di += 1
    return groups


_TOK = re.compile(r"[a-z0-9%']+")
def _tokens(t: str) -> List[str]: return _TOK.findall(t.lower())

def _word_timeline(sentences: List[dict]) -> List[tuple]:
    """(token, t0, t1) for every spoken word. Real word times are used when the sentence carries them; otherwise the sentence's spoken interval is
    shared out by character length (an estimate: say so wherever it matters)."""
    out = []
    for s in sentences:
        ws = s.get("words")
        if ws:
            for w in ws:
                for tk in _tokens(str(w.get("w", ""))): out.append((tk, float(w["t0"]), float(w["t1"])))
            continue
        toks = _tokens(s["text"]); a, b = float(s["start"]), max(float(s["start"]) + 0.3, float(s["end"]) - 0.25)
        tot = sum(len(t) + 1 for t in toks) or 1; t = a
        for tk in toks:
            dur = (b - a) * (len(tk) + 1) / tot; out.append((tk, t, t + dur)); t += dur
    return out

def retime(dscenes: List[dict], sentences: List[dict]) -> List[List[dict]]:
    """Per director scene: its own sentences with start/end taken from the narration's word timeline (the director may regroup or split the spoken
    sentences, so alignment is by words, not by sentence). Scene boundaries are made contiguous; every spoken word belongs to exactly one scene."""
    words = _word_timeline(sentences); gi = 0; groups: List[List[dict]] = []
    for ds in dscenes:
        subs = [x.strip() for x in re.split(r"(?<=[.!?])\s+", ds["narration"]) if x.strip()]; scene_sents = []
        for sub in subs:
            toks = _tokens(sub); first = last = None
            for tk in toks:
                for look in range(gi, min(len(words), gi + 8)):
                    if words[look][0] == tk: gi = look; break
                else: look = min(gi, len(words) - 1)
                if first is None: first = look
                last = look; gi = min(look + 1, len(words) - 1) if look + 1 < len(words) else look
            if first is None or not words: continue
            scene_sents.append({"text": sub, "start": words[first][1], "end": words[last][2]})
        groups.append(scene_sents)
    flat = [s for g in groups for s in g]
    for i, s in enumerate(flat): s["end"] = max(s["end"], flat[i + 1]["start"] if i + 1 < len(flat) else s["end"])
    if flat: flat[0]["start"] = 0.0
    if flat and sentences: flat[-1]["end"] = max(flat[-1]["end"], float(sentences[-1]["end"]))
    return groups
