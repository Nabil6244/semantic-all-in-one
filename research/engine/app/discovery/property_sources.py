"""Bounded, property-centric query generation.

Given a `PropertyIdentity`, generate a small set of targeted queries aimed
at finding *other pages about this exact property* — not a broad topic
search. Used to feed a `SearchProvider` when discovering secondary sources
(brokerage/agent/MLS-syndication/aggregator copies of the same listing).
"""
from __future__ import annotations

from typing import List, Optional

from app.models.property import PropertyIdentity

_DEFAULT_MAX_QUERIES = 10


def generate_property_queries(
    identity: PropertyIdentity,
    agent_name: Optional[str] = None,
    brokerage_name: Optional[str] = None,
    max_queries: int = _DEFAULT_MAX_QUERIES,
) -> List[str]:
    queries: List[str] = []
    seen = set()

    def add(query: Optional[str]) -> None:
        if not query:
            return
        query = query.strip()
        key = query.lower()
        if query and key not in seen and len(queries) < max_queries:
            seen.add(key)
            queries.append(query)

    address = identity.canonical_address or identity.normalized_address
    if address:
        add(address)
        add(f"{address} property")
        add(f"{address} photos")
        add(f"{address} video")
        add(f"{address} virtual tour")
        add(f"{address} listing")

    for listing_id in identity.listing_ids:
        add(listing_id)
    for mls_id in identity.mls_ids:
        add(f"MLS {mls_id}")

    if identity.property_name:
        add(identity.property_name)

    if agent_name and address:
        add(f"{agent_name} {address}")
    if brokerage_name and address:
        add(f"{brokerage_name} {address}")

    return queries[:max_queries]
