"""Scene visual need — reuse Style Intelligence 3.0 profile signals."""

from __future__ import annotations

import re

from providers.base import SceneRow
from style_engine.visual_profile import build_scene_visual_profile
from style_engine.schema import ResolvedStyle

from .models import VISUAL_NEEDS

_ROLE_TO_NEED = {
    "establishing": "establishing",
    "event": "action",
    "archival_evidence": "evidence",
    "person": "character",
    "character": "character",
    "location": "location",
    "object": "explanation",
    "process": "process",
    "mechanism": "process",
    "map": "map",
    "timeline": "timeline",
    "comparison": "comparison",
    "scale": "scale",
    "data": "explanation",
    "document": "document",
    "quote": "document",
    "atmosphere": "atmosphere",
    "abstract": "explanation",
    "reaction": "action",
    "scientific_visualization": "scientific",
    "transition": "atmosphere",
}

_ACTION = re.compile(r"\b(launch|explod|ignit|fight|run|rush|crash|fall|rise)\b", re.I)
_REVEAL = re.compile(r"\b(revealed|discovered|breakthrough|changed everything|turned out)\b", re.I)
_REFLECT = re.compile(r"\b(looking back|in the end|ultimately|legacy|remember)\b", re.I)


def infer_visual_need(
    narration: str,
    visual_goal: str = "",
    visual_description: str = "",
    importance: str = "normal",
    resolved: ResolvedStyle | None = None,
) -> str:
    row = SceneRow(
        scene_number="0",
        script_segment=narration,
        prompt=visual_description or visual_goal,
        visual_description=visual_description,
    )
    profile = build_scene_visual_profile(row, resolved)
    need = _ROLE_TO_NEED.get(profile.visual_role, "establishing")
    text = f"{narration} {visual_goal} {visual_description}"
    if _REVEAL.search(text):
        need = "reveal"
    elif _ACTION.search(text):
        need = "action"
    elif _REFLECT.search(text):
        need = "reflection"
    if need not in VISUAL_NEEDS:
        need = "establishing"
    return need
