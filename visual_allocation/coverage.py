"""Visual Coverage Planner — narration duration vs asset coverage."""

from __future__ import annotations

from typing import Optional

from visual_director.schema import VisualScene, provider_max_duration

from style_engine.schema import ResolvedStyle
from style_engine.visual_profile import build_scene_visual_profile
from providers.base import SceneRow

from .models import (
    ASSET_TYPES_IMAGE,
    ASSET_TYPES_VIDEO,
    AllocationDecision,
    AllocationSettings,
    CoverageSegment,
    VisualCoveragePlan,
)

DEFAULT_CLIP_ESTIMATE = {
    "video": 5.0,
    "stock_video": 4.0,
    "youtube_video": 3.0,
    "archive_video": 3.0,
    "nasa_video": 3.0,
    "image": 2.5,
    "stock_image": 2.5,
    "flow_image": 2.5,
}


def _estimate_clip_duration(asset_type: str, scene: VisualScene) -> float:
    provider = scene.provider_preference or asset_type
    cap = provider_max_duration(provider.replace("_video", "").replace("_image", ""))
    beat = float(scene.duration or 0)
    if beat > 0:
        return min(beat, cap)
    return min(DEFAULT_CLIP_ESTIMATE.get(asset_type, 3.5), cap)


def plan_scene_coverage(
    scene: VisualScene,
    decision: AllocationDecision,
    settings: AllocationSettings,
    resolved: Optional[ResolvedStyle] = None,
    *,
    narration_duration: Optional[float] = None,
) -> VisualCoveragePlan:
    narr = narration_duration if narration_duration is not None else float(scene.duration or 3.0)
    narr = max(1.5, narr)
    asset_type = decision.asset_type
    clip_est = _estimate_clip_duration(asset_type, scene)

    row = SceneRow(
        scene_number=str(scene.scene_id),
        script_segment=scene.narration,
        asset_type=asset_type,
        prompt=scene.visual_description or scene.primary_query,
        visual_description=scene.visual_description,
    )
    profile = build_scene_visual_profile(row, resolved)
    role = profile.visual_role
    query_hint = scene.primary_query or scene.visual_description[:80]

    is_video = asset_type in ASSET_TYPES_VIDEO
    is_image = asset_type in ASSET_TYPES_IMAGE

    # CASE A — asset long enough
    if clip_est >= narr * 0.88:
        seg = CoverageSegment(0.0, narr, asset_type, visual_role=role, semantic_query_hint=query_hint)
        return VisualCoveragePlan(
            scene_id=scene.scene_id,
            narration_duration=narr,
            segments=[seg],
            strategy="single",
            reason="asset duration covers narration",
            avoid_blind_loop=False,
        )

    # Images with camera movement can cover longer narration
    if is_image and narr <= clip_est * 1.6:
        seg = CoverageSegment(0.0, narr, asset_type, visual_role=role, semantic_query_hint=query_hint)
        return VisualCoveragePlan(
            scene_id=scene.scene_id,
            narration_duration=narr,
            segments=[seg],
            strategy="single",
            reason="still with camera movement covers beat",
            avoid_blind_loop=False,
        )

    gap = narr - clip_est
    ratio = clip_est / narr if narr else 1.0

    # CASE B — slightly shorter (hold tail, no loop)
    if is_video and gap <= 1.2 and ratio >= 0.72:
        seg = CoverageSegment(
            0.0, narr, asset_type, visual_role=role, avoid_loop=True, semantic_query_hint=query_hint
        )
        return VisualCoveragePlan(
            scene_id=scene.scene_id,
            narration_duration=narr,
            segments=[seg],
            strategy="hold_tail",
            reason="slight shortfall — hold end frame instead of loop",
            avoid_blind_loop=True,
        )

    # CASE C — substantially shorter — dual complementary coverage
    if is_video and ratio < 0.72:
        split = round(clip_est, 2)
        comp_type = _complement_type(asset_type, profile.visual_role, decision.visual_need)
        seg_a = CoverageSegment(
            0.0, split, asset_type, visual_role=role, semantic_query_hint=query_hint
        )
        seg_b = CoverageSegment(
            split,
            narr,
            comp_type,
            visual_role=role,
            avoid_loop=False,
            semantic_query_hint=f"{query_hint} {comp_type.replace('_', ' ')}",
        )
        return VisualCoveragePlan(
            scene_id=scene.scene_id,
            narration_duration=narr,
            segments=[seg_a, seg_b],
            strategy="dual",
            reason="short video paired with complementary visual",
            avoid_blind_loop=True,
        )

    # Fallback single with loop avoidance flag for renderer
    seg = CoverageSegment(
        0.0, narr, asset_type, visual_role=role, avoid_loop=True, semantic_query_hint=query_hint
    )
    return VisualCoveragePlan(
        scene_id=scene.scene_id,
        narration_duration=narr,
        segments=[seg],
        strategy="extend",
        reason="coverage extension preferred over blind loop",
        avoid_blind_loop=True,
    )


def _complement_type(primary: str, visual_role: str, visual_need: str) -> str:
    if visual_need in ("document", "map", "timeline", "evidence"):
        return "stock_image"
    if visual_role in ("map", "document", "timeline"):
        return "stock_image"
    if visual_need in ("scientific", "process", "explanation"):
        return "stock_video"
    if primary in ("archive_video", "nasa_video", "youtube_video"):
        return "stock_image"
    if primary == "video":
        return "stock_video"
    return "stock_image"


def refine_coverage_duration(
    plan: VisualCoveragePlan,
    narration_duration: float,
    downloaded_duration: Optional[float] = None,
) -> VisualCoveragePlan:
    """Refine after alignment or download — re-run planner logic with actual durations."""
    if narration_duration <= 0:
        return plan
    if downloaded_duration and plan.strategy == "single":
        if downloaded_duration >= narration_duration * 0.88:
            plan.narration_duration = narration_duration
            if plan.segments:
                plan.segments[0].end = narration_duration
            plan.avoid_blind_loop = False
            plan.reason = "downloaded asset covers aligned narration"
            return plan
        if narration_duration - downloaded_duration <= 1.2:
            plan.strategy = "hold_tail"
            plan.avoid_blind_loop = True
            plan.reason = "aligned narration slightly longer — hold tail"
            if plan.segments:
                plan.segments[0].end = narration_duration
                plan.segments[0].avoid_loop = True
    plan.narration_duration = narration_duration
    return plan
