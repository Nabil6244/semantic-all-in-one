"""Backfill search queries and visual descriptions after Visual Allocation."""

from __future__ import annotations

from typing import List

from visual_director.schema import (
    DOCUMENTARY_VIDEO_TYPES,
    FLOW_ASSET_TYPES,
    SEARCH_ASSET_TYPES,
    VisualPlan,
    VisualScene,
    unique_search_queries,
)


def scene_prompt_hint(scene: VisualScene, *, max_words: int = 12) -> str:
    """Best available text for stock search or Flow generation."""
    for candidate in (scene.visual_description, scene.visual_goal, scene.narration):
        text = " ".join((candidate or "").split()).strip()
        if len(text) >= 8:
            return _trim_words(text, max_words)
    return _trim_words(scene.narration or "documentary b-roll scene", max_words)


def _trim_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def _broader_query(primary: str, narration: str) -> str:
    words = (narration or "").split()
    if len(words) >= 6:
        alt = _trim_words(" ".join(words[:10]), 10)
        if alt.lower() != primary.lower():
            return alt
    parts = primary.split()
    if len(parts) > 4:
        return " ".join(parts[:6])
    return f"{primary} documentary"


def synthesize_search_queries(scene: VisualScene, asset_type: str) -> List[str]:
    hint = scene_prompt_hint(scene)
    queries = unique_search_queries(list(scene.search_queries))
    if not queries:
        queries = [hint]
    if asset_type in DOCUMENTARY_VIDEO_TYPES:
        if len(queries) < 2:
            broader = _broader_query(queries[0], scene.narration)
            queries = unique_search_queries(queries + [broader])
        if len(queries) < 2:
            queries = unique_search_queries(queries + [_trim_words(scene.narration, 10)])
    return queries


def demote_local_to_stock(scene: VisualScene) -> None:
    """AI Analyze must not emit manual-only `local` scenes."""
    pref = (scene.provider_preference or "").strip().lower()
    if (scene.asset_type or "").lower() != "local" and pref != "local":
        return
    hint = scene_prompt_hint(scene)
    scene.asset_type = "stock_video"
    scene.provider_preference = "stock_video"
    if not scene.search_queries:
        scene.search_queries = unique_search_queries([hint])
    if not (scene.visual_description or "").strip():
        scene.visual_description = hint


def finalize_scene_prompts(scene: VisualScene) -> None:
    """Ensure scene fields satisfy router/export after allocation type changes."""
    demote_local_to_stock(scene)
    asset_type = (scene.asset_type or "").strip().lower()
    if not asset_type:
        return

    if asset_type in FLOW_ASSET_TYPES:
        if not (scene.visual_description or "").strip():
            scene.visual_description = scene_prompt_hint(scene, max_words=80)
        return

    if asset_type in SEARCH_ASSET_TYPES or asset_type in DOCUMENTARY_VIDEO_TYPES:
        scene.search_queries = synthesize_search_queries(scene, asset_type)
        if not (scene.visual_description or "").strip():
            scene.visual_description = scene.search_queries[0]


def finalize_plan_prompts(plan: VisualPlan) -> None:
    for scene in plan.scenes:
        finalize_scene_prompts(scene)
