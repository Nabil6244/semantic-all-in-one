"""Beat ↔ VO alignment — Script Analyzer beats timed to real voiceover."""

from __future__ import annotations

from typing import List, Sequence

from visual_director.schema import VisualScene

from .schema import AlignedBeat, VOAnalysis
from .quality import (
    detect_opportunity_tags,
    idea_count,
    narrative_importance,
    visual_opportunity,
)


def align_beats_to_vo(
    scenes: Sequence[VisualScene],
    vo: VOAnalysis,
) -> List[AlignedBeat]:
    """Align semantic beats to VO using existing align_rows infrastructure.

    Duration always comes from Whisper-aligned timestamps — never from text alone.
    """
    from video_generator import align_rows

    if not scenes:
        return []
    if not vo.words:
        raise RuntimeError("VO analysis has no words — cannot align beats")

    rows = [
        {
            "scene_number": str(scene.scene_id),
            "script_segment": scene.narration,
        }
        for scene in scenes
    ]
    whisper_words = vo.words_as_tuples()
    aligned, audio_end = align_rows(rows, whisper_words)

    # Ensure coverage reaches VO end
    if aligned:
        aligned[-1]["end_time"] = max(
            float(aligned[-1]["end_time"]), float(audio_end), vo.audio_duration
        )

    beats: List[AlignedBeat] = []
    for scene, timing in zip(scenes, aligned):
        start = float(timing["start_time"])
        end = float(timing["end_time"])
        if end <= start:
            end = start + 0.2
        density = _density_in_window(vo, start, end)
        pause_before, pause_after = _pauses_around(vo, start, end)
        internal = _internal_pauses(vo, start, end)
        narr_imp = narrative_importance(scene)
        vis_opp = visual_opportunity(scene, duration=end - start, speech_density=density)
        tags = detect_opportunity_tags(scene.narration, scene.visual_goal, scene.visual_description)
        beats.append(
            AlignedBeat(
                beat_id=int(scene.scene_id),
                narration=scene.narration,
                start=round(start, 3),
                end=round(end, 3),
                align_confidence=float(timing.get("confidence") or 0.0),
                visual_goal=scene.visual_goal or "",
                visual_description=scene.visual_description or "",
                importance=scene.importance or "medium",
                asset_type=scene.asset_type or "",
                provider_preference=scene.provider_preference or "",
                search_queries=list(scene.search_queries or []),
                fallbacks=list(scene.fallbacks or []),
                visual_treatment=scene.visual_treatment or "",
                transition=scene.transition or "cut",
                minimum_quality=scene.minimum_quality or "1080p",
                narrative_importance=narr_imp,
                visual_opportunity=vis_opp,
                speech_density=density,
                pause_before=pause_before,
                pause_after=pause_after,
                internal_pauses=internal,
                opportunity_tags=tags,
                idea_count=idea_count(scene.narration),
            )
        )

    # Close small gaps / overlaps so timeline is contiguous without inventing content.
    _stitch_timeline(beats, vo.audio_duration)
    return beats


def _density_in_window(vo: VOAnalysis, start: float, end: float) -> float:
    dur = max(0.05, end - start)
    count = sum(1 for w in vo.words if w.end > start and w.start < end)
    return round(count / dur, 3)


def _pauses_around(vo: VOAnalysis, start: float, end: float) -> tuple:
    before = 0.0
    after = 0.0
    for p in vo.pauses:
        ps = float(p.get("start") or 0)
        pe = float(p.get("end") or 0)
        pd = float(p.get("duration") or (pe - ps))
        if pe <= start + 0.05 and pe >= start - 0.6:
            before = max(before, pd)
        if ps >= end - 0.05 and ps <= end + 0.6:
            after = max(after, pd)
    return round(before, 3), round(after, 3)


def _internal_pauses(vo: VOAnalysis, start: float, end: float) -> List[float]:
    """Pause starts strictly inside the beat — natural visual change points."""
    out: List[float] = []
    for p in vo.pauses:
        ps = float(p.get("start") or 0)
        pd = float(p.get("duration") or 0)
        if pd < 0.35:
            continue
        if start + 0.9 < ps < end - 0.9:
            out.append(round(ps, 3))
    return out


def _stitch_timeline(beats: List[AlignedBeat], audio_end: float) -> None:
    if not beats:
        return
    beats[0].start = max(0.0, beats[0].start)
    for i in range(len(beats) - 1):
        a, b = beats[i], beats[i + 1]
        if b.start > a.end + 0.08:
            mid = (a.end + b.start) / 2.0
            if a.speech_density <= b.speech_density:
                a.end = round(b.start, 3)
            else:
                a.end = round(mid, 3)
                b.start = round(mid, 3)
        elif b.start < a.end:
            mid = (a.end + b.start) / 2.0
            a.end = round(mid, 3)
            b.start = round(mid, 3)
        if a.end <= a.start:
            a.end = a.start + 0.15
    beats[-1].end = max(beats[-1].end, float(audio_end))
    if beats[-1].end <= beats[-1].start:
        beats[-1].end = beats[-1].start + 0.2
