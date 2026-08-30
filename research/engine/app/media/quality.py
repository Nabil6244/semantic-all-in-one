"""Measured image quality tiers.

Tiering is deliberately based on the LONG SIDE of *measured* pixel
dimensions. Declared dimensions (from srcset `w` descriptors, embedded-JSON
`width` keys, or `<img width>`) are kept for provenance and used only as a
clearly-labelled fallback when a probe was impossible — never mixed silently
with measured values, because the whole point of probing is that declared
numbers are frequently wrong.

If the only version of a photo a site exposes is small, it is retained at
its true tier. Nothing here upscales, rewrites, or invents a larger URL.
"""
from __future__ import annotations

from typing import Optional

# Long-side thresholds, per the media-quality requirement.
TIER_1_MIN = 1600
TIER_2_MIN = 1200
TIER_3_MIN = 960

TIER_LABELS = {
    1: "tier1_1600plus",
    2: "tier2_1200plus",
    3: "tier3_960plus",
    4: "tier4_below960",
}


def quality_tier(long_side: Optional[int]) -> Optional[int]:
    """1..4 for a known long side, or None when the size is unknown.

    None is NOT tier 4 — "we could not measure this" and "we measured this
    and it is small" are different facts, and collapsing them would let an
    unprobeable image masquerade as a known-bad one (or vice versa)."""
    if not long_side or long_side <= 0:
        return None
    if long_side >= TIER_1_MIN:
        return 1
    if long_side >= TIER_2_MIN:
        return 2
    if long_side >= TIER_3_MIN:
        return 3
    return 4


def tier_label(tier: Optional[int]) -> str:
    return TIER_LABELS.get(tier or 0, "unknown")


def tier_score(tier: Optional[int]) -> float:
    """Normalized 0..1 ranking contribution. Unknown sizes score below
    tier 3 but above tier 4: an unmeasured image might be excellent, but it
    must never outrank an image we have positively measured as large."""
    return {1: 1.0, 2: 0.75, 3: 0.5, 4: 0.15}.get(tier or 0, 0.35)
