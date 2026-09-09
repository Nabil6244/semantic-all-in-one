"""Post-alignment editorial plan shared by visual, audio, music, and pacing layers."""

from .audio_director import apply_audio_director, enrich_scene_audio_fields
from .builder import build_editorial_plan
from .complements import AssetCandidate, select_complements
from .edit_decision import EditDecision, EditorialEvent, ShotSpec
from .engine import (
    EditorialEngine,
    compile_editorial_plan,
    decision_map_from_plan,
    edit_decisions_from_plan,
)
from .intent import EditorialIntent
from .music_director import build_music_plan, render_ducked_music
from .pacing import authoritative_transition_map, finalize_transitions
from .persistence import (
    cache_settings_key,
    clear_editorial_plan,
    load_editorial_plan,
    save_editorial_plan,
)
from .qa import run_editorial_qa, save_editorial_qa
from .reasoner import (
    NullEditorialReasoner,
    StaticEditorialReasoner,
    build_editorial_reasoner,
    enrich_plan_with_editorial_ai,
    parse_intent_payload,
    reasoner_mode,
)
from .schema import (
    EDITORIAL_PLAN_VERSION,
    CameraStyle,
    EditorialPlan,
    EditorialScene,
    Purpose,
)
from .timeline import EditorialTimeline, TimelineEvent, validate_visual_timeline

__all__ = [
    "EDITORIAL_PLAN_VERSION",
    "AssetCandidate",
    "CameraStyle",
    "EditDecision",
    "EditorialEngine",
    "EditorialEvent",
    "EditorialIntent",
    "EditorialPlan",
    "EditorialScene",
    "EditorialTimeline",
    "NullEditorialReasoner",
    "Purpose",
    "ShotSpec",
    "StaticEditorialReasoner",
    "TimelineEvent",
    "apply_audio_director",
    "authoritative_transition_map",
    "build_editorial_plan",
    "build_editorial_reasoner",
    "build_music_plan",
    "cache_settings_key",
    "clear_editorial_plan",
    "compile_editorial_plan",
    "decision_map_from_plan",
    "edit_decisions_from_plan",
    "enrich_plan_with_editorial_ai",
    "enrich_scene_audio_fields",
    "finalize_transitions",
    "load_editorial_plan",
    "parse_intent_payload",
    "reasoner_mode",
    "render_ducked_music",
    "run_editorial_qa",
    "save_editorial_plan",
    "save_editorial_qa",
    "select_complements",
    "validate_visual_timeline",
]
