"""Project-level repetition QA."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from providers.base import AssetResult
from scene_recovery import scene_key
from style_engine.visual_selection import SelectionHistory

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> Set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def score_repetition(
    asset_id: str,
    title: str,
    description: str,
    history: Optional[SelectionHistory],
    *,
    project_asset_ids: Optional[Set[str]] = None,
) -> tuple[float, list[str]]:
    """1.0 = fresh; lower = repetitive."""
    warnings: list[str] = []
    score = 1.0
    aid = (asset_id or "").strip()
    if aid and history and aid in history.used_asset_ids:
        score -= 0.45
        warnings.append("duplicate asset ID in project")
    if aid and project_asset_ids and aid in project_asset_ids:
        score -= 0.35
        warnings.append("asset reused across scenes")

    blob = _tokens(f"{title} {description}")
    if history and blob:
        overlap = len(blob & history.concept_tokens)
        if overlap >= 4:
            score -= 0.2
            warnings.append("repeated visual concept")
        subj = blob & history.subject_tokens
        if len(subj) >= 2:
            score -= 0.12
            warnings.append("repeated subject")

    if history and history.provider_counts:
        top = max(history.provider_counts.values()) if history.provider_counts else 0
        if top >= 8:
            score -= 0.08
            warnings.append("provider concentration")

    return max(0.0, min(1.0, score)), warnings


def collect_project_asset_ids(results: Dict[str, AssetResult]) -> Dict[str, str]:
    """Map asset_id -> first scene key."""
    seen: Dict[str, str] = {}
    for key, result in results.items():
        if not getattr(result, "ok", False):
            continue
        meta = getattr(result, "metadata", None) or {}
        aid = str(meta.get("provider_asset_id") or meta.get("asset_id") or "")
        if aid and aid not in seen:
            seen[aid] = key
    return seen


def detect_project_repetition_issues(
    results: Dict[str, AssetResult],
) -> List[str]:
    """Soft project-level warnings."""
    by_asset: Dict[str, List[str]] = {}
    for key, result in results.items():
        if not getattr(result, "ok", False):
            continue
        meta = getattr(result, "metadata", None) or {}
        aid = str(meta.get("provider_asset_id") or meta.get("asset_id") or "")
        if aid:
            by_asset.setdefault(aid, []).append(key)
    issues = []
    for aid, keys in by_asset.items():
        if len(keys) > 1:
            issues.append(f"asset {aid} used in scenes {', '.join(keys)}")
    return issues
