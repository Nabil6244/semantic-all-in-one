"""Simple lexical ranking for documentary clip candidates."""

from __future__ import annotations

import re
from typing import Callable, List, Sequence, TypeVar

from providers.media_quality.scoring import selection_score

_TOKEN = re.compile(r"[a-z0-9]+")

T = TypeVar("T")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def score_text(query: str, *parts: str) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    blob = " ".join(p for p in parts if p)
    t = _tokens(blob)
    if not t:
        return 0.0
    overlap = len(q & t) / len(q)
    return overlap


def rank_by_text(
    candidates: Sequence[T],
    query: str,
    text_fn: Callable[[T], tuple],
    *,
    script_segment: str = "",
    visual_description: str = "",
    provider: str = "",
    width_fn: Callable[[T], int] | None = None,
    height_fn: Callable[[T], int] | None = None,
    url_fn: Callable[[T], str] | None = None,
    duration_fn: Callable[[T], float | None] | None = None,
    asset_id_fn: Callable[[T], str] | None = None,
    used_asset_ids: set[str] | None = None,
    provider_use_counts: dict[str, int] | None = None,
    selection_context=None,
    log=None,
) -> List[T]:
    """Rank clip candidates by relevance + quality (metadata only)."""
    scored: List[tuple[float, T]] = []
    for c in candidates:
        parts = text_fn(c)
        title = parts[0] if parts else ""
        description = " ".join(str(p) for p in parts[1:] if p)
        w = width_fn(c) if width_fn else 0
        h = height_fn(c) if height_fn else 0
        url = url_fn(c) if url_fn else ""
        dur = duration_fn(c) if duration_fn else None
        aid = asset_id_fn(c) if asset_id_fn else ""
        if selection_context is not None:
            from style_engine.visual_selection import smart_selection_score

            breakdown = smart_selection_score(
                query=query,
                script_segment=script_segment,
                visual_description=visual_description,
                title=str(title),
                description=str(description),
                width=w,
                height=h,
                download_url=url,
                provider=provider,
                media_type="video",
                duration=dur,
                used_asset_ids=used_asset_ids,
                asset_id=aid,
                provider_use_counts=provider_use_counts,
                is_archival=True,
                context=selection_context,
            )
        else:
            breakdown = selection_score(
                query=query,
                script_segment=script_segment,
                visual_description=visual_description,
                title=str(title),
                description=str(description),
                width=w,
                height=h,
                download_url=url,
                provider=provider,
                media_type="video",
                duration=dur,
                used_asset_ids=used_asset_ids,
                asset_id=aid,
                provider_use_counts=provider_use_counts,
                is_archival=True,
            )
        if breakdown.reject_reason:
            if log:
                log(f"[{provider.upper()}] rejected {aid or title}: {breakdown.reject_reason}")
            # Archival: allow marginal items if nothing else passes floor
            fallback = score_text(query, script_segment, visual_description, title, description)
            if fallback <= 0:
                continue
            scored.append((fallback * 2.0, c))
            continue
        scored.append((breakdown.total, c))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if log and scored:
        log(f"[{provider.upper()}] top candidate score={scored[0][0]:.2f}")
    return [c for _, c in scored] or list(candidates)
