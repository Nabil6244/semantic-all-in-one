"""The DEDICATED Overscaled CSV contract — separate from the existing normal CSV.

    NORMAL CSV                          OVERSCALED CSV
    scene_number,script_segment,        scene_number,script_segment,node_id,
    asset_type,prompt                   node_type,role,asset_type,prompt,
                                         caption,highlight,camera_action,
                                         camera_target,edge_from,edge_to,
                                         edge_label,edge_style,chapter_title,
                                         node_label

``chapter_title`` is optional: a non-empty value starts a new persistent
chapter header (bold centered text, distinct from any image node) that stays
on screen — like the reference "Overscaled" channel's per-subject title card
— until the NEXT row with a non-empty ``chapter_title``, or the segment ends.

``node_label`` is optional: a short (1-3 word) tag rendered in red directly
above that node's media — e.g. "Vasa", "British" — distinct from both the
big centered ``chapter_title`` and the longer black ``caption`` sentence
drawn below the media. ``highlight`` accepts one OR MORE comma-separated
substrings of ``caption`` (e.g. ``"472,497"``); each is colored red inline.

``edge_style`` is optional: ``"callout"`` renders that arrow thick and red
(a "look here, this proves it" pointer, e.g. caption text -> proof photo);
anything else (or blank) is the default ``"sequential"`` black connector
arrow used for the normal cause->effect chain.

The two schemas are never merged. This module does not read or change the
existing normal CSV parser (``providers.base.SceneRow`` / ``csv.DictReader``
usage in video_generator.py/app.py) at all — it is a wholly separate reader
for a wholly separate file format.

The CSV describes semantic editorial intent only:
  - one row = one narration beat, optionally defining a node reveal, a causal
    edge, and/or a camera move — never pixel/canvas coordinates, never an
    ffmpeg filter, never a renderer instruction.
  - a row may define a NEW node (node_id + at least one of node_type/
    asset_type/prompt/caption) or simply REFERENCE an already-defined node_id
    for camera_target/edge_from/edge_to purposes.
  - re-defining the SAME node_id with conflicting node data on a later row is
    rejected as a compiler error, not silently overwritten.

Deterministic: same CSV -> same SceneGraph (no random ids, no timestamps, no
LLM calls). Placeholder beat/node/camera timing (word-count based, same
convention as scene_graph.generator's heuristic path) is used until
scene_graph.voiceover_sync retimes everything against the real voiceover.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence

from .generator import MIN_ROW_DURATION_S, WORDS_PER_SECOND
from .generator import SceneGraphGenerationResult
from .schema import (
    CameraKeyframe,
    CaptionSpec,
    SceneEdge,
    SceneGraph,
    SceneGraphAction,
    SceneGraphBeat,
    SceneNode,
    TitleCue,
)

# CSV column -> CameraKeyframe.zoom. The renderer no longer uses a camera at
# all (the canvas is fixed and never moves — see scene_graph/render.py);
# camera_action/camera_target are accepted and still populate
# scene_graph.camera_keyframes purely as inert, deprecated metadata so
# existing CSVs/JSON keep round-tripping without a compiler error.
_CAMERA_ACTION_ZOOM = {
    "focus": 1.4,
    "zoom_in": 1.4,
    "establish": 1.0,
    "zoom_out": 1.0,
    "pan": 1.15,
    "hold": 1.15,
}
DEFAULT_EDGE_DRAW_DURATION_S = 1.0

REQUIRED_COLUMNS = ("scene_number", "script_segment")
OPTIONAL_COLUMNS = (
    "node_id", "node_type", "role", "asset_type", "prompt", "caption",
    "highlight", "camera_action", "camera_target", "edge_from", "edge_to",
    "edge_label", "edge_style", "chapter_title", "node_label",
)
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


def _get(row: Mapping[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def _node_defines_data(row: Mapping[str, str]) -> bool:
    return any(_get(row, k) for k in ("node_type", "asset_type", "prompt", "caption"))


def compile_overscaled_csv(
    csv_rows: Sequence[Mapping[str, str]],
    *,
    segment_id: str,
    title: str = "",
    style_preset: str = "overscaled",
) -> SceneGraphGenerationResult:
    """Compile the dedicated Overscaled CSV contract into a validated SceneGraph.

    Never raises. Structural CSV problems (missing required columns, a
    conflicting node redefinition) are returned as ``ok=False`` with clear
    error strings, exactly like the LLM path in scene_graph.generator — the
    caller decides what to do, nothing here fabricates a corrupted graph.
    """

    errors: List[str] = []
    if not csv_rows:
        errors.append("Overscaled CSV has no rows")
        return SceneGraphGenerationResult(ok=False, scene_graph=None, errors=errors, source="overscaled_csv")

    for col in REQUIRED_COLUMNS:
        if col not in csv_rows[0]:
            errors.append(f"Overscaled CSV missing required column '{col}'")
    if errors:
        return SceneGraphGenerationResult(ok=False, scene_graph=None, errors=errors, source="overscaled_csv")

    nodes: List[SceneNode] = []
    node_defined_by: Dict[str, int] = {}  # node_id -> row index that defined it
    edges: List[SceneEdge] = []
    camera_keyframes: List[CameraKeyframe] = []
    beats: List[SceneGraphBeat] = []
    title_cues: List[TitleCue] = []

    cursor = 0.0
    for index, row in enumerate(csv_rows):
        scene_number = _get(row, "scene_number") or str(index + 1)
        script_segment = _get(row, "script_segment")
        word_count = len(script_segment.split())
        duration = max(MIN_ROW_DURATION_S, word_count / WORDS_PER_SECOND)
        start = cursor
        end = cursor + duration
        cursor = end

        actions: List[SceneGraphAction] = []

        node_id = _get(row, "node_id")
        if node_id and _node_defines_data(row):
            if node_id in node_defined_by:
                prior_index = node_defined_by[node_id]
                errors.append(
                    f"row {index + 1} (scene {scene_number}): node_id {node_id!r} was already "
                    f"defined on row {prior_index + 1} — conflicting redefinition"
                )
            else:
                node_defined_by[node_id] = index
                caption_text = _get(row, "caption")
                highlight = _get(row, "highlight") or None
                caption = CaptionSpec(text=caption_text, highlight=highlight) if caption_text else None
                node = SceneNode(
                    id=node_id,
                    type=_get(row, "node_type") or "image",
                    semantic_role=_get(row, "role"),
                    asset_source=_get(row, "asset_type"),
                    asset_reference=_get(row, "prompt"),
                    appear_at=round(start, 4),
                    label=_get(row, "node_label"),
                    caption=caption,
                    # Records the ORIGINATING CSV row's scene_number so a later
                    # media-resolution pass can route through the existing
                    # resolve_scene_assets()/find_image_for_scene() convention,
                    # which requires a numeric scene_number — see
                    # scene_graph/media_resolution.py. Purely additive metadata;
                    # nothing else reads or requires this key.
                    metadata={"scene_number": scene_number},
                )
                nodes.append(node)
            actions.append(
                SceneGraphAction(type="reveal_node", action_id=f"a_reveal_{node_id}_{scene_number}", node_id=node_id)
            )

        edge_from = _get(row, "edge_from")
        edge_to = _get(row, "edge_to")
        if edge_from and edge_to:
            edge_id = f"e_{edge_from}_{edge_to}"
            edge_label = _get(row, "edge_label")
            edge_style_raw = _get(row, "edge_style").lower()
            # "group"/"group_grid" are real graph edges (group their
            # endpoints into one on-screen chapter, see
            # layout._connected_chapters) that never draw a visible arrow
            # (see layout.compute_layout's edge-window loop) — used by
            # scene_graph.exp_solar_csv's four_row/index_grid adapters
            # respectively. No existing/documented Overscaled CSV column
            # value was ever "group"/"group_grid" (only "callout" was
            # recognized; everything else, including these, previously
            # fell through to "sequential"), so this is additive: any
            # pre-existing CSV keeps its exact prior behavior.
            edge_kind = edge_style_raw if edge_style_raw in ("callout", "group", "group_grid") else "sequential"
            edges.append(
                SceneEdge(
                    id=edge_id,
                    from_node=edge_from,
                    to_node=edge_to,
                    style="hand_drawn",
                    kind=edge_kind,
                    draw_at=round(start, 4),
                    duration=DEFAULT_EDGE_DRAW_DURATION_S,
                    metadata={"label": edge_label} if edge_label else {},
                )
            )
            actions.append(
                SceneGraphAction(type="draw_edge", action_id=f"a_draw_{edge_id}_{scene_number}", edge_id=edge_id)
            )

        chapter_title = _get(row, "chapter_title")
        if chapter_title:
            title_cues.append(TitleCue(text=chapter_title, at=round(start, 4)))

        camera_action = _get(row, "camera_action")
        camera_target = _get(row, "camera_target")
        if camera_action and camera_target:
            cam_id = f"cam_{scene_number}"
            zoom = _CAMERA_ACTION_ZOOM.get(camera_action.lower(), 1.0)
            camera_keyframes.append(
                CameraKeyframe(
                    keyframe_id=cam_id,
                    at=round(start, 4),
                    frame_nodes=[camera_target],
                    zoom=zoom,
                )
            )
            actions.append(
                SceneGraphAction(type="move_camera", action_id=f"a_cam_{cam_id}", camera_keyframe_id=cam_id)
            )

        beats.append(
            SceneGraphBeat(
                beat_id=f"beat_{scene_number}",
                narration=script_segment,
                start=round(start, 4),
                end=round(end, 4),
                actions=actions,
            )
        )

    if errors:
        return SceneGraphGenerationResult(ok=False, scene_graph=None, errors=errors, source="overscaled_csv")

    scene_graph = SceneGraph(
        segment_id=segment_id,
        title=title,
        style_preset=style_preset,
        duration=round(cursor, 4),
        nodes=nodes,
        edges=edges,
        camera_keyframes=camera_keyframes,
        beats=beats,
        title_cues=title_cues,
    )
    validation_errors = scene_graph.validate()
    if validation_errors:
        return SceneGraphGenerationResult(
            ok=False, scene_graph=None, errors=validation_errors, source="overscaled_csv"
        )
    return SceneGraphGenerationResult(ok=True, scene_graph=scene_graph, errors=[], source="overscaled_csv")
