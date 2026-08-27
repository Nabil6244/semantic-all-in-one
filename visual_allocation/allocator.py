"""Visual Allocation Engine — deterministic asset-type decisions."""

from __future__ import annotations

from typing import List, Optional, Tuple

from style_engine.schema import ResolvedStyle
from style_engine.visual_profile import build_scene_visual_profile
from providers.base import SceneRow
from visual_director.schema import VisualPlan, VisualScene

from .budget import ai_budget_limit, flow_opportunity_score, select_flow_scenes
from .coverage import plan_scene_coverage
from .curve import curve_video_bias, position_ratio
from .models import (
    ASSET_TYPES_IMAGE,
    ASSET_TYPES_VIDEO,
    AllocationBundle,
    AllocationDecision,
    AllocationSettings,
)
from .rhythm import RhythmState
from .scene_needs import infer_visual_need

ASSET_TO_PROVIDER = {
    "video": "flow_video",
    "image": "flow_image",
    "stock_video": "stock_video",
    "stock_image": "stock_image",
    "youtube_video": "youtube",
    "archive_video": "archive",
    "nasa_video": "nasa",
}

VIDEO_NEED_OVERRIDE = frozenset({
    "action",
    "reveal",
    "scientific",
    "scale",
    "process",
})

IMAGE_NEED_OVERRIDE = frozenset({
    "document",
    "map",
    "evidence",
    "timeline",
})

IMPORTANCE_VIDEO_BOOST = {"high": 0.18, "medium": 0.08, "normal": 0.0, "low": -0.05}


def _ensure_balanced_flow_video(
    decisions: List[AllocationDecision],
    settings: AllocationSettings,
) -> None:
    """Balanced/automatic modes should not assign Flow budget entirely as stills."""
    strat = (settings.visual_strategy or "automatic").lower()
    if strat not in ("balanced", "automatic"):
        return
    flow = [d for d in decisions if d.flow_selected]
    if not flow:
        return
    videos = [d for d in flow if d.asset_type == "video"]
    if videos:
        return
    min_videos = max(1, int(len(flow) * 0.35))
    ranked = sorted(flow, key=lambda d: d.flow_opportunity_score, reverse=True)
    for dec in ranked[:min_videos]:
        dec.asset_type = "video"
        dec.provider_preference = "flow_video"
        dec.visual_kind = "video"
        dec.reason = (dec.reason or "") + "; balanced flow video floor"


def _style_video_bias(resolved: Optional[ResolvedStyle]) -> float:
    if resolved is None or resolved.style is None:
        return 0.0
    style = resolved.style
    sid = style.id
    shots = style.shot_selection
    bias = (shots.establishing_weight + shots.evidence_weight) * 0.15 - shots.atmosphere_weight * 0.05
    if sid in ("premium_documentary", "space_documentary", "nature_wildlife_documentary"):
        bias += 0.08
    if sid in ("history_documentary", "ancient_history_documentary", "military_war_documentary"):
        bias -= 0.06
    if sid == "ai_narration":
        bias += 0.05
    return bias


def _documentary_asset_type(
    visual_need: str,
    visual_role: str,
    style_id: str,
    prefer_video: bool,
) -> str:
    if visual_need in IMAGE_NEED_OVERRIDE or visual_role in ("document", "map", "timeline"):
        if visual_need == "map" or visual_role == "map":
            return "stock_image"
        if style_id in ("history_documentary", "ancient_history_documentary", "military_war_documentary", "true_crime_documentary"):
            return "archive_video"
        return "stock_image"
    if visual_need == "scientific" or visual_role == "scientific_visualization":
        if style_id == "space_documentary":
            return "nasa_video"
        return "stock_video" if prefer_video else "stock_image"
    if visual_need in ("action", "reveal") and prefer_video:
        return "stock_video"
    if style_id in ("history_documentary", "military_war_documentary", "geopolitics_documentary", "news_current_affairs"):
        if visual_need in ("evidence", "timeline", "action"):
            return "archive_video"
    if visual_need == "character" and not prefer_video:
        return "stock_image"
    return "stock_video" if prefer_video else "stock_image"


def _score_video_vs_image(
    scene: VisualScene,
    *,
    position: float,
    visual_need: str,
    settings: AllocationSettings,
    resolved: Optional[ResolvedStyle],
    rhythm: RhythmState,
) -> Tuple[bool, float, bool]:
    curve = curve_video_bias(position, settings.visual_strategy)
    style_adj = _style_video_bias(resolved)
    rhythm_adj = rhythm.rhythm_video_adjustment()
    imp = (scene.importance or "normal").lower()
    imp_adj = IMPORTANCE_VIDEO_BOOST.get(imp, 0.0)

    override_video = visual_need in VIDEO_NEED_OVERRIDE
    override_image = visual_need in IMAGE_NEED_OVERRIDE
    curve_overridden = override_video or override_image

    if override_image and not override_video:
        return False, curve, True
    if override_video and not override_image:
        return True, curve, True

    score = curve + style_adj + rhythm_adj + imp_adj
    if position < 0.12 and settings.visual_strategy != "image_heavy":
        score += 0.06
    return score >= 0.5, curve, curve_overridden


def allocate_visual_plan(
    plan: VisualPlan,
    settings: AllocationSettings,
    resolved: Optional[ResolvedStyle] = None,
) -> AllocationBundle:
    scenes = list(plan.scenes)
    total = len(scenes)
    style_id = resolved.style_id if resolved else ""
    budget = ai_budget_limit(total, settings)
    rhythm = RhythmState()

    # Pass 1 — score flow opportunities
    flow_scores: List[Tuple[int, float]] = []
    prelim: List[dict] = []
    for i, scene in enumerate(scenes):
        pos = position_ratio(i, total)
        need = infer_visual_need(
            scene.narration,
            scene.visual_goal,
            scene.visual_description,
            scene.importance,
            resolved,
        )
        row = SceneRow(
            scene_number=str(scene.scene_id),
            script_segment=scene.narration,
            prompt=scene.visual_description,
            visual_description=scene.visual_description,
        )
        profile = build_scene_visual_profile(row, resolved)
        prefer_video, curve_bias, overridden = _score_video_vs_image(
            scene, position=pos, visual_need=need, settings=settings, resolved=resolved, rhythm=rhythm
        )
        fscore = flow_opportunity_score(
            scene,
            visual_need=need,
            visual_role=profile.visual_role,
            position=pos,
            style_id=style_id,
            recent_flow=rhythm.recent_flow,
        )
        flow_scores.append((scene.scene_id, fscore))
        prelim.append(
            {
                "scene": scene,
                "need": need,
                "role": profile.visual_role,
                "prefer_video": prefer_video,
                "curve_bias": curve_bias,
                "overridden": overridden,
                "flow_score": fscore,
            }
        )

    flow_selected = select_flow_scenes(flow_scores, budget)
    opportunities = sum(1 for _, s in flow_scores if s >= 0.35)

    decisions: List[AllocationDecision] = []
    coverage_plans = []
    flow_assigned = 0

    for item in prelim:
        scene: VisualScene = item["scene"]
        need = item["need"]
        prefer_video = item["prefer_video"]
        sid = scene.scene_id
        is_flow = sid in flow_selected and item["flow_score"] >= 0.35 and need not in IMAGE_NEED_OVERRIDE

        if is_flow:
            use_flow_video = prefer_video
            strat = (settings.visual_strategy or "automatic").lower()
            if not use_flow_video and strat in ("balanced", "automatic", "video_heavy"):
                imp = (scene.importance or "normal").lower()
                if (
                    item["flow_score"] >= 0.45
                    or need in VIDEO_NEED_OVERRIDE
                    or imp == "high"
                ):
                    use_flow_video = True
            asset_type = "video" if use_flow_video else "image"
            flow_assigned += 1
            reason_parts = [
                f"flow opportunity ({item['flow_score']:.2f})",
                f"need={need}",
            ]
        elif prefer_video:
            asset_type = _documentary_asset_type(need, item["role"], style_id, True)
            reason_parts = [f"video bias ({item['curve_bias']:.2f})", f"need={need}"]
        else:
            asset_type = _documentary_asset_type(need, item["role"], style_id, False)
            reason_parts = [f"image bias ({item['curve_bias']:.2f})", f"need={need}"]

        if item["overridden"]:
            reason_parts.append("importance/style override")

        provider = ASSET_TO_PROVIDER.get(asset_type, scene.provider_preference or "stock")
        visual_kind = "video" if asset_type in ASSET_TYPES_VIDEO else "image"

        decision = AllocationDecision(
            scene_id=sid,
            visual_kind=visual_kind,
            asset_type=asset_type,
            provider_preference=provider,
            visual_need=need,
            flow_opportunity_score=item["flow_score"],
            flow_selected=is_flow,
            curve_video_bias=item["curve_bias"],
            importance=(scene.importance or "normal"),
            reason="; ".join(reason_parts),
            curve_overridden=item["overridden"],
        )
        decisions.append(decision)
        rhythm.record(visual_kind, need, is_flow)
        coverage_plans.append(plan_scene_coverage(scene, decision, settings, resolved))

    _ensure_balanced_flow_video(decisions, settings)

    return AllocationBundle(
        settings=settings,
        decisions=decisions,
        coverage_plans=coverage_plans,
        ai_budget_limit=budget,
        ai_opportunities=opportunities,
        ai_assigned=flow_assigned,
        style_id=style_id,
    )


def apply_allocation_to_plan(
    plan: VisualPlan,
    settings: AllocationSettings,
    resolved: Optional[ResolvedStyle] = None,
) -> AllocationBundle:
    """Mutate VisualScene asset types from allocation; return diagnostic bundle."""
    from visual_allocation.prompt_backfill import finalize_plan_prompts
    from visual_director.schema import VisualPlanError, assert_pipeline_compatible

    bundle = allocate_visual_plan(plan, settings, resolved)
    by_id = {d.scene_id: d for d in bundle.decisions}
    for scene in plan.scenes:
        dec = by_id.get(scene.scene_id)
        if dec is None:
            continue
        scene.asset_type = dec.asset_type
        scene.provider_preference = dec.provider_preference
    finalize_plan_prompts(plan)
    errors = assert_pipeline_compatible(plan)
    if errors:
        preview = "; ".join(errors[:3])
        extra = f" (+{len(errors) - 3} more)" if len(errors) > 3 else ""
        raise VisualPlanError(
            f"Visual plan is not executable after allocation: {preview}{extra}"
        )
    plan.set_allocation(bundle.to_dict())
    return bundle
