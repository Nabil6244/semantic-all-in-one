"""Complementary asset scoring for multi-asset editorial coverage.

Used by the shot planner when a beat needs more visual coverage than the
primary asset can honestly provide. Prefers a *different useful visual role*
over near-duplicate B-roll.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

from .media_analysis import analyze_media_editability
from .schema import EditorialScene

# Preferred role progression when narration supports multi-shot storytelling.
ROLE_PROGRESSION = (
    "context",
    "detail",
    "action",
    "consequence",
    "evidence",
    "atmosphere",
)

_PURPOSE_BY_ROLE = {
    "context": "context",
    "detail": "detail",
    "action": "action",
    "consequence": "consequence",
    "evidence": "evidence",
    "claim_evidence": "evidence",
    "process": "action",
    "geography": "context",
    "scale": "consequence",
    "atmosphere": "atmosphere",
    "object": "detail",
    "statistic": "evidence",
    "explanation": "detail",
    "reveal": "detail",
}

_STOP = frozenset(
    "a an the and or of to for in on at with from by is are was were be this that "
    "it its their they we you our as into over under than then so not no".split()
)


@dataclasses.dataclass
class AssetCandidate:
    """One visual source that may cover (part of) a beat."""

    asset_id: str
    path: Path
    is_primary: bool = False
    asset_class: str = ""
    query_hint: str = ""
    visual_role: str = "context"
    editorial_purpose: str = "context"
    score: float = 0.0
    metadata: dict = dataclasses.field(default_factory=dict)

    @property
    def label(self) -> str:
        return str(self.path)


def _tokens(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def infer_complement_role(
    *,
    primary_role: str,
    asset_class: str,
    query_hint: str,
    index: int = 0,
) -> str:
    """Pick a useful *different* role for a complementary shot."""
    blob = f"{asset_class} {query_hint}".lower()
    if any(w in blob for w in ("close", "detail", "macro", "machine", "component")):
        return "detail"
    if any(w in blob for w in ("truck", "transport", "ship", "deliver", "mov")):
        return "action"
    if any(w in blob for w in ("grid", "demand", "result", "power line", "skyline")):
        return "consequence"
    if any(w in blob for w in ("document", "chart", "data", "map", "archive")):
        return "evidence"
    if "image" in (asset_class or "") and primary_role in ("process", "action"):
        return "detail"
    # Walk progression away from primary
    try:
        idx = ROLE_PROGRESSION.index(primary_role if primary_role in ROLE_PROGRESSION else "context")
    except ValueError:
        idx = 0
    return ROLE_PROGRESSION[min(len(ROLE_PROGRESSION) - 1, idx + 1 + index)]


def editorial_purpose_for_role(role: str) -> str:
    return _PURPOSE_BY_ROLE.get(role, "context")


def score_complement_candidate(
    candidate: AssetCandidate,
    *,
    scene: EditorialScene,
    primary: AssetCandidate,
    beat_role: str,
    used_asset_ids: Sequence[str],
    recent_asset_ids: Sequence[str],
    preferred_asset_ids: Optional[Sequence[str]] = None,
) -> float:
    """Higher is better. Semantic mismatch / near-duplicates score low."""
    if candidate.is_primary:
        return 0.35  # primary is baseline, not a "complement pick"

    narr = f"{scene.narration_excerpt} {scene.visual_goal} {scene.visual_description}"
    narr_tok = _tokens(narr)
    cand_tok = _tokens(f"{candidate.query_hint} {candidate.visual_role} {candidate.asset_class}")
    prim_tok = _tokens(f"{primary.query_hint} {primary.visual_role} {scene.visual_variety_key}")

    score = 0.0

    # Semantic overlap with narration (required for acceptance)
    if narr_tok:
        overlap_n = len(narr_tok & cand_tok)
        overlap = overlap_n / max(1, min(6, len(narr_tok)))
        score += min(0.40, overlap * 0.55)
        if overlap_n == 0:
            # Unrelated B-roll must not clear the quality bar
            score -= 0.45
    else:
        score += 0.10

    # Role compatibility: different from primary, but on the progression
    if candidate.visual_role and candidate.visual_role != (primary.visual_role or beat_role):
        score += 0.18
    else:
        score -= 0.12  # near-identical role → likely duplicate B-roll

    if candidate.visual_role in ROLE_PROGRESSION:
        try:
            p_idx = ROLE_PROGRESSION.index(primary.visual_role if primary.visual_role in ROLE_PROGRESSION else "context")
            c_idx = ROLE_PROGRESSION.index(candidate.visual_role)
            if c_idx == p_idx + 1:
                score += 0.12  # natural next beat
            elif c_idx > p_idx:
                score += 0.06
        except ValueError:
            pass

    # Evidence value for evidence/statistic beats
    if beat_role in ("claim_evidence", "statistic", "evidence") and candidate.visual_role in (
        "evidence",
        "detail",
        "claim_evidence",
    ):
        score += 0.10

    # Editability / media quality proxy
    known = None
    meta = candidate.metadata or {}
    try:
        known = float(meta.get("actual_duration") or meta.get("duration") or 0) or None
    except (TypeError, ValueError):
        known = None
    edit = analyze_media_editability(
        candidate.path,
        known_duration=known,
        asset_type=candidate.asset_class,
    )
    score += 0.12 * float(edit.editability_score)

    # Source reliability: prefer stock/archive/youtube evidence over unknown
    ac = (candidate.asset_class or "").lower()
    if any(k in ac for k in ("archive", "youtube", "nasa", "document")):
        score += 0.06
    if "stock" in ac:
        score += 0.04

    # Repetition penalties
    aid = candidate.asset_id
    if aid and used_asset_ids.count(aid) >= 1:
        score -= 0.18 * used_asset_ids.count(aid)
    if aid and aid in recent_asset_ids[-4:]:
        score -= 0.15

    # Near-duplicate of primary query → reject-ish
    if prim_tok and cand_tok:
        sim = len(prim_tok & cand_tok) / max(1, len(prim_tok | cand_tok))
        if sim >= 0.75 and candidate.visual_role == (primary.visual_role or beat_role):
            score -= 0.35
        elif sim >= 0.85:
            score -= 0.20

    # AI director preferred assets
    prefs = {str(p) for p in (preferred_asset_ids or []) if str(p).strip()}
    if prefs and candidate.asset_id in prefs:
        score += 0.22

    # Path must exist
    if not candidate.path.is_file():
        return -1.0

    return round(score, 4)


def select_complements(
    candidates: Sequence[AssetCandidate],
    *,
    scene: EditorialScene,
    primary: AssetCandidate,
    beat_role: str,
    used_asset_ids: Sequence[str],
    recent_asset_ids: Sequence[str],
    max_complements: int = 3,
    min_score: float = 0.28,
    preferred_asset_ids: Optional[Sequence[str]] = None,
) -> List[AssetCandidate]:
    """Return ranked complements that clear the quality bar (excludes primary)."""
    scored: List[AssetCandidate] = []
    for cand in candidates:
        if cand.is_primary:
            continue
        if cand.asset_id and cand.asset_id == primary.asset_id:
            continue
        s = score_complement_candidate(
            cand,
            scene=scene,
            primary=primary,
            beat_role=beat_role,
            used_asset_ids=used_asset_ids,
            recent_asset_ids=recent_asset_ids,
            preferred_asset_ids=preferred_asset_ids,
        )
        cand.score = s
        if s >= min_score:
            scored.append(cand)
    scored.sort(key=lambda c: (-c.score, c.asset_id))
    # Diversity: avoid two complements with same role when alternatives exist
    picked: List[AssetCandidate] = []
    seen_roles: Set[str] = set()
    for cand in scored:
        if len(picked) >= max_complements:
            break
        role = cand.visual_role or "context"
        if role in seen_roles and len(scored) > len(picked) + 1:
            # Prefer role variety unless this score is clearly best leftover
            continue
        picked.append(cand)
        seen_roles.add(role)
    # If diversity filter was too aggressive, fill from remaining
    if len(picked) < min(max_complements, len(scored)):
        for cand in scored:
            if cand in picked:
                continue
            picked.append(cand)
            if len(picked) >= max_complements:
                break
    return picked


def needs_complementary_coverage(
    *,
    required: float,
    primary_usable: float,
    coverage_strategy: str = "",
    media_kind: str = "video",
) -> bool:
    """True when another real asset would help more than punch-in alone."""
    if required <= 0:
        return False
    strategy = (coverage_strategy or "").lower()
    if strategy == "dual":
        return True
    if media_kind == "image" and required >= 5.5:
        return True
    if primary_usable <= 0:
        return media_kind != "image"  # images handled via Ken Burns unless long
    ratio = primary_usable / required
    if ratio >= 0.88:
        return False
    if ratio < 0.72:
        return True
    # Mild shortfall: only if dual/extend already planned
    return strategy in ("extend", "hold_tail", "dual") and (required - primary_usable) > 1.0
