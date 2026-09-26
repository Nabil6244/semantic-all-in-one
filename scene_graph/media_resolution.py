"""Bridge SceneNode.asset_source/asset_reference to the EXISTING media
resolution system (Flow / Pexels / YouTube / local) — no second provider
implementation.

Reuses ``video_generator.resolve_scene_assets()`` verbatim: the same
function the normal CSV workflow already calls, which itself routes through
the existing ``providers.base.SceneRow`` / ``providers.router`` /
``asset_manager.AssetManager`` stack, unchanged. This module's only job is
the two small adapter steps ``resolve_scene_assets`` does not do on its own:

  1. turn each SceneNode into the same CSV-row-shaped dict that function
     already expects (scene_number, script_segment, asset_type, prompt) —
     using node.asset_source as asset_type and node.asset_reference as
     prompt, so the existing flow_image/flow_video/stock_image/stock_video/
     youtube_video contract is preserved exactly (never reinterpreted, never
     converted into semantic_role or vice versa).
  2. read the numbered files it wrote back out via the existing
     ``find_image_for_scene`` and hand back a ``{node_id: path}`` dict —
     scene_graph.layout/composition's own contract.

``resolve_scene_assets`` requires a numeric scene_number (it writes/reads
``images_dir/00N.<ext>``); the Overscaled compiler already stashes each
node's originating CSV scene_number in ``node.metadata["scene_number"]``
for exactly this purpose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .schema import SceneGraph

# Node types that never carry a resolvable external asset (nothing to fetch).
# "checklist_item" is Exp Solar-only (scene_graph.exp_solar_csv's own
# beat=checklist rows — see schema.KNOWN_NODE_TYPES; Overscaled's CSV/
# compiler has no way to produce one) and is structural UI: the persistent
# checklist strip (scene_graph.layout's checklist_windows / composition's
# render_checklist_strip_frame) draws it from node.label/appear_at alone,
# never from resolved media — so it must never enter asset resolution at
# all, rather than needing a placeholder asset_type/prompt just to satisfy
# the resolver. Anchors are NOT included here — they CAN have a real
# asset (the small corner icon) — see spec.
_NON_ASSET_NODE_TYPES = frozenset({"checklist_item"})


def resolve_scene_graph_media(
    scene_graph: SceneGraph,
    *,
    images_dir: Path,
    pexels_api_key: Optional[str] = None,
    flow_engine_manager=None,
    flow_settings: Optional[dict] = None,
    youtube_max_results: int = 5,
    youtube_clip_duration: float = 3.5,
    youtube_transcript_matching: bool = True,
    log=print,
    on_scene_start=None,
    on_scene_complete=None,
    on_scene_generating=None,
    on_manager_ready=None,
) -> Dict[str, str]:
    """Resolve every node's real media file through the EXISTING provider
    stack. Returns {node_id: local_file_path} for whatever actually resolved
    — a node with no asset_source/asset_reference (or one the existing
    providers couldn't resolve) is simply absent from the result, and
    scene_graph.composition already renders a placeholder for that case."""

    import video_generator as vg

    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    scene_number_to_node_id: Dict[str, str] = {}
    for node in scene_graph.nodes:
        if node.type in _NON_ASSET_NODE_TYPES:
            continue
        scene_number = str(node.metadata.get("scene_number") or "").strip()
        if not scene_number or not (node.asset_source or node.asset_reference):
            continue
        scene_number_to_node_id[scene_number] = node.id
        rows.append({
            "scene_number": scene_number,
            "script_segment": node.caption.text if node.caption else "",
            "asset_type": node.asset_source,
            "prompt": node.asset_reference,
        })

    if not rows:
        return {}

    vg.resolve_scene_assets(
        rows, images_dir,
        pexels_api_key=pexels_api_key,
        flow_engine_manager=flow_engine_manager,
        flow_settings=flow_settings,
        youtube_max_results=youtube_max_results,
        youtube_clip_duration=youtube_clip_duration,
        youtube_transcript_matching=youtube_transcript_matching,
        log=log,
        on_scene_start=on_scene_start,
        on_scene_complete=on_scene_complete,
        on_scene_generating=on_scene_generating,
        on_manager_ready=on_manager_ready,
    )

    resolved: Dict[str, str] = {}
    for scene_number, node_id in scene_number_to_node_id.items():
        found = vg.find_image_for_scene(images_dir, scene_number)
        if found is not None:
            resolved[node_id] = str(found)
    return resolved
