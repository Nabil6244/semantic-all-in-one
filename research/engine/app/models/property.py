"""Property identity: a normalized fingerprint of "the exact listing" a
script/topic/URL is about, plus the result of matching a candidate
page/entity against it.

This is the backbone of the V3 property-centric pipeline: everything
downstream (source discovery, media collection, ranking) is scoped to "does
this belong to THIS property," not "is this near-topic content from a
real-estate site."
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PropertyIdentity(BaseModel):
    """A deterministic fingerprint built from the strongest available
    identifiers for one specific real-world property/listing."""

    canonical_address: Optional[str] = None
    """Best single human-readable address string, e.g. from schema.org PostalAddress."""
    normalized_address: Optional[str] = None
    """Lowercased, punctuation-stripped, whitespace-collapsed form used for comparison."""
    street_number: Optional[str] = None
    street_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

    listing_ids: List[str] = Field(default_factory=list)
    mls_ids: List[str] = Field(default_factory=list)

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    property_name: Optional[str] = None
    acreage: Optional[float] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    sqft: Optional[float] = None
    price: Optional[float] = None

    confidence: float = 0.0
    """How confident we are this fingerprint actually identifies one real
    property (more/stronger identifiers = higher). Not the same thing as a
    SamePropertyMatch confidence — this is about the fingerprint itself."""
    evidence: List[str] = Field(default_factory=list)
    """Human-readable notes on what identifiers were available and where
    they came from — e.g. "address from JSON-LD PostalAddress (source_001)"."""

    def has_strong_identifier(self) -> bool:
        return bool(
            self.listing_ids or self.mls_ids or self.normalized_address
            or (self.latitude is not None and self.longitude is not None)
        )


class SamePropertyMatch(BaseModel):
    """Result of comparing a candidate page/entity's identifiers against a
    target `PropertyIdentity`. Conservative by design — a missed secondary
    source is far cheaper than confidently attaching the wrong property's
    photos to a script about a different one."""

    is_match: bool
    confidence: float
    match_score: float
    reasons: List[str] = Field(default_factory=list)
