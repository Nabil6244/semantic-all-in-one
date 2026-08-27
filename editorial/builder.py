"""Build EditorialPlan from aligned rows + optional VisualDirector plan (heuristic fallback)."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from video_generator import _scene_display_timeline, is_distinctive, split_words

from .schema import (
    HOOK_WINDOW_S,
    CameraStyle,
    EditorialPlan,
    EditorialScene,
    Purpose,
    _norm_camera,
    _norm_transition,
)

_IMPORTANCE_SCORE = {"high": 0.85, "medium": 0.55, "low": 0.35}
_TREATMENT_TO_CAMERA = {
    "push_in": "push_in",
    "push": "push_in",
    "slow_push": "push_in",
    "pull_out": "pull_out",
    "pull": "pull_out",
    "static": "static",
    "hold": "hold",
    "drift": "subtle_drift",
    "subtle_drift": "subtle_drift",
    "pan": "subtle_drift",
}
_HOOK_CUE = re.compile(
    r"\b(secret|shocking|never|why|how|what if|imagine|story|truth|discover)\b",
    re.I,
)
_EMOTION_CUE = re.compile(
    r"\b(love|hate|fear|heart|pain|joy|angry|sad|beautiful|devastating)\b",
    re.I,
)
_EVIDENCE_CUE = re.compile(
    r"\b(study|research|data|percent|million|scientists|found|proof|evidence)\b",
    re.I,
)
_OUTRO_CUE = re.compile(
    r"\b(thank|subscribe|finally|in conclusion|remember|goodbye|see you)\b",
    re.I,
)
_CAMERA_POOL: Tuple[CameraStyle, ...] = (
    "push_in",
    "pull_out",
    "static",
    "subtle_drift",
    "hold",
)


def _visual_scene_lookup(visual_plan: Any) -> Dict[str, Any]:
    if visual_plan is None:
        return {}
    scenes = getattr(visual_plan, "scenes", None) or []
    out: Dict[str, Any] = {}
    for scene in scenes:
        sid = str(getattr(scene, "scene_id", "") or "")
        if sid:
            out[sid] = scene
    return out


def _variety_key(
    *,
    asset_type: str,
    prompt: str,
    visual_description: str,
    provider: str,
) -> str:
    blob = " ".join(
        p.lower()
        for p in (asset_type, provider, prompt, visual_description)
        if p
    )
    tokens = sorted({t for t in split_words(blob) if is_distinctive(t) or len(t) > 4})
    if not tokens:
        return hashlib.sha256(blob.encode()).hexdigest()[:12]
    return "|".join(tokens[:6])


def _infer_purpose(
    *,
    index: int,
    total: int,
    start: float,
    text: str,
    importance: str,
) -> Purpose:
    if index == 0 or start < 3.0:
        return "hook"
    if index == total - 1 or _OUTRO_CUE.search(text):
        return "outro"
    if _EMOTION_CUE.search(text):
        return "emotion"
    if _EVIDENCE_CUE.search(text):
        return "evidence"
    if _HOOK_CUE.search(text) and start < HOOK_WINDOW_S:
        return "hook"
    if importance == "high" and start < HOOK_WINDOW_S * 1.5:
        return "hook"
    if index > 0 and len(text.split()) < 8:
        return "transition"
    return "context"


def _attention_score(
    *,
    purpose: Purpose,
    importance: str,
    start: float,
    text: str,
    index: int,
) -> float:
    base = _IMPORTANCE_SCORE.get(importance, 0.55)
    if purpose == "hook":
        base = max(base, 0.78)
    if purpose == "emotion":
        base = max(base, 0.72)
    if purpose == "evidence":
        base = max(base, 0.65)
    if start < HOOK_WINDOW_S:
        hook_boost = 1.0 - (start / HOOK_WINDOW_S) * 0.35
        base = min(1.0, base + hook_boost * 0.22)
    if _HOOK_CUE.search(text):
        base = min(1.0, base + 0.12)
    caps = sum(1 for w in re.findall(r"[A-Z]{2,}", text) if len(w) >= 3)
    if caps:
        base = min(1.0, base + min(0.15, caps * 0.05))
    if index == 0:
        base = min(1.0, base + 0.08)
    return round(min(1.0, max(0.0, base)), 3)


def _treatment_camera(visual_treatment: str) -> Optional[CameraStyle]:
    key = (visual_treatment or "").strip().lower().replace(" ", "_")
    mapped = _TREATMENT_TO_CAMERA.get(key)
    return mapped  # type: ignore[return-value]


def _pick_camera_style(
    *,
    index: int,
    attention: float,
    purpose: Purpose,
    start: float,
    visual_treatment: str,
    prev_camera: Optional[str],
    prev_variety: Optional[str],
    variety_key: str,
) -> CameraStyle:
    from_treatment = _treatment_camera(visual_treatment)
    if from_treatment:
        candidate = from_treatment
    elif purpose == "hook" or (start < HOOK_WINDOW_S and attention >= 0.7):
        candidate = "push_in" if index % 2 == 0 else "subtle_drift"
    elif purpose == "outro":
        candidate = "pull_out" if attention >= 0.5 else "hold"
    elif purpose == "emotion":
        candidate = "subtle_drift"
    elif attention >= 0.75:
        candidate = "push_in"
    elif attention <= 0.4:
        candidate = "hold"
    else:
        candidate = _CAMERA_POOL[index % len(_CAMERA_POOL)]

    # Neighbor variety: avoid repeating camera + variety key.
    if prev_camera == candidate and prev_variety == variety_key:
        alts = [c for c in _CAMERA_POOL if c != prev_camera]
        if alts:
            candidate = alts[index % len(alts)]
    elif prev_camera == candidate:
        alts = [c for c in _CAMERA_POOL if c != prev_camera]
        if alts:
            candidate = alts[0]

    return _norm_camera(candidate)


def _infer_transition_in(
    *,
    index: int,
    start: float,
    purpose: Purpose,
    attention: float,
    visual_transition: str,
) -> Optional[str]:
    from_plan = _norm_transition(visual_transition)
    if from_plan:
        return from_plan
    if index == 0:
        return "fade"
    if start < HOOK_WINDOW_S and purpose in ("hook", "emotion") and attention >= 0.65:
        return "dissolve" if index % 2 else "fade"
    return None


def _heuristic_ambience(text: str, prompt: str) -> str:
    blob = f"{text} {prompt}".lower()
    if any(w in blob for w in ("rain", "storm", "thunder")):
        return "rain"
    if any(w in blob for w in ("ocean", "beach", "river", "water", "shore")):
        return "water"
    if any(w in blob for w in ("forest", "nature", "wind", "bird", "wild")):
        return "nature"
    if any(w in blob for w in ("city", "street", "urban", "downtown")):
        return "city"
    if any(w in blob for w in ("crowd", "market", "people", "stadium")):
        return "crowd"
    if any(w in blob for w in ("traffic", "highway", "road", "car")):
        return "traffic"
    if any(w in blob for w in ("train", "subway", "airport", "plane")):
        return "transport"
    if any(w in blob for w in ("fire", "campfire", "fireplace")):
        return "fire"
    if any(w in blob for w in ("office", "computer", "server", "lab", "tech")):
        return "technology"
    if any(w in blob for w in ("dark", "mystery", "tension", "horror")):
        return "atmospheric"
    return "room"


def _row_context(row: Mapping[str, Any], aligned: Mapping[str, Any]) -> Tuple[str, str, str]:
    text = str(row.get("script_segment") or aligned.get("script_segment") or "")
    prompt = str(row.get("prompt") or row.get("stock") or "")
    asset_type = str(row.get("asset_type") or "")
    return text, prompt, asset_type


def build_editorial_plan(
    rows: Sequence[dict],
    aligned_rows: Sequence[dict],
    audio_end: float,
    *,
    visual_plan: Any = None,
    settings_key: str = "",
    audio_key: str = "",
) -> EditorialPlan:
    """Build plan using display timeline windows (matches render + ambience)."""
    windows = _scene_display_timeline(list(aligned_rows), float(audio_end))
    by_num = {str(r.get("scene_number")): r for r in rows}
    visual_by_id = _visual_scene_lookup(visual_plan)
    total = len(aligned_rows)
    scenes: List[EditorialScene] = []
    prev_camera: Optional[str] = None
    prev_variety: Optional[str] = None

    for i, aligned in enumerate(aligned_rows):
        sn = str(aligned.get("scene_number") or "")
        row = by_num.get(sn) or {}
        vs = visual_by_id.get(sn)
        start, end = windows[i] if i < len(windows) else (0.0, float(audio_end))
        duration = max(0.05, end - start)
        text, prompt, asset_type = _row_context(row, aligned)

        importance = str(getattr(vs, "importance", None) or "medium")
        visual_goal = str(getattr(vs, "visual_goal", "") or "")
        visual_description = str(getattr(vs, "visual_description", "") or "")
        visual_treatment = str(getattr(vs, "visual_treatment", "") or "")
        visual_transition = str(getattr(vs, "transition", "") or "")
        provider = str(getattr(vs, "provider_preference", None) or asset_type or "")

        if not asset_type:
            asset_type = str(getattr(vs, "asset_type", "") or "")

        variety_key = _variety_key(
            asset_type=asset_type,
            prompt=prompt,
            visual_description=visual_description,
            provider=provider,
        )
        purpose = _infer_purpose(
            index=i,
            total=total,
            start=start,
            text=text,
            importance=importance,
        )
        attention = _attention_score(
            purpose=purpose,
            importance=importance,
            start=start,
            text=text,
            index=i,
        )
        camera = _pick_camera_style(
            index=i,
            attention=attention,
            purpose=purpose,
            start=start,
            visual_treatment=visual_treatment,
            prev_camera=prev_camera,
            prev_variety=prev_variety,
            variety_key=variety_key,
        )
        transition_in = _infer_transition_in(
            index=i,
            start=start,
            purpose=purpose,
            attention=attention,
            visual_transition=visual_transition,
        )
        ambience = _heuristic_ambience(text, prompt)
        pacing_bias = (
            "fast" if attention >= 0.75 else ("slow" if attention <= 0.4 else "normal")
        )
        if purpose in ("explanation", "evidence") and attention < 0.65:
            pacing_bias = "slow"
        music_role = "lift" if purpose == "hook" else ("drop" if purpose == "outro" else "hold")
        if purpose == "emotion":
            music_role = "drop"

        scenes.append(
            EditorialScene(
                scene_number=sn,
                start=round(start, 4),
                end=round(end, 4),
                duration=round(duration, 4),
                narration_excerpt=text[:240],
                purpose=purpose,
                attention_score=attention,
                importance=importance,
                asset_type_intent=asset_type or provider,
                camera_style=camera,
                visual_variety_key=variety_key,
                visual_goal=visual_goal,
                visual_description=visual_description,
                visual_treatment=visual_treatment,
                ambience_profile=ambience,
                ambience_intensity=1.0,
                transition_in=transition_in,
                pacing_bias=pacing_bias,  # type: ignore[arg-type]
                music_role=music_role,  # type: ignore[arg-type]
            )
        )
        prev_camera = camera
        prev_variety = variety_key

    plan = EditorialPlan(
        audio_key=audio_key,
        settings_key=settings_key,
        audio_end=float(audio_end),
        scenes=scenes,
    )

    # Directors enrich the plan (still no Gemini required — heuristics only).
    from .audio_director import enrich_scene_audio_fields
    from .music_director import assign_film_sections
    from .pacing import apply_pacing_camera_energy, finalize_transitions

    enrich_scene_audio_fields(plan)
    apply_pacing_camera_energy(plan)
    finalize_transitions(plan)
    sections = assign_film_sections(plan)
    plan.film_sections = [s.to_dict() for s in sections]
    return plan
