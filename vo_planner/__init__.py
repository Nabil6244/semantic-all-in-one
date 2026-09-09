"""Option 3: VO-Aware Visual Planner.

Isolated workflow. Does not modify Script Analyzer or CSV Generator.
"""

from __future__ import annotations

from .bridge import merge_vo_aware_into_payload, to_visual_plan
from .engine import (
    analyze_vo_only,
    build_vo_aware_plan,
    compact_handoff_json,
    derive_allocation_settings,
    format_plan_preview,
    plan_from_voiceover,
)
from .errors import VoPlannerStageError
from .schema import (
    VO_PLANNER_VERSION,
    AssetMixPreferences,
    VOAnalysis,
    VoAwarePlan,
)
from .vo_analyzer import analyze_voiceover

__all__ = [
    "VO_PLANNER_VERSION",
    "AssetMixPreferences",
    "VOAnalysis",
    "VoAwarePlan",
    "VoPlannerStageError",
    "analyze_voiceover",
    "analyze_vo_only",
    "build_vo_aware_plan",
    "plan_from_voiceover",
    "to_visual_plan",
    "merge_vo_aware_into_payload",
    "format_plan_preview",
    "compact_handoff_json",
    "derive_allocation_settings",
]
