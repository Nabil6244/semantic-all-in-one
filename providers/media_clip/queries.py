"""Ordered, de-duplicated search queries from a SceneRow."""

from __future__ import annotations

from typing import List

from providers.base import SceneRow
from providers.stock.query import build_queries, clean_query

# Words Visual Director adds that hurt archive/nasa/commons keyword search.
_DOC_NOISE = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or",
    "animation", "animated", "cinematic", "footage", "video", "clip",
    "showing", "scene", "visual", "documentary", "historical",
    "real", "actual", "official", "broll", "b-roll",
    "graphic", "graphics", "illustration", "render", "rendered",
    "slow", "motion", "wide", "shot", "close", "up", "aerial",
}


def unique_media_queries(scene: SceneRow) -> List[str]:
    raw: List[str] = []
    extras = [str(q).strip() for q in (getattr(scene, "search_queries", None) or [])]
    prompt = (scene.prompt or "").strip()
    if extras:
        raw.extend(extras)
    elif "||" in prompt:
        raw.extend(p.strip() for p in prompt.split("||"))
    elif prompt:
        raw.append(prompt)
    if prompt.startswith("identifier:"):
        ident = prompt.split(":", 1)[1].strip()
        return [ident] if ident else []
    seen = set()
    out: List[str] = []
    for query in raw:
        query = " ".join(query.split())
        key = query.lower()
        if not query or key in seen:
            continue
        seen.add(key)
        out.append(query)
    return out


def _shorten_query_variants(query: str) -> List[str]:
    """Progressively broader variants — same idea as stock build_queries."""
    base = clean_query(query)
    if not base:
        return []
    out: List[str] = []
    seen = set()

    def add(raw: str) -> None:
        q = clean_query(raw)
        if not q:
            return
        key = q.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(q)

    for variant in build_queries(base):
        add(variant)

    trimmed_words = [w for w in base.split() if w.lower() not in _DOC_NOISE]
    if trimmed_words:
        trimmed = " ".join(trimmed_words)
        if trimmed.lower() != base.lower():
            for variant in build_queries(trimmed):
                add(variant)
        words = list(trimmed_words)
        while len(words) > 2:
            words = words[:-1]
            add(" ".join(words))

    return out


def expanded_media_queries(scene: SceneRow) -> List[str]:
    """Unique queries plus shorter fallbacks when the director prompt is too specific."""
    seen = set()
    out: List[str] = []
    for base in unique_media_queries(scene):
        for query in _shorten_query_variants(base):
            key = query.lower()
            if key not in seen:
                seen.add(key)
                out.append(query)
    return out
