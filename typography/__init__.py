"""Modern typography theme/render layer for Smart Text Effects.

Does not plan events — maps existing Smart Editing text-effect payloads
to premium documentary styles at render time.
"""

from .fonts import FontRegistry, resolve_font_path
from .placement import resolve_placement
from .render import (
    build_drawtext_filters,
    format_display_text,
    render_style_overlay,
    typography_params_for_effect,
)
from .styles import EFFECT_TO_STYLE, TYPOGRAPHY_STYLES, map_effect_to_style
from .theme import DEFAULT_THEME, TypographyTheme, get_theme
from .debug import typography_debug_enabled, typography_proof_enabled
from .variation import (
    classify_semantic,
    plan_typography_decision,
    reset_variation_history,
    get_variation_history,
)

__all__ = [
    "DEFAULT_THEME",
    "EFFECT_TO_STYLE",
    "FontRegistry",
    "TYPOGRAPHY_STYLES",
    "TypographyTheme",
    "classify_semantic",
    "format_display_text",
    "build_drawtext_filters",
    "get_theme",
    "get_variation_history",
    "map_effect_to_style",
    "plan_typography_decision",
    "render_style_overlay",
    "reset_variation_history",
    "resolve_font_path",
    "resolve_placement",
    "typography_params_for_effect",
    "typography_debug_enabled",
    "typography_proof_enabled",
]
