"""Ambience profile per scene: a deterministic, context-aware selector with Gemini kept for the scenes where the evidence conflicts.

What it weighs (not a keyword lookup): the narration AND the picture's own description (the picture is where the scene IS, the narration is
what is said about it), a bed that continues over scenes with no evidence of their own and fades back to the quiet room bed, the neighbouring scenes (a bed does not
flap between profiles on weak evidence), and which beds the sound library actually has. A scene with no evidence at all keeps the bed
that is already playing. Gemini is asked only about scenes whose two best profiles are close; its answer is accepted only if it is one of
those two (or the quiet room bed), so it cannot override the picture with an unrelated bed. settings "ai_planning": "full" asks Gemini for
every scene (the behaviour before this engine); "off" never asks."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from . import lexicon as L
from .core import DecisionCache, TELEMETRY, ai_allowed, ai_mode, run_batches, stable_key

TASK = "ambience"
NARRATION_W, PICTURE_W = 0.6, 1.0
HOLD = 2             # scenes a bed keeps playing with no new evidence before the quiet room bed takes over
STRONG = 0.9           # own evidence needed to leave the bed that is playing
CLOSE = 0.7            # second best within this share of the best = a conflict
ASK_BATCH = 25
PROMPT_VERSION = "1"
BASE = "room"          # the quiet bed used when nothing is known


def _available(catalog: Any) -> set:
    """Profiles the sound library can voice (some bed with one of the profile's tags and a real file)."""
    import smart_editing as se

    out = {BASE}
    try:
        pool = list(catalog._by_category.get("ambience", []))
        for profile, tags in se._AMBIENCE_PROFILES.items():
            if profile == "none":
                continue
            want = {t.lower() for t in tags}
            if any(want & set(e.tags) and e.resolved_path(catalog.root).is_file() for e in pool):
                out.add(profile)
    except Exception:
        out.update(L.ENVIRONMENT)
    return out


def _scene_scores(text: str, prompt: str, profiles: Sequence[str]) -> Dict[str, float]:
    nw = NARRATION_W if prompt.strip() else PICTURE_W   # with no picture description the narration is the only evidence there is
    return {p: nw * L.score_terms(text, L.ENVIRONMENT[p]) + PICTURE_W * L.score_terms(prompt, L.ENVIRONMENT[p])
            for p in profiles if p in L.ENVIRONMENT}


def _top2(scores: Mapping[str, float]) -> Tuple[Tuple[str, float], Tuple[str, float]]:
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    a = ranked[0] if ranked else (BASE, 0.0)
    b = ranked[1] if len(ranked) > 1 else (BASE, 0.0)
    return a, b


def decide(rows: Sequence[Mapping], aligned_rows: Sequence[Mapping], available: set) -> List[dict]:
    """The deterministic pass. -> [{scene_number, profile, source:'heuristic', confidence, conflict:[p1,p2] | None, own:{...}}] in scene order."""
    by_num = {str(r.get("scene_number")): r for r in rows}
    profiles = [p for p in L.ENVIRONMENT if p in available]
    own: List[Dict[str, float]] = []
    for a in aligned_rows:
        r = by_num.get(str(a.get("scene_number") or "")) or {}
        text = str(r.get("script_segment") or a.get("script_segment") or "")
        prompt = str(r.get("prompt") or r.get("stock") or "")
        own.append(_scene_scores(text, prompt, profiles))
    out: List[dict] = []
    current, quiet_for = BASE, 0
    for i, a in enumerate(aligned_rows):
        s = own[i]
        (p1, v1), (p2, v2) = _top2(s)
        conflict = None
        if v1 >= STRONG or (p1 == BASE and v1 >= 0.5):   # the quiet room bed is cheap and safe to switch to
            profile, conf, why = p1, min(1.0, 0.55 + 0.25 * (v1 - v2) + 0.2 * min(v1, 1.5) / 1.5), "own"
            if v2 >= CLOSE * v1 and v2 >= 0.5:   # two things named about equally: material, so the AI may decide
                conflict, conf = [p1, p2], 0.45
            quiet_for = 0
        else:   # no evidence of its own: the bed that is playing continues, then fades back to the quiet room bed
            quiet_for += 1
            if quiet_for > HOLD:
                current = BASE
            profile, conf, why = current, 0.4, "kept"
        current = profile
        out.append({"scene_number": str(a.get("scene_number") or ""), "profile": profile, "source": "heuristic", "confidence": round(conf, 2),
                    "conflict": conflict, "why": why})
    return out


# ---- the AI part -----------------------------------------------------------------------------------------------------------------

def _model() -> str:
    import os

    try:
        from visual_director.llm import DEFAULT_GEMINI_MODEL
    except Exception:
        DEFAULT_GEMINI_MODEL = "gemini"
    return os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL


def _ask(llm: Any, lines: List[str], valid: Sequence[Mapping]) -> Dict[str, str]:
    import smart_editing as se

    raw = llm.complete(se._AMBIENCE_SYSTEM, "Pick one ambience profile per scene.\n" + "\n".join(lines))
    payload = se._extract_json_object(raw)
    parsed = se._parse_ai_ambience(payload, valid)
    if not parsed:
        raise ValueError("the ambience answer could not be read")
    return {p["scene_number"]: p["profile"] for p in parsed}


def plan_profiles(rows: Sequence[Mapping], aligned_rows: Sequence[Mapping], *, settings: Optional[Mapping[str, Any]] = None, catalog: Any = None,
                  cache_dir: Optional[Path] = None, llm_factory: Optional[Callable[[], Any]] = None, workers: int = 2, retries: int = 1,
                  sleep: Callable[[float], None] = time.sleep) -> Tuple[List[dict], dict]:
    """-> (profiles in scene order, report). Every profile dict has scene_number, profile, source ('heuristic' | 'ai'), provenance
    ('rules' | 'ai' | 'cache'), confidence. Never raises for an AI problem: those scenes keep the deterministic profile."""
    t0 = time.monotonic()
    before = TELEMETRY.snapshot().get(TASK, {})
    settings = dict(settings or {})
    avail = _available(catalog) if catalog is not None else set(L.ENVIRONMENT)
    out = decide(rows, aligned_rows, avail)
    n = len(out)
    mode = ai_mode(settings)
    can_ask = ai_allowed(settings, "ambience") or (llm_factory is not None and mode != "off")
    full = mode == "full"
    for o in out:
        o["provenance"] = "rules"
    ask = [i for i, o in enumerate(out) if full or o["conflict"]] if can_ask else []
    cache = DecisionCache(Path(cache_dir) / "ambience_scenes.json" if cache_dir else None)
    by_num = {str(r.get("scene_number")): r for r in rows}

    def line(i: int) -> str:
        a = aligned_rows[i]
        r = by_num.get(str(a.get("scene_number") or "")) or {}
        text = str(r.get("script_segment") or a.get("script_segment") or "")[:120]
        prompt = str(r.get("prompt") or "")[:80]
        return f"scene {out[i]['scene_number']}: {text}" + (f" | visual: {prompt}" if prompt else "")

    model = _model()
    keys: Dict[int, str] = {}
    to_ask: List[int] = []
    for i in ask:
        prev_t = line(i - 1) if i > 0 else ""
        next_t = line(i + 1) if i + 1 < n else ""
        keys[i] = stable_key(model, PROMPT_VERSION, line(i), prev_t, next_t, full)
        if cache.has(keys[i]):
            _apply_ai(out[i], cache.get(keys[i]), full, "cache")
        else:
            to_ask.append(i)
    failed = 0
    if to_ask:
        batches = [to_ask[k:k + ASK_BATCH] for k in range(0, len(to_ask), ASK_BATCH)]
        local: Dict[int, Any] = {}

        def call(idxs: List[int]) -> Dict[str, str]:
            llm = local.setdefault(id(idxs), llm_factory() if llm_factory else _real_llm(settings))
            valid = [{"scene_number": out[i]["scene_number"]} for i in idxs]
            return _ask(llm, [line(i) for i in idxs], valid)

        for res, idxs in zip(run_batches(batches, call, workers=workers, retries=retries, sleep=sleep, task=TASK), batches):
            if not res.ok:
                failed += len(idxs)
                continue
            for i in idxs:
                answer = res.value.get(out[i]["scene_number"])
                cache.put(keys[i], answer)
                _apply_ai(out[i], answer, full, "ai")
        cache.flush()
    counts = {"cache": sum(o["provenance"] == "cache" for o in out), "ai": sum(o["provenance"] == "ai" for o in out)}
    TELEMETRY.add(TASK, decisions=n, cache=counts["cache"], ai=counts["ai"], rules=n - counts["cache"] - counts["ai"], wall_s=time.monotonic() - t0)
    print(TELEMETRY.line(TASK, before))
    report = {"scenes": n, "asked": len(ask), "failed": failed, **counts, "mode": mode, "seconds": round(time.monotonic() - t0, 2)}
    return out, report


def _real_llm(settings: Mapping[str, Any]) -> Any:
    from visual_director.llm import GeminiLLM

    return GeminiLLM(settings=settings, timeout=75.0)


def _apply_ai(o: dict, answer: Optional[str], full: bool, provenance: str) -> None:
    """Take Gemini's profile when it is one of the two profiles in conflict (or the quiet room bed); in "full" mode take it as given."""
    if not answer:
        return
    import smart_editing as se

    profile = se._normalize_ambience_profile(answer)
    allowed = set(o["conflict"] or []) | {BASE}
    if full or profile in allowed:
        o["profile"], o["source"], o["provenance"], o["confidence"] = profile, "ai", provenance, 0.8
