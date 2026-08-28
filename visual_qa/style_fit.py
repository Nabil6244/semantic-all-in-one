"""Style-aware QA thresholds — reuses Style Intelligence 3.0."""

from __future__ import annotations

from typing import Optional

from style_engine.schema import ResolvedStyle


ARCHIVAL_STYLE_IDS = frozenset({
    "history_documentary",
    "ancient_history_documentary",
    "military_war_documentary",
    "true_crime_documentary",
    "geopolitics_documentary",
})

PREMIUM_STYLE_IDS = frozenset({
    "premium_documentary",
    "space_documentary",
    "nature_wildlife_documentary",
})

AI_NARRATION_STYLE = "ai_narration"


def style_id_from_resolved(resolved: Optional[ResolvedStyle]) -> str:
    if resolved is None:
        return ""
    return str(resolved.style_id or getattr(resolved.style, "id", "") or "")


def is_archival_context(
    resolved: Optional[ResolvedStyle],
    *,
    provider: str = "",
    asset_type: str = "",
) -> bool:
    sid = style_id_from_resolved(resolved)
    if sid in ARCHIVAL_STYLE_IDS:
        return True
    p = (provider or "").lower()
    if p in ("archive", "internet_archive", "nasa"):
        return True
    if (asset_type or "").lower() in ("archive_video", "nasa_video"):
        return True
    return False


def style_quality_expectation(resolved: Optional[ResolvedStyle]) -> float:
    """How strict composition/polish expectations are (0–1)."""
    sid = style_id_from_resolved(resolved)
    if sid in PREMIUM_STYLE_IDS:
        return 0.85
    if sid == AI_NARRATION_STYLE:
        return 0.65
    if sid in ARCHIVAL_STYLE_IDS:
        return 0.45
    return 0.6


def adjust_technical_penalty(base_penalty: float, resolved: Optional[ResolvedStyle], is_archival: bool) -> float:
    if is_archival:
        return base_penalty * 0.35
    sid = style_id_from_resolved(resolved)
    if sid in PREMIUM_STYLE_IDS:
        return base_penalty * 1.1
    return base_penalty


def score_style_fit(
    semantic: float,
    technical: float,
    resolved: Optional[ResolvedStyle],
    *,
    is_archival: bool,
) -> float:
    expect = style_quality_expectation(resolved)
    if is_archival:
        return min(1.0, 0.55 + semantic * 0.35 + technical * 0.1)
    blend = semantic * 0.5 + technical * 0.5
    if blend >= expect:
        return min(1.0, blend + 0.05)
    return max(0.0, blend - (expect - blend) * 0.3)
