"""Visual QA + Auto-Fix — verify selected assets after provider resolution."""

from __future__ import annotations

from .fix_engine import FixAllReport, fix_all_issues
from .models import (
    QA_ENGINE_VERSION,
    ProjectQAReport,
    RecommendedAction,
    VisualQAResult,
    VisualQAStatus,
    scene_preserves_source_authority,
)
from .project_qa import build_project_report, summarize_visual_qa_for_ui
from .scorer import evaluate_scene_asset

__all__ = [
    "QA_ENGINE_VERSION",
    "VisualQAResult",
    "VisualQAStatus",
    "RecommendedAction",
    "ProjectQAReport",
    "FixAllReport",
    "evaluate_scene_asset",
    "build_project_report",
    "summarize_visual_qa_for_ui",
    "fix_all_issues",
    "scene_preserves_source_authority",
]
