"""Property Visual Plan — maps analyzed PropertyBeats onto the existing
VisualScene/VisualPlan schema and existing asset providers. Property Video
workflow only; never touches the normal Script Analyzer path.

Two deliberate reuse decisions:

- CINEMATIC beats get no hardcoded asset_type. They're left for the existing
  visual_allocation engine (Flow-video budget / Flow-image soft cap / curve)
  to decide exactly as it would for any normal scene — rather than building
  a second allocation system here.
- Stock scenes carry the *intent-derived* query (see
  property_script.build_visual_intent), never the raw narration, so a price
  or a proper-noun dump never reaches Pexels as a search string.

Property scope travels beside the plan as a scene_number -> property_id map
(the same sidecar pattern AssetManager already uses for coverage_by_scene),
because the CSV schema is unchanged and must stay that way.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from research.library import ResearchLibrary
from research.models import ResearchResult
from research.property_script import (
    SOURCE_FLOW,
    SOURCE_RESEARCH,
    SOURCE_STOCK,
    BeatCategory,
    PropertyBeat,
)
from visual_director.schema import VisualPlan, VisualScene


def _asset_type_for(beat: PropertyBeat, has_scoped_media: bool) -> str:
    """Concrete asset_type for this beat, or "" to hand the decision to the
    existing allocation engine."""
    if beat.preferred_source == SOURCE_RESEARCH and has_scoped_media:
        return "research"
    if beat.preferred_source == SOURCE_STOCK:
        return "stock_video"
    if beat.preferred_source == SOURCE_FLOW:
        return "image"
    # Research preferred but this listing has no usable media -> fall back
    # to relevant stock rather than crashing or forcing another listing's
    # photos in.
    if beat.preferred_source == SOURCE_RESEARCH and not has_scoped_media:
        return "stock_video"
    return ""


def build_property_visual_plan(
    beats: List[PropertyBeat],
    research_result: Optional[ResearchResult] = None,
    *,
    library: Optional[ResearchLibrary] = None,
    topic: str = "",
) -> Tuple[VisualPlan, Dict[str, str]]:
    """Returns (plan, property_scope_by_scene).

    `library` (multi-listing) takes precedence over `research_result`
    (single-listing, backward compatible) when deciding whether a given
    beat's own property actually has usable media.
    """
    def has_media_for(property_id: str) -> bool:
        if library is not None:
            if property_id:
                return bool(library.media_for(property_id))
            return library.has_media()
        return bool(research_result and research_result.has_media())

    scenes: List[VisualScene] = []
    scope: Dict[str, str] = {}

    for i, beat in enumerate(beats, start=1):
        scoped_media = has_media_for(beat.property_id)
        asset_type = _asset_type_for(beat, scoped_media)
        intent = beat.intent

        # Stock scenes search on the INTENT, not the narration.
        query = ""
        if intent is not None:
            query = intent.stock_query if asset_type == "stock_video" else intent.flow_prompt
        description = intent.subject if intent is not None else ""

        if beat.property_id:
            scope[str(i)] = beat.property_id

        scenes.append(
            VisualScene(
                scene_id=i,
                narration=beat.narration,
                visual_goal=(intent.subject if intent is not None else beat.category.value),
                visual_description=description,
                asset_type=asset_type,
                provider_preference=("research" if asset_type == "research" else ""),
                search_queries=([query] if query else []),
                timestamp_needed=False,
                timestamp_hint="",
                duration=0.0,
                importance="normal",
                fallbacks=([beat.fallback_source] if beat.fallback_source else []),
                visual_treatment=beat.reason,
                transition="cut",
            )
        )
    return VisualPlan(topic=topic, scenes=scenes), scope
