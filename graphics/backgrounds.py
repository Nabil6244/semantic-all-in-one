"""Adaptive text background intelligence.

Does NOT put the same black rectangle behind every text element.
Chooses NONE / SHADOW / GRADIENT / SCRIM / PANEL / PILL / LOWER_THIRD /
FULL_WIDTH_OVERLAY from local brightness, complexity, role, and length.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .design_system import DocumentaryDesignSystem, get_design_system
from .schema import BackgroundKind


def choose_background(
    *,
    role: str,
    text: str,
    composition: Optional[Dict[str, Any]] = None,
    importance: str = "medium",
    over_face: bool = False,
    emphasis: str = "normal",
    design: DocumentaryDesignSystem | None = None,
) -> BackgroundKind:
    """Pick a documentary-appropriate background treatment."""
    design = design or get_design_system()
    role_u = (role or "LABEL").upper()
    text = (text or "").strip()
    n_chars = len(text)
    n_words = len(text.split())
    composition = composition or {}

    # Explicit role defaults first — then adapt.
    base: BackgroundKind = design.background_for(role_u)

    brightness = _frame_brightness(composition)
    complexity = _frame_complexity(composition)
    placement = str(
        composition.get("prefer")
        or composition.get("fallback")
        or composition.get("placement")
        or ""
    )

    # Major statistic / callout → intentional panel.
    if role_u == "STATISTIC" and importance in ("high", "critical"):
        return "PANEL"
    if role_u in ("LOWER_THIRD", "NAME"):
        return "LOWER_THIRD"
    if role_u == "CHAPTER" and n_words <= 4:
        return "NONE" if brightness < 0.45 else "SHADOW"

    # Text over face / busy subject → move treatment up, never none.
    if over_face or placement in (composition.get("avoid") or ()):
        if role_u in ("LABEL", "LOCATION", "DATA_LABEL"):
            return "PILL"
        if n_chars >= 28:
            return "FULL_WIDTH_OVERLAY"
        return "PANEL" if complexity >= 0.55 else "GRADIENT"

    # Bright complex footage → dark gradient / scrim.
    if brightness >= 0.66 and complexity >= 0.45:
        if n_chars <= 18 and role_u in ("LABEL", "LOCATION"):
            return "PILL"
        if role_u == "STATISTIC":
            return "PANEL"
        return "GRADIENT" if n_chars >= 24 else "SCRIM"

    # Dark clean background → no plate (shadow only for long lines).
    if brightness <= 0.38 and complexity <= 0.35:
        if importance == "low" and emphasis == "subtle" and n_chars <= 28:
            return "NONE"
        if n_chars <= 22 and role_u not in ("STATISTIC", "CALLOUT", "LOWER_THIRD", "NAME"):
            return "NONE" if role_u != "QUOTE" else "SHADOW"
        return "SHADOW"

    # Low importance on reasonably clean frames → minimal treatment.
    if importance == "low" and emphasis == "subtle" and complexity <= 0.4 and n_chars <= 20:
        if role_u in ("LABEL", "LOCATION", "DATE", "TECHNICAL_LABEL"):
            return "NONE" if brightness <= 0.5 else "SHADOW"

    # Small labels → compact translucent panel / pill.
    if role_u in ("LABEL", "LOCATION", "DATA_LABEL") and n_chars <= 28:
        return "PILL" if complexity >= 0.4 or brightness >= 0.55 else base

    # Long captions → full-width soft overlay.
    if n_chars >= 48 or n_words >= 10:
        return "FULL_WIDTH_OVERLAY" if brightness >= 0.5 else "SCRIM"

    return base


def background_params(
    kind: BackgroundKind,
    *,
    fontsize: int,
    text_w: int,
    text_h: int,
    design: DocumentaryDesignSystem | None = None,
) -> Dict[str, Any]:
    """Pixel-level draw parameters for the chosen background."""
    design = design or get_design_system()
    kind = (kind or "SCRIM").upper()  # type: ignore[assignment]
    pad_x = int(fontsize * design.panel_pad_x_em)
    pad_y = int(fontsize * design.panel_pad_y_em)

    if kind == "NONE":
        return {"kind": kind, "draw": False}
    if kind == "SHADOW":
        return {
            "kind": kind,
            "draw": False,  # shadow is drawn on glyphs, not a plate
            "glyph_shadow": True,
        }
    if kind == "PILL":
        return {
            "kind": kind,
            "draw": True,
            "shape": "rounded",
            "pad_x": max(10, int(pad_x * 0.85)),
            "pad_y": max(6, int(pad_y * 0.75)),
            "radius": int(fontsize * design.pill_radius_em),
            "fill": design.panel_fill,
            "blur": 0,
        }
    if kind == "PANEL":
        return {
            "kind": kind,
            "draw": True,
            "shape": "rounded",
            "pad_x": pad_x + int(fontsize * 0.25),
            "pad_y": pad_y + int(fontsize * 0.15),
            "radius": int(design.corner_radius_px),
            "fill": design.panel_fill_strong,
            "blur": 0,
            "accent_line": True,
        }
    if kind == "LOWER_THIRD":
        return {
            "kind": kind,
            "draw": True,
            "shape": "lower_third",
            "pad_x": pad_x,
            "pad_y": pad_y,
            "radius": 0,
            "fill": design.panel_fill_strong,
            "blur": 0,
            "accent_bar": True,
        }
    if kind == "FULL_WIDTH_OVERLAY":
        return {
            "kind": kind,
            "draw": True,
            "shape": "full_width",
            "pad_x": 0,
            "pad_y": max(pad_y, int(text_h * 0.55)),
            "radius": 0,
            "fill": (0, 0, 0, 150),
            "blur": max(12, int(fontsize * 0.4)),
        }
    if kind == "GRADIENT":
        return {
            "kind": kind,
            "draw": True,
            "shape": "gradient",
            "pad_x": int(text_w * 0.25) + int(fontsize * 0.8),
            "pad_y": int(text_h * 0.9) + int(fontsize * 0.55),
            "radius": 0,
            "fill": (0, 0, 0, 150),
            "blur": max(24, int(fontsize * 0.75)),
        }
    # SCRIM default
    return {
        "kind": "SCRIM",
        "draw": True,
        "shape": "ellipse",
        "pad_x": int(text_w * 0.20) + int(fontsize * 1.0),
        "pad_y": int(text_h * 0.85) + int(fontsize * 0.7),
        "radius": 0,
        "fill": design.scrim_fill,
        "blur": max(28, int(fontsize * 0.85)),
    }


def _frame_brightness(composition: Dict[str, Any]) -> float:
    cells = composition.get("cells") or {}
    if not isinstance(cells, dict) or not cells:
        # Heuristic from avoid list: many bright avoids → bright frame.
        avoid = composition.get("avoid") or ()
        return 0.55 + 0.05 * min(4, len(avoid))
    means = [float(c.get("mean") or 0.5) for c in cells.values() if isinstance(c, dict)]
    if not means:
        return 0.5
    return sum(means) / len(means)


def _frame_complexity(composition: Dict[str, Any]) -> float:
    cells = composition.get("cells") or {}
    if not isinstance(cells, dict) or not cells:
        avoid = composition.get("avoid") or ()
        return min(1.0, 0.3 + 0.12 * len(avoid))
    details = [float(c.get("detail") or 0.0) for c in cells.values() if isinstance(c, dict)]
    if not details:
        return 0.4
    # Normalize roughly into 0–1 using typical saliency magnitudes.
    avg = sum(details) / len(details)
    return max(0.0, min(1.0, avg * 8.0))
