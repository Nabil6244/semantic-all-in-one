"""The pass that gives every stretch of narration something relevant to see (What If plans; StarMap Cinema through the same functions).

1. gate_3d     a craft/globe shot whose narration is not about it becomes a picture of what is said, or a composed graphic when the sentence is a figure /
               change / comparison / sequence ...
2. enrich      a sentence with something to show (concepts.analyze strength >= MIN_STRENGTH) and no graphic yet gets one composed for it, as a card over the
               footage, or full frame when its shot is already a plate. At most one per MIN_GAP_S; never over an existing graphic.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import compose, concepts
from .concepts import content_words
from .relevance import COVERING, fallback_picture, three_d_relevant
from . import scene as scene_mod

MIN_STRENGTH = 0.6
MIN_GAP_S = 9.0
MAX_PER_MIN = 4.0
LEAD_S = 0.1
HOOK_S = 4.0
Author = Optional[Callable[[str, str], str]]


def _covered(layers: Sequence[Dict[str, Any]], a: float, b: float) -> bool:
    return any(L.get("type") in COVERING and float(L.get("start", 0)) < b and a < float(L.get("end", 0)) for L in layers)


def _shot_at(shots: Sequence[Any], t: float) -> Optional[Any]:
    return next((s for s in shots if s.start - 1e-6 <= t < s.end), None)


SCENE_MIN_CONF = 0.65
SCENE_SHARE_MAX = 0.45
MAX_AI_CALLS = 14


def _make_scene(s: Any, spec: Dict[str, Any]) -> None:
    s.kind, s.asset, s.file, s.credit, s.model, s.texture, s.name = "scene", "", "", "", "", "", ""
    s.cite = ("ILLUSTRATION", "GENERATED 3D SCENE")
    s.extra["scene_spec"] = spec
    s.extra.pop("full_bleed", None)


def upgrade_scenes(shots: Sequence[Any], notes: List[str], *, author: Author = None) -> int:
    """A picture/clip shot whose sentence describes something drawable (a world, a craft, the air around it, a fall) becomes a 3D scene generated for that
    sentence: never next to another 3D shot, never over a "photo" claim, at most SCENE_SHARE_MAX of the shots."""
    from whatif import planner as pl

    shots = list(shots)
    is3d = lambda x: x.kind in ("craft", "globe", "scene", "hero")           # noqa: E731
    count = sum(1 for x in shots if is3d(x))
    done = asked = 0
    for i, s in enumerate(shots):
        if s.kind not in ("image", "video") or s.length < 3.0 or s.extra.get("lockup") or pl.PHOTO.search(s.text or ""):
            continue
        if (i and is3d(shots[i - 1])) or (i + 1 < len(shots) and is3d(shots[i + 1])):
            continue
        if (count + 1) / max(1, len(shots)) > SCENE_SHARE_MAX:
            break
        got = scene_mod.scene_for(s.text)
        if (not got or got[1] < SCENE_MIN_CONF) and author is not None and asked < MAX_AI_CALLS and len(content_words(s.text)) >= 5:
            asked += 1
            got = scene_mod.author(s.text, author) or got           # the model reads what the rules cannot
        if not got or got[1] < SCENE_MIN_CONF:
            continue
        _make_scene(s, got[0])
        count += 1
        done += 1
    if done:
        notes.append(f"plan: {done} picture shot(s) became a 3D scene generated from their sentence")
    return done


def gate_3d(shots: Sequence[Any], notes: List[str]) -> int:
    """Irrelevant craft/globe shots (narration not about them) become a picture of the sentence."""
    from whatif import variety

    n = 0
    shots = list(shots)
    for i, s in enumerate(shots):
        near = " ".join(x.text for x in shots[max(0, i - 1):i + 2])            # a shot cut out of a longer stretch is still about its neighbours' subject
        if s.kind in ("craft", "globe") and not s.extra.get("lockup") and not three_d_relevant(s, near, variety.CARRY):
            got = scene_mod.scene_for(s.text)
            if got and got[1] >= SCENE_MIN_CONF:            # a scene generated from this sentence beats a stand-in picture
                _make_scene(s, got[0])
            else:
                for k, v in fallback_picture(s.text).items():
                    setattr(s, k, v)
            s.extra.pop("full_bleed", None)
            n += 1
    if n:
        notes.append(f"plan: relevance: {n} 3D shot(s) not about their narration became a picture of what is said")
    return n


def enrich(shots: Sequence[Any], layers: List[Dict[str, Any]], words: Sequence[Any], duration: float, notes: List[str], *, author: Author = None) -> int:
    """Compose a graphic for each sentence that says something showable and has no graphic yet. -> how many were added."""
    from whatif import narration as nr

    if not words or duration <= 0:
        return 0
    sn = nr.sentences(list(words))
    budget = max(1, int(duration / 60.0 * MAX_PER_MIN))
    made, last = 0, -1e9
    for a, b in sn:
        if made >= budget:
            break
        text = nr.span_text(list(words), a, b)
        t0 = max(0.0, words[a].start - LEAD_S)
        if t0 < HOOK_S or t0 - last < MIN_GAP_S:
            continue
        c = concepts.analyze(text)
        if c.strength < MIN_STRENGTH:
            continue
        host = _shot_at(shots, t0)
        on_plate = host is not None and host.kind == "plate"
        t1 = min(duration - 0.3, max(words[b].end + 0.6, t0 + 3.5), t0 + 8.0)
        if on_plate:
            t1 = min(t1, host.end)                       # a full-frame layout never runs on into the next shot
        if t1 - t0 < 3.0 or _covered(layers, t0, t1):
            continue
        t = (compose.author(text, c, author) if author else None) or compose.compose(c, plate=on_plate)
        if t is None:
            continue
        layers.append({"type": "tm_template", "template": t, "slots": {}, "cues": {}, "start": round(t0, 3), "end": round(t1, 3), "fade_in": 0.2, "fade_out": 0.3,
                       "z": 4 if on_plate else 6, "plate": False, "composed": c.kind})
        last = t0
        made += 1
    if made:
        notes.append(f"plan: composed {made} graphic(s) from the narration (figures, changes, comparisons, sequences, timelines, lists, quotes, terms)")
    return made


def apply(shots: Sequence[Any], layers: List[Dict[str, Any]], words: Sequence[Any], duration: float, notes: List[str], *, author: Author = None,
          gate: bool = True) -> None:
    if gate:
        gate_3d(shots, notes)
    if author is None:
        from .ai import author_from_settings

        author = author_from_settings()
    upgrade_scenes(shots, notes, author=author)
    enrich(shots, layers, words, duration, notes, author=author)
