"""Shared motion primitives for War Documentary cards and maps. All are pure functions of time: same t, same value.

    ease_out / ease_in_out / smoothstep   0..1 -> 0..1
    ramp(t, start, length)                0 before start, 1 after start + length
    stagger(i, base, step)                start time of the i-th item
    count_value(t, start, target)         integer counted up over COUNT_S
    draw_fraction(t, start, length)       how much of a line / bar / rule is drawn (eased)
    pulse(t, period)                      (scale 1..1.0+, alpha 1..0) ring that grows and fades, for location highlights
    slow_zoom(t, dur, z0, z1)             restrained push-in factor
    pan(t, dur, x0, x1)                   restrained pan
    lerp / lerp_box                       interpolation of numbers and (x0, y0, x1, y1) boxes (map camera)
    card_alpha(t, dur)                    fade in then out
    typed(text, t, start, length)         the leading part of text (typed headlines)
    point_on_polyline(points, f)          position at fraction f along a polyline (arrows and routes)
    partial_polyline(points, f)           the first f of a polyline, as a point list (line draw-on)
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from . import tokens as T
from .. import look as L

Point = Tuple[float, float]


def clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def ease_out(x: float) -> float:
    return L.ease_out(x)


def ease_in_out(x: float) -> float:
    x = clamp01(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def smoothstep(x: float) -> float:
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ramp(t: float, start: float, length: float) -> float:
    return L.ramp(t, start, length)


def stagger(i: int, base: float, step: float) -> float:
    return base + i * step


def count_value(t: float, start: float, target: int, length: float = T.COUNT_S) -> int:
    k = ramp(t, start, length)
    if k <= 0:
        return 0
    return max(1, int(round(target * ease_out(k)))) if target else 0


def draw_fraction(t: float, start: float, length: float = T.DRAW_S) -> float:
    return ease_out(ramp(t, start, length))


def pulse(t: float, period: float = T.PULSE_S) -> Tuple[float, float]:
    ph = (t % period) / period
    return 1.0 + 1.6 * ph, 1.0 - ph


def slow_zoom(t: float, dur: float, z0: float = 1.0, z1: float = 1.05) -> float:
    return z0 + (z1 - z0) * (t / dur if dur > 0 else 1.0)


def pan(t: float, dur: float, x0: float, x1: float) -> float:
    return x0 + (x1 - x0) * (t / dur if dur > 0 else 1.0)


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def lerp_box(a: Sequence[float], b: Sequence[float], k: float) -> Tuple[float, float, float, float]:
    return tuple(lerp(x, y, k) for x, y in zip(a, b))  # type: ignore[return-value]


def card_alpha(t: float, dur: float) -> float:
    return L.card_alpha(t, dur)


def typed(text: str, t: float, start: float, length: float) -> str:
    n = len(text)
    return text[: max(0, int(n * ramp(t, start, length)))] if n else ""


def _seg_lengths(points: Sequence[Point]) -> List[float]:
    return [math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]) for i in range(len(points) - 1)]


def partial_polyline(points: Sequence[Point], f: float) -> List[Point]:
    f = clamp01(f)
    if len(points) < 2 or f <= 0:
        return list(points[:1])
    lens = _seg_lengths(points)
    target = sum(lens) * f
    out: List[Point] = [points[0]]
    acc = 0.0
    for i, ln in enumerate(lens):
        if acc + ln >= target:
            k = (target - acc) / ln if ln else 0.0
            out.append((points[i][0] + (points[i + 1][0] - points[i][0]) * k, points[i][1] + (points[i + 1][1] - points[i][1]) * k))
            return out
        out.append(points[i + 1])
        acc += ln
    return out


def point_on_polyline(points: Sequence[Point], f: float) -> Point:
    return partial_polyline(points, f)[-1]
