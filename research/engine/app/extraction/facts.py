"""Fact extraction: normalized, source-attributed claims pulled from a page.

V1 uses rule-based extraction only (regex + schema.org field mapping) — no
LLM is required. `FactExtractor` is the seam for a future LLM-backed
extractor; it must return the same `Fact` shape so downstream ranking/dedup/
conflict logic doesn't need to change.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Protocol

from app.extraction.webpage import PageExtraction
from app.models.fact import Fact, FactConflict

# --- generic, domain-agnostic numeric/unit patterns -------------------------
# Each entry: key, regex, unit, value_group, transform
_TEXT_PATTERNS: List[tuple] = [
    ("acreage", re.compile(r"(\d+(?:\.\d+)?)\s*[-\s]?acres?\b", re.I), "acres"),
    ("price", re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)\b"), "usd"),
    ("bedrooms", re.compile(r"(\d+)\s*[-\s]?(?:bed(?:room)?s?)\b", re.I), "count"),
    ("bathrooms", re.compile(r"(\d+(?:\.\d+)?)\s*[-\s]?(?:bath(?:room)?s?)\b", re.I), "count"),
    # Matches "2,400 sq ft", "2400 sqft", and prose phrasing like
    # "3,200-square-foot home" (hyphenated, singular "foot").
    ("square_feet", re.compile(r"([\d,]+)\s*[-\s]?(?:sq\.?\s?ft\.?|square[-\s]+f(?:ee|oo)t|sqft)\b", re.I), "sqft"),
    ("year", re.compile(r"\b(19\d{2}|20\d{2})\b"), "year"),
]


def _to_number(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").strip()
    try:
        val = float(cleaned)
        return int(val) if val.is_integer() else val
    except ValueError:
        return None


def extract_facts_from_text(text: str, source_id: str, confidence: float = 0.55) -> List[Fact]:
    """Regex-based extraction over visible page text. Conservative confidence
    since text-pattern matches are heuristic, not structured data."""
    facts: List[Fact] = []
    seen = set()
    for key, pattern, unit in _TEXT_PATTERNS:
        for match in pattern.finditer(text):
            raw_value = match.group(1)
            normalized = _to_number(raw_value)
            dedup = (key, raw_value)
            if dedup in seen:
                continue
            seen.add(dedup)
            context_start = max(0, match.start() - 40)
            context_end = min(len(text), match.end() + 40)
            facts.append(
                Fact(
                    key=key,
                    value=f"{raw_value} {unit}".strip() if unit != "usd" else f"${raw_value}",
                    normalized_value=normalized,
                    unit=unit,
                    original_text=match.group(0).strip(),
                    source_id=source_id,
                    confidence=confidence,
                    context=text[context_start:context_end].strip(),
                )
            )
    return facts


# --- schema.org / JSON-LD field mapping --------------------------------------
_JSONLD_SIMPLE_FIELDS = {
    "name": "title",
    "description": "description",
    "datePublished": "date_published",
    "sku": "sku",
    "brand": "brand",
}


def _flatten(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return value.get("name") or value.get("value") or value.get("@id")
    if isinstance(value, list) and value:
        return _flatten(value[0])
    return None


def extract_facts_from_json_ld(entity: Dict[str, Any], source_id: str, confidence: float = 0.9) -> List[Fact]:
    """High-confidence facts from structured data — schema.org fields are
    author-declared, not inferred, so confidence is higher than text regex."""
    facts: List[Fact] = []

    for field, key in _JSONLD_SIMPLE_FIELDS.items():
        val = _flatten(entity.get(field))
        if val:
            facts.append(Fact(key=key, value=str(val), source_id=source_id, confidence=confidence))

    # price via offers.price / offers.priceCurrency
    offers = entity.get("offers")
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict):
        price = offers.get("price")
        currency = offers.get("priceCurrency", "")
        if price is not None:
            norm = _to_number(str(price))
            facts.append(
                Fact(
                    key="price", value=f"{price} {currency}".strip(),
                    normalized_value=norm, unit=currency or None,
                    source_id=source_id, confidence=confidence,
                )
            )

    # address (PostalAddress or plain string)
    address = entity.get("address")
    if isinstance(address, dict):
        parts = [
            address.get("streetAddress"), address.get("addressLocality"),
            address.get("addressRegion"), address.get("postalCode"),
            address.get("addressCountry"),
        ]
        addr_str = ", ".join(p for p in parts if p)
        if addr_str:
            facts.append(Fact(key="address", value=addr_str, source_id=source_id, confidence=confidence))
    elif isinstance(address, str) and address:
        facts.append(Fact(key="address", value=address, source_id=source_id, confidence=confidence))

    # floorSize (QuantitativeValue)
    floor_size = entity.get("floorSize")
    if isinstance(floor_size, dict):
        val = floor_size.get("value")
        unit = floor_size.get("unitText") or floor_size.get("unitCode")
        if val is not None:
            facts.append(
                Fact(
                    key="square_feet", value=f"{val} {unit or ''}".strip(),
                    normalized_value=_to_number(str(val)), unit=unit,
                    source_id=source_id, confidence=confidence,
                )
            )

    # numberOfRooms / numberOfBedrooms / numberOfBathroomsTotal
    for schema_field, fact_key in (
        ("numberOfBedrooms", "bedrooms"),
        ("numberOfBathroomsTotal", "bathrooms"),
        ("numberOfRooms", "rooms"),
    ):
        val = entity.get(schema_field)
        if val is not None:
            facts.append(
                Fact(
                    key=fact_key, value=str(val), normalized_value=_to_number(str(val)),
                    unit="count", source_id=source_id, confidence=confidence,
                )
            )

    return facts


class FactExtractor(Protocol):
    """Interface so an LLM-backed extractor can be swapped in later without
    touching planner/researcher/ranking code."""

    def extract(self, page: PageExtraction, source_id: str) -> List[Fact]: ...


class RuleBasedFactExtractor:
    """Default V1 extractor: schema.org fields (high confidence) + regex over
    visible text (lower confidence). No LLM involved."""

    def extract(self, page: PageExtraction, source_id: str) -> List[Fact]:
        if not page.accessible:
            return []
        facts: List[Fact] = []
        from app.extraction.structured_data import find_entities_by_type

        # Prefer specific listing/product-like entities, else fall back to all blocks.
        entities = find_entities_by_type(
            page.json_ld, "Product", "RealEstateListing", "House", "SingleFamilyResidence",
            "Article", "NewsArticle", "Place", "Event", "Organization",
        ) or page.json_ld

        for entity in entities:
            facts.extend(extract_facts_from_json_ld(entity, source_id))

        if page.visible_text:
            facts.extend(extract_facts_from_text(page.visible_text, source_id))

        return facts


# Keys that are inherently free-text (every source phrases its own title/
# description differently — that's not a factual disagreement) or naturally
# multi-valued (a property can have many "feature" facts from many sources
# without any of them contradicting each other). Flagging these as
# "conflicts" would just be noise, not a real cross-source disagreement.
_NON_CONFLICTING_KEYS = {"title", "description", "feature"}


def detect_conflicts(facts: List[Fact]) -> List[FactConflict]:
    """Group facts by key; when facts from different sources disagree on the
    normalized value for the same key, record a conflict. All facts are kept
    regardless — conflicts are annotations, not filters."""
    by_key: Dict[str, List[Fact]] = {}
    for fact in facts:
        by_key.setdefault(fact.key, []).append(fact)

    conflicts: List[FactConflict] = []
    for key, key_facts in by_key.items():
        if key in _NON_CONFLICTING_KEYS or len(key_facts) < 2:
            continue
        distinct_values = {
            (f.normalized_value if f.normalized_value is not None else f.value) for f in key_facts
        }
        # different sources reporting the exact same source_id+value isn't a conflict
        distinct_sources = {f.source_id for f in key_facts}
        if len(distinct_values) > 1 and len(distinct_sources) > 1:
            conflicts.append(
                FactConflict(
                    key=key,
                    facts=key_facts,
                    note=f"{len(distinct_values)} differing values for '{key}' across {len(distinct_sources)} sources",
                )
            )
    return conflicts
