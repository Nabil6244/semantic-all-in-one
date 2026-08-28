"""Map QA failures to recovery actions."""

from __future__ import annotations

from typing import Iterable

from .models import RecommendedAction, VisualQAResult, scene_preserves_source_authority
from providers.base import SceneRow


def recommended_action_for(result: VisualQAResult, scene: SceneRow) -> RecommendedAction:
    reasons = " ".join(result.failure_reasons + result.warnings).lower()
    manual = scene_preserves_source_authority(scene)

    if "flow" in reasons and ("frozen" in reasons or "artifact" in reasons):
        return RecommendedAction.REGENERATE_FLOW if not manual else RecommendedAction.RETRY_SAME
    if "semantic mismatch" in reasons or "wrong subject" in reasons:
        return RecommendedAction.RETRY_SAME if manual else RecommendedAction.ALTERNATIVE
    if "duplicate asset" in reasons or "repeated visual" in reasons:
        return RecommendedAction.ALTERNATIVE if not manual else RecommendedAction.MANUAL_REVIEW
    if "substantially short" in reasons or "too short" in reasons:
        return RecommendedAction.COVERAGE_REPAIR if not manual else RecommendedAction.RETRY_SAME
    if "vertical framing" in reasons or "low resolution" in reasons:
        return RecommendedAction.ALTERNATIVE if not manual else RecommendedAction.RETRY_SAME
    if result.overall_score < 0.6:
        return RecommendedAction.RETRY_SAME if manual else RecommendedAction.ALTERNATIVE
    if result.overall_score < 0.8:
        return RecommendedAction.RERANK if not manual else RecommendedAction.KEEP
    return RecommendedAction.NONE


def apply_recommended_action(result: VisualQAResult, scene: SceneRow) -> VisualQAResult:
    result.recommended_action = recommended_action_for(result, scene)
    return result
