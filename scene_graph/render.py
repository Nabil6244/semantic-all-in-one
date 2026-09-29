"""Render one Overscaled segment to a standalone MP4 clip via FFmpeg.

Fixed-canvas motion-design compositor: the canvas is exactly the output
resolution (e.g. 1920x1080), the background is always plain white, and THE
CAMERA NEVER MOVES. There are no camera legs, no per-leg FFmpeg encodes, and
no concatenation. Every node/edge is one timed overlay layer (a short
fade+scale-in "reveal", then a static "hold" for the rest of the segment —
persistent, editorial-board style) composited into a SINGLE ffmpeg
filter_complex graph that produces the WHOLE clip in ONE encode.

This is the ONLY place that talks to FFmpeg for Overscaled content, and it
produces an ordinary video file — no audio, no container tricks. The
existing EditorialTimeline/preview/export pipeline then treats that file
exactly like any other VIDEO_1 source (a Flow render, a stock clip, ...):
this module never modifies video_generator.py, preview_engine.py, or
editorial/timeline.py, because from their point of view there is nothing
new to understand.

This is a TIMED editorial composition, not a mind-map/storyboard renderer:
scene_graph.layout already scoped every node/edge to its own "chapter turn"
(``layout.active_windows`` / ``layout.edge_windows``) so that only ~1-3
cards are ever on screen at once — this module's only job is to composite
exactly that timeline, never to fall back to showing everything at once.

Reference-verified behavior (frames pulled from the real "Overscaled"
channel's own videos): new elements FADE in, but an element that is no
longer needed simply CUTS out instantly on the same beat that brings the
next element in — there is no mirrored fade-out. This module matches that:
every layer below fades in, then holds, then is simply absent past its
window's end (nothing scheduled there — nothing to fade).

Technique:
  1. A plain white (or style-configured) `color` source spans the WHOLE
     segment duration — the fixed, never-moving canvas.
  2. Each node gets, for its OWN active window only (not the whole segment):
       - a short Pillow-rendered fade+scale-in PNG SEQUENCE (~0.2-0.4s at
         the target fps — see scene_graph.composition.render_node_reveal_frame),
         fed to ffmpeg via `-itsoffset <window_start> -framerate fps
         -i seq/%05d.png` so it starts exactly on time and simply isn't
         present before then;
       - optionally ONE static "settled" PNG held via `-loop 1 -t <hold>`
         for the rest of the window — then nothing: an instant hard cut
         away, matching the reference (see module docstring above).
     A `video_loop` node whose resolved media is an actual video file gets
     its shadow+border+caption rendered "hollow" (transparent interior) and
     the REAL source video decoded live, scaled to the card and clipped to
     its own window, and overlaid underneath that hollow decoration —
     genuine video-in-card playback, not a static thumbnail.
  3. Each edge (causal arrow) gets the same reveal+hold treatment, scoped to
     ``layout.edge_windows`` (the intersection of its two endpoints' own
     windows — an arrow can never outlive either endpoint), using
     scene_graph.composition.render_edge_reveal_frame's progressive
     hand-sketched draw-on, plus an optional inline text label
     (``edge.metadata["label"]``) once the stroke finishes drawing.
  4. Each persistent chapter/subject title (``layout.title_windows`` — bold
     centered text, independent of any image node — see
     scene_graph.composition.render_title_reveal_frame) gets the same
     fade-in-then-hold-then-cut treatment as a node.
  5. All of the above are chained with plain `overlay` filters (titles
     first, then nodes in narration order, then edges on top) and encoded
     ONCE — no intermediate per-object or per-leg MP4s.

Reuses providers.ffmpeg_runner.run_ffmpeg for process execution (timeouts /
stall detection / binary resolution), the same call other renderers use.
"""

from __future__ import annotations

import dataclasses
import math
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from map_scene.clip import is_map_clip
from media_duration import probe_media_duration
from providers.ffmpeg_runner import encode_argv, run_ffmpeg

from .composition import (
    VIDEO_SUFFIXES,
    render_checklist_strip_frame,
    render_edge_reveal_frame,
    render_node_decoration_frame,
    render_node_media_only_frame,
    render_node_reveal_frame,
    render_title_reveal_frame,
)
from .layout import MARGIN_PX, SceneGraphLayout
from .map_nodes import is_map_node
from .schema import SceneEdge, SceneGraph, SceneNode
from .style_presets import StylePreset

# Per the Overscaled spec: fade/scale-in reveals stay short and restrained.
NODE_REVEAL_DURATION_S = 0.3
_NODE_REVEAL_RANGE = (0.2, 0.4)
EDGE_REVEAL_DURATION_S = 0.65
_EDGE_REVEAL_RANGE = (0.5, 0.8)

_MIN_HOLD_S = 0.04  # ffmpeg needs a strictly positive -t

# Ken Burns applies only to static images/diagrams held on screen — never to
# video_loop (real footage already moves), anchor cards, or the brief
# reveal-in itself. Motion is expressed entirely by FFmpeg's own `zoompan`
# filter (no per-frame Python re-render): the media crop is rendered ONCE
# (render_node_media_only_frame) and fed to ffmpeg as a single looped input
# frame; zoompan generates the whole zoom/pan sequence internally from cached,
# deterministic parameters solved once in scene_graph.layout
# (layout.node_ken_burns — see routing.deterministic_unit).
_KEN_BURNS_NODE_TYPES = ("image", "diagram")


def _kenburns_pre_filter(
    *, width: int, height: int, hold_start: float, hold_duration: float, fps: int,
    zoom_end: float, pan_x: float, pan_y: float, offset_expr: Optional[str] = None,
) -> str:
    """Build the zoompan+trim+setpts chain that turns ONE static input frame
    into a smooth ``hold_duration``-long zoom/pan clip, correctly positioned
    on the segment's global timeline.

    Three real ffmpeg gotchas this works around (verified empirically):
      - zoompan's `d` is "output frames per INPUT frame arrival" — feeding it
        many input frames (the default loop framerate) multiplies the frame
        count by d, causing a 100x+ duration blowup. Fixed by `-framerate 1`
        on the input (see the layer's input_args) so only ONE input frame is
        ever delivered before `trim` closes the stream.
      - `d=1` (naively "one output per input frame") resets the zoom state
        every frame instead of accumulating it — the zoom expression's
        `zoom` variable does not persist the way a continuous video stream
        would. `d` must equal the FULL frame count for one static photo.
      - zoompan resets PTS to start at 0, silently discarding the input's
        own `-itsoffset` shift — breaks `eof_action=pass` timing on the
        overlay. Fixed by an explicit `setpts=PTS-STARTPTS+{offset}/TB`
        after `trim` to restore the correct global timestamp.
    """
    # Frame count by the same [start, end) sampling rule as every other
    # layer (see _frame_span), so the Ken Burns clip and its decoration hold
    # cover exactly the same frames. ``offset_expr`` lets the renderer
    # substitute a segment-relative start (see _Layer.filter).
    d_frames = _frame_span(hold_start, hold_start + hold_duration, fps)
    rate = (zoom_end - 1.0) / max(1, d_frames - 1)
    dx_px = pan_x * width
    dy_px = pan_y * height
    zoom_expr = f"min(zoom+{rate:.8f},{zoom_end:.6f})"
    x_expr = f"max(0,min(iw-iw/zoom,(iw-iw/zoom)/2+{dx_px:.3f}*(on/{d_frames})))"
    y_expr = f"max(0,min(ih-ih/zoom,(ih-ih/zoom)/2+{dy_px:.3f}*(on/{d_frames})))"
    offset = offset_expr if offset_expr is not None else f"{hold_start:.6f}"
    return (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':s={width}x{height}:d={d_frames}:fps={fps},"
        f"trim=end_frame={d_frames},setpts=PTS-STARTPTS+{offset}/TB,format=rgba,{_TRAILING_PAD}"
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value if value > 0 else lo))


def _is_video_file(path: Optional[str]) -> bool:
    if not path:
        return False
    return Path(path).suffix.lower() in VIDEO_SUFFIXES


class RenderCancelled(Exception):
    """The user stopped the render (see render_overscaled_segment's
    ``cancel_check``) — a distinct outcome from a failure."""


_OFFSET_TOKEN = "{OFFSET}"
# Input option for every still-image (PNG) input: a single-threaded decoder.
# ffmpeg otherwise gives EACH input a CPU-sized frame-thread pool — measured
# ~19 threads per input; with this, half the threads and ~30% less RSS at
# the same speed (stills gain nothing from threaded decoding). Live video
# card inputs keep ffmpeg's default threading.
_STILL_DECODE = ("-threads", "1")
# Appended to finite, filter-timed inputs (Ken Burns clips, reveal
# sequences): one cloned trailing frame, never drawn (each overlay's enable
# range covers exactly the layer's own frames). Without it overlay's
# eof_action=pass sometimes treats the last visible frame as end-of-stream
# and skips it — measured: the Ken Burns photo vanished for one frame at the
# end of its card (visible in the original renderer too), and a segment
# boundary inside such a clip reproduced it.
_TRAILING_PAD = "tpad=stop=1:stop_mode=clone"
_REVEAL_PRE = f"format=rgba,{_TRAILING_PAD}"


@dataclasses.dataclass
class _Layer:
    """One ffmpeg input + the overlay filter step that composites it.

    ``offset`` is the layer's global start (its ``-itsoffset``) and
    ``duration`` how long it is on screen, so the renderer can place it in a
    time SEGMENT (see _plan_segments) by shifting its offset; with shift=0
    the generated argv/filter are exactly what a single-pass render uses.
    ``pre_filter`` may contain ``{OFFSET}``, replaced by the shifted offset
    (zoompan resets PTS and must restore it explicitly)."""

    input_args: List[str]  # everything after "-itsoffset <offset>"
    offset: float = 0.0
    duration: float = 0.0
    frames: int = 0  # output frames this layer is visible on (0: derive from duration)
    overlay_xy: Tuple[int, int] = (0, 0)
    pre_filter: str = ""  # optional per-input filter (e.g. scale/pad/fade) before the overlay

    @property
    def end(self) -> float:
        return self.offset + self.duration

    def argv(self, shift: float = 0.0, fps: int = 0) -> List[str]:
        return ["-itsoffset", f"{_snap(self.offset - shift, fps):.6f}", *self.input_args]

    def filter(self, shift: float = 0.0, fps: int = 0) -> str:
        return (self.pre_filter or "format=rgba").replace(_OFFSET_TOKEN, f"{_snap(self.offset - shift, fps):.6f}")

    def enable(self, shift: float, fps: int) -> str:
        """Exact output-frame range this layer is composited on, relative to
        a render starting at ``shift`` (``n`` = overlay's main frame index)."""
        first = _first_frame(self.offset - shift, fps)
        count = self.frames or _frame_span(self.offset, self.end, fps)
        return f"between(n,{first},{first + count - 1})"


_GRID_EPS = 1e-6


def _first_frame(t: float, fps: int) -> int:
    """Index of the first output frame at or after time ``t``."""
    return math.ceil(t * fps - _GRID_EPS)


def _frame_span(start: float, end: float, fps: int) -> int:
    """How many output frames a layer covering [start, end) is visible on:
    frame k shows it iff start <= k/fps < end. Consecutive layers (one ends
    exactly where the next starts) therefore hand over with no gap frame and
    no overlap frame — the reference style's instant hard cut."""
    return max(1, _first_frame(end, fps) - _first_frame(start, fps))


def _snap(t: float, fps: int) -> float:
    """Move a layer start onto the output frame grid — the first frame at or
    after it — so a layer starts on the same frame whether it is rendered in
    one pass or time-shifted into a segment (segment starts are frame-
    aligned, so shifting never changes which frame that is)."""
    return _first_frame(t, fps) / fps if fps else t


def _hold_layer(png_path: Path, start: float, hold_duration: float, fps: int) -> _Layer:
    """A static PNG held on screen from ``start`` for ``hold_duration``.

    Demuxer-paced (``-loop 1``), so frames are produced only as the render
    reaches them. (Generating them with the in-graph ``loop`` filter instead
    was measured to make ffmpeg buffer every future hold frame: a 3-minute
    single-pass render went from ~3 minutes to ~110.) ``-framerate {fps}``
    puts the frames on the output frame grid — ffmpeg's default 25 fps image
    rate quantized every hold's start/end to a 0.04 s grid, up to half a
    frame off. ``-t`` covers one frame more than needed so the last visible
    frame is never the stream's final one; the overlay's enable range (see
    _Layer.enable) is what decides exactly which frames show it."""
    frames = _frame_span(start, start + max(_MIN_HOLD_S, hold_duration), fps)
    return _Layer(
        [*_STILL_DECODE, "-loop", "1", "-framerate", str(fps), "-t", f"{(frames + 1) / fps:.6f}", "-i", str(png_path)],
        offset=start, duration=frames / fps, frames=frames,
    )


def _write_png_sequence(seq_dir: Path, frames) -> None:
    seq_dir.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(frames):
        frame.save(seq_dir / f"{i:05d}.png")


def _node_reveal_layers(
    node: SceneNode,
    *,
    layout: SceneGraphLayout,
    style: StylePreset,
    media_image,
    hollow: bool,
    fps: int,
    work_dir: Path,
) -> List[_Layer]:
    """The reveal-in + settled-hold input layers for one node's OWN active
    window (from scene_graph.layout — a chapter's members are only ever on
    screen for their own slice of the segment, not the whole thing). Nothing
    is scheduled past the window's end — the node is simply gone (a hard
    cut), matching the reference style rather than fading out."""

    rect = layout.node_rects.get(node.id)
    window = layout.active_windows.get(node.id)
    if rect is None or window is None:
        return []
    appear_at, window_end = window
    total = window_end - appear_at
    if total <= 0:
        return []

    canvas_size = (layout.canvas_width, layout.canvas_height)
    reveal_duration = min(_clamp(NODE_REVEAL_DURATION_S, *_NODE_REVEAL_RANGE), total)
    hold_duration = max(0.0, total - reveal_duration)
    # Already-solved once at layout time (see compute_layout's narration-
    # caption pass / routing.solve_caption_position) — (0, 0) when there was
    # no conflict, reproducing today's exact position.
    caption_offset = layout.caption_positions.get(node.id, (0.0, 0.0))

    node_dir = work_dir / f"node_{node.id}"
    reveal_count = max(1, round(reveal_duration * fps))
    reveal_frames = [
        render_node_reveal_frame(
            node, rect, media_image, style, canvas_size=canvas_size, background="",
            progress=min(1.0, (i + 1) / reveal_count), hollow=hollow, caption_offset=caption_offset,
        )
        for i in range(reveal_count)
    ]
    _write_png_sequence(node_dir / "reveal", reveal_frames)
    layers = [
        _Layer([*_STILL_DECODE, "-framerate", str(fps), "-i", str(node_dir / "reveal" / "%05d.png")],
               offset=appear_at, duration=reveal_count / fps, frames=reveal_count,
               pre_filter=_REVEAL_PRE)
    ]

    if hold_duration > 0:
        hold_start = appear_at + reveal_duration
        kb_params = None if hollow else layout.node_ken_burns.get(node.id)
        if node.type in _KEN_BURNS_NODE_TYPES and kb_params and media_image is not None:
            w, h = max(1, round(rect.width)), max(1, round(rect.height))
            media_path = node_dir / "kb_media.png"
            render_node_media_only_frame(node, rect, media_image, style).save(media_path)
            layers.append(
                _Layer(
                    [*_STILL_DECODE, "-loop", "1", "-framerate", "1", "-i", str(media_path)],
                    offset=hold_start, duration=_frame_span(hold_start, hold_start + hold_duration, fps) / fps,
                    frames=_frame_span(hold_start, hold_start + hold_duration, fps),
                    overlay_xy=(int(rect.x), int(rect.y)),
                    pre_filter=_kenburns_pre_filter(
                        width=w, height=h, hold_start=hold_start, hold_duration=hold_duration, fps=fps,
                        zoom_end=float(kb_params["zoom_end"]), pan_x=float(kb_params["pan_x"]),
                        pan_y=float(kb_params["pan_y"]), offset_expr=_OFFSET_TOKEN,
                    ),
                )
            )
            decoration_path = node_dir / "kb_decoration.png"
            render_node_decoration_frame(
                node, rect, style, canvas_size=canvas_size, caption_offset=caption_offset,
            ).save(decoration_path)
            layers.append(_hold_layer(decoration_path, hold_start, hold_duration, fps))
        else:
            settled_path = node_dir / "settled.png"
            reveal_frames[-1].save(settled_path)
            layers.append(_hold_layer(settled_path, hold_start, hold_duration, fps))
    return layers


def _title_reveal_layers(
    text: str, start: float, end: float, *, layout: SceneGraphLayout, fps: int, work_dir: Path, index: int,
) -> List[_Layer]:
    """Same fade-in-then-hold-then-hard-cut treatment as a node, for one
    persistent chapter/subject title (bold centered text, no card)."""

    total = end - start
    if total <= 0 or not text:
        return []

    canvas_size = (layout.canvas_width, layout.canvas_height)
    reveal_duration = min(_clamp(NODE_REVEAL_DURATION_S, *_NODE_REVEAL_RANGE), total)
    hold_duration = max(0.0, total - reveal_duration)
    # Pushed down below Exp Solar's checklist strip when one is reserved
    # (layout.checklist_band_px is 0 for Overscaled and for every
    # non-checklist Exp Solar segment, so this is MARGIN_PX unchanged then).
    top_margin = MARGIN_PX + layout.checklist_band_px

    title_dir = work_dir / f"title_{index}"
    reveal_count = max(1, round(reveal_duration * fps))
    reveal_frames = [
        render_title_reveal_frame(
            text, canvas_size=canvas_size, top_margin=top_margin, progress=min(1.0, (i + 1) / reveal_count),
        )
        for i in range(reveal_count)
    ]
    _write_png_sequence(title_dir / "reveal", reveal_frames)
    layers = [
        _Layer([*_STILL_DECODE, "-framerate", str(fps), "-i", str(title_dir / "reveal" / "%05d.png")],
               offset=start, duration=reveal_count / fps, frames=reveal_count,
               pre_filter=_REVEAL_PRE)
    ]
    if hold_duration > 0:
        settled_path = title_dir / "settled.png"
        reveal_frames[-1].save(settled_path)
        layers.append(_hold_layer(settled_path, start + reveal_duration, hold_duration, fps))
    return layers


def _checklist_strip_layers(
    scene_graph: SceneGraph, *, layout: SceneGraphLayout, fps: int, work_dir: Path,
) -> List[_Layer]:
    """Exp Solar's persistent checklist header strip: one STATIC image per
    state-segment (layout.checklist_windows is already in chronological
    order, one entry per item), held via -loop/-t for that item's own
    (becomes_current_at, becomes_completed_at) window — no reveal/fade, per
    the reference's instant state-change behavior (same convention
    _title_reveal_layers/_node_reveal_layers already use for a hard cut).
    Spans the segment from the FIRST item's own start through the LAST
    item's own end, i.e. the whole time any item is "current" — before the
    first item starts, nothing is drawn (nothing to show grey-only that
    the reveal itself doesn't already show at index -1... in practice the
    first item's own window starts at its appear_at, matching every other
    node's own reveal timing). Empty (returns []) whenever there are no
    checklist items — Overscaled and non-checklist Exp Solar segments are
    unaffected."""

    windows = layout.checklist_windows
    if not windows:
        return []

    labels = [label for label, _, _ in windows]
    canvas_size = (layout.canvas_width, layout.canvas_height)
    layers: List[_Layer] = []
    strip_dir = work_dir / "checklist_strip"
    for i, (_, start, end) in enumerate(windows):
        total = end - start
        if total <= 0:
            continue
        frame = render_checklist_strip_frame(
            labels, i, canvas_size=canvas_size, band_height=layout.checklist_band_px, margin_px=MARGIN_PX,
        )
        frame_path = strip_dir / f"state_{i:02d}.png"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame.save(frame_path)
        layers.append(_hold_layer(frame_path, start, total, fps))
    return layers


def _node_video_layer(
    node: SceneNode,
    *,
    layout: SceneGraphLayout,
    resolved_media: Dict[str, str],
) -> Optional[_Layer]:
    """The live decoded-video input for a video_loop card, scaled/padded to
    exactly fill its rect (the hollow decoration layer draws the border on
    top of it afterwards) — real playback, never a frozen thumbnail. Clipped
    to the node's own active window (chapter turn), not the whole segment."""

    rect = layout.node_rects.get(node.id)
    window = layout.active_windows.get(node.id)
    media_path = resolved_media.get(node.id)
    if rect is None or window is None or not _is_video_file(media_path) or node.type == "anchor":
        return None

    appear_at, window_end = window
    available = window_end - appear_at
    if available <= 0:
        return None

    real_duration = probe_media_duration(media_path, log_failures=False)
    play_duration = min(available, real_duration) if real_duration else available
    if play_duration <= 0:
        return None
    # A map clip is one continuous camera move: when the scene outlasts it,
    # hold its last frame for the rest of the window (a card that goes blank,
    # or a zoom that restarts, would look broken).
    hold_pad = 0.0
    if is_map_node(node) and real_duration and available > real_duration + 0.05 and is_map_clip(media_path):
        hold_pad = available - real_duration

    w, h = max(2, round(rect.width)), max(2, round(rect.height))
    fade_in_d = min(0.3, play_duration)
    # The fade is timed relative to the clip's OWN first frame: with the
    # input shifted by -itsoffset, "st=0" on global timestamps meant the fade
    # had always already finished (a no-op), and it would have fired only
    # when a render segment happened to start at this card.
    filt = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,"
        f"setpts=PTS-STARTPTS,fade=t=in:st=0:d={fade_in_d:.3f}:alpha=1,"
        + (f"tpad=stop_mode=clone:stop_duration={hold_pad:.4f}," if hold_pad > 0 else "")
        + f"setpts=PTS+{_OFFSET_TOKEN}/TB,format=rgba"
    )
    return _Layer(
        ["-t", f"{play_duration:.4f}", "-i", str(media_path)],
        offset=appear_at, duration=play_duration + hold_pad,
        overlay_xy=(int(rect.x), int(rect.y)),
        pre_filter=filt,
    )


def _edge_reveal_layers(
    edge: SceneEdge,
    *,
    layout: SceneGraphLayout,
    style: StylePreset,
    fps: int,
    work_dir: Path,
) -> List[_Layer]:
    """An arrow is only ever drawn while BOTH its endpoints are on screen —
    scene_graph.layout already intersected the two nodes' windows into
    ``layout.edge_windows``, so an arrow hard-cuts away the moment either
    endpoint's own chapter turn ends, per spec: 'arrows appear only when
    their connected elements exist'."""

    from_rect = layout.node_rects.get(edge.from_node)
    to_rect = layout.node_rects.get(edge.to_node)
    window = layout.edge_windows.get(edge.id)
    if from_rect is None or to_rect is None or window is None:
        return []

    draw_at, window_end = window
    total = window_end - draw_at
    if total <= 0:
        return []

    canvas_size = (layout.canvas_width, layout.canvas_height)
    reveal_duration = min(_clamp(float(edge.duration) or EDGE_REVEAL_DURATION_S, *_EDGE_REVEAL_RANGE), total)
    hold_duration = max(0.0, total - reveal_duration)

    # Cached, already-solved (once, at layout time — never here) obstacle-
    # aware route + label position, see scene_graph.routing.solve_edge_route
    # / solve_label_position. Absent only for an edge that couldn't be
    # solved (e.g. a missing rect) — render_edge_reveal_frame then falls
    # back to a direct line, same as before this existed.
    route_points = layout.edge_routes.get(edge.id)
    label_pos = layout.edge_label_positions.get(edge.id)

    edge_dir = work_dir / f"edge_{edge.id}"
    reveal_count = max(1, round(reveal_duration * fps))
    reveal_frames = [
        render_edge_reveal_frame(
            edge, from_rect, to_rect, style, canvas_size=canvas_size,
            progress=min(1.0, (i + 1) / reveal_count),
            route_points=route_points, label_pos=label_pos,
        )
        for i in range(reveal_count)
    ]
    _write_png_sequence(edge_dir / "reveal", reveal_frames)
    layers = [
        _Layer([*_STILL_DECODE, "-framerate", str(fps), "-i", str(edge_dir / "reveal" / "%05d.png")],
               offset=draw_at, duration=reveal_count / fps, frames=reveal_count,
               pre_filter=_REVEAL_PRE)
    ]

    if hold_duration > 0:
        settled_path = edge_dir / "settled.png"
        reveal_frames[-1].save(settled_path)
        layers.append(_hold_layer(settled_path, draw_at + reveal_duration, hold_duration, fps))
    return layers


def render_overscaled_segment(
    scene_graph: SceneGraph,
    layout: SceneGraphLayout,
    style: StylePreset,
    *,
    out_path: Path,
    resolved_media: Optional[Dict[str, str]] = None,
    resolution: str = "1920x1080",
    fps: int = 30,
    work_dir: Optional[Path] = None,
    on_progress: Optional[Callable[[str, float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """Render the full segment (fixed canvas, gated reveals, live video
    cards) to ONE MP4. No camera, no legs. Rendered in one ffmpeg pass when
    the layer graph fits the per-process budget, otherwise in bounded time
    segments joined by stream copy (see _plan_segments)."""

    from .composition import load_media_image  # local import: avoids a cycle at module load

    out_width, out_height = (int(v) for v in resolution.lower().split("x"))
    out_path = Path(out_path)
    work_dir = Path(work_dir) if work_dir else out_path.parent / f"_{out_path.stem}_layers"
    work_dir.mkdir(parents=True, exist_ok=True)
    resolved_media = resolved_media or {}
    # Rendered as a whole number of frames: a fractional tail (e.g. 193.75 s =
    # 5812.5 frames) made the LAST frame a half-frame emitted during ffmpeg's
    # end-of-stream flush, with every overlay missing from it (measured).
    # The output frame count is unchanged (ffmpeg already rounded it up).
    duration = _first_frame(float(scene_graph.duration) or 1.0, fps) / fps
    bg_color = (style.canvas or {}).get("background") or "#ffffff"

    def _stop_if_cancelled() -> None:
        if cancel_check is not None and cancel_check():
            raise RenderCancelled("render cancelled")

    try:
        layers = _collect_layers(
            scene_graph, layout, style, resolved_media=resolved_media, fps=fps, work_dir=work_dir,
            load_media_image=load_media_image, on_progress=on_progress, cancel_check=_stop_if_cancelled,
        )
        segments = _plan_segments(layers, duration=duration, fps=fps)

        if on_progress:
            on_progress("Encoding final video…", 0.55)

        if len(segments) == 1:
            _stop_if_cancelled()
            _render_segment_clip(
                layers, 0.0, duration, out_path=out_path, bg_color=bg_color, width=out_width,
                height=out_height, fps=fps, total_duration=duration, on_progress=on_progress,
                cancel_check=_stop_if_cancelled,
            )
        else:
            seg_dir = work_dir / "_segments"
            seg_dir.mkdir(parents=True, exist_ok=True)
            seg_paths = _render_segments_bounded(
                layers, segments, seg_dir=seg_dir, bg_color=bg_color, width=out_width, height=out_height,
                fps=fps, total_duration=duration, on_progress=on_progress, cancel_check=_stop_if_cancelled,
            )
            _stop_if_cancelled()
            _concat_segments(seg_paths, out_path, work_dir=seg_dir, duration=duration)
    finally:
        # Always — success, failure, or an exception: a failed long-form render
        # previously left hundreds of MB of layer PNGs behind on every attempt.
        shutil.rmtree(work_dir, ignore_errors=True)

    if on_progress:
        on_progress("Encoding final video… done", 0.90)
    return out_path


def _collect_layers(
    scene_graph: SceneGraph,
    layout: SceneGraphLayout,
    style: StylePreset,
    *,
    resolved_media: Dict[str, str],
    fps: int,
    work_dir: Path,
    load_media_image,
    on_progress: Optional[Callable[[str, float], None]],
    cancel_check: Optional[Callable[[], None]] = None,
) -> List[_Layer]:
    """Every overlay layer of the segment, in compositing order: titles
    first, then nodes in narration order, then edges, then Exp Solar's
    checklist strip (always topmost)."""

    layers: List[_Layer] = []
    if on_progress:
        on_progress("Preparing composition layers…", 0.45)

    for i, (text, start, end) in enumerate(layout.title_windows):
        layers.extend(_title_reveal_layers(text, start, end, layout=layout, fps=fps, work_dir=work_dir, index=i))

    media_tmp = work_dir / "_media_tmp"
    for node in scene_graph.nodes:
        if cancel_check is not None:
            cancel_check()  # raises RenderCancelled — layer prep is minutes on long projects
        media_path = resolved_media.get(node.id)
        is_live_video = _is_video_file(media_path) and node.type != "anchor"

        video_layer = _node_video_layer(
            node, layout=layout, resolved_media=resolved_media,
        ) if is_live_video else None
        if video_layer is not None:
            layers.append(video_layer)

        if is_map_node(node):
            continue  # full-screen map: just the clip — no card, border or caption layers
        media_image = None if is_live_video else load_media_image(media_path, media_tmp)
        layers.extend(_node_reveal_layers(
            node, layout=layout, style=style, media_image=media_image, hollow=is_live_video,
            fps=fps, work_dir=work_dir,
        ))

    for edge in scene_graph.edges:
        layers.extend(_edge_reveal_layers(edge, layout=layout, style=style, fps=fps, work_dir=work_dir))

    # Exp Solar's persistent checklist strip, added LAST so it is always
    # the topmost layer — "reserve its own screen area so it never
    # overlaps the main visual/captions" per spec; empty (a no-op) for
    # Overscaled and any non-checklist Exp Solar segment.
    layers.extend(_checklist_strip_layers(scene_graph, layout=layout, fps=fps, work_dir=work_dir))
    return layers


# --- Segmented rendering ---------------------------------------------------
# One ffmpeg process per render used to take EVERY layer of the whole video as
# its own input. Measured on macOS 1080p30: a 3-minute project = 144 inputs,
# ~3,200 ffmpeg threads and 1.7 GB RSS; a 10-minute one (484 inputs) failed
# outright with "Error while opening decoder: Resource temporarily
# unavailable" (the 4,096 threads-per-process limit). The same argv (35 KB at
# 3 minutes, 478 KB at 40) also exceeds Windows' 32,767-character command-line
# limit. So a graph over these budgets is cut into time segments, each
# rendered by its own bounded ffmpeg process and joined losslessly (stream
# copy). A graph within budget still renders in ONE pass, unchanged.
_MAX_SEGMENT_INPUTS = 96
_MAX_SEGMENT_ARGV_CHARS = 28000  # Windows CreateProcess limit is 32,767
_TIME_EPS = 1e-6
_LINGER_MARGIN_S = 0.1  # > one frame at ffmpeg's default 25 fps image-loop rate


def _layer_cost(layer: _Layer) -> int:
    """Approximate argv characters this layer contributes (inputs + filters)."""
    return sum(len(a) + 1 for a in layer.argv()) + len(layer.filter()) + 64


def _layers_in(layers: List[_Layer], seg_start: float, seg_end: float) -> List[_Layer]:
    # A finished layer stays composited slightly PAST its nominal end: a looped
    # PNG input runs at ffmpeg's default 25 fps, so its last frame is shown
    # for up to 1/25 s more (measured: dropping it produced one wrong frame at
    # a segment boundary). Including an already-ended layer is always safe —
    # ffmpeg composites it at the same relative time exactly as the single
    # pass would, or not at all — so the start edge gets a generous margin.
    return [
        layer for layer in layers
        if layer.offset < seg_end - _TIME_EPS and layer.end > seg_start - _LINGER_MARGIN_S
    ]


def _plan_segments(
    layers: List[_Layer],
    *,
    duration: float,
    fps: int,
    max_inputs: Optional[int] = None,
    max_argv_chars: Optional[int] = None,
) -> List[Tuple[float, float]]:
    """Frame-aligned (start, end) segments whose layer sets fit the budgets.

    Cuts are only placed where some layer STARTS (a reveal/chapter turn), so
    most layers are never split; a layer that does span a cut is simply
    included in both segments with its offset shifted, which ffmpeg
    composites identically. Returns [(0, duration)] when everything fits."""

    max_inputs = _MAX_SEGMENT_INPUTS if max_inputs is None else max_inputs
    max_argv_chars = _MAX_SEGMENT_ARGV_CHARS if max_argv_chars is None else max_argv_chars

    def fits(start: float, end: float) -> bool:
        members = _layers_in(layers, start, end)
        return len(members) <= max_inputs and sum(_layer_cost(m) for m in members) <= max_argv_chars

    if fits(0.0, duration):
        return [(0.0, duration)]

    candidates = sorted({
        round(layer.offset * fps) / fps for layer in layers
        if _TIME_EPS < layer.offset < duration - _TIME_EPS
    })
    segments: List[Tuple[float, float]] = []
    seg_start = 0.0
    last_ok: Optional[float] = None
    for cut in candidates:
        if cut <= seg_start + _TIME_EPS:
            continue
        if fits(seg_start, cut):
            last_ok = cut
            continue
        if last_ok is not None:
            # Close at the last cut that still fit, then re-test this cut.
            segments.append((seg_start, last_ok))
            seg_start, last_ok = last_ok, None
            if fits(seg_start, cut):
                last_ok = cut
                continue
        # Even the smallest possible step overflows (too many layers at once):
        # cut here anyway — no finer cut point exists.
        segments.append((seg_start, cut))
        seg_start, last_ok = cut, None
    if last_ok is not None and not fits(seg_start, duration):
        segments.append((seg_start, last_ok))
        seg_start = last_ok
    segments.append((seg_start, duration))
    return segments


def _render_segment_clip(
    layers: List[_Layer],
    seg_start: float,
    seg_end: float,
    *,
    out_path: Path,
    bg_color: str,
    width: int,
    height: int,
    fps: int,
    total_duration: float,
    on_progress: Optional[Callable[[str, float], None]],
    label: str = "",
    cancel_check: Optional[Callable[[], None]] = None,
) -> None:
    seg_duration = max(1.0 / fps, seg_end - seg_start)
    inputs: List[str] = ["-y", "-f", "lavfi", "-i", f"color=c={bg_color}:s={width}x{height}:r={fps}:d={seg_duration:.6f}"]
    filters: List[str] = [f"[0:v]format=rgba,fps={fps}[bg0]"]
    current = "bg0"
    for input_idx, layer in enumerate(_layers_in(layers, seg_start, seg_end), start=1):
        inputs.extend(layer.argv(seg_start, fps))
        ov, nxt = f"ov{input_idx}", f"c{input_idx}"
        x, y = layer.overlay_xy
        filters.append(f"[{input_idx}:v]{layer.filter(seg_start, fps)}[{ov}]")
        # eof_action=pass (NOT ffmpeg's default "repeat"): once this finite
        # layer's own local duration ends, revert to passing the
        # composition-so-far through unchanged. The default would otherwise
        # freeze this layer's LAST frame and keep compositing it for the
        # rest of the video — invisible where a later, opaque, identically-
        # bounded card happens to cover it, but a real bug wherever it
        # doesn't (e.g. a caption drawn below the card rect, never covered
        # by the next unrelated chapter's own — caption-less — card).
        # enable=: the layer is drawn on EXACTLY its own output frames (frame k
        # shows it iff start <= k/fps < end) — deterministic regardless of how
        # ffmpeg timestamps/ends each input, and identical in any segment.
        filters.append(
            f"[{current}][{ov}]overlay={x}:{y}:eof_action=pass:enable='{layer.enable(seg_start, fps)}'[{nxt}]"
        )
        current = nxt
    filters.append(f"[{current}]scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p,fps={fps}[outv]")

    def _ffmpeg_progress(info: dict) -> None:
        if not on_progress:
            return
        time_str = info.get("time")
        if not time_str:
            return
        try:
            h, m, s = time_str.split(":")
            elapsed = seg_start + int(h) * 3600 + int(m) * 60 + float(s)
        except ValueError:
            return
        fraction = 0.55 + 0.35 * max(0.0, min(1.0, elapsed / total_duration))
        on_progress(f"Encoding final video… ({elapsed:.0f}s/{total_duration:.0f}s)", fraction)

    cmd = ["ffmpeg", *inputs, "-filter_complex", ";".join(filters), "-map", "[outv]",
           "-t", f"{seg_duration:.6f}",
           *encode_argv(quality="documentary"), str(out_path)]
    result = run_ffmpeg(
        cmd, owner="overscaled_render", media_duration_s=seg_duration, label="overscaled_render",
        on_progress=_ffmpeg_progress,
    )
    if cancel_check is not None:
        # Always, whatever the exit code: a SIGTERM'd ffmpeg exits 0 ("Exiting
        # normally, received signal 15") and can leave a PARTIAL file behind.
        cancel_check()
    if _ffmpeg_failed(result) or not out_path.is_file():
        where = f" ({label}, {seg_start:.1f}s-{seg_end:.1f}s)" if label else ""
        raise RuntimeError(f"Overscaled render failed{where} (rc={result.returncode}): {result.stderr[-2000:]}")


def _segment_workers(segment_count: int) -> int:
    """How many segments to encode at once — the EXISTING resource governor's
    LONG-FORM ffmpeg budget (hardware/governor.py: one encoder at a time,
    "sustained throughput / stability for ~40 min docs"), overridable via
    VIDEOGEN_FFMPEG_WORKERS on machines with headroom; never more than there
    are segments. Measured on a 16 GB Apple Silicon Mac under normal desktop
    memory pressure, 10-minute 1080p project: 1 worker 747 s / 1.4 GB peak,
    2 workers 821 s / 2.0 GB — concurrent encoders competed for memory."""
    try:
        from hardware.governor import get_governor

        workers = int(get_governor().recommend_ffmpeg_workers(long_form=True))
    except Exception:
        workers = 1
    return max(1, min(workers, segment_count))


def _render_segments_bounded(
    layers: List[_Layer],
    segments: List[Tuple[float, float]],
    *,
    seg_dir: Path,
    bg_color: str,
    width: int,
    height: int,
    fps: int,
    total_duration: float,
    on_progress: Optional[Callable[[str, float], None]],
    cancel_check: Callable[[], None],
) -> List[Path]:
    """Encode every segment with at most _segment_workers() ffmpeg processes
    at once. Returns the segment files in timeline order. The first failure
    or a Stop request prevents any further segment from starting (running
    ones are stopped by the caller's process-registry kill on Stop)."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    lock = threading.Lock()
    done_seconds = {"total": 0.0}
    live: Dict[int, float] = {}
    failed = threading.Event()

    def progress_for(index: int, seg_len: float):
        def report(message: str, fraction: float) -> None:
            if on_progress is None:
                return
            # Per-segment ffmpeg time -> overall seconds encoded, summed over
            # every segment, so parallel segments never move the bar backward.
            try:
                seconds = float(message.split("(")[1].split("s/")[0]) - segments[index][0]
            except (IndexError, ValueError):
                return
            with lock:
                live[index] = max(0.0, min(seg_len, seconds))
                encoded = done_seconds["total"] + sum(live.values())
            on_progress(
                f"Encoding final video… ({encoded:.0f}s/{total_duration:.0f}s)",
                0.55 + 0.35 * max(0.0, min(1.0, encoded / total_duration)),
            )
        return report

    def render(index: int) -> Path:
        if failed.is_set():
            raise RuntimeError("an earlier segment failed")
        cancel_check()
        seg_start, seg_end = segments[index]
        seg_path = seg_dir / f"seg_{index:04d}.mp4"
        try:
            _render_segment_clip(
                layers, seg_start, seg_end, out_path=seg_path, bg_color=bg_color, width=width,
                height=height, fps=fps, total_duration=total_duration,
                on_progress=progress_for(index, seg_end - seg_start),
                label=f"segment {index + 1}/{len(segments)}", cancel_check=cancel_check,
            )
        except BaseException:
            failed.set()
            raise
        with lock:
            live.pop(index, None)
            done_seconds["total"] += seg_end - seg_start
        return seg_path

    workers = _segment_workers(len(segments))
    if workers == 1:
        return [render(i) for i in range(len(segments))]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="overscaled_seg") as pool:
        futures = [pool.submit(render, i) for i in range(len(segments))]
        errors = [f.exception() for f in futures]  # waits for every segment
    cancelled = [e for e in errors if isinstance(e, RenderCancelled)]
    if cancelled:
        raise cancelled[0]
    real = [e for e in errors if e is not None and str(e) != "an earlier segment failed"]
    if real:
        raise real[0]
    return [f.result() for f in futures]


def _ffmpeg_failed(result) -> bool:
    """Non-zero exit, OR killed by run_ffmpeg's timeout/stall watchdog or a
    signal — ffmpeg exits 0 after SIGTERM, so rc alone would accept a
    truncated file as a finished render."""
    return (
        result.returncode != 0
        or bool(getattr(result, "timed_out", False))
        or bool(getattr(result, "stalled", False))
        or "received signal" in str(getattr(result, "stderr", "") or "")
    )


def _concat_segments(seg_paths: List[Path], out_path: Path, *, work_dir: Path, duration: float) -> None:
    """Join same-codec segment clips without re-encoding (concat demuxer)."""
    from video_generator import write_ffmpeg_concat_list  # Windows-safe, quote-escaped paths

    list_path = write_ffmpeg_concat_list(seg_paths, work_dir / "segments.txt")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)]
    result = run_ffmpeg(cmd, owner="overscaled_render", media_duration_s=duration, label="overscaled_concat")
    if _ffmpeg_failed(result) or not out_path.is_file():
        raise RuntimeError(f"Overscaled segment join failed (rc={result.returncode}): {result.stderr[-2000:]}")
