"""Graphics-specific quality control.

Detects unreadable / excessive / inconsistent graphics and auto-fixes
high-confidence problems (usually by dropping or shortening).
"""

from __future__ import annotations

from typing import Any, List

from .design_system import get_design_system
from .schema import GraphicsPlan


def qc_graphics_plan(
    graphics_plan: GraphicsPlan,
    *,
    plan: Any = None,
    memory: Any = None,
) -> List[dict]:
    """Return issue dicts; may mark fixed=True with action drop/shorten."""
    issues: List[dict] = []
    design = get_design_system()
    specs = list(graphics_plan.specs or [])
    if not specs:
        return issues

    ordered = sorted(specs, key=lambda s: float(s.start))

    # Density: prefer dropping low-importance / high-priority-number first
    for i, spec in enumerate(ordered):
        window = [
            s for s in ordered
            if abs(float(s.start) - float(spec.start)) <= 8.0
        ]
        if len(window) > 2:
            ranked = sorted(
                window,
                key=lambda s: (
                    {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                        str(getattr(s, "importance", "medium")), 2
                    ),
                    s.priority,
                    -s.confidence,
                ),
            )
            for extra in ranked[2:]:
                if str(getattr(extra, "importance", "medium")) in ("high", "critical"):
                    continue
                issues.append(
                    {
                        "severity": "WARN",
                        "category": "graphics_density",
                        "graphic_id": extra.graphic_id,
                        "scene_number": extra.scene_number,
                        "message": "Too many graphics in a short period",
                        "fixed": True,
                        "action": "drop",
                    }
                )

    # Memory-aware repetition (if provided)
    if memory is not None:
        seen_keys = set()
        for spec in ordered:
            text = (spec.text.text if spec.text else "") or ""
            key = f"{spec.role}|{text.strip().lower()}"
            if key in seen_keys and str(getattr(spec, "importance", "medium")) == "low":
                issues.append(
                    {
                        "severity": "WARN",
                        "category": "graphics_memory",
                        "graphic_id": spec.graphic_id,
                        "scene_number": spec.scene_number,
                        "message": "Repeated low-importance concept",
                        "fixed": True,
                        "action": "drop",
                    }
                )
            seen_keys.add(key)

    scenes_by_sn = {}
    if plan is not None:
        for sc in getattr(plan, "scenes", None) or []:
            scenes_by_sn[str(sc.scene_number)] = sc

    for spec in ordered:
        dur = float(spec.end) - float(spec.start)
        if dur > design.hold_max + 1.5:
            issues.append(
                {
                    "severity": "WARN",
                    "category": "graphics_duration",
                    "graphic_id": spec.graphic_id,
                    "scene_number": spec.scene_number,
                    "message": f"Graphic lasts too long ({dur:.1f}s)",
                    "fixed": True,
                    "action": "shorten",
                }
            )
            spec.end = round(spec.start + design.hold_max + 0.6, 4)
            if spec.text:
                spec.text.end = spec.end

        sc = scenes_by_sn.get(str(spec.scene_number))
        if sc is not None:
            if float(spec.start) < float(sc.start) - 0.05:
                issues.append(
                    {
                        "severity": "INFO",
                        "category": "graphics_timing",
                        "graphic_id": spec.graphic_id,
                        "scene_number": spec.scene_number,
                        "message": "Graphic starts before scene — clamped",
                        "fixed": True,
                        "action": "clamp",
                    }
                )
                spec.start = float(sc.start)
                if spec.text:
                    spec.text.start = spec.start

        text = (spec.text.text if spec.text else "") or ""
        size_vh = 0.0
        if spec.text and isinstance(spec.text.metadata, dict):
            try:
                size_vh = float(spec.text.metadata.get("size_vh") or 0.0)
            except (TypeError, ValueError):
                size_vh = 0.0
        if size_vh > 0.078 and spec.text is not None:
            issues.append(
                {
                    "severity": "WARN",
                    "category": "graphics_size",
                    "graphic_id": spec.graphic_id,
                    "scene_number": spec.scene_number,
                    "message": f"Text size_vh {size_vh:.3f} exceeds documentary cap — clamped",
                    "fixed": True,
                    "action": "clamp_size",
                }
            )
            spec.text.metadata["size_vh"] = 0.078
        n_chars = len(text.strip())
        if (
            spec.text is not None
            and spec.role not in ("STATISTIC", "CHAPTER", "TITLE")
            and size_vh >= 0.07
            and n_chars >= 12
        ):
            issues.append(
                {
                    "severity": "WARN",
                    "category": "graphics_size",
                    "graphic_id": spec.graphic_id,
                    "scene_number": spec.scene_number,
                    "message": "Informational overlay was oversized — reduced",
                    "fixed": True,
                    "action": "clamp_size",
                }
            )
            spec.text.metadata["size_vh"] = min(size_vh, 0.048)

        if len(text.strip()) < 1:
            issues.append(
                {
                    "severity": "WARN",
                    "category": "graphics_content",
                    "graphic_id": spec.graphic_id,
                    "scene_number": spec.scene_number,
                    "message": "Empty graphic text",
                    "fixed": True,
                    "action": "drop",
                }
            )
            continue

        if spec.role in ("STATISTIC", "LABEL", "LOCATION", "EMPHASIS") and len(text) > 48:
            issues.append(
                {
                    "severity": "WARN",
                    "category": "graphics_content",
                    "graphic_id": spec.graphic_id,
                    "scene_number": spec.scene_number,
                    "message": "Excessive text for graphic role — truncated",
                    "fixed": True,
                    "action": "truncate",
                }
            )
            if spec.text:
                spec.text.text = text[:45].rstrip() + "…"

        if spec.role == "CAPTION" and str(spec.animation).upper() in (
            "SCALE",
            "WORD_EMPHASIS",
            "CHARACTER_REVEAL",
        ):
            issues.append(
                {
                    "severity": "INFO",
                    "category": "graphics_motion",
                    "graphic_id": spec.graphic_id,
                    "scene_number": spec.scene_number,
                    "message": "Softened caption animation to FADE",
                    "fixed": True,
                    "action": "soften_motion",
                }
            )
            spec.animation = "FADE"
            if spec.text:
                spec.text.animation = "FADE"

    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            a, b = ordered[i], ordered[j]
            if a.role != b.role:
                continue
            if a.end <= b.start or b.end <= a.start:
                continue
            if a.scene_number == b.scene_number:
                weaker = a if a.confidence < b.confidence else b
                issues.append(
                    {
                        "severity": "WARN",
                        "category": "graphics_overlap",
                        "graphic_id": weaker.graphic_id,
                        "scene_number": weaker.scene_number,
                        "message": f"Overlapping {a.role} graphics",
                        "fixed": True,
                        "action": "drop",
                    }
                )

    return issues
