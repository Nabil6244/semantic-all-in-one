"""Source type classification and source-quality scoring."""
from __future__ import annotations

import re
from typing import Optional

from app.models.source import SourceType

_GOV_RE = re.compile(r"\.gov(\.[a-z]{2})?$", re.I)
_ACADEMIC_RE = re.compile(r"\.(edu|ac\.[a-z]{2})$", re.I)
_ARCHIVE_HOSTS = {"web.archive.org", "archive.org"}
_SOCIAL_HOSTS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "tiktok.com",
    "reddit.com", "pinterest.com", "linkedin.com",
}
_NEWS_HINTS = ("news", "times", "post", "herald", "tribune", "gazette", "reuters", "bbc", "cnn", "apnews")
_LISTING_HINTS = ("zillow", "realtor", "redfin", "trulia", "listing", "mls", "homes.com", "apartments.com")
_COMPANY_HINTS = ("realty", "realtors", "brokerage", "properties")
"""Agency/broker company pages — e.g. an individual agent's site on a
brokerage domain. Deliberately narrower than a generic "company" guess so it
doesn't swallow unrelated business sites."""
_AGGREGATOR_HINTS = ("wikipedia.org", "wikidata.org", "yelp.com", "tripadvisor")

# Base quality weight per source type — reflects general trustworthiness,
# not topical relevance (that's ranking/relevance.py's job). LISTING ranks
# above COMPANY here to match the requested real-estate priority order
# (original listing > official agency/broker page); `is_primary` (see
# score_source_quality) is what actually drives "this is the source the
# caller pointed us at" regardless of type.
_TYPE_WEIGHTS = {
    SourceType.GOVERNMENT: 1.0,
    SourceType.ACADEMIC: 0.95,
    SourceType.OFFICIAL: 0.9,
    SourceType.NEWS: 0.8,
    SourceType.LISTING: 0.75,
    SourceType.COMPANY: 0.7,
    SourceType.ARCHIVE: 0.6,
    SourceType.AGGREGATOR: 0.55,
    SourceType.SOCIAL: 0.4,
    SourceType.UNKNOWN: 0.5,
}


def classify_source_type(url: str, domain: Optional[str] = None) -> SourceType:
    host = (domain or "").lower()
    if not host:
        from app.dedup.urls import url_domain
        host = url_domain(url)

    if _GOV_RE.search(host):
        return SourceType.GOVERNMENT
    if _ACADEMIC_RE.search(host):
        return SourceType.ACADEMIC
    if host in _ARCHIVE_HOSTS:
        return SourceType.ARCHIVE
    if host in _SOCIAL_HOSTS:
        return SourceType.SOCIAL
    if any(hint in host for hint in _AGGREGATOR_HINTS):
        return SourceType.AGGREGATOR
    if any(hint in host for hint in _LISTING_HINTS):
        return SourceType.LISTING
    if any(hint in host for hint in _COMPANY_HINTS):
        return SourceType.COMPANY
    if any(hint in host for hint in _NEWS_HINTS):
        return SourceType.NEWS
    return SourceType.UNKNOWN


def score_source_quality(
    source_type: SourceType, accessible: bool, has_title: bool, https: bool, is_primary: bool = False,
) -> float:
    """`is_primary` reflects "the caller gave us this URL directly" (a
    listing/article the user explicitly pointed at) vs. "we found this via
    search" — a lightweight proxy for the requested priority order (original
    source > official page > authoritative source > secondary > generic)
    without hard-coding domain-specific source lists."""
    score = _TYPE_WEIGHTS.get(source_type, 0.5)
    if not accessible:
        score *= 0.2
    if has_title:
        score += 0.05
    if https:
        score += 0.05
    if is_primary:
        score += 0.1
    return round(min(score, 1.0), 4)
