"""The relevance gate: a 3D model, globe or picture stays only when the sentence under it is about it."""

from __future__ import annotations

import re
from typing import Any, Optional

from .concepts import STOP

COVERING = {"tm_template", "tm_metric", "tm_annotate", "tm_bars", "tm_compare", "tm_timeline", "tm_logaxis", "tm_composition", "tm_curve", "tm_dial", "tm_discmap",
            "tm_grid", "tm_orbitmap", "tm_phase", "tm_wave", "tm_gauge", "tm_survival", "tm_title", "tm_mission", "tm_clock", "tm_section"}


def _stem(w: str) -> str:
    w = w.lower().strip("'s")
    return re.sub(r"(ing|ed|es|s)$", "", w) if len(w) > 4 else w


def shot_subject_tokens(shot: Any) -> list:
    """Name words a 3D shot claims to show ("VOYAGER 1", "JUPITER", "JAMES WEBB SPACE TELESCOPE"); the model file / texture name as well."""
    raw = f"{getattr(shot, 'name', '')} {str(getattr(shot, 'model', '')).split('.')[0]} {str(getattr(shot, 'texture', '')).split('.')[0].replace('2k_', '')}"
    return [_stem(w) for w in re.findall(r"[A-Za-z]{3,}", raw) if w.lower() not in STOP and w.lower() not in ("glb", "jpg", "space", "solar", "probe", "simple", "atmosphere", "bluemarble", "lroc", "cassini")
            or w.lower() in ("cassini",)]


def three_d_relevant(shot: Any, text: str, carry: Any = None) -> bool:
    """A craft/globe shot is about its subject when the narration under it names it (any word of its name), or continues it ("the probe ...")."""
    if getattr(shot, "kind", "") not in ("craft", "globe"):
        return True
    said = {_stem(w) for w in re.findall(r"[A-Za-z]{3,}", text or "")}
    toks = shot_subject_tokens(shot)
    if not toks or any(t in said for t in toks):
        return True
    return bool(carry is not None and carry.search(text or ""))


def fallback_picture(text: str) -> dict:
    """The shot fields of an illustration made from THIS sentence (the fix for an irrelevant model: a picture of what is said, not a stand-in)."""
    from whatif import planner as pl

    return {"kind": "image", "asset": f"flow_image:{pl.house(text)}{pl.brief(text)}", "cite": ("AI ILLUSTRATION", ""), "model": "", "texture": "", "name": "", "atmosphere": ""}
