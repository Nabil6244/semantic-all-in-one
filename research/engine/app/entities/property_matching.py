"""Property identity fingerprinting and same-property matching.

Two jobs:
1. `build_property_identity` — turn a `NormalizedEntity` (already produced
   by the real_estate domain adapter) + its source facts into a
   `PropertyIdentity` fingerprint.
2. `match_property` — decide whether a *candidate* identity (built the same
   way, from a different page) refers to the same real-world property as a
   *target* identity, with a conservative, explainable weighted score.

Deliberately reuses the existing `NormalizedEntity`/`Fact` shapes rather than
re-extracting anything — this module only compares and fingerprints.
"""
from __future__ import annotations

import re
from typing import List, Optional

from app.models.entity import NormalizedEntity
from app.models.fact import Fact
from app.models.property import PropertyIdentity, SamePropertyMatch
from app.ranking.relevance import text_similarity

_ADDR_STRIP_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
_STREET_SPLIT_RE = re.compile(r"^\s*(\d+[\w-]*)\s+(.*)$")

# Conservative: at least one of these signals must fire for a match to be
# accepted at all, no matter how much weak/supporting evidence piles up.
_MATCH_THRESHOLD = 0.5


def normalize_address_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = _ADDR_STRIP_RE.sub(" ", text.lower())
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    return cleaned or None


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def build_property_identity(entity: NormalizedEntity, facts: List[Fact]) -> PropertyIdentity:
    attrs = entity.attributes
    loc = entity.location
    evidence: List[str] = []

    street = loc.street if loc else None
    street_number = street_name = None
    if street:
        m = _STREET_SPLIT_RE.match(street.strip())
        if m:
            street_number, street_name = m.group(1), m.group(2)

    canonical_parts = [
        p for p in [
            street, loc.city if loc else None, loc.state if loc else None,
            loc.postal_code if loc else None, loc.country if loc else None,
        ] if p
    ]
    canonical_address = ", ".join(canonical_parts) if canonical_parts else attrs.get("address")
    normalized_address = normalize_address_text(canonical_address)
    if normalized_address:
        evidence.append(f"normalized address: {normalized_address}")

    listing_ids: List[str] = []
    mls_ids: List[str] = []
    listing_fact = next((f for f in facts if f.key == "listing_id"), None)
    if listing_fact:
        listing_ids.append(listing_fact.value)
        haystack = f"{listing_fact.original_text or ''} {listing_fact.context or ''}".lower()
        if "mls" in haystack:
            mls_ids.append(listing_fact.value)
        evidence.append(f"listing_id: {listing_fact.value}")

    lat = _to_float(loc.latitude) if loc else None
    lon = _to_float(loc.longitude) if loc else None
    if lat is not None and lon is not None:
        evidence.append(f"coordinates: {lat:.4f},{lon:.4f}")

    if entity.name:
        evidence.append(f"property_name: {entity.name}")

    identity = PropertyIdentity(
        canonical_address=canonical_address,
        normalized_address=normalized_address,
        street_number=street_number,
        street_name=street_name,
        city=loc.city if loc else None,
        state=loc.state if loc else None,
        postal_code=loc.postal_code if loc else None,
        country=loc.country if loc else None,
        listing_ids=listing_ids,
        mls_ids=mls_ids,
        latitude=lat,
        longitude=lon,
        property_name=entity.name,
        acreage=_to_float(attrs.get("acreage")),
        bedrooms=_to_float(attrs.get("bedrooms")),
        bathrooms=_to_float(attrs.get("bathrooms")),
        sqft=_to_float(attrs.get("square_footage") or attrs.get("square_feet")),
        price=_to_float(attrs.get("price")),
        evidence=evidence,
    )

    score = 0.0
    if identity.normalized_address:
        score += 0.4
    if identity.listing_ids or identity.mls_ids:
        score += 0.35
    if identity.latitude is not None and identity.longitude is not None:
        score += 0.25
    if identity.property_name:
        score += 0.1
    if identity.city and identity.state:
        score += 0.1
    identity.confidence = round(min(score, 1.0), 4)
    return identity


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _close(a: Optional[float], b: Optional[float], tolerance_ratio: float) -> bool:
    if a is None or b is None:
        return False
    if a == 0 and b == 0:
        return True
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= tolerance_ratio


def match_property(candidate: PropertyIdentity, target: PropertyIdentity) -> SamePropertyMatch:
    """Conservative weighted match. A match requires at least one strong or
    medium signal (listing/MLS ID, normalized address, coordinate proximity,
    street+city+state, or a strongly similar property name) — accumulated
    weak/supporting evidence (acreage/price/beds/baths) alone never crosses
    the threshold on its own."""
    reasons: List[str] = []
    score = 0.0
    has_strong_or_medium = False

    shared_ids = (set(candidate.listing_ids) | set(candidate.mls_ids)) & (
        set(target.listing_ids) | set(target.mls_ids)
    )
    if shared_ids:
        score += 0.9
        has_strong_or_medium = True
        reasons.append(f"shared listing/MLS ID: {', '.join(sorted(shared_ids))}")

    if candidate.normalized_address and candidate.normalized_address == target.normalized_address:
        score += 0.85
        has_strong_or_medium = True
        reasons.append("matching normalized address")

    if (
        candidate.latitude is not None and candidate.longitude is not None
        and target.latitude is not None and target.longitude is not None
    ):
        distance_km = _haversine_km(candidate.latitude, candidate.longitude, target.latitude, target.longitude)
        if distance_km <= 0.5:  # ~500m — same parcel, allows for GPS jitter
            score += 0.6
            has_strong_or_medium = True
            reasons.append(f"coordinates within {distance_km * 1000:.0f}m")

    if (
        not has_strong_or_medium
        and candidate.street_name and candidate.city and candidate.state
        and candidate.street_name.lower() == (target.street_name or "").lower()
        and candidate.city.lower() == (target.city or "").lower()
        and candidate.state.lower() == (target.state or "").lower()
    ):
        score += 0.5
        has_strong_or_medium = True
        reasons.append("matching street + city + state")

    if candidate.property_name and target.property_name:
        name_sim = text_similarity(candidate.property_name, target.property_name)
        if name_sim >= 0.5:
            score += 0.25
            has_strong_or_medium = True
            reasons.append(f"similar property name (similarity={name_sim:.2f})")

    # Supporting evidence only — never sufficient alone.
    if _close(candidate.acreage, target.acreage, 0.05):
        score += 0.05
        reasons.append("matching acreage")
    if _close(candidate.price, target.price, 0.1):
        score += 0.05
        reasons.append("matching price (within 10%)")
    if candidate.bedrooms is not None and candidate.bedrooms == target.bedrooms:
        score += 0.03
        reasons.append("matching bedroom count")
    if candidate.bathrooms is not None and candidate.bathrooms == target.bathrooms:
        score += 0.03
        reasons.append("matching bathroom count")
    if _close(candidate.sqft, target.sqft, 0.05):
        score += 0.03
        reasons.append("matching square footage")

    match_score = round(min(score, 1.0), 4)
    is_match = has_strong_or_medium and match_score >= _MATCH_THRESHOLD

    comparable = sum(
        1 for pair in (
            (candidate.normalized_address, target.normalized_address),
            (candidate.listing_ids or candidate.mls_ids, target.listing_ids or target.mls_ids),
            (candidate.latitude, target.latitude),
            (candidate.property_name, target.property_name),
        ) if pair[0] and pair[1]
    )
    confidence = match_score if comparable >= 2 else round(match_score * 0.75, 4)

    if not reasons:
        reasons.append("no comparable identifiers found")

    return SamePropertyMatch(is_match=is_match, confidence=confidence, match_score=match_score, reasons=reasons)
