"""Post-analyze validation report and allocation mix estimates."""

from __future__ import annotations

from typing import Optional

from providers.router import SceneAssetRouter
from visual_director.schema import VisualPlan

from .budget import ai_budget_limit, flow_image_soft_cap
from .curve import curve_video_bias
from .models import AllocationBundle, AllocationSettings


def _estimate_scene_count(word_count: int) -> int:
    if word_count <= 0:
        return 0
    # ~3.5s visual beat @ ~145 wpm ≈ 8–9 words per scene (rough planning aid).
    return max(8, int(word_count / 8.5))


def estimate_allocation_mix(
    word_count: int,
    settings: AllocationSettings,
    *,
    style_id: str = "",
) -> str:
    """Rough pre-analyze mix for Brand & Style preview (not exact)."""
    n = _estimate_scene_count(word_count)
    if n <= 0:
        return "Paste a script to preview visual mix."
    flow_video_cap = ai_budget_limit(n, settings)
    flow_image_ceiling = flow_image_soft_cap(n, settings)
    strat = (settings.visual_strategy or "automatic").lower()
    mid_bias = curve_video_bias(0.5, strat)
    video_share = 0.55 if strat == "video_heavy" else 0.35 if strat == "balanced" else 0.22 if strat == "image_heavy" else mid_bias
    stock_video = max(0, int(n * video_share * 0.72))
    stock_image = max(0, int(n * (1.0 - video_share) * 0.55))
    flow_video = max(0, int(flow_video_cap * 0.85))
    flow_image = max(0, int(flow_image_ceiling * 0.55))
    doc = 0
    if style_id in (
        "history_documentary",
        "ancient_history_documentary",
        "military_war_documentary",
        "space_documentary",
    ):
        doc = max(2, int(n * 0.06))
    parts = [
        f"~{n} scenes",
        f"Flow video ~{flow_video} (credits)",
        f"Flow image up to ~{flow_image} (free)",
        f"Stock video ~{stock_video}",
        f"Stock image ~{stock_image}",
    ]
    if doc:
        parts.append(f"Archive/NASA ~{doc}")
    return " · ".join(parts)


def build_plan_validation_report(
    plan: VisualPlan,
    bundle: Optional[AllocationBundle] = None,
) -> str:
    rows = plan.to_scene_rows()
    lines = [
        "VALIDATION REPORT",
        f"Scenes: {len(plan.scenes)}",
    ]
    if plan.topic:
        lines.append(f"Topic: {plan.topic}")

    type_counts: dict[str, int] = {}
    empty_prompts = 0
    unassigned = 0
    local_rows = 0
    for scene, row in zip(plan.scenes, rows):
        at = (scene.asset_type or row.asset_type or "unknown").lower()
        type_counts[at] = type_counts.get(at, 0) + 1
        prompt = (row.prompt or row.stock or "").strip()
        if not prompt and at not in ("local",):
            empty_prompts += 1
        if SceneAssetRouter.classify(row) is None:
            if at == "local":
                local_rows += 1
            else:
                unassigned += 1

    mix = ", ".join(f"{k} {v}" for k, v in sorted(type_counts.items()))
    lines.append(f"Asset mix: {mix}")

    if bundle is not None:
        lines.append(
            f"Flow video (credits): {bundle.ai_assigned}/{bundle.ai_budget_limit} · "
            f"Flow image (free): {bundle.flow_image_assigned} · "
            f"{bundle.ai_opportunities} opportunities"
        )

    if plan.warnings:
        lines.append(f"Director warnings: {len(plan.warnings)}")
        for w in plan.warnings[:5]:
            lines.append(f"  • {w}")
        if len(plan.warnings) > 5:
            lines.append(f"  … +{len(plan.warnings) - 5} more")

    issues = []
    if empty_prompts:
        issues.append(f"{empty_prompts} scene(s) missing prompts")
    if unassigned:
        issues.append(f"{unassigned} unroutable scene(s)")
    if local_rows:
        issues.append(f"{local_rows} manual-only local row(s) — OK if user-added")

    if issues:
        lines.append("Issues:")
        for item in issues:
            lines.append(f"  ⚠ {item}")
    else:
        lines.append("Issues: none — ready for Generate Assets")

    return "\n".join(lines)
