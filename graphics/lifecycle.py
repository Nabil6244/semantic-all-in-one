"""Graphic lifecycle helpers — ENTER / HOLD / EXIT timing."""

from __future__ import annotations

from .design_system import DocumentaryDesignSystem, get_design_system
from .schema import GraphicLifecycle


def compute_lifecycle(
    *,
    role: str,
    available_s: float,
    importance: str = "medium",
    information_density: float = 0.5,
    design: DocumentaryDesignSystem | None = None,
) -> GraphicLifecycle:
    """Fit ENTER/HOLD/EXIT into available window without lingering."""
    design = design or get_design_system()
    role_u = (role or "").upper()
    enter = design.enter_default
    exit_s = design.exit_default
    if role_u == "STATISTIC":
        enter = design.enter_statistic
        exit_s = design.exit_statistic
    elif role_u in ("LOWER_THIRD", "NAME"):
        enter = design.enter_lower_third
        exit_s = design.exit_lower_third
    elif role_u == "CHAPTER":
        enter = 0.5
        exit_s = 0.4

    avail = max(0.6, float(available_s))
    # Hold scales with importance and inverse density.
    dens = max(0.0, min(1.0, float(information_density)))
    base_hold = {
        "low": 1.4,
        "medium": 2.2,
        "high": 3.0,
        "critical": 3.6,
    }.get(str(importance or "medium").lower(), 2.2)
    hold = base_hold * (1.15 - 0.35 * dens)
    hold = max(design.hold_min, min(design.hold_max, hold))

    total_wanted = enter + hold + exit_s
    if total_wanted > avail:
        # Shrink hold first, then enter/exit proportionally.
        overhead = enter + exit_s
        if overhead >= avail * 0.85:
            scale = (avail * 0.85) / max(0.05, overhead)
            enter *= scale
            exit_s *= scale
            hold = max(0.35, avail - enter - exit_s)
        else:
            hold = max(0.35, avail - overhead)

    return GraphicLifecycle(
        enter_s=round(enter, 3),
        hold_s=round(hold, 3),
        exit_s=round(exit_s, 3),
    )


def clamp_window(
    start: float,
    end: float,
    *,
    scene_start: float,
    scene_end: float,
    lifecycle: GraphicLifecycle | None = None,
) -> tuple[float, float]:
    """Keep graphic inside / near scene, preferring lifecycle total length."""
    s0 = float(scene_start)
    s1 = float(scene_end)
    start = max(s0, float(start))
    end = min(s1, float(end))
    if end <= start:
        end = min(s1, start + 1.2)
    if lifecycle is not None:
        need = lifecycle.total
        if end - start < need * 0.85:
            end = min(s1, start + need)
            if end - start < need * 0.85:
                start = max(s0, end - need)
    return round(start, 4), round(end, 4)
