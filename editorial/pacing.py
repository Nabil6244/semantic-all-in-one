"""Pacing Director — one authoritative transition map from EditorialPlan.

Priority: EditorialPlan.transition_in → VisualDirector (already in plan) → heuristic.
Does not retime narration / Whisper. Affects transition density/style + energy hints.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .schema import HOOK_WINDOW_S, EditorialPlan, EditorialScene, _norm_transition

_STYLES = ("dissolve", "fade", "soft", "flash", "fade")


def _transition_budget(n_boundaries: int, *, hook_heavy: bool = False) -> int:
    if n_boundaries <= 0:
        return 0
    frac = 0.28 if hook_heavy else 0.22
    return max(1, min(n_boundaries, int(round(n_boundaries * frac))))


def _score_boundary(prev: EditorialScene, cur: EditorialScene) -> float:
    score = abs(float(cur.attention_score) - float(prev.attention_score)) * 2.0
    if cur.purpose != prev.purpose:
        score += 1.4
    if cur.purpose in ("hook", "emotion", "reveal") or prev.purpose in (
        "hook",
        "emotion",
        "reveal",
    ):
        score += 0.8
    if cur.pacing_bias == "fast" or prev.pacing_bias == "fast":
        score += 0.5
    if cur.pacing_bias == "slow" and prev.pacing_bias == "slow":
        score -= 0.4
    if cur.visual_variety_key and cur.visual_variety_key == prev.visual_variety_key:
        score -= 0.6
    if cur.start < HOOK_WINDOW_S:
        score += 0.9
    if cur.attention_score >= 0.75:
        score += 0.7
    return score


def _pick_style(scene: EditorialScene, pick_index: int) -> str:
    if scene.transition_in and scene.transition_in != "cut":
        return scene.transition_in
    if scene.start < HOOK_WINDOW_S and scene.purpose in ("hook", "reveal"):
        return "dissolve" if pick_index % 2 == 0 else "fade"
    if scene.purpose in ("emotion", "reflection"):
        return "soft"
    if scene.attention_score >= 0.8:
        return "flash" if pick_index % 3 == 0 else "dissolve"
    if scene.pacing_bias == "slow":
        return "fade"
    return _STYLES[pick_index % len(_STYLES)]


def finalize_transitions(plan: EditorialPlan) -> EditorialPlan:
    """Write authoritative transition_in onto the plan (in place).

    Existing non-null transition_in (from VisualDirector / builder) wins.
    Heuristic fills remaining budget. Clears excess mechanical spam.
    """
    scenes = plan.scenes
    if len(scenes) < 2:
        if scenes and not scenes[0].transition_in:
            scenes[0].transition_in = "fade"
        return plan

    # Scene 0: soft open if unset
    if not scenes[0].transition_in:
        scenes[0].transition_in = "fade"

    explicit = {
        i
        for i, s in enumerate(scenes)
        if i > 0 and s.transition_in and s.transition_in != "cut"
    }
    scored: List[Tuple[float, int]] = []
    for i in range(1, len(scenes)):
        if i in explicit:
            continue
        scored.append((_score_boundary(scenes[i - 1], scenes[i]), i))
    scored.sort(key=lambda t: (-t[0], t[1]))

    budget = _transition_budget(len(scenes) - 1)
    # Leave room for explicit picks
    remaining = max(0, budget - len(explicit))
    picked: List[int] = []
    for score, i in scored:
        if len(picked) >= remaining:
            break
        if score < 0.9 and len(picked) >= max(1, remaining // 2):
            continue
        if any(abs(i - j) == 1 for j in list(picked) + list(explicit)):
            # Avoid adjacent transitions unless inside hook window
            if scenes[i].start >= HOOK_WINDOW_S:
                continue
        scenes[i].transition_in = _pick_style(scenes[i], len(picked))
        picked.append(i)

    # Clear weak leftover None → hard cut (None means no style in render map)
    for i, scene in enumerate(scenes):
        if i == 0:
            continue
        if scene.transition_in == "cut":
            scene.transition_in = None

    # Hook window: ensure at least one purposeful transition into scenes 2..N in window
    hook_scenes = [s for s in scenes[1:] if s.start < HOOK_WINDOW_S]
    if hook_scenes and not any(s.transition_in for s in hook_scenes):
        target = max(hook_scenes, key=lambda s: s.attention_score)
        target.transition_in = "dissolve"

    # Outside hook: prefer fewer transitions on explanation/reflection (slow)
    for scene in scenes:
        if scene.start >= HOOK_WINDOW_S and scene.purpose in ("explanation", "evidence"):
            if scene.pacing_bias == "slow" and scene.attention_score < 0.6:
                if scene.transition_in in ("flash",):
                    scene.transition_in = "fade"

    return plan


def authoritative_transition_map(plan: EditorialPlan) -> Dict[str, str]:
    """Single map for render_video — only non-cut styles."""
    finalize_transitions(plan)
    return plan.transition_style_map()


def apply_pacing_camera_energy(plan: EditorialPlan) -> EditorialPlan:
    """Nudge camera styles for hook energy / slow explanation without retiming.

    Does not override an explicit VisualDirector treatment already mapped to camera.
    """
    for scene in plan.scenes:
        if (scene.visual_treatment or "").strip():
            continue
        if scene.start < HOOK_WINDOW_S:
            if scene.camera_style in ("static", "hold") and scene.attention_score >= 0.55:
                scene.camera_style = (
                    "push_in" if scene.purpose in ("hook", "reveal") else "subtle_drift"
                )
        elif scene.purpose in ("explanation", "evidence", "timeline", "reflection") and scene.pacing_bias == "slow":
            if scene.camera_style == "push_in" and scene.attention_score < 0.7:
                scene.camera_style = "hold"
        elif scene.purpose == "scale" and scene.camera_style in ("static", "hold"):
            scene.camera_style = "pull_out"
        elif scene.attention_score >= 0.85 and scene.camera_style == "static":
            scene.camera_style = "push_in"
    return plan


def scene_split_suggestions(plan: EditorialPlan) -> List[dict]:
    """Optional soft suggestions only — never applied automatically to CSV."""
    out: List[dict] = []
    for scene in plan.scenes:
        if scene.duration >= 7.5 and scene.attention_score >= 0.7:
            out.append(
                {
                    "scene_number": scene.scene_number,
                    "reason": "long high-attention beat",
                    "suggested_split_at": round(scene.start + scene.duration * 0.5, 2),
                }
            )
    return out
