"""Persist EditorialPlan to state/editorial_plan.json with cache keys."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional, Sequence

from .schema import EDITORIAL_PLAN_VERSION, EditorialPlan

PLAN_JSON_NAME = "editorial_plan.json"


def plan_file(state_dir: Path) -> Path:
    return Path(state_dir) / PLAN_JSON_NAME


def cache_settings_key(
    rows: Sequence[dict],
    *,
    visual_plan_dict: Optional[dict] = None,
) -> str:
    payload: dict[str, Any] = {
        "editorial_plan_version": EDITORIAL_PLAN_VERSION,
        "rows": [
            {
                "scene_number": str(r.get("scene_number") or ""),
                "script_segment": str(r.get("script_segment") or "")[:120],
                "asset_type": str(r.get("asset_type") or ""),
                "prompt": str(r.get("prompt") or r.get("stock") or "")[:80],
            }
            for r in rows
        ],
    }
    if visual_plan_dict:
        payload["visual_plan"] = visual_plan_dict
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_editorial_plan(state_dir: Path) -> dict:
    path = plan_file(state_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_editorial_plan(state_dir: Path, plan: EditorialPlan) -> Path:
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = plan_file(state_dir)
    path.write_text(
        json.dumps(plan.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_cached_plan(
    state_dir: Path,
    *,
    audio_key: str,
    settings_key: str,
) -> Optional[EditorialPlan]:
    cached = load_editorial_plan(state_dir)
    if not cached:
        return None
    if int(cached.get("version") or 0) != EDITORIAL_PLAN_VERSION:
        return None
    if cached.get("audio_key") != audio_key:
        return None
    if cached.get("settings_key") != settings_key:
        return None
    plan_blob = cached.get("scenes")
    if not isinstance(plan_blob, list):
        return None
    return EditorialPlan.from_dict(cached)
