"""Does a plan have a CREATIVE problem worth an AI critic's attention? Objective defects are the validator's and local_fix's job; this only
looks for what code can suspect but not judge: monotony, repetition, an unbalanced mix, a chapter that opens like the last. A plan with no
suspicion goes straight on; the critic's request is spent where an editor would look."""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

from .plan import Beat, HybridPlan
from .validate import Finding

CREATIVE_CODES = {"churn", "repeated_footage", "map_redundant", "map_static", "overlay_dense", "no_footage", "no_map"}
RUN_BEATS, RUN_SECONDS = 4, 150.0       # this many beats of one mode in a row, lasting this long, is monotony
SAME_PLACE_RUN = 4                      # this many map beats in a row on the same camera place


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (text or "").lower()).strip()


def unit_flags(beats: Sequence[Beat], findings: Sequence[Finding]) -> List[str]:
    """Reasons to have this run of beats (a chapter, or a whole short plan) criticised; empty = no suspicion."""
    ids = {b.id for b in beats}
    reasons = [f"validator noticed {f.code} in {f.beat}" for f in findings if f.beat in ids and f.severity == "warning" and f.code in CREATIVE_CODES]
    run: List[Beat] = []
    for b in list(beats) + [None]:
        if b is not None and run and b.mode == run[-1].mode:
            run.append(b)
            continue
        if len(run) >= RUN_BEATS and run[-1].end - run[0].start >= RUN_SECONDS:
            reasons.append(f"{len(run)} {run[0].mode} beats in a row ({run[0].id}-{run[-1].id})")
        run = [b] if b is not None else []
    same: List[Beat] = []
    for b in list(beats) + [None]:
        if b is not None and b.mode != "footage" and same and b.cam_place and b.cam_place == same[-1].cam_place and not b.layers:
            same.append(b)
            continue
        if len(same) >= SAME_PLACE_RUN:
            reasons.append(f"{len(same)} map beats in a row on {same[0].cam_place} with nothing added ({same[0].id}-{same[-1].id})")
        same = [b] if (b is not None and b.mode != "footage") else []
    return reasons


def global_flags(plan: HybridPlan) -> List[str]:
    """Documentary-wide suspicion: only meaningful for a plan with several chapters or a long one."""
    reasons: List[str] = []
    if plan.duration < 600:
        return reasons
    total = max(plan.duration, 1.0)
    footage = sum(b.end - b.start for b in plan.beats if b.mode == "footage") / total
    if footage < 0.08:
        reasons.append(f"footage is only {footage:.0%} of the documentary")
    if footage > 0.7:
        reasons.append(f"footage is {footage:.0%} of the documentary")
    seen: Dict[str, str] = {}
    dup = []
    for b in plan.beats:
        for q in [c.asset for c in b.clips] + [card.asset for card in b.cards]:
            k = _norm(q)
            if k in seen and seen[k] != b.id:
                dup.append(q)
            seen.setdefault(k, b.id)
    if len(dup) >= 3:
        reasons.append(f"{len(dup)} pictures or clips are asked for more than once")
    if len(plan.chapters) > 1:
        openers: List[Tuple[str, str]] = []
        for c in plan.chapters:
            first = next((b for b in plan.beats if b.chapter == c["id"]), None)
            if first:
                openers.append((first.mode, _norm(first.cam_place)))
        if len(openers) >= 4 and len(set(openers)) <= max(1, len(openers) // 3):
            reasons.append("the chapters all open the same way")
    return reasons
