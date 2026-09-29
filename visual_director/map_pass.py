"""Add full-screen map scenes to an AI visual plan (normal mode).

When a line places the story somewhere real ("...in the Florida Panhandle"),
its scene becomes an animated satellite map, like the reference style's map
shots — the same conservative detector as the Local Visual Planner
(map_scene.detect: bundled borders only, the name must be used as a place).
At most one map per ~30 s of narration and never two scenes in a row.

In a countdown script ("35. The Roof of Florida. ..."), each fact opens on
a map of the place that fact is about, like the reference style — when any
line of the fact names one.

Only AI-planned scenes are changed; a CSV the user wrote is never touched.
"""

from __future__ import annotations

from typing import Callable, Optional

MIN_GAP_S = 30.0
_WORDS_PER_SECOND = 2.5
_KEEP_TYPES = {"map", "local", "local_image", "local_video", "research"}


def add_map_scenes(plan, *, detect: Optional[Callable] = None, min_gap_s: float = MIN_GAP_S) -> int:
    """Turn qualifying scenes of ``plan`` into map scenes in place. Returns how many."""
    scenes = list(getattr(plan, "scenes", []) or [])
    if any((s.asset_type or "").lower() == "research" for s in scenes):
        return 0  # Property Video plans show the researched listing's own media
    context = " ".join(s.narration or "" for s in scenes)
    if detect is None or getattr(detect, "__name__", "") == "detect_map_place":
        from map_scene.detect import detect_map_place as _plain

        detect = (lambda text, _p=_plain: _p(text, context=context))
    fact_maps = _fact_opening_maps(scenes, detect, context)
    t, last_map_at, prev_map, added = 0.0, None, False, 0
    for index, scene in enumerate(scenes):
        narration = (scene.narration or "").strip()
        start = t
        t += float(scene.duration or 0) or len(narration.split()) / _WORDS_PER_SECOND
        asset_type = (scene.asset_type or "").lower()
        if asset_type in _KEEP_TYPES:
            prev_map = asset_type == "map"
            last_map_at = start if prev_map else last_map_at
            continue
        pick = fact_maps.get(index) if not prev_map else None
        if pick is None:
            if prev_map or (last_map_at is not None and start - last_map_at < min_gap_s):
                prev_map = False
                continue
            try:
                pick = detect(narration)
            except Exception:
                pick = None
        if pick is None:
            prev_map = False
            continue
        scene.asset_type = "map"
        scene.provider_preference = "map"
        scene.visual_description = pick.prompt
        scene.visual_goal = f"Map of {pick.name}"
        scene.search_queries = []
        scene.fallbacks = []
        last_map_at, prev_map, added = start, True, added + 1
    return added


def _fact_opening_maps(scenes, detect, context: str = "") -> dict:
    """scene index -> MapPick for each countdown fact's first scene: the place
    its title names ("35. The Roof of Florida"), else the first place named
    anywhere in that fact."""
    try:
        from editorial.countdown import detect_countdown
        from map_scene.detect import detect_place_in_title

        countdown = detect_countdown([s.narration or "" for s in scenes])
    except Exception:
        countdown = None
    if countdown is None:
        return {}
    facts = sorted(countdown.facts, key=lambda f: f.scene_index)
    starts = [f.scene_index for f in facts]
    picks = {}
    for i, fact in enumerate(facts):
        if fact.scene_index in picks:
            continue
        end = starts[i + 1] if i + 1 < len(starts) else len(scenes)
        pick = detect_place_in_title(fact.title, context=context)
        for scene in ([] if pick else scenes[fact.scene_index:end]):
            try:
                pick = detect(scene.narration or "")
            except Exception:
                pick = None
            if pick is not None:
                break
        if pick is not None:
            picks[fact.scene_index] = pick
    return picks
