"""Expand cinematic YouTube search prompts into shorter, searchable variants.

Visual Director / Gemini often emits AI-image-style paragraphs as
``search_queries``. yt-dlp ``ytsearch`` returns 0 hits for those; Stock already
has progressive broadening in ``providers/stock/query.py`` — this is the
YouTube equivalent.
"""

from __future__ import annotations

import re
from typing import List

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "from",
    "to", "for", "by", "as", "into", "over", "under",
}

# Phrases that help an AI image prompt but kill YouTube search recall.
_FLUFF = re.compile(
    r"\b("
    r"real|authentic|period[- ]accurate|cinematic|highly detailed|"
    r"black and white|black[- ]and[- ]white|sepia(?:[- ]toned)?|"
    r"archival footage|stock footage|documentary footage|found footage|"
    r"footage|clip|video|shot of|scene of|showing|featuring"
    r")\b[,:]?",
    re.I,
)

_PUNCT = re.compile(r"[^\w\s\-]+", re.U)
_LOOSE_OR = re.compile(r"\s+or\s+", re.I)


def clean_youtube_query(raw: str) -> str:
    text = _PUNCT.sub(" ", raw or "")
    text = _LOOSE_OR.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def expand_youtube_query(raw: str, *, max_variants: int = 6) -> List[str]:
    """Return ordered unique search strings: original first, then broader.

    Long descriptive prompts are shortened so ``ytsearch`` can actually hit
    related archival / documentary uploads.
    """
    base = clean_youtube_query(raw)
    if not base:
        return []

    out: List[str] = []
    seen = set()

    def add(q: str) -> None:
        q = clean_youtube_query(q)
        # Drop leading filler ("from the mid-1940s…").
        parts = q.split()
        while parts and parts[0].lower() in _STOPWORDS:
            parts.pop(0)
        q = " ".join(parts)
        key = q.lower()
        if not q or key in seen:
            return
        content = [w for w in q.split() if w.lower() not in _STOPWORDS]
        if len(content) < 2:
            return
        seen.add(key)
        out.append(q)

    add(base)

    stripped = _FLUFF.sub(" ", base)
    add(stripped)

    words = [w for w in clean_youtube_query(stripped).split() if w.lower() not in _STOPWORDS]
    if words:
        add(" ".join(words))

    for n in (6, 4, 3):
        if len(words) > n:
            add(" ".join(words[:n]))

    if len(words) >= 2:
        add(" ".join(words[:2]))

    return out[:max_variants]
