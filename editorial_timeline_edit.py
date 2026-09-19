"""Interactive-timeline editing operations (Semantic YT Studio 2.0 — CapCut-style editor).

Operates on the SAME ``EditorialTimeline``/``TimelineEvent`` structures the
render pipeline reads (editorial/timeline.py) and persists them back into the
SAME ``state/editorial_plan.json`` file the editorial engine already owns
(editorial/persistence.py) — no new persistence architecture, no new
timeline data model.

Editability model:
  - TEXT / GRAPHICS / SFX / AMBIENCE / MUSIC / VIDEO_2 events carry
    independent start/end times and may be freely moved, trimmed, split,
    deleted, duplicated (see FREELY_MOVABLE_TRACKS).
  - VIDEO_1 / IMAGE (PRIMARY_VISUAL_TRACKS) form the continuous on-screen
    playhead (see editorial/timeline.py's validate_visual_timeline). They are
    editable — trim/split/delete/duplicate/reorder/replace — but never
    freely dragged to an arbitrary time: every operation that changes one
    primary clip's duration RIPPLES every later primary-track clip by the
    same delta, so the visual layer never develops a gap or an overlap on
    its own. VOICEOVER stays fixed (the narration recording is immutable);
    a ripple edit can therefore leave visuals running short/long of the
    narration — that is flagged via qc_issues()/validate_visual_timeline(),
    exactly like any other real NLE's ripple trim against a locked audio
    spine, never silently hidden.
  - VIDEO_2 (OVERLAY_VISUAL_TRACKS) is a genuinely INDEPENDENT B-roll
    overlay track: move/trim/split/delete/duplicate/speed all behave like
    a freely-movable clip (drag anywhere, no ripple in either direction)
    while still carrying real visual-shot semantics (source_start/
    source_end/speed on trim and split). A VIDEO_2 event whose time range
    genuinely OVERLAPS a primary clip is rendered as a true picture-in-
    picture overlay (video_generator.composite_broll_overlay) rather than
    sequential coverage — see reconcile_timeline_into_decisions().
  - reconcile_timeline_into_decisions() is the one-way bridge FROM an
    operator-edited timeline back INTO the EditDecision/ShotSpec structures
    the FFmpeg renderer actually consumes, so edits made here genuinely
    affect the exported file (see app.py's render pipeline).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from editorial.persistence import plan_file
from editorial.timeline import EditorialTimeline, TimelineEvent, validate_visual_timeline

# PRIMARY_VISUAL_TRACKS form "the continuous playhead" (module docstring):
# VIDEO_1/IMAGE ripple against each other so the on-screen video never
# develops a gap or an overlap on its own. OVERLAY_VISUAL_TRACKS (VIDEO_2)
# is a genuinely INDEPENDENT B-roll overlay track — it never ripples the
# primary timeline and is never rippled BY primary edits either. It behaves
# like a freely-movable track (see FREELY_MOVABLE_TRACKS below) except it
# keeps visual-only semantics: source_start/source_end/speed tracking on
# trim/split, and it is what reconcile_timeline_into_decisions() looks for
# to detect a genuine time-overlap with a primary shot and render it as a
# real picture-in-picture overlay (video_generator.composite_broll_overlay)
# rather than sequential coverage.
PRIMARY_VISUAL_TRACKS = frozenset({"VIDEO_1", "IMAGE"})
OVERLAY_VISUAL_TRACKS = frozenset({"VIDEO_2"})
VISUAL_TRACKS = PRIMARY_VISUAL_TRACKS | OVERLAY_VISUAL_TRACKS

# The ONE authoritative speed range for a visual shot — the Inspector
# slider, the preview proxy renderer (preview_engine.py), and the final
# FFmpeg renderer (video_generator._render_editorial_shot) all clamp to
# this SAME range. Before this constant existed the renderer silently
# clamped to a narrower [0.8, 1.25] than the Inspector offered
# ([0.25, 2.0]) — a real, confirmed preview/export divergence (a user
# picking 2x got 1.25x in the exported file with no indication). Widening
# the renderer to match is safe: setpts-based speed change has no hard
# ffmpeg limit in this range.
MIN_SPEED = 0.25
MAX_SPEED = 2.0


def clamp_speed(speed: float) -> float:
    try:
        s = float(speed)
    except (TypeError, ValueError):
        return 1.0
    return max(MIN_SPEED, min(MAX_SPEED, s))

# Tracks whose timing an operator may freely edit from the interactive
# timeline (arbitrary drag to any time). VIDEO_2 (B-roll overlay) is here
# too — unlike VIDEO_1/IMAGE it is NOT part of the ripple-locked primary
# playhead, so a drag genuinely repositions it, exactly like a text/SFX
# clip, while still carrying visual-shot semantics (see VISUAL_TRACKS).
FREELY_MOVABLE_TRACKS = frozenset({"TEXT", "GRAPHICS", "SFX", "AMBIENCE", "MUSIC"}) | OVERLAY_VISUAL_TRACKS

# All tracks an operator may edit in some fashion (trim/split/delete/
# duplicate at minimum). Visual tracks are included but are ripple-only —
# see module docstring and FREELY_MOVABLE_TRACKS.
EDITABLE_TRACKS = FREELY_MOVABLE_TRACKS | VISUAL_TRACKS

MIN_EVENT_DURATION = 0.10


def load_timeline(state_dir: Path) -> EditorialTimeline:
    """Old projects with no editorial_plan.json (or no "timeline" key) get an
    empty, valid EditorialTimeline — never a crash, never invented events."""
    try:
        path = plan_file(state_dir)
        if not path.is_file():
            return EditorialTimeline()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return EditorialTimeline()
        return EditorialTimeline.from_dict(data.get("timeline") or {})
    except (OSError, ValueError, TypeError):
        return EditorialTimeline()


def save_timeline(state_dir: Path, timeline: EditorialTimeline) -> bool:
    """Patch only the "timeline" key of the existing editorial_plan.json,
    preserving every other field the editorial engine wrote. Best-effort —
    returns False (never raises) if the plan file doesn't exist yet (nothing
    sensible to patch) or can't be written."""
    try:
        path = plan_file(state_dir)
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        data["timeline"] = timeline.to_dict()
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except (OSError, ValueError, TypeError):
        return False


def is_editable(event: TimelineEvent) -> bool:
    return event.track in EDITABLE_TRACKS


def is_freely_movable(event: TimelineEvent) -> bool:
    return event.track in FREELY_MOVABLE_TRACKS


def _visual_events_sorted(timeline: EditorialTimeline) -> List[TimelineEvent]:
    """The continuous PRIMARY visual playhead only — VIDEO_2 overlays are
    deliberately excluded (see OVERLAY_VISUAL_TRACKS): they never take part
    in reorder-to-index or the ripple sequence."""
    return sorted(
        (e for e in timeline.events if e.track in PRIMARY_VISUAL_TRACKS),
        key=lambda e: (float(e.start), float(e.end), e.event_id),
    )


def _ripple_shift_after(timeline: EditorialTimeline, after_time: float, delta: float, *, exclude_id: str = "") -> None:
    """Shift every PRIMARY visual-track event that starts at/after
    ``after_time`` by ``delta`` seconds, preserving the continuous visual
    playhead invariant that validate_visual_timeline() checks for. Never
    touches VOICEOVER, VIDEO_2 (an independent overlay — see
    OVERLAY_VISUAL_TRACKS), or any other freely-movable track."""
    if abs(delta) < 1e-9:
        return
    for e in timeline.events:
        if e.track not in PRIMARY_VISUAL_TRACKS or e.event_id == exclude_id:
            continue
        if float(e.start) >= after_time - 1e-6:
            e.start = round(max(0.0, float(e.start) + delta), 4)
            e.end = round(max(e.start, float(e.end) + delta), 4)


def _primary_scene_number_at(timeline: EditorialTimeline, start: float, end: float) -> str:
    """Best-match scene_number for a VIDEO_2 overlay clip spanning
    [start, end) — the PRIMARY (VIDEO_1/IMAGE) event it overlaps the most,
    or the nearest primary event if it doesn't overlap any at all (a
    slightly-off drag still reconciles into a sensible scene bucket rather
    than silently vanishing at export — see reconcile_timeline_into_
    decisions, which groups events by scene_number). Called automatically
    whenever an overlay clip's timing changes (move/trim/split/duplicate/
    insert) so the operator never has to think about scene numbers."""
    best = None
    best_score = None
    for e in timeline.events:
        if e.track not in PRIMARY_VISUAL_TRACKS:
            continue
        overlap = min(end, float(e.end)) - max(start, float(e.start))
        score = overlap if overlap > 0 else -abs(max(start, float(e.start)) - min(end, float(e.end)))
        if best_score is None or score > best_score:
            best_score = score
            best = e
    return str(best.scene_number) if best is not None else ""


def _resync_overlay_scene_number(timeline: EditorialTimeline, ev: TimelineEvent) -> None:
    if ev.track in OVERLAY_VISUAL_TRACKS:
        ev.scene_number = _primary_scene_number_at(timeline, float(ev.start), float(ev.end))


def find_event(timeline: EditorialTimeline, event_id: str) -> Optional[TimelineEvent]:
    for e in timeline.events:
        if e.event_id == event_id:
            return e
    return None


def timeline_duration(timeline: EditorialTimeline) -> float:
    """The CURRENT total playable/displayable length of the timeline —
    NOT the same thing as ``timeline.audio_end``.

    ``timeline.audio_end`` is set once, from the recorded narration's own
    length, and is deliberately left untouched by editing operations —
    qc_issues()/validate_visual_timeline() need that original, stable
    value to correctly flag "visual coverage no longer matches the
    narration" as a real warning, not something that silently stops being
    detectable the moment an edit extends the project.

    But every OTHER consumer that needs "how long is the timeline right
    now" (the TimelineCanvas ruler/scroll extent, the preview player's
    scrub-bar range, the audio mixdown's own output length, scene-boundary
    snap targets, the freely-movable-track end clamp) was reading
    ``timeline.audio_end`` directly — so extending a clip (e.g. an IMAGE
    event's duration) past that original length made the edit fully real
    in the data model while staying invisible/unreachable everywhere else
    (the ruler stopped there, the scrub bar couldn't seek past it, the
    mixed audio was truncated there) — reported live as "the editor still
    behaves like the timeline duration is fixed." This is the one
    authoritative computation for that — never re-derive it ad hoc."""
    end = float(timeline.audio_end or 0.0)
    if timeline.events:
        end = max(end, max((float(e.end) for e in timeline.events), default=0.0))
    return end


def scene_boundaries(timeline: EditorialTimeline) -> List[float]:
    """Distinct start/end times of the (read-only) visual layer — the
    snap targets for editable-track drags, per the spec's "snap primarily
    to scene boundaries and sensible clip boundaries."""
    bounds: set[float] = {0.0, timeline_duration(timeline)}
    for e in timeline.events:
        if e.track in ("VIDEO_1", "VIDEO_2", "IMAGE"):
            bounds.add(round(float(e.start), 3))
            bounds.add(round(float(e.end), 3))
    return sorted(bounds)


def snap_time(t: float, bounds: List[float], tolerance: float = 0.25) -> float:
    if not bounds:
        return t
    nearest = min(bounds, key=lambda b: abs(b - t))
    return nearest if abs(nearest - t) <= tolerance else t


def move_event(
    timeline: EditorialTimeline,
    event_id: str,
    new_start: float,
    *,
    snap: bool = True,
    tolerance: float = 0.25,
) -> bool:
    """Shift a freely-movable event's whole window, preserving its duration.
    No-op (returns False) for a missing event, a visual-track event (those
    ripple-reorder instead — see move_visual_event()), or a target that
    would push it out of [0, audio_end]."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_freely_movable(ev):
        return False
    dur = ev.duration
    start = max(0.0, float(new_start))
    if snap:
        start = snap_time(start, scene_boundaries(timeline), tolerance)
    end = start + dur
    total = timeline_duration(timeline)
    if total and end > total:
        end = total
        start = max(0.0, end - dur)
    ev.start = round(start, 4)
    ev.end = round(end, 4)
    _resync_overlay_scene_number(timeline, ev)
    return True


def trim_event_start(timeline: EditorialTimeline, event_id: str, new_start: float, *, snap: bool = True) -> bool:
    """Trim an event's start. For a PRIMARY visual-track event this is a
    ripple trim: every later primary clip shifts by the same delta so the
    playhead stays continuous. A VIDEO_2 overlay trims in place instead —
    no ripple, since it is an independent track (see OVERLAY_VISUAL_TRACKS)
    — but it still tracks source_start like any real visual shot."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_editable(ev):
        return False
    start = max(0.0, float(new_start))
    if snap:
        start = snap_time(start, scene_boundaries(timeline))
    if start >= ev.end - MIN_EVENT_DURATION:
        return False
    if ev.track in PRIMARY_VISUAL_TRACKS and start < ev.start:
        # Trimming the start earlier would overlap the previous primary
        # clip unless that clip also shrinks — not a safe ripple direction
        # from the start handle, so only allow shortening (start later).
        return False
    delta = round(start, 4) - ev.start
    if ev.track in VISUAL_TRACKS:
        # Left trim moves `delta` seconds of TIMELINE duration off the
        # front, i.e. `delta * speed` seconds of SOURCE media — advance
        # source_start by that much (mirror image of a right-trim, which
        # never touches source_start). Same math as split_event below.
        meta = dict(ev.metadata or {})
        speed = float(meta.get("speed") or 1.0)
        src_start = float(meta.get("source_start") or 0.0)
        meta["source_start"] = round(max(0.0, src_start + delta * speed), 4)
        ev.metadata = meta
    ev.start = round(start, 4)
    if ev.track in PRIMARY_VISUAL_TRACKS:
        # The clip shrank by `delta` (start moved later by `delta`), so
        # everything after it ripples EARLIER by that same amount to close
        # the resulting gap — the mirror image of trim_event_end below.
        _ripple_shift_after(timeline, ev.end, -delta, exclude_id=ev.event_id)
    _resync_overlay_scene_number(timeline, ev)
    return True


def trim_event_end(timeline: EditorialTimeline, event_id: str, new_end: float, *, snap: bool = True) -> bool:
    """Trim an event's end. For a PRIMARY visual-track event this is a
    ripple trim: every later primary clip shifts by the same delta (see
    trim_event_start). A VIDEO_2 overlay trims in place, no ripple."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_editable(ev):
        return False
    end = float(new_end)
    if snap:
        end = snap_time(end, scene_boundaries(timeline))
    if ev.track not in VISUAL_TRACKS:
        total = timeline_duration(timeline)
        if total:
            end = min(end, total)
    if end <= ev.start + MIN_EVENT_DURATION:
        return False
    delta = round(end, 4) - ev.end
    ev.end = round(end, 4)
    if ev.track in PRIMARY_VISUAL_TRACKS:
        _ripple_shift_after(timeline, ev.end - delta, delta, exclude_id=ev.event_id)
    _resync_overlay_scene_number(timeline, ev)
    return True


def split_event(timeline: EditorialTimeline, event_id: str, at_time: float) -> Optional[str]:
    """Split an editable event into two at ``at_time``. Returns the new
    (second-half) event's id, or None if the split point doesn't leave both
    halves at least MIN_EVENT_DURATION long. A visual-track split needs no
    ripple — the combined span of the two halves equals the original."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_editable(ev):
        return None
    t = float(at_time)
    if t <= ev.start + MIN_EVENT_DURATION or t >= ev.end - MIN_EVENT_DURATION:
        return None
    second = dataclasses.replace(ev, event_id=f"{ev.event_id}-split-{uuid.uuid4().hex[:8]}", start=round(t, 4))
    if ev.track in VISUAL_TRACKS:
        meta = dict(second.metadata or {})
        src_start = float(meta.get("source_start") or 0.0)
        src_end = meta.get("source_end")
        speed = float(meta.get("speed") or 1.0)
        first_dur = round(t, 4) - ev.start
        offset_in_source = first_dur * speed
        meta["source_start"] = round(src_start + offset_in_source, 4)
        second.metadata = meta
        first_meta = dict(ev.metadata or {})
        if src_end is not None:
            first_meta["source_end"] = round(src_start + offset_in_source, 4)
        ev.metadata = first_meta
    ev.end = round(t, 4)
    timeline.events.append(second)
    _resync_overlay_scene_number(timeline, second)
    return second.event_id


def delete_event(timeline: EditorialTimeline, event_id: str, *, ripple: bool = True) -> bool:
    """Delete an editable event. A PRIMARY visual-track delete ripple-closes
    the resulting gap by default (ripple=True) — pass ripple=False for a
    "lift" delete that leaves a gap (e.g. an undo helper that will
    re-insert). A VIDEO_2 overlay delete never ripples anything — it is an
    independent track (see OVERLAY_VISUAL_TRACKS)."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_editable(ev):
        return False
    timeline.events.remove(ev)
    if ripple and ev.track in PRIMARY_VISUAL_TRACKS:
        _ripple_shift_after(timeline, ev.end, -(ev.end - ev.start))
    return True


def duplicate_event(timeline: EditorialTimeline, event_id: str) -> Optional[str]:
    """Duplicate an editable event immediately after itself. For a
    freely-movable track (including VIDEO_2 — an independent overlay, see
    OVERLAY_VISUAL_TRACKS) the copy is appended right after the original.
    For a PRIMARY visual track every later primary clip ripples later by
    the duplicate's duration, so the copy is genuinely inserted — never
    overlapping — into the continuous playhead."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_editable(ev):
        return None
    dur = ev.duration
    new_ev = copy.copy(ev)
    new_ev.event_id = f"{ev.event_id}-dup-{uuid.uuid4().hex[:8]}"
    new_ev.start = round(ev.end, 4)
    new_ev.end = round(ev.end + dur, 4)
    new_ev.metadata = dict(ev.metadata or {})
    if ev.track in PRIMARY_VISUAL_TRACKS:
        _ripple_shift_after(timeline, ev.end, dur)
    elif ev.track not in VISUAL_TRACKS:
        total = timeline_duration(timeline)
        if total and new_ev.end > total:
            new_ev.start = round(max(0.0, total - dur), 4)
            new_ev.end = round(new_ev.start + dur, 4)
    timeline.events.append(new_ev)
    _resync_overlay_scene_number(timeline, new_ev)
    return new_ev.event_id


_REORDER_CONTENT_FIELDS = (
    "source", "scale", "position_x", "position_y", "rotation", "crop",
    "animation", "transition_in", "transition_out", "metadata",
)


def reorder_visual_event(timeline: EditorialTimeline, event_id: str, *, direction: str) -> bool:
    """Swap a visual clip's CONTENT with its immediate predecessor/successor
    in the continuous visual playhead (direction: "earlier" or "later").
    Timeline slots (start/end/event_id/scene_number) never move — only what
    plays in them trades places — so the playhead stays gap-free by
    construction and event_ids stay stable for selection/undo."""
    ev = find_event(timeline, event_id)
    if ev is None or ev.track not in PRIMARY_VISUAL_TRACKS:
        return False
    ordered = _visual_events_sorted(timeline)
    idx = next((i for i, e in enumerate(ordered) if e.event_id == event_id), None)
    if idx is None:
        return False
    other_idx = idx - 1 if direction == "earlier" else idx + 1
    if other_idx < 0 or other_idx >= len(ordered):
        return False
    other = ordered[other_idx]
    for field in _REORDER_CONTENT_FIELDS:
        a_val, b_val = getattr(ev, field), getattr(other, field)
        setattr(ev, field, copy.deepcopy(b_val) if isinstance(b_val, dict) else b_val)
        setattr(other, field, copy.deepcopy(a_val) if isinstance(a_val, dict) else a_val)
    return True


def visual_sequence_order(timeline: EditorialTimeline) -> List[TimelineEvent]:
    """The continuous visual playhead in on-screen order — the sequence a
    drag-to-reorder gesture picks an insertion index into."""
    return _visual_events_sorted(timeline)


def move_visual_event_to_index(timeline: EditorialTimeline, event_id: str, target_index: int) -> bool:
    """Drag-to-reorder: pull ``event_id`` out of the continuous visual
    sequence and reinsert it at ``target_index``, then reflow every visual
    clip's start/end back-to-back in the new order (each clip keeps its own
    duration — only its position changes). This is what makes dragging a
    VIDEO_1/VIDEO_2/IMAGE clip on the timeline actually move it, the way an
    operator coming from CapCut/Premiere expects — plain drag-anywhere is
    intentionally NOT supported for visual clips (see module docstring);
    this is the real, working equivalent: drag to reorder, never a gap."""
    ev = find_event(timeline, event_id)
    if ev is None or ev.track not in PRIMARY_VISUAL_TRACKS:
        return False
    ordered = _visual_events_sorted(timeline)
    try:
        ordered.remove(ev)
    except ValueError:
        return False
    target_index = max(0, min(int(target_index), len(ordered)))
    ordered.insert(target_index, ev)
    t = 0.0
    for e in ordered:
        dur = e.duration
        e.start = round(t, 4)
        e.end = round(t + dur, 4)
        t = e.end
    return True


def replace_event_source(
    timeline: EditorialTimeline,
    event_id: str,
    *,
    new_source: str,
    metadata_updates: Optional[dict] = None,
) -> bool:
    """Swap a clip's underlying media (B-roll replace) without touching its
    timing. Works for any editable track (a video/image B-roll swap, or
    swapping the audio file behind an SFX/ambience/music clip)."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_editable(ev):
        return False
    ev.source = str(new_source)
    if metadata_updates:
        meta = dict(ev.metadata or {})
        meta.update(metadata_updates)
        ev.metadata = meta
    return True


def set_event_property(timeline: EditorialTimeline, event_id: str, **fields) -> bool:
    """Generic property setter for the Inspector panel (volume, mute,
    opacity, scale, position, rotation, transitions, speed, text content,
    ...). Anything matching a real TimelineEvent field is set directly;
    anything else is merged into .metadata (e.g. "volume", "muted", "text",
    "speed" for a visual shot). Never touches start/end/track/event_id —
    use the dedicated timing functions for those."""
    ev = find_event(timeline, event_id)
    if ev is None or not is_editable(ev):
        return False
    direct = {"opacity", "scale", "position_x", "position_y", "rotation", "crop", "z_index",
              "animation", "transition_in", "transition_out", "source"}
    meta = dict(ev.metadata or {})
    for key, value in fields.items():
        if key in direct:
            setattr(ev, key, value)
        elif key in ("start", "end", "track", "event_id", "scene_number", "duration"):
            continue
        else:
            meta[key] = value
    ev.metadata = meta
    return True


def add_event(
    timeline: EditorialTimeline,
    *,
    track: str,
    start: float,
    end: float,
    scene_number: str = "",
    source: str = "",
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """Insert a new freely-movable-track event (e.g. Inspector's "Add SFX",
    or the media browser dropping an ambience/music/text/graphics clip).
    Returns the new event_id, or None if the track isn't one this editor
    supports here — visual tracks use insert_visual_clip() instead, since
    they need ripple placement, not an arbitrary time window."""
    if track not in FREELY_MOVABLE_TRACKS:
        return None
    if end <= start:
        return None
    event_id = f"{track.lower()}-{uuid.uuid4().hex[:10]}"
    timeline.add(
        TimelineEvent(
            event_id=event_id,
            track=track,  # type: ignore[arg-type]
            start=round(float(start), 4),
            end=round(float(end), 4),
            scene_number=str(scene_number),
            source=str(source),
            metadata=dict(metadata or {}),
        )
    )
    return event_id


def insert_visual_clip(
    timeline: EditorialTimeline,
    *,
    track: str,
    at_time: float,
    duration: float,
    scene_number: str = "",
    source: str = "",
    metadata: Optional[dict] = None,
    snap: bool = True,
) -> Optional[str]:
    """Insert a new visual clip at ``at_time`` on ``track``.

    VIDEO_1/IMAGE (PRIMARY_VISUAL_TRACKS): rippled insert — ``at_time``
    snaps to the nearest existing visual clip boundary so it always lands
    cleanly between two clips (or at the very start/end), and every later
    primary clip shifts later by ``duration`` so nothing overlaps.

    VIDEO_2 (OVERLAY_VISUAL_TRACKS, real B-roll): placed directly at
    ``at_time`` with NO ripple of the primary playhead — it is an
    independent overlay track (see module docstring) and is expected to
    overlap VIDEO_1/IMAGE; that is the point. Its scene_number is derived
    automatically from whichever primary clip it lands on/nearest to (see
    _primary_scene_number_at) so reconcile_timeline_into_decisions() finds
    it in the right scene's bucket without the caller having to know."""
    if track not in VISUAL_TRACKS or duration <= 0:
        return None
    if track in OVERLAY_VISUAL_TRACKS:
        t = max(0.0, float(at_time))
        if snap:
            t = snap_time(t, scene_boundaries(timeline))
        end = t + float(duration)
        sn = str(scene_number) or _primary_scene_number_at(timeline, t, end)
        event_id = f"{track.lower()}-{uuid.uuid4().hex[:10]}"
        timeline.add(
            TimelineEvent(
                event_id=event_id,
                track=track,  # type: ignore[arg-type]
                start=round(t, 4),
                end=round(end, 4),
                scene_number=sn,
                source=str(source),
                z_index=10,
                metadata=dict(metadata or {}),
            )
        )
        return event_id
    t = snap_time(max(0.0, float(at_time)), scene_boundaries(timeline), tolerance=1e9)
    _ripple_shift_after(timeline, t, float(duration))
    event_id = f"{track.lower()}-{uuid.uuid4().hex[:10]}"
    timeline.add(
        TimelineEvent(
            event_id=event_id,
            track=track,  # type: ignore[arg-type]
            start=round(t, 4),
            end=round(t + float(duration), 4),
            scene_number=str(scene_number),
            source=str(source),
            z_index=10,
            metadata=dict(metadata or {}),
        )
    )
    return event_id


def partition_broll_overlaps(
    events: Sequence[TimelineEvent],
) -> "tuple[List[TimelineEvent], List[TimelineEvent]]":
    """The ONE shared definition of "which VIDEO_2 events are genuine
    B-roll overlays" — used by BOTH reconcile_timeline_into_decisions()
    (export) and preview_engine.build_visual_segments() (preview), so the
    two can never silently diverge on what counts as an overlay (task:
    "Do NOT duplicate the overlay implementation").

    Given any set of VISUAL_TRACKS events (typically one scene's, or a
    whole project's), returns (sequential, broll):
      - broll: OVERLAY_VISUAL_TRACKS (VIDEO_2) events that genuinely
        OVERLAP a PRIMARY_VISUAL_TRACKS (VIDEO_1/IMAGE) event in time.
      - sequential: everything else — every primary event, AND any VIDEO_2
        event that does NOT overlap a primary event (the common
        auto-generated dual-shot case), sorted by (start, track, id).
    """
    primary = [e for e in events if e.track in PRIMARY_VISUAL_TRACKS]
    candidates = [e for e in events if e.track in OVERLAY_VISUAL_TRACKS]

    def _overlaps_primary(ev: TimelineEvent) -> bool:
        return any(
            max(float(ev.start), float(p.start)) < min(float(ev.end), float(p.end))
            for p in primary
        )

    broll = [e for e in candidates if primary and _overlaps_primary(e)]
    broll_ids = {e.event_id for e in broll}
    sequential = sorted(
        (e for e in events if e.event_id not in broll_ids),
        key=lambda e: (float(e.start), e.track, e.event_id),
    )
    return sequential, broll


def reconcile_timeline_into_decisions(
    decisions: Sequence,
    timeline: EditorialTimeline,
) -> list:
    """Bridge an operator-edited EditorialTimeline back into the
    EditDecision/ShotSpec list the FFmpeg renderer actually consumes.

    This is the one function that makes visual-track edits (trim/split/
    delete/duplicate/reorder/replace/speed) genuinely affect the exported
    file, rather than being a cosmetic timeline-view-only change. Every
    ShotSpec field written here has a documented 1:1 origin in a
    TimelineEvent (see editorial/engine.py's build_timeline_from_decisions,
    which produces exactly these fields) — this is that mapping run in
    reverse.

    A scene whose visual clips were all deleted from the timeline is left
    UNCHANGED in the returned list (never rendered with zero visual
    coverage) — that case surfaces instead as a qc_issues() gap warning.

    Real B-roll: a VIDEO_2 event that genuinely OVERLAPS a VIDEO_1/IMAGE
    event in time (not just labeled "VIDEO_2" — see build_timeline_from_
    decisions, which alternates VIDEO_1/VIDEO_2 labels for purely
    SEQUENTIAL multi-shot coverage too) is pulled OUT of the sequential
    shots list and returned instead as a picture-in-picture overlay on
    EditDecision.broll (video_generator.composite_broll_overlay renders
    it). A non-overlapping VIDEO_2 event — the common case for an
    auto-generated dual-shot scene — is left as an ordinary sequential
    shot, unchanged from prior behavior.
    """
    from editorial.edit_decision import ShotSpec

    by_sn_events: Dict[str, List[TimelineEvent]] = {}
    for e in timeline.events:
        if e.track in VISUAL_TRACKS:
            by_sn_events.setdefault(str(e.scene_number), []).append(e)

    out = []
    for d in decisions:
        sn = str(d.scene_number)
        events = by_sn_events.get(sn)
        if not events:
            out.append(d)
            continue
        sequential_events, real_broll = partition_broll_overlaps(events)
        scene_start_abs = min((float(e.start) for e in sequential_events), default=0.0)

        shots = []
        for e in sequential_events:
            meta = e.metadata or {}
            shots.append(
                ShotSpec(
                    shot_id=e.event_id,
                    output_duration=max(0.05, float(e.duration)),
                    source_start=float(meta.get("source_start") or 0.0),
                    source_end=meta.get("source_end"),
                    scale=float(e.scale or 1.0),
                    crop_x=float(e.position_x if e.position_x is not None else 0.5),
                    crop_y=float(e.position_y if e.position_y is not None else 0.5),
                    speed=float(meta.get("speed") or 1.0),
                    shot_size=str(meta.get("shot_size") or "medium"),
                    camera_style=str(e.animation or "static"),
                    transition_in=str(e.transition_in or "cut"),
                    transition_duration=float(meta.get("transition_duration") or 0.0),
                    transition_direction=str(meta.get("transition_direction") or ""),
                    hold_tail=bool(meta.get("hold_tail", False)),
                    reason=str(meta.get("reason") or ""),
                    asset_id=str(meta.get("asset_id") or ""),
                    source_path=str(e.source or ""),
                    visual_role=str(meta.get("visual_role") or ""),
                    editorial_purpose=str(meta.get("editorial_purpose") or ""),
                )
            )

        broll_entries = []
        for e in real_broll:
            meta = e.metadata or {}
            broll_entries.append(
                {
                    "shot_id": e.event_id,
                    "source_path": str(e.source or ""),
                    "source_start": float(meta.get("source_start") or 0.0),
                    "speed": float(meta.get("speed") or 1.0),
                    "overlay_start": round(float(e.start) - scene_start_abs, 4),
                    "overlay_duration": round(float(e.duration), 4),
                    "scale": float(meta.get("broll_scale") or 0.4),
                    "position": str(meta.get("broll_position") or "bottom_right"),
                }
            )

        out.append(dataclasses.replace(d, shots=shots, broll=broll_entries))
    return out


# ---- SFX / AMBIENCE bridge --------------------------------------------
#
# smart_editing.py plans SFX/ambience INDEPENDENTLY of the editorial
# engine's own (semantic-only, unresolved) SFX EditorialEvents — it picks
# real catalog files (smart_editing.mix_sfx_with_narration /
# _resolve_sfx_file, resolved under smart_editing.sfx_library_root()) and
# mixes them directly into a pre-rendered narration WAV, bypassing the
# operator-facing EditorialTimeline entirely. That meant an operator's
# SFX/AMBIENCE edits in the Editor (move/trim/delete/volume/mute) had NO
# effect on the exported audio — the export always re-derived a fresh
# smart_editing plan from scratch. These two functions are the two-way
# bridge that fixes that, mirroring reconcile_timeline_into_decisions()'s
# approach for the visual tracks:
#   materialize_sfx_ambience_events() — first-cut time: replace the
#     semantic-only SFX/AMBIENCE placeholders with the REAL, resolved,
#     playable smart_editing plan, so what the operator sees/edits is what
#     will actually be heard.
#   sfx_ambience_events_for_export() — export time: read back the (possibly
#     operator-edited) SFX/AMBIENCE events into the dict shape
#     mix_sfx_with_narration() already expects.


def materialize_sfx_ambience_events(
    timeline: EditorialTimeline,
    *,
    sfx_events: Optional[Sequence[dict]] = None,
    ambience_beds: Optional[Sequence[dict]] = None,
) -> None:
    """Replace every SFX/AMBIENCE TimelineEvent with ones built from
    smart_editing.build_plan()'s resolved events. ``entry["file"]`` is kept
    catalog-relative in metadata (so export re-resolves it against
    sfx_library_root() exactly like the pre-existing mixer does) and also
    used as-is for ``.source`` — good enough for the timeline/UI to display
    a filename; the preview proxy resolves the real absolute path itself
    via smart_editing.sfx_library_root() (see preview_engine.py)."""
    timeline.events = [e for e in timeline.events if e.track not in ("SFX", "AMBIENCE")]
    for i, ev in enumerate(sfx_events or []):
        file_rel = str(ev.get("file") or "")
        if not file_rel:
            continue
        start = float(ev.get("start") or 0.0)
        end = float(ev.get("end") or (start + 0.5))
        if end <= start:
            end = start + 0.05
        timeline.add(
            TimelineEvent(
                event_id=f"sfx-{i}-{uuid.uuid4().hex[:8]}",
                track="SFX",  # type: ignore[arg-type]
                start=round(start, 4), end=round(end, 4),
                scene_number=str(ev.get("scene_number") or ""),
                source=file_rel,
                z_index=40,
                metadata={"file": file_rel, "volume": float(ev.get("volume") or 1.0)},
            )
        )
    for i, bed in enumerate(ambience_beds or []):
        file_rel = str(bed.get("file") or "")
        if not file_rel:
            continue
        start = float(bed.get("start") or 0.0)
        end = float(bed.get("end") or start)
        if end <= start:
            continue
        timeline.add(
            TimelineEvent(
                event_id=f"amb-{i}-{uuid.uuid4().hex[:8]}",
                track="AMBIENCE",  # type: ignore[arg-type]
                start=round(start, 4), end=round(end, 4),
                scene_number=str(bed.get("scene_number") or ""),
                source=file_rel,
                z_index=1,
                metadata={
                    "file": file_rel,
                    "volume": float(bed.get("volume") or 1.0),
                    "profile": str(bed.get("profile") or ""),
                },
            )
        )


def sfx_ambience_events_for_export(
    timeline: EditorialTimeline,
    *,
    muted_tracks: frozenset = frozenset(),
    solo_tracks: frozenset = frozenset(),
) -> "tuple[list, list]":
    """(sfx_events, ambience_beds) in the exact dict shape
    smart_editing.mix_sfx_with_narration() expects, built from the
    operator's current (possibly edited) SFX/AMBIENCE TimelineEvents —
    deletions, moves, volume/mute edits all flow through automatically
    since this reads whatever is on the timeline right now. Track-level
    mute/solo (TimelineCanvas header buttons) are applied here too, since
    those aren't per-event metadata."""
    any_solo = bool(solo_tracks)
    sfx: List[dict] = []
    ambience: List[dict] = []
    for e in timeline.events:
        if e.track not in ("SFX", "AMBIENCE"):
            continue
        if e.track in muted_tracks or bool((e.metadata or {}).get("muted")):
            continue
        if any_solo and e.track not in solo_tracks:
            continue
        meta = e.metadata or {}
        file_ref = str(meta.get("file") or e.source or "")
        if not file_ref:
            continue
        entry = {
            "start": round(float(e.start), 3),
            "end": round(float(e.end), 3),
            "volume": float(meta.get("volume", 1.0)),
            "file": file_ref,
        }
        if e.track == "SFX":
            sfx.append(entry)
        else:
            entry["profile"] = str(meta.get("profile") or "")
            entry["scene_number"] = str(e.scene_number or "")
            ambience.append(entry)
    return sfx, ambience


def qc_issues(timeline: EditorialTimeline) -> list:
    """Reuse the existing QC validator — never a bespoke re-implementation."""
    try:
        return validate_visual_timeline(timeline, audio_end=timeline.audio_end)
    except Exception:
        return []
