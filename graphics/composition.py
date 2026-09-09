"""Deterministic composition intelligence for text graphics.

AI/Director decides WHAT/WHY. This module decides HOW:
style, placement, size, background, animation, timing.

Uses frame composition cells when available; falls back to role heuristics.
Same inputs → same outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .backgrounds import choose_background
from .design_system import DocumentaryDesignSystem, get_design_system
from .lifecycle import clamp_window, compute_lifecycle
from .schema import AnimationKind, BackgroundKind, GraphicLifecycle
from .semantics import infer_semantics, normalize_role

# 3×3 documentary placement candidates
PLACEMENT_CANDIDATES: Tuple[str, ...] = (
    "top_left",
    "top_center",
    "top_right",
    "center_left",
    "center",
    "center_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
)

_ANCHORS: Dict[str, Tuple[float, float]] = {
    "top_left": (0.22, 0.16),
    "top_center": (0.50, 0.14),
    "top_right": (0.78, 0.16),
    "center_left": (0.24, 0.46),
    "center": (0.50, 0.44),
    "center_right": (0.76, 0.46),
    "bottom_left": (0.24, 0.78),
    "bottom_center": (0.50, 0.76),
    "bottom_right": (0.76, 0.78),
}

# Soft documentary bias — lower band preferred, not forced.
_ROLE_PLACEMENT_BIAS: Dict[str, Tuple[str, ...]] = {
    "LOWER_THIRD": ("bottom_left", "bottom_center"),
    "NAME": ("bottom_left", "bottom_center"),
    "LOCATION": ("bottom_left", "top_left", "bottom_center"),
    "STATISTIC": ("bottom_right", "top_right", "bottom_center"),
    "DATE": ("bottom_left", "top_left", "bottom_center"),
    "CHAPTER": ("bottom_center", "center"),
    "QUOTE": ("bottom_center", "bottom_left"),
    "EMPHASIS": ("bottom_center", "bottom_right"),
    "CALLOUT": ("bottom_center", "bottom_left"),
    "TECHNICAL_LABEL": ("bottom_right", "top_right", "bottom_left"),
    "ANNOTATION": ("bottom_right", "top_right"),
    "CAPTION": ("bottom_center",),
    "TITLE": ("bottom_center", "center"),
    "LABEL": ("bottom_left", "bottom_center"),
}

# Occupied-area + font-size hard limits (fractions of the frame).
# High importance may climb the hierarchy but never exceeds these caps.
_MIN_SIZE_VH = 0.026
_MAX_SIZE_VH = 0.078  # strongest role, still documentary-capped
_MAX_BLOCK_HEIGHT_RATIO = 0.16
_MAX_BLOCK_WIDTH_RATIO = 0.52
_MAX_LINES_DEFAULT = 3
_MAX_LINES_BY_ROLE = {
    "STATISTIC": 2,
    "CHAPTER": 2,
    "TITLE": 2,
    "QUOTE": 3,
    "LOWER_THIRD": 2,
    "NAME": 2,
    "LOCATION": 2,
    "DATE": 1,
    "TECHNICAL_LABEL": 2,
    "ANNOTATION": 2,
    "CAPTION": 2,
    "EMPHASIS": 3,
    "CALLOUT": 3,
    "LABEL": 2,
}

# Role → hard maximum line size (vh). Importance cannot raise these.
_ROLE_MAX_VH = {
    "TECHNICAL_LABEL": 0.036,
    "ANNOTATION": 0.036,
    "LOCATION": 0.038,
    "DATE": 0.036,
    "CAPTION": 0.036,
    "DATA_LABEL": 0.038,
    "LABEL": 0.040,
    "LOWER_THIRD": 0.042,
    "NAME": 0.042,
    "CALLOUT": 0.046,
    "EMPHASIS": 0.048,
    "QUOTE": 0.050,
    "EVIDENCE": 0.048,
    "COMPARISON": 0.048,
    "TITLE": 0.062,
    "CHAPTER": 0.068,
    "STATISTIC": 0.078,
}

# Role → floor so type stays readable at 1080p (~28px at 0.026).
_ROLE_MIN_VH = {
    "STATISTIC": 0.052,
    "CHAPTER": 0.046,
    "TITLE": 0.044,
    "EMPHASIS": 0.034,
    "CALLOUT": 0.034,
}


@dataclass
class CompositionDecision:
    """Final presentation decision for one text graphic."""

    role: str
    importance: str
    emphasis: str
    semantic_purpose: str
    style_id: str
    placement: str
    position_x: float
    position_y: float
    alignment: str
    size_vh: float
    scale: float
    background: BackgroundKind
    animation: AnimationKind
    lifecycle: GraphicLifecycle
    start: float
    end: float
    font_family: str
    weight: str
    tracking_em: float
    z_index: int
    needs_strong_bg: bool = False
    scores: Dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "importance": self.importance,
            "emphasis": self.emphasis,
            "semantic_purpose": self.semantic_purpose,
            "style_id": self.style_id,
            "placement": self.placement,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "alignment": self.alignment,
            "size_vh": self.size_vh,
            "scale": self.scale,
            "background": self.background,
            "animation": self.animation,
            "lifecycle": self.lifecycle.to_dict(),
            "start": self.start,
            "end": self.end,
            "font_family": self.font_family,
            "weight": self.weight,
            "tracking_em": self.tracking_em,
            "z_index": self.z_index,
            "needs_strong_bg": self.needs_strong_bg,
            "scores": dict(self.scores),
            "reason": self.reason,
        }


def select_style_id(
    *,
    role: str,
    importance: str = "medium",
    emphasis: str = "normal",
) -> str:
    """Deterministic style id within the existing typography vocabulary."""
    role_u = normalize_role(role)
    if role_u == "STATISTIC":
        return "fact_number"
    if role_u in ("LOWER_THIRD", "NAME"):
        return "minimal_caption"
    if role_u == "LOCATION":
        return "minimal_caption"
    if role_u == "CHAPTER":
        return "statement"
    if role_u == "QUOTE":
        return "quote"
    if role_u == "DATE":
        return "minimal_caption"
    if role_u in ("TECHNICAL_LABEL", "ANNOTATION", "LABEL", "DATA_LABEL"):
        return "minimal_caption"
    if role_u == "CAPTION":
        return "minimal_caption"
    if role_u in ("EMPHASIS", "CALLOUT"):
        if emphasis in ("strong", "dramatic") or importance in ("high", "critical"):
            return "keyword_highlight"
        return "keyword_highlight"
    if role_u == "TITLE":
        return "statement"
    if role_u == "EVIDENCE":
        return "keyword_highlight"
    if role_u == "COMPARISON":
        return "statement"
    return "keyword_highlight"


def max_lines_for_role(role: str) -> int:
    return int(_MAX_LINES_BY_ROLE.get(normalize_role(role), _MAX_LINES_DEFAULT))


def estimate_wrapped_lines(text: str, size_vh: float, *, max_lines: int = 3) -> int:
    """Estimate wrap count from size + documentary max width (16:9 assumed)."""
    raw = " ".join((text or "").split())
    if not raw:
        return 1
    size_vh = max(_MIN_SIZE_VH, float(size_vh) or _MIN_SIZE_VH)
    # char width ≈ 0.55em; max block width is a fraction of frame width.
    chars_per_line = max(10, int(_MAX_BLOCK_WIDTH_RATIO * 1.778 / (0.55 * size_vh)))
    n = max(1, (len(raw) + chars_per_line - 1) // chars_per_line)
    n_words = max(1, len(raw.split()))
    n = min(n, n_words, max(1, max_lines))
    return n


def occupied_block_ratios(
    text: str,
    size_vh: float,
    *,
    n_lines: int | None = None,
    has_secondary: bool = False,
) -> Tuple[float, float]:
    """Approximate (width_ratio, height_ratio) of the rendered text block."""
    raw = " ".join((text or "").split())
    lines = n_lines or estimate_wrapped_lines(raw, size_vh)
    longest = max((len(p) for p in raw.split()), default=1) if raw else 1
    if lines > 1 and raw:
        chars_per_line = max(1, (len(raw) + lines - 1) // lines)
        longest = min(len(raw), max(chars_per_line, longest))
    width_ratio = min(0.95, longest * 0.55 * float(size_vh) / 1.778 + 0.04)
    height_ratio = float(size_vh) * (1.22 * lines + (0.45 if has_secondary else 0.0)) + 0.02
    return round(width_ratio, 4), round(height_ratio, 4)


def compute_size_vh(
    *,
    role: str,
    text: str,
    importance: str = "medium",
    emphasis: str = "normal",
    available_region_score: float = 0.5,
    design: DocumentaryDesignSystem | None = None,
    display_duration: float = 2.5,
    visual_complexity: float = 0.4,
    n_lines: int | None = None,
    graphic_type: str = "",
    has_secondary: bool = False,
) -> float:
    """Restrained documentary size. Importance changes hierarchy, not the cap."""
    design = design or get_design_system()
    role_u = normalize_role(role)
    gtype = str(graphic_type or role_u).upper()
    base = float(design.size_vh_for(role_u))
    n_chars = len((text or "").strip())
    n_words = len((text or "").split())
    max_lines = max_lines_for_role(role_u)

    # Hierarchy only — small steps. Never a license to go huge.
    imp_mul = {"low": 0.94, "medium": 1.0, "high": 1.06, "critical": 1.10}.get(
        importance, 1.0
    )
    emp_mul = {"subtle": 0.96, "normal": 1.0, "strong": 1.04, "dramatic": 1.06}.get(
        emphasis, 1.0
    )

    if n_chars >= 56 or n_words >= 12:
        length_mul = 0.78
    elif n_chars >= 36 or n_words >= 8:
        length_mul = 0.86
    elif n_chars >= 22 or n_words >= 5:
        length_mul = 0.93
    elif n_chars <= 6 and role_u == "STATISTIC":
        length_mul = 1.08
    elif n_chars <= 10 and role_u in ("STATISTIC", "CHAPTER", "TITLE"):
        length_mul = 1.04
    else:
        length_mul = 1.0

    # Tight / busy regions shrink; they must not inflate size.
    region = max(0.0, min(1.0, available_region_score))
    region_mul = 0.92 + 0.08 * region

    dur = max(0.0, float(display_duration or 0.0))
    if dur and dur < 1.3:
        dur_mul = 0.94
    elif dur > 4.0:
        dur_mul = 1.03
    else:
        dur_mul = 1.0

    complexity = max(0.0, min(1.0, float(visual_complexity or 0.0)))
    cx_mul = 0.92 if complexity >= 0.7 else (0.96 if complexity >= 0.5 else 1.0)

    if gtype in ("LOWER_THIRD", "NAME") or role_u in ("LOWER_THIRD", "NAME"):
        type_mul = 0.98
    elif gtype == "STATISTIC" or role_u == "STATISTIC":
        type_mul = 1.0
    else:
        type_mul = 1.0

    size = base * imp_mul * emp_mul * length_mul * region_mul * dur_mul * cx_mul * type_mul

    role_max = float(_ROLE_MAX_VH.get(role_u, 0.048))
    role_min = float(_ROLE_MIN_VH.get(role_u, _MIN_SIZE_VH))
    size = min(size, role_max, _MAX_SIZE_VH)
    size = max(size, role_min, _MIN_SIZE_VH)

    lines = n_lines or estimate_wrapped_lines(text, size, max_lines=max_lines)
    if lines > max_lines:
        size *= max_lines / float(lines)
        lines = max_lines
    width_r, height_r = occupied_block_ratios(
        text, size, n_lines=lines, has_secondary=has_secondary
    )
    if height_r > _MAX_BLOCK_HEIGHT_RATIO and height_r > 0:
        size *= _MAX_BLOCK_HEIGHT_RATIO / height_r
    if width_r > _MAX_BLOCK_WIDTH_RATIO and width_r > 0:
        size *= _MAX_BLOCK_WIDTH_RATIO / width_r

    size = min(size, role_max, _MAX_SIZE_VH)
    size = max(size, min(role_min, role_max), _MIN_SIZE_VH)
    return round(size, 4)


def score_placements(
    *,
    role: str,
    text: str,
    composition: Optional[Dict[str, Any]] = None,
    importance: str = "medium",
    occupied: Optional[Sequence[str]] = None,
) -> Dict[str, float]:
    """Score each 3×3 cell. Higher is better."""
    role_u = normalize_role(role)
    composition = composition or {}
    cells = composition.get("cells") if isinstance(composition.get("cells"), dict) else {}
    avoid = set(composition.get("avoid") or ())
    if isinstance(composition.get("avoid"), str):
        avoid = {composition["avoid"]}
    occupied_set = set(occupied or ())
    n_chars = len((text or "").strip())
    scores: Dict[str, float] = {}

    bias = _ROLE_PLACEMENT_BIAS.get(role_u, ("bottom_center", "bottom_left"))

    for name in PLACEMENT_CANDIDATES:
        score = 50.0
        # Soft documentary lower-band preference (not a hard lock).
        if name.startswith("bottom"):
            score += 12.0
        elif name == "center":
            score -= 8.0 if role_u not in ("CHAPTER", "TITLE") else 2.0
        else:  # top
            score += 2.0 if role_u in ("LOCATION", "DATE", "STATISTIC", "ANNOTATION") else -6.0

        if name in bias:
            score += 18.0 - 4.0 * list(bias).index(name)

        # Frame cell quality
        cell = cells.get(name) if isinstance(cells, dict) else None
        if isinstance(cell, dict):
            detail = float(cell.get("detail") or 0.0)
            mean = float(cell.get("mean") or 0.5)
            textlike = float(cell.get("textlike") or 0.0)
            variance = float(cell.get("variance") or 0.0)
            # Prefer quiet, not blown-out, not text-like.
            score += max(-25.0, 18.0 - detail * 80.0)
            score += max(-12.0, 8.0 - max(0.0, mean - 0.6) * 30.0)
            score -= textlike * 40.0
            score -= variance * 10.0
        elif name in avoid:
            score -= 30.0

        if name in avoid:
            score -= 20.0
        if name in occupied_set:
            score -= 35.0

        # Long text prefers wider center-bottom.
        if n_chars >= 36 and name.endswith(("_left", "_right")):
            score -= 10.0
        if n_chars >= 36 and name == "bottom_center":
            score += 8.0

        # Lower-thirds strongly prefer left lower.
        if role_u in ("LOWER_THIRD", "NAME") and name == "bottom_left":
            score += 14.0
        if role_u in ("LOWER_THIRD", "NAME") and name.startswith("top"):
            score -= 20.0

        # Never put long callouts dead-center over action unless nowhere else.
        if role_u in ("CALLOUT", "EMPHASIS", "CAPTION") and name == "center":
            score -= 15.0

        scores[name] = round(score, 3)

    # Prefer analyser fallback as a bonus target when present.
    fallback = str(composition.get("fallback") or composition.get("prefer") or "")
    if fallback in scores:
        scores[fallback] = round(scores[fallback] + 10.0, 3)

    return scores


def select_placement(
    *,
    role: str,
    text: str,
    composition: Optional[Dict[str, Any]] = None,
    importance: str = "medium",
    occupied: Optional[Sequence[str]] = None,
) -> Tuple[str, float, float, str, Dict[str, float], bool]:
    """Return placement, x, y, alignment, scores, needs_strong_bg."""
    scores = score_placements(
        role=role,
        text=text,
        composition=composition,
        importance=importance,
        occupied=occupied,
    )
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best_name, best_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else best_score

    # If best is still poor, keep it but signal stronger background.
    needs_strong_bg = best_score < 35.0 or (best_score - second) < 2.0 and best_name in (
        set((composition or {}).get("avoid") or ())
    )

    ax, ay = _ANCHORS.get(best_name, (0.5, 0.76))
    if best_name.endswith("left"):
        align = "left"
    elif best_name.endswith("right"):
        align = "right"
    else:
        align = "center"

    # Safe-area clamp
    ax = max(0.12, min(0.88, ax))
    ay = max(0.12, min(0.86, ay))
    return best_name, ax, ay, align, scores, needs_strong_bg


def _footage_busy(
    footage: Optional[Dict[str, Any]] = None,
    composition: Optional[Dict[str, Any]] = None,
) -> float:
    """0–1 how visually busy the underlying shot is."""
    footage = footage or {}
    motion = float(footage.get("motion_level") or footage.get("camera_speed") or 0.4)
    complexity = float(footage.get("visual_complexity") or 0.0)
    detail = 0.0
    cells = (composition or {}).get("cells") if isinstance(composition, dict) else None
    if isinstance(cells, dict) and cells:
        vals = [
            float(c.get("detail") or 0.0)
            for c in cells.values()
            if isinstance(c, dict)
        ]
        if vals:
            detail = sum(vals) / len(vals)
    return max(0.0, min(1.0, max(motion, complexity, detail * 2.5)))


def _footage_steals_reveal(
    footage: Optional[Dict[str, Any]] = None,
    intent: Any = None,
) -> bool:
    footage = footage or {}
    if footage.get("reveal") or footage.get("major_reveal"):
        return True
    if intent is not None and bool(getattr(intent, "reveal", False)):
        phase = str(getattr(intent, "reveal_phase", "") or "")
        return phase in ("reveal", "emphasize", "")
    phase = str(footage.get("reveal_phase") or "")
    return phase in ("reveal", "emphasize")


def select_animation(
    *,
    role: str,
    emphasis: str = "normal",
    purpose: str = "identify",
    footage: Optional[Dict[str, Any]] = None,
    composition: Optional[Dict[str, Any]] = None,
    duration: float = 2.0,
    intent: Any = None,
) -> AnimationKind:
    """Small documentary vocabulary. Animation is optional.

    CLEAN_FADE         → FADE
    SUBTLE_SLIDE       → SLIDE
    REVEAL             → MASK_REVEAL
    STATISTIC_REVEAL   → MASK_REVEAL
    LOWER_THIRD_REVEAL → SLIDE
    CHAPTER_REVEAL     → MASK_REVEAL
    """
    role_u = normalize_role(role)
    footage = footage or {}
    motion = float(footage.get("motion_level") or footage.get("camera_speed") or 0.4)
    busy = _footage_busy(footage, composition)
    steal = _footage_steals_reveal(footage, intent)
    short = duration < 1.15

    if role_u == "STATISTIC":
        anim: AnimationKind = "MASK_REVEAL"
    elif role_u in ("LOWER_THIRD", "NAME"):
        anim = "SLIDE"
    elif role_u == "LOCATION":
        anim = "SLIDE"
    elif role_u in ("CHAPTER", "TITLE"):
        anim = "MASK_REVEAL"
    elif role_u in ("TECHNICAL_LABEL", "ANNOTATION", "CAPTION", "LABEL"):
        anim = "FADE"
    elif purpose == "reveal" or role_u == "REVEAL":
        anim = "MASK_REVEAL"
    elif emphasis in ("strong", "dramatic") and purpose in ("emphasize", "reveal"):
        anim = "MASK_REVEAL"
    else:
        anim = "FADE"

    # Footage remains the hero. Busy / fast / steal → simpler fade.
    if steal and role_u not in ("STATISTIC", "CHAPTER", "LOWER_THIRD", "NAME"):
        anim = "FADE"
    if (motion >= 0.55 or busy >= 0.6 or short) and anim == "MASK_REVEAL":
        if role_u not in ("STATISTIC", "CHAPTER"):
            anim = "FADE"
    if motion >= 0.7 and anim == "SLIDE" and role_u not in ("LOWER_THIRD", "NAME"):
        anim = "FADE"
    return anim


def select_timing(
    *,
    role: str,
    scene_start: float,
    scene_end: float,
    scene_duration: float,
    importance: str = "medium",
    text: str = "",
    narration: str = "",
    anchor_time: Optional[float] = None,
    design: DocumentaryDesignSystem | None = None,
) -> Tuple[float, float, GraphicLifecycle]:
    """Align enter with semantic emphasis when possible; never fill whole scene."""
    design = design or get_design_system()
    role_u = normalize_role(role)
    dens = min(1.0, len((text or "").split()) / 8.0)

    if anchor_time is not None:
        start = float(anchor_time)
    else:
        start = _default_start(
            role_u, scene_start, scene_duration, text=text, narration=narration
        )

    lifecycle = compute_lifecycle(
        role=role_u,
        available_s=max(0.8, scene_end - start),
        importance=importance,
        information_density=dens,
        design=design,
    )
    # Fast footage / low importance → shorter hold.
    if importance == "low":
        lifecycle.hold_s = min(lifecycle.hold_s, 1.6)
    end = start + lifecycle.total
    start, end = clamp_window(
        start, end, scene_start=scene_start, scene_end=scene_end, lifecycle=lifecycle
    )
    return start, end, lifecycle


def _default_start(
    role: str,
    scene_start: float,
    scene_duration: float,
    *,
    text: str = "",
    narration: str = "",
) -> float:
    # Try to align statistic/name with its first occurrence in narration.
    needle = (text or "").strip()
    narr = narration or ""
    if needle and narr:
        idx = narr.lower().find(needle.lower().lstrip("+").split()[0][:12].lower())
        if idx >= 0 and len(narr) > 0:
            frac = idx / max(1, len(narr))
            # Appear slightly before the spoken emphasis.
            t = scene_start + scene_duration * max(0.08, min(0.75, frac * 0.85))
            return t

    mid = scene_start + scene_duration * 0.42
    if role in ("LOCATION", "LABEL", "DATE", "CHAPTER"):
        return scene_start + min(0.25, scene_duration * 0.12)
    if role in ("LOWER_THIRD", "NAME"):
        return scene_start + min(0.35, scene_duration * 0.15)
    if role == "STATISTIC":
        return max(scene_start + 0.2, mid - 0.2)
    if role in ("TECHNICAL_LABEL", "ANNOTATION"):
        return scene_start + min(0.4, scene_duration * 0.2)
    return mid - 0.15


def compose_presentation(
    *,
    role: str,
    text: str,
    secondary_text: str = "",
    scene_start: float,
    scene_end: float,
    scene_duration: float,
    importance: Any = None,
    emphasis: Any = None,
    purpose: Any = None,
    confidence: float = 0.6,
    decision: str = "",
    intent: Any = None,
    composition: Optional[Dict[str, Any]] = None,
    footage: Optional[Dict[str, Any]] = None,
    narration: str = "",
    anchor_time: Optional[float] = None,
    occupied_placements: Optional[Sequence[str]] = None,
    design: DocumentaryDesignSystem | None = None,
) -> CompositionDecision:
    """Single deterministic presentation decision for one graphic."""
    design = design or get_design_system()
    role_u, imp, emp, purp = infer_semantics(
        role=role,
        importance=importance,
        emphasis=emphasis,
        purpose=purpose,
        confidence=confidence,
        decision=decision,
        intent=intent,
    )
    style_id = select_style_id(role=role_u, importance=imp, emphasis=emp)
    placement, px, py, align, scores, needs_bg = select_placement(
        role=role_u,
        text=text,
        composition=composition,
        importance=imp,
        occupied=occupied_placements,
    )
    start, end, lifecycle = select_timing(
        role=role_u,
        scene_start=scene_start,
        scene_end=scene_end,
        scene_duration=scene_duration,
        importance=imp,
        text=text,
        narration=narration,
        anchor_time=anchor_time,
        design=design,
    )
    anim = select_animation(
        role=role_u,
        emphasis=emp,
        purpose=purp,
        footage=footage,
        composition=composition,
        duration=max(0.4, end - start),
        intent=intent,
    )
    # Footage-aware lifecycle speed
    motion = float((footage or {}).get("motion_level") or 0.4)
    if motion >= 0.7:
        lifecycle.enter_s = max(0.18, lifecycle.enter_s * 0.75)
        lifecycle.exit_s = max(0.15, lifecycle.exit_s * 0.75)
        lifecycle.hold_s = max(0.9, lifecycle.hold_s * 0.85)
        end = min(scene_end, start + lifecycle.total)
    elif motion <= 0.25:
        lifecycle.enter_s = min(0.55, lifecycle.enter_s * 1.15)

    region_score = max(0.0, min(1.0, (scores.get(placement, 50.0) + 20.0) / 100.0))
    complexity = float(
        (footage or {}).get("visual_complexity")
        or (composition or {}).get("detail")
        or motion
        or 0.4
    )
    size_vh = compute_size_vh(
        role=role_u,
        text=text or secondary_text,
        importance=imp,
        emphasis=emp,
        available_region_score=region_score,
        design=design,
        display_duration=max(0.4, end - start),
        visual_complexity=complexity,
        has_secondary=bool((secondary_text or "").strip()),
        graphic_type=str(decision or role_u),
    )
    bg = choose_background(
        role=role_u,
        text=text,
        composition=composition,
        importance=imp,
        over_face=needs_bg or placement in set((composition or {}).get("avoid") or ()),
        emphasis=emp,
        design=design,
    )
    if needs_bg and bg in ("NONE", "SHADOW"):
        bg = "SCRIM" if len(text or "") < 28 else "PANEL"
    if role_u in ("LOWER_THIRD", "NAME"):
        bg = "LOWER_THIRD"

    font_family, weight = design.font_for(role_u)
    tracking = 0.02 if role_u == "STATISTIC" else (0.01 if role_u == "CHAPTER" else 0.0)
    z = 70 if role_u == "STATISTIC" or imp in ("high", "critical") else 60
    # Scale is a layout token, not a second size multiplier.
    scale = 1.0

    reason = (
        f"{role_u}/{purp} → {style_id} @ {placement} "
        f"size={size_vh:.3f} bg={bg} anim={anim}"
    )
    return CompositionDecision(
        role=role_u,
        importance=imp,
        emphasis=emp,
        semantic_purpose=purp,
        style_id=style_id,
        placement=placement,
        position_x=px,
        position_y=py,
        alignment=align,
        size_vh=size_vh,
        scale=scale,
        background=bg,
        animation=anim,
        lifecycle=lifecycle,
        start=start,
        end=end,
        font_family=font_family,
        weight=weight,
        tracking_em=tracking,
        z_index=z,
        needs_strong_bg=needs_bg,
        scores=scores,
        reason=reason,
    )
