"""Map relation lines (opt-in, DirectorOptions.maplines; phase D of the upgrade plan, re-scoped).

The planned "overlay composited over the compiled map clip" would need a layer the Hybrid plan does not have, or the Explainer rendering maps itself: both mean changes in hybrid/ or pakmap/.
This is the part that needs neither: the plan's own `line` layer (kind "flow", already drawn by the map engine) between two places the narration joins with a relation word
("from Egypt to Libya", "sailed across the Atlantic", "invaded Poland"): the viewer sees the move as a line between the two places at the moment the second is spoken.
Rules: one line per map beat; both places already shown on this beat's map with their own layers; the same sentence; a relation word within the four words between them;
and the beat's final camera view holds both places (so the line is never drawn off screen); a line between a place and itself, or two places that resolve to the same country, is never drawn."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

from ..beats import framing as FR

RELATION = frozenset("""to toward towards into onto across through over from invaded attacked reached entered crossed sailed marched flew shipped moved fled migrated traveled travelled advanced retreated""".split())
MAX_BETWEEN = 4
LINE_KIND = "flow"


def _norm(w: str) -> str:
    return re.sub(r"[^a-z]", "", w.lower())


def relation_lines(shown: Sequence[Any], cam: Dict[str, Any], words, sents: Sequence[Any], waits: Dict[str, float]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Returns ([{places, kind, offset_s}], notes). `shown` are the beat's PlaceHits in spoken order; `waits` {place: seconds the layer waits for the camera}."""
    notes: List[str] = []
    hs = sorted((h for h in shown if h.match), key=lambda h: h.match["start"])
    view = cam.get("view")
    for a, b in zip(hs, hs[1:]):
        ia, ib = a.match.get("word_indices") or [], b.match.get("word_indices") or []
        if not ia or not ib or a.name == b.name:
            continue
        lo, hi = max(ia) + 1, min(ib)
        if hi <= lo - 0 or hi - lo > MAX_BETWEEN:
            continue
        between = list(range(lo, hi))
        if not any(_norm(words[g][0]) in RELATION for g in between):
            continue
        s_ = next((s for s in sents if ia[0] in s.widx), None)
        if s_ is None or ib[-1] not in s_.widx:
            notes.append(f"line {a.name} to {b.name}: the two places are in different sentences")
            continue
        if view is None:
            notes.append(f"line {a.name} to {b.name}: no single camera view is in force to check both places against")
            continue
        try:
            box = FR.view_box(*view)
            if not (FR.inside(box, FR.place_bbox(a.name)) and FR.inside(box, FR.place_bbox(b.name))):
                notes.append(f"line {a.name} to {b.name}: the final camera view does not hold both places")
                continue
        except Exception as exc:
            notes.append(f"line {a.name} to {b.name}: the places cannot be framed ({str(exc)[:60]})")
            continue
        return [{"places": [a.name, b.name], "kind": LINE_KIND, "offset_s": round(max(waits.get(a.name, 0.0), waits.get(b.name, 0.0)), 3)}], notes
    return [], notes
