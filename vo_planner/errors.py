"""Stage-tagged errors for Option 3 (user-facing, actionable)."""

from __future__ import annotations


class VoPlannerStageError(Exception):
    """Raised when a named planning stage fails."""

    STAGE_LABELS = {
        "script_validation": "Script validation failed",
        "voiceover_validation": "Voiceover validation failed",
        "script_analyzer": "Script analysis failed",
        "voiceover_analysis": "Voiceover analysis failed",
        "beat_alignment": "Beat alignment failed",
        "coverage_planning": "Coverage planning failed",
        "visual_plan": "VisualPlan generation failed",
        "cache": "Cached plan load failed",
        "csv_import": "CSV import failed",
    }

    def __init__(self, stage: str, message: str, *, cause: BaseException | None = None):
        self.stage = stage
        self.user_message = (message or "").strip() or "Unexpected error"
        self.cause = cause
        label = self.STAGE_LABELS.get(stage, stage.replace("_", " ").title())
        super().__init__(f"{label}: {self.user_message}")

    @property
    def title(self) -> str:
        return self.STAGE_LABELS.get(self.stage, "Claude Plan failed")
