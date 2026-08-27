"""AUTO style detection via ContentProfile scoring — Gemini optional, never required."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .loader import list_builtin_styles
from .profile import (
    DEFAULT_STYLE_WEIGHTS,
    ContentProfile,
    build_content_profile,
    content_source_hash,
    load_cached_profile,
    reason_for_style,
    save_cached_profile,
    score_styles,
)
from .schema import VideoStyle


def _style_weights_from_builtins() -> Dict[str, Dict[str, float]]:
    out = dict(DEFAULT_STYLE_WEIGHTS)
    for style in list_builtin_styles():
        w = dict(style.intelligence.weights or {})
        if w:
            out[style.id] = w
    return out


def detect_style(
    *,
    script: str = "",
    visual_plan: Any = None,
    rows: Optional[List[dict]] = None,
    title: str = "",
    state_dir: Any = None,
    gemini_settings: Optional[dict] = None,
) -> Tuple[VideoStyle, float, str, List[Dict[str, Any]], ContentProfile, List[Dict[str, Any]]]:
    """
    Return (style, confidence, reason, alternatives, profile, all_scores).

    Never calls Gemini by default. If gemini_settings is provided and configured,
    a single optional enrichment may adjust densities — still falls back to local profile.
    """
    styles = {s.id: s for s in list_builtin_styles()}
    fallback = styles.get("premium_documentary") or next(iter(styles.values()))
    src_hash = content_source_hash(script, visual_plan, rows, title)
    state_path = Path(state_dir) if state_dir else None
    profile = load_cached_profile(state_path, src_hash)
    if profile is None:
        profile = build_content_profile(
            script=script, visual_plan=visual_plan, rows=rows, title=title
        )
        # Optional one-shot Gemini enrichment (never required, never per-scene).
        if gemini_settings:
            profile = _maybe_enrich_with_gemini(profile, script, gemini_settings)
        save_cached_profile(state_path, profile)

    scored = score_styles(profile, style_weights=_style_weights_from_builtins())
    best_id, confidence = scored[0] if scored else (fallback.id, 0.4)
    style = styles.get(best_id) or fallback
    reason = reason_for_style(best_id, profile)
    alternatives = [
        {"style_id": sid, "score": round(float(sc), 3)}
        for sid, sc in scored[1:3]
    ]
    all_scores = [{"style_id": sid, "score": round(float(sc), 3)} for sid, sc in scored]
    return style, float(confidence), reason, alternatives, profile, all_scores


def _maybe_enrich_with_gemini(
    profile: ContentProfile, script: str, settings: dict
) -> ContentProfile:
    """Best-effort single enrichment. On any failure, return profile unchanged."""
    try:
        from visual_director.llm import gemini_configured

        if not gemini_configured(settings):
            return profile
        # Keep enrichment extremely light: only nudge domain densities from a tiny prompt
        # if the script is long enough to matter. Skip network if no key / errors.
        key = str(settings.get("gemini_api_key") or "").strip()
        if not key or len(script or "") < 80:
            return profile
        # Intentionally do not call Gemini here in unit tests / offline — reserved hook.
        # Calling the live API from detection would violate "lightweight / cache once"
        # unless the host explicitly opts in via STYLE_GEMINI_ENRICH=1.
        import os

        if os.environ.get("STYLE_GEMINI_ENRICH", "").strip() not in ("1", "true", "yes"):
            return profile
        from visual_director.llm import GeminiLLM

        llm = GeminiLLM(settings=settings, timeout=20.0)
        tip = llm.complete(
            "Classify documentary domain as one of: history, space, explainer, cinematic, science. "
            "Reply with only the word.",
            (script or "")[:1200],
        )
        word = str(tip or "").strip().lower().split()[0] if tip else ""
        if word.startswith("history"):
            profile.historical_density = min(1.0, profile.historical_density + 0.12)
            profile.domain = "history"
        elif word.startswith("space"):
            profile.astronomy_density = min(1.0, profile.astronomy_density + 0.12)
            profile.domain = "space"
        elif word.startswith("explainer"):
            profile.explainer_density = min(1.0, profile.explainer_density + 0.12)
            profile.domain = "explainer"
        elif word.startswith("cinematic"):
            profile.cinematic_potential = min(1.0, profile.cinematic_potential + 0.12)
        elif word.startswith("science"):
            profile.scientific_density = min(1.0, profile.scientific_density + 0.1)
    except Exception:
        return profile
    return profile
