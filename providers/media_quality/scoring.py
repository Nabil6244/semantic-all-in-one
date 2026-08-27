"""Metadata-first quality, relevance, and selection scoring for media candidates.

Used by stock, archive, and NASA providers. Does not download or decode media.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Optional, Set

_TOKEN = re.compile(r"[a-z0-9]+")

# Stock footage minimum (landscape documentary default).
MIN_STOCK_WIDTH = 1000
MIN_STOCK_HEIGHT = 600

# Archival sources may be lower resolution but still valuable.
MIN_ARCHIVAL_WIDTH = 480
MIN_ARCHIVAL_HEIGHT = 270

_PREVIEW_MARKERS = (
    "thumb",
    "thumbnail",
    "preview",
    "img-thumbs",
    "/960w/",
    "/640w/",
    "/480w/",
    "/320w/",
    "placeholder",
    "contact-sheet",
    "contact_sheet",
    "posterframe",
    "sprite",
)

_PROXY_MARKERS = (
    "proxy",
    "sample",
    "lowres",
    "low-res",
    "low_res",
    "webrip",
    "~small",
    "~mobile",
    "~thumb",
)

_DERIVATIVE_MARKERS = _PREVIEW_MARKERS + _PROXY_MARKERS


@dataclasses.dataclass
class ScoreBreakdown:
    quality: float = 0.0
    relevance: float = 0.0
    usability: float = 0.0
    reliability: float = 0.0
    duplicate_penalty: float = 0.0
    provider_repetition_penalty: float = 0.0
    technical_risk: float = 0.0
    reject_reason: str = ""
    # Style Intelligence 3.0 signals (optional — zero when not used)
    visual_role_score: float = 0.0
    style_fit_score: float = 0.0
    source_score: float = 0.0
    evidence_score: float = 0.0
    concept_repetition_penalty: float = 0.0
    duration_fit_score: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.quality
            + self.relevance
            + self.usability
            + self.reliability
            + self.visual_role_score * 0.45
            + self.style_fit_score * 0.35
            + self.source_score
            + self.evidence_score
            + self.duration_fit_score
            - self.duplicate_penalty
            - self.provider_repetition_penalty
            - self.concept_repetition_penalty
            - self.technical_risk
        )

    @property
    def final_selection_score(self) -> float:
        """Alias for reporting — semantic relevance + role + quality dominate."""
        return self.total


def _tokens(text: str) -> Set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def is_preview_or_derivative_url(url: str) -> bool:
    u = (url or "").lower()
    return any(marker in u for marker in _DERIVATIVE_MARKERS)


def is_archival_provider(provider: str) -> bool:
    return (provider or "").lower() in {"archive", "internet_archive", "nasa"}


def effective_dimensions(
    width: int,
    height: int,
    download_url: str,
    provider: str = "",
) -> tuple[int, int]:
    """When URL clearly indicates a derivative, cap advertised dimensions."""
    w, h = max(0, int(width or 0)), max(0, int(height or 0))
    url = (download_url or "").lower()
    if not url:
        return w, h
    if "960w" in url or "/960/" in url:
        return min(w, 960), min(h, 640) if h else h
    if "640w" in url or "webformat" in url:
        return min(w, 640), min(h, 427) if h else h
    if "480w" in url or "~medium" in url:
        return min(w, 854), min(h, 480) if h else h
    if "~large" in url and "~orig" not in url:
        return min(w, 1280), min(h, 720) if h else h
    if is_preview_or_derivative_url(url) and w > 960:
        return min(w, 960), min(h, 540) if h else h
    if provider == "pixabay" and "largeimageurl" not in url and "imageurl" not in url:
        if "webformat" in url:
            return min(w, 640), min(h, 427) if h else h
        if "large" in url:
            return min(w, 1280), min(h, 853) if h else h
    return w, h


def passes_quality_floor(
    *,
    width: int,
    height: int,
    download_url: str = "",
    provider: str = "",
    media_type: str = "video",
    duration: Optional[float] = None,
    is_archival: Optional[bool] = None,
) -> tuple[bool, str]:
    if is_preview_or_derivative_url(download_url):
        return False, "preview/derivative URL"
    archival = is_archival if is_archival is not None else is_archival_provider(provider)
    ew, eh = effective_dimensions(width, height, download_url, provider)
    if ew <= 0 or eh <= 0:
        if archival and download_url:
            return True, ""
        return False, "missing dimensions"
    if archival:
        if ew < MIN_ARCHIVAL_WIDTH or eh < MIN_ARCHIVAL_HEIGHT:
            return False, f"archival too small ({ew}x{eh})"
        return True, ""
    if ew < MIN_STOCK_WIDTH or eh < MIN_STOCK_HEIGHT:
        return False, f"below stock floor ({ew}x{eh})"
    if media_type == "video" and duration is not None and 0 < duration < 0.8:
        return False, "clip too short"
    return True, ""


def relevance_score(
    *,
    query: str,
    script_segment: str = "",
    visual_description: str = "",
    title: str = "",
    description: str = "",
    extra_text: str = "",
) -> float:
    """Relevance beats raw resolution — weight query + scene context heavily."""
    q = _tokens(query)
    if not q:
        q = _tokens(script_segment)
    if not q:
        return 0.0
    hay = _tokens(" ".join([title, description, visual_description, script_segment, extra_text]))
    if not hay:
        return 0.0
    overlap = len(q & hay) / len(q)
    # Partial credit when only subset of query terms match (broader queries).
    if overlap < 0.35 and q & hay:
        overlap = max(overlap, 0.25 + 0.1 * len(q & hay))
    return min(1.0, overlap) * 3.0


def quality_score(
    *,
    width: int,
    height: int,
    download_url: str = "",
    provider: str = "",
    media_type: str = "video",
    duration: Optional[float] = None,
    is_archival: Optional[bool] = None,
) -> float:
    archival = is_archival if is_archival is not None else is_archival_provider(provider)
    ew, eh = effective_dimensions(width, height, download_url, provider)
    if ew <= 0 or eh <= 0:
        return 0.15 if archival else 0.0
    pixels = ew * eh
    hd = 1920 * 1080
    if archival:
        # Authentic 480p–720p archival can score well; don't punish age/resolution alone.
        if pixels >= hd:
            base = 0.85
        elif pixels >= 854 * 480:
            base = 0.75
        elif pixels >= MIN_ARCHIVAL_WIDTH * MIN_ARCHIVAL_HEIGHT:
            base = 0.55
        else:
            base = 0.2
        if "~orig" in (download_url or "").lower() or "original" in (download_url or "").lower():
            base += 0.1
        return min(1.0, base)
    if pixels <= hd:
        score = pixels / hd
    else:
        score = max(0.4, 1.0 - min((pixels - hd) / hd, 0.8))
    if media_type == "video" and duration and duration >= 2:
        score += 0.08
    if media_type == "video" and ew >= 3840:
        score -= 0.25
    if "~orig" in (download_url or "").lower():
        score += 0.12
    return max(0.0, min(1.2, score))


def provider_reliability(provider: str) -> float:
    """Small secondary signal — never dominates relevance/quality."""
    p = (provider or "").lower()
    return {
        "pexels": 0.12,
        "nasa": 0.10,
        "archive": 0.08,
        "pixabay": 0.06,
        "openverse": 0.02,
    }.get(p, 0.04)


_SPACE_HINTS = frozenset(
    {"rocket", "nasa", "planet", "orbit", "iss", "apollo", "moon", "mars", "space", "satellite"}
)
_HISTORY_HINTS = frozenset(
    {
        "archive",
        "war",
        "historical",
        "century",
        "ancient",
        "empire",
        "battle",
        "newsreel",
        "194",
        "191",
        "18",
        "17",
    }
)


def provider_topic_boost(
    provider: str,
    script_segment: str = "",
    visual_description: str = "",
    style_id: str = "",
) -> float:
    """Boost archival/NASA providers when scene + style clearly match."""
    blob = f"{script_segment} {visual_description}".lower()
    p = (provider or "").lower()
    score = 0.0
    if p in ("nasa",) and any(h in blob for h in _SPACE_HINTS):
        score += 0.32
    if p in ("archive", "internet_archive") and any(h in blob for h in _HISTORY_HINTS):
        score += 0.28
    sid = (style_id or "").lower()
    if sid == "space_documentary" and p == "nasa":
        score += 0.12
    if sid in ("history_documentary", "ancient_history_documentary", "military_war_documentary"):
        if p in ("archive", "internet_archive"):
            score += 0.1
    return score


def selection_score(
    *,
    query: str,
    script_segment: str = "",
    visual_description: str = "",
    title: str = "",
    description: str = "",
    extra_text: str = "",
    width: int = 0,
    height: int = 0,
    download_url: str = "",
    provider: str = "",
    media_type: str = "video",
    duration: Optional[float] = None,
    used_asset_ids: Optional[Set[str]] = None,
    asset_id: str = "",
    provider_use_counts: Optional[dict[str, int]] = None,
    is_archival: Optional[bool] = None,
    style_id: str = "",
) -> ScoreBreakdown:
    ok, reason = passes_quality_floor(
        width=width,
        height=height,
        download_url=download_url,
        provider=provider,
        media_type=media_type,
        duration=duration,
        is_archival=is_archival,
    )
    if not ok:
        return ScoreBreakdown(reject_reason=reason)

    rel = relevance_score(
        query=query,
        script_segment=script_segment,
        visual_description=visual_description,
        title=title,
        description=description,
        extra_text=extra_text,
    )
    qual = quality_score(
        width=width,
        height=height,
        download_url=download_url,
        provider=provider,
        media_type=media_type,
        duration=duration,
        is_archival=is_archival,
    )
    risk = 0.0
    if is_preview_or_derivative_url(download_url):
        risk += 1.5
    dup = 5.0 if asset_id and used_asset_ids and asset_id in used_asset_ids else 0.0
    rep = 0.0
    if provider_use_counts and provider:
        count = provider_use_counts.get(provider.lower(), 0)
        if count > 0:
            rep = min(0.35 * count, 1.0)
    return ScoreBreakdown(
        quality=qual,
        relevance=rel,
        usability=0.05,
        reliability=provider_reliability(provider),
        source_score=provider_topic_boost(
            provider, script_segment, visual_description, style_id
        ),
        duplicate_penalty=dup,
        provider_repetition_penalty=rep,
        technical_risk=risk,
    )
