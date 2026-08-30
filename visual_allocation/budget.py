"""AI video budget — Flow VIDEO is credit-capped; Flow IMAGE is free and uncapped."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from visual_director.schema import VisualScene

from .models import AllocationSettings

IMAGE_NEED_BLOCK = frozenset({
    "document",
    "map",
    "evidence",
    "timeline",
})

# Practical candidacy floor for free Flow stills. `flow_image_fit()` builds
# from flow_score (typically 0.1-0.3) plus small bonuses, so the previous
# 0.38 was effectively unreachable: on a real 148-scene project it passed
# 1 of 131 eligible scenes, handing the other 130 to stock by default.
FLOW_IMAGE_FIT_FLOOR = 0.24

VIDEO_NEED_BOOST = frozenset({
    "action",
    "reveal",
    "scientific",
    "scale",
    "process",
})


def ai_budget_limit(scene_count: int, settings: AllocationSettings) -> int:
    """Hard cap for paid Flow video scenes only."""
    n = max(0, int(scene_count))
    mode = (settings.ai_video_budget or "normal").lower()
    if mode == "conservative":
        return max(2, int(n * 0.05))
    if mode == "high":
        return max(12, int(n * 0.18))
    if mode == "custom":
        return max(0, int(settings.ai_video_budget_custom))
    # normal
    return max(6, int(n * 0.12))


def flow_image_soft_cap(scene_count: int, settings: AllocationSettings) -> int:
    """Visual-variety reference point for Flow images — NOT a credit budget.

    Flow images are free, so nothing here rations them: this value only
    tells `select_flow_image_scenes()` roughly where an all-AI look starts,
    and it can never force an otherwise-eligible scene to stock (crossing it
    costs nothing but a framing-variation cue). Kept as a function, and
    still strategy-aware, so `visual_strategy` continues to shape the mix.

    Contrast with `ai_budget_limit()` above, which IS a hard credit cap and
    is deliberately left untouched — Flow VIDEO still costs credits.
    """
    n = max(0, int(scene_count))
    if n <= 0:
        return 0
    strat = (settings.visual_strategy or "automatic").lower()
    if strat == "image_heavy":
        return max(4, int(n * 0.85))
    if strat == "video_heavy":
        return max(2, int(n * 0.45))
    if strat == "balanced":
        return max(3, int(n * 0.70))
    # automatic
    return max(3, int(n * 0.65))


def flow_opportunity_score(
    scene: VisualScene,
    *,
    visual_need: str,
    visual_role: str,
    position: float,
    style_id: str,
    recent_flow: int,
) -> float:
    score = 0.0
    imp = (scene.importance or "normal").lower()
    if imp == "high":
        score += 0.28
    elif imp == "medium":
        score += 0.12

    if visual_need in VIDEO_NEED_BOOST:
        score += 0.22
    if visual_role in ("scientific_visualization", "abstract", "process", "mechanism", "scale"):
        score += 0.2
    if visual_need in IMAGE_NEED_BLOCK:
        score -= 0.35

    treatment = (scene.visual_treatment or "").lower()
    goal = (scene.visual_goal or "").lower()
    desc = (scene.visual_description or "").lower()
    blob = f"{treatment} {goal} {desc}"
    if any(w in blob for w in ("cinematic", "impossible", "visualization", "metaphor", "conceptual")):
        score += 0.18
    if any(w in blob for w in ("archival", "document", "newspaper", "map", "photograph")):
        score -= 0.25

    if position < 0.15:
        score += 0.12
    if style_id in ("premium_documentary", "space_documentary", "future_tech_documentary"):
        score += 0.08
    if style_id in ("history_documentary", "ancient_history_documentary", "military_war_documentary"):
        score -= 0.15
    if style_id == "ai_narration":
        score += 0.1

    pref = (scene.provider_preference or "").lower()
    if pref in ("flow", "flow_video", "flow_image", "video", "image"):
        score += 0.15
    if pref in ("archive", "archive_video", "nasa", "nasa_video"):
        score -= 0.2

    if recent_flow > 0:
        score -= min(0.08 * recent_flow, 0.24)
    return max(0.0, min(1.0, score))


def flow_image_fit(item: Dict[str, Any]) -> float:
    """Emergent suitability for free Flow stills (not a fixed mix target)."""
    need = item.get("need") or ""
    if need in IMAGE_NEED_BLOCK:
        return 0.0

    fit = float(item.get("flow_score") or 0.0)
    if not item.get("prefer_video"):
        fit += 0.12
    role = item.get("role") or ""
    if role in ("abstract", "process", "mechanism", "scientific_visualization"):
        fit += 0.1
    if need in ("explanation", "comparison", "process"):
        fit += 0.08
    if item.get("prefer_video") and need in VIDEO_NEED_BOOST:
        fit -= 0.22
    return max(0.0, min(1.0, fit))


def select_flow_video_scenes(
    prelim: List[Dict[str, Any]],
    scored: List[Tuple[int, float]],
    budget: int,
) -> set[int]:
    """Return scene_ids for paid Flow video — never exceeds budget."""
    if budget <= 0:
        return set()
    by_id = {item["scene"].scene_id: item for item in prelim}
    ordered = sorted(scored, key=lambda row: row[1], reverse=True)
    chosen: set[int] = set()
    for scene_id, score in ordered:
        if score < 0.35:
            continue
        if len(chosen) >= budget:
            break
        item = by_id.get(scene_id)
        if item is None:
            continue
        need = item.get("need") or ""
        if need in IMAGE_NEED_BLOCK:
            continue
        prefer_video = bool(item.get("prefer_video"))
        imp = (item["scene"].importance or "normal").lower()
        video_fit = prefer_video or need in VIDEO_NEED_BOOST or imp == "high"
        if not video_fit and score < 0.5:
            continue
        chosen.add(scene_id)
    return chosen


def select_flow_image_scenes(
    prelim: List[Dict[str, Any]],
    *,
    video_selected: set[int],
    soft_cap: int = 0,
) -> set[int]:
    """Return scene_ids for free Flow images — EVERY image-suitable scene.

    Flow images are free, so there is no budget to ration and nothing here
    may push an eligible scene to stock. Stock image is a fallback for
    scenes Flow cannot serve, not a competitor Flow has to out-score:

        image-suitable scene -> Flow image
        Flow unsuitable/unavailable/failed -> stock image

    `soft_cap` is still accepted (and still computed by
    `flow_image_soft_cap()` for the Brand & Style mix preview) but is
    deliberately NOT applied as a limit: capping here is precisely what
    inverted the priority before, silently sending eligible scenes to
    stock once a quota filled.

    The only exclusions are:
      * the scene already won a paid Flow VIDEO slot, and
      * `flow_image_fit()` is below FLOW_IMAGE_FIT_FLOOR — which includes
        every IMAGE_NEED_BLOCK need (document/map/evidence/timeline),
        scored 0.0, so factual/documentary scenes stay on real media.
    """
    chosen: set[int] = set()
    for item in prelim:
        sid = item["scene"].scene_id
        if sid in video_selected:
            continue
        if flow_image_fit(item) < FLOW_IMAGE_FIT_FLOOR:
            continue
        chosen.add(sid)
    return chosen


def select_flow_scenes(
    scored: List[Tuple[int, float]],
    budget: int,
) -> set[int]:
    """Legacy helper — treats budget as Flow video cap using scores only."""
    if budget <= 0:
        return set()
    ordered = sorted(scored, key=lambda row: row[1], reverse=True)
    chosen: set[int] = set()
    for scene_id, score in ordered:
        if score < 0.35:
            continue
        if len(chosen) >= budget:
            break
        chosen.add(scene_id)
    return chosen
