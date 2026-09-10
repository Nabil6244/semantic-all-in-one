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
    recent_cameras: Optional[Sequence[str]] = None,
    prefer_static: bool = False,
) -> str:
    """Pick a camera treatment; avoid repeating recent motion patterns."""
    if prefer_static:
        candidate = "static" if prev_camera != "static" else "subtle_drift"
    elif shot_size in ("close", "extreme_close", "detail"):
        candidate = "push_in"
    elif shot_size in ("extreme_wide", "wide") and purpose == "scale":
        candidate = "pull_out"
    elif purpose in ("emotion", "reflection"):
        candidate = "subtle_drift"
    elif purpose == "outro":
        candidate = "pull_out"
    elif purpose in ("evidence",):
        # Documents / archival stills: prefer static or extremely subtle motion.
        pool = ("static", "hold", "subtle_drift", "static")
        candidate = pool[index % len(pool)]
    else:
        pool = ("static", "subtle_drift", "push_in", "hold", "pull_out")
        candidate = pool[index % len(pool)]

    recent = [c for c in (recent_cameras or []) if c]
    if prev_camera and not recent:
        recent = [prev_camera]

    # Avoid identical treatment back-to-back, and avoid three identical motions
    # in a short window (zoom/zoom/zoom).
    if candidate == prev_camera or (
        recent and recent[-3:].count(candidate) >= 2 and candidate not in ("static", "hold")
    ):
        alts = [
            c
            for c in ("static", "hold", "subtle_drift", "push_in", "pull_out")
            if c != candidate and c != prev_camera
        ]
        # Prefer static/hold over another aggressive zoom when breaking a streak.
        if recent and recent[-2:].count("push_in") >= 2:
            alts = [c for c in ("static", "hold", "subtle_drift", "pull_out") if c != prev_camera] or alts
        candidate = alts[index % len(alts)] if alts else candidate
    return candidate


def source_identity_key(asset_id: str = "", source_path: str = "") -> str:
    """Normalize to the underlying asset — crop/reframe variants share identity."""
    aid = (asset_id or "").strip()
    if aid:
        # Strip shot suffixes like _s0 / crop tags; keep 001 / 001_b base ids.
        base = aid.split("#")[0].split("|")[0].strip()
        return base
    path = (source_path or "").strip()
    if not path:
        return ""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    # 001_crop / 001_zoom still map to 001 when tagged that way
    for suffix in ("_crop", "_zoom", "_reframe", "_punch", "_kb"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


class ContinuityTracker:
    """Stateful tracker across scenes for variety + motif callbacks."""

    def __init__(self) -> None:
        self.prev_shot_size: Optional[str] = None
        self.prev_camera: Optional[str] = None
        self.prev_strategy: Optional[str] = None
        self.prev_variety_key: Optional[str] = None
        self.motif_counts: Dict[str, int] = {}
        self.recent_assets: List[str] = []
        self.recent_cameras: List[str] = []
        self.recent_source_keys: List[str] = []

    def note_asset(self, asset_key: str) -> int:
        key = source_identity_key(asset_id=asset_key) or (asset_key or "").strip()
        if not key:
            return 0
        self.motif_counts[key] = self.motif_counts.get(key, 0) + 1
        self.recent_assets.append(key)
        self.recent_source_keys.append(key)
        if len(self.recent_assets) > 24:
            self.recent_assets = self.recent_assets[-24:]
        if len(self.recent_source_keys) > 24:
            self.recent_source_keys = self.recent_source_keys[-24:]
        return self.motif_counts[key]

    def source_reuse_count(self, asset_id: str = "", source_path: str = "") -> int:
        key = source_identity_key(asset_id=asset_id, source_path=source_path)
        if not key:
            return 0
        return int(self.motif_counts.get(key, 0))

    def update_from_shots(
        self,
        shot_sizes: Sequence[str],
        camera: str,
        strategy: str,
        variety_key: str,
        cameras: Optional[Sequence[str]] = None,
    ) -> None:
        if shot_sizes:
            self.prev_shot_size = shot_sizes[-1]
        self.prev_camera = camera
        self.prev_strategy = strategy
        self.prev_variety_key = variety_key
        for cam in cameras or ([camera] if camera else []):
            if not cam:
                continue
            self.recent_cameras.append(cam)
        if len(self.recent_cameras) > 16:
            self.recent_cameras = self.recent_cameras[-16:]
