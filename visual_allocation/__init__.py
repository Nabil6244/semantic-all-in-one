"""Visual Allocation Engine — feeds Visual Director output, not EditorialPlan."""

from __future__ import annotations

from .allocator import allocate_visual_plan, apply_allocation_to_plan
from .prompt_backfill import finalize_plan_prompts, finalize_scene_prompts, scene_prompt_hint
from .cache import allocation_cache_key, script_fingerprint_from_plan
from .coverage import plan_scene_coverage, refine_coverage_duration
from .models import (
    ALLOCATION_ENGINE_VERSION,
    AllocationBundle,
    AllocationDecision,
    AllocationSettings,
    VisualCoveragePlan,
)
from .settings import load_allocation_settings, save_allocation_settings
from .validation import build_plan_validation_report, estimate_allocation_mix

__all__ = [
    "ALLOCATION_ENGINE_VERSION",
    "AllocationBundle",
    "AllocationDecision",
    "AllocationSettings",
    "VisualCoveragePlan",
    "allocate_visual_plan",
    "apply_allocation_to_plan",
    "finalize_plan_prompts",
    "finalize_scene_prompts",
    "scene_prompt_hint",
    "plan_scene_coverage",
    "refine_coverage_duration",
    "allocation_cache_key",
    "script_fingerprint_from_plan",
    "load_allocation_settings",
    "save_allocation_settings",
    "build_plan_validation_report",
    "estimate_allocation_mix",
]
