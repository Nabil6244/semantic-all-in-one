"""Script-to-transcript matching — no embedding model or extra dependency: the
project has none installed (see requirements.txt), and V2's spec explicitly
says not to bring in "huge AI infrastructure" for this. Combines word-overlap
(order-independent, catches paraphrase/synonym-free rewording) with a fuzzy
sequence ratio (catches near-identical phrasing) — simple, dependency-free,
good enough to beat "always pick timestamp 0"."""

from __future__ import annotations

import difflib
import re
from typing import List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import TranscriptSegment

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "and", "is", "was", "were", "are",
    "for", "with", "that", "this", "it", "as", "by", "at", "from", "be", "has",
    "have", "had", "its", "we", "you", "they", "he", "she", "his", "her", "our",
    "i", "not", "but", "or", "so", "if", "will", "would", "can", "could", "just",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _score(query_tokens: set, query_text: str, candidate_tokens: set, candidate_text: str) -> float:
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
    fuzzy = difflib.SequenceMatcher(None, query_text.lower(), candidate_text.lower()).ratio()
    return 0.7 * overlap + 0.3 * fuzzy


def text_relevance_score(a: str, b: str) -> float:
    """Public wrapper around the same lexical-overlap + fuzzy scoring used for
    transcript matching — reused by ranking.py for title/prompt relevance so
    candidate ranking and transcript matching share one scoring approach
    instead of two."""
    return _score(_tokens(a), a, _tokens(b), b)


def best_transcript_match(
    segments: Sequence["TranscriptSegment"],
    query_text: str,
    window: int = 1,
    min_score: float = 0.12,
) -> Optional[Tuple["TranscriptSegment", float]]:
    """Slide a `window`-sized group of consecutive transcript lines (context
    like the iPhone example in the spec spans several short lines) across the
    transcript, scoring each group's combined text against query_text. Returns
    (first segment of the best-scoring group, score), or None if nothing clears
    min_score — callers must treat None as "no match", not silently use segment 0."""
    query_tokens = _tokens(query_text)
    if not query_tokens or not segments:
        return None

    best_segment = None
    best_score = min_score
    for i in range(len(segments)):
        group = segments[i:i + window + 1]
        combined = " ".join(s.text for s in group)
        score = _score(query_tokens, query_text, _tokens(combined), combined)
        if score > best_score:
            best_score = score
            best_segment = group[0]

    if best_segment is None:
        return None
    return best_segment, best_score
