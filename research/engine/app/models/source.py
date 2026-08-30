"""Source (provenance) models."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AccessStatus(str, Enum):
    """Why a page was or wasn't accessible — kept distinct from SourceType so
    ranking/provenance can reason about reachability independently of trust."""

    OK = "ok"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    ROBOTS_DISALLOWED = "robots_disallowed"
    EMPTY_RESPONSE = "empty_response"
    """A successful status code (e.g. 200/202) but no usable HTML body —
    commonly an anti-bot interstitial/challenge response rather than a real
    error, but still not something we extracted anything from."""
    UNKNOWN_ERROR = "unknown_error"


class SourceType(str, Enum):
    OFFICIAL = "official"
    GOVERNMENT = "government"
    ACADEMIC = "academic"
    NEWS = "news"
    LISTING = "listing"
    COMPANY = "company"
    ARCHIVE = "archive"
    SOCIAL = "social"
    AGGREGATOR = "aggregator"
    UNKNOWN = "unknown"


class Source(BaseModel):
    """A single web page or document used as research provenance."""

    source_id: str
    source_url: str
    source_title: Optional[str] = None
    source_type: SourceType = SourceType.UNKNOWN
    domain: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status_code: Optional[int] = None
    accessible: bool = True
    access_status: AccessStatus = AccessStatus.OK
    error: Optional[str] = None
    """Human-readable failure reason, mirrors `access_status`."""
    quality_score: float = 0.0
    normalized_url: Optional[str] = None
    is_primary: bool = False
    """True when this URL was supplied directly by the caller (topic/script
    URLs or --url), as opposed to discovered via search — a signal that this
    is likely the "original" source rather than a secondary mention."""

    is_same_property: Optional[bool] = None
    """V3 property-centric pipeline only: whether this page was determined
    to be about the same target property (None when not evaluated, e.g. a
    non-property-focused run)."""
    property_match_score: Optional[float] = None
    property_match_reasons: list[str] = Field(default_factory=list)
    match_classification: Optional[str] = None
    """V4: one of PRIMARY / SECONDARY_SAME_PROPERTY / UNRELATED / UNCERTAIN —
    see property_researcher.classify_source_match. None when not evaluated."""
