"""Auto-Fix orchestration — reuses AssetManager recovery."""

from __future__ import annotations

import dataclasses
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from providers.base import AssetResult, SceneRow, SceneStatus
from scene_recovery import scene_key

from .models import RecommendedAction, VisualQAResult, VisualQAStatus, scene_preserves_source_authority
from .retry import recommended_action_for
from .scorer import evaluate_scene_asset

if TYPE_CHECKING:
    from asset_manager import AssetManager


LogFn = Callable[[str], None]


@dataclasses.dataclass
class FlowBudgetState:
    limit: int = 0
    used: int = 0
    reserve: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def can_regenerate_flow(self) -> bool:
        return self.remaining > self.reserve


@dataclasses.dataclass
class FixAllReport:
    targeted: int = 0
    fixed: int = 0
    still_weak: int = 0
    still_fail: int = 0
    flow_regenerations: int = 0
    actions: Dict[str, str] = dataclasses.field(default_factory=dict)


def _scene_uses_flow_video_credit(scene: SceneRow) -> bool:
    """Only Flow video regenerations consume the paid credit budget."""
    pref = (getattr(scene, "provider_preference", None) or "").lower()
    at = (scene.asset_type or "").lower()
    if pref == "flow_image" or at == "flow_image":
        return False
    if pref == "flow_video" or at in ("flow_video", "video"):
        return True
    if at == "image":
        return False
    return True


def _flow_budget_from_allocation(allocation: Optional[dict], scene_count: int) -> FlowBudgetState:
    if not isinstance(allocation, dict):
        return FlowBudgetState()
    try:
        limit = int(allocation.get("ai_budget_limit") or 0)
        used = int(allocation.get("ai_assigned") or 0)
    except (TypeError, ValueError):
        limit = used = 0
    version = int(allocation.get("allocation_version") or 1)
    if version < 2 and allocation.get("decisions"):
        vids = sum(
            1
            for d in allocation.get("decisions") or []
            if isinstance(d, dict)
            and d.get("flow_selected")
            and str(d.get("asset_type") or "").lower() == "video"
        )
        if vids:
            used = vids
    if limit <= 0 and scene_count > 0:
        from visual_allocation.budget import ai_budget_limit
        from visual_allocation.models import AllocationSettings

        limit = ai_budget_limit(scene_count, AllocationSettings())
    reserve = max(1, int(limit * 0.1)) if limit else 0
    return FlowBudgetState(limit=limit, used=used, reserve=reserve)


def _apply_fix_action(
    mgr: "AssetManager",
    scene: SceneRow,
    action: RecommendedAction,
    *,
    flow_budget: FlowBudgetState,
    log: LogFn = print,
) -> AssetResult:
    manual = scene_preserves_source_authority(scene)

    if action == RecommendedAction.REGENERATE_FLOW:
        uses_credit = _scene_uses_flow_video_credit(scene)
        if uses_credit and not flow_budget.can_regenerate_flow():
            log(f"[VQA] Scene {scene.scene_number}: Flow video budget exhausted — alternative")
            return mgr.alternative_scene(scene)
        if uses_credit:
            flow_budget.used += 1
        return mgr.regenerate_scene(scene)

    if action in (RecommendedAction.RETRY_SAME, RecommendedAction.RERANK):
        return mgr.retry_scene(scene)

    if action == RecommendedAction.ALTERNATIVE:
        if manual:
            return mgr.retry_scene(scene)
        return mgr.alternative_scene(scene)

    if action == RecommendedAction.CHANGE_SOURCE:
        if manual:
            return mgr.retry_scene(scene)
        alt = mgr.recovery.next_alternative(scene)
        if alt and alt.get("kind") == "provider":
            return mgr.change_source(scene, str(alt.get("provider")))
        return mgr.alternative_scene(scene)

    if action == RecommendedAction.COVERAGE_REPAIR:
        return mgr.alternative_scene(scene) if not manual else mgr.retry_scene(scene)

    return mgr.retry_scene(scene)


def fix_scene_if_needed(
    mgr: "AssetManager",
    scene: SceneRow,
    qa: VisualQAResult,
    *,
    results: Dict[str, AssetResult],
    flow_budget: FlowBudgetState,
    max_attempts: int = 2,
    log: LogFn = print,
) -> tuple[AssetResult, VisualQAResult]:
    key = scene_key(scene.scene_number)
    if qa.status == VisualQAStatus.PASS:
        return results.get(key) or AssetResult(
            scene.scene_number, None, None, mgr.classify(scene), SceneStatus.READY
        ), qa

    action = recommended_action_for(qa, scene)
    if action in (RecommendedAction.NONE, RecommendedAction.KEEP, RecommendedAction.MANUAL_REVIEW):
        return results.get(key), qa

    result = results.get(key)
    latest_qa = qa
    for attempt in range(max_attempts):
        log(f"[VQA] Scene {scene.scene_number}: {action.value} (attempt {attempt + 1})")
        result = _apply_fix_action(mgr, scene, action, flow_budget=flow_budget, log=log)
        results[key] = result
        if not result.ok:
            break
        latest_qa = evaluate_scene_asset(
            scene,
            result,
            images_dir=mgr.images_dir,
            coverage_plan=(result.metadata or {}).get("coverage_plan"),
            selection_history=mgr.selection_history,
            resolved=getattr(mgr, "resolved_style", None),
            enable_vision=False,
        )
        if latest_qa.status != VisualQAStatus.FAIL:
            break
        action = recommended_action_for(latest_qa, scene)
    return results.get(key) or result, latest_qa


def fix_all_issues(
    mgr: "AssetManager",
    scenes: List[SceneRow],
    qa_results: Dict[str, VisualQAResult],
    results: Dict[str, AssetResult],
    *,
    allocation: Optional[dict] = None,
    max_attempts: int = 2,
    log: LogFn = print,
) -> FixAllReport:
    """Targeted repair for WEAK/FAIL scenes only."""
    report = FixAllReport()
    flow_budget = _flow_budget_from_allocation(allocation, len(scenes))

    for scene in scenes:
        key = scene_key(scene.scene_number)
        qa = qa_results.get(key)
        if qa is None or qa.status == VisualQAStatus.PASS or qa.status == VisualQAStatus.SKIPPED:
            continue
        report.targeted += 1
        before = qa.status
        _, after_qa = fix_scene_if_needed(
            mgr, scene, qa, results=results, flow_budget=flow_budget, max_attempts=max_attempts, log=log
        )
        qa_results[key] = after_qa
        report.actions[key] = after_qa.recommended_action.value
        if after_qa.status == VisualQAStatus.PASS:
            report.fixed += 1
        elif after_qa.status == VisualQAStatus.WEAK:
            report.still_weak += 1
        else:
            report.still_fail += 1
        if before != VisualQAStatus.PASS and after_qa.recommended_action == RecommendedAction.REGENERATE_FLOW:
            report.flow_regenerations += 1

    return report
