"""AI video budget — score opportunities; Flow video is credit-capped, Flow image is soft-capped."""

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
    """Upper ceiling for free Flow images — selection stays score-driven below this."""
    n = max(0, int(scene_count))
    if n <= 0:
        return 0
    strat = (settings.visual_strategy or "automatic").lower()
    if strat == "image_heavy":
        return max(4, int(n * 0.45))
    if strat == "video_heavy":
        return max(2, int(n * 0.12))
    if strat == "balanced":
        return max(3, int(n * 0.28))
    # automatic
    return max(3, int(n * 0.22))


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
    soft_cap: int,
) -> set[int]:
    """Return scene_ids for free Flow images — score-driven with a soft ceiling."""
    if soft_cap <= 0:
        return set()
    candidates: List[Tuple[int, float]] = []
    for item in prelim:
        scene = item["scene"]
        sid = scene.scene_id
        if sid in video_selected:
            continue
        fit = flow_image_fit(item)
        if fit < 0.38:
            continue
        candidates.append((sid, fit))
    ordered = sorted(candidates, key=lambda row: row[1], reverse=True)
    chosen: set[int] = set()
    for sid, fit in ordered:
        if len(chosen) >= soft_cap:
            break
        # Soft cap tightens as we approach the ceiling — emergent, not a fixed quota.
        if soft_cap > 0:
            ratio = len(chosen) / soft_cap
            if ratio >= 0.85 and fit < 0.55:
                continue
            if ratio >= 0.7 and fit < 0.48:
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
