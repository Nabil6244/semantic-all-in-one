"""Bridge VoAwarePlan → existing VisualPlan for CSV / allocation pipeline."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from visual_director.schema import VisualPlan, VisualScene

from .schema import AlignedBeat, CoverageContract, CoverageUnit, VoAwarePlan
from .quality import strip_generic_stock_language


def _enrich_description(beat: AlignedBeat, units: Sequence[CoverageUnit], contract: Optional[CoverageContract]) -> str:
    """Compact directive baked into visual_description for Claude / providers."""
    base = strip_generic_stock_language(beat.visual_description or beat.visual_goal or "")
    if not units:
        return base
    parts = [base] if base else []
    u0 = units[0]
    parts.append(
        f"[VO {u0.start:.1f}-{units[-1].end:.1f}s | {contract.strategy if contract else u0.strategy} | "
        f"{u0.shot_scale}/{u0.camera}/{u0.motion} | purpose:{u0.visual_purpose}]"
    )
    if len(units) > 1:
        parts.append(
            "coverage:"
            + "; ".join(
                f"{u.unit_id} {u.duration:.1f}s {u.strategy} {u.visual_purpose}"
                for u in units
            )
        )
    req = u0.quality_requirements or {}
    if req:
        parts.append(
            "req:"
            + ",".join(
                f"{k}={v}" for k, v in list(req.items())[:5]
                if not isinstance(v, (list, dict))
            )
        )
    if u0.avoid:
        parts.append("avoid:" + ",".join(u0.avoid[:5]))
    return " ".join(parts).strip()


def to_visual_plan(
    vo_plan: VoAwarePlan,
    *,
    source_scenes: Optional[Sequence[VisualScene]] = None,
) -> VisualPlan:
    """Map VO-aware beats onto VisualScene list for existing CSV Generator."""
    by_id: Dict[int, VisualScene] = {}
    if source_scenes:
        for s in source_scenes:
            by_id[int(s.scene_id)] = s

    units_by_beat: Dict[int, List[CoverageUnit]] = {}
    for u in vo_plan.units:
        units_by_beat.setdefault(u.beat_id, []).append(u)
    contracts = {c.beat_id: c for c in vo_plan.contracts}

    scenes: List[VisualScene] = []
    for beat in vo_plan.beats:
        src = by_id.get(beat.beat_id)
        beat_units = units_by_beat.get(beat.beat_id) or []
        contract = contracts.get(beat.beat_id)
        desc = _enrich_description(beat, beat_units, contract)
        # Duration = actual VO span (authority)
        duration = round(max(1.5, beat.duration), 2)
        if src is not None:
            scenes.append(
                VisualScene(
                    scene_id=beat.beat_id,
                    narration=beat.narration,
                    visual_goal=src.visual_goal or beat.visual_goal,
                    visual_description=desc or src.visual_description,
                    asset_type=src.asset_type,
                    provider_preference=src.provider_preference,
                    search_queries=list(src.search_queries or beat.search_queries),
                    timestamp_needed=src.timestamp_needed,
                    timestamp_hint=src.timestamp_hint,
                    duration=duration,
                    importance=src.importance or beat.importance,
                    fallbacks=list(src.fallbacks or beat.fallbacks),
                    visual_treatment=src.visual_treatment or beat.visual_treatment,
                    transition=src.transition or beat.transition,
                    minimum_quality=src.minimum_quality or beat.minimum_quality,
                )
            )
        else:
            scenes.append(
                VisualScene(
                    scene_id=beat.beat_id,
                    narration=beat.narration,
                    visual_goal=beat.visual_goal or "support narration",
                    visual_description=desc or beat.visual_description or beat.visual_goal,
                    asset_type=beat.asset_type or "stock_video",
                    provider_preference=beat.provider_preference or "stock_video",
                    search_queries=list(beat.search_queries),
                    timestamp_needed=False,
                    timestamp_hint="",
                    duration=duration,
                    importance=beat.importance or "medium",
                    fallbacks=list(beat.fallbacks),
                    visual_treatment=beat.visual_treatment or "",
                    transition=beat.transition or "cut",
                    minimum_quality=beat.minimum_quality or "1080p",
                )
            )

    warnings = list(vo_plan.warnings)
    for issue in vo_plan.qc_issues:
        if issue.severity in ("error", "warning"):
            warnings.append(f"[VO-QC:{issue.severity}] {issue.message}")

    plan = VisualPlan(topic=vo_plan.topic or "VO-Aware Plan", scenes=scenes, warnings=warnings)
    # Attach compact handoff for workspace JSON (not part of dataclass fields).
    plan.vo_aware = vo_plan.compact_handoff()  # type: ignore[attr-defined]
    plan.vo_aware_full = vo_plan.to_dict()  # type: ignore[attr-defined]
    return plan


def merge_vo_aware_into_payload(plan: VisualPlan, payload: dict) -> dict:
    """Inject vo_aware blocks into ai_visual_plan.json payload."""
    out = dict(payload)
    vo = getattr(plan, "vo_aware", None)
    full = getattr(plan, "vo_aware_full", None)
    if isinstance(vo, dict):
        out["vo_aware"] = vo
    if isinstance(full, dict):
        out["vo_aware_full"] = full
    out["planner"] = "vo_aware"
    return out
