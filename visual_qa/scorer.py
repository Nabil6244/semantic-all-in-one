"""Combine QA signals into VisualQAResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Set

from providers.base import AssetResult, SceneRow
from providers.media_quality.scoring import is_archival_provider
from style_engine.schema import ResolvedStyle
from style_engine.visual_selection import SelectionHistory

from .cache import get_cached, store_cached
from .coverage import narration_duration_from_coverage, score_duration_coverage
from .flow_qa import check_flow_temporal_quality
from .frame_sampler import sample_frames
from .models import (
    PASS_THRESHOLD,
    VisualQAResult,
    VisualQAStatus,
    scene_preserves_source_authority,
    status_from_score,
)
from .repetition import score_repetition
from .retry import apply_recommended_action
from .semantic import metadata_semantic_score, needs_vision_inspection, vision_semantic_score
from .style_fit import is_archival_context, score_style_fit, style_id_from_resolved
from .technical import check_technical


def evaluate_scene_asset(
    scene: SceneRow,
    result: AssetResult,
    *,
    images_dir: Optional[Path] = None,
    coverage_plan: Optional[dict] = None,
    selection_history: Optional[SelectionHistory] = None,
    resolved: Optional[ResolvedStyle] = None,
    settings: Optional[dict] = None,
    project_asset_ids: Optional[Set[str]] = None,
    enable_vision: bool = True,
) -> VisualQAResult:
    """Run tiered Visual QA on a finalized asset."""
    key = str(scene.scene_number)
    meta = result.metadata or {}
    asset_id = str(meta.get("provider_asset_id") or meta.get("asset_id") or "")
    style_id = style_id_from_resolved(resolved)

    if not result.ok or result.path is None:
        from .models import RecommendedAction

        return VisualQAResult(
            scene_number=key,
            asset_id=asset_id,
            status=VisualQAStatus.SKIPPED,
            recommended_action=RecommendedAction.NONE,
        )

    path = Path(result.path)
    if images_dir is not None:
        cached = get_cached(images_dir, path, key, style_id=style_id)
        if cached is not None:
            return cached

    provider = str(meta.get("provider") or getattr(result.source, "value", "") or "")
    asset_type = str(scene.asset_type or meta.get("asset_type") or "")
    archival = is_archival_context(resolved, provider=provider, asset_type=asset_type)

    tech = check_technical(path, result.media_type, is_archival=archival)
    semantic, sem_warn = metadata_semantic_score(scene, result, resolved)

    cache_dir = Path(images_dir) / ".visual_qa_frames" if images_dir else None
    frames = sample_frames(path, result.media_type, cache_dir=cache_dir, duration=tech.duration)

    source_val = getattr(result.source, "value", str(result.source or "")).lower()
    if source_val in ("flow_video", "flow_image", "video", "image"):
        flow_score, flow_warn = check_flow_temporal_quality(frames)
        semantic = semantic * 0.65 + flow_score * 0.35
        sem_warn.extend(flow_warn)

    vision_used = False
    if enable_vision and needs_vision_inspection(
        scene, result, semantic=semantic, technical=tech.score
    ):
        vis_score, vis_warn = vision_semantic_score(scene, frames, settings=settings)
        if vis_score is not None:
            vision_used = True
            semantic = semantic * 0.4 + vis_score * 0.6
            sem_warn.extend(vis_warn)

    narr_dur = narration_duration_from_coverage(coverage_plan, fallback=float(meta.get("duration") or 3.0))
    dur_score, cov_warn, refined_cov = score_duration_coverage(narr_dur, tech.duration, coverage_plan)

    rep_score, rep_warn = score_repetition(
        asset_id,
        str(meta.get("title") or ""),
        str(meta.get("description") or meta.get("tags") or ""),
        selection_history,
        project_asset_ids=project_asset_ids,
    )

    style_fit = score_style_fit(semantic, tech.score, resolved, is_archival=archival)
    composition = min(1.0, tech.score + (0.1 if not any("vertical" in w for w in tech.issues) else 0))
    visual_quality = (tech.score * 0.5 + semantic * 0.35 + style_fit * 0.15)

    overall = (
        semantic * 0.30
        + tech.score * 0.22
        + visual_quality * 0.15
        + style_fit * 0.12
        + dur_score * 0.13
        + rep_score * 0.08
    )
    overall = max(0.0, min(1.0, overall))

    failures = [w for w in tech.issues if tech.score < 0.5]
    warnings = sem_warn + cov_warn + rep_warn + [w for w in tech.issues if w not in failures]

    if semantic < 0.45:
        failures.append("semantic mismatch")
    if dur_score < 0.5:
        failures.append("duration insufficient")
    if rep_score < 0.55:
        warnings.append("repetition concern")

    status = status_from_score(overall, archival_ok=archival)
    if scene_preserves_source_authority(scene) and status == VisualQAStatus.FAIL and semantic >= 0.35:
        status = VisualQAStatus.WEAK
        warnings.append("manual source — review recommended")

    qa = VisualQAResult(
        scene_number=key,
        asset_id=asset_id,
        status=status,
        overall_score=overall,
        semantic_match=semantic,
        technical_quality=tech.score,
        visual_quality=visual_quality,
        composition=composition,
        style_fit=style_fit,
        duration_coverage=dur_score,
        repetition_score=rep_score,
        failure_reasons=failures,
        warnings=warnings,
        vision_used=vision_used,
    )
    apply_recommended_action(qa, scene)

    if images_dir is not None:
        store_cached(images_dir, path, key, qa, style_id=style_id)

    if refined_cov is not None and isinstance(meta, dict):
        meta["_refined_coverage_plan"] = refined_cov

    return qa
