"""Map scenes in Overscaled / Exp Solar: a node whose asset_source is "map".

Version 1 shows a map full screen (like the reference style's map shots),
never as a small card:
  * layout gives it the whole frame and the screen to itself (no other cards,
    no arrows, no chapter title band over it; Exp Solar's progress strip
    stays on top),
  * it has no card border, shadow, label or caption — the node's caption
    becomes the map's own label (drawn inside the map clip),
  * the clip holds its last frame if the scene outlasts it.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .schema import SceneGraph, SceneNode

MAP_ASSET_SOURCE = "map"
# A caption longer than this reads as a sentence, not a map label; the map
# then labels the place itself.
LABEL_MAX_WORDS = 6

Window = Tuple[float, float]


def is_map_node(node: SceneNode) -> bool:
    return str(getattr(node, "asset_source", "") or "").strip().lower() == MAP_ASSET_SOURCE


def _with_label(prompt: str, caption: str) -> str:
    prompt = (prompt or "").strip()
    text = " ".join((caption or "").split())
    if not text or len(text.split()) > LABEL_MAX_WORDS:
        return prompt
    options = [p.strip().lower() for p in prompt.split("|")[1:]]
    if any(o.startswith("label:") for o in options):
        return prompt  # the author already chose one
    return f"{prompt} | label: {text.rstrip('.')}"


def prepare_map_nodes(scene_graph: SceneGraph) -> SceneGraph:
    """Normalize map nodes in place (idempotent) — run before media
    resolution, since the caption is folded into the map prompt."""
    map_ids = set()
    for node in scene_graph.nodes:
        if not is_map_node(node):
            continue
        map_ids.add(node.id)
        node.type = "video_loop"
        node.border = False
        node.shadow = False
        node.label = ""
        if node.caption is not None:
            node.asset_reference = _with_label(node.asset_reference, node.caption.text)
            node.caption = None
    if not map_ids:
        return scene_graph
    dropped = {e.id for e in scene_graph.edges if e.from_node in map_ids or e.to_node in map_ids}
    if dropped:
        scene_graph.edges = [e for e in scene_graph.edges if e.id not in dropped]
        for beat in scene_graph.beats:
            beat.actions = [a for a in beat.actions if not (a.type == "draw_edge" and a.edge_id in dropped)]
    return scene_graph


def subtract_windows(window: Window, cuts: Sequence[Window], *, min_len: float = 0.5) -> List[Window]:
    """``window`` minus every cut, as the remaining pieces (tiny slivers dropped)."""
    pieces = [window]
    for c0, c1 in sorted(cuts):
        nxt = []
        for s, e in pieces:
            if c1 <= s or c0 >= e:
                nxt.append((s, e))
                continue
            if c0 > s:
                nxt.append((s, c0))
            if c1 < e:
                nxt.append((c1, e))
        pieces = nxt
    return [(s, e) for s, e in pieces if e - s >= min_len]
