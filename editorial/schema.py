"""Editorial Plan schema — post-alignment film bible for render + smart editing hints."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Literal, Optional

EDITORIAL_PLAN_VERSION = 2
HOOK_WINDOW_S = 30.0

CameraStyle = Literal["push_in", "pull_out", "static", "hold", "subtle_drift"]
Purpose = Literal[
    "hook",
    "context",
    "evidence",
    "explanation",
    "emotion",
    "reveal",
    "comparison",
    "scale",
    "process",
    "timeline",
    "location",
    "character",
    "transition",
    "reflection",
    "outro",
]
PacingBias = Literal["slow", "normal", "fast"]
MusicRole = Literal["hold", "lift", "drop", "none"]

ALLOWED_CAMERA_STYLES = frozenset(
    {"push_in", "pull_out", "static", "hold", "subtle_drift"}
)
ALLOWED_PURPOSES = frozenset(
    {
        "hook",
        "context",
        "evidence",
        "explanation",
        "emotion",
        "reveal",
        "comparison",
        "scale",
        "process",
        "timeline",
        "location",
        "character",
        "transition",
        "reflection",
        "outro",
    }
)
ALLOWED_TRANSITIONS = frozenset({"cut", "dissolve", "fade", "soft", "flash", "match_cut"})


def _norm_camera(raw: str) -> CameraStyle:
    key = (raw or "static").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "push": "push_in",
        "slow_push": "push_in",
        "zoom_in": "push_in",
        "pull": "pull_out",
        "zoom_out": "pull_out",
        "drift": "subtle_drift",
        "pan": "subtle_drift",
        "still": "static",
        "freeze": "hold",
    }
    key = aliases.get(key, key)
    return key if key in ALLOWED_CAMERA_STYLES else "static"


def _norm_purpose(raw: str) -> Purpose:
    key = (raw or "context").strip().lower()
    return key if key in ALLOWED_PURPOSES else "context"


def _norm_transition(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    key = str(raw).strip().lower().replace(" ", "_")
    if key == "match_cut":
        return "dissolve"
    if key in ALLOWED_TRANSITIONS:
        return key
    return None


@dataclasses.dataclass
class EditorialScene:
    scene_number: str
    start: float
    end: float
    duration: float
    narration_excerpt: str = ""
    purpose: Purpose = "context"
    attention_score: float = 0.5
    importance: str = "medium"
    asset_type_intent: str = ""
    camera_style: CameraStyle = "static"
    visual_variety_key: str = ""
    visual_goal: str = ""
    visual_description: str = ""
    visual_treatment: str = ""
    ambience_profile: str = "room"
    ambience_intensity: float = 1.0
    allow_silence: bool = False
    sfx_moments: List[dict] = dataclasses.field(default_factory=list)
    transition_in: Optional[str] = None
    pacing_bias: PacingBias = "normal"
    music_role: MusicRole = "hold"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EditorialScene":
        moments = data.get("sfx_moments") or []
        if not isinstance(moments, list):
            moments = []
        return cls(
            scene_number=str(data.get("scene_number") or ""),
            start=float(data.get("start") or 0.0),
            end=float(data.get("end") or 0.0),
            duration=float(data.get("duration") or 0.0),
            narration_excerpt=str(data.get("narration_excerpt") or ""),
            purpose=_norm_purpose(str(data.get("purpose") or "context")),
            attention_score=float(data.get("attention_score") or 0.5),
            importance=str(data.get("importance") or "medium"),
            asset_type_intent=str(data.get("asset_type_intent") or ""),
            camera_style=_norm_camera(str(data.get("camera_style") or "static")),
            visual_variety_key=str(data.get("visual_variety_key") or ""),
            visual_goal=str(data.get("visual_goal") or ""),
            visual_description=str(data.get("visual_description") or ""),
            visual_treatment=str(data.get("visual_treatment") or ""),
            ambience_profile=str(data.get("ambience_profile") or "room"),
            ambience_intensity=float(data.get("ambience_intensity") or 1.0),
            allow_silence=bool(data.get("allow_silence")),
            sfx_moments=[m for m in moments if isinstance(m, dict)],
            transition_in=_norm_transition(data.get("transition_in")),
            pacing_bias=str(data.get("pacing_bias") or "normal"),  # type: ignore[arg-type]
            music_role=str(data.get("music_role") or "hold"),  # type: ignore[arg-type]
        )


@dataclasses.dataclass
class EditorialPlan:
    version: int = EDITORIAL_PLAN_VERSION
    audio_key: str = ""
    settings_key: str = ""
    audio_end: float = 0.0
    hook_window_s: float = HOOK_WINDOW_S
    scenes: List[EditorialScene] = dataclasses.field(default_factory=list)
    film_sections: List[dict] = dataclasses.field(default_factory=list)
    music: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {
            "version": self.version,
            "audio_key": self.audio_key,
            "settings_key": self.settings_key,
            "audio_end": self.audio_end,
            "hook_window_s": self.hook_window_s,
            "scenes": [s.to_dict() for s in self.scenes],
            "film": {"hook_window_s": self.hook_window_s, "sections": list(self.film_sections)},
            "music": dict(self.music or {}),
        }
        style = getattr(self, "style", None)
        if isinstance(style, dict) and style:
            out["style"] = dict(style)
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "EditorialPlan":
        scenes_raw = data.get("scenes") or []
        scenes = [
            EditorialScene.from_dict(s) for s in scenes_raw if isinstance(s, dict)
        ]
        film = data.get("film") if isinstance(data.get("film"), dict) else {}
        sections = list(film.get("sections") or data.get("film_sections") or [])
        music = data.get("music") if isinstance(data.get("music"), dict) else {}
        plan = cls(
            version=int(data.get("version") or EDITORIAL_PLAN_VERSION),
            audio_key=str(data.get("audio_key") or ""),
            settings_key=str(data.get("settings_key") or ""),
            audio_end=float(data.get("audio_end") or 0.0),
            hook_window_s=float(
                data.get("hook_window_s") or film.get("hook_window_s") or HOOK_WINDOW_S
            ),
            scenes=scenes,
            film_sections=[s for s in sections if isinstance(s, dict)],
            music=dict(music),
        )
        style = data.get("style")
        if isinstance(style, dict) and style:
            setattr(plan, "style", dict(style))
        return plan

    def scene_by_number(self) -> Dict[str, EditorialScene]:
        return {str(s.scene_number): s for s in self.scenes}

    def transition_style_map(self) -> Dict[str, str]:
        """Map scene_number → transition style for render_video (into-scene)."""
        out: Dict[str, str] = {}
        for scene in self.scenes:
            if scene.transition_in and scene.transition_in != "cut":
                out[str(scene.scene_number)] = scene.transition_in
        return out

    def camera_style_map(self) -> Dict[str, str]:
        return {str(s.scene_number): s.camera_style for s in self.scenes}

    def ambience_profile_map(self) -> Dict[str, str]:
        return {str(s.scene_number): s.ambience_profile for s in self.scenes}

    def ambience_intensity_map(self) -> Dict[str, float]:
        return {str(s.scene_number): float(s.ambience_intensity) for s in self.scenes}

    def display_timeline(self) -> List[tuple[float, float]]:
        return [(s.start, s.end) for s in self.scenes]
