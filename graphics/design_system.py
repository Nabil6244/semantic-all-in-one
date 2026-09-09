"""Documentary design system — one consistent package for the whole film.

Centralizes typography hierarchy, panels, spacing, motion timing, and map/chart
style tokens so scene 1 and scene N feel like the same documentary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

from .schema import AnimationKind, BackgroundKind


@dataclass(frozen=True)
class DocumentaryDesignSystem:
    """Single visual language for graphics + text overlays."""

    name: str = "documentary_package_v1"
    # Typography hierarchy (vh = fraction of frame height).
    # Documentary, not social-caption: hierarchy via role, not huge type.
    size_title: float = 0.058
    size_subtitle: float = 0.040
    size_statistic: float = 0.070
    size_label: float = 0.034
    size_lower_third_name: float = 0.038
    size_lower_third_role: float = 0.026
    size_callout: float = 0.040
    size_chapter: float = 0.056
    size_quote: float = 0.044
    size_caption: float = 0.032
    # Fonts (resolved via typography.fonts)
    font_display: str = "Manrope"
    font_body: str = "Outfit"
    font_data: str = "Space Grotesk"
    font_ui: str = "DM Sans"
    # Colors RGBA
    fill: Tuple[int, int, int, int] = (255, 255, 255, 255)
    fill_muted: Tuple[int, int, int, int] = (230, 230, 230, 230)
    accent: Tuple[int, int, int, int] = (0, 220, 255, 255)
    panel_fill: Tuple[int, int, int, int] = (8, 10, 14, 168)
    panel_fill_strong: Tuple[int, int, int, int] = (6, 8, 12, 200)
    scrim_fill: Tuple[int, int, int, int] = (0, 0, 0, 140)
    stroke: Tuple[int, int, int, int] = (0, 0, 0, 180)
    line: Tuple[int, int, int, int] = (255, 255, 255, 200)
    # Spacing / panels
    margin_x_ratio: float = 0.07
    safe_top_ratio: float = 0.10
    safe_bottom_ratio: float = 0.10
    panel_pad_x_em: float = 0.55
    panel_pad_y_em: float = 0.40
    corner_radius_px: float = 6.0
    pill_radius_em: float = 0.55
    line_thickness_px: float = 2.0
    shadow_blur: float = 4.0
    # Motion timing (seconds)
    enter_default: float = 0.35
    exit_default: float = 0.28
    enter_statistic: float = 0.40
    exit_statistic: float = 0.30
    enter_lower_third: float = 0.45
    exit_lower_third: float = 0.35
    hold_min: float = 1.2
    hold_max: float = 4.5
    # Density limits — breathing room between graphics
    max_graphics_per_30s: int = 3
    min_gap_between_graphics: float = 2.4
    # Role → default animation (limited documentary vocabulary).
    # CLEAN_FADE / SUBTLE_SLIDE / REVEAL / STATISTIC_REVEAL /
    # LOWER_THIRD_REVEAL / CHAPTER_REVEAL — mapped onto existing kinds.
    role_animation: Dict[str, AnimationKind] = field(
        default_factory=lambda: {
            "LOCATION": "SLIDE",
            "STATISTIC": "MASK_REVEAL",
            "CHAPTER": "MASK_REVEAL",
            "REVEAL": "MASK_REVEAL",
            "EMPHASIS": "FADE",
            "LOWER_THIRD": "SLIDE",
            "LABEL": "FADE",
            "CALLOUT": "FADE",
            "QUOTE": "FADE",
            "NAME": "SLIDE",
            "TITLE": "MASK_REVEAL",
            "CAPTION": "FADE",
            "PROGRESS": "FADE",
        }
    )
    # Role → default background
    role_background: Dict[str, BackgroundKind] = field(
        default_factory=lambda: {
            "LOCATION": "PILL",
            "STATISTIC": "PANEL",
            "CHAPTER": "NONE",
            "LOWER_THIRD": "LOWER_THIRD",
            "LABEL": "LOWER_THIRD",
            "CALLOUT": "LOWER_THIRD",
            "QUOTE": "SCRIM",
            "NAME": "LOWER_THIRD",
            "TITLE": "SCRIM",
            "CAPTION": "SCRIM",
            "EMPHASIS": "LOWER_THIRD",
            "DATA_LABEL": "PILL",
        }
    )

    def animation_for(self, role: str) -> AnimationKind:
        return self.role_animation.get(str(role or "").upper(), "FADE")

    def background_for(self, role: str) -> BackgroundKind:
        return self.role_background.get(str(role or "").upper(), "SCRIM")

    def size_vh_for(self, role: str) -> float:
        r = str(role or "").upper()
        mapping = {
            "TITLE": self.size_title,
            "SUBTITLE": self.size_subtitle,
            "STATISTIC": self.size_statistic,
            "LABEL": self.size_label,
            "LOCATION": self.size_label,
            "NAME": self.size_lower_third_name,
            "LOWER_THIRD": self.size_lower_third_name,
            "CALLOUT": self.size_callout,
            "CHAPTER": self.size_chapter,
            "QUOTE": self.size_quote,
            "CAPTION": self.size_caption,
            "EMPHASIS": self.size_callout,
            "DATA_LABEL": self.size_label,
            "DATE": self.size_label,
            "EVIDENCE": self.size_callout,
            "ANNOTATION": self.size_label * 0.9,
            "TECHNICAL_LABEL": self.size_label * 0.85,
            "COMPARISON": self.size_callout,
        }
        return mapping.get(r, self.size_label)

    def font_for(self, role: str) -> Tuple[str, str]:
        r = str(role or "").upper()
        if r in ("STATISTIC", "DATA_LABEL", "PROGRESS"):
            return self.font_data, "Bold"
        if r in ("TITLE", "CHAPTER", "EMPHASIS"):
            return self.font_display, "ExtraBold"
        if r in ("LOWER_THIRD", "NAME", "LOCATION", "LABEL"):
            return self.font_ui, "SemiBold" if r != "NAME" else "Bold"
        if r == "QUOTE":
            return self.font_body, "Bold"
        return self.font_body, "Bold"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "size_title": self.size_title,
            "size_statistic": self.size_statistic,
            "font_display": self.font_display,
            "font_body": self.font_body,
            "font_data": self.font_data,
            "accent": list(self.accent),
            "enter_default": self.enter_default,
            "exit_default": self.exit_default,
            "max_graphics_per_30s": self.max_graphics_per_30s,
        }


DEFAULT_DESIGN = DocumentaryDesignSystem()
_ACTIVE: DocumentaryDesignSystem = DEFAULT_DESIGN


def get_design_system() -> DocumentaryDesignSystem:
    return _ACTIVE


def set_design_system(system: DocumentaryDesignSystem | None) -> DocumentaryDesignSystem:
    global _ACTIVE
    _ACTIVE = system or DEFAULT_DESIGN
    return _ACTIVE
