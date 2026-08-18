"""Turn a raw stock keyword string into one or more search queries: the cleaned
original first, then progressively broader fallbacks, so a zero-result search
doesn't just give up on the scene."""

from __future__ import annotations

import re
from typing import List

_STOPWORDS = {"a", "an", "the", "of", "in", "on", "at", "with", "and", "or"}


def clean_query(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def build_queries(raw: str) -> List[str]:
    base = clean_query(raw)
    if not base:
        return []
    queries = [base]
    words = base.split()

    stripped = [w for w in words if w.lower() not in _STOPWORDS]
    if stripped and stripped != words:
        candidate = " ".join(stripped)
        if candidate.lower() != base.lower():
            queries.append(candidate)

    if len(words) > 1:
        candidate = " ".join(words[:-1])
        if candidate.lower() not in (q.lower() for q in queries):
            queries.append(candidate)

    if len(words) > 2 and words[0].lower() not in (q.lower() for q in queries):
        queries.append(words[0])

    return queries
