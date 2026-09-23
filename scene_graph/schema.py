"""Overscaled Scene Graph — semantic composition intent (Phase 1: data model only).

This is an intermediate representation, NOT a replacement for anything:

    Existing CSV / script
        -> Visual Director (unchanged)
        -> SceneGraph (this module)
        -> Layout            (not implemented yet)
        -> Composition        (not implemented yet)
        -> existing EditorialTimeline / TimelineEvent (unchanged)
        -> existing preview / FFmpeg export (unchanged)

A SceneGraph describes ONE composition segment: a persistent large canvas
holding image / diagram / video-loop / anchor nodes, causal arrows between
them, semantic captions, and a low-frequency camera timeline — independent
of node-reveal cadence (see module docstring intent in the design brief).

Deliberately excluded from this phase (do not add speculatively):
  - pixel layout coordinates (nodes/camera keep `position`/`size` optional;
    a later layout pass fills them in — the LLM-facing intent stays semantic)
  - any TimelineEvent/track compilation
  - any rendering

Conventions mirror the rest of the codebase (see editorial/timeline.py,
graphics/schema.py): plain ``dataclasses``, hand-written permissive
``to_dict``/``from_dict`` pairs that filter to known fields and default
missing/invalid data rather than raising, and small ``validate()`` methods
that return a list of human-readable problem strings (empty == valid) —
the same non-raising "issue list" shape as
``editorial.timeline.validate_visual_timeline``.

``asset_source`` on a SceneNode reuses the SAME asset-type contract as the
existing CSV/Visual-Director pipeline (``flow_image``, ``flow_video``,
``stock_image``, ``stock_video``, ``youtube_video``, ``local``, ...; see
``providers.base.AssetSource`` / ``visual_director.schema``). This module
does not import that enum (keeping this new package dependency-free during
the foundation phase) but the value space is the same — callers should pass
through whatever asset_type/provider string the existing pipeline already
produced. ``semantic_role`` is a wholly separate, free-text concept (e.g.
"design_flaw", "establisher") and must never be confused with it.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

SCENE_GRAPH_VERSION = 1

# Documentary/recommended node types — intentionally NOT a strict enum.
# Unknown types are accepted (permissive schema, matches TextOverlaySpec/
# GraphicSpec convention of normalizing-with-fallback rather than rejecting).
KNOWN_NODE_TYPES = frozenset({"image", "diagram", "video_loop", "anchor"})

# Action types with a well-defined required target field. Unknown/custom
# action types are still accepted; only these get their target-field
# presence checked in validate().
KNOWN_ACTION_TYPES = frozenset({"reveal_node", "draw_edge", "move_camera", "set_caption"})


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v) for v in value]


@dataclasses.dataclass
class CaptionSpec:
    """A short on-canvas caption with an optional structural highlight.

    The highlight is never baked into an image — it's one or more
    comma-separated substrings of ``text`` (e.g. ``"472,497"``) that the
    renderer colors red inline, matching the reference "Overscaled" style's
    multiple highlighted keywords per sentence (a single term with no comma
    still works exactly as a plain single highlight).
    """

    text: str = ""
    highlight: Optional[str] = None
    font: str = ""
    position: Optional[Dict[str, float]] = None

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not str(self.text or "").strip():
            errors.append("CaptionSpec.text is required and cannot be empty")
            return errors
        if self.highlight is not None:
            highlight = str(self.highlight)
            if not highlight:
                errors.append("CaptionSpec.highlight cannot be an empty string (use null instead)")
            else:
                terms = [t.strip() for t in highlight.split(",") if t.strip()]
                if not terms:
                    errors.append("CaptionSpec.highlight cannot be an empty string (use null instead)")
                for term in terms:
                    if term not in self.text:
                        errors.append(
                            f"CaptionSpec.highlight {term!r} is not a verbatim substring of text {self.text!r}"
                        )
        return errors

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "highlight": self.highlight,
            "font": self.font,
            "position": dict(self.position) if isinstance(self.position, dict) else None,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CaptionSpec":
        if not isinstance(data, dict):
            return cls()
        highlight = data.get("highlight")
        position = data.get("position")
        return cls(
            text=str(data.get("text") or ""),
            highlight=str(highlight) if highlight is not None else None,
            font=str(data.get("font") or ""),
            position=dict(position) if isinstance(position, dict) else None,
        )


@dataclasses.dataclass
class SceneNode:
    """One asset placed on the large composition canvas."""

    id: str
    type: str = "image"  # image | diagram | video_loop | anchor (extensible)
    semantic_role: str = ""  # e.g. "establisher", "design_flaw" — NOT asset_source
    asset_source: str = ""  # e.g. "flow_image" — same contract as existing CSV asset_type
    asset_reference: str = ""  # concrete path / prompt / provider id for the asset
    appear_at: float = 0.0
    duration: Optional[float] = None  # None == persists until segment/camera moves on
    label: str = ""  # short red tag drawn ABOVE the media (e.g. "Vasa") — distinct from `caption`
    caption: Optional[CaptionSpec] = None
    position: Optional[Dict[str, float]] = None  # filled by the (future) layout pass
    size: Optional[Dict[str, float]] = None  # filled by the (future) layout pass
    scale: float = 1.0
    rotation: float = 0.0
    border: bool = True
    shadow: bool = True
    z_index: int = 0
    relationships: Dict[str, Any] = dataclasses.field(default_factory=dict)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not str(self.id or "").strip():
            errors.append("SceneNode.id is required and cannot be empty")
        if not str(self.type or "").strip():
            errors.append(f"SceneNode {self.id!r}: type is required and cannot be empty")
        if float(self.appear_at) < 0:
            errors.append(f"SceneNode {self.id!r}: appear_at must be >= 0")
        if self.duration is not None and float(self.duration) < 0:
            errors.append(f"SceneNode {self.id!r}: duration must be >= 0 when set")
        if self.caption is not None:
            errors.extend(
                f"SceneNode {self.id!r}: {msg}" for msg in self.caption.validate()
            )
        return errors

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "semantic_role": self.semantic_role,
            "asset_source": self.asset_source,
            "asset_reference": self.asset_reference,
            "appear_at": round(float(self.appear_at), 4),
            "duration": round(float(self.duration), 4) if self.duration is not None else None,
            "label": self.label,
            "caption": self.caption.to_dict() if self.caption is not None else None,
            "position": dict(self.position) if isinstance(self.position, dict) else None,
            "size": dict(self.size) if isinstance(self.size, dict) else None,
            "scale": self.scale,
            "rotation": self.rotation,
            "border": bool(self.border),
            "shadow": bool(self.shadow),
            "z_index": int(self.z_index),
            "relationships": dict(self.relationships or {}),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SceneNode":
        if not isinstance(data, dict):
            data = {}
        caption = data.get("caption")
        position = data.get("position")
        size = data.get("size")
        duration = data.get("duration")
        return cls(
            id=str(data.get("id") or ""),
            type=str(data.get("type") or "image"),
            semantic_role=str(data.get("semantic_role") or ""),
            asset_source=str(data.get("asset_source") or ""),
            asset_reference=str(data.get("asset_reference") or ""),
            appear_at=float(data.get("appear_at") or 0.0),
            duration=float(duration) if duration is not None else None,
            label=str(data.get("label") or ""),
            caption=CaptionSpec.from_dict(caption) if isinstance(caption, dict) else None,
            position=dict(position) if isinstance(position, dict) else None,
            size=dict(size) if isinstance(size, dict) else None,
            scale=float(data.get("scale") if data.get("scale") is not None else 1.0),
            rotation=float(data.get("rotation") or 0.0),
            border=bool(data.get("border", True)),
            shadow=bool(data.get("shadow", True)),
            z_index=int(data.get("z_index") or 0),
            relationships=_as_dict(data.get("relationships")),
            metadata=_as_dict(data.get("metadata")),
        )


@dataclasses.dataclass
class SceneEdge:
    """A first-class causal arrow between two nodes. Never rendered here."""

    id: str
    from_node: str = ""
    to_node: str = ""
    style: str = ""  # e.g. "hand_drawn" — preset supplies the default
    color: str = ""  # empty == preset default
    kind: str = "sequential"  # "sequential" (default, black connector) | "callout" (thick red emphasis pointer)
    draw_at: float = 0.0
    duration: float = 1.0
    curve: Dict[str, Any] = dataclasses.field(default_factory=dict)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not str(self.id or "").strip():
            errors.append("SceneEdge.id is required and cannot be empty")
        if not str(self.from_node or "").strip():
            errors.append(f"SceneEdge {self.id!r}: 'from' is required and cannot be empty")
        if not str(self.to_node or "").strip():
            errors.append(f"SceneEdge {self.id!r}: 'to' is required and cannot be empty")
        if float(self.draw_at) < 0:
            errors.append(f"SceneEdge {self.id!r}: draw_at must be >= 0")
        if float(self.duration) <= 0:
            errors.append(f"SceneEdge {self.id!r}: duration must be > 0")
        return errors

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_node,
            "to": self.to_node,
            "style": self.style,
            "color": self.color,
            "kind": self.kind,
            "draw_at": round(float(self.draw_at), 4),
            "duration": round(float(self.duration), 4),
            "curve": dict(self.curve or {}),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SceneEdge":
        if not isinstance(data, dict):
            data = {}
        from_node = data.get("from", data.get("from_node"))
        to_node = data.get("to", data.get("to_node"))
        return cls(
            id=str(data.get("id") or ""),
            from_node=str(from_node or ""),
            to_node=str(to_node or ""),
            style=str(data.get("style") or ""),
            color=str(data.get("color") or ""),
            kind=str(data.get("kind") or "sequential"),
            draw_at=float(data.get("draw_at") or 0.0),
            duration=float(data.get("duration") if data.get("duration") is not None else 1.0),
            curve=_as_dict(data.get("curve")),
            metadata=_as_dict(data.get("metadata")),
        )


@dataclasses.dataclass
class CameraKeyframe:
    """A low-frequency camera framing change. NOT a TimelineEvent (yet)."""

    at: float = 0.0
    keyframe_id: str = ""
    frame_nodes: List[str] = dataclasses.field(default_factory=list)
    zoom: float = 1.0
    position: Optional[Dict[str, float]] = None
    easing: str = "ease_in_out"

    def validate(self) -> List[str]:
        errors: List[str] = []
        if float(self.at) < 0:
            errors.append(f"CameraKeyframe {self.keyframe_id or self.at!r}: at must be >= 0")
        if float(self.zoom) <= 0:
            errors.append(f"CameraKeyframe {self.keyframe_id or self.at!r}: zoom must be > 0")
        return errors

    def to_dict(self) -> dict:
        return {
            "at": round(float(self.at), 4),
            "keyframe_id": self.keyframe_id,
            "frame_nodes": list(self.frame_nodes or []),
            "zoom": self.zoom,
            "position": dict(self.position) if isinstance(self.position, dict) else None,
            "easing": self.easing,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CameraKeyframe":
        if not isinstance(data, dict):
            data = {}
        position = data.get("position")
        return cls(
            at=float(data.get("at") or 0.0),
            keyframe_id=str(data.get("keyframe_id") or ""),
            frame_nodes=_as_str_list(data.get("frame_nodes")),
            zoom=float(data.get("zoom") if data.get("zoom") is not None else 1.0),
            position=dict(position) if isinstance(position, dict) else None,
            easing=str(data.get("easing") or "ease_in_out"),
        )


@dataclasses.dataclass
class SceneGraphAction:
    """One coordinated effect a narration beat causes.

    A beat may carry several actions (a node reveal AND an arrow draw-on
    AND a caption change, all from one sentence) — this is intentionally
    NOT a rigid "one sentence = one node" model.
    """

    type: str = ""  # reveal_node | draw_edge | move_camera | set_caption (extensible)
    action_id: str = ""
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    camera_keyframe_id: Optional[str] = None
    caption: Optional[CaptionSpec] = None
    payload: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        action_type = str(self.type or "").strip()
        label = self.action_id or action_type or "<action>"
        if not action_type:
            errors.append(f"SceneGraphAction {label!r}: type is required and cannot be empty")
            return errors
        if action_type == "reveal_node" and not str(self.node_id or "").strip():
            errors.append(f"SceneGraphAction {label!r}: reveal_node requires node_id")
        if action_type == "draw_edge" and not str(self.edge_id or "").strip():
            errors.append(f"SceneGraphAction {label!r}: draw_edge requires edge_id")
        if action_type == "move_camera" and not str(self.camera_keyframe_id or "").strip():
            errors.append(f"SceneGraphAction {label!r}: move_camera requires camera_keyframe_id")
        if action_type == "set_caption":
            if not str(self.node_id or "").strip():
                errors.append(f"SceneGraphAction {label!r}: set_caption requires node_id")
            if self.caption is None:
                errors.append(f"SceneGraphAction {label!r}: set_caption requires a caption")
            else:
                errors.extend(
                    f"SceneGraphAction {label!r}: {msg}" for msg in self.caption.validate()
                )
        return errors

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "action_id": self.action_id,
            "node_id": self.node_id,
            "edge_id": self.edge_id,
            "camera_keyframe_id": self.camera_keyframe_id,
            "caption": self.caption.to_dict() if self.caption is not None else None,
            "payload": dict(self.payload or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SceneGraphAction":
        if not isinstance(data, dict):
            data = {}
        node_id = data.get("node_id")
        edge_id = data.get("edge_id")
        camera_keyframe_id = data.get("camera_keyframe_id")
        caption = data.get("caption")
        return cls(
            type=str(data.get("type") or ""),
            action_id=str(data.get("action_id") or ""),
            node_id=str(node_id) if node_id is not None else None,
            edge_id=str(edge_id) if edge_id is not None else None,
            camera_keyframe_id=str(camera_keyframe_id) if camera_keyframe_id is not None else None,
            caption=CaptionSpec.from_dict(caption) if isinstance(caption, dict) else None,
            payload=_as_dict(data.get("payload")),
        )


@dataclasses.dataclass
class SceneGraphBeat:
    """One narration beat and every composition action it triggers."""

    beat_id: str
    narration: str = ""
    start: float = 0.0
    end: float = 0.0
    actions: List[SceneGraphAction] = dataclasses.field(default_factory=list)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not str(self.beat_id or "").strip():
            errors.append("SceneGraphBeat.beat_id is required and cannot be empty")
        label = self.beat_id or "<beat>"
        if float(self.start) < 0:
            errors.append(f"SceneGraphBeat {label!r}: start must be >= 0")
        if float(self.end) <= float(self.start):
            errors.append(f"SceneGraphBeat {label!r}: end must be greater than start")
        for action in self.actions:
            errors.extend(f"SceneGraphBeat {label!r}: {msg}" for msg in action.validate())
        return errors

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "narration": self.narration,
            "start": round(float(self.start), 4),
            "end": round(float(self.end), 4),
            "actions": [a.to_dict() for a in self.actions],
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SceneGraphBeat":
        if not isinstance(data, dict):
            data = {}
        actions = [
            SceneGraphAction.from_dict(a)
            for a in (data.get("actions") or [])
            if isinstance(a, dict)
        ]
        return cls(
            beat_id=str(data.get("beat_id") or ""),
            narration=str(data.get("narration") or ""),
            start=float(data.get("start") or 0.0),
            end=float(data.get("end") or 0.0),
            actions=actions,
            metadata=_as_dict(data.get("metadata")),
        )


@dataclasses.dataclass
class SceneCanvas:
    """Canvas size/background override. None fields mean 'use style preset default'."""

    width: Optional[int] = None
    height: Optional[int] = None
    background: str = ""

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "background": self.background}

    @classmethod
    def from_dict(cls, data: Any) -> "SceneCanvas":
        if not isinstance(data, dict):
            return cls()
        width = data.get("width")
        height = data.get("height")
        return cls(
            width=int(width) if width is not None else None,
            height=int(height) if height is not None else None,
            background=str(data.get("background") or ""),
        )


@dataclasses.dataclass
class TitleCue:
    """A persistent chapter/subject header (e.g. a ship's name) — rendered as
    bold centered text, distinct from any image node. Active from ``at``
    until the next TitleCue's ``at`` (or the segment end), matching the
    reference "Overscaled" style's per-subject title card that stays up
    while the underlying content nodes come and go beneath it."""

    text: str = ""
    at: float = 0.0

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not str(self.text or "").strip():
            errors.append("TitleCue.text is required and cannot be empty")
        if float(self.at) < 0:
            errors.append(f"TitleCue {self.text!r}: at must be >= 0")
        return errors

    def to_dict(self) -> dict:
        return {"text": self.text, "at": round(float(self.at), 4)}

    @classmethod
    def from_dict(cls, data: Any) -> "TitleCue":
        if not isinstance(data, dict):
            data = {}
        return cls(text=str(data.get("text") or ""), at=float(data.get("at") or 0.0))


@dataclasses.dataclass
class SceneGraph:
    """One complete Overscaled composition segment (semantic intent only).

    No final pixel coordinates are required here — SceneNode/CameraKeyframe
    ``position``/``size`` stay optional until a (future) layout pass fills
    them in. This object never becomes a TimelineEvent by itself; a later,
    separate compilation step does that (not implemented in this phase).
    """

    segment_id: str
    version: int = SCENE_GRAPH_VERSION
    title: str = ""
    style_preset: str = ""  # e.g. "overscaled" — id into scene_graph.style_presets
    duration: float = 0.0
    canvas: SceneCanvas = dataclasses.field(default_factory=SceneCanvas)
    nodes: List[SceneNode] = dataclasses.field(default_factory=list)
    edges: List[SceneEdge] = dataclasses.field(default_factory=list)
    camera_keyframes: List[CameraKeyframe] = dataclasses.field(default_factory=list)
    beats: List[SceneGraphBeat] = dataclasses.field(default_factory=list)
    title_cues: List[TitleCue] = dataclasses.field(default_factory=list)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not str(self.segment_id or "").strip():
            errors.append("SceneGraph.segment_id is required and cannot be empty")
        for cue in self.title_cues:
            errors.extend(cue.validate())

        node_ids = [n.id for n in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            dupes = sorted({n for n in node_ids if node_ids.count(n) > 1})
            errors.append(f"duplicate SceneNode id(s): {dupes}")
        node_id_set = set(node_ids)
        for node in self.nodes:
            errors.extend(node.validate())

        edge_ids = [e.id for e in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            dupes = sorted({e for e in edge_ids if edge_ids.count(e) > 1})
            errors.append(f"duplicate SceneEdge id(s): {dupes}")
        edge_id_set = set(edge_ids)
        for edge in self.edges:
            errors.extend(edge.validate())
            if edge.from_node and edge.from_node not in node_id_set:
                errors.append(
                    f"SceneEdge {edge.id!r}: 'from' node {edge.from_node!r} does not exist"
                )
            if edge.to_node and edge.to_node not in node_id_set:
                errors.append(
                    f"SceneEdge {edge.id!r}: 'to' node {edge.to_node!r} does not exist"
                )

        keyframe_ids = [k.keyframe_id for k in self.camera_keyframes if k.keyframe_id]
        if len(set(keyframe_ids)) != len(keyframe_ids):
            dupes = sorted({k for k in keyframe_ids if keyframe_ids.count(k) > 1})
            errors.append(f"duplicate CameraKeyframe keyframe_id(s): {dupes}")
        keyframe_id_set = set(keyframe_ids)

        prev_at: Optional[float] = None
        for idx, kf in enumerate(self.camera_keyframes):
            errors.extend(kf.validate())
            for ref in kf.frame_nodes:
                if ref not in node_id_set:
                    errors.append(
                        f"CameraKeyframe[{idx}] frame_nodes references unknown node {ref!r}"
                    )
            if prev_at is not None and float(kf.at) <= prev_at:
                errors.append(
                    f"CameraKeyframe[{idx}] at={kf.at} is not after the previous keyframe "
                    f"at={prev_at} (camera_keyframes must be strictly increasing in time)"
                )
            prev_at = float(kf.at)

        for beat in self.beats:
            errors.extend(beat.validate())
            if self.duration and float(beat.end) > float(self.duration) + 0.001:
                errors.append(
                    f"SceneGraphBeat {beat.beat_id!r}: end={beat.end} exceeds segment duration={self.duration}"
                )
            for action in beat.actions:
                if action.type == "reveal_node" and action.node_id not in node_id_set:
                    errors.append(
                        f"SceneGraphBeat {beat.beat_id!r} action {action.action_id or action.type!r}: "
                        f"node_id {action.node_id!r} does not exist"
                    )
                if action.type == "set_caption" and action.node_id not in node_id_set:
                    errors.append(
                        f"SceneGraphBeat {beat.beat_id!r} action {action.action_id or action.type!r}: "
                        f"node_id {action.node_id!r} does not exist"
                    )
                if action.type == "draw_edge" and action.edge_id not in edge_id_set:
                    errors.append(
                        f"SceneGraphBeat {beat.beat_id!r} action {action.action_id or action.type!r}: "
                        f"edge_id {action.edge_id!r} does not exist"
                    )
                if action.type == "move_camera" and action.camera_keyframe_id:
                    if action.camera_keyframe_id not in keyframe_id_set:
                        errors.append(
                            f"SceneGraphBeat {beat.beat_id!r} action {action.action_id or action.type!r}: "
                            f"camera_keyframe_id {action.camera_keyframe_id!r} does not exist"
                        )

        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "segment_id": self.segment_id,
            "title": self.title,
            "style_preset": self.style_preset,
            "duration": round(float(self.duration), 4),
            "canvas": self.canvas.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "camera_keyframes": [k.to_dict() for k in self.camera_keyframes],
            "beats": [b.to_dict() for b in self.beats],
            "title_cues": [c.to_dict() for c in self.title_cues],
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SceneGraph":
        if not isinstance(data, dict):
            data = {}
        nodes = [
            SceneNode.from_dict(n) for n in (data.get("nodes") or []) if isinstance(n, dict)
        ]
        edges = [
            SceneEdge.from_dict(e) for e in (data.get("edges") or []) if isinstance(e, dict)
        ]
        title_cues = [
            TitleCue.from_dict(c) for c in (data.get("title_cues") or []) if isinstance(c, dict)
        ]
        camera_keyframes = [
            CameraKeyframe.from_dict(k)
            for k in (data.get("camera_keyframes") or [])
            if isinstance(k, dict)
        ]
        beats = [
            SceneGraphBeat.from_dict(b) for b in (data.get("beats") or []) if isinstance(b, dict)
        ]
        return cls(
            segment_id=str(data.get("segment_id") or ""),
            version=int(data.get("version") or SCENE_GRAPH_VERSION),
            title=str(data.get("title") or ""),
            style_preset=str(data.get("style_preset") or ""),
            duration=float(data.get("duration") or 0.0),
            canvas=SceneCanvas.from_dict(data.get("canvas")),
            nodes=nodes,
            edges=edges,
            camera_keyframes=camera_keyframes,
            beats=beats,
            title_cues=title_cues,
            metadata=_as_dict(data.get("metadata")),
        )
