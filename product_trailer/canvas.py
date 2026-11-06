"""A canvas that keeps building (docs/product_trailer/REVIEW_REFERENCE_4.md, gap 2).

The references keep one flat scene on screen across 2-4 sentences: the same phones stay where they are, each new fact is added on its word, and a
fact the narrator has moved on from stays, dimmed. build() turns consecutive flat-phone scenes of the same phones into that: the first scene does
not fade out ("keep"), the next one does not re-enter ("cont") and carries the earlier facts it does not replace ("dim"); its new facts are listed in
"fresh" (product_trailer/wordcue.py times them, layers/pt_flatphones.mjs draws them). A scene with nothing new, other phones, or a shot between them
still cuts, and a canvas ends after MAX_CHAIN scenes or CANVAS_MAX_S seconds so the screen keeps changing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .voiceover import norm

FACTS = ("text", "top", "badge", "side", "fill", "cable")
DIMS = ("text", "top", "badge", "side")          # facts that stay on screen, dimmed, when the next sentence moves on
MAX_CHAIN = 4
CANVAS_MAX_S = 24.0


def _flat_of(shot: Dict[str, Any], layers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The one pt_flatphones of a paper shot whose layers are only the paper and that row of phones, else None."""
    if shot.get("kind") != "black":
        return None
    a, b = float(shot["start"]), float(shot["end"])
    mine = [L for L in layers if isinstance(L, dict) and "start" in L and a - 0.01 <= float(L["start"]) < b]
    flats = [L for L in mine if L.get("type") == "pt_flatphones"]
    if len(flats) != 1 or any(L.get("type") not in ("pt_paper", "pt_flatphones") for L in mine) or flats[0].get("hold"):
        return None
    return flats[0]


def _same_phones(A: Dict[str, Any], B: Dict[str, Any]) -> bool:
    pa, pb = A.get("phones") or [], B.get("phones") or []
    if not pa or len(pa) != len(pb):
        return False
    named = 0
    for x, y in zip(pa, pb):
        lx, ly = norm(x.get("label") or ""), norm(y.get("label") or "")
        if lx and ly:
            if lx != ly:
                return False
            named += 1
        elif not lx and not ly and (x.get("color") or "") != (y.get("color") or ""):
            return False
    return named > 0 or all(not norm(y.get("label") or "") for y in pb)


def _merge(A: Dict[str, Any], B: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """B's phones with A's unreplaced facts carried (dimmed) and B's new facts marked fresh; None when B adds nothing."""
    out, any_fresh = [], False
    for x, y in zip(A["phones"], B["phones"]):
        p = {k: v for k, v in y.items() if k not in ("at", "badge_at", "fresh", "dim", "was")}
        if not p.get("label") and x.get("label"):
            p["label"] = x["label"]
        for k in ("color", "cams", "design"):
            if k in x and k not in p:
                p[k] = x[k]
        fresh = [f for f in FACTS if f in y and y[f] != x.get(f)]
        dim = [f for f in DIMS if f not in y and f in x]
        for f in dim:
            p[f] = x[f]
        was = {f: x[f] for f in ("text", "top") if f in fresh and x.get(f) not in (None, "")}
        if was:
            p["was"] = was                       # the old value stays until the new one is said (??MP -> 10MP)
        if fresh:
            p["fresh"] = fresh
            any_fresh = True
        if dim:
            p["dim"] = dim
        out.append(p)
    return out if any_fresh else None


def build(shots: List[Dict[str, Any]], layers: List[Dict[str, Any]]) -> None:
    """Join consecutive flat scenes of the same phones into one building canvas, in place."""
    prev: Optional[Dict[str, Any]] = None
    prev_shot: Optional[Dict[str, Any]] = None
    chain = 0
    for s in shots:
        F = _flat_of(s, layers)
        joined = False
        if F is not None and prev is not None and prev_shot is not None and abs(float(s["start"]) - float(prev_shot["end"])) < 0.05:
            t0 = float(prev.get("t0", prev["start"]))
            if chain < MAX_CHAIN and float(s["end"]) - t0 <= CANVAS_MAX_S and _same_phones(prev, F):
                phones = _merge(prev, F)
                if phones is not None:
                    prev.update({"keep": True, "fade_out": 0})      # the engine's own layer fades would dip the join
                    prev["end"] = round(float(s["start"]), 3)
                    F.update({"phones": phones, "cont": True, "fade_in": 0, "start": round(float(s["start"]), 3), "t0": t0})
                    if not F.get("title") and prev.get("title"):
                        F["title"] = prev["title"]
                    chain += 1
                    joined = True
        if not joined:
            chain = 1 if F is not None else 0
        prev, prev_shot = F, s
