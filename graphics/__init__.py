"""Professional Graphics + Motion Design Engine.

Timeline-native graphics for documentary storytelling. Extends
EditorialTimeline / typography / FFmpeg overlays — does not replace them.

Composition intelligence (style / placement / size / background / motion /
timing) is deterministic and driven by semantic role + frame context.
"""

from .backgrounds import background_params, choose_background
from .composition import (
    CompositionDecision,
    compose_presentation,
    compute_size_vh,
    estimate_wrapped_lines,
    max_lines_for_role,
    occupied_block_ratios,
    score_placements,
    select_animation,
    select_placement,
    select_style_id,
    select_timing,
)
from .conflicts import filter_smart_text_for_graphics, smart_text_conflicts_with_graphics
from .design_system import (
    DEFAULT_DESIGN,
    DocumentaryDesignSystem,
    get_design_system,
    set_design_system,
)
from .director import GraphicDirective, decide_for_scenes, decide_graphic
from .engine import (
    attach_graphics_plan,
    graphic_spec_to_timeline_event,
    graphics_from_timeline,
    materialize_graphics_on_timeline,
    plan_graphics,
)
from .lifecycle import clamp_window, compute_lifecycle
from .memory import GraphicsMemory
from .motion import (
    MOTION_PRIMITIVES,
    ease,
    overlay_animation_name,
    sample_keyframes,
)
from .qc import qc_graphics_plan
from .render import render_graphic_overlay, render_graphics_for_scene
from .schema import (
    ANIMATION_TO_OVERLAY,
    GRAPHIC_ROLES,
    TEXT_ROLES,
    GraphicLifecycle,
    GraphicSpec,
    GraphicsPlan,
    Keyframe,
    MapGraphicSpec,
    TextOverlaySpec,
)
from .semantics import infer_semantics

__all__ = [
    "ANIMATION_TO_OVERLAY",
    "DEFAULT_DESIGN",
    "GRAPHIC_ROLES",
    "MOTION_PRIMITIVES",
    "TEXT_ROLES",
    "CompositionDecision",
    "DocumentaryDesignSystem",
    "GraphicDirective",
    "GraphicLifecycle",
    "GraphicSpec",
    "GraphicsMemory",
    "GraphicsPlan",
    "Keyframe",
    "MapGraphicSpec",
    "TextOverlaySpec",
    "attach_graphics_plan",
    "background_params",
    "choose_background",
    "clamp_window",
    "compose_presentation",
    "compute_lifecycle",
    "compute_size_vh",
    "decide_for_scenes",
    "decide_graphic",
    "ease",
    "estimate_wrapped_lines",
    "filter_smart_text_for_graphics",
    "get_design_system",
    "graphic_spec_to_timeline_event",
    "graphics_from_timeline",
    "infer_semantics",
    "materialize_graphics_on_timeline",
    "max_lines_for_role",
    "occupied_block_ratios",
    "overlay_animation_name",
    "plan_graphics",
    "qc_graphics_plan",
    "render_graphic_overlay",
    "render_graphics_for_scene",
    "sample_keyframes",
    "score_placements",
    "select_animation",
    "select_placement",
    "select_style_id",
    "select_timing",
    "set_design_system",
    "smart_text_conflicts_with_graphics",
]
