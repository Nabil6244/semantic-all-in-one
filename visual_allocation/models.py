"""Visual Allocation Engine — models (additive, does not replace EditorialPlan)."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

ALLOCATION_ENGINE_VERSION = 2

VISUAL_STRATEGIES = frozenset({"automatic", "video_heavy", "balanced", "image_heavy"})
AI_BUDGET_MODES = frozenset({"conservative", "normal", "high", "custom"})
COVERAGE_MODES = frozenset({"automatic", "minimize_repetition", "cinematic_coverage", "maximum_motion"})

VISUAL_NEEDS = frozenset({
    "establishing",
    "action",
    "reveal",
    "comparison",
    "process",
    "timeline",
    "location",
    "character",
    "evidence",
    "document",
    "map",
    "scientific",
    "scale",
    "atmosphere",
    "explanation",
    "reflection",
})

ASSET_TYPES_VIDEO = frozenset({
    "video",
    "stock_video",
    "youtube_video",
    "archive_video",
    "nasa_video",
})
ASSET_TYPES_IMAGE = frozenset({"image", "stock_image", "flow_image"})


ALLOCATION_PRESET_LABELS = (
    "Custom",
    "Documentary (stock-forward)",
    "Cinematic (Flow video)",
    "Balanced (default)",
    "Explainer (image-heavy)",
)


def allocation_preset_settings(label: str) -> Optional["AllocationSettings"]:
    """Return preset AllocationSettings or None for Custom."""
    key = (label or "").strip()
    if key == "Documentary (stock-forward)":
        return AllocationSettings(
            visual_strategy="video_heavy",
            ai_video_budget="conservative",
            coverage_mode="minimize_repetition",
        )
    if key == "Cinematic (Flow video)":
        return AllocationSettings(
            visual_strategy="video_heavy",
            ai_video_budget="high",
            coverage_mode="cinematic_coverage",
        )
    if key == "Balanced (default)":
        return AllocationSettings(
            visual_strategy="balanced",
            ai_video_budget="normal",
            coverage_mode="automatic",
        )
    if key == "Explainer (image-heavy)":
        return AllocationSettings(
            visual_strategy="image_heavy",
            ai_video_budget="conservative",
            coverage_mode="automatic",
        )
    return None


@dataclasses.dataclass
class AllocationSettings:
    visual_strategy: str = "automatic"
    ai_video_budget: str = "normal"
    ai_video_budget_custom: int = 20
    coverage_mode: str = "automatic"
    allocation_version: int = ALLOCATION_ENGINE_VERSION

    def fingerprint(self) -> dict:
        return {
            "allocation_version": self.allocation_version,
            "visual_strategy": self.visual_strategy,
            "ai_video_budget": self.ai_video_budget,
            "ai_video_budget_custom": int(self.ai_video_budget_custom),
            "coverage_mode": self.coverage_mode,
        }


@dataclasses.dataclass
class AllocationDecision:
    scene_id: int
    visual_kind: str  # image | video
    asset_type: str
    provider_preference: str
    visual_need: str = "establishing"
    flow_opportunity_score: float = 0.0
    flow_selected: bool = False
    curve_video_bias: float = 0.5
    importance: str = "normal"
    reason: str = ""
    curve_overridden: bool = False
    manual_preserved: bool = False

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CoverageSegment:
    start: float
    end: float
    asset_class: str  # stock_video, image, archive_video, etc.
    visual_role: str = ""
    avoid_loop: bool = False
    semantic_query_hint: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class VisualCoveragePlan:
    scene_id: int
    narration_duration: float
    segments: List[CoverageSegment]
    strategy: str = "single"  # single | dual | hold_tail | extend
    reason: str = ""
    avoid_blind_loop: bool = False

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "narration_duration": self.narration_duration,
            "segments": [s.to_dict() for s in self.segments],
            "strategy": self.strategy,
            "reason": self.reason,
            "avoid_blind_loop": self.avoid_blind_loop,
        }


@dataclasses.dataclass
class AllocationBundle:
    settings: AllocationSettings
    decisions: List[AllocationDecision]
    coverage_plans: List[VisualCoveragePlan]
    ai_budget_limit: int = 0
    ai_opportunities: int = 0
    ai_assigned: int = 0  # Flow video only (paid credits)
    flow_image_assigned: int = 0  # Free Flow stills
    style_id: str = ""

    def to_dict(self) -> dict:
        return {
            "allocation_version": ALLOCATION_ENGINE_VERSION,
            "settings": self.settings.fingerprint(),
            "style_id": self.style_id,
            "ai_budget_limit": self.ai_budget_limit,
            "ai_opportunities": self.ai_opportunities,
            "ai_assigned": self.ai_assigned,
            "flow_image_assigned": self.flow_image_assigned,
            "decisions": [d.to_dict() for d in self.decisions],
            "coverage_plans": [p.to_dict() for p in self.coverage_plans],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AllocationBundle":
        if not isinstance(data, dict):
            return cls(settings=AllocationSettings(), decisions=[], coverage_plans=[])
        settings_raw = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        settings = AllocationSettings(
            visual_strategy=str(settings_raw.get("visual_strategy") or "automatic"),
            ai_video_budget=str(settings_raw.get("ai_video_budget") or "normal"),
            ai_video_budget_custom=int(settings_raw.get("ai_video_budget_custom") or 20),
            coverage_mode=str(settings_raw.get("coverage_mode") or "automatic"),
        )
        decisions = [
            AllocationDecision(**{k: v for k, v in d.items() if k in AllocationDecision.__dataclass_fields__})
            for d in (data.get("decisions") or [])
            if isinstance(d, dict)
        ]
        coverage = []
        for p in data.get("coverage_plans") or []:
            if not isinstance(p, dict):
                continue
            segs = [
                CoverageSegment(**{k: v for k, v in s.items() if k in CoverageSegment.__dataclass_fields__})
                for s in (p.get("segments") or [])
                if isinstance(s, dict)
            ]
            coverage.append(
                VisualCoveragePlan(
                    scene_id=int(p.get("scene_id") or 0),
                    narration_duration=float(p.get("narration_duration") or 0),
                    segments=segs,
                    strategy=str(p.get("strategy") or "single"),
                    reason=str(p.get("reason") or ""),
                    avoid_blind_loop=bool(p.get("avoid_blind_loop")),
                )
            )
        version = int(data.get("allocation_version") or 1)
        ai_assigned = int(data.get("ai_assigned") or 0)
        flow_image_assigned = int(data.get("flow_image_assigned") or 0)
        if version < ALLOCATION_ENGINE_VERSION and decisions and flow_image_assigned <= 0:
            imgs = sum(
                1 for d in decisions if d.flow_selected and d.asset_type == "image"
            )
            vids = sum(
                1 for d in decisions if d.flow_selected and d.asset_type == "video"
            )
            if imgs or vids:
                flow_image_assigned = imgs
                ai_assigned = vids
        return cls(
            settings=settings,
            decisions=decisions,
            coverage_plans=coverage,
            ai_budget_limit=int(data.get("ai_budget_limit") or 0),
            ai_opportunities=int(data.get("ai_opportunities") or 0),
            ai_assigned=ai_assigned,
            flow_image_assigned=flow_image_assigned,
            style_id=str(data.get("style_id") or ""),
        )
