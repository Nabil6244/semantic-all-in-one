"""Reusable motion design primitives + simple keyframe easing.

Composable building blocks — not one-off per graphic type.
Maps onto existing FFmpeg overlay motion where possible.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence

from .schema import ANIMATION_TO_OVERLAY, EasingKind, Keyframe


def overlay_animation_name(animation: str) -> str:
    """Map graphics AnimationKind → video_generator overlay motion id."""
    key = str(animation or "FADE").upper()
    return ANIMATION_TO_OVERLAY.get(key, "fade")


def ease(t: float, kind: EasingKind = "ease_out") -> float:
    """t in [0,1] → eased [0,1]."""
    t = max(0.0, min(1.0, float(t)))
    if kind == "linear":
        return t
    if kind == "ease_in":
        return t * t
    if kind == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    # ease_in_out
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0


def sample_keyframes(keyframes: Sequence[Keyframe], t: float) -> float:
    """Interpolate property at time t (seconds from graphic start)."""
    if not keyframes:
        return 0.0
    kfs = sorted(keyframes, key=lambda k: k.t)
    if t <= kfs[0].t:
        return kfs[0].value
    if t >= kfs[-1].t:
        return kfs[-1].value
    for i in range(len(kfs) - 1):
        a, b = kfs[i], kfs[i + 1]
        if a.t <= t <= b.t:
            span = max(1e-6, b.t - a.t)
            u = ease((t - a.t) / span, b.easing)
            return a.value + (b.value - a.value) * u
    return kfs[-1].value


def lifecycle_opacity_keyframes(enter: float, hold: float, exit_s: float) -> List[Keyframe]:
    """Standard ENTER/HOLD/EXIT opacity curve."""
    t_hold = enter
    t_exit = enter + hold
    t_end = enter + hold + exit_s
    return [
        Keyframe(0.0, 0.0, "ease_out"),
        Keyframe(t_hold, 1.0, "ease_out"),
        Keyframe(t_exit, 1.0, "linear"),
        Keyframe(t_end, 0.0, "ease_in"),
    ]


def lifecycle_scale_keyframes(
    enter: float, hold: float, exit_s: float, *, from_scale: float = 0.92
) -> List[Keyframe]:
    t_hold = enter
    t_exit = enter + hold
    t_end = enter + hold + exit_s
    return [
        Keyframe(0.0, from_scale, "ease_out"),
        Keyframe(t_hold, 1.0, "ease_out"),
        Keyframe(t_exit, 1.0, "linear"),
        Keyframe(t_end, 0.98, "ease_in"),
    ]


def count_up_value(
    target: float,
    t: float,
    *,
    enter: float,
    decimals: int = 0,
) -> float:
    """Animate a number from 0 → target over ENTER."""
    if enter <= 0:
        return target
    u = ease(max(0.0, min(1.0, t / enter)), "ease_out")
    val = target * u
    if decimals <= 0:
        return float(math.floor(val + 0.5))
    return round(val, decimals)


# Named primitives (documentation + dispatch keys)
MOTION_PRIMITIVES = frozenset(
    {
        "TEXT_FADE",
        "TEXT_SLIDE",
        "TEXT_SCALE",
        "MASK_REVEAL",
        "LINE_DRAW",
        "BAR_GROW",
        "NUMBER_COUNT",
        "MARKER_POP",
        "MAP_ZOOM",
        "MAP_PAN",
        "ROUTE_DRAW",
        "HIGHLIGHT",
        "PANEL_REVEAL",
        "IMAGE_REVEAL",
        "PROGRESS_FILL",
        "CHART_GROW",
    }
)


def primitives_for_role(role: str) -> Iterable[str]:
    r = (role or "").upper()
    if r == "STATISTIC":
        return ("TEXT_SCALE", "NUMBER_COUNT", "PANEL_REVEAL")
    if r == "LOCATION":
        return ("TEXT_SLIDE", "TEXT_FADE")
    if r in ("LOWER_THIRD", "NAME"):
        return ("TEXT_SLIDE", "PANEL_REVEAL")
    if r == "PROGRESS":
        return ("PROGRESS_FILL", "NUMBER_COUNT", "TEXT_FADE")
    if r == "MAP":
        return ("MAP_ZOOM", "MARKER_POP", "ROUTE_DRAW")
    if r == "PROCESS":
        return ("PANEL_REVEAL", "LINE_DRAW", "TEXT_FADE")
    if r == "CHART":
        return ("CHART_GROW", "NUMBER_COUNT", "TEXT_FADE")
    return ("TEXT_FADE",)
