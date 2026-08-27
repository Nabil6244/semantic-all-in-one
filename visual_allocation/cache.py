"""Allocation cache fingerprint helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from .models import ALLOCATION_ENGINE_VERSION, AllocationSettings


def allocation_cache_key(
    *,
    script_fingerprint: str,
    style_fingerprint: Optional[dict] = None,
    settings: Optional[AllocationSettings] = None,
) -> str:
    payload = {
        "allocation_version": ALLOCATION_ENGINE_VERSION,
        "script": script_fingerprint,
        "style": style_fingerprint or {},
        "settings": (settings or AllocationSettings()).fingerprint(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def script_fingerprint_from_plan(plan_dict: dict) -> str:
    scenes = plan_dict.get("scenes") if isinstance(plan_dict, dict) else []
    parts = []
    for s in scenes or []:
        if not isinstance(s, dict):
            continue
        parts.append(
            "|".join(
                [
                    str(s.get("scene_id", "")),
                    str(s.get("narration", ""))[:120],
                    str(s.get("visual_description", ""))[:80],
                ]
            )
        )
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
