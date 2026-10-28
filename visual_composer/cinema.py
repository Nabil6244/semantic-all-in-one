"""StarMap Cinema adapter: the same pass on a compiled Cinema spec (spec["layers"], spec["footage"], plan.beats / plan.words).

Called once from starmap.cinema.apply after variety (see docs/visual_composer.md). Everything it adds is a tm_template layer over what is on screen."""

from __future__ import annotations

import re
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Dict, List

from . import apply as vc
from .relevance import shot_subject_tokens, _stem

MODEL_LAYERS = ("cinema_craft", "cinema_globe")


def _beat_text(plan: Any, a: float, b: float) -> str:
    return " ".join(str(x.text) for x in plan.beats if x.text and x.start < b and a < x.end)


def gate_layers(spec: Dict[str, Any], plan: Any, notes: List[str]) -> int:
    """A cinema_craft / cinema_globe layer (and its caption) whose beat does not name it is removed: the footage underneath stays."""
    from whatif import variety

    layers, drop = spec["layers"], []
    for L in layers:
        if L.get("type") not in MODEL_LAYERS or not L.get("_cite"):
            continue
        name = SimpleNamespace(name=str(L["_cite"]).split(" OF ")[-1].replace("NASA TEXTURE MAP", ""), model=str(L.get("model", "")).replace("wi:", ""),
                               texture=str(L.get("texture", "")), kind="craft" if L["type"] == "cinema_craft" else "globe")
        near = _beat_text(plan, float(L["start"]) - 6.0, float(L["end"]) + 6.0)
        said = {_stem(w) for w in re.findall(r"[A-Za-z]{3,}", near)}
        toks = shot_subject_tokens(name)
        if toks and not any(t in said for t in toks) and not variety.CARRY.search(near):
            drop.append(L)
    for L in drop:
        layers.remove(L)
        layers[:] = [c for c in layers if not (c.get("type") == "tm_caption" and abs(float(c["start"]) - float(L["start"]) - 0.4) < 0.05 and c.get("over_footage"))]
    if drop:
        notes.append(f"Cinema relevance: {len(drop)} 3D shot(s) not about their narration removed (the footage under them stays)")
    return len(drop)


ENGINE_FILE = Path(__file__).resolve().parent.parent / "starmap-engine" / "page.js"
SCENE_SHARE_MAX = 0.45
THREE_D = ("cinema_craft", "cinema_globe", "cinema_hero", "cinema_scene")


def engine_supports_scene() -> bool:
    """Scene layers are only written when the Cinema engine can draw them (starmap-engine/page.js registers `cinema_scene`)."""
    try:
        return "cinema_scene" in ENGINE_FILE.read_text(encoding="utf-8")
    except OSError:
        return False


def _scene_layer(a: float, z: float, scene_spec: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "cinema_scene", "scene_spec": scene_spec, "start": round(a, 3), "end": round(z, 3), "fade_in": 0.2, "fade_out": 0.25, "over_footage": True, "z": 2}


def scenes(spec: Dict[str, Any], plan: Any, notes: List[str], *, author: Any = None) -> int:
    """A footage beat whose sentence describes something drawable (a world, a craft, the air around it, an interior, a field) is drawn as a 3D scene
    generated for it (what If's scene composer), over the footage. Not next to another 3D shot, not over a "photo" claim, at most SCENE_SHARE_MAX of the footage."""
    from whatif import planner as wp
    from . import scene as scene_mod
    from .apply import MAX_AI_CALLS, SCENE_MIN_CONF
    from .concepts import content_words

    if not engine_supports_scene():
        return 0
    layers, footage = spec["layers"], sorted(spec.get("footage") or [], key=lambda x: float(x["start"]))
    spans = lambda: [(float(L["start"]), float(L["end"])) for L in layers if L.get("type") in THREE_D]      # noqa: E731
    taken, made, asked = len(spans()), 0, 0
    for f in footage:
        a, z = float(f["start"]), float(f["end"])
        text = _beat_text(plan, a, z)
        if z - a < 3.0 or not text or wp.PHOTO.search(text):
            continue
        if any(x < z + 3.0 and a - 3.0 < y for x, y in spans()):
            continue
        if (taken + made + 1) / max(1, len(footage)) > SCENE_SHARE_MAX:
            break
        got = scene_mod.scene_for(text)
        if (not got or got[1] < SCENE_MIN_CONF) and author is not None and asked < MAX_AI_CALLS and len(content_words(text)) >= 5:
            asked += 1
            got = scene_mod.author(text, author) or got
        if not got or got[1] < SCENE_MIN_CONF:
            continue
        layers.append(_scene_layer(a, z, got[0]))
        made += 1
    if made:
        notes.append(f"Cinema scenes: {made} footage shot(s) drawn as a 3D scene generated from their sentence")
    return made


def enrich_spec(spec: Dict[str, Any], plan: Any, notes: List[str]) -> int:
    from starmap.cinema import _wi_words

    gate_layers(spec, plan, notes)
    from .ai import author_from_settings

    scenes(spec, plan, notes, author=author_from_settings())
    words = _wi_words(plan)
    layers = spec["layers"]
    hosts = [SimpleNamespace(kind="image", start=float(f["start"]), end=float(f["end"])) for f in (spec.get("footage") or [])]
    hosts += [SimpleNamespace(kind="plate" if L["type"] == "cinema_plate" else "craft", start=float(L["start"]), end=float(L["end"]))
              for L in layers if L.get("type") in ("cinema_plate",) + THREE_D]
    dur = float(spec.get("duration") or 0) or max((float(L.get("end", 0)) for L in layers), default=0.0)
    return vc.enrich(hosts, layers, words, dur, notes)
