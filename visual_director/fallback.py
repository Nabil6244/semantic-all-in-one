"""Deterministic Script Analyzer backup — same VisualPlan contract as Gemini.

Used only when Gemini is unavailable (quota, high demand, timeout, network,
malformed responses after retries). Not a quality replacement for Gemini.
"""

from __future__ import annotations

import re
from typing import List, Sequence

from .schema import VisualPlan, VisualScene, provider_max_duration

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)

_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "over",
    "under", "about", "when", "what", "which", "their", "there", "have",
    "been", "were", "will", "would", "could", "should", "than", "then",
    "they", "them", "were", "was", "are", "is", "a", "an", "of", "to",
    "in", "on", "at", "by", "as", "or", "but", "not", "be", "it", "its",
})

_HIGH_IMPORTANCE = frozenset({
    "reveal", "secret", "truth", "critical", "crucial", "finally", "never",
    "million", "billion", "percent", "war", "death", "discovery", "evidence",
    "because", "however", "danger", "collapse", "breakthrough",
})

_LOCATION = frozenset({
    "city", "country", "ocean", "river", "factory", "harbor", "port",
    "street", "border", "mountain", "desert", "island", "capital", "valley",
})

_ENTITY_HINTS = frozenset({
    "company", "president", "worker", "scientist", "engineer", "ship",
    "container", "machine", "engine", "government", "army", "market",
})

# Target spoken words per beat (~4–8s at documentary pace). Soft target only.
_TARGET_WORDS = 55
_MAX_WORDS = 95
_MIN_WORDS = 18


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if t]


def _content_words(text: str) -> List[str]:
    return [t for t in _tokens(text) if t not in _STOP and len(t) > 2]


def _split_sentences(script: str) -> List[str]:
    text = re.sub(r"\r\n?", "\n", (script or "").strip())
    if not text:
        return []
    parts = _SENTENCE_SPLIT.split(text)
    out = []
    for p in parts:
        s = re.sub(r"\s+", " ", p).strip()
        if s:
            out.append(s)
    return out


def _group_sentences(sentences: Sequence[str]) -> List[str]:
    """Group sentences into narration beats — O(n), no fixed max beat count."""
    if not sentences:
        return []
    groups: List[str] = []
    buf: List[str] = []
    words = 0
    for sent in sentences:
        sw = len(sent.split())
        if buf and words + sw > _MAX_WORDS:
            groups.append(" ".join(buf))
            buf = [sent]
            words = sw
            continue
        buf.append(sent)
        words += sw
        if words >= _TARGET_WORDS and (sent.endswith((".", "!", "?")) or words >= _MAX_WORDS):
            groups.append(" ".join(buf))
            buf = []
            words = 0
    if buf:
        # Merge tiny trailing fragment into previous when possible
        if groups and words < _MIN_WORDS:
            groups[-1] = groups[-1] + " " + " ".join(buf)
        else:
            groups.append(" ".join(buf))
    # Ensure at least 2 beats for VisualPlan MIN_SCENES
    if len(groups) == 1:
        words_list = groups[0].split()
        if len(words_list) >= 8:
            mid = len(words_list) // 2
            groups = [" ".join(words_list[:mid]), " ".join(words_list[mid:])]
        else:
            groups = [groups[0], groups[0]]
    return groups


def _importance(text: str) -> str:
    toks = set(_tokens(text))
    if toks & _HIGH_IMPORTANCE or any(ch.isdigit() for ch in text):
        return "high"
    if len(text.split()) < 20:
        return "low"
    return "medium"


def _keywords(text: str, *, limit: int = 6) -> List[str]:
    words = _content_words(text)
    # Prefer earlier distinctive words; keep order, unique
    seen = set()
    out = []
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out or ["documentary", "subject"]


def _visual_goal(text: str, keywords: Sequence[str]) -> str:
    toks = set(_tokens(text))
    if toks & _LOCATION:
        loc = next(k for k in _LOCATION if k in toks)
        return f"establish {loc} context"
    if toks & _ENTITY_HINTS:
        ent = next(k for k in _ENTITY_HINTS if k in toks)
        return f"show {ent} evidence"
    if keywords:
        return f"illustrate {' '.join(keywords[:3])}"
    return "support narration"


def _duration_for(text: str) -> float:
    # ~2.4 words/sec documentary pacing estimate — only for backup; VO alignment overrides later
    wc = max(1, len(text.split()))
    dur = wc / 2.4
    cap = provider_max_duration("stock_video")
    return round(min(cap, max(1.5, dur)), 2)


def _topic_from_script(script: str) -> str:
    first = (script or "").strip().split("\n", 1)[0].strip()
    words = first.split()
    if not words:
        return "Documentary"
    title = " ".join(words[:10])
    if len(words) > 10:
        title += "…"
    return title[:80]


def deterministic_visual_plan(script: str, *, reason: str = "") -> VisualPlan:
    """Build a valid VisualPlan without any LLM call."""
    sentences = _split_sentences(script)
    if not sentences:
        # Still produce two minimal scenes so callers get a valid plan shape
        sentences = ["The story begins.", "The story continues."]
    narrations = _group_sentences(sentences)
    scenes: List[VisualScene] = []
    for i, narr in enumerate(narrations, start=1):
        kws = _keywords(narr)
        goal = _visual_goal(narr, kws)
        query = " ".join(kws[:4])
        desc = f"Specific documentary visual of {query}".strip()
        scenes.append(
            VisualScene(
                scene_id=i,
                narration=narr,
                visual_goal=goal,
                visual_description=desc,
                asset_type="stock_video",
                provider_preference="stock_video",
                search_queries=[query, f"{query} documentary"],
                timestamp_needed=False,
                timestamp_hint="",
                duration=_duration_for(narr),
                importance=_importance(narr),
                fallbacks=["stock_image"],
                visual_treatment="",
                transition="cut",
                minimum_quality="1080p",
            )
        )

    warnings = [
        "backup_analyzer: deterministic fallback (Gemini unavailable)",
    ]
    if reason:
        warnings.append(f"gemini_failure: {reason[:200]}")
    plan = VisualPlan(topic=_topic_from_script(script), scenes=scenes, warnings=warnings)
    plan.analyzer_source = "backup"  # type: ignore[attr-defined]
    return plan
