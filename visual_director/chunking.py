"""Split long scripts into parallel planning sections."""

from __future__ import annotations

import re
from typing import List

from .schema import VisualPlan, VisualScene

CHUNK_WORD_THRESHOLD = 2500
DEFAULT_CHUNK_TARGET_WORDS = 1200
MIN_CHUNK_WORDS = 400


def script_word_count(script: str) -> int:
    return len((script or "").split())


def should_chunk_plan(script: str) -> bool:
    return script_word_count(script) >= CHUNK_WORD_THRESHOLD


def split_script_into_chunks(
    script: str,
    *,
    target_words: int = DEFAULT_CHUNK_TARGET_WORDS,
) -> List[str]:
    """Split on paragraph boundaries; keep sections within ~target_words."""
    text = (script or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if not parts:
        parts = [text]
    chunks: List[str] = []
    current: List[str] = []
    current_words = 0
    for para in parts:
        w = len(para.split())
        if (
            current
            and current_words + w > target_words
            and current_words >= MIN_CHUNK_WORDS
        ):
            chunks.append("\n\n".join(current))
            current = [para]
            current_words = w
        else:
            current.append(para)
            current_words += w
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_plan_user_message(
    chunk: str,
    *,
    section_index: int,
    section_total: int,
    full_word_count: int,
) -> str:
    from .director import _plan_user_message

    words = script_word_count(chunk)
    return (
        f"Plan visual beats for SECTION {section_index + 1} of {section_total} "
        f"from a longer narration ({full_word_count:,} words total).\n"
        "Cover ONLY the words in this section — do not summarize other sections "
        "and do not stop early.\n\n"
        + _plan_user_message(chunk).replace(
            "Create a complete visual timeline for this entire narration.",
            "Create a complete visual timeline for THIS SECTION ONLY.",
        )
    )


def merge_chunk_plans(plans: List[VisualPlan]) -> VisualPlan:
    if not plans:
        return VisualPlan(topic="", scenes=[])
    scenes: List[VisualScene] = []
    warnings: List[str] = []
    topic = ""
    for plan in plans:
        if not topic and (plan.topic or "").strip():
            topic = plan.topic.strip()
        scenes.extend(plan.scenes)
        warnings.extend(plan.warnings or [])
    for i, scene in enumerate(scenes, start=1):
        scene.scene_id = i
    if not topic and scenes:
        topic = scenes[0].visual_goal
    return VisualPlan(topic=topic, scenes=scenes, warnings=warnings)
