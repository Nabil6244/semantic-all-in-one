"""Focused search-query generation.

We deliberately generate a small, bounded set of queries from the research
target rather than crawling broadly — see ARCHITECTURE notes in README.
"""
from __future__ import annotations

from typing import List, Optional

from app.models.research import ExtractedEntities

_DOMAIN_TEMPLATES = {
    "real_estate": ["{topic} listing", "{topic} price acreage", "{topic} photos"],
    "travel": ["{topic} guide", "{topic} things to do", "{topic} travel tips"],
    "cars": ["{topic} specs review", "{topic} price", "{topic} photos"],
    "products": ["{topic} review", "{topic} specs", "{topic} price"],
    "history": ["{topic} history", "{topic} timeline"],
    "science": ["{topic} research study", "{topic} explained"],
    "companies": ["{topic} company overview", "{topic} news"],
    "news": ["{topic} latest news"],
    "biographies": ["{topic} biography", "{topic} life history"],
}

_DEFAULT_TEMPLATES = ["{topic}", "{topic} overview", "{topic} facts"]


def generate_queries(
    topic: Optional[str],
    entities: Optional[ExtractedEntities] = None,
    domain: str = "unknown",
    max_queries: int = 5,
) -> List[str]:
    if not topic:
        # fall back to the most prominent extracted subject/entity
        if entities and entities.subjects:
            topic = entities.subjects[0]
        elif entities and entities.entities:
            topic = entities.entities[0]
        else:
            return []

    templates = _DOMAIN_TEMPLATES.get(domain, _DEFAULT_TEMPLATES)
    queries: List[str] = []
    seen = set()
    for template in templates:
        query = template.format(topic=topic).strip()
        key = query.lower()
        if key not in seen:
            seen.add(key)
            queries.append(query)
        if len(queries) >= max_queries:
            break

    if entities:
        for location in entities.locations[:1]:
            if location.lower() in topic.lower():
                continue
            query = f"{topic} {location}".strip()
            if query.lower() not in seen and len(queries) < max_queries:
                seen.add(query.lower())
                queries.append(query)

    return queries[:max_queries]
