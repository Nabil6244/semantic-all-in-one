"""Motion presets: pure functions of the element's age, on a fixed 30 fps frame grid, so a frame depends only on (preset, age) and the same plan draws the same bytes. Tables are integers or
fixed decimals (like the narrator's BOB table); nothing is random. Phase 9 of the reference-2 plan (docs/explainer/explainer_reference2_analysis.md): slam (stamps) and slide_in (plates)."""

from __future__ import annotations

import re
from typing import Tuple

GRID_FPS = 30
VERSION = 1                      # carried in a motion cue's params, so a change to a table changes the clip's cache key (without touching any other clip's)

# (scale, alpha, extra rotation in degrees (counter-clockwise, added to the stamp's own tilt), dx, dy): frame 0 is the cue frame itself; frame 4 is the impact, 3 frames of shake follow
SLAM = (
    (1.55, 0.35, 5.0, 0, 0),
    (1.36, 0.70, 3.5, 0, 0),
    (1.18, 1.00, 2.0, 0, 0),
    (1.03, 1.00, 0.8, 0, 0),
    (0.94, 1.00, 0.0, 3, 2),
    (0.985, 1.00, 0.0, -3, -2),
    (1.012, 1.00, 0.0, 2, 1),
    (1.00, 1.00, 0.0, 0, 0),
)
# variants for phase F (rotated through a video so the same entrance is not seen twice in a row): 0 = SLAM above; 1 = a drop from above with a bounce (no scale change); 2 = a soft press (scale only, no shake)
SLAM_DROP = (
    (1.0, 0.45, 0.0, 0, -150),
    (1.0, 0.80, 0.0, 0, -100),
    (1.0, 1.00, 0.0, 0, -52),
    (1.0, 1.00, 0.0, 0, -16),
    (1.0, 1.00, 0.0, 0, 7),
    (1.0, 1.00, 0.0, 0, -4),
    (1.0, 1.00, 0.0, 0, 2),
    (1.0, 1.00, 0.0, 0, 0),
)
SLAM_SOFT = (
    (1.30, 0.40, 2.0, 0, 0),
    (1.18, 0.75, 1.0, 0, 0),
    (1.08, 1.00, 0.5, 0, 0),
    (1.02, 1.00, 0.0, 0, 0),
    (0.97, 1.00, 0.0, 0, 0),
    (1.01, 1.00, 0.0, 0, 0),
    (1.00, 1.00, 0.0, 0, 0),
    (1.00, 1.00, 0.0, 0, 0),
)
SLAM_VARIANTS = (SLAM, SLAM_DROP, SLAM_SOFT)
SLAM_FRAMES = len(SLAM)
IMPACT_FRAME = 4
SLIDE_FRAMES = 9


def frame_of(age: float) -> int:
    return max(0, int(age * GRID_FPS + 1e-6))


def slam(age: float) -> Tuple[float, float, float, int, int]:
    return SLAM[min(frame_of(age), SLAM_FRAMES - 1)]


def slam_frame(frame: int, variant: int = 0):
    return SLAM_VARIANTS[variant % len(SLAM_VARIANTS)][min(frame, SLAM_FRAMES - 1)]


def slam_settled(age: float) -> bool:
    return frame_of(age) >= SLAM_FRAMES - 1


def slide_in(age: float, dist: int = 60) -> Tuple[int, float]:
    """(offset in px still to travel, alpha): ease-out cubic over SLIDE_FRAMES frames."""
    k = min(1.0, frame_of(age) / (SLIDE_FRAMES - 1))
    e = 1 - (1 - k) ** 3
    return int(round((1 - e) * dist)), round(0.25 + 0.75 * e, 3)


# ---- count_up: an integer roll to a spoken quantity (phase C) ----
COUNT_RE = re.compile(r"^(?P<pre>[$\u20ac\u00a3]?)(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<dec>\d{1,2}))?(?P<suf>(?:\s?(?:%|percent|million|billion|trillion|thousand|hundred|k|m|bn))?(?:\s(?!(?:and|of|the|an|to|in|on|at|for|with|by|from|or|but|is|was|are|were|that|than|as|it|its)\b)[A-Za-z]{2,12})?)$", re.I)
UNIT_RE = re.compile(r"^\s?(?:%|percent|million|billion|trillion|thousand|hundred|k|m|bn)\b", re.I)
COUNT_MIN_FRAMES, COUNT_MAX_FRAMES = 24, 36          # 0.8 to 1.2 s


def count_spec(text: str, frames: int = 30):
    """{pre, suf, dec, to, commas, frames} for a bare quantity text such as "1,200", "$2.5 million", "45%", or None. `to` is an integer in units of 10**-dec, so the roll is pure integer arithmetic."""
    m = COUNT_RE.match(" ".join((text or "").split()))
    if not m:
        return None
    dec = m.group("dec") or ""
    ints = m.group("int")
    to = int(ints.replace(",", "") + dec)
    return {"pre": m.group("pre"), "suf": m.group("suf"), "unit": bool(UNIT_RE.match(m.group("suf") or "")), "dec": len(dec), "to": to, "commas": "," in ints, "frames": max(COUNT_MIN_FRAMES, min(COUNT_MAX_FRAMES, int(frames)))}


def _fmt(v: int, spec) -> str:
    d = spec["dec"]
    ip, fp = (v // 10 ** d, v % 10 ** d) if d else (v, 0)
    body = f"{ip:,}" if spec["commas"] else str(ip)
    if d:
        body += "." + str(fp).zfill(d)
    return f"{spec['pre']}{body}{spec['suf']}"


def count_text(age: float, spec) -> str:
    """The number shown at `age`: ease-out cubic in integers; from frame `frames` on it is exactly the final text."""
    n = spec["frames"]
    f = frame_of(age)
    if f >= n:
        return _fmt(spec["to"], spec)
    return _fmt(spec["to"] * (n ** 3 - (n - f) ** 3) // n ** 3, spec)


# ---- cross_out: two strokes, 5 frames each (phase C) ----
CROSS_STROKE_FRAMES = 5


def cross_out(age: float) -> Tuple[float, float]:
    """Progress (0..1) of the first and second stroke; the second starts when the first is done."""
    f = frame_of(age)
    return min(1.0, f / CROSS_STROKE_FRAMES), min(1.0, max(0, f - CROSS_STROKE_FRAMES) / CROSS_STROKE_FRAMES)


PLATE_VARIANTS = 3          # 0 slides down from above, 1 slides in from the right, 2 fades in with a short rise


def plate_motion(age: float, variant: int = 0, dist: int = 60):
    """(dx, dy still to travel, alpha) at `age` for entrance `variant`."""
    off, alpha = slide_in(age, dist)
    v = variant % PLATE_VARIANTS
    if v == 0:
        return 0, -off, alpha
    if v == 1:
        return off * 2, 0, alpha
    return 0, off // 3, round(0.1 + 0.9 * (alpha - 0.25) / 0.75, 3)
