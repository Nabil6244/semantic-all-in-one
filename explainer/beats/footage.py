"""A footage beat for the application's own sources (Phase 9, opt-in): one clip reference "<source>:<query>" with a query taken from the narration, and the beat's key phrase as a Hybrid
`typed_caption` template over it. The Explainer never fetches anything: the application's "Get the scenes" step does, with the keys and network it already has. Every query word is spoken
inside the beat (checked by explainer.beats.relevance.check_plan with allow_sources), so a clip is always about what is being said."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .relevance import Word, beat_tokens, find_phrase

MAX_QUERY_WORDS = 3
CAPTION_LEAD_S = 0.0
CAPTION_MIN_READ_S = 1.2        # a caption must start at least this long before its beat ends


def pick_query(tokens: Sequence[str], strong: frozenset, stop: frozenset, weak: frozenset = frozenset()) -> Optional[Tuple[str, int]]:
    """(query, index of the key word) from the beat's tokens: the first STRONG filmable word (a place, vehicle, crowd or machine; a title such as "queen" never carries a clip), with the content
    word right before it (an adjective: "spanish ships") and one right after it when that is filmable too ("ships treasure"). Function words never enter a query."""
    concrete = strong | weak
    for i, t in enumerate(tokens):
        if t in strong:
            q = [t]
            if i > 0 and tokens[i - 1] not in stop and not tokens[i - 1].isdigit() and tokens[i - 1] not in concrete:
                q.insert(0, tokens[i - 1])
            if i + 1 < len(tokens) and tokens[i + 1] in concrete and len(q) < MAX_QUERY_WORDS:
                q.append(tokens[i + 1])
            return " ".join(q), i
    return None


def make_footage_beat(beat_id: str, start: float, end: float, words: Sequence[Word], *, source: str, query: str, caption: Optional[Dict[str, Any]], still_sources: Sequence[str],
                      purpose: str = "") -> Dict[str, Any]:
    """The Hybrid plan beat. `caption` = {"text", "t"} (the quote and the time its first word is spoken) or None."""
    clip: Dict[str, Any] = {"asset": f"{source}:{query}", "reason": f"shows {query}: the narration says \"{(caption or {}).get('text', query)}\""}
    if source in still_sources:
        clip["kenburns"] = True
    beat: Dict[str, Any] = {"id": beat_id, "mode": "footage", "start": float(start), "end": float(end), "purpose": purpose or f"explainer footage: {query}",
                            "footage": {"clips": [clip], "footage_intent": query}}
    if caption:
        beat["layers"] = [{"id": f"{beat_id}_cap1", "type": "template", "kind": "typed_caption", "t": round(float(caption["t"]) + CAPTION_LEAD_S, 3), "text": caption["text"], "until": "beat_end"}]
    return beat
