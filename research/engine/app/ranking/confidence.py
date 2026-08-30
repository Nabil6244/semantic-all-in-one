"""Research-level confidence: a bounded heuristic with an explanation, not a
precise fake probability.

Combines four cheap, explainable signals:
- how much of the extracted fact set came from structured data (JSON-LD)
  vs. text-pattern guesses
- average quality of the accessible sources
- cross-source agreement (fewer/no conflicts is better)
- extraction coverage (more distinct fact keys found)
"""
from __future__ import annotations

from typing import List

from app.models.fact import Fact, FactConflict
from app.models.research import ResearchConfidence
from app.models.source import Source

_STRUCTURED_CONFIDENCE_THRESHOLD = 0.8
_MAX_CONFIDENCE = 0.97  # never claim near-certainty from heuristics alone


def compute_confidence(
    facts: List[Fact], sources: List[Source], conflicts: List[FactConflict]
) -> ResearchConfidence:
    reasons: List[str] = []

    if facts:
        structured = sum(1 for f in facts if f.confidence >= _STRUCTURED_CONFIDENCE_THRESHOLD)
        structured_ratio = structured / len(facts)
        if structured:
            reasons.append(f"{structured}/{len(facts)} facts from structured data (JSON-LD)")
    else:
        structured_ratio = 0.0
        reasons.append("no facts extracted")

    accessible_sources = [s for s in sources if s.accessible]
    if accessible_sources:
        source_authority = sum(s.quality_score for s in accessible_sources) / len(accessible_sources)
        reasons.append(f"{len(accessible_sources)} accessible source(s), avg quality {source_authority:.2f}")
    else:
        source_authority = 0.0
        reasons.append("no accessible sources")

    distinct_keys_with_multiple_sources = len({
        f.key for f in facts
        if len({other.source_id for other in facts if other.key == f.key}) > 1
    })
    if not facts:
        agreement = 0.0  # nothing to agree on — don't credit "no conflicts"
    elif conflicts:
        agreement = max(0.0, 1 - (len(conflicts) / max(1, distinct_keys_with_multiple_sources or len(conflicts))))
        reasons.append(f"{len(conflicts)} conflicting fact(s) across sources")
    else:
        agreement = 1.0
        if len({s.source_id for s in sources}) > 1:
            reasons.append("no cross-source conflicts detected")

    distinct_keys = len({f.key for f in facts})
    extraction_quality = min(1.0, distinct_keys / 8)
    if distinct_keys:
        reasons.append(f"{distinct_keys} distinct fact field(s) extracted")

    score = (
        0.30 * structured_ratio
        + 0.30 * source_authority
        + 0.25 * agreement
        + 0.15 * extraction_quality
    )
    score = round(min(score, _MAX_CONFIDENCE), 2)

    return ResearchConfidence(confidence=score, reasons=reasons)
