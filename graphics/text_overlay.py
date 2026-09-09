"""Build professional TextOverlaySpec from Graphics Director directives.

Presentation (where/size/bg/motion/timing) is decided by composition intelligence.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from .composition import CompositionDecision, compose_presentation
from .design_system import DocumentaryDesignSystem, get_design_system
from .director import GraphicDirective
from .schema import GraphicSpec, TextOverlaySpec


def build_text_overlay(
    directive: GraphicDirective,
    *,
    scene_number: str,
    scene_start: float,
    scene_end: float,
    scene_duration: float,
    importance: str = "medium",
    composition: Optional[dict] = None,
    design: DocumentaryDesignSystem | None = None,
    anchor_time: Optional[float] = None,
    narration: str = "",
    footage: Optional[dict] = None,
    intent: Any = None,
    occupied_placements: Optional[Sequence[str]] = None,
) -> GraphicSpec:
    """Materialize a timeline-ready GraphicSpec with TextOverlaySpec."""
    design = design or get_design_system()
    decision = compose_presentation(
        role=directive.role,
        text=(directive.text_hint or "").strip(),
        secondary_text=(directive.secondary_hint or "").strip(),
        scene_start=scene_start,
        scene_end=scene_end,
        scene_duration=scene_duration,
        importance=importance,
        confidence=float(directive.confidence or 0.6),
        decision=str(directive.decision or ""),
        intent=intent,
        composition=composition,
        footage=footage,
        narration=narration or "",
        anchor_time=anchor_time,
        occupied_placements=occupied_placements,
        design=design,
    )
    return _spec_from_decision(
        decision,
        directive=directive,
        scene_number=scene_number,
    )


def apply_composition_to_text(
    text_spec: TextOverlaySpec,
    decision: CompositionDecision,
) -> TextOverlaySpec:
    """Stamp a CompositionDecision onto an existing TextOverlaySpec."""
    text_spec.role = decision.role if decision.role else text_spec.role
    text_spec.start = decision.start
    text_spec.end = decision.end
    text_spec.position_x = decision.position_x
    text_spec.position_y = decision.position_y
    text_spec.scale = decision.scale
    text_spec.font_family = decision.font_family or text_spec.font_family
    text_spec.weight = decision.weight or text_spec.weight
    text_spec.alignment = decision.alignment
    text_spec.tracking_em = decision.tracking_em
    text_spec.background = decision.background
    text_spec.animation = decision.animation
    text_spec.z_index = decision.z_index
    text_spec.placement = decision.placement
    text_spec.style_id = decision.style_id
    text_spec.importance = decision.importance
    text_spec.emphasis = decision.emphasis
    text_spec.semantic_purpose = decision.semantic_purpose
    text_spec.lifecycle = decision.lifecycle
    meta = dict(text_spec.metadata or {})
    meta["size_vh"] = decision.size_vh
    meta["composition_reason"] = decision.reason
    meta["placement_scores"] = dict(decision.scores)
    text_spec.metadata = meta
    return text_spec


def _spec_from_decision(
    decision: CompositionDecision,
    *,
    directive: GraphicDirective,
    scene_number: str,
) -> GraphicSpec:
    role = decision.role
    text_spec = TextOverlaySpec(
        role=role if role else "LABEL",
        text=(directive.text_hint or "").strip(),
        secondary_text=(directive.secondary_hint or "").strip(),
        tertiary_text=(directive.tertiary_hint or "").strip(),
        start=decision.start,
        end=decision.end,
        position_x=decision.position_x,
        position_y=decision.position_y,
        scale=decision.scale,
        opacity=1.0,
        font_family=decision.font_family,
        weight=decision.weight,
        alignment=decision.alignment,
        tracking_em=decision.tracking_em,
        background=decision.background,
        animation=decision.animation,
        z_index=decision.z_index,
        placement=decision.placement,
        style_id=decision.style_id,
        importance=decision.importance,
        emphasis=decision.emphasis,
        semantic_purpose=decision.semantic_purpose,
        lifecycle=decision.lifecycle,
        metadata={
            "decision": directive.decision,
            "reason": directive.reason,
            "size_vh": decision.size_vh,
            "composition_reason": decision.reason,
            "placement_scores": dict(decision.scores),
        },
    )

    track = "TEXT"
    if directive.decision in (
        "MAP", "PROCESS", "CHART", "TIMELINE", "COMPARISON", "PROGRESS", "DOCUMENT"
    ):
        track = "GRAPHICS"

    sfx = ""
    if role == "STATISTIC":
        sfx = "subtle_hit"
    elif directive.decision == "MAP":
        sfx = "ui_tick"

    return GraphicSpec(
        graphic_id=f"gfx_{scene_number}_{role.lower()}",
        decision=directive.decision,
        role=role,
        scene_number=str(scene_number),
        start=decision.start,
        end=decision.end,
        track=track,
        reason=directive.reason,
        confidence=directive.confidence,
        priority=directive.priority,
        importance=decision.importance,
        emphasis=decision.emphasis,
        semantic_purpose=decision.semantic_purpose,
        text=text_spec,
        payload=dict(directive.payload or {}),
        lifecycle=decision.lifecycle,
        animation=decision.animation,
        sfx_action=sfx,
        z_index=decision.z_index,
        underneath="hold",
    )
