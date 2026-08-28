"""Duration / coverage QA — reuses Visual Coverage Planner."""

from __future__ import annotations

from typing import Any, Optional

from visual_allocation.coverage import refine_coverage_duration
from visual_allocation.models import VisualCoveragePlan


def _plan_from_dict(raw: Optional[dict]) -> Optional[VisualCoveragePlan]:
    if not isinstance(raw, dict):
        return None
    from visual_allocation.models import CoverageSegment

    segs = []
    for item in raw.get("segments") or []:
        if not isinstance(item, dict):
            continue
        segs.append(
            CoverageSegment(
                start=float(item.get("start") or 0),
                end=float(item.get("end") or 0),
                asset_type=str(item.get("asset_type") or ""),
                visual_role=str(item.get("visual_role") or ""),
                avoid_loop=bool(item.get("avoid_loop")),
                semantic_query_hint=str(item.get("semantic_query_hint") or ""),
            )
        )
    return VisualCoveragePlan(
        scene_id=int(raw.get("scene_id") or 0),
        narration_duration=float(raw.get("narration_duration") or 0),
        segments=segs,
        strategy=str(raw.get("strategy") or "single"),
        reason=str(raw.get("reason") or ""),
        avoid_blind_loop=bool(raw.get("avoid_blind_loop")),
    )


def score_duration_coverage(
    narration_duration: float,
    asset_duration: Optional[float],
    coverage_plan: Optional[dict] = None,
) -> tuple[float, list[str], Optional[dict]]:
    """Score how well asset duration covers narration; refine coverage plan."""
    warnings: list[str] = []
    narr = max(0.0, float(narration_duration or 0))
    asset = float(asset_duration) if asset_duration and asset_duration > 0 else 0.0

    if narr <= 0:
        return 1.0, warnings, coverage_plan
    if asset <= 0:
        warnings.append("unknown asset duration")
        return 0.4, warnings, coverage_plan

    ratio = asset / narr
    if ratio >= 0.88:
        score = min(1.0, 0.85 + ratio * 0.1)
    elif ratio >= 0.72:
        score = 0.75
        warnings.append("slightly short clip — hold tail preferred")
    elif ratio >= 0.5:
        score = 0.55
        warnings.append("substantially short — complementary coverage recommended")
    else:
        score = 0.35
        warnings.append("clip too short for narration beat")

    refined_dict = coverage_plan
    plan = _plan_from_dict(coverage_plan)
    if plan is not None:
        refined = refine_coverage_duration(plan, narr, asset)
        refined_dict = {
            "scene_id": refined.scene_id,
            "narration_duration": refined.narration_duration,
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "asset_type": s.asset_type,
                    "visual_role": s.visual_role,
                    "avoid_loop": s.avoid_loop,
                    "semantic_query_hint": s.semantic_query_hint,
                }
                for s in refined.segments
            ],
            "strategy": refined.strategy,
            "reason": refined.reason,
            "avoid_blind_loop": refined.avoid_blind_loop,
        }
        if refined.avoid_blind_loop and ratio < 0.72:
            warnings.append("blind loop avoided — dual coverage or hold tail")

    return max(0.0, min(1.0, score)), warnings, refined_dict


def narration_duration_from_coverage(coverage_plan: Optional[dict], fallback: float = 3.0) -> float:
    if isinstance(coverage_plan, dict):
        try:
            d = float(coverage_plan.get("narration_duration") or 0)
            if d > 0:
                return d
        except (TypeError, ValueError):
            pass
    return max(1.5, float(fallback or 3.0))
