"""Script Analyzer result cache — avoid repeated Gemini calls for unchanged scripts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from .schema import VisualPlan, VisualScene

# Bump when analyzer output contract or fallback/Gemini integration changes.
ANALYZER_VERSION = 1

CACHE_NAME = "script_analyzer_plan.json"


def script_fingerprint(script: str) -> str:
    raw = (script or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def style_fingerprint(style_guidance: str = "") -> str:
    raw = (style_guidance or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def analyzer_cache_key(
    script: str,
    *,
    style_guidance: str = "",
    analyzer_version: int = ANALYZER_VERSION,
) -> str:
    parts = [
        script_fingerprint(script),
        style_fingerprint(style_guidance),
        str(int(analyzer_version)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:28]


def cache_path(state_dir: Path) -> Path:
    return Path(state_dir) / CACHE_NAME


def visual_plan_from_dict(data: dict) -> VisualPlan:
    scenes: list[VisualScene] = []
    for s in data.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        scenes.append(
            VisualScene(
                scene_id=int(s.get("scene_id") or len(scenes) + 1),
                narration=str(s.get("narration") or ""),
                visual_goal=str(s.get("visual_goal") or ""),
                visual_description=str(s.get("visual_description") or ""),
                asset_type=str(s.get("asset_type") or "stock_video"),
                provider_preference=str(s.get("provider_preference") or "stock_video"),
                search_queries=list(s.get("search_queries") or []),
                timestamp_needed=bool(s.get("timestamp_needed")),
                timestamp_hint=str(s.get("timestamp_hint") or ""),
                duration=float(s.get("duration") or 3.0),
                importance=str(s.get("importance") or "medium"),
                fallbacks=list(s.get("fallbacks") or ["stock_image"]),
                visual_treatment=str(s.get("visual_treatment") or ""),
                transition=str(s.get("transition") or "cut"),
                minimum_quality=str(s.get("minimum_quality") or "1080p"),
            )
        )
    return VisualPlan(
        topic=str(data.get("topic") or "Untitled"),
        scenes=scenes,
        warnings=list(data.get("warnings") or []),
        allocation=data.get("allocation"),
    )


def load_cached_plan(
    state_dir: Optional[Path],
    key: str,
    *,
    analyzer_version: int = ANALYZER_VERSION,
) -> Optional[VisualPlan]:
    if state_dir is None:
        return None
    path = cache_path(state_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("cache_key") != key:
        return None
    if int(payload.get("analyzer_version") or 0) != int(analyzer_version):
        return None
    plan_data = payload.get("plan")
    if not isinstance(plan_data, dict) or not plan_data.get("scenes"):
        return None
    try:
        plan = visual_plan_from_dict(plan_data)
    except Exception:
        return None
    if len(plan.scenes) < 2:
        return None
    # Mark provenance for UI/diagnostics without changing schema.
    plan.analyzer_source = "cache"  # type: ignore[attr-defined]
    return plan


def save_cached_plan(
    state_dir: Optional[Path],
    key: str,
    plan: VisualPlan,
    *,
    analyzer_version: int = ANALYZER_VERSION,
    source: str = "gemini",
) -> None:
    if state_dir is None:
        return
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "cache_key": key,
        "analyzer_version": int(analyzer_version),
        "source": source,
        "plan": plan.to_dict(),
    }
    cache_path(state_dir).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
