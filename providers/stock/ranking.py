"""Candidate filtering + ranking. Deliberately does NOT weight video duration
heavily — actual scene duration is only known after Whisper alignment, and the
existing renderer already loops/trims video to fit whatever duration it gets."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable, List, Optional, Set

from providers.media_quality.scoring import (
    effective_dimensions,
    passes_quality_floor,
    selection_score,
)

if TYPE_CHECKING:
    from ..base import SceneRow
    from .base import Candidate

_WORD_RE = re.compile(r"[a-z0-9]+")


def filter_candidates(candidates: Iterable["Candidate"]) -> List["Candidate"]:
    """Landscape + metadata quality floor (preview/derivative URLs rejected)."""
    out = []
    for c in candidates:
        if c.orientation != "landscape":
            continue
        ew, eh = effective_dimensions(c.width, c.height, c.url, c.provider)
        ok, _ = passes_quality_floor(
            width=ew,
            height=eh,
            download_url=c.url,
            provider=c.provider,
            media_type=c.media_type.value,
            duration=c.duration,
            is_archival=False,
        )
        if ok:
            out.append(c)
    return out


def _tokens(text: str) -> Set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def _relevance_score(candidate: "Candidate", query: str) -> float:
    """Legacy helper — kept for tests that import it directly."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    haystack = (
        _tokens(candidate.source_url)
        | _tokens(candidate.extra.get("alt", ""))
        | _tokens(candidate.extra.get("tags", ""))
        | _tokens(candidate.author)
    )
    if not haystack:
        return 0.0
    return len(query_tokens & haystack) / len(query_tokens)


def _candidate_dedupe_key(candidate: "Candidate") -> str:
    raw = (candidate.url or candidate.source_url or "").lower().strip()
    if raw:
        return raw.split("?")[0].rstrip("/")
    title = (
        candidate.extra.get("alt", "")
        or candidate.extra.get("tags", "")
        or ""
    ).lower().strip()
    if len(title) >= 8:
        return f"title:{title[:96]}"
    return f"{candidate.provider}:{candidate.asset_id}"


def dedupe_candidates(candidates: List["Candidate"]) -> List["Candidate"]:
    """Drop cross-provider duplicates (same URL or near-identical title)."""
    seen: set[str] = set()
    out: List["Candidate"] = []
    for c in candidates:
        key = _candidate_dedupe_key(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def rank_candidates(
    candidates: List["Candidate"],
    query: str,
    used_asset_ids: Set[str],
    *,
    scene: Optional["SceneRow"] = None,
    provider_use_counts: Optional[dict[str, int]] = None,
    selection_context=None,
    required_duration: Optional[float] = None,
    log=None,
) -> List["Candidate"]:
    candidates = dedupe_candidates(candidates)
    scored: List[tuple[float, Candidate, object]] = []
    script = getattr(scene, "script_segment", "") or ""
    visual = getattr(scene, "visual_description", "") or ""
    style_id = ""
    if selection_context is not None:
        style_id = getattr(selection_context, "style_id", "") or ""

    for c in candidates:
        ew, eh = effective_dimensions(c.width, c.height, c.url, c.provider)
        if selection_context is not None:
            from style_engine.visual_selection import smart_selection_score

            breakdown = smart_selection_score(
                query=query,
                script_segment=script,
                visual_description=visual,
                title=c.extra.get("alt", "") or c.extra.get("tags", ""),
                description=c.extra.get("tags", "") or c.extra.get("alt", ""),
                extra_text=c.source_url,
                width=ew,
                height=eh,
                download_url=c.url,
                provider=c.provider,
                media_type=c.media_type.value,
                duration=c.duration,
                used_asset_ids=used_asset_ids,
                asset_id=c.asset_id,
                provider_use_counts=provider_use_counts,
                is_archival=False,
                context=selection_context,
                required_duration=required_duration,
            )
        else:
            breakdown = selection_score(
                query=query,
                script_segment=script,
                visual_description=visual,
                title=c.extra.get("alt", "") or c.extra.get("tags", ""),
                description=c.extra.get("tags", "") or c.extra.get("alt", ""),
                extra_text=c.source_url,
                width=ew,
                height=eh,
                download_url=c.url,
                provider=c.provider,
                media_type=c.media_type.value,
                duration=c.duration,
                used_asset_ids=used_asset_ids,
                asset_id=c.asset_id,
                provider_use_counts=provider_use_counts,
                is_archival=False,
                style_id=style_id,
            )
        if breakdown.reject_reason:
            if log:
                log(
                    f"[STOCK] rejected {c.provider}/{c.asset_id}: {breakdown.reject_reason}"
                )
            continue
        scored.append((breakdown.total, c, breakdown))

    scored.sort(key=lambda row: row[0], reverse=True)
    if log and scored:
        best = scored[0]
        b = best[2]
        c = best[1]
        log(
            f"[STOCK] ranked top {c.provider} {c.width}x{c.height} "
            f"Q={b.quality:.2f} R={b.relevance:.2f} role={b.visual_role_score:.2f} "
            f"style={b.style_fit_score:.2f} score={b.total:.2f}"
        )
    return [c for _, c, _ in scored]
