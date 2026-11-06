"""Word-timed builds: each item of a review graphic appears on the word that names it (docs/product_trailer/REVIEW_REFERENCE_4.md, gap 1).

The references build one canvas while the narrator talks: colour cards pop in as each colour is said, a chip badge lands on "Extreme", a benchmark
bar grows when its chip is named. cue_layers() reads the narrator's word times and writes, per item, `at` = seconds after the layer's start when
the item is first named inside the layer's window (and `badge_at` / `highlight_at` for a badge or a tweet's marked phrase). Layers that find no
`at` keep their own stagger, so nothing changes for an item that is never said. Only the words' own times are used: no Gemini, no Whisper run here.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .voiceover import _wtimes, norm

STOP = {"the", "a", "an", "and", "of", "with", "for", "to", "in", "on", "is", "its", "it", "or", "vs", "new", "x"}
FIRST_MAX = 0.8                 # a fresh graphic shows its first item by then, so the paper is never empty for long (no still screens)
STEP = 0.12                     # an unnamed item after a named one follows it by this much (the layers' own stagger)
ITEMS = {                       # layer type -> (list key, fields that name an item, in order of preference)
    "pt_flatphones": ("phones", ("label", "text", "top")),
    "pt_compare3": ("cols", ("label",)),
    "pt_bench": ("rows", ("label", "text")),
    "pt_glass": ("cards", ("title",)),
    "pt_gauge": ("gauges", ("label",)),
    "pt_thermal": ("phones", ("label",)),
    "pt_coststack": ("rows", ("label",)),
    "pt_swatches": ("cards", ("name",)),
    "pt_sides": ("items", ("value", "sub")),
}
Part = Tuple[str, float]


def wtimes(words: Sequence[Any]) -> List[Tuple[str, float, float]]:
    return _wtimes(words)


def _parts(tok: str) -> List[str]:
    """'12gb' -> ['12', 'gb'] so '12GB' matches a narrator's '12 GB' and the other way round."""
    return re.findall(r"\d+|[a-z]+", tok) or [tok]


def _expand(W: Sequence[Tuple[str, float, float]], a: float, b: float) -> List[Part]:
    return [(p, s) for w, s, _e in W if a - 0.05 <= s <= b for p in _parts(w)]


def _phrase_parts(text: str) -> List[str]:
    return [p for t in (norm(x) for x in str(text).split()) if t for p in _parts(t)]


def _useful(p: str) -> bool:
    return p not in STOP and (len(p) > 1 or p.isdigit())


def phrase_time(W: Sequence[Tuple[str, float, float]], phrase: str, a: float, b: float, skip: Iterable[str] = ()) -> Optional[float]:
    """When `phrase` is first said inside a..b: the whole phrase in a row if it is said that way, else its first distinctive word
    (words in `skip`, shared with the other items of the same graphic, never count)."""
    want = _phrase_parts(phrase)
    if not want:
        return None
    seq = _expand(W, a, b)
    toks = [p for p, _ in seq]
    n = len(want)
    for i in range(len(toks) - n + 1):
        if toks[i:i + n] == want:
            return seq[i][1]
    keys = {p for p in want if _useful(p)} - set(skip)
    for p, s in seq:
        if p in keys:
            return s
    return None


def _cue_items(L: Dict[str, Any], W, key: str, fields: Tuple[str, ...]) -> None:
    if L.get("hold"):
        return                                   # a settled copy of the scene before it: its items are already on screen
    L[key] = [dict(it) if isinstance(it, dict) else it for it in (L.get(key) or [])]   # held copies share the list: write on our own copy
    items = [it for it in L[key] if isinstance(it, dict)]
    a, b = float(L.get("start", 0.0)), float(L.get("end", L.get("start", 0.0) + 5.0))
    if len(items) < 1 or b <= a:
        return
    cont = bool(L.get("cont"))                   # a building canvas (product_trailer/canvas.py): its phones are on screen; only new facts get times
    per = [tuple(x for x in (it.get("fresh") or ()) if x in ("text", "top")) if cont else fields for it in items]
    names = [" ".join(str(it.get(f) or "") for f in fs) for it, fs in zip(items, per)]
    sets = [set(p for p in _phrase_parts(nm) if _useful(p)) for nm in names]
    shared = set.intersection(*sets) if len(sets) > 1 else set()
    found: List[Optional[float]] = []
    for it, fs in zip(items, per):
        t = None
        for f in fs:
            if it.get(f) not in (None, ""):
                t = phrase_time(W, str(it[f]), a, b, shared)
                if t is not None:
                    break
        found.append(t)
    badges = [phrase_time(W, str(it["badge"]), a, b) if it.get("badge") not in (None, "") else None for it in items]
    if all(t is None for t in found) and all(t is None for t in badges):
        return                                   # nothing named: the layer keeps its own stagger
    prev = None
    for it, t, bt in zip(items, found, badges):
        if t is not None:
            it["at"] = round(max(0.0, t - a), 2)
        elif prev is not None and not cont:
            it["at"] = round(prev + STEP, 2)    # an unnamed item after a named one comes just after it, never before
        if bt is not None:
            it["badge_at"] = round(max(0.0, bt - a), 2)
        prev = it.get("at", prev)
    timed = [it for it in items if "at" in it]
    if not cont and timed and len(timed) == len(items) and min(it["at"] for it in timed) > FIRST_MAX:
        first = min(timed, key=lambda it: it["at"])
        first["at"] = 0.0                        # the scene opens with its first item; the rest still land on their words


def cue_layers(layers: List[Dict[str, Any]], W: Sequence[Tuple[str, float, float]]) -> List[Dict[str, Any]]:
    """Write word times onto every list graphic in `layers` (in place) and return them. `W` is wtimes(words)."""
    if not W:
        return layers
    for L in layers:
        if not isinstance(L, dict):
            continue
        typ = L.get("type")
        if typ in ITEMS:
            key, fields = ITEMS[typ]
            _cue_items(L, W, key, fields)
        elif typ == "pt_ring" and L.get("phrase") and "at" not in L:
            t = phrase_time(W, str(L["phrase"]), float(L.get("start", 0.0)), float(L.get("end", 0.0)))
            if t is not None:
                L["at"] = round(max(0.0, t - float(L.get("start", 0.0))), 2)
        elif typ == "pt_tweet" and L.get("highlight"):
            t = phrase_time(W, str(L["highlight"]), float(L.get("start", 0.0)), float(L.get("end", 0.0)))
            if t is not None:
                L["highlight_at"] = round(max(0.0, t - float(L.get("start", 0.0))), 2)
    return layers
