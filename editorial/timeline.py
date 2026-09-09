"""Layer-based editorial timeline — independent start/end per event.

Does not replace the voiceover-authoritative scene windows. It describes
parallel layers (video shots, text, music, ambience, SFX) that may start/end
independently of scene boundaries when the editor decides so.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Literal, Optional

TrackName = Literal[
    "VIDEO_1",
    "VIDEO_2",
    "IMAGE",
    "TEXT",
    "GRAPHICS",
    "VOICEOVER",
    "MUSIC",
    "AMBIENCE",
    "SFX",
]

ALLOWED_TRACKS = frozenset(
    {
        "VIDEO_1",
        "VIDEO_2",
        "IMAGE",
        "TEXT",
        "GRAPHICS",
        "VOICEOVER",
        "MUSIC",
        "AMBIENCE",
        "SFX",
    }
)


@dataclasses.dataclass
class TimelineEvent:
    """One timed event on a timeline track."""

    event_id: str
    track: TrackName
    start: float
    end: float
    scene_number: str = ""
    source: str = ""
    opacity: float = 1.0
    scale: float = 1.0
    position_x: float = 0.5
    position_y: float = 0.5
    rotation: float = 0.0
    crop: Optional[Dict[str, float]] = None
    z_index: int = 0
    animation: str = ""
    transition_in: str = "cut"
    transition_out: str = "cut"
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, float(self.end) - float(self.start))

    def to_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["duration"] = round(self.duration, 4)
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "TimelineEvent":
        fields = {f.name for f in dataclasses.fields(cls)}
        raw = {k: v for k, v in (data or {}).items() if k in fields}
        track = str(raw.get("track") or "VIDEO_1")
        if track not in ALLOWED_TRACKS:
            track = "VIDEO_1"
        raw["track"] = track
        if raw.get("crop") is not None and not isinstance(raw["crop"], dict):
            raw["crop"] = None
        if not isinstance(raw.get("metadata"), dict):
            raw["metadata"] = {}
        return cls(**raw)


@dataclasses.dataclass
class EditorialTimeline:
    """Full layered timeline for one render."""

    version: int = 1
    audio_end: float = 0.0
    events: List[TimelineEvent] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "audio_end": round(float(self.audio_end), 4),
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EditorialTimeline":
        if not isinstance(data, dict):
            return cls()
        events = [
            TimelineEvent.from_dict(e)
            for e in (data.get("events") or [])
            if isinstance(e, dict)
        ]
        return cls(
            version=int(data.get("version") or 1),
            audio_end=float(data.get("audio_end") or 0.0),
            events=events,
        )

    def events_on(self, track: str) -> List[TimelineEvent]:
        return [e for e in self.events if e.track == track]

    def events_for_scene(self, scene_number: str) -> List[TimelineEvent]:
        sn = str(scene_number)
        return [e for e in self.events if e.scene_number == sn]

    def add(self, event: TimelineEvent) -> None:
        self.events.append(event)

    def sorted_events(self) -> List[TimelineEvent]:
        return sorted(self.events, key=lambda e: (e.start, e.z_index, e.event_id))


_VISUAL_TRACKS = ("VIDEO_1", "VIDEO_2", "IMAGE")


def validate_visual_timeline(
    timeline: EditorialTimeline,
    *,
    audio_end: Optional[float] = None,
) -> List[dict]:
    """QC visual coverage: monotonic, positive duration, no accidental gaps.

    Graphics / text overlays may overlap video; video+image layers should form
    a continuous playhead. Returns concise issue dicts (no log spam).
    """
    issues: List[dict] = []
    visual = [
        e for e in timeline.events
        if e.track in _VISUAL_TRACKS
    ]
    visual.sort(key=lambda e: (float(e.start), float(e.end), e.event_id))
    prev_end: Optional[float] = None
    prev_scene = ""
    for ev in visual:
        dur = float(ev.end) - float(ev.start)
        if dur <= 0.001:
            issues.append(
                {
                    "severity": "WARN",
                    "category": "timeline",
                    "scene_number": ev.scene_number,
                    "message": (
                        f"zero-duration visual {ev.event_id} "
                        f"{ev.start:.2f}–{ev.end:.2f}"
                    ),
                    "asset": ev.source,
                    "start": ev.start,
                    "end": ev.end,
                }
            )
        if prev_end is not None and ev.start + 0.05 < prev_end:
            # Same-scene dual-track overlap is intended (VIDEO_1/VIDEO_2 A/B).
            same_scene = str(ev.scene_number) == str(prev_scene)
            if not same_scene:
                issues.append(
                    {
                        "severity": "WARN",
                        "category": "timeline",
                        "scene_number": ev.scene_number,
                        "message": (
                            f"overlap vs previous visual end {prev_end:.2f}s "
                            f"(this starts {ev.start:.2f}s)"
                        ),
                        "asset": ev.source,
                    }
                )
        if prev_end is not None and ev.start > prev_end + 0.12:
            issues.append(
                {
                    "severity": "WARN",
                    "category": "timeline",
                    "scene_number": ev.scene_number,
                    "message": (
                        f"visual gap {prev_end:.2f}s→{ev.start:.2f}s"
                    ),
                    "asset": ev.source,
                }
            )
        prev_end = max(prev_end or 0.0, float(ev.end))
        prev_scene = ev.scene_number

    end_limit = audio_end if audio_end is not None else timeline.audio_end
    if visual and end_limit and prev_end is not None and prev_end + 0.25 < float(end_limit):
        issues.append(
            {
                "severity": "WARN",
                "category": "timeline",
                "scene_number": visual[-1].scene_number,
                "message": (
                    f"visual coverage ends {prev_end:.2f}s "
                    f"before audio {float(end_limit):.2f}s"
                ),
            }
        )
    return issues
