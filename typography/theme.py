"""Central typography theme — fonts, sizes, motion, and safe zones."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TypographyTheme:
    """Tunable documentary typography settings (no Smart Editing logic)."""

    name: str = "documentary_2026"
    # Vertical safe zone: keep text out of extreme edges / faces.
    margin_x_ratio: float = 0.07
    y_primary_ratio: float = 0.70
    y_secondary_ratio: float = 0.78
    y_statement_ratio: float = 0.62
    # Motion (seconds) — short & controlled, no bounce.
    fade_in: float = 0.11
    fade_out: float = 0.09
    slide_px: float = 10.0
    scale_from: float = 0.96
    # Hierarchy multipliers applied on top of style size_vh.
    intensity_size_boost: float = 0.10
    # Default colors (RGBA 0–255).
    fill: tuple = (255, 255, 255, 255)
    stroke: tuple = (0, 0, 0, 220)
    accent: tuple = (0, 220, 255, 255)  # high-visibility cyan accent (not karaoke gold)
    # Style overrides keyed by style id (merged onto TYPOGRAPHY_STYLES).
    style_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def with_overrides(self, **kwargs: Any) -> "TypographyTheme":
        data = {
            "name": self.name,
            "margin_x_ratio": self.margin_x_ratio,
            "y_primary_ratio": self.y_primary_ratio,
            "y_secondary_ratio": self.y_secondary_ratio,
            "y_statement_ratio": self.y_statement_ratio,
            "fade_in": self.fade_in,
            "fade_out": self.fade_out,
            "slide_px": self.slide_px,
            "scale_from": self.scale_from,
            "intensity_size_boost": self.intensity_size_boost,
            "fill": self.fill,
            "stroke": self.stroke,
            "accent": self.accent,
            "style_overrides": deepcopy(self.style_overrides),
        }
        data.update(kwargs)
        return TypographyTheme(**data)


DEFAULT_THEME = TypographyTheme()
_THEME: TypographyTheme = DEFAULT_THEME


def get_theme() -> TypographyTheme:
    return _THEME


def set_theme(theme: Optional[TypographyTheme]) -> TypographyTheme:
    global _THEME
    _THEME = theme or DEFAULT_THEME
    return _THEME
