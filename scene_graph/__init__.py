"""Overscaled Scene Graph — semantic composition intermediate representation.

Phase 1/2 (foundation + CSV compiler): data model, validation, serialization,
a StylePreset registry, and CSV/heuristic/LLM-adapter generation — imported
eagerly below, dependency-free (stdlib only).

Phase 3 (full pipeline) lives in separate submodules, imported explicitly by
callers rather than eagerly here, since they pull in heavier project
dependencies (Pillow, ffmpeg, editorial.timeline, video_generator):

    scene_graph.overscaled_csv   — the dedicated Overscaled CSV contract
    scene_graph.layout           — deterministic SceneGraph -> fixed-canvas geometry
    scene_graph.composition      — Pillow rendering of node/edge reveal frames
    scene_graph.voiceover_sync   — retime placeholder timing to real audio
    scene_graph.render           — ONE fixed-canvas ffmpeg encode (no camera,
                                    no legs — see its own module docstring)
    scene_graph.timeline         — compile a rendered segment into a plain
                                    EditorialTimeline (VIDEO_1 + VOICEOVER,
                                    no new track, no timeline/engine changes)
    scene_graph.pipeline         — run_overscaled_pipeline(): ties all of the
                                    above together end to end

None of this touches EditorialTimeline, preview_engine.py, video_generator.py,
graphics/, Visual Director, or the editor UI — see scene_graph/schema.py and
each submodule's own docstring for the exact integration boundary.
"""

from .generator import (
    SceneGraphGenerationResult,
    generate_scene_graph,
    generate_scene_graph_heuristic,
    generate_scene_graph_with_llm,
    scene_rows_from_csv_rows,
)
from .schema import (
    KNOWN_ACTION_TYPES,
    KNOWN_NODE_TYPES,
    SCENE_GRAPH_VERSION,
    CameraKeyframe,
    CaptionSpec,
    SceneCanvas,
    SceneEdge,
    SceneGraph,
    SceneGraphAction,
    SceneGraphBeat,
    SceneNode,
    TitleCue,
)
from .style_presets import (
    STYLE_PRESET_VERSION,
    StylePreset,
    clear_style_preset_cache,
    list_style_presets,
    load_style_preset,
    style_presets_by_id,
)

__all__ = [
    "KNOWN_ACTION_TYPES",
    "KNOWN_NODE_TYPES",
    "SCENE_GRAPH_VERSION",
    "STYLE_PRESET_VERSION",
    "CameraKeyframe",
    "CaptionSpec",
    "SceneCanvas",
    "SceneEdge",
    "SceneGraph",
    "SceneGraphAction",
    "SceneGraphBeat",
    "SceneGraphGenerationResult",
    "SceneNode",
    "StylePreset",
    "TitleCue",
    "clear_style_preset_cache",
    "generate_scene_graph",
    "generate_scene_graph_heuristic",
    "generate_scene_graph_with_llm",
    "list_style_presets",
    "load_style_preset",
    "scene_rows_from_csv_rows",
    "style_presets_by_id",
]
