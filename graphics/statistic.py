"""Statistic graphic treatment — large number + label, restrained motion."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .design_system import DocumentaryDesignSystem, get_design_system
from .schema import GraphicLifecycle, TextOverlaySpec


def build_statistic_overlay(
    *,
    display: str,
    label: str = "",
    context: str = "",
    value: Optional[float] = None,
    unit: str = "",
    start: float = 0.0,
    end: float = 0.0,
    lifecycle: Optional[GraphicLifecycle] = None,
    design: DocumentaryDesignSystem | None = None,
) -> TextOverlaySpec:
    """Professional statistic card: +25% / ELECTRICITY DEMAND."""
    design = design or get_design_system()
    display = (display or "").strip()
    label = (label or "").strip().upper()
    return TextOverlaySpec(
        role="STATISTIC",
        text=display,
        secondary_text=label,
        tertiary_text=(context or "").strip(),
        start=start,
        end=end,
        position_x=0.78,
        position_y=0.78,
        alignment="center",
        font_family=design.font_data,
        weight="Bold",
        tracking_em=0.02,
        background="PANEL",
        animation="MASK_REVEAL",
        z_index=70,
        style_id="fact_number",
        lifecycle=lifecycle or GraphicLifecycle(
            enter_s=design.enter_statistic,
            hold_s=2.2,
            exit_s=design.exit_statistic,
        ),
        metadata={
            "template": "statistic_v1",
            "value": value,
            "unit": unit,
            "count_up": value is not None,
            "underline": True,
        },
    )


def statistic_render_payload(spec: TextOverlaySpec) -> Dict[str, Any]:
    """Extra draw instructions for the renderer."""
    meta = spec.metadata or {}
    return {
        "primary": spec.text,
        "label": spec.secondary_text,
        "context": spec.tertiary_text,
        "count_up": bool(meta.get("count_up")),
        "value": meta.get("value"),
        "unit": meta.get("unit") or "",
        "underline": bool(meta.get("underline", True)),
    }
