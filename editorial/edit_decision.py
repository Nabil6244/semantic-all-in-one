"""Edit decisions — how a narration beat is covered visually.

Voiceover duration remains authoritative. These structures describe *how* to
fill that window with meaningful coverage (multi-shot, punch-in, retime, etc.)
instead of blindly looping or freezing.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Literal, Optional

CoverageStrategy = Literal[
    "SINGLE_SHOT",
    "DUAL_ASSET",
    "MULTI_SHOT",
    "EXTEND",
    "RETIME",
    "PUNCH_IN",
    "REFRAME",
    "IMAGE_MOTION",
    "SAFE_LOOP",
    "BRIDGE",
    "MONTAGE",
    "HOLD_TAIL",
]

ShotSize = Literal[
    "extreme_wide",
    "wide",
    "medium",
    "close",
    "extreme_close",
    "detail",
]

VisualRole = Literal[
    "claim_evidence",
    "statistic",
    "process",
    "geography",
    "person",
    "historical",
    "comparison",
    "scale",
    "reveal",
    "cause_effect",
    "atmosphere",
    "object",
    "metaphor",
    "explanation",
    "context",
]

ALLOWED_STRATEGIES = frozenset(
    {
        "SINGLE_SHOT",
        "DUAL_ASSET",
        "MULTI_SHOT",
        "EXTEND",
        "RETIME",
        "PUNCH_IN",
        "REFRAME",
        "IMAGE_MOTION",
        "SAFE_LOOP",
        "BRIDGE",
        "MONTAGE",
        "HOLD_TAIL",
    }
)

# Editorial quality ranking — lower is better / less damaging.
# Prefer a real complementary asset over transforming the primary.
# RETIME beats freeze/loop; for small shortfalls the planner prefers RETIME
# over multi-shot via branching (not this rank alone).
STRATEGY_QUALITY_RANK: Dict[str, int] = {
    "SINGLE_SHOT": 1,
    "DUAL_ASSET": 2,
    "MULTI_SHOT": 3,
    "EXTEND": 4,
    "BRIDGE": 5,
    "PUNCH_IN": 6,
    "REFRAME": 6,
    "IMAGE_MOTION": 7,
    "RETIME": 8,
    "MONTAGE": 9,
    "SAFE_LOOP": 10,
    "HOLD_TAIL": 11,
}


@dataclasses.dataclass
class MediaEditability:
    """Editorial potential of a source asset (deterministic analysis)."""

    native_duration: float = 0.0
    usable_duration: float = 0.0
    media_kind: str = "unknown"  # video | image | unknown
    motion_level: float = 0.5  # 0 static … 1 high motion
    loopability: float = 0.0
    crop_potential: float = 0.7
    reframe_potential: float = 0.7
    punch_in_potential: float = 0.75
    slow_motion_potential: float = 0.3
    speed_change_tolerance: float = 0.15  # max |speed-1|
    visual_complexity: float = 0.5
    editability_score: float = 0.5  # 0–1 aggregate
    natural_endpoint: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MediaEditability":
        if not isinstance(data, dict):
            return cls()
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in fields})


@dataclasses.dataclass
class ShotSpec:
    """One editorial shot inside a beat's coverage plan.

    `source_path` / `asset_id` let different shots reference different files
    (primary + complementary B-roll). Empty source_path → use the scene primary.
    """

    shot_id: str
    output_duration: float
    source_start: float = 0.0
    source_end: Optional[float] = None  # None → use until needed
    scale: float = 1.0  # >1 = punch-in
    crop_x: float = 0.5  # normalized focal x (0–1)
    crop_y: float = 0.5
    speed: float = 1.0
    shot_size: ShotSize = "medium"
    camera_style: str = "static"
    transition_in: str = "cut"
    # Real (xfade-blended) transition duration in seconds — 0 means "use
    # the existing per-clip fade-to-color scheme" (transition_in's OLD
    # vocabulary: fade/dissolve/flash/soft). A value > 0 together with
    # transition_in set to one of video_generator.TRANSITION_TYPES
    # (crossfade/dip_black/dip_white/wipe/slide) requests a genuine
    # cross-clip blend via video_generator.build_xfade_filter_complex —
    # see editorial_timeline_edit.py's module docstring for why these two
    # vocabularies are kept separate rather than reusing one field.
    transition_duration: float = 0.0
    # Directional variant for "wipe"/"slide" (left/right/up/down — see
    # video_generator.TRANSITION_DIRECTIONS). Ignored by every other
    # transition_in value. Empty string -> renderer default ("left").
    transition_direction: str = ""
    hold_tail: bool = False
    reason: str = ""
    # Multi-asset coverage (optional — empty means scene primary)
    asset_id: str = ""
    source_path: str = ""
    visual_role: str = ""
    editorial_purpose: str = ""  # context|detail|action|consequence|evidence|…

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ShotSpec":
        fields = {f.name for f in dataclasses.fields(cls)}
        raw = {k: v for k, v in (data or {}).items() if k in fields}
        if "shot_size" in raw and raw["shot_size"] not in (
            "extreme_wide",
            "wide",
            "medium",
            "close",
            "extreme_close",
            "detail",
        ):
            raw["shot_size"] = "medium"
        return cls(**raw)


@dataclasses.dataclass
class EditDecision:
    """How to cover one narration beat with one or more shots."""

    scene_number: str
    required_duration: float
    strategy: CoverageStrategy = "SINGLE_SHOT"
    shots: List[ShotSpec] = dataclasses.field(default_factory=list)
    source_asset: str = ""
    visual_role: VisualRole = "context"
    confidence: float = 0.7
    reason: str = ""
    avoid_blind_loop: bool = True
    attention_state: str = "understanding"
    reveal_phase: str = "none"  # none|setup|build|withhold|reveal|emphasize
    # Real B-roll picture-in-picture overlays for this scene — VIDEO_2
    # timeline events that genuinely OVERLAP a primary (VIDEO_1/IMAGE)
    # shot in time, as opposed to `shots` (always sequential/concatenated).
    # Each entry: {source_path, source_start, speed, overlay_start,
    # overlay_duration, scale, position} — overlay_start/duration are
    # relative to the SCENE's own rendered clip (t=0 at scene start). See
    # editorial_timeline_edit.reconcile_timeline_into_decisions (which
    # populates this from an operator-edited timeline) and
    # video_generator.composite_broll_overlay (which renders it).
    broll: List[dict] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scene_number": self.scene_number,
            "required_duration": round(float(self.required_duration), 4),
            "strategy": self.strategy,
            "shots": [s.to_dict() for s in self.shots],
            "source_asset": self.source_asset,
            "visual_role": self.visual_role,
            "confidence": round(float(self.confidence), 3),
            "reason": self.reason,
            "avoid_blind_loop": self.avoid_blind_loop,
            "attention_state": self.attention_state,
            "reveal_phase": self.reveal_phase,
            "broll": list(self.broll),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EditDecision":
        if not isinstance(data, dict):
            raise TypeError("EditDecision.from_dict expects dict")
        strategy = str(data.get("strategy") or "SINGLE_SHOT").upper()
        if strategy not in ALLOWED_STRATEGIES:
            strategy = "SINGLE_SHOT"
        shots_raw = data.get("shots") or []
        shots = [
            ShotSpec.from_dict(s) for s in shots_raw if isinstance(s, dict)
        ]
        role = str(data.get("visual_role") or "context")
        return cls(
            scene_number=str(data.get("scene_number") or ""),
            required_duration=float(data.get("required_duration") or 0.0),
            strategy=strategy,  # type: ignore[arg-type]
            shots=shots,
            source_asset=str(data.get("source_asset") or ""),
            visual_role=role,  # type: ignore[arg-type]
            confidence=float(data.get("confidence") or 0.7),
            reason=str(data.get("reason") or ""),
            avoid_blind_loop=bool(data.get("avoid_blind_loop", True)),
            attention_state=str(data.get("attention_state") or "understanding"),
            reveal_phase=str(data.get("reveal_phase") or "none"),
            broll=[b for b in (data.get("broll") or []) if isinstance(b, dict)],
        )

    @property
    def shot_count(self) -> int:
        return len(self.shots)

    def total_output_duration(self) -> float:
        return round(sum(max(0.05, float(s.output_duration)) for s in self.shots), 4)


@dataclasses.dataclass
class EditorialEvent:
    """Coordinated audiovisual moment (stat appear, reveal, etc.)."""

    event_id: str
    start: float
    end: float
    kind: str  # statistic|reveal|location|emphasis|impact|chapter|graphic
    scene_number: str = ""
    visual_action: str = ""
    text_action: str = ""
    sfx_action: str = ""
    music_action: str = ""
    confidence: float = 0.6
    # Optional content payload for graphics / text overlays (never FFmpeg).
    payload: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EditorialEvent":
        fields = {f.name for f in dataclasses.fields(cls)}
        raw = {k: v for k, v in (data or {}).items() if k in fields}
        if not isinstance(raw.get("payload"), dict):
            raw["payload"] = {}
        return cls(**raw)
