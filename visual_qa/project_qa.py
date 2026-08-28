"""Project-level Visual QA summary."""

from __future__ import annotations

from typing import Dict, List, Optional

from providers.base import AssetResult, SceneRow
from scene_recovery import scene_key

from .models import ProjectQAReport, VisualQAResult, VisualQAStatus
from .repetition import detect_project_repetition_issues
from .scorer import evaluate_scene_asset


def build_project_report(
    scenes: List[SceneRow],
    results: Dict[str, AssetResult],
    *,
    images_dir=None,
    coverage_by_scene: Optional[dict] = None,
    selection_history=None,
    resolved=None,
    settings: Optional[dict] = None,
) -> ProjectQAReport:
    qa_results: List[VisualQAResult] = []
    seen_ids: set[str] = set()

    for scene in scenes:
        key = scene_key(scene.scene_number)
        result = results.get(key)
        if result is None or not getattr(result, "ok", False):
            qa_results.append(VisualQAResult(scene_number=str(scene.scene_number), status=VisualQAStatus.SKIPPED))
            continue
        meta = result.metadata or {}
        cov = meta.get("coverage_plan") or (coverage_by_scene or {}).get(key)
        existing = meta.get("visual_qa")
        if isinstance(existing, dict):
            qa = VisualQAResult.from_dict(existing)
        else:
            aid = str(meta.get("provider_asset_id") or "")
            qa = evaluate_scene_asset(
                scene,
                result,
                images_dir=images_dir,
                coverage_plan=cov,
                selection_history=selection_history,
                resolved=resolved,
                settings=settings,
                project_asset_ids=seen_ids,
                enable_vision=False,
            )
            if aid:
                seen_ids.add(aid)
        qa_results.append(qa)

    report = ProjectQAReport(total=len(qa_results), results=qa_results)
    for qa in qa_results:
        if qa.status == VisualQAStatus.PASS:
            report.pass_count += 1
        elif qa.status == VisualQAStatus.WEAK:
            report.weak_count += 1
        elif qa.status == VisualQAStatus.FAIL:
            report.fail_count += 1
        else:
            report.skipped_count += 1

    scored = [q for q in qa_results if q.status != VisualQAStatus.SKIPPED]
    if scored:
        report.avg_semantic = sum(q.semantic_match for q in scored) / len(scored)
        report.avg_technical = sum(q.technical_quality for q in scored) / len(scored)
        report.coverage_pct = sum(q.duration_coverage for q in scored) / len(scored)
        report.repetition_pct = sum(q.repetition_score for q in scored) / len(scored)

    dup_issues = detect_project_repetition_issues(results)
    report.duplicate_assets = len(dup_issues)
    return report


def summarize_visual_qa_for_ui(report: ProjectQAReport) -> str:
    return " · ".join(report.summary_lines()[2:8])
