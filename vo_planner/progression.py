"""Visual progression — ENVIRONMENT → … → REVEAL (deterministic)."""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from .schema import AlignedBeat, PROGRESSION_STAGES

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STAGE_KEYWORDS = {
    "environment": (
        "world", "city", "landscape", "sky", "ocean", "forest", "planet",
        "street", "room", "building", "skyline", "horizon", "country",
    ),
    "scale": (
        "scale", "massive", "tiny", "enormous", "vast", "million", "billion",
        "entire", "whole", "size", "compared",
    ),
    "object": (
        "object", "device", "machine", "tool", "document", "book", "phone",
        "car", "ship", "weapon", "artifact", "product",
    ),
    "person": (
        "person", "people", "man", "woman", "worker", "scientist", "leader",
        "child", "crowd", "face", "hands", "president", "founder",
    ),
    "action": (
        "runs", "builds", "launches", "attacks", "creates", "destroys",
        "moves", "flies", "explodes", "crashes", "works", "fights",
    ),
    "mechanism": (
        "how", "process", "system", "engine", "mechanism", "because",
        "works", "algorithm", "pipeline", "circuit", "reaction",
    ),
    "consequence": (
        "result", "consequence", "after", "impact", "effect", "damage",
        "collapse", "success", "failure", "fallout", "outcome",
    ),
    "reveal": (
        "reveal", "truth", "secret", "finally", "actually", "twist",
        "discovery", "hidden", "real", "uncover",
    ),
}


def infer_stage(beat: AlignedBeat, *, index: int = 0, total: int = 1) -> str:
    blob = f"{beat.narration} {beat.visual_goal} {beat.visual_description}".lower()
    toks = set(_TOKEN_RE.findall(blob))
    scores = []
    for stage in PROGRESSION_STAGES:
        keys = _STAGE_KEYWORDS[stage]
        hit = sum(1 for k in keys if k in blob or k in toks)
        scores.append((hit, stage))
    scores.sort(key=lambda x: (-x[0], PROGRESSION_STAGES.index(x[1])))
    if scores[0][0] > 0:
        return scores[0][1]
    # Positional fallback arc
    if total <= 1:
        return "environment"
    t = index / max(1, total - 1)
    if t < 0.12:
        return "environment"
    if t < 0.25:
        return "scale"
    if t < 0.4:
        return "object"
    if t < 0.55:
        return "person"
    if t < 0.7:
        return "action"
    if t < 0.82:
        return "mechanism"
    if t < 0.92:
        return "consequence"
    return "reveal"


def next_distinct_stage(preferred: str, previous: Optional[str]) -> str:
    if not previous or preferred != previous:
        return preferred
    idx = PROGRESSION_STAGES.index(preferred) if preferred in PROGRESSION_STAGES else 0
    for offset in range(1, len(PROGRESSION_STAGES)):
        cand = PROGRESSION_STAGES[(idx + offset) % len(PROGRESSION_STAGES)]
        if cand != previous:
            return cand
    return preferred


def plan_progression(beats: Sequence[AlignedBeat]) -> List[str]:
    """Prefer a forward narrative arc; avoid random stage jumps when confidence is weak."""
    stages: List[str] = []
    prev: Optional[str] = None
    total = len(beats)
    for i, beat in enumerate(beats):
        preferred = infer_stage(beat, index=i, total=total)
        # Soft arc: if preferred jumps backward more than 2 steps without a strong tag, nudge forward
        if prev and preferred in PROGRESSION_STAGES and prev in PROGRESSION_STAGES:
            pi = PROGRESSION_STAGES.index(prev)
            ci = PROGRESSION_STAGES.index(preferred)
            tags = set(beat.opportunity_tags or [])
            strong_jump = bool(tags & {"reveal", "consequence", "dramatic_action", "statistic"})
            if ci + 2 < pi and not strong_jump:
                preferred = PROGRESSION_STAGES[min(len(PROGRESSION_STAGES) - 1, pi + 1)]
        stage = next_distinct_stage(preferred, prev)
        stages.append(stage)
        prev = stage
    return stages


def shot_scale_for_stage(stage: str, *, unit_index: int = 0, prev_scale: Optional[str] = None) -> str:
    defaults = {
        "environment": ("wide", "extreme_wide", "wide"),
        "scale": ("extreme_wide", "wide", "medium"),
        "object": ("medium", "close", "detail"),
        "person": ("medium", "close", "medium"),
        "action": ("medium", "wide", "close"),
        "mechanism": ("close", "detail", "medium"),
        "consequence": ("wide", "medium", "close"),
        "reveal": ("close", "detail", "medium"),
    }
    options = defaults.get(stage, ("medium", "wide", "close"))
    scale = options[min(unit_index, len(options) - 1)]
    if prev_scale and scale == prev_scale:
        for cand in options:
            if cand != prev_scale:
                return cand
        # Fall through progression ladder
        ladder = ["extreme_wide", "wide", "medium", "close", "detail"]
        if prev_scale in ladder:
            return ladder[(ladder.index(prev_scale) + 1) % len(ladder)]
    return scale


def camera_for_stage(stage: str, *, prev_camera: Optional[str] = None) -> str:
    mapping = {
        "environment": "eye_level",
        "scale": "high",
        "object": "eye_level",
        "person": "eye_level",
        "action": "low",
        "mechanism": "oblique",
        "consequence": "high",
        "reveal": "pov",
    }
    cam = mapping.get(stage, "eye_level")
    if prev_camera and cam == prev_camera:
        for alt in ("eye_level", "high", "low", "oblique", "pov", "overhead"):
            if alt != prev_camera:
                return alt
    return cam


def motion_for_strategy(strategy: str, stage: str, *, prev_motion: Optional[str] = None) -> str:
    if strategy == "hold":
        motion = "static"
    elif strategy == "image_motion":
        motion = "ken_burns"
    elif strategy == "punch_in":
        motion = "push_in"
    elif stage in ("environment", "scale"):
        motion = "slow_pan"
    elif stage in ("action", "reveal"):
        motion = "push_in"
    elif stage == "mechanism":
        motion = "orbit"
    else:
        motion = "static"
    if prev_motion and motion == prev_motion and motion != "static":
        for alt in ("static", "slow_pan", "push_in", "pull_out", "orbit"):
            if alt != prev_motion:
                return alt
    return motion
