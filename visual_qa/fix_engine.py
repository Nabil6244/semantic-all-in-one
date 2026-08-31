"""Auto-Fix orchestration — reuses AssetManager recovery."""

from __future__ import annotations

import dataclasses
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from providers.base import AssetResult, AssetSource, SceneRow, SceneStatus
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
    # Credits spent by QA repairs specifically. Tracked apart from `used`
    # (which starts at the allocation's own assignment) so the total can be
    # written back and survive the next Fix All click.
    qa_spent: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def can_regenerate_flow(self) -> bool:
        return self.remaining > self.reserve

    def spend(self) -> None:
        self.used += 1
        self.qa_spent += 1


@dataclasses.dataclass
class FixAllReport:
    targeted: int = 0
    fixed: int = 0
    still_weak: int = 0
    still_fail: int = 0
    flow_regenerations: int = 0
    # PAID Flow video credits this pass actually consumed.
    flow_credits_spent: int = 0
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


# Key under which cumulative QA-driven Flow VIDEO spend is stored on the
# allocation dict, so it persists with the visual plan.
QA_FLOW_SPEND_KEY = "qa_flow_video_regenerations"


def _flow_budget_from_allocation(allocation: Optional[dict], scene_count: int) -> FlowBudgetState:
    if not isinstance(allocation, dict):
        return FlowBudgetState()
    try:
        limit = int(allocation.get("ai_budget_limit") or 0)
        used = int(allocation.get("ai_assigned") or 0)
    except (TypeError, ValueError):
        limit = used = 0
    # Credits already burned by earlier QA repairs. Without this the budget
    # reset to the plan's original figure on every Fix All click, so each
    # click handed out a fresh full allowance of PAID Flow video credits.
    try:
        prior_qa = max(0, int(allocation.get(QA_FLOW_SPEND_KEY) or 0))
    except (TypeError, ValueError):
        prior_qa = 0
    used += prior_qa
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

    # Every action that re-runs Flow costs a PAID video credit, not just
    # REGENERATE_FLOW. The budget used to guard that one action only — while
    # RETRY_SAME went straight to mgr.retry_scene() and spent a credit with no
    # check at all. And because scene_preserves_source_authority() is true for
    # any scene with an asset_type set, RETRY_SAME is the branch nearly every
    # real Flow video scene actually takes, so in practice the ceiling guarded
    # almost nothing. `alternative_scene` is exempt: it moves the scene to
    # stock, which is exactly the free fallback to use when credits run out.
    spends_credit = _scene_uses_flow_video_credit(scene) and action in (
        RecommendedAction.REGENERATE_FLOW,
        RecommendedAction.RETRY_SAME,
        RecommendedAction.RERANK,
    )
    if spends_credit and not flow_budget.can_regenerate_flow():
        log(
            f"[VQA] Scene {scene.scene_number}: Flow video credit budget exhausted "
            f"({flow_budget.used}/{flow_budget.limit}) — using a stock alternative"
        )
        return mgr.alternative_scene(scene)
    if spends_credit:
        flow_budget.spend()

    if action == RecommendedAction.REGENERATE_FLOW:
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


# Lifetime cap on AUTOMATIC repairs per scene, counted across every Fix All
# invocation rather than reset on each click. `max_attempts` only ever bounded
# a single call, so clicking Fix All repeatedly kept regenerating the same
# stubborn scene — and for Flow video each of those spends a real credit.
# Manual per-scene Retry deliberately does NOT go through here and stays
# unlimited: an explicit operator action is authoritative.
LIFETIME_REPAIR_ATTEMPTS = 3


def _repair_attempts(result: Optional[AssetResult]) -> int:
    meta = getattr(result, "metadata", None)
    if not isinstance(meta, dict):
        return 0
    vqa = meta.get("visual_qa")
    if not isinstance(vqa, dict):
        return 0
    try:
        return int(vqa.get("repair_attempts") or 0)
    except (TypeError, ValueError):
        return 0


def _record_repair_attempt(result: Optional[AssetResult], count: int) -> None:
    """Persist the attempt count on the asset so it survives the next click."""
    meta = getattr(result, "metadata", None)
    if not isinstance(meta, dict):
        return
    vqa = meta.get("visual_qa")
    if not isinstance(vqa, dict):
        vqa = {}
        meta["visual_qa"] = vqa
    vqa["repair_attempts"] = int(count)


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

    # Google Flow is a paid, credit-based generator, not a QA-repairable
    # asset: once a scene is configured for Flow, automatic repair must never
    # call it again — no regenerate, no retry, no swap to another source —
    # regardless of what the QA verdict recommends or whether an asset has
    # been delivered yet. The operator decides via the existing manual
    # Retry/Change Source controls; QA only ever gets to say "needs review".
    if mgr.classify(scene) in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO):
        needs_review = dataclasses.replace(qa, recommended_action=RecommendedAction.MANUAL_REVIEW)
        return results.get(key), needs_review

    action = recommended_action_for(qa, scene)
    if action in (RecommendedAction.NONE, RecommendedAction.KEEP, RecommendedAction.MANUAL_REVIEW):
        return results.get(key), qa

    result = results.get(key)

    # Stop automatically re-running a scene that has already had its chances.
    # Hand it to the operator instead of burning more time (and Flow credits)
    # on an approach that has not worked; the existing asset is untouched.
    spent = _repair_attempts(result)
    if spent >= LIFETIME_REPAIR_ATTEMPTS:
        log(
            f"[VQA] Scene {scene.scene_number}: {spent} automatic repair(s) already "
            f"attempted — leaving it for manual review"
        )
        exhausted = dataclasses.replace(
            qa, recommended_action=RecommendedAction.MANUAL_REVIEW
        )
        return result, exhausted

    remaining = max(0, LIFETIME_REPAIR_ATTEMPTS - spent)
    latest_qa = qa
    for attempt in range(min(max_attempts, remaining)):
        spent += 1
        log(f"[VQA] Scene {scene.scene_number}: {action.value} (attempt {attempt + 1})")
        result = _apply_fix_action(mgr, scene, action, flow_budget=flow_budget, log=log)
        previous = results.get(key)
        if result is not None and result.ok:
            results[key] = result
        elif previous is None or not previous.ok:
            # Nothing usable to preserve — record the failure exactly as before.
            results[key] = result
        else:
            # A QA-triggered repair FAILED on a scene that already had a working
            # asset. Keep the working asset: overwriting it turned an advisory
            # QA verdict into a hard NEEDS_ACTION and blocked the render
            # (allow_final_render keys on result.ok), discarding a usable image
            # because an optional improvement attempt did not land.
            log(
                f"[VQA] Scene {scene.scene_number}: {action.value} failed — "
                f"keeping the existing asset"
            )
        _record_repair_attempt(results.get(key), spent)
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

    # Persist this pass's paid spend onto the allocation so the ceiling is
    # cumulative across clicks rather than per-click.
    if isinstance(allocation, dict) and flow_budget.qa_spent:
        try:
            prior = max(0, int(allocation.get(QA_FLOW_SPEND_KEY) or 0))
        except (TypeError, ValueError):
            prior = 0
        allocation[QA_FLOW_SPEND_KEY] = prior + flow_budget.qa_spent
    report.flow_credits_spent = flow_budget.qa_spent

    return report
