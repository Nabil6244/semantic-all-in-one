"""Semantic visual QA — metadata first, optional vision tier."""

from __future__ import annotations

import re
from typing import List, Optional, Set

from providers.base import AssetResult, SceneRow
from providers.media_quality.scoring import relevance_score
from style_engine.schema import ResolvedStyle
from style_engine.visual_profile import build_scene_visual_profile
from style_engine.visual_selection import build_selection_context

_TOKEN = re.compile(r"[a-z0-9]+")

_GENERIC = frozenset({
    "ocean", "waves", "water", "city", "people", "walking", "business",
    "office", "nature", "sky", "background", "abstract", "generic",
})


def _tokens(text: str) -> Set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def metadata_semantic_score(
    scene: SceneRow,
    result: AssetResult,
    resolved: Optional[ResolvedStyle] = None,
) -> tuple[float, list[str]]:
    """Level 2 — narration vs asset metadata relevance."""
    warnings: list[str] = []
    meta = result.metadata or {}
    title = str(meta.get("title") or meta.get("alt") or "")
    desc = str(meta.get("description") or meta.get("tags") or "")
    query = scene.prompt or scene.stock or ""
    visual = getattr(scene, "visual_description", "") or ""

    rel = relevance_score(
        query=query or scene.script_segment,
        script_segment=scene.script_segment,
        visual_description=visual,
        title=title,
        description=desc,
        extra_text=str(meta.get("source_url") or ""),
    )
    score = min(1.0, rel / 3.0)

    narr_t = _tokens(scene.script_segment)
    asset_t = _tokens(f"{title} {desc} {query}")
    if narr_t and asset_t:
        overlap = len(narr_t & asset_t) / max(len(narr_t), 1)
        if overlap < 0.08 and score < 0.45:
            warnings.append("semantic mismatch — generic or wrong subject")
            score *= 0.7

    ctx = build_selection_context(scene, resolved)
    role = ctx.profile.visual_role
    if role in ("scientific_visualization", "event", "archival_evidence"):
        specific = narr_t - _GENERIC
        if specific and len(specific & asset_t) == 0 and score < 0.5:
            warnings.append("specific scene beat not reflected in asset metadata")
            score *= 0.65

    return max(0.0, min(1.0, score)), warnings


def needs_vision_inspection(
    scene: SceneRow,
    result: AssetResult,
    *,
    semantic: float,
    technical: float,
    importance: str = "medium",
) -> bool:
    """Level 3 gate — vision only when uncertain."""
    source = getattr(result.source, "value", str(result.source or "")).lower()
    if source in ("flow_video", "flow_image", "video", "image"):
        if semantic < 0.55 or technical < 0.6:
            return True
    if importance == "high" and semantic < 0.65:
        return True
    if semantic < 0.45:
        return True
    if technical < 0.5:
        return True
    return False


def vision_semantic_score(
    scene: SceneRow,
    frame_paths: List,
    *,
    settings: Optional[dict] = None,
) -> tuple[Optional[float], list[str]]:
    """Optional Gemini vision verification — returns None if unavailable."""
    if not frame_paths:
        return None, []
    api_key = ""
    if settings:
        from visual_director.llm import resolve_gemini_api_key

        api_key = resolve_gemini_api_key(settings)
    if not api_key:
        return None, []

    try:
        import base64
        import json
        import requests

        parts = [
            {
                "text": (
                    "You verify documentary B-roll. Return JSON only: "
                    '{"semantic_match":0-1,"usable":true/false,"reason":"..."}\n'
                    f"Narration: {scene.script_segment[:400]}\n"
                    f"Required visual: {(scene.prompt or scene.stock or '')[:200]}"
                )
            }
        ]
        for fp in frame_paths[:2]:
            p = fp if hasattr(fp, "read_bytes") else None
            from pathlib import Path

            path = Path(fp)
            if not path.is_file() or path.stat().st_size > 900_000:
                continue
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 256},
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )
        resp = requests.post(url, json=body, timeout=45)
        if resp.status_code != 200:
            return None, []
        text = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return None, []
        data = json.loads(text[start:end])
        score = float(data.get("semantic_match") or 0)
        warnings = []
        if not data.get("usable", True):
            warnings.append(str(data.get("reason") or "vision: not usable"))
        return max(0.0, min(1.0, score)), warnings
    except Exception:
        return None, []
