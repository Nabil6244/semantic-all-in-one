"""Overscaled SceneGraph generation from the EXISTING production CSV contract.

    Existing CSV (scene_number, script_segment, asset_type, prompt)
        -> providers.base.SceneRow (existing, unchanged)
        -> SceneGraph semantic intent (this module)
        -> [not implemented yet: layout / composition / EditorialTimeline]

This module does not read or parse CSV files itself — it consumes
``providers.base.SceneRow`` objects, the SAME normalized row type the
existing renderer/router already use, so the CSV contract and its parser
(``csv.DictReader`` + ``SceneRow.from_csv_row``) are untouched.

Two independent generation paths, both returning the same
``SceneGraphGenerationResult`` shape so callers never have to special-case:

  - ``generate_scene_graph_heuristic`` — deterministic, no network, no LLM.
    Maps each SceneRow's existing asset_type/prompt into a SceneNode, derives
    a semantic_role, and links a simple "design flaw -> consequence" causal
    edge when narration signals it. Always available; used as the safe
    fallback and for tests.

  - ``generate_scene_graph_with_llm`` — an ISOLATED Overscaled adapter around
    the existing ``visual_director.llm.LLMProvider`` protocol (the same
    ``complete(system, user) -> str`` seam ``GeminiLLM``/``StaticLLM`` already
    implement). It never imports or touches ``visual_director/director.py``,
    never changes its global prompt, and never touches the ``VisualScene``
    contract — this is a separate prompt/schema entirely. Model output is
    required to be SceneGraph-shaped JSON and is rejected (not silently
    accepted) unless it round-trips through ``SceneGraph.from_dict`` and
    passes ``SceneGraph.validate()`` cleanly.

``generate_scene_graph`` ties them together: try the injected LLM (if any),
fall back to the heuristic generator on ANY failure (bad JSON, invalid
SceneGraph, network/auth error). Nothing here can break the existing
pipeline — on failure it returns a result with ``ok=False`` and the caller
decides what to do; it never raises past this module and never fabricates a
SceneGraph from incomplete data.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import List, Optional, Sequence

from providers.base import SceneRow
from visual_director.llm import LLMError, LLMProvider

from .schema import (
    CameraKeyframe,
    CaptionSpec,
    SceneEdge,
    SceneGraph,
    SceneGraphAction,
    SceneGraphBeat,
    SceneNode,
)

# --- asset_type -> node.type -------------------------------------------------
# Preserves the EXISTING asset contract values verbatim in SceneNode.asset_source;
# this table only decides the composition node "shape", never the source itself.
_IMAGE_NODE_TYPES = frozenset(
    {"image", "flow_image", "stock_image", "commons_image", "local_image", "local", ""}
)
_VIDEO_LOOP_NODE_TYPES = frozenset(
    {
        "video",
        "flow_video",
        "stock_video",
        "youtube_video",
        "archive_video",
        "nasa_video",
        "commons_video",
        "local_video",
        "stock",
    }
)

_DIAGRAM_KEYWORDS = ("diagram", "schematic", "cross section", "cross-section", "blueprint")
_DESIGN_FLAW_KEYWORDS = (
    "but ", "however", "problem", "flaw", "too narrow", "too small", "too weak",
    "couldn't", "could not", "wasn't enough", "was not enough", "failed to",
    "not enough", "not strong enough",
)
_ARCHIVAL_ASSET_TYPES = frozenset(
    {"youtube_video", "archive_video", "nasa_video", "commons_video", "commons_image"}
)

WORDS_PER_SECOND = 2.5  # ~150 wpm narration pace; a placeholder ordering signal
MIN_ROW_DURATION_S = 1.5


def _node_type_for_asset_type(asset_type: str) -> str:
    key = str(asset_type or "").strip().lower()
    if key in _VIDEO_LOOP_NODE_TYPES:
        return "video_loop"
    return "image"  # covers _IMAGE_NODE_TYPES and any unrecognized value (safe default)


def _has_any(text: str, keywords: Sequence[str]) -> Optional[str]:
    lower = str(text or "").lower()
    for kw in keywords:
        if kw in lower:
            return kw
    return None


def _classify_semantic_role(
    *, index: int, total: int, script_segment: str, prompt: str, asset_type: str, node_type: str
) -> str:
    combined = f"{script_segment} {prompt}"
    if _has_any(combined, _DIAGRAM_KEYWORDS):
        return "diagram"
    if _has_any(script_segment, _DESIGN_FLAW_KEYWORDS):
        return "design_flaw"
    if index == 0:
        return "title"
    if total > 1 and index == total - 1:
        return "final_still"
    if str(asset_type or "").strip().lower() in _ARCHIVAL_ASSET_TYPES:
        return "archival"
    if node_type == "video_loop":
        return "video_loop"
    if index <= 2:
        return "establisher"
    return "detail"


def _short_caption_text(script_segment: str, *, max_chars: int = 90) -> str:
    text = str(script_segment or "").strip()
    # First sentence only, for a "short declarative caption" (style guidance,
    # not enforced elsewhere in this module).
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0] if text else ""
    first = first or text
    if len(first) <= max_chars:
        return first
    truncated = first[:max_chars].rsplit(" ", 1)[0]
    return (truncated or first[:max_chars]).rstrip(",;:") + "..."


def _caption_for_row(script_segment: str, *, highlight_keyword: Optional[str]) -> CaptionSpec:
    caption_text = _short_caption_text(script_segment)
    highlight = None
    if highlight_keyword:
        stripped = highlight_keyword.strip()
        # Only ever set a highlight that is a verbatim substring of the
        # caption we actually produced — never fabricate one.
        if stripped and stripped.lower() in caption_text.lower():
            start = caption_text.lower().index(stripped.lower())
            highlight = caption_text[start:start + len(stripped)]
    return CaptionSpec(text=caption_text, highlight=highlight)


@dataclasses.dataclass
class SceneGraphGenerationResult:
    """Uniform outcome for both the heuristic and LLM generation paths.

    ``ok=False`` means the caller should fall back to the existing pipeline
    unchanged — this never raises and never hands back a half-built graph.
    """

    ok: bool
    scene_graph: Optional[SceneGraph]
    errors: List[str]
    source: str  # "heuristic" | "llm" | "heuristic_fallback_after_llm_failure"


def scene_rows_from_csv_rows(csv_rows: Sequence[dict]) -> List[SceneRow]:
    """Thin pass-through to the EXISTING row normalizer — no new CSV parsing."""

    return [SceneRow.from_csv_row(dict(r)) for r in csv_rows]


def generate_scene_graph_heuristic(
    segment_id: str,
    rows: Sequence[SceneRow],
    *,
    title: str = "",
    style_preset: str = "overscaled",
) -> SceneGraphGenerationResult:
    """Deterministic, network-free SceneGraph generation from existing SceneRows.

    One row maps to at most one SceneNode (this path does not attempt
    semantic decomposition of a sentence into several nodes — that's what
    the LLM path is for); a row with no asset_type and no prompt/stock query
    produces a beat with narration but no visual action ("no visual node").
    """

    total = len(rows)
    nodes: List[SceneNode] = []
    edges: List[SceneEdge] = []
    camera_keyframes: List[CameraKeyframe] = []
    beats: List[SceneGraphBeat] = []

    cursor = 0.0
    pending_flaw_node_id: Optional[str] = None
    pending_flaw_keyword: Optional[str] = None

    for index, row in enumerate(rows):
        script_segment = row.script_segment or ""
        word_count = len(script_segment.split())
        duration = max(MIN_ROW_DURATION_S, word_count / WORDS_PER_SECOND)
        start = cursor
        end = cursor + duration
        cursor = end

        asset_type = row.asset_type or ""
        prompt_or_stock = row.prompt or row.stock or ""
        has_asset_info = bool(asset_type) or bool(prompt_or_stock)

        actions: List[SceneGraphAction] = []
        node_id: Optional[str] = None

        if has_asset_info:
            node_type = _node_type_for_asset_type(asset_type)
            flaw_kw = _has_any(script_segment, _DESIGN_FLAW_KEYWORDS)
            semantic_role = _classify_semantic_role(
                index=index,
                total=total,
                script_segment=script_segment,
                prompt=prompt_or_stock,
                asset_type=asset_type,
                node_type=node_type,
            )

            # A row right after a design_flaw row is its narrative consequence.
            if pending_flaw_node_id is not None:
                semantic_role = "consequence"

            node_id = f"n{row.scene_number or index + 1}"
            caption = _caption_for_row(
                script_segment,
                highlight_keyword=flaw_kw if semantic_role == "design_flaw" else None,
            )
            node = SceneNode(
                id=node_id,
                type=node_type,
                semantic_role=semantic_role,
                asset_source=asset_type,
                asset_reference=prompt_or_stock,
                appear_at=round(start, 4),
            )
            if caption.text:
                node.caption = caption
            nodes.append(node)

            actions.append(SceneGraphAction(type="reveal_node", action_id=f"a_reveal_{node_id}", node_id=node_id))

            if semantic_role == "consequence" and pending_flaw_node_id is not None:
                edge_id = f"e_{pending_flaw_node_id}_{node_id}"
                edges.append(
                    SceneEdge(
                        id=edge_id,
                        from_node=pending_flaw_node_id,
                        to_node=node_id,
                        style="hand_drawn",
                        draw_at=round(start, 4),
                    )
                )
                actions.append(
                    SceneGraphAction(type="draw_edge", action_id=f"a_draw_{edge_id}", edge_id=edge_id)
                )
                pending_flaw_node_id = None
                pending_flaw_keyword = None

            if semantic_role == "design_flaw":
                pending_flaw_node_id = node_id
                pending_flaw_keyword = flaw_kw

            cam_id = f"cam_{row.scene_number or index + 1}"
            zoom = 1.2 if semantic_role in ("diagram", "design_flaw", "consequence", "detail") else 1.0
            camera_keyframes.append(
                CameraKeyframe(
                    keyframe_id=cam_id,
                    at=round(start, 4),
                    frame_nodes=[node_id],
                    zoom=zoom,
                )
            )
            actions.append(
                SceneGraphAction(type="move_camera", action_id=f"a_cam_{cam_id}", camera_keyframe_id=cam_id)
            )

        beats.append(
            SceneGraphBeat(
                beat_id=f"beat_{row.scene_number or index + 1}",
                narration=script_segment,
                start=round(start, 4),
                end=round(end, 4),
                actions=actions,
            )
        )

    scene_graph = SceneGraph(
        segment_id=segment_id,
        title=title,
        style_preset=style_preset,
        duration=round(cursor, 4),
        nodes=nodes,
        edges=edges,
        camera_keyframes=camera_keyframes,
        beats=beats,
    )
    errors = scene_graph.validate()
    return SceneGraphGenerationResult(
        ok=not errors, scene_graph=scene_graph, errors=errors, source="heuristic"
    )


# --- LLM-backed path ---------------------------------------------------------

_SYSTEM_PROMPT = """You generate Overscaled-style composition intent as strict JSON.

Overscaled is a whiteboard-collage documentary style: one large persistent
canvas per segment holds image/diagram/video_loop/anchor nodes that appear
over time, connected by causal arrows, with short captions and a camera that
pans/zooms across the canvas.

Output ONE JSON object matching this shape exactly (no prose, no markdown
fences, no extra commentary):

{
  "segment_id": string,
  "title": string,
  "style_preset": string,
  "duration": number,
  "nodes": [{"id": string, "type": "image"|"diagram"|"video_loop"|"anchor",
             "semantic_role": string, "asset_source": string,
             "asset_reference": string, "appear_at": number,
             "caption": {"text": string, "highlight": string|null} | null}],
  "edges": [{"id": string, "from": string, "to": string, "style": string,
             "color": string, "draw_at": number, "duration": number}],
  "camera_keyframes": [{"keyframe_id": string, "at": number,
                          "frame_nodes": [string], "zoom": number}],
  "beats": [{"beat_id": string, "narration": string, "start": number,
              "end": number,
              "actions": [{"type": "reveal_node"|"draw_edge"|"move_camera"|"set_caption",
                            "action_id": string, "node_id": string|null,
                            "edge_id": string|null,
                            "camera_keyframe_id": string|null,
                            "caption": object|null}]}]
}

Hard rules:
- Every node's "asset_source" MUST be copied verbatim from the scene's
  existing asset_type (do not invent a new asset provider vocabulary).
- "semantic_role" is a separate, free-text concept from "asset_source" —
  never put the asset type into semantic_role or vice versa.
- A "highlight" must be a verbatim substring of that caption's "text".
- Do NOT output pixel coordinates, canvas x/y, width/height, FFmpeg filters,
  Pillow/drawing instructions, or timeline events of any kind. Positions and
  final layout are decided by a later stage, not by you.
- Not every scene needs a node; not every sentence needs exactly one node.
- Output valid JSON only.
"""


def _build_user_prompt(
    segment_id: str, rows: Sequence[SceneRow], *, title: str, style_preset: str
) -> str:
    scene_lines = []
    for row in rows:
        scene_lines.append(
            json.dumps(
                {
                    "scene_number": row.scene_number,
                    "script_segment": row.script_segment,
                    "asset_type": row.asset_type,
                    "prompt": row.prompt or row.stock,
                }
            )
        )
    return (
        f"segment_id: {segment_id}\n"
        f"title: {title}\n"
        f"style_preset: {style_preset}\n"
        "Existing CSV scenes (scene_number, script_segment, asset_type, prompt):\n"
        + "\n".join(scene_lines)
    )


def _extract_json_object(text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"```\s*$", "", stripped).strip()
    return stripped


def generate_scene_graph_with_llm(
    segment_id: str,
    rows: Sequence[SceneRow],
    *,
    llm: LLMProvider,
    title: str = "",
    style_preset: str = "overscaled",
) -> SceneGraphGenerationResult:
    """Isolated Overscaled adapter over the existing LLMProvider seam.

    Never imports visual_director.director, never touches its prompt or the
    VisualScene contract. Any failure (network, bad JSON, invalid SceneGraph)
    is returned as ``ok=False`` — it is never raised past this function and
    never produces a half-valid SceneGraph.
    """

    user_prompt = _build_user_prompt(segment_id, rows, title=title, style_preset=style_preset)
    try:
        raw = llm.complete(_SYSTEM_PROMPT, user_prompt)
    except LLMError as exc:
        return SceneGraphGenerationResult(ok=False, scene_graph=None, errors=[f"LLM error: {exc}"], source="llm")
    except Exception as exc:  # never let an LLM/transport failure escape this module
        return SceneGraphGenerationResult(
            ok=False, scene_graph=None, errors=[f"LLM call failed unexpectedly: {exc}"], source="llm"
        )

    try:
        parsed = json.loads(_extract_json_object(raw))
    except (json.JSONDecodeError, TypeError) as exc:
        return SceneGraphGenerationResult(
            ok=False, scene_graph=None, errors=[f"LLM did not return valid JSON: {exc}"], source="llm"
        )
    if not isinstance(parsed, dict):
        return SceneGraphGenerationResult(
            ok=False, scene_graph=None, errors=["LLM JSON must be an object, not a list/scalar"], source="llm"
        )

    scene_graph = SceneGraph.from_dict(parsed)
    errors = scene_graph.validate()
    if errors:
        return SceneGraphGenerationResult(ok=False, scene_graph=None, errors=errors, source="llm")
    return SceneGraphGenerationResult(ok=True, scene_graph=scene_graph, errors=[], source="llm")


def generate_scene_graph(
    segment_id: str,
    rows: Sequence[SceneRow],
    *,
    title: str = "",
    style_preset: str = "overscaled",
    llm: Optional[LLMProvider] = None,
) -> SceneGraphGenerationResult:
    """Try the injected LLM (if any); always fall back to the safe heuristic.

    With no ``llm`` supplied this is 100% deterministic and offline — the
    default for tests and for any caller that hasn't wired up Gemini yet.
    """

    if llm is not None:
        llm_result = generate_scene_graph_with_llm(
            segment_id, rows, llm=llm, title=title, style_preset=style_preset
        )
        if llm_result.ok:
            return llm_result
        fallback = generate_scene_graph_heuristic(
            segment_id, rows, title=title, style_preset=style_preset
        )
        fallback.errors = list(llm_result.errors) + list(fallback.errors)
        fallback.source = "heuristic_fallback_after_llm_failure"
        return fallback
    return generate_scene_graph_heuristic(segment_id, rows, title=title, style_preset=style_preset)
