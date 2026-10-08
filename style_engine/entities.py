"""Recurring figures: a style's canonical visual descriptions, added to the AI prompts of the CSV scenes that name them.

The CSV stays the production contract. Enrichment only appends a fixed block to the prompt of an AI scene whose own
narration or prompt names a figure (Enoch, the Watchers, Semjaza ...), so the same figure looks the same in every AI
scene. It never creates, removes, reorders or retypes a scene, never touches a real-source search (stock, archive,
artwork), and leaves every scene that names no figure exactly as it was. Running it twice gives the same prompt.
A style without `entities` is never touched."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

AI_ASSET_TYPES = frozenset({"image", "video", "flow_image", "flow_video"})
MARK = "Recurring figures --"


def _pattern(name: str) -> re.Pattern:
    return re.compile(r"(?<![\w'])" + re.escape(name.lower()) + r"(?![\w'])")


def referenced(text: str, entities: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The entities a text names (by id or alias, whole words, case-insensitive), in the style's own order; phrases an
    entity lists under `not_when` ("book of enoch") do not count as naming it."""
    low = (text or "").lower()
    out = []
    for e in entities:
        t = low
        for phrase in e.get("not_when") or []:
            t = t.replace(str(phrase).lower(), " ")
        names = [str(e.get("name") or e.get("id") or "")] + [str(a) for a in e.get("aliases") or []]
        if any(n and _pattern(n).search(t) for n in names):
            out.append(e)
    return out


def _block(found: List[Dict[str, Any]]) -> str:
    parts = []
    for e in found:
        rules = "; ".join(str(r) for r in e.get("visual_rules") or [])
        parts.append(f"{e.get('name') or e['id']}: {e['canonical_description']}" + (f" ({rules})" if rules else "") + ".")
    return f"{MARK} " + " ".join(parts)


def enrich_prompt(prompt: str, narration: str, entities: List[Dict[str, Any]]) -> str:
    """The prompt with the canonical descriptions of the figures this scene names. Unchanged when it names none."""
    prompt = prompt or ""
    base = prompt.split(f" {MARK}", 1)[0] if MARK in prompt else prompt
    found = referenced(f"{narration} {base}", entities)
    if not found:
        return base if MARK in prompt else prompt
    return f"{base.rstrip()} {_block(found)}"


def enrich_plan(plan: Any, entities: Optional[List[Dict[str, Any]]]) -> int:
    """Enrich the AI scenes of a VisualPlan in place (their visual description is the CSV prompt). Returns how many
    prompts changed. Scenes keep their number, order, narration and asset type."""
    if not entities:
        return 0
    changed = 0
    for scene in plan.scenes:
        if str(scene.asset_type or "") not in AI_ASSET_TYPES:
            continue
        new = enrich_prompt(scene.visual_description, scene.narration, entities)
        if new != scene.visual_description:
            scene.visual_description = new
            changed += 1
    return changed
