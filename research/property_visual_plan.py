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


def _wants_youtube_location(beat: PropertyBeat) -> bool:
    """Narrow, explicit trigger: only a genuine geography/access beat with a
    real place name to search on. Never used just because a scene lacks
    property media — that stays stock's job."""
    intent = beat.intent
    if intent is None or intent.visual_purpose != "location_context":
        return False
    # build_visual_intent's LOCATION branch sets subject to
    # "regional access / setting near {place}", falling back to literal
    # "near the area" when neither a proper noun in the narration nor the
    # listing's own city/state resolved to a real place (see
    # property_script.build_visual_intent). Only a real place name makes
    # YouTube's location/community search meaningfully better than stock.
    subject = (intent.subject or "").strip().lower()
    return bool(subject) and not subject.endswith("near the area")


def _asset_type_for(beat: PropertyBeat, has_scoped_media: bool) -> str:
    """Concrete asset_type for this beat, or "" to hand the decision to the
    existing allocation engine."""
    if beat.preferred_source == SOURCE_RESEARCH and has_scoped_media:
        return "research"
    if beat.preferred_source == SOURCE_STOCK:
        if _wants_youtube_location(beat):
            return "youtube_video"
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

    # A beat left at asset_type="" is handed to the existing visual_allocation
    # engine (see module docstring). That engine's infer_visual_need() reads
    # visual_description/visual_goal text through its own generic role-hint
    # matcher (style_engine.visual_selection._ROLE_HINTS) — unchanged here.
    # This just makes sure the WHY signal we already computed (visual_purpose)
    # is legible to that existing matcher as an ordinary hint word, the same
    # way any other scene's description would be.
    _PURPOSE_ROLE_HINT = {
        "lifestyle": "atmosphere cinematic broll",
        "atmosphere": "atmosphere cinematic broll",
        "scenic_context": "establishing landscape wide",
        "transition": "transition montage",
    }

    scenes: List[VisualScene] = []
    scope: Dict[str, str] = {}

    for i, beat in enumerate(beats, start=1):
        scoped_media = has_media_for(beat.property_id)
        asset_type = _asset_type_for(beat, scoped_media)
        intent = beat.intent

        # Stock/YouTube scenes search on the INTENT, not the raw narration.
        query = ""
        if intent is not None:
            query = intent.flow_prompt
            if asset_type in ("stock_video", "youtube_video"):
                query = intent.stock_query
        description = intent.subject if intent is not None else ""
        if asset_type == "" and intent is not None and intent.visual_purpose in _PURPOSE_ROLE_HINT:
            description = f"{description} {_PURPOSE_ROLE_HINT[intent.visual_purpose]}".strip()

        if beat.property_id:
            scope[str(i)] = beat.property_id

        provider_preference = ""
        fallbacks = [beat.fallback_source] if beat.fallback_source else []
        if asset_type == "research":
            provider_preference = "research"
        elif asset_type == "youtube_video":
            provider_preference = "youtube"
            fallbacks = ["stock_video"]  # AssetManager honors this on a real YouTube miss.

        scenes.append(
            VisualScene(
                scene_id=i,
                narration=beat.narration,
                visual_goal=(intent.subject if intent is not None else beat.category.value),
                visual_description=description,
                asset_type=asset_type,
                provider_preference=provider_preference,
                search_queries=([query] if query else []),
                timestamp_needed=False,
                timestamp_hint="",
                duration=0.0,
                importance="normal",
                fallbacks=fallbacks,
                visual_treatment=beat.reason,
                transition="cut",
            )
        )
    return VisualPlan(topic=topic, scenes=scenes), scope
