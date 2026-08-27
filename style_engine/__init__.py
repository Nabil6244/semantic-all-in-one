"""Brand Kit + Video Style engine (feeds EditorialPlan; never bypasses it)."""

from .apply import (
    apply_resolved_style,
    apply_style_to_scenes,
    asset_preference_rank,
    style_prompt_adornment,
)
from .detect import detect_style
from .loader import (
    brand_choices,
    load_brand_kit,
    load_style,
    save_user_brand_kit,
    style_choices,
)
from .profile import ContentProfile, build_content_profile, score_styles
from .resolver import merge_brand_overrides, resolve_from_workspace, resolve_style
from .schema import (
    BRAND_KIT_VERSION,
    VIDEO_STYLE_VERSION,
    BrandKit,
    ResolvedStyle,
    VideoStyle,
)
from .typography_map import typography_theme_for_resolved

__all__ = [
    "BRAND_KIT_VERSION",
    "VIDEO_STYLE_VERSION",
    "BrandKit",
    "VideoStyle",
    "ResolvedStyle",
    "ContentProfile",
    "detect_style",
    "build_content_profile",
    "score_styles",
    "resolve_style",
    "resolve_from_workspace",
    "merge_brand_overrides",
    "apply_resolved_style",
    "apply_style_to_scenes",
    "asset_preference_rank",
    "style_prompt_adornment",
    "typography_theme_for_resolved",
    "load_style",
    "load_brand_kit",
    "style_choices",
    "brand_choices",
    "save_user_brand_kit",
]
