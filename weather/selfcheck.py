"""The checks a Weather plan passes before it is rendered, as one list (Check plan shows it; Generate logs it).

    checks(plan, payload) -> [(ok, line)]

Nothing here changes the plan: the fixes were already made (weather.autofix, weather.motion, weather.teamplate.cutaways) and listed
as "Fixed for you"; this measures the result against the targets so you can see it before the long render. A failed check is a
warning, never a reason to stop."""

from __future__ import annotations

from collections import Counter
from typing import List, Tuple

STILL_TARGET_S = 7.0
MAP_TARGET = 0.50
ARRIVE_S = 3.5


def _merge(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def longest_still(plan, payload) -> Tuple[float, float]:
    """(seconds, where): the longest stretch with nothing moving on screen — no camera move, no graphic arriving, no timed loop and
    no footage."""
    spans = []
    for b in plan.beats:
        if b.mode == "footage":
            spans.append([b.start, b.end])
            continue
        for c in b.camera:
            if c.action == "start":
                continue
            dur = c.dur if c.dur is not None else {"fly_to": 2.2, "push_in": 8.0, "pull_back": 2.0}.get(c.action, 2.0)
            spans.append([c.t, c.t + dur])
        spans += [[lay.t, lay.t + ARRIVE_S] for lay in b.layers]
    for e in list(getattr(payload, "events", [])) + list(getattr(payload, "fills", [])):
        if "t_in" in e:
            spans.append([float(e["t_in"]), float(e["t_in"]) + ARRIVE_S])
    for r in list(getattr(payload, "rasters", [])) + list(getattr(payload, "satellite", [])):
        if "t_in" in r and "t_out" in r:
            spans.append([float(r["t_in"]), float(r["t_out"])])
    best, where, t = 0.0, 0.0, 0.0
    for a, z in _merge(spans) + [[plan.duration, plan.duration]]:
        if a - t > best:
            best, where = a - t, t
        t = max(t, z)
    return best, where


def checks(plan, payload) -> List[Tuple[bool, str]]:
    total = sum(b.end - b.start for b in plan.beats) or 1.0
    footage = sum(b.end - b.start for b in plan.beats if b.mode == "footage") / total
    still, at = longest_still(plan, payload)
    asks = Counter(str(c.asset) for b in plan.beats for c in b.clips if str(c.asset).startswith(("stock_video:", "stock_image:")))
    repeats = [a for a, k in asks.items() if k > 1]
    numbers = len(getattr(getattr(payload, "report", None), "lines", []) or [])
    return [
        (still <= STILL_TARGET_S, f"longest still stretch {still:.1f} s at {at:.0f} s (target: {STILL_TARGET_S:.0f} s or less)"),
        (1 - footage <= MAP_TARGET + 0.05, f"map on screen {1 - footage:.0%} of the video (target: about {MAP_TARGET:.0%} or less)"),
        (True, f"full-screen footage {footage:.0%} of the video"),
        (not repeats, "no stock search asked for twice" if not repeats else f"{len(repeats)} stock search(es) asked for more than once"),
        (True, f"{numbers} number(s) on screen, each from its source (weather_numbers.txt lists them)"),
    ]


def as_text(items: List[Tuple[bool, str]]) -> str:
    return "\n".join(("  ok  " if ok else "  !   ") + line for ok, line in items)
