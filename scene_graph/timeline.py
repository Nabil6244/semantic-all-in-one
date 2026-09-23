"""Compile a rendered Overscaled segment into the EXISTING EditorialTimeline.

Per the Overscaled spec: camera/composition are already baked into the
rendered clip by scene_graph.render, so integration needs nothing more than
ONE ordinary VIDEO_1 TimelineEvent pointing at that clip — exactly the same
track a Flow render or a stock clip would use. No new track, no GRAPHICS
events, no camera TimelineEvent. editorial/timeline.py itself is not
imported for modification — only its existing, unchanged dataclasses are
used to build a timeline value, the same way any other caller does.
"""

from __future__ import annotations

import uuid

from editorial.timeline import EditorialTimeline, TimelineEvent


def compile_segment_to_timeline(
    *,
    segment_clip_path: str,
    voiceover_path: str,
    duration: float,
    scene_number: str = "1",
) -> EditorialTimeline:
    """One VIDEO_1 event (the pre-composed Overscaled clip) + one VOICEOVER
    event (a per-beat timing marker) — a complete, renderable, previewable
    EditorialTimeline using only existing, unmodified track types.

    The VOICEOVER event's ``source`` is deliberately left empty, matching
    the documented real-project convention (see
    preview_engine.build_audio_mix's docstring): narration is one
    continuous, immutable recording passed separately as ``voiceover_path``
    to whatever consumes this timeline (preview_engine.build_audio_mix's own
    ``voiceover_path=`` kwarg, video_generator.render_video's ``audio_path``
    argument) — never read off the TimelineEvent itself. ``voiceover_path``
    is still returned here (see the caller) so it travels alongside the
    timeline it belongs to.
    """

    video_event = TimelineEvent(
        event_id=f"overscaled_video_{uuid.uuid4().hex[:8]}",
        track="VIDEO_1",
        start=0.0,
        end=float(duration),
        scene_number=scene_number,
        source=str(segment_clip_path),
        metadata={"overscaled": True},
    )
    voiceover_event = TimelineEvent(
        event_id=f"overscaled_vo_{uuid.uuid4().hex[:8]}",
        track="VOICEOVER",
        start=0.0,
        end=float(duration),
        scene_number=scene_number,
        source="",
    )
    return EditorialTimeline(audio_end=float(duration), events=[video_event, voiceover_event])
