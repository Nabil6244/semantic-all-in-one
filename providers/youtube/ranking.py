"""Candidate ranking. YouTube's own search order is already relevance-sorted
for the query text, so that order is the primary signal — this re-weights it
with title/prompt relevance (reusing the same lexical scorer as transcript
matching, not a separate model), plus a few cheap, honest tie-breakers:
caption availability (needed for transcript matching to do anything at all),
landscape orientation (matches this project's output), a penalty for
long-form content (1+ hour ambience/background loops make timestamp
selection meaningless — see base.py's compute_fallback_timestamp), and a
penalty for titles that read as a playlist/livestream/music video/ambience
loop rather than a normal standalone clip. Discards absurdly short/long
results outright."""

from __future__ import annotations

import re
from typing import List, TYPE_CHECKING

from .matching import text_relevance_score

if TYPE_CHECKING:
    from .base import VideoCandidate

_MIN_DURATION = 5.0  # shorter than this can't safely hold a 3-4s clip with lead-in
_MAX_DURATION = 3 * 60 * 60  # 3h — discard obvious mismatches (full streams, etc.)
_LONG_FORM_START = 20 * 60  # 20 minutes — beyond this, penalize proportionally
_LONG_FORM_MAX_PENALTY = 4.0

# Title substrings that reliably signal "not a normal standalone video" —
# ambience/background loops, livestreams, playlists, pure-music uploads.
# Heuristic, not exhaustive; false negatives just mean no penalty applied,
# never a wrongly-excluded good candidate (this only re-weights, never drops).
_UNDESIRABLE_TITLE_HINTS = (
    "hour loop", "hours loop", "no loop", "1 hour", "2 hour", "3 hour",
    "10 hour", "12 hour", "24/7", "live now", "livestream", "live stream",
    "🔴 live", "full album", "official music video", "lyric video", "lyrics",
    "asmr", "white noise", "background music", "sleep music", "study music",
    "relaxing music", "playlist", "compilation",
)
_HOUR_HINT_RE = re.compile(r"\b\d{1,2}\s*hours?\b")


def _duration_penalty(duration) -> float:
    if not duration or duration <= _LONG_FORM_START:
        return 0.0
    excess_hours = (duration - _LONG_FORM_START) / 3600.0
    return min(_LONG_FORM_MAX_PENALTY, excess_hours * 2.0)


def _title_penalty(title: str) -> float:
    t = title.lower()
    if any(hint in t for hint in _UNDESIRABLE_TITLE_HINTS) or _HOUR_HINT_RE.search(t):
        return 2.0
    return 0.0


# A query that asks for footage (the CSV prompts end in "footage" / "b-roll") wants pictures of the thing, not people talking about it:
# studio talk, map commentary, explainers, reactions, Shorts and video games are pushed down, titles that name filmed footage go up.
_FOOTAGE_QUERY_RE = re.compile(r"\b(footage|b-?roll|clip)\b", re.IGNORECASE)
_TALK_TITLE_RE = re.compile(
    r"\b(interview|podcast|analysis|analy[sz]ed|explained|explainer|reaction|reacts?|debate|discussion|panel|press conference|briefing|"
    r"q\s*&\s*a|opinion|commentary|map update|lecture|speech|talk show|#shorts?|shorts|tiktok|gameplay|arma ?3|war thunder|simulation|"
    r"animated|animation)\b", re.IGNORECASE)
_FILMED_TITLE_RE = re.compile(
    r"\b(footage|drone|combat|frontline|front line|aftermath|bodycam|helmet ?cam|filmed|video shows|caught on camera|b-?roll|"
    r"aerial|timelapse|4k)\b", re.IGNORECASE)


def _footage_intent(c: "VideoCandidate", query: str) -> float:
    if not query or not _FOOTAGE_QUERY_RE.search(query):
        return 0.0
    t = c.title or ""
    return (1.0 if _FILMED_TITLE_RE.search(t) else 0.0) - (2.5 if _TALK_TITLE_RE.search(t) else 0.0)


def _score(c: "VideoCandidate", query: str) -> float:
    score = 0.0
    if query:
        score += text_relevance_score(query, c.title) * 3.0
        score += _footage_intent(c, query)
    if c.has_captions:
        score += 1.0
    if c.width and c.height and c.width >= c.height:
        score += 0.3
    score -= _duration_penalty(c.duration)
    score -= _title_penalty(c.title)
    return score


def rank_candidates(candidates: List["VideoCandidate"], query: str = "") -> List["VideoCandidate"]:
    usable = [
        c for c in candidates
        if c.duration is None or (_MIN_DURATION <= c.duration <= _MAX_DURATION)
    ]
    if not usable:
        usable = list(candidates)
    # Stable sort: ties keep YouTube's original relevance order (index in the
    # input list acts as the implicit tiebreak since Python's sort is stable).
    return sorted(usable, key=lambda c: _score(c, query), reverse=True)
