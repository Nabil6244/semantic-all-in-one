"""Load/save visual allocation settings from project workspace."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import AllocationSettings

if TYPE_CHECKING:
    from project_workspace import ProjectWorkspace

DEFAULTS = AllocationSettings()


def load_allocation_settings(ws: "ProjectWorkspace | None" = None) -> AllocationSettings:
    if ws is None:
        return AllocationSettings()
    raw = ws.read_meta().get("visual_allocation")
    if not isinstance(raw, dict):
        return AllocationSettings()
    return AllocationSettings(
        visual_strategy=str(raw.get("visual_strategy") or DEFAULTS.visual_strategy),
        ai_video_budget=str(raw.get("ai_video_budget") or DEFAULTS.ai_video_budget),
        ai_video_budget_custom=int(raw.get("ai_video_budget_custom") or DEFAULTS.ai_video_budget_custom),
        coverage_mode=str(raw.get("coverage_mode") or DEFAULTS.coverage_mode),
    )


def save_allocation_settings(ws: "ProjectWorkspace", settings: AllocationSettings) -> None:
    data = ws.read_meta()
    data.update(ws.to_dict())
    data["visual_allocation"] = settings.fingerprint()
    ws._write_meta(data)
