"""Map Brand Kit caption/accent prefs onto TypographyTheme (optional)."""

from __future__ import annotations

from typing import Optional, Tuple

from typography.theme import TypographyTheme, get_theme

from .schema import BrandKit, ResolvedStyle


def _parse_hex_rgb(color: str) -> Optional[Tuple[int, int, int]]:
    raw = (color or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return None
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return None


def typography_theme_for_resolved(
    resolved: Optional[ResolvedStyle],
    base: Optional[TypographyTheme] = None,
) -> TypographyTheme:
    """Return theme with brand accent applied when BrandKit has accent_color."""
    theme = base or get_theme()
    kit: Optional[BrandKit] = resolved.brand_kit if resolved else None
    if kit is None:
        return theme
    kwargs = {}
    rgb = _parse_hex_rgb(kit.accent_color)
    if rgb is not None:
        kwargs["accent"] = (rgb[0], rgb[1], rgb[2], 255)
    name = str((kit.typography or {}).get("theme") or "").strip()
    if name:
        kwargs["name"] = name
    if not kwargs:
        return theme
    return theme.with_overrides(**kwargs)
