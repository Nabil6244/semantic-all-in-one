"""Reusable motion design primitives + simple keyframe easing.

Composable building blocks — not one-off per graphic type.
Maps onto existing FFmpeg overlay motion where possible.
"""

from __future__ import annotations

from typing import Sequence

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
