"""Pure-geometry arrow-route + label-position SOLVING — no Pillow, no
FFmpeg, no per-frame rendering.

Performance contract (see scene_graph/layout.py's compute_layout): every
function here that searches over candidates is called EXACTLY ONCE per
edge, at layout/planning time, and the result is cached onto
SceneGraphLayout. scene_graph.composition then only ever SAMPLES the
already-chosen shape into pixels — once per frame, cheaply, with no
searching. Nothing in this module is safe to call per video frame; nothing
in composition.py's per-frame path calls it.

Shared by scene_graph.layout (solves) and scene_graph.composition (draws)
without a circular import: this module depends on nothing project-specific.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from typing import List, Sequence, Tuple

Point = Tuple[float, float]


@dataclasses.dataclass(frozen=True)
class ObstacleRect:
    """An axis-aligned keep-out zone — a card's rect (already expanded by
    its own caption/label margins) or a coarse bounding box around an
    already-solved arrow, so later edges softly avoid crossing earlier
    ones too."""

    x0: float
    y0: float
    x1: float
    y1: float


def rect_obstacle(x: float, y: float, x2: float, y2: float, *, margin: float = 0.0) -> ObstacleRect:
    return ObstacleRect(x - margin, y - margin, x2 + margin, y2 + margin)


def _bezier_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    mt = 1.0 - t
    x = mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0]
    y = mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1]
    return (x, y)


def bow_curve(x0: float, y0: float, x1: float, y1: float, *, bulge_px: float, side: int, samples: int = 24) -> List[Point]:
    """A clean (no hand-drawn jitter) cubic-bezier from (x0,y0) to (x1,y1),
    bowed ``bulge_px`` along the perpendicular normal (``side`` = +1/-1) —
    one candidate "shape" in the small deterministic family solve_edge_route
    picks from. Jitter is layered on top of the CHOSEN shape separately, at
    render time (see composition._hand_drawn_curve), never here."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    off = bulge_px * side
    p0 = (x0, y0)
    p1 = (x0 + dx * 0.30 + nx * off, y0 + dy * 0.30 + ny * off)
    p2 = (x0 + dx * 0.66 + nx * off, y0 + dy * 0.66 + ny * off)
    p3 = (x1, y1)
    return [_bezier_point(p0, p1, p2, p3, i / (samples - 1)) for i in range(samples)]


def _segment_intersects_rect(ax: float, ay: float, bx: float, by: float, r: ObstacleRect) -> bool:
    """Cheap segment-vs-AABB test: clip the segment's parametric range
    against each of the rect's 4 half-plane bounds (Liang-Barsky), no
    library, no per-frame cost (called only from the one-time solve)."""
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, ax - r.x0), (dx, r.x1 - ax),
        (-dy, ay - r.y0), (dy, r.y1 - ay),
    ):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return t0 <= t1


def polyline_hits_rect(points: Sequence[Point], r: ObstacleRect) -> bool:
    return any(_segment_intersects_rect(a[0], a[1], b[0], b[1], r) for a, b in zip(points, points[1:]))


def polyline_bbox(points: Sequence[Point], *, margin: float = 10.0) -> ObstacleRect:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return ObstacleRect(min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


def _resample_polyline(points: Sequence[Point], count: int) -> List[Point]:
    """Evenly re-spaces ``points`` (by arc length) into exactly ``count``
    samples — keeps every candidate's point count consistent regardless of
    shape, so _truncate_polyline's arc-length draw-on progress behaves the
    same for a bow or an elbow route."""
    if len(points) <= 1 or count <= 1:
        return list(points)
    seg_lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    total = sum(seg_lengths) or 1e-6
    step = total / (count - 1)
    out = [points[0]]
    seg_i, covered = 0, 0.0
    for k in range(1, count - 1):
        target = k * step
        while seg_i < len(seg_lengths) and covered + seg_lengths[seg_i] < target:
            covered += seg_lengths[seg_i]
            seg_i += 1
        if seg_i >= len(seg_lengths):
            out.append(points[-1])
            continue
        remaining = target - covered
        t = remaining / seg_lengths[seg_i] if seg_lengths[seg_i] else 0.0
        a, b = points[seg_i], points[seg_i + 1]
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    out.append(points[-1])
    return out


def elbow_curve(x0: float, y0: float, x1: float, y1: float, *, clear_y: float, samples: int = 28) -> List[Point]:
    """An "over the top" or "under the bottom" detour: P0 up/down to
    ``clear_y`` (an ABSOLUTE y coordinate, not a small delta — see
    solve_edge_route, which derives it from the actual obstacles' own
    bounds), straight across at that altitude, then back down/up to P3.
    Deliberately SHARP (no corner-rounding): margins this tight are exactly
    why an elbow was needed instead of a bow in the first place (verified —
    even ONE light Chaikin pass reliably re-clips the same obstacle it was
    meant to clear, since the rounding eats back into the last few pixels
    of clearance right where the corner needs to turn). The render-time
    hand-drawn jitter (see composition._hand_drawn_curve) still softens the
    look without risking the correctness a bow already failed to
    provide — see solve_edge_route's docstring and
    test_scene_graph_layout.py's TestObstacleAwareArrowRouting."""
    raw = [(x0, y0), (x0, clear_y), (x1, clear_y), (x1, y1)]
    return _resample_polyline(raw, samples)


# Small, deterministic candidate family — NOT a continuous search space, NOT
# hundreds of paths. Bows first (cheap, smooth, handle the common case —
# "curve above"/"curve below"/"stronger" per spec); elbows last, tried only
# when no bow clears (a bow's peak deviation from the straight line is only
# ~0.75x its control-point offset, both ends anchored, so it fundamentally
# can't hug a tight detour close to a fixed endpoint the way a flat-roofed
# elbow can).
CANDIDATE_BULGES: Tuple[Tuple[float, int], ...] = (
    (0.0, 1),
    (180.0, 1), (180.0, -1),
    (350.0, 1), (350.0, -1),
)
_ELBOW_MARGIN_PX = 24.0  # clearance above/below the obstacles' own combined edge


@dataclasses.dataclass(frozen=True)
class SolvedRoute:
    points: Tuple[Point, ...]  # the clean, chosen polyline (pre-jitter) — CACHE this, not a shape parameter
    collisions: int  # how many obstacle SEGMENTS the chosen route still crosses; 0 == fully clear


def _route_severity(points: Sequence[Point], obstacles: Sequence[ObstacleRect]) -> int:
    """Total intersecting SEGMENTS across all obstacles — a coarse but
    cheap severity proxy (a route that only grazes one obstacle's corner
    scores lower than one that cuts across its middle), not just a boolean
    "does it hit anything" — see solve_edge_route."""
    total = 0
    for r in obstacles:
        total += sum(1 for a, b in zip(points, points[1:]) if _segment_intersects_rect(a[0], a[1], b[0], b[1], r))
    return total


def solve_edge_route(
    x0: float, y0: float, x1: float, y1: float, obstacles: Sequence[ObstacleRect],
) -> SolvedRoute:
    """Tries the small CANDIDATE_BULGES family first, then (only if none of
    those clear every obstacle) CANDIDATE_ELBOW_CLEARANCES, scoring each by
    intersection severity (dominant) then by how small its deviation is
    (tie-break — the least-drastic route that still clears everything).
    Called ONCE per edge at layout time — see
    scene_graph.layout.compute_layout. If nothing is fully clean, returns
    whichever candidate has the LOWEST severity (never fails outright)."""
    best: Tuple[float, List[Point], int] | None = None

    for bulge, side in CANDIDATE_BULGES:
        pts = bow_curve(x0, y0, x1, y1, bulge_px=bulge, side=side)
        severity = _route_severity(pts, obstacles)
        cost = severity * 1000.0 + bulge
        if best is None or cost < best[0]:
            best = (cost, pts, severity)
        if severity == 0:
            break  # fully clear — the smallest bow tried so far wins, no need to search further

    if (best is None or best[2] > 0) and obstacles:
        # Obstacle-AWARE elbow targets: go above the topmost obstacle edge,
        # or below the bottommost — not a generic small nudge (a bow's own
        # small bulge already covers that case; an elbow only gets tried
        # when those failed, so it needs to reach an altitude that's
        # provably clear of what's actually in the way).
        top_y = min(r.y0 for r in obstacles) - _ELBOW_MARGIN_PX
        bottom_y = max(r.y1 for r in obstacles) + _ELBOW_MARGIN_PX
        for clear_y in (top_y, bottom_y):
            pts = elbow_curve(x0, y0, x1, y1, clear_y=clear_y)
            severity = _route_severity(pts, obstacles)
            deviation = abs(clear_y - min(y0, y1)) + abs(clear_y - max(y0, y1))
            cost = severity * 1000.0 + 1000.0 + deviation  # elbows are a last resort: always costlier than any bow
            if best is None or cost < best[0]:
                best = (cost, pts, severity)
            if severity == 0:
                break

    _, pts, severity = best  # type: ignore[misc]
    return SolvedRoute(points=tuple(pts), collisions=severity)


# Same small, deterministic offset ladder the old per-frame label search
# used — kept here so it's solved once and cached, not re-searched per frame.
#
# The base offset must clear more than just the label's own half-height: the
# render-time cosmetic wobble (composition._jitter_polyline, amplitude up to
# ~10px) perturbs the drawn line AFTER this solve, so a label anchored too
# close to the (unjittered) curve can end up with the jittered stroke drawn
# straight through its text — confirmed visually via a real render (an
# "idea becomes aircraft" label with the arrow's own wobbled line crossing
# it). 36px clears a ~10px jitter plus a ~16-20px label half-height with
# margin to spare.
_LABEL_OFFSETS: Tuple[float, ...] = (36.0, 54.0, 72.0, 90.0, 108.0)


def solve_label_position(
    curve_points: Sequence[Point], label_half_w: float, label_half_h: float, keep_out: Sequence[ObstacleRect],
) -> Point:
    """Where to anchor a short arrow-label's CENTER so its bounding box
    clears every obstacle in ``keep_out`` (every active card, other arrow
    labels, etc.) — tries offsets along the curve's local normal, both
    signs, until clear. Called ONCE per labeled edge; the render-time draw
    just uses the returned point directly."""
    mid = curve_points[len(curve_points) // 2]
    a = curve_points[max(0, len(curve_points) // 2 - 1)]
    b = curve_points[min(len(curve_points) - 1, len(curve_points) // 2 + 1)]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length

    for offset in _LABEL_OFFSETS:
        for sign in (1.0, -1.0):
            x, y = mid[0] + nx * offset * sign, mid[1] + ny * offset * sign
            box = ObstacleRect(x - label_half_w, y - label_half_h, x + label_half_w, y + label_half_h)
            if not any(_rects_overlap(box, r) for r in keep_out):
                return (x, y)
    # Nothing fully clear — fall back to the first offset (least-bad, same
    # as the old behavior's implicit fallback when the loop never broke).
    return (mid[0] + nx * _LABEL_OFFSETS[0], mid[1] + ny * _LABEL_OFFSETS[0])


def _rects_overlap(a: ObstacleRect, b: ObstacleRect) -> bool:
    return not (a.x1 <= b.x0 or b.x1 <= a.x0 or a.y1 <= b.y0 or b.y1 <= a.y0)


def keep_out_exit_point(
    cx: float, cy: float, tx: float, ty: float, box: ObstacleRect, *, pad: float = 0.0,
) -> Point:
    """Where the ray from (cx, cy) toward (tx, ty) first exits ``box``
    (already expanded by any keep-out margin the caller wants, e.g. a
    card's caption/label band) — so an arrow starts/ends at the card's
    true edge, never cutting across its own or another card's caption
    text along the way. Cheap O(1) ray/AABB math — safe to call every
    frame (it's not a search), unlike solve_edge_route/solve_label_position
    above which must only run once and be cached."""
    x0, y0 = box.x0 - pad, box.y0 - pad
    x1, y1 = box.x1 + pad, box.y1 + pad
    dx, dy = tx - cx, ty - cy
    candidates = [1.0]
    if dx > 0:
        candidates.append((x1 - cx) / dx)
    elif dx < 0:
        candidates.append((x0 - cx) / dx)
    if dy > 0:
        candidates.append((y1 - cy) / dy)
    elif dy < 0:
        candidates.append((y0 - cy) / dy)
    t = min(c for c in candidates if c > 0)
    return (cx + dx * t, cy + dy * t)


def deterministic_unit(seed: str, index: int) -> float:
    """A stable, reproducible value in [-1, 1] for ``seed`` — same
    hash-seeding convention as composition._hand_drawn_curve's jitter, reused
    here for Ken Burns parameter generation (see layout.solve_ken_burns)."""
    digest = hashlib.sha1(f"{seed}:{index}".encode("utf-8")).digest()
    return (digest[0] / 255.0) * 2.0 - 1.0
