"""Visual QA result models."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Dict, List, Optional

from providers.base import SceneRow
from style_engine.visual_selection import scene_has_manual_authority

QA_ENGINE_VERSION = 1

PASS_THRESHOLD = 0.80
WEAK_THRESHOLD = 0.60


class VisualQAStatus(str, Enum):
    PASS = "PASS"
    WEAK = "WEAK"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class RecommendedAction(str, Enum):
    NONE = "none"
    KEEP = "keep"
    RETRY_SAME = "retry_same"
    RERANK = "rerank"
    ALTERNATE_QUERY = "alternate_query"
    ALTERNATIVE = "alternative"
    CHANGE_SOURCE = "change_source"
    REGENERATE_FLOW = "regenerate_flow"
    COVERAGE_REPAIR = "coverage_repair"
    MANUAL_REVIEW = "manual_review"


@dataclasses.dataclass
class VisualQAResult:
    scene_number: str
    asset_id: str = ""
    status: VisualQAStatus = VisualQAStatus.SKIPPED
    overall_score: float = 0.0
    semantic_match: float = 0.0
    technical_quality: float = 0.0
    visual_quality: float = 0.0
    composition: float = 0.0
    style_fit: float = 0.0
    duration_coverage: float = 0.0
    repetition_score: float = 1.0
    failure_reasons: List[str] = dataclasses.field(default_factory=list)
    warnings: List[str] = dataclasses.field(default_factory=list)
    recommended_action: RecommendedAction = RecommendedAction.NONE
    vision_used: bool = False
    engine_version: int = QA_ENGINE_VERSION

    def to_dict(self) -> dict:
        return {
            "scene_number": self.scene_number,
            "asset_id": self.asset_id,
            "status": self.status.value,
            "overall_score": round(self.overall_score, 4),
            "semantic_match": round(self.semantic_match, 4),
            "technical_quality": round(self.technical_quality, 4),
            "visual_quality": round(self.visual_quality, 4),
            "composition": round(self.composition, 4),
            "style_fit": round(self.style_fit, 4),
            "duration_coverage": round(self.duration_coverage, 4),
            "repetition_score": round(self.repetition_score, 4),
            "failure_reasons": list(self.failure_reasons),
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action.value,
            "vision_used": self.vision_used,
            "engine_version": self.engine_version,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "VisualQAResult":
        if not isinstance(raw, dict):
            return cls(scene_number="")
        try:
            status = VisualQAStatus(str(raw.get("status") or "SKIPPED"))
        except ValueError:
            status = VisualQAStatus.SKIPPED
        try:
            action = RecommendedAction(str(raw.get("recommended_action") or "none"))
        except ValueError:
            action = RecommendedAction.NONE
        return cls(
            scene_number=str(raw.get("scene_number") or ""),
            asset_id=str(raw.get("asset_id") or ""),
            status=status,
            overall_score=float(raw.get("overall_score") or 0),
            semantic_match=float(raw.get("semantic_match") or 0),
            technical_quality=float(raw.get("technical_quality") or 0),
            visual_quality=float(raw.get("visual_quality") or 0),
            composition=float(raw.get("composition") or 0),
            style_fit=float(raw.get("style_fit") or 0),
            duration_coverage=float(raw.get("duration_coverage") or 0),
            repetition_score=float(raw.get("repetition_score") or 1),
            failure_reasons=list(raw.get("failure_reasons") or []),
            warnings=list(raw.get("warnings") or []),
            recommended_action=action,
            vision_used=bool(raw.get("vision_used")),
            engine_version=int(raw.get("engine_version") or QA_ENGINE_VERSION),
        )


@dataclasses.dataclass
class ProjectQAReport:
    total: int = 0
    pass_count: int = 0
    weak_count: int = 0
    fail_count: int = 0
    skipped_count: int = 0
    avg_semantic: float = 0.0
    avg_technical: float = 0.0
    coverage_pct: float = 0.0
    repetition_pct: float = 0.0
    duplicate_assets: int = 0
    results: List[VisualQAResult] = dataclasses.field(default_factory=list)

    def summary_lines(self) -> List[str]:
        lines = [
            "VISUAL QA",
            f"{self.total} scenes",
            f"✓ {self.pass_count} PASS",
            f"⚠ {self.weak_count} WEAK",
            f"✕ {self.fail_count} FAIL",
        ]
        if self.skipped_count:
            lines.append(f"— {self.skipped_count} skipped")
        if self.total:
            lines.append(f"Semantic Match: {self.avg_semantic * 100:.0f}%")
            lines.append(f"Technical Health: {self.avg_technical * 100:.0f}%")
            lines.append(f"Coverage: {self.coverage_pct * 100:.0f}%")
            lines.append(f"Repetition: {self.repetition_pct * 100:.0f}%")
        return lines


def scene_preserves_source_authority(scene: SceneRow) -> bool:
    """Explicit CSV asset_type — auto-fix must not change source/type."""
    if scene_has_manual_authority(scene):
        return True
    return bool((scene.asset_type or "").strip())


def status_from_score(score: float, *, archival_ok: bool = False) -> VisualQAStatus:
    floor = 0.55 if archival_ok else WEAK_THRESHOLD
    if score >= PASS_THRESHOLD:
        return VisualQAStatus.PASS
    if score >= floor:
        return VisualQAStatus.WEAK
    return VisualQAStatus.FAIL
