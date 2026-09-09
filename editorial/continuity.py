"""Continuity + attention helpers for editorial decisions.

Tracks recent visual motifs, shot sizes, and attention state so adjacent
shots feel intentional rather than randomly assembled.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .edit_decision import ShotSize
from .schema import EditorialScene, Purpose

# Purpose → default visual role (semantic explanation, not decoration).
PURPOSE_VISUAL_ROLE: Dict[str, str] = {
    "hook": "atmosphere",
    "context": "context",
    "evidence": "claim_evidence",
    "explanation": "explanation",
    "emotion": "atmosphere",
    "reveal": "reveal",
    "comparison": "comparison",
    "scale": "scale",
    "process": "process",
    "timeline": "process",
    "location": "geography",
    "character": "person",
    "transition": "atmosphere",
    "reflection": "atmosphere",
    "outro": "atmosphere",
}

ATTENTION_CYCLE = (
    "curiosity",
    "understanding",
    "anticipation",
    "surprise",
    "emotional_weight",
    "relief",
    "new_curiosity",
)

_SHOT_PROGRESSION: Dict[str, List[ShotSize]] = {
    "scale": ["wide", "medium", "close"],
    "reveal": ["wide", "medium", "close"],
    "process": ["medium", "close", "detail"],
    "claim_evidence": ["medium", "close"],
    "geography": ["wide", "medium"],
    "person": ["wide", "medium", "close"],
    "explanation": ["medium", "close"],
    "comparison": ["medium", "medium"],
    "atmosphere": ["wide", "medium"],
    "context": ["wide", "medium"],
    "object": ["medium", "close", "detail"],
    "metaphor": ["wide", "medium"],
    "historical": ["medium", "close"],
    "cause_effect": ["medium", "close"],
    "statistic": ["medium", "close"],
}


def visual_role_for_scene(scene: EditorialScene) -> str:
    purpose: Purpose = scene.purpose
    role = PURPOSE_VISUAL_ROLE.get(purpose, "context")
    blob = f"{scene.narration_excerpt} {scene.visual_goal} {scene.visual_description}".lower()
    if any(w in blob for w in ("percent", "%", "million", "billion", "data", "statistic")):
        return "statistic"
    if any(w in blob for w in ("map", "border", "country", "region", "city of")):
        return "geography"
    if any(w in blob for w in ("factory", "manufactur", "assembl", "process", "built")):
        return "process"
    if any(w in blob for w in ("document", "report", "archive", "photograph", "footage")):
        return "claim_evidence"
    return role


def attention_state_for_scene(scene: EditorialScene, index: int, total: int) -> str:
    if scene.purpose == "hook" or scene.start < 8.0:
        return "curiosity"
    if scene.purpose == "reveal":
        return "surprise"
    if scene.purpose in ("emotion", "reflection"):
        return "emotional_weight"
    if scene.purpose == "outro":
        return "relief"
    if scene.purpose in ("evidence", "explanation", "process"):
        return "understanding"
    if scene.attention_score >= 0.78:
        return "anticipation"
    # Mild cycle so the film does not stay in one emotional state
    return ATTENTION_CYCLE[index % len(ATTENTION_CYCLE)]


def reveal_phase_for_scene(scene: EditorialScene) -> str:
    if scene.purpose != "reveal" and scene.attention_score < 0.8:
        return "none"
    if scene.purpose == "reveal":
        return "reveal"
    if scene.purpose == "hook" and scene.attention_score >= 0.75:
        return "setup"
    return "none"


def shot_size_sequence(
    visual_role: str,
    n_shots: int,
    *,
    prev_size: Optional[str] = None,
) -> List[ShotSize]:
    """Prefer wide→medium→close progression; avoid repeating prev framing."""
    base = list(_SHOT_PROGRESSION.get(visual_role, ["medium", "close"]))
    out: List[ShotSize] = []
    for i in range(max(1, n_shots)):
        size = base[i % len(base)]
        if prev_size and i == 0 and size == prev_size and len(base) > 1:
            size = base[1]
        out.append(size)  # type: ignore[arg-type]
        prev_size = size
    return out


def scale_for_shot_size(shot_size: str) -> float:
    return {
        "extreme_wide": 1.0,
        "wide": 1.0,
        "medium": 1.12,
        "close": 1.28,
        "extreme_close": 1.45,
        "detail": 1.55,
    }.get(shot_size, 1.0)


def camera_for_shot(
    shot_size: str,
    *,
    purpose: str,
    index: int,
    prev_camera: Optional[str] = None,
) -> str:
    if shot_size in ("close", "extreme_close", "detail"):
        candidate = "push_in"
    elif shot_size in ("extreme_wide", "wide") and purpose == "scale":
        candidate = "pull_out"
    elif purpose in ("emotion", "reflection"):
        candidate = "subtle_drift"
    elif purpose == "outro":
        candidate = "pull_out"
    else:
        pool = ("subtle_drift", "push_in", "static", "hold")
        candidate = pool[index % len(pool)]
    if prev_camera == candidate:
        alts = [c for c in ("push_in", "pull_out", "subtle_drift", "static", "hold") if c != prev_camera]
        candidate = alts[index % len(alts)] if alts else candidate
    return candidate


class ContinuityTracker:
    """Stateful tracker across scenes for variety + motif callbacks."""

    def __init__(self) -> None:
        self.prev_shot_size: Optional[str] = None
        self.prev_camera: Optional[str] = None
        self.prev_strategy: Optional[str] = None
        self.prev_variety_key: Optional[str] = None
        self.motif_counts: Dict[str, int] = {}
        self.recent_assets: List[str] = []

    def note_asset(self, asset_key: str) -> int:
        key = (asset_key or "").strip()
        if not key:
            return 0
        self.motif_counts[key] = self.motif_counts.get(key, 0) + 1
        self.recent_assets.append(key)
        if len(self.recent_assets) > 24:
            self.recent_assets = self.recent_assets[-24:]
        return self.motif_counts[key]

    def update_from_shots(
        self,
        shot_sizes: Sequence[str],
        camera: str,
        strategy: str,
        variety_key: str,
    ) -> None:
        if shot_sizes:
            self.prev_shot_size = shot_sizes[-1]
        self.prev_camera = camera
        self.prev_strategy = strategy
        self.prev_variety_key = variety_key
