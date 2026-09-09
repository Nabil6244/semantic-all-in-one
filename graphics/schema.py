"""Graphics + motion design schemas — timeline-native, not scene-bound.

Graphics are first-class TimelineEvent payloads on TEXT / GRAPHICS tracks.
They never replace EditorialTimeline; they enrich event.metadata + source.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Literal, Optional

# Orchestrator-level decision (WHAT / WHY)
GraphicDecision = Literal[
    "NO_GRAPHIC",
    "TEXT",
    "STATISTIC",
    "MAP",
    "PROCESS",
    "CHART",
    "CALLOUT",
    "TIMELINE",
    "LOWER_THIRD",
    "LABEL",
    "LOCATION",
    "QUOTE",
    "CHAPTER",
    "DOCUMENT",
    "COMPARISON",
    "PROGRESS",
]

# Graphic roles (editorial purpose)
GRAPHIC_ROLES = frozenset(
    {
        "STATISTIC",
        "DATA",
        "MAP",
        "LOCATION",
        "TIMELINE",
        "PROCESS",
        "COMPARISON",
        "RANKING",
        "COUNTDOWN",
        "PROGRESS",
        "CALLOUT",
        "ARROW",
        "HIGHLIGHT",
        "LABEL",
        "QUOTE",
        "DOCUMENT",
        "CHART",
        "DIAGRAM",
        "UI_ELEMENT",
        "CHAPTER",
        "REVEAL",
        "LOWER_THIRD",
        "TITLE",
        "SUBTITLE",
        "NAME",
        "EMPHASIS",
        "CAPTION",
        "DATA_LABEL",
    }
)

# Text overlay roles
TEXT_ROLES = frozenset(
    {
        "TITLE",
        "SUBTITLE",
        "LABEL",
        "LOCATION",
        "NAME",
        "STATISTIC",
        "CALLOUT",
        "QUOTE",
        "EMPHASIS",
        "CHAPTER",
        "LOWER_THIRD",
        "CAPTION",
        "DATA_LABEL",
        "DATE",
        "EVIDENCE",
        "ANNOTATION",
        "COMPARISON",
        "TECHNICAL_LABEL",
        "PERSON",
    }
)

ImportanceLevel = Literal["low", "medium", "high", "critical"]
EmphasisLevel = Literal["subtle", "normal", "strong", "dramatic"]
SemanticPurpose = Literal[
    "identify",
    "explain",
    "emphasize",
    "reveal",
    "compare",
    "establish",
    "quantify",
    "orient",
    "warn",
    "transition",
]

IMPORTANCE_LEVELS = frozenset({"low", "medium", "high", "critical"})
EMPHASIS_LEVELS = frozenset({"subtle", "normal", "strong", "dramatic"})
SEMANTIC_PURPOSES = frozenset(
    {
        "identify",
        "explain",
        "emphasize",
        "reveal",
        "compare",
        "establish",
        "quantify",
        "orient",
        "warn",
        "transition",
    }
)

BackgroundKind = Literal[
    "NONE",
    "SHADOW",
    "GRADIENT",
    "SCRIM",
    "PANEL",
    "PILL",
    "LOWER_THIRD",
    "FULL_WIDTH_OVERLAY",
]

AnimationKind = Literal[
    "FADE",
    "SLIDE",
    "SCALE",
    "TYPE_ON",
    "MASK_REVEAL",
    "WIPE",
    "BLUR_IN",
    "BLUR_OUT",
    "POSITION_REVEAL",
    "CHARACTER_REVEAL",
    "WORD_EMPHASIS",
    "COUNT_UP",
    "NONE",
]

# Map AnimationKind → existing FFmpeg overlay motion strings
ANIMATION_TO_OVERLAY: Dict[str, str] = {
    "FADE": "fade",
    "SLIDE": "slide_fade",
    "SCALE": "fade",  # unused; keep mapping for old specs → restrained fade
    "TYPE_ON": "fade",
    "MASK_REVEAL": "reveal",
    "WIPE": "reveal",
    "BLUR_IN": "fade",
    "BLUR_OUT": "fade",
    "POSITION_REVEAL": "slide_fade",
    "CHARACTER_REVEAL": "fade",
    "WORD_EMPHASIS": "fade",
    "COUNT_UP": "reveal",
    "NONE": "fade",
}

EasingKind = Literal["linear", "ease_in", "ease_out", "ease_in_out"]


@dataclasses.dataclass
class GraphicLifecycle:
    """ENTER → HOLD → EXIT relative to graphic start."""

    enter_s: float = 0.35
    hold_s: float = 2.0
    exit_s: float = 0.30

    @property
    def total(self) -> float:
        return max(0.05, self.enter_s + self.hold_s + self.exit_s)

    def to_dict(self) -> dict:
        return {
            "enter_s": round(self.enter_s, 3),
            "hold_s": round(self.hold_s, 3),
            "exit_s": round(self.exit_s, 3),
            "total": round(self.total, 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphicLifecycle":
        if not isinstance(data, dict):
            return cls()
        return cls(
            enter_s=float(data.get("enter_s") or 0.35),
            hold_s=float(data.get("hold_s") or 2.0),
            exit_s=float(data.get("exit_s") or 0.30),
        )


@dataclasses.dataclass
class Keyframe:
    """Simple property keyframe (Phase 8 lite)."""

    t: float  # seconds relative to graphic start
    value: float
    easing: EasingKind = "ease_out"

    def to_dict(self) -> dict:
        return {"t": round(self.t, 4), "value": self.value, "easing": self.easing}


@dataclasses.dataclass
class TextOverlaySpec:
    """Professional text overlay — independent of scene attachment."""

    role: str = "LABEL"
    text: str = ""
    secondary_text: str = ""
    tertiary_text: str = ""
    start: float = 0.0
    end: float = 0.0
    position_x: float = 0.5
    position_y: float = 0.76
    scale: float = 1.0
    opacity: float = 1.0
    rotation: float = 0.0
    font_family: str = ""
    weight: str = "Bold"
    alignment: str = "center"  # left | center | right
    tracking_em: float = 0.0
    line_spacing: float = 1.15
    background: BackgroundKind = "SCRIM"
    padding: float = 0.35  # relative to fontsize
    corner_radius: float = 0.0
    shadow: bool = True
    border: bool = False
    animation: AnimationKind = "FADE"
    z_index: int = 60
    placement: str = ""  # typography placement id when known
    style_id: str = ""  # maps into typography styles when possible
    importance: str = "medium"
    emphasis: str = "normal"
    semantic_purpose: str = "identify"
    lifecycle: GraphicLifecycle = dataclasses.field(default_factory=GraphicLifecycle)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["lifecycle"] = self.lifecycle.to_dict()
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "TextOverlaySpec":
        if not isinstance(data, dict):
            return cls()
        fields = {f.name for f in dataclasses.fields(cls)}
        raw = {k: v for k, v in data.items() if k in fields}
        if isinstance(raw.get("lifecycle"), dict):
            raw["lifecycle"] = GraphicLifecycle.from_dict(raw["lifecycle"])
        elif "lifecycle" in raw:
            raw.pop("lifecycle", None)
        role = str(raw.get("role") or "LABEL").upper()
        raw["role"] = role if role in TEXT_ROLES else "LABEL"
        bg = str(raw.get("background") or "SCRIM").upper()
        raw["background"] = bg if bg in (
            "NONE", "SHADOW", "GRADIENT", "SCRIM", "PANEL", "PILL",
            "LOWER_THIRD", "FULL_WIDTH_OVERLAY",
        ) else "SCRIM"
        anim = str(raw.get("animation") or "FADE").upper()
        raw["animation"] = anim if anim in ANIMATION_TO_OVERLAY else "FADE"
        imp = str(raw.get("importance") or "medium").lower()
        raw["importance"] = imp if imp in IMPORTANCE_LEVELS else "medium"
        emp = str(raw.get("emphasis") or "normal").lower()
        raw["emphasis"] = emp if emp in EMPHASIS_LEVELS else "normal"
        purp = str(raw.get("semantic_purpose") or "identify").lower()
        raw["semantic_purpose"] = purp if purp in SEMANTIC_PURPOSES else "identify"
        if not isinstance(raw.get("metadata"), dict):
            raw["metadata"] = {}
        return cls(**raw)


@dataclasses.dataclass
class MapGraphicSpec:
    """Structured map event (Phase 5) — never a generic image."""

    map_source: str = ""
    projection: str = "mercator"
    center_lon: float = 0.0
    center_lat: float = 0.0
    zoom: float = 1.0
    regions: List[str] = dataclasses.field(default_factory=list)
    markers: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    routes: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    labels: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    highlight: List[str] = dataclasses.field(default_factory=list)
    animation: str = "marker_pop"
    duration: float = 3.0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class GraphicSpec:
    """Unified graphic cue for timeline materialization + render."""

    graphic_id: str
    decision: str = "TEXT"  # GraphicDecision
    role: str = "LABEL"
    scene_number: str = ""
    start: float = 0.0
    end: float = 0.0
    track: str = "TEXT"  # TEXT | GRAPHICS
    reason: str = ""
    confidence: float = 0.6
    priority: int = 2  # lower = prefer (matches GRAPHICS PRIORITY)
    importance: str = "medium"
    emphasis: str = "normal"
    semantic_purpose: str = "identify"
    text: Optional[TextOverlaySpec] = None
    map: Optional[MapGraphicSpec] = None
    payload: Dict[str, Any] = dataclasses.field(default_factory=dict)
    lifecycle: GraphicLifecycle = dataclasses.field(default_factory=GraphicLifecycle)
    animation: AnimationKind = "FADE"
    sfx_action: str = ""
    z_index: int = 60
    underneath: str = "hold"  # hold footage | dim | blur (advisory)

    def to_dict(self) -> dict:
        return {
            "graphic_id": self.graphic_id,
            "decision": self.decision,
            "role": self.role,
            "scene_number": self.scene_number,
            "start": round(float(self.start), 4),
            "end": round(float(self.end), 4),
            "track": self.track,
            "reason": self.reason,
            "confidence": round(float(self.confidence), 3),
            "priority": int(self.priority),
            "importance": self.importance,
            "emphasis": self.emphasis,
            "semantic_purpose": self.semantic_purpose,
            "text": self.text.to_dict() if self.text else None,
            "map": self.map.to_dict() if self.map else None,
            "payload": dict(self.payload or {}),
            "lifecycle": self.lifecycle.to_dict(),
            "animation": self.animation,
            "sfx_action": self.sfx_action,
            "z_index": int(self.z_index),
            "underneath": self.underneath,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphicSpec":
        if not isinstance(data, dict):
            return cls(graphic_id="")
        text = data.get("text")
        map_g = data.get("map")
        imp = str(data.get("importance") or "medium").lower()
        emp = str(data.get("emphasis") or "normal").lower()
        purp = str(data.get("semantic_purpose") or "identify").lower()
        return cls(
            graphic_id=str(data.get("graphic_id") or ""),
            decision=str(data.get("decision") or "TEXT"),
            role=str(data.get("role") or "LABEL"),
            scene_number=str(data.get("scene_number") or ""),
            start=float(data.get("start") or 0.0),
            end=float(data.get("end") or 0.0),
            track=str(data.get("track") or "TEXT"),
            reason=str(data.get("reason") or ""),
            confidence=float(data.get("confidence") or 0.6),
            priority=int(data.get("priority") or 2),
            importance=imp if imp in IMPORTANCE_LEVELS else "medium",
            emphasis=emp if emp in EMPHASIS_LEVELS else "normal",
            semantic_purpose=purp if purp in SEMANTIC_PURPOSES else "identify",
            text=TextOverlaySpec.from_dict(text) if isinstance(text, dict) else None,
            map=MapGraphicSpec(**{
                k: v for k, v in (map_g or {}).items()
                if k in {f.name for f in dataclasses.fields(MapGraphicSpec)}
            }) if isinstance(map_g, dict) else None,
            payload=dict(data.get("payload") or {}) if isinstance(data.get("payload"), dict) else {},
            lifecycle=GraphicLifecycle.from_dict(data.get("lifecycle") or {}),
            animation=str(data.get("animation") or "FADE"),  # type: ignore[arg-type]
            sfx_action=str(data.get("sfx_action") or ""),
            z_index=int(data.get("z_index") or 60),
            underneath=str(data.get("underneath") or "hold"),
        )


@dataclasses.dataclass
class GraphicsPlan:
    """Compile-time graphics decisions for one documentary."""

    version: int = 1
    specs: List[GraphicSpec] = dataclasses.field(default_factory=list)
    qc_issues: List[dict] = dataclasses.field(default_factory=list)
    design_system: str = "documentary_package_v1"

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "design_system": self.design_system,
            "specs": [s.to_dict() for s in self.specs],
            "qc_issues": list(self.qc_issues),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphicsPlan":
        if not isinstance(data, dict):
            return cls()
        specs = [
            GraphicSpec.from_dict(s)
            for s in (data.get("specs") or [])
            if isinstance(s, dict)
        ]
        return cls(
            version=int(data.get("version") or 1),
            specs=specs,
            qc_issues=list(data.get("qc_issues") or []),
            design_system=str(data.get("design_system") or "documentary_package_v1"),
        )
