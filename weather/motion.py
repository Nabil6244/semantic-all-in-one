"""The map never stands still: a Weather map beat that would sit on one frame for more than STILL_S gets slow, bounded camera motion.

A beat written "hold" (or one whose camera already arrived) can leave the same picture on screen for a minute: pakMap's drift
is off for Weather (it carried a two-minute hold from Houston to Mississippi), so nothing moves. This pass finds every stretch of
a map beat where the camera has no move, and fills it with a slow push in, the next one easing back out by the same amount, so the
view breathes but stays on the place the narration is about (the zoom returns to where it was; the centre never moves).

Graphics keep their own timing; this only adds camera steps (hybrid.plan.CameraStep) between the ones the plan already has, never
inside footage dissolves (hybrid.plan.free_interval)."""

from __future__ import annotations

from typing import List, Tuple

STILL_S = 6.0        # a still stretch longer than this gets motion
MOVE_MAX_S = 10.0    # one move lasts at most this long (a longer stretch gets several, alternating)
ZOOM = 0.3           # each push in / pull back (pakMap zoom levels): gentle
MARGIN_S = 0.3


def _busy(beat) -> List[Tuple[float, float]]:
    out = []
    for c in beat.camera:
        if c.action == "start":
            continue
        dur = c.dur if c.dur is not None else {"fly_to": 2.2, "push_in": 8.0, "pull_back": 2.0}.get(c.action, 2.0)
        out.append((c.t, c.t + dur))
    return sorted(out)


def keep_moving(plan, notes: List[str]) -> int:
    """Add camera motion to still stretches of map beats. Returns how many moves were added. The zoom is balanced over the video:
    every push in is answered by a pull back of the same size before the next push in."""
    from hybrid.plan import CameraStep, free_interval

    started = False
    pushed = False   # the last added move zoomed in: the next one eases back
    added = 0
    for i, b in enumerate(plan.beats):
        if any(c.action == "start" for c in b.camera):
            started = True
        if not plan.is_map_mode(b) or not started:
            continue
        lo, hi = free_interval(plan, i)
        gaps, cur = [], lo
        for a, z in _busy(b) + [(hi, hi)]:
            if a - cur > STILL_S:
                gaps.append((cur, a))
            cur = max(cur, z)
        new = []
        for a, z in gaps:
            t = a + MARGIN_S
            while z - MARGIN_S - t > STILL_S * 0.6:
                dur = round(min(MOVE_MAX_S, z - MARGIN_S - t), 2)
                new.append(CameraStep(action="pull_back" if pushed else "push_in", t=round(t, 2), dur=dur, zoom_delta=ZOOM))
                pushed = not pushed
                t += dur
        if new:
            b.camera = sorted(b.camera + new, key=lambda c: (c.action != "start", c.t))
            added += len(new)
    if pushed:   # end where we started: the last push in is answered within its own beat's time if there is room
        for i in range(len(plan.beats) - 1, -1, -1):
            b = plan.beats[i]
            if not plan.is_map_mode(b):
                continue
            lo, hi = free_interval(plan, i)
            end = max((c.t + (c.dur or 2.0) for c in b.camera if c.action != "start"), default=lo)
            if hi - end >= 2.0:
                b.camera.append(CameraStep(action="pull_back", t=round(end + 0.1, 2), dur=round(min(4.0, hi - end - 0.2), 2), zoom_delta=ZOOM))
                added += 1
            break
    if added:
        notes.append(f"{added} slow camera move(s) added where the map would have stood still for more than {STILL_S:g} s")
    return added
