"""Retime a SceneGraph's placeholder (word-count) timing against the REAL
voiceover — the voiceover remains the authoritative temporal backbone, per
the existing project's own convention (see editorial/schema.py: "duration
is the REQUIRED scene length, derived from the voiceover, and remains
authoritative"). This module does not replace the existing audio system or
Whisper alignment; it reuses the same probe (media_duration.probe_media_duration)
and accepts already-aligned word timestamps (the same shape
video_generator.transcribe_audio/align_rows already produce) as an optional
input, so real Whisper alignment can be plugged in later without changing
this module's contract.

Two modes, both deterministic and pure (return a NEW SceneGraph):
  - proportional (default, always available): scale every timestamp in the
    graph so its total duration matches the real audio file's duration.
  - word-aligned (opt-in, ``whisper_words`` supplied): walk real per-word
    timestamps beat-by-beat, consuming each beat's own word count, and
    rescale that beat's internal events (node appear_at, edge draw_at,
    camera keyframe at) proportionally within its new, real time window.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from media_duration import probe_media_duration

from .schema import SceneGraph

WhisperWord = Tuple[str, float, float]  # (word, start, end) — same shape video_generator uses


def retime_to_audio_duration(scene_graph: SceneGraph, audio_path: str) -> SceneGraph:
    """Proportionally rescale every timestamp so the graph spans the real
    voiceover file's actual duration. Never fabricates a duration: if the
    file can't be probed, the graph is returned unchanged."""

    real_duration = probe_media_duration(audio_path)
    if not real_duration or real_duration <= 0:
        return SceneGraph.from_dict(scene_graph.to_dict())

    old_duration = float(scene_graph.duration) or 1.0
    scale = real_duration / old_duration
    return _rescale(scene_graph, scale=scale, new_total_duration=real_duration)


def _rescale(scene_graph: SceneGraph, *, scale: float, new_total_duration: float) -> SceneGraph:
    data = scene_graph.to_dict()
    data["duration"] = round(new_total_duration, 4)
    for node in data.get("nodes") or []:
        node["appear_at"] = round(float(node.get("appear_at") or 0.0) * scale, 4)
        if node.get("duration") is not None:
            node["duration"] = round(float(node["duration"]) * scale, 4)
    for edge in data.get("edges") or []:
        edge["draw_at"] = round(float(edge.get("draw_at") or 0.0) * scale, 4)
        edge["duration"] = round(max(0.05, float(edge.get("duration") or 1.0) * scale), 4)
    for kf in data.get("camera_keyframes") or []:
        kf["at"] = round(float(kf.get("at") or 0.0) * scale, 4)
    for cue in data.get("title_cues") or []:
        cue["at"] = round(float(cue.get("at") or 0.0) * scale, 4)
    for beat in data.get("beats") or []:
        beat["start"] = round(float(beat.get("start") or 0.0) * scale, 4)
        beat["end"] = round(float(beat.get("end") or 0.0) * scale, 4)
    return SceneGraph.from_dict(data)


def retime_to_whisper_words(scene_graph: SceneGraph, whisper_words: Sequence[WhisperWord]) -> SceneGraph:
    """Align each beat to its real span of narration words, then rescale
    that beat's own node/edge/camera timestamps proportionally within the
    beat's (old-relative -> new-real) window. Deterministic given the same
    word list; never reorders beats or fabricates words that weren't given."""

    if not whisper_words:
        return SceneGraph.from_dict(scene_graph.to_dict())

    data = scene_graph.to_dict()
    beats = data.get("beats") or []
    cursor = 0
    new_windows = []  # (old_start, old_end, new_start, new_end) per beat
    for beat in beats:
        word_count = max(1, len((beat.get("narration") or "").split()))
        chunk = whisper_words[cursor: cursor + word_count]
        cursor += word_count
        if not chunk:
            # Ran out of real words (narration shorter than the CSV
            # implied) — hold the last known real time rather than guess.
            last_end = new_windows[-1][3] if new_windows else 0.0
            new_start, new_end = last_end, last_end + 0.01
        else:
            new_start, new_end = float(chunk[0][1]), float(chunk[-1][2])
        old_start, old_end = float(beat.get("start") or 0.0), float(beat.get("end") or 0.0)
        new_windows.append((old_start, old_end, new_start, new_end))
        beat["start"] = round(new_start, 4)
        beat["end"] = round(new_end, 4)

    def remap(old_t: float) -> float:
        for old_start, old_end, new_start, new_end in new_windows:
            if old_start <= old_t <= old_end:
                old_span = max(1e-6, old_end - old_start)
                frac = (old_t - old_start) / old_span
                return round(new_start + frac * (new_end - new_start), 4)
        # Outside every beat window (shouldn't normally happen) — clamp to
        # the nearest known window rather than extrapolate wildly.
        if old_t <= new_windows[0][0]:
            return new_windows[0][2]
        return new_windows[-1][3]

    for node in data.get("nodes") or []:
        node["appear_at"] = remap(float(node.get("appear_at") or 0.0))
    for edge in data.get("edges") or []:
        edge["draw_at"] = remap(float(edge.get("draw_at") or 0.0))
    for kf in data.get("camera_keyframes") or []:
        kf["at"] = remap(float(kf.get("at") or 0.0))
    for cue in data.get("title_cues") or []:
        cue["at"] = remap(float(cue.get("at") or 0.0))

    data["duration"] = new_windows[-1][3] if new_windows else data.get("duration")
    return SceneGraph.from_dict(data)
