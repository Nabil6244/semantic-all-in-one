"""Graphics engine — plan specs, materialize onto EditorialTimeline, QC.

Extends the existing timeline; does not create a second architecture.
Presentation intelligence lives in composition.py / memory.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from editorial.timeline import EditorialTimeline, TimelineEvent

from .composition import compose_presentation
from .design_system import DocumentaryDesignSystem, get_design_system
from .director import GraphicDirective, decide_for_scenes
from .lower_third import build_lower_third
from .memory import GraphicsMemory
from .qc import qc_graphics_plan
from .schema import ANIMATION_TO_OVERLAY, GraphicSpec, GraphicsPlan
from .statistic import build_statistic_overlay
from .text_overlay import apply_composition_to_text, build_text_overlay


def plan_graphics(
    plan: Any,
    *,
    intents: Optional[Mapping[str, Any]] = None,
    design: DocumentaryDesignSystem | None = None,
    composition_by_scene: Optional[Mapping[str, dict]] = None,
    footage_by_scene: Optional[Mapping[str, dict]] = None,
) -> GraphicsPlan:
    """Run Graphics Director + composition intelligence across all scenes."""
    design = design or get_design_system()
    scenes = getattr(plan, "scenes", None) or []
    directives_by_scene = decide_for_scenes(scenes, intents=intents, design=design)
    specs: List[GraphicSpec] = []
    memory = GraphicsMemory()
    scene_order: List[str] = []
    occupied: List[str] = []
    comp_map = composition_by_scene or {}
    footage_map = footage_by_scene or {}
    intent_map = intents or {}

    for scene in scenes:
        sn = str(scene.scene_number)
        scene_order.append(sn)
        directives = directives_by_scene.get(sn) or []
        importance = str(getattr(scene, "importance", "medium") or "medium")
        narration = str(getattr(scene, "narration_excerpt", "") or "")
        intent = intent_map.get(sn) or intent_map.get(sn.zfill(3))
        composition = comp_map.get(sn) or comp_map.get(sn.zfill(3)) or {}
        footage = footage_map.get(sn) or {}
        # Infer mild footage hints from editorial scene fields when absent.
        if not footage:
            footage = _footage_hints_from_scene(scene)

        consecutive = memory.consecutive_graphic_scenes(scene_order[:-1])
        for d in directives:
            suppress = memory.should_suppress(
                role=d.role,
                text=d.text_hint or "",
                secondary=d.secondary_hint or "",
                start=float(scene.start),
                importance=importance,
                priority=int(d.priority or 2),
                consecutive_scenes=consecutive,
            )
            if suppress and str(importance).lower() not in ("high", "critical"):
                continue
            if suppress in ("repeated_concept_too_soon",) and str(importance).lower() in (
                "high",
                "critical",
            ):
                continue

            spec = _materialize_directive(
                d,
                scene_number=sn,
                scene_start=float(scene.start),
                scene_end=float(scene.end),
                scene_duration=float(scene.duration),
                importance=importance,
                design=design,
                narration=narration,
                intent=intent,
                composition=composition if isinstance(composition, dict) else None,
                footage=footage,
                occupied_placements=occupied,
            )
            if spec is None or not (spec.text and (spec.text.text or "").strip()):
                continue
            # Memory / density gate after presentation is known
            suppress2 = memory.should_suppress(
                role=spec.role,
                text=spec.text.text,
                secondary=spec.text.secondary_text,
                start=float(spec.start),
                importance=spec.importance,
                priority=int(spec.priority or 2),
                consecutive_scenes=consecutive,
            )
            if suppress2 and spec.importance not in ("high", "critical"):
                continue

            specs.append(spec)
            occupied.append(str(spec.text.placement or ""))
            if len(occupied) > 6:
                del occupied[0]
            memory.record(
                graphic_id=spec.graphic_id,
                role=spec.role,
                text=spec.text.text,
                secondary=spec.text.secondary_text,
                start=float(spec.start),
                importance=spec.importance,
                scene_number=sn,
            )

    gplan = GraphicsPlan(specs=specs, design_system=design.name)
    gplan.qc_issues = qc_graphics_plan(gplan, plan=plan, memory=memory)
    drop_ids = {
        str(issue.get("graphic_id") or "")
        for issue in gplan.qc_issues
        if issue.get("fixed") and issue.get("action") == "drop"
    }
    if drop_ids:
        gplan.specs = [s for s in gplan.specs if s.graphic_id not in drop_ids]
    return gplan


def materialize_graphics_on_timeline(
    timeline: EditorialTimeline,
    graphics_plan: GraphicsPlan,
) -> EditorialTimeline:
    """Add TEXT/GRAPHICS TimelineEvents for each GraphicSpec."""
    for spec in graphics_plan.specs:
        timeline.add(graphic_spec_to_timeline_event(spec))
        if spec.sfx_action:
            timeline.add(
                TimelineEvent(
                    event_id=f"{spec.graphic_id}_sfx",
                    track="SFX",
                    start=float(spec.start),
                    end=round(min(float(spec.end), float(spec.start) + 0.35), 4),
                    scene_number=spec.scene_number,
                    animation=spec.sfx_action,
                    z_index=5,
                    metadata={
                        "kind": "graphic_sfx",
                        "sfx_action": spec.sfx_action,
                        "graphic_id": spec.graphic_id,
                    },
                )
            )
    return timeline


def graphic_spec_to_timeline_event(spec: GraphicSpec) -> TimelineEvent:
    """Encode GraphicSpec into a single TimelineEvent (metadata carries payload)."""
    text = spec.text
    anim = ""
    if text and text.animation:
        anim = ANIMATION_TO_OVERLAY.get(str(text.animation).upper(), "fade")
    elif spec.animation:
        anim = ANIMATION_TO_OVERLAY.get(str(spec.animation).upper(), "fade")

    source = ""
    if text:
        source = text.text
        if text.secondary_text:
            source = f"{text.text} | {text.secondary_text}"

    meta: Dict[str, Any] = {
        "graphic": True,
        "graphic_id": spec.graphic_id,
        "decision": spec.decision,
        "role": spec.role,
        "reason": spec.reason,
        "confidence": spec.confidence,
        "priority": spec.priority,
        "importance": spec.importance,
        "emphasis": spec.emphasis,
        "semantic_purpose": spec.semantic_purpose,
        "payload": dict(spec.payload or {}),
        "lifecycle": spec.lifecycle.to_dict(),
        "sfx_action": spec.sfx_action,
        "underneath": spec.underneath,
        "spec": spec.to_dict(),
    }
    if text:
        meta["text_overlay"] = text.to_dict()
        meta["background"] = text.background
        meta["style_id"] = text.style_id
        meta["placement"] = text.placement

    track = spec.track if spec.track in ("TEXT", "GRAPHICS") else "TEXT"
    return TimelineEvent(
        event_id=spec.graphic_id,
        track=track,  # type: ignore[arg-type]
        start=float(spec.start),
        end=float(spec.end),
        scene_number=spec.scene_number,
        source=source,
        opacity=float(text.opacity) if text else 1.0,
        scale=float(text.scale) if text else 1.0,
        position_x=float(text.position_x) if text else 0.5,
        position_y=float(text.position_y) if text else 0.5,
        rotation=float(text.rotation) if text else 0.0,
        z_index=int(spec.z_index),
        animation=anim,
        transition_in="fade",
        transition_out="fade",
        metadata=meta,
    )


def graphics_from_timeline(timeline: EditorialTimeline | dict | None) -> List[GraphicSpec]:
    """Recover GraphicSpecs from timeline events (for render)."""
    if timeline is None:
        return []
    if isinstance(timeline, dict):
        timeline = EditorialTimeline.from_dict(timeline)
    specs: List[GraphicSpec] = []
    for ev in timeline.events:
        meta = ev.metadata or {}
        if not meta.get("graphic"):
            continue
        raw = meta.get("spec")
        if isinstance(raw, dict):
            specs.append(GraphicSpec.from_dict(raw))
            continue
        from .schema import TextOverlaySpec

        text = None
        if isinstance(meta.get("text_overlay"), dict):
            text = TextOverlaySpec.from_dict(meta["text_overlay"])
        elif ev.source:
            parts = str(ev.source).split("|")
            text = TextOverlaySpec(
                role=str(meta.get("role") or "LABEL"),
                text=parts[0].strip(),
                secondary_text=parts[1].strip() if len(parts) > 1 else "",
                start=float(ev.start),
                end=float(ev.end),
                position_x=float(ev.position_x),
                position_y=float(ev.position_y),
            )
        specs.append(
            GraphicSpec(
                graphic_id=ev.event_id,
                decision=str(meta.get("decision") or "TEXT"),
                role=str(meta.get("role") or "LABEL"),
                scene_number=ev.scene_number,
                start=float(ev.start),
                end=float(ev.end),
                track=ev.track,
                reason=str(meta.get("reason") or ""),
                confidence=float(meta.get("confidence") or 0.5),
                importance=str(meta.get("importance") or "medium"),
                emphasis=str(meta.get("emphasis") or "normal"),
                semantic_purpose=str(meta.get("semantic_purpose") or "identify"),
                text=text,
                payload=dict(meta.get("payload") or {}),
                animation="FADE",
                z_index=int(ev.z_index),
            )
        )
    return specs


def attach_graphics_plan(plan: Any, graphics_plan: GraphicsPlan) -> None:
    setattr(plan, "graphics_plan", graphics_plan.to_dict())


def _footage_hints_from_scene(scene: Any) -> dict:
    camera = str(getattr(scene, "camera_style", "") or "").lower()
    pacing = str(getattr(scene, "pacing_bias", "") or "").lower()
    motion = 0.4
    if camera in ("static", "hold"):
        motion = 0.15
    elif camera in ("subtle_drift",):
        motion = 0.3
    elif camera in ("push_in", "pull_out"):
        motion = 0.55
    if pacing == "fast":
        motion = max(motion, 0.7)
    elif pacing == "slow":
        motion = min(motion, 0.25)
    return {
        "motion_level": motion,
        "stable": motion < 0.28,
        "camera_style": camera,
        "pacing_bias": pacing,
    }


def _materialize_directive(
    d: GraphicDirective,
    *,
    scene_number: str,
    scene_start: float,
    scene_end: float,
    scene_duration: float,
    importance: str,
    design: DocumentaryDesignSystem,
    narration: str = "",
    intent: Any = None,
    composition: Optional[dict] = None,
    footage: Optional[dict] = None,
    occupied_placements: Optional[Sequence[str]] = None,
) -> Optional[GraphicSpec]:
    common = dict(
        scene_number=scene_number,
        scene_start=scene_start,
        scene_end=scene_end,
        scene_duration=scene_duration,
        importance=importance,
        design=design,
        narration=narration,
        intent=intent,
        composition=composition,
        footage=footage,
        occupied_placements=occupied_placements,
    )

    if d.decision in ("MAP", "PROCESS", "CHART", "TIMELINE", "COMPARISON", "PROGRESS", "DOCUMENT"):
        if not (d.text_hint or "").strip():
            return None
        spec = build_text_overlay(
            GraphicDirective(
                decision="TEXT" if d.decision != "PROGRESS" else "PROGRESS",
                role="LABEL" if d.decision != "PROGRESS" else "CALLOUT",
                reason=d.reason + " (text fallback until dedicated renderer)",
                confidence=d.confidence * 0.9,
                priority=min(d.priority, 4),
                text_hint=d.text_hint,
                secondary_hint=d.secondary_hint,
                payload=d.payload,
            ),
            **common,
        )
        spec.decision = d.decision
        spec.role = d.role
        spec.payload = dict(d.payload or {})
        spec.payload["pending_renderer"] = d.decision
        return spec

    if d.decision == "STATISTIC" or d.role == "STATISTIC":
        base = build_text_overlay(d, **common)
        decision = compose_presentation(
            role="STATISTIC",
            text=d.text_hint or "",
            secondary_text=d.secondary_hint or "",
            scene_start=scene_start,
            scene_end=scene_end,
            scene_duration=scene_duration,
            importance=importance,
            confidence=float(d.confidence or 0.6),
            decision="STATISTIC",
            intent=intent,
            composition=composition,
            footage=footage,
            narration=narration,
            occupied_placements=occupied_placements,
            design=design,
        )
        stat = build_statistic_overlay(
            display=d.text_hint,
            label=d.secondary_hint,
            value=(d.payload or {}).get("value"),
            unit=str((d.payload or {}).get("unit") or ""),
            start=decision.start,
            end=decision.end,
            lifecycle=decision.lifecycle,
            design=design,
        )
        base.text = apply_composition_to_text(stat, decision)
        base.start = decision.start
        base.end = decision.end
        base.lifecycle = decision.lifecycle
        base.animation = decision.animation
        base.importance = decision.importance
        base.emphasis = decision.emphasis
        base.semantic_purpose = decision.semantic_purpose
        base.z_index = decision.z_index
        return base

    if d.decision == "LOWER_THIRD" or d.role in (
        "LOWER_THIRD", "NAME", "CALLOUT", "EMPHASIS", "LABEL"
    ):
        base = build_text_overlay(d, **common)
        primary = d.text_hint
        secondary = d.secondary_hint
        if d.role in ("CALLOUT", "EMPHASIS", "LABEL") and not secondary:
            words = (primary or "").split()
            if len(words) >= 4:
                primary = " ".join(words[:2])
                secondary = " ".join(words[2:8])
        decision = compose_presentation(
            role="LOWER_THIRD" if d.role in ("CALLOUT", "EMPHASIS", "LABEL") else d.role,
            text=primary or "",
            secondary_text=secondary or "",
            scene_start=scene_start,
            scene_end=scene_end,
            scene_duration=scene_duration,
            importance=importance,
            confidence=float(d.confidence or 0.6),
            decision="LOWER_THIRD",
            intent=intent,
            composition=composition,
            footage=footage,
            narration=narration,
            occupied_placements=occupied_placements,
            design=design,
        )
        lt = build_lower_third(
            name=primary or "",
            title=secondary or "",
            start=decision.start,
            end=decision.end,
            lifecycle=decision.lifecycle,
            design=design,
        )
        base.text = apply_composition_to_text(lt, decision)
        base.role = d.role if d.role in ("LOWER_THIRD", "NAME") else "LOWER_THIRD"
        base.decision = "LOWER_THIRD" if d.decision in ("TEXT", "CALLOUT") else d.decision
        base.start = decision.start
        base.end = decision.end
        base.lifecycle = decision.lifecycle
        base.animation = decision.animation
        base.importance = decision.importance
        base.emphasis = decision.emphasis
        base.semantic_purpose = decision.semantic_purpose
        base.z_index = decision.z_index
        return base

    return build_text_overlay(d, **common)
