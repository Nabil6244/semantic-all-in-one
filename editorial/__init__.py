"""Post-alignment editorial plan shared by visual, audio, music, and pacing layers."""

from .audio_director import apply_audio_director, enrich_scene_audio_fields
from .builder import build_editorial_plan
from .music_director import build_music_plan, render_ducked_music
from .pacing import authoritative_transition_map, finalize_transitions
from .persistence import (
    cache_settings_key,
    load_editorial_plan,
    save_editorial_plan,
)
from .qa import run_editorial_qa, save_editorial_qa
from .schema import (
    EDITORIAL_PLAN_VERSION,
    CameraStyle,
    EditorialPlan,
    EditorialScene,
    Purpose,
)

__all__ = [
    "EDITORIAL_PLAN_VERSION",
    "CameraStyle",
    "EditorialPlan",
    "EditorialScene",
    "Purpose",
    "apply_audio_director",
    "authoritative_transition_map",
    "build_editorial_plan",
    "build_music_plan",
    "cache_settings_key",
    "enrich_scene_audio_fields",
    "finalize_transitions",
    "load_editorial_plan",
    "render_ducked_music",
    "run_editorial_qa",
    "save_editorial_plan",
    "save_editorial_qa",
]
