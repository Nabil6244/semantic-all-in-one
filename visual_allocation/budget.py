"""AI video budget — score opportunities and enforce hard cap."""

from __future__ import annotations

from typing import List, Tuple

from visual_director.schema import VisualScene

from .models import AllocationSettings


def ai_budget_limit(scene_count: int, settings: AllocationSettings) -> int:
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

    if visual_need in ("action", "reveal", "scientific", "scale", "process"):
        score += 0.22
    if visual_role in ("scientific_visualization", "abstract", "process", "mechanism", "scale"):
        score += 0.2
    if visual_need in ("document", "map", "evidence", "timeline"):
        score -= 0.35

    treatment = (scene.visual_treatment or "").lower()
    goal = (scene.visual_goal or "").lower()
    desc = (scene.visual_description or "").lower()
    blob = f"{treatment} {goal} {desc}"
    if any(w in blob for w in ("cinematic", "impossible", "visualization", "metaphor", "conceptual")):
        score += 0.18
    if any(w in blob for w in ("archival", "document", "newspaper", "map", "photograph")):
        score -= 0.25

    # Early hook + cinematic styles benefit from flow
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


def select_flow_scenes(
    scored: List[Tuple[int, float]],
    budget: int,
) -> set[int]:
    """Return scene_ids selected for Flow — never exceeds budget."""
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
