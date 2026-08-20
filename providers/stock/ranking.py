"""Candidate filtering + ranking. Deliberately does NOT weight video duration
heavily — actual scene duration is only known after Whisper alignment, and the
existing renderer already loops/trims video to fit whatever duration it gets."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable, List, Set

if TYPE_CHECKING:
    from .base import Candidate

MIN_WIDTH = 1000
MIN_HEIGHT = 600

_WORD_RE = re.compile(r"[a-z0-9]+")


def filter_candidates(candidates: Iterable["Candidate"]) -> List["Candidate"]:
    """Landscape only (matches this app's current default 1920x1080 output) and a
    minimum resolution floor so we never pick something that'll look soft after
    the renderer's cover-crop to full frame."""
    out = []
    for c in candidates:
        if c.orientation != "landscape":
            continue
        if c.width < MIN_WIDTH or c.height < MIN_HEIGHT:
            continue
        out.append(c)
    return out


def _tokens(text: str) -> Set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def _relevance_score(candidate: "Candidate", query: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    haystack = (
        _tokens(candidate.source_url)
        | _tokens(candidate.extra.get("alt", ""))
        | _tokens(candidate.author)
    )
    if not haystack:
        return 0.0
    return len(query_tokens & haystack) / len(query_tokens)


def rank_candidates(
    candidates: List["Candidate"], query: str, used_asset_ids: Set[str]
) -> List["Candidate"]:
    def score(c: "Candidate") -> float:
        s = _relevance_score(c, query) * 3.0
        # Resolution: reward, capped so an 8K image doesn't dominate a fine 1080p match.
        pixels = c.width * c.height
        hd = 1920 * 1080
        if pixels <= hd:
            s += pixels / hd
        else:
            # Huge 4K+ stock videos stall downloads; prefer 1080p-class files.
            s += max(0.4, 1.0 - min((pixels - hd) / hd, 0.8))
        if c.media_type.value == "video" and c.duration and c.duration >= 2:
            s += 0.5  # mild bonus for a usable (not near-zero-length) clip
        if c.media_type.value == "video" and c.width >= 3840:
            s -= 1.2
        if c.asset_id in used_asset_ids:
            s -= 5.0  # strong repeat-penalty: heavily discourage reusing the same asset
        return s

    return sorted(candidates, key=score, reverse=True)
