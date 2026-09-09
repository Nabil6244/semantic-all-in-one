"""Professional lower-third templates — restrained documentary style."""

from __future__ import annotations

from typing import Optional

from .design_system import DocumentaryDesignSystem, get_design_system
from .schema import GraphicLifecycle, TextOverlaySpec


def build_lower_third(
    *,
    name: str,
    title: str = "",
    organization: str = "",
    location: str = "",
    date: str = "",
    source: str = "",
    start: float = 0.0,
    end: float = 0.0,
    lifecycle: Optional[GraphicLifecycle] = None,
    design: DocumentaryDesignSystem | None = None,
) -> TextOverlaySpec:
    """Classic enter → hold → exit lower third (not social-media oversized)."""
    design = design or get_design_system()
    name = (name or "").strip()
    title = (title or "").strip()
    organization = (organization or "").strip()
    secondary = title
    if organization and title:
        secondary = f"{title}  ·  {organization}"
    elif organization:
        secondary = organization
    tertiary_parts = [p for p in (location, date, source) if p]
    tertiary = "  ·  ".join(tertiary_parts)

    return TextOverlaySpec(
        role="LOWER_THIRD",
        text=name,
        secondary_text=secondary,
        tertiary_text=tertiary,
        start=start,
        end=end,
        position_x=0.20,
        position_y=0.82,
        alignment="left",
        font_family=design.font_ui,
        weight="Bold",
        background="LOWER_THIRD",
        animation="SLIDE",
        z_index=65,
        style_id="minimal_caption",
        lifecycle=lifecycle or GraphicLifecycle(
            enter_s=design.enter_lower_third,
            hold_s=max(1.8, (end - start) - design.enter_lower_third - design.exit_lower_third),
            exit_s=design.exit_lower_third,
        ),
        metadata={"template": "documentary_lower_third_v1"},
    )
