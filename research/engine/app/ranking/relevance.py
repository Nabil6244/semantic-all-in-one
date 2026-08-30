"""Domain-agnostic relevance scoring (bag-of-words cosine similarity).

Deliberately simple and dependency-free — no embeddings/ML models. This is
scoring for the *research engine's* candidate selection only; it is not, and
must not become, a replacement for Semantic YT Studio's Smart Visual
Selection algorithm.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, List, Optional

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or", "is",
    "are", "was", "were", "be", "with", "by", "from", "this", "that", "it",
    "as", "its", "into", "your", "you", "we", "our",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _vector(tokens: List[str]) -> Counter:
    return Counter(tokens)


def cosine_similarity(vec_a: Counter, vec_b: Counter) -> float:
    if not vec_a or not vec_b:
        return 0.0
    common = set(vec_a) & set(vec_b)
    dot = sum(vec_a[t] * vec_b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def text_similarity(text_a: Optional[str], text_b: Optional[str]) -> float:
    return cosine_similarity(_vector(tokenize(text_a)), _vector(tokenize(text_b)))


def multi_text_similarity(query: Optional[str], texts: Iterable[Optional[str]]) -> float:
    """Similarity of `query` against the concatenation of several text fields
    (e.g. title + description + alt text), so any one strong match counts."""
    combined = " ".join(t for t in texts if t)
    return text_similarity(query, combined)
