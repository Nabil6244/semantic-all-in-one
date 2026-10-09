"""Modern Tech News: an independent editorial system for technology videos.

It owns the editorial decisions only: it writes guidance for the existing VisualDirector and refines the VisualPlan
that comes back (pacing, product-first prompts, source routing). The Normal pipeline does the production: the same
4-column CSV, asset providers, graphics, EditorialTimeline and renderer. Selected per project, never auto-detected.
"""

from .editorial import (
    EDITING_SYSTEM,
    SceneContext,
    StoryContext,
    build_story,
    is_relevant,
    scene_context,
    search_query,
    analyze_scene,
    classify_concept,
    classify_evidence,
    editorial_guidance,
    flow_generations,
    refine_plan,
    smart_editing_settings,
)

__all__ = [
    "EDITING_SYSTEM",
    "SceneContext",
    "StoryContext",
    "build_story",
    "is_relevant",
    "scene_context",
    "search_query",
    "flow_generations",
    "analyze_scene",
    "classify_concept",
    "classify_evidence",
    "editorial_guidance",
    "refine_plan",
    "smart_editing_settings",
]
