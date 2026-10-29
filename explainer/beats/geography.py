"""Geography beats: which beats deserve the map, and the direction cue a map beat draws.

A beat that SAYS where things lie ("look east across the Adriatic", "from Venice to Constantinople") is what the map exists for; a beat that only mentions a place in passing is not.
`map_priority` scores a beat from its own words and the places it names; `pick_map_beats` spends the map budget on the highest scores first (equal scores keep story order, so a
script with no geography relations is planned exactly as before). `direction_cue` returns the two coordinates of a `flow` line that crosses a named water or region in the direction
the narration gives. Pure functions; nothing is drawn here."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

DIRS: Dict[str, Tuple[float, float]] = {          # (east, north) unit components
    "east": (1, 0), "eastward": (1, 0), "eastwards": (1, 0), "west": (-1, 0), "westward": (-1, 0), "westwards": (-1, 0),
    "north": (0, 1), "northward": (0, 1), "northwards": (0, 1), "south": (0, -1), "southward": (0, -1), "southwards": (0, -1),
    "northeast": (.7, .7), "northwest": (-.7, .7), "southeast": (.7, -.7), "southwest": (-.7, -.7),
}
ROUTE_WORDS = frozenset("across toward towards beyond through along over between from into past".split())
DIR_WINDOW = 5        # a direction word counts for a place when it is spoken at most this many tokens before it
_LATLON = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$")


def is_coordinate(ref: str) -> bool:
    return bool(_LATLON.match(str(ref).replace(" ", "")))


def _hit_index(tk: Sequence[Dict[str, Any]], match: Dict[str, Any]) -> int:
    wi = (match.get("word_indices") or [None])[0]
    return next((i for i, t in enumerate(tk) if t["word_index"] == wi), -1)


def direction_before(tk: Sequence[Dict[str, Any]], match: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    i = _hit_index(tk, match)
    for j in range(max(0, i - DIR_WINDOW), i):
        if i >= 0 and tk[j]["tok"] in DIRS:
            return tk[j]["tok"], tk[j]
    return None


def map_priority(tk: Sequence[Dict[str, Any]], hits: Sequence[Any]) -> Tuple[int, List[str]]:
    """(score, reasons). hits: PlaceHit-like objects with .name, .kind and .match."""
    score, why = 0, []
    for h in hits:
        if not getattr(h, "match", None):
            continue
        d = direction_before(tk, h.match)
        if d:
            score += 3
            why.append(f"direction: '{d[0]}' toward {h.name}")
        i = _hit_index(tk, h.match)
        if i > 0 and any(t["tok"] in ROUTE_WORDS for t in tk[max(0, i - 4):i]):
            score += 2
            why.append(f"route word before {h.name}")
        if getattr(h, "kind", "") == "sea":
            score += 1
            why.append(f"{h.name} is a sea or lagoon: only a map shows where it lies")
    if len(hits) >= 2 and score:
        score += 1
        why.append("two or more places related")
    return score, why


def pick_map_beats(cands: Sequence[Dict[str, Any]], n_beats: int, budget_s: float, max_run: int = 2) -> List[str]:
    """cands: [{idx, id, dur, score}] (the beats that have a place and are long enough) in story order. Returns the ids that get the map: highest score first, ties in story order, never more
    than `max_run` neighbours in a row, never over `budget_s`. With all scores equal this is the plain first-come rule."""
    chosen: Dict[int, Dict[str, Any]] = {}
    used = 0.0
    order = sorted(cands, key=lambda c: (-c["score"], c["idx"]))
    if cands and cands[0]["idx"] == 0:                       # the opening beat keeps the map it would have had: the story starts on it
        order.insert(0, order.pop(order.index(cands[0])))
    for c in order:
        if used + c["dur"] > budget_s + 1e-9:
            continue
        run_l = run_r = 0
        j = c["idx"] - 1
        while j in chosen:
            run_l, j = run_l + 1, j - 1
        j = c["idx"] + 1
        while j in chosen:
            run_r, j = run_r + 1, j + 1
        if run_l + run_r + 1 > max_run:
            continue
        chosen[c["idx"]] = c
        used += c["dur"]
    return [c["id"] for c in sorted(chosen.values(), key=lambda c: c["idx"])]


def direction_cue(tk: Sequence[Dict[str, Any]], place: str, match: Dict[str, Any], resolve) -> Optional[Dict[str, Any]]:
    """A `flow` line across `place` in the direction the narration gives ("look east across the Adriatic"). Needs a direction word just before the place and an area of known size
    (a sea, a region, a country). Returns {places: [lat,lon ref, lat,lon ref], t, direction} or None. The line runs across the middle half of the place's own box."""
    d = direction_before(tk, match)
    if d is None:
        return None
    try:
        loc = resolve(place)
    except Exception:
        return None
    if not (getattr(loc, "is_area", False) or getattr(loc, "kind", "") == "sea"):
        return None
    ex, ny = DIRS[d[0]]
    w, s, e, n = loc.bbox
    cx, cy = (w + e) / 2, (s + n) / 2
    hx, hy = (e - w) * 0.40 * ex, (n - s) * 0.40 * ny
    if not (ex or ny) or math.hypot(hx, hy) < 0.05:
        return None
    dlat = (n - s) * -0.12 if ex and not ny else 0.0                       # the place's own label sits on its centre: the line runs beside it, not under it
    dlon = (e - w) * 0.12 if ny and not ex else 0.0
    a, b = (cy - hy + dlat, cx - hx + dlon), (cy + hy + dlat, cx + hx + dlon)
    return {"places": [f"{a[0]:.3f},{a[1]:.3f}", f"{b[0]:.3f},{b[1]:.3f}"], "t": round(d[1]["start"], 4), "direction": d[0]}
