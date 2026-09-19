"""Real (not static/JPEG) proxy preview for the interactive Editor.

Builds two small, cached, real media files from the CURRENT (possibly
operator-edited) EditorialTimeline — the SAME EditorialTimeline export's
reconcile_timeline_into_decisions() reads, never a second editing model:

  - a video-only proxy MP4 covering the whole visual timeline, at reduced
    resolution/fps, reusing the SAME Ken Burns / camera-motion filter
    builders as the final renderer (video_generator._zoompan_filter,
    ._camera_motion, ._static_filter, ._video_fit_filter), the SAME real
    B-roll overlay primitive (video_generator.composite_broll_overlay —
    see build_visual_segments/render_segment_clip), and the SAME real
    xfade transition builder (video_generator.build_xfade_filter_complex —
    see build_video_proxy) export uses, so the preview genuinely matches
    final output's EDIT rather than approximating a different one, and
  - a mixed-down audio WAV (voiceover + music + ambience + sfx, honoring
    per-track/per-event volume and mute/solo) for real synced playback.

Both are cached per-segment via render_cache.RenderCache (Phase 1 — reused,
not reinvented) so re-opening the Editor or making one small edit only
re-encodes the segments that actually changed — see _segment_cache_key's
docstring for exactly what invalidates a given segment, and
build_video_proxy's assembly-level cache for why an edit that doesn't
touch the video timeline at all (e.g. an SFX-only change) never re-runs
the video concat/xfade step.

Deliberate, stated preview/export differences (never a different EDIT,
only different rendering cost/quality — see module's final report):
  - lower resolution/fps than the final export.
  - a genuine cut/crossfade/dip/wipe/slide requested at a boundary
    between two DIFFERENT B-roll compositing states of the SAME base clip
    (overlay turning on/off, not a real shot change) is not applied there
    — a real cut in the underlying primary clip is what actually receives
    the requested transition, exactly matching what export renders.

No new heavyweight media framework: this module only shells out to the
already-bundled ffmpeg binary (see app.py's ensure_ffmpeg_on_path()) and
reads its own cached output files with the stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from editorial.timeline import EditorialTimeline, TimelineEvent

# Schema bumped: segments now carry a real overlay (B-roll compositing) and
# the final assembly can be a real xfade chain instead of a plain concat —
# both change what a given cache entry actually represents, so old
# preview_proxy cache entries must never be reused across this boundary.
PROXY_SCHEMA_VERSION = 2
PROXY_DIRNAME = "preview_proxy"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def _ffmpeg_bin() -> str:
    return "ffmpeg"


def is_video_source(path: str) -> bool:
    return bool(path) and Path(path).suffix.lower() not in IMAGE_EXTS


@dataclass
class VisualSegment:
    """One contiguous, gap-free slice of the visual playhead — either a
    real TimelineEvent's on-screen window, or a synthesized black gap.
    ``overlay`` is a genuinely-overlapping VIDEO_2 B-roll event active for
    this segment's ENTIRE window (segments are split on overlay
    start/end too — see build_visual_segments — so a segment never needs
    to represent "overlay only during part of me"); None means no B-roll
    is active here."""

    start: float
    end: float
    event: Optional[TimelineEvent]
    overlay: Optional[TimelineEvent] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def is_gap(self) -> bool:
        return self.event is None


def build_visual_segments(timeline: EditorialTimeline) -> List[VisualSegment]:
    """Linear, gap-free list of segments covering [0, audio_end).

    Uses the SAME overlap definition export uses (editorial_timeline_edit.
    partition_broll_overlaps — one shared source of truth, never a second
    incompatible B-roll model): a VIDEO_2 event that genuinely overlaps a
    primary (VIDEO_1/IMAGE) event becomes a real overlay attached to every
    segment across its span (composited via video_generator.
    composite_broll_overlay in render_segment_clip — real simultaneous
    B-roll, not a hard z-index swap). A VIDEO_2 event that does NOT overlap
    any primary event is treated as ordinary sequential coverage, exactly
    like the auto-generated dual-shot case — unchanged from prior
    behavior. Among primary events that overlap each other (rare, e.g. a
    mid-transition edit state), the higher z_index one still wins for that
    window, same as before."""
    from editorial_timeline_edit import VISUAL_TRACKS, partition_broll_overlaps

    all_visual = [e for e in timeline.events if e.track in VISUAL_TRACKS]
    sequential, broll = partition_broll_overlaps(all_visual)
    primary = sorted(sequential, key=lambda e: (float(e.start), -int(e.z_index), e.event_id))

    end_limit = float(timeline.audio_end or 0.0)
    if all_visual:
        end_limit = max(end_limit, max(float(e.end) for e in all_visual))
    if end_limit <= 0:
        return []

    # Boundary list includes BOTH primary and overlay start/ends, so every
    # atomic segment has a constant (winner, overlay-or-None) pair across
    # its whole span — O(n log n), never O(n^2) even for 500-scene projects.
    boundaries = sorted(
        {0.0, end_limit}
        | {round(float(e.start), 4) for e in primary}
        | {round(float(e.end), 4) for e in primary}
        | {round(float(e.start), 4) for e in broll}
        | {round(float(e.end), 4) for e in broll}
    )
    segments: List[VisualSegment] = []
    for i in range(len(boundaries) - 1):
        t0, t1 = boundaries[i], boundaries[i + 1]
        if t1 - t0 <= 1e-4:
            continue
        mid = (t0 + t1) / 2.0
        candidates = [e for e in primary if float(e.start) <= mid < float(e.end)]
        winner = max(candidates, key=lambda e: (int(e.z_index), e.event_id)) if candidates else None
        overlay = next((e for e in broll if float(e.start) <= mid < float(e.end)), None)
        prev = segments[-1] if segments else None
        if prev is not None and prev.event is winner and prev.overlay is overlay:
            segments[-1] = VisualSegment(prev.start, t1, winner, overlay)
        else:
            segments.append(VisualSegment(t0, t1, winner, overlay))
    return segments


def _camera_filter_for_segment(seg: VisualSegment, width: int, height: int, fps: int) -> str:
    from video_generator import _camera_motion, _static_filter, _video_fit_filter, _zoompan_filter

    ev = seg.event
    source = ev.source if ev else ""
    if ev is None or not source:
        return f"color=c=black:s={width}x{height}:r={fps}:d={max(seg.duration, 0.05):.3f},format=yuv420p"
    if is_video_source(source):
        return _video_fit_filter(width, height, fps)
    frames = max(1, round(seg.duration * fps))
    use_zoom, zoom_in, style = _camera_motion(ev.animation, index=0, zoom=True)
    if not use_zoom:
        return _static_filter(width, height)
    return _zoompan_filter(width, height, fps, frames, zoom_in, 0.10, camera_style=style)


def _file_identity(path: str) -> tuple:
    try:
        st = Path(path).stat() if path and Path(path).is_file() else None
        return (st.st_mtime_ns, st.st_size) if st else (None, None)
    except OSError:
        return (None, None)


def _segment_cache_key(seg: VisualSegment, width: int, height: int, fps: int) -> str:
    """Cache identity for one rendered (and, if applicable, B-roll-
    composited) proxy segment. Covers every property that changes the
    rendered pixels — media identity, source offsets, speed, scale/
    position, AND (new) the overlay's own identity/timing/scale/position —
    so an edit to ONE clip (or its B-roll) invalidates only the affected
    segment(s), never the whole project (see module docstring / task 8)."""
    ev = seg.event
    meta = dict(ev.metadata or {}) if ev else {}
    payload = {
        "schema": PROXY_SCHEMA_VERSION,
        "source": ev.source if ev else None,
        "duration": round(seg.duration, 3),
        "scale": round(float(ev.scale), 3) if ev else None,
        "position": [round(float(ev.position_x), 3), round(float(ev.position_y), 3)] if ev else None,
        "animation": ev.animation if ev else None,
        "source_start": meta.get("source_start"),
        "speed": meta.get("speed"),
        "width": width, "height": height, "fps": fps,
    }
    if ev is not None and ev.source:
        payload["source_identity"] = _file_identity(ev.source)
    if seg.overlay is not None:
        ov = seg.overlay
        ov_meta = dict(ov.metadata or {})
        payload["overlay"] = {
            "source": ov.source,
            "source_identity": _file_identity(ov.source),
            "source_start": ov_meta.get("source_start"),
            "speed": ov_meta.get("speed"),
            "scale": ov_meta.get("broll_scale"),
            "position": ov_meta.get("broll_position"),
            # Where inside the overlay's OWN [start,end) this segment
            # falls — a later segment of the same overlay needs a
            # different source offset even though every other field above
            # is identical (see render_segment_clip).
            "offset_into_overlay": round(seg.start - float(ov.start), 3),
        }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_ffmpeg(args: Sequence[str], *, timeout: float = 30.0) -> bool:
    try:
        result = subprocess.run(
            [_ffmpeg_bin(), "-y", *args],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=timeout, text=True,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _is_valid_media_file(path: Path, *, min_duration: float = 0.0) -> bool:
    """A cheap, real (ffprobe-backed, not just "file exists and is
    non-empty") integrity check. Exists because a cached proxy segment CAN
    become truncated/corrupt through causes outside this module's control
    (an interrupted write, a killed process, disk pressure — reproduced
    for real: a concurrency race, since fixed, left several cached
    segments as truncated MP4s with no moov atom — ffmpeg happily reports
    success writing them, and a bare is_file()/size>0 check happily
    "hit" on them forever after, silently serving a wrong/incomplete
    preview indefinitely). Never trust "the file exists" alone for
    something that gets cached across app restarts."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10.0,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False
        return float(result.stdout.strip()) >= min_duration
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def render_segment_clip(seg: VisualSegment, out_path: Path, *, width: int, height: int, fps: int) -> bool:
    """Render one proxy segment to out_path — including real B-roll
    compositing when ``seg.overlay`` is set (reuses video_generator.
    composite_broll_overlay, the SAME primitive export uses — no second,
    incompatible overlay renderer). Best-effort: returns False (never
    raises) on any ffmpeg failure — the caller falls back to a black
    filler so one bad asset never blocks the whole preview. If the overlay
    composite specifically fails, the base clip (without B-roll) is kept
    rather than failing the whole segment — a partial-but-honest preview
    beats no preview."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ev = seg.event
    dur = max(seg.duration, 0.05)
    if ev is None or not ev.source:
        base_ok = _run_ffmpeg(
            [
                "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}:d={dur:.3f}",
                "-t", f"{dur:.3f}", "-an", "-r", str(fps), str(out_path),
            ]
        )
        return base_ok and _apply_overlay_if_any(seg, out_path, width=width, height=height, fps=fps)
    vf = _camera_filter_for_segment(seg, width, height, fps)
    source = ev.source
    meta = dict(ev.metadata or {})
    args: List[str] = []
    if is_video_source(source):
        from editorial_timeline_edit import clamp_speed

        speed = clamp_speed(meta.get("speed") or 1.0)
        src_start = float(meta.get("source_start") or 0.0)
        # -t must sit BEFORE -i (an INPUT read-limit on undecoded source
        # seconds) — placed after -i it becomes an OUTPUT duration cap
        # measured on the POST-setpts (already speed-compressed) timeline,
        # which reads far more source than intended and yields an output
        # `dur * speed` seconds long instead of `dur` (verified with real
        # ffmpeg: a 1.8x segment came out 3.6s instead of 2.0s — genuinely
        # wrong output duration, not merely "different quality"; export's
        # own _render_editorial_shot places -t correctly, this was a
        # preview-only bug this pass fixes).
        args += ["-ss", f"{max(0.0, src_start):.3f}", "-t", f"{dur * speed:.3f}", "-i", source]
        pts = f"setpts={1.0 / speed:.6f}*PTS," if abs(speed - 1.0) > 1e-3 else ""
        args += ["-vf", f"{pts}{vf}", "-an"]
    else:
        args += ["-loop", "1", "-i", source, "-t", f"{dur:.3f}", "-vf", vf, "-an"]
    args += ["-r", str(fps), str(out_path)]
    if not _run_ffmpeg(args):
        return False
    return _apply_overlay_if_any(seg, out_path, width=width, height=height, fps=fps)


def _apply_overlay_if_any(seg: VisualSegment, base_out: Path, *, width: int, height: int, fps: int) -> bool:
    """In-place: composite seg.overlay onto the just-rendered base_out, if
    any. The overlay is active for this segment's ENTIRE span (segments
    are split on overlay edges — see build_visual_segments), so it's a
    full-clip overlay: overlay_start=0, overlay_duration=segment duration."""
    ov = seg.overlay
    if ov is None or not ov.source:
        return True
    from editorial_timeline_edit import clamp_speed
    from video_generator import composite_broll_overlay

    meta = dict(ov.metadata or {})
    speed = clamp_speed(meta.get("speed") or 1.0)
    base_source_start = float(meta.get("source_start") or 0.0)
    # How far into the overlay's OWN [start,end) window this segment
    # begins, in SOURCE seconds (accounting for the overlay's own speed).
    offset_into_overlay = max(0.0, float(seg.start) - float(ov.start))
    composited = base_out.with_name(base_out.stem + "_broll" + base_out.suffix)
    ok = composite_broll_overlay(
        base_out, Path(ov.source), composited,
        overlay_start=0.0, overlay_duration=seg.duration,
        width=width, height=height, fps=fps,
        broll_source_start=base_source_start + offset_into_overlay * speed,
        broll_speed=speed,
        scale=float(meta.get("broll_scale") or 0.4),
        position=str(meta.get("broll_position") or "bottom_right"),
    )
    if ok and composited.is_file():
        try:
            composited.replace(base_out)
        except OSError:
            return True  # keep the un-composited base — never fail the segment
    else:
        try:
            composited.unlink(missing_ok=True)
        except OSError:
            pass
    return True


def _segment_transition_in(seg: VisualSegment) -> Optional["tuple[str, float, str]"]:
    """The real transition requested INTO this segment (same convention
    export uses — video_generator.render_video reads it off the scene's
    first shot's transition_in/transition_duration/transition_direction).
    None if this segment doesn't open with a real, positive-duration
    transition from video_generator.TRANSITION_TYPES."""
    from video_generator import TRANSITION_TYPES

    ev = seg.event
    if ev is None:
        return None
    meta = dict(ev.metadata or {})
    ttype = str(ev.transition_in or "cut").lower()
    tdur = float(meta.get("transition_duration") or 0.0)
    if ttype in TRANSITION_TYPES and ttype != "cut" and tdur > 0.0:
        return (ttype, tdur, str(meta.get("transition_direction") or ""))
    return None


def build_video_proxy(
    state_dir: Path,
    timeline: EditorialTimeline,
    *,
    width: int = 480,
    height: int = 270,
    fps: int = 15,
) -> Optional[Path]:
    """Build (or reuse from cache) the video-only proxy for the current
    timeline — including real B-roll compositing (render_segment_clip) and
    real xfade transitions at cuts that request one (SAME vocabulary/
    filter-graph builder as export: video_generator.TRANSITION_TYPES /
    build_xfade_filter_complex — one shared transition semantics, never a
    second incompatible one). Returns None if the timeline has no visual
    content."""
    from render_cache import RenderCache

    segments = build_visual_segments(timeline)
    if not segments:
        return None
    proxy_dir = Path(state_dir) / PROXY_DIRNAME
    proxy_dir.mkdir(parents=True, exist_ok=True)
    cache = RenderCache(proxy_dir)
    # A per-CALL unique scratch prefix — critical for rapid editing (task
    # 17/18): two overlapping build_video_proxy() invocations (an in-flight
    # background thread from an earlier edit, still running when a newer
    # edit starts another one — the debounce only prevents a *scheduled*
    # rebuild from starting late, it does not cancel one already running)
    # must never write their scratch renders to the SAME plain filename
    # (the old `_render_{i}.mp4` — no per-call identity at all). Two
    # threads racing on that shared path could corrupt or delete each
    # other's in-progress ffmpeg output — reproduced for real: a live
    # project's proxy build failed outright after rapid edits, traced back
    # to exactly this collision (see final report).
    build_id = uuid.uuid4().hex[:10]
    clip_paths: List[Path] = []
    seg_keys: List[str] = []
    for i, seg in enumerate(segments):
        key = f"seg_{i}"
        cache_key = _segment_cache_key(seg, width, height, fps)
        seg_keys.append(cache_key)
        hit = cache.get(key, cache_key)
        # A cache "hit" is only trustworthy if the file is actually a
        # valid, decodable clip — RenderCache.get() itself only checks
        # is_file()/size>0, which a truncated/corrupt MP4 (e.g. from an
        # interrupted write) satisfies just as well as a good one, and
        # then serves FOREVER, across every future build and app restart
        # (reproduced for real — see _is_valid_media_file's docstring).
        if hit is not None and not _is_valid_media_file(hit, min_duration=0.03):
            hit = None
        if hit is not None:
            clip_paths.append(hit)
            continue
        tmp_out = proxy_dir / f"_render_{build_id}_{i}.mp4"
        ok = render_segment_clip(seg, tmp_out, width=width, height=height, fps=fps)
        if ok and tmp_out.is_file() and _is_valid_media_file(tmp_out, min_duration=0.03):
            cache.put(key, cache_key, tmp_out)
            hit2 = cache.get(key, cache_key)
            clip_paths.append(hit2 if hit2 is not None else tmp_out)
        try:
            tmp_out.unlink(missing_ok=True)
        except OSError:
            pass

    if len(clip_paths) != len(segments):
        # A partial failure (one segment's render or cache-validity check
        # failed) must never silently produce a WRONG-but-plausible-
        # looking preview — a shortened/incomplete video with no
        # indication anything is missing is worse than an honest failure
        # (task: "no fake preview"; also the transition-index math below
        # assumes clip_paths is a 1:1, in-order match to segments, which a
        # dropped MIDDLE segment would silently violate). The caller
        # (EditorView._apply_proxy) already shows a clear, honest
        # "preview couldn't be built" state and safely retries on the
        # next edit — nothing here risks the timeline itself.
        return None

    # A real transition applies only at a boundary where the underlying
    # PRIMARY clip actually changes (a real cut) — NOT at a boundary that's
    # only an overlay turning on/off over the SAME base clip (see
    # build_visual_segments — those share `.event` but differ in
    # `.overlay`), which would otherwise wipe/crossfade into "the same
    # shot, now with B-roll", a nonsensical visual glitch.
    transitions: List[Optional[tuple]] = []
    any_transition = False
    for i in range(1, len(segments)):
        t = None
        if segments[i].event is not segments[i - 1].event:
            t = _segment_transition_in(segments[i])
        transitions.append(t)
        any_transition = any_transition or t is not None

    if any_transition:
        # build_xfade_filter_complex chains ALL boundaries through ONE
        # continuous xfade filter graph once ANY real transition is
        # requested anywhere — every OTHER boundary (a plain cut the
        # operator never touched) is submitted as None, which the shared
        # function (unmodified — export's own code) turns into an
        # implicit MIN_XFADE_DURATION (0.05s) blend. Confirmed with real
        # ffmpeg: at this proxy's LOW fps (10-15, vs export's 24-30+),
        # 0.05s rounds to under a single frame, and ffmpeg's xfade filter
        # does not degrade gracefully there — it corrupts the ENTIRE
        # chained output (a correct ~5.3s result came back as 1.5s, even
        # with just two plain-cut boundaries and no real transition
        # anywhere near them). Replacing every None with an EXPLICIT,
        # frame-safe "cut" duration avoids ever handing the shared
        # function a sub-frame value, without changing that function or
        # export's own fps/behavior at all.
        frame_floor = max(2.0 / max(fps, 1), 0.05)
        for k in range(len(transitions)):
            if transitions[k] is None:
                transitions[k] = ("cut", frame_floor, "")

        # Guard against a degenerate xfade chain (also found for real):
        # each transition is clamped against its two immediate neighbors
        # INDEPENDENTLY by build_xfade_filter_complex, correct for
        # export's normal case (one real cut between two whole scenes)
        # but not safe here — B-roll-overlay segment splitting can put a
        # SHORT segment between two boundaries that EACH want a blend, so
        # it gets squeezed from both sides at once. Cap each transition to
        # a share of BOTH neighbors' duration so no segment is ever
        # over-consumed from both ends together.
        for k, t in enumerate(transitions):
            ttype, tdur, tdir = t
            left_dur, right_dur = segments[k].duration, segments[k + 1].duration
            safe = max(frame_floor, min(tdur, left_dur * 0.4, right_dur * 0.4))
            if safe != tdur:
                transitions[k] = (ttype, safe, tdir)

    assembly_payload = {"segs": seg_keys, "transitions": transitions, "fps": fps}
    assembly_key = hashlib.sha256(json.dumps(assembly_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]
    out_path = proxy_dir / f"proxy_video_{assembly_key}.mp4"
    if out_path.is_file() and out_path.stat().st_size > 0:
        if _is_valid_media_file(out_path, min_duration=sum(s.duration for s in segments) * 0.5):
            _prune_stale_assemblies(proxy_dir, keep=out_path)
            return out_path
        # A cached assembly that's corrupt OR suspiciously short (well
        # under half the expected total — exactly how the real incident
        # this check exists for looked: a 1.8s file cached in place of a
        # correct 5.1s one) must never be served silently — fall through
        # and rebuild it fresh instead of trusting stale bytes on disk.

    # Write to a build_id-unique scratch path, then atomically rename into
    # the content-addressed final name (os.replace is an atomic rename on
    # POSIX and Windows) — a concurrent build racing toward the SAME
    # assembly_key (e.g. an undo landing back on an already-seen state)
    # can never make another reader observe a half-written file.
    scratch_out = proxy_dir / f"_assembly_{build_id}.mp4"
    if any_transition and len(clip_paths) > 1:
        from video_generator import build_xfade_filter_complex

        durations = [max(0.05, seg.duration) for seg in segments[: len(clip_paths)]]
        try:
            filter_complex, video_label = build_xfade_filter_complex(durations, transitions)
        except ValueError:
            filter_complex, video_label = None, None
        ok = False
        if filter_complex:
            cmd: List[str] = []
            for p in clip_paths:
                cmd += ["-i", str(p)]
            cmd += [
                "-filter_complex", filter_complex, "-map", f"[{video_label}]",
                "-an", "-r", str(fps), str(scratch_out),
            ]
            ok = _run_ffmpeg(cmd, timeout=120.0)
        if not ok:
            # A broken xfade graph must never take down the whole preview —
            # fall back to a plain cut concat so editing still shows SOMETHING.
            ok = _concat_clips(clip_paths, scratch_out, fps=fps, build_id=build_id)
    else:
        ok = _concat_clips(clip_paths, scratch_out, fps=fps, build_id=build_id)

    expected_total = sum(s.duration for s in segments)
    if ok and scratch_out.is_file() and scratch_out.stat().st_size > 0 and _is_valid_media_file(scratch_out, min_duration=expected_total * 0.5):
        try:
            os.replace(scratch_out, out_path)
        except OSError:
            try:
                scratch_out.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        _prune_stale_assemblies(proxy_dir, keep=out_path)
        return out_path
    try:
        scratch_out.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def _concat_clips(clip_paths: List[Path], out_path: Path, *, fps: int, build_id: Optional[str] = None) -> bool:
    from video_generator import write_ffmpeg_concat_list

    # Unique per call (task 17/18) — a shared "concat_list.txt" name would
    # let two concurrent builds (an in-flight rebuild from a rapid edit,
    # racing a newer one) overwrite each other's list mid-read, exactly
    # the class of bug that corrupted a real project's proxy build (see
    # build_video_proxy's build_id comment / final report).
    suffix = build_id or uuid.uuid4().hex[:10]
    concat_list = out_path.parent / f"concat_list_{suffix}.txt"
    try:
        write_ffmpeg_concat_list(clip_paths, concat_list)
        ok = _run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(out_path)],
            timeout=60.0,
        )
        if not ok:
            # Re-encode concat (mismatched codecs/params across cached segments).
            ok = _run_ffmpeg(
                ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-r", str(fps), str(out_path)],
                timeout=90.0,
            )
        return ok
    finally:
        try:
            concat_list.unlink(missing_ok=True)
        except OSError:
            pass


_ASSEMBLY_PRUNE_GRACE_S = 120.0


def _prune_stale_assemblies(proxy_dir: Path, *, keep: Path) -> None:
    """Bounded disk usage (task 25): an assembled proxy (proxy_video_
    <hash>.mp4) from an edit state nobody's on anymore is dead weight —
    remove it rather than letting every edit leave one behind forever.
    Individual segment clips stay under RenderCache's own eviction policy
    (untouched here).

    Deliberately conservative — only removes files older than a generous
    grace period (_ASSEMBLY_PRUNE_GRACE_S), NEVER "everything but the one
    I just made": rapid editing (task 17/18) can have several builds for
    DIFFERENT edit states genuinely in flight/just-finished at once (an
    in-flight background build from an earlier edit, still running when a
    newer edit starts another one), and an eager "delete anything not
    mine" or even "delete anything older than mine" sweep can delete a
    sibling build's output the instant before that build's own caller
    checks it exists — reproduced for real with concurrent threads during
    this pass's own testing. A grace period means a normal edit session
    (rebuilds arrive seconds apart) never accumulates unbounded files,
    while two builds racing within the same second can't destroy each
    other."""
    try:
        now = time.time()
        for p in proxy_dir.glob("proxy_video_*.mp4"):
            if p == keep:
                continue
            try:
                if now - p.stat().st_mtime > _ASSEMBLY_PRUNE_GRACE_S:
                    p.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        pass


# ---- audio mixdown --------------------------------------------------------

AUDIO_TRACKS = ("VOICEOVER", "MUSIC", "AMBIENCE", "SFX")


def resolve_audio_source(e: TimelineEvent) -> str:
    """An SFX/AMBIENCE event's ``.source``/``metadata["file"]`` is a
    catalog-relative path (see editorial_timeline_edit.
    materialize_sfx_ambience_events — the SAME contract
    smart_editing.mix_sfx_with_narration's _resolve_sfx_file uses for
    export), not directly openable by ffmpeg from an arbitrary cwd.
    VOICEOVER/MUSIC sources are already absolute project paths and pass
    through unchanged. Returns "" if nothing resolves."""
    raw = str((e.metadata or {}).get("file") or e.source or "")
    if not raw:
        return ""
    p = Path(raw)
    if p.is_absolute():
        return raw if p.is_file() else ""
    if e.track in ("SFX", "AMBIENCE"):
        try:
            from smart_editing import sfx_library_root

            resolved = sfx_library_root() / raw
            return str(resolved) if resolved.is_file() else ""
        except Exception:
            return ""
    return raw if p.is_file() else ""


def _audio_events(timeline: EditorialTimeline, *, muted_tracks: frozenset = frozenset(), solo_tracks: frozenset = frozenset()) -> List[TimelineEvent]:
    any_solo = bool(solo_tracks)
    out = []
    for e in timeline.events:
        if e.track not in AUDIO_TRACKS or not resolve_audio_source(e):
            continue
        if e.track in muted_tracks or bool((e.metadata or {}).get("muted")):
            continue
        if any_solo and e.track not in solo_tracks:
            continue
        out.append(e)
    return out


def _voiceover_track_active(
    voiceover_path: Optional[Path], *, muted_tracks: frozenset, solo_tracks: frozenset
) -> bool:
    if not voiceover_path:
        return False
    try:
        if not Path(voiceover_path).is_file():
            return False
    except OSError:
        return False
    if "VOICEOVER" in muted_tracks:
        return False
    if solo_tracks and "VOICEOVER" not in solo_tracks:
        return False
    return True


def build_audio_mix(
    state_dir: Path,
    timeline: EditorialTimeline,
    *,
    muted_tracks: frozenset = frozenset(),
    solo_tracks: frozenset = frozenset(),
    voiceover_path: Optional[Path] = None,
) -> Optional[Path]:
    """Mix every real, unmuted audio-track event into one WAV honoring
    per-event volume overrides (event.metadata["volume"], default 1.0) and
    track-level mute/solo — real audio reflecting the actual edit state,
    cached by the content+settings that went into it.

    ``voiceover_path``: the REAL recorded narration file (see
    ProjectWorkspace.get_active_voiceover/find_voiceover_audio). Real
    projects' VOICEOVER TimelineEvents carry an EMPTY ``.source`` — they
    are just per-beat timing markers (the narration is one continuous,
    immutable recording, never a set of separate per-clip files like SFX/
    AMBIENCE — see editorial_timeline_edit's module docstring) — so they
    are correctly excluded from the generic per-event loop below (their
    resolve_audio_source() is "") and are NOT what makes narration
    audible. Without this parameter, voiceover was silently missing from
    every preview mix entirely (confirmed live on a real project: the
    preview played video with no narration at all, with no error or
    indication why — reported directly as "voiceover not playing").
    Mirrors export's own model exactly (video_generator.render_video's
    audio_path IS this same whole file, with mix_sfx_with_narration only
    ever ADDING SFX/ambience on top of it — never per-event-trimming the
    narration itself), so this is real parity, not an invented behavior.
    Per-event VOICEOVER volume metadata is intentionally NOT applied here
    — export doesn't apply it either (there is no code path that reads a
    VOICEOVER TimelineEvent's per-event volume at export time), so
    skipping it here is consistent parity, not a new preview-only gap."""
    events = _audio_events(timeline, muted_tracks=muted_tracks, solo_tracks=solo_tracks)
    voiceover_active = _voiceover_track_active(voiceover_path, muted_tracks=muted_tracks, solo_tracks=solo_tracks)
    if not events and not voiceover_active:
        return None
    proxy_dir = Path(state_dir) / PROXY_DIRNAME
    proxy_dir.mkdir(parents=True, exist_ok=True)
    # NOT timeline.audio_end directly — see editorial_timeline_edit.
    # timeline_duration's docstring. An edit extending a visual (or audio)
    # clip past the narration's own length must extend the mixed audio's
    # own output length too, or the extra portion plays back silent even
    # though the video proxy correctly shows it.
    from editorial_timeline_edit import timeline_duration

    mix_dur = timeline_duration(timeline)
    if not mix_dur:
        mix_dur = max((e.end for e in events), default=0.0)
    payload = {
        "schema": PROXY_SCHEMA_VERSION,
        "muted": sorted(muted_tracks), "solo": sorted(solo_tracks),
        "duration": round(mix_dur, 3),
        "voiceover": (
            [str(voiceover_path), _file_identity(str(voiceover_path))] if voiceover_active else None
        ),
        "events": [
            [resolve_audio_source(e), round(float(e.start), 3), round(float(e.end), 3), float((e.metadata or {}).get("volume", 1.0))]
            for e in events
        ],
    }
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    out_path = proxy_dir / f"audio_mix_{key}.wav"
    if out_path.is_file() and out_path.stat().st_size > 0:
        return out_path

    inputs: List[str] = []
    filter_parts: List[str] = []
    labels: List[str] = []
    if voiceover_active:
        inputs += ["-i", str(voiceover_path)]
        filter_parts.append(f"[0:a]atrim=0:{mix_dur:.3f},asetpts=PTS-STARTPTS[a0]")
        labels.append("[a0]")
    for e in events:
        i = len(labels)
        vol = float((e.metadata or {}).get("volume", 1.0))
        delay_ms = max(0, round(float(e.start) * 1000))
        inputs += ["-i", resolve_audio_source(e)]
        filt = f"[{i}:a]atrim=0:{e.duration:.3f},adelay={delay_ms}:all=1,volume={vol:.3f}[a{i}]"
        filter_parts.append(filt)
        labels.append(f"[a{i}]")
    filter_complex = ";".join(filter_parts) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0[mixed]"
    # Write to a per-call scratch path then atomically rename into the
    # content-addressed final name — two concurrent builds landing on the
    # SAME key (e.g. undo returning to an already-seen audio state) must
    # never let a reader (the player opening this WAV for playback) see a
    # half-written file (task 17/18 — same class of race fixed in
    # build_video_proxy's build_id comment).
    scratch_out = proxy_dir / f"_audio_mix_{uuid.uuid4().hex[:10]}.wav"
    args = [*inputs, "-filter_complex", filter_complex, "-map", "[mixed]", "-t", f"{mix_dur:.3f}", str(scratch_out)]
    ok = _run_ffmpeg(args, timeout=60.0)
    if ok and scratch_out.is_file() and scratch_out.stat().st_size > 0:
        try:
            os.replace(scratch_out, out_path)
            return out_path
        except OSError:
            pass
    try:
        scratch_out.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def effective_state_at(
    timeline: EditorialTimeline,
    t: float,
    *,
    muted_tracks: frozenset = frozenset(),
    solo_tracks: frozenset = frozenset(),
) -> Dict[str, object]:
    """The resolved preview plan at timeline time ``t`` — a deterministic,
    inspectable snapshot for tests (and, if useful, debugging) that never
    requires rendering or comparing pixels (task: "PREVIEW SEMANTIC
    SNAPSHOT"). Built from build_visual_segments()/_audio_events() — the
    SAME functions the real proxy pipeline uses, so this snapshot can
    never silently diverge from what actually gets rendered.

    Returns a dict:
      primary_event_id / primary_source / primary_effective_source_time /
        primary_speed — the active VIDEO_1/IMAGE (or VIDEO_2-if-sequential)
        clip and where in ITS source media playback is at time t.
      overlay_event_id / overlay_source / overlay_effective_source_time /
        overlay_speed — the active B-roll overlay, or all None if none.
      transition — {type, duration, direction} if `t` falls inside a real
        transition's window at a genuine cut boundary, else None.
      audio — list of {track, event_id, volume} for every audio event
        actually audible at `t` (already filtered by mute/solo/track-mute,
        matching what build_audio_mix would actually mix in).
    """
    from editorial_timeline_edit import clamp_speed

    segments = build_visual_segments(timeline)
    idx = next((i for i, s in enumerate(segments) if s.start <= t < s.end), None)
    seg = segments[idx] if idx is not None else None

    def _clip_state(ev: Optional[TimelineEvent], seg_start: float) -> "tuple[Optional[str], Optional[str], Optional[float], Optional[float]]":
        if ev is None:
            return None, None, None, None
        meta = dict(ev.metadata or {})
        speed = clamp_speed(meta.get("speed") or 1.0)
        src_start = float(meta.get("source_start") or 0.0)
        elapsed = max(0.0, float(t) - float(seg_start))
        return ev.event_id, ev.source, round(src_start + elapsed * speed, 3), speed

    primary_id, primary_src, primary_t, primary_speed = _clip_state(seg.event if seg else None, seg.start if seg else 0.0)
    overlay_id, overlay_src, overlay_t, overlay_speed = (
        _clip_state(seg.overlay, float(seg.overlay.start)) if seg and seg.overlay else (None, None, None, None)
    )

    transition = None
    if seg is not None and idx is not None and idx > 0 and segments[idx - 1].event is not seg.event:
        spec = _segment_transition_in(seg)
        if spec is not None:
            ttype, tdur, tdir = spec
            if float(t) < float(seg.start) + tdur:
                transition = {"type": ttype, "duration": tdur, "direction": tdir or "left"}

    audio = [
        {
            "track": e.track,
            "event_id": e.event_id,
            "volume": float((e.metadata or {}).get("volume", 1.0)),
        }
        for e in _audio_events(timeline, muted_tracks=muted_tracks, solo_tracks=solo_tracks)
        if float(e.start) <= float(t) < float(e.end)
    ]

    return {
        "primary_event_id": primary_id,
        "primary_source": primary_src,
        "primary_effective_source_time": primary_t,
        "primary_speed": primary_speed,
        "overlay_event_id": overlay_id,
        "overlay_source": overlay_src,
        "overlay_effective_source_time": overlay_t,
        "overlay_speed": overlay_speed,
        "transition": transition,
        "audio": audio,
    }


def clear_proxy_cache(state_dir: Path) -> None:
    """Best-effort wipe of the whole preview proxy directory (e.g. after a
    project's assets were regenerated from scratch)."""
    try:
        shutil.rmtree(Path(state_dir) / PROXY_DIRNAME, ignore_errors=True)
    except OSError:
        pass
