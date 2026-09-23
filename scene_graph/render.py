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
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from media_duration import probe_media_duration
from providers.ffmpeg_runner import run_ffmpeg

from .composition import (
    VIDEO_SUFFIXES,
    render_edge_reveal_frame,
    render_node_decoration_frame,
    render_node_media_only_frame,
    render_node_reveal_frame,
    render_title_reveal_frame,
)
from .layout import MARGIN_PX, SceneGraphLayout
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
    zoom_end: float, pan_x: float, pan_y: float,
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
    d_frames = max(1, round(hold_duration * fps))
    rate = (zoom_end - 1.0) / max(1, d_frames - 1)
    dx_px = pan_x * width
    dy_px = pan_y * height
    zoom_expr = f"min(zoom+{rate:.8f},{zoom_end:.6f})"
    x_expr = f"max(0,min(iw-iw/zoom,(iw-iw/zoom)/2+{dx_px:.3f}*(on/{d_frames})))"
    y_expr = f"max(0,min(ih-ih/zoom,(ih-ih/zoom)/2+{dy_px:.3f}*(on/{d_frames})))"
    return (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':s={width}x{height}:d={d_frames}:fps={fps},"
        f"trim=end_frame={d_frames},setpts=PTS-STARTPTS+{hold_start:.6f}/TB,format=rgba"
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value if value > 0 else lo))


def _is_video_file(path: Optional[str]) -> bool:
    if not path:
        return False
    return Path(path).suffix.lower() in VIDEO_SUFFIXES


@dataclasses.dataclass
class _Layer:
    """One ffmpeg input + the overlay filter step that composites it."""

    input_args: List[str]
    overlay_xy: Tuple[int, int] = (0, 0)
    pre_filter: str = ""  # optional per-input filter (e.g. scale/pad/fade) before the overlay


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

    node_dir = work_dir / f"node_{node.id}"
    reveal_count = max(1, round(reveal_duration * fps))
    reveal_frames = [
        render_node_reveal_frame(
            node, rect, media_image, style, canvas_size=canvas_size, background="",
            progress=min(1.0, (i + 1) / reveal_count), hollow=hollow,
        )
        for i in range(reveal_count)
    ]
    _write_png_sequence(node_dir / "reveal", reveal_frames)
    layers = [
        _Layer(["-itsoffset", f"{appear_at:.4f}", "-framerate", str(fps),
                "-i", str(node_dir / "reveal" / "%05d.png")])
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
                    ["-itsoffset", f"{hold_start:.4f}", "-loop", "1", "-framerate", "1", "-i", str(media_path)],
                    overlay_xy=(int(rect.x), int(rect.y)),
                    pre_filter=_kenburns_pre_filter(
                        width=w, height=h, hold_start=hold_start, hold_duration=hold_duration, fps=fps,
                        zoom_end=float(kb_params["zoom_end"]), pan_x=float(kb_params["pan_x"]),
                        pan_y=float(kb_params["pan_y"]),
                    ),
                )
            )
            decoration_path = node_dir / "kb_decoration.png"
            render_node_decoration_frame(node, rect, style, canvas_size=canvas_size).save(decoration_path)
            layers.append(
                _Layer(["-itsoffset", f"{hold_start:.4f}", "-loop", "1", "-t",
                        f"{max(_MIN_HOLD_S, hold_duration):.4f}", "-i", str(decoration_path)])
            )
        else:
            settled_path = node_dir / "settled.png"
            reveal_frames[-1].save(settled_path)
            layers.append(
                _Layer(["-itsoffset", f"{hold_start:.4f}", "-loop", "1", "-t",
                        f"{max(_MIN_HOLD_S, hold_duration):.4f}", "-i", str(settled_path)])
            )
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

    title_dir = work_dir / f"title_{index}"
    reveal_count = max(1, round(reveal_duration * fps))
    reveal_frames = [
        render_title_reveal_frame(
            text, canvas_size=canvas_size, top_margin=MARGIN_PX, progress=min(1.0, (i + 1) / reveal_count),
        )
        for i in range(reveal_count)
    ]
    _write_png_sequence(title_dir / "reveal", reveal_frames)
    layers = [
        _Layer(["-itsoffset", f"{start:.4f}", "-framerate", str(fps),
                "-i", str(title_dir / "reveal" / "%05d.png")])
    ]
    if hold_duration > 0:
        settled_path = title_dir / "settled.png"
        reveal_frames[-1].save(settled_path)
        layers.append(
            _Layer(["-itsoffset", f"{start + reveal_duration:.4f}", "-loop", "1", "-t",
                    f"{max(_MIN_HOLD_S, hold_duration):.4f}", "-i", str(settled_path)])
        )
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

    w, h = max(2, round(rect.width)), max(2, round(rect.height))
    fade_in_d = min(0.3, play_duration)
    filt = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,"
        f"fade=t=in:st=0:d={fade_in_d:.3f}:alpha=1,format=rgba"
    )
    return _Layer(
        ["-itsoffset", f"{appear_at:.4f}", "-t", f"{play_duration:.4f}", "-i", str(media_path)],
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
        _Layer(["-itsoffset", f"{draw_at:.4f}", "-framerate", str(fps),
                "-i", str(edge_dir / "reveal" / "%05d.png")])
    ]

    if hold_duration > 0:
        settled_path = edge_dir / "settled.png"
        reveal_frames[-1].save(settled_path)
        layers.append(
            _Layer(["-itsoffset", f"{draw_at + reveal_duration:.4f}", "-loop", "1", "-t",
                    f"{max(_MIN_HOLD_S, hold_duration):.4f}", "-i", str(settled_path)])
        )
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
) -> Path:
    """Render the full segment (fixed canvas, gated reveals, live video
    cards) to ONE MP4 via ONE ffmpeg encode. No camera, no legs, no concat.
    """

    from .composition import load_media_image  # local import: avoids a cycle at module load

    out_width, out_height = (int(v) for v in resolution.lower().split("x"))
    out_path = Path(out_path)
    work_dir = Path(work_dir) if work_dir else out_path.parent / f"_{out_path.stem}_layers"
    work_dir.mkdir(parents=True, exist_ok=True)
    resolved_media = resolved_media or {}
    duration = float(scene_graph.duration) or 1.0
    bg_color = (style.canvas or {}).get("background") or "#ffffff"

    inputs: List[str] = ["-y", "-f", "lavfi", "-i", f"color=c={bg_color}:s={out_width}x{out_height}:d={duration:.4f}"]
    filters: List[str] = [f"[0:v]format=rgba,fps={fps}[bg0]"]
    label = "bg0"
    input_idx = 1

    def _chain_overlay(layer: _Layer) -> None:
        nonlocal label, input_idx
        inputs.extend(layer.input_args)
        ov = f"ov{input_idx}"
        nxt = f"c{input_idx}"
        x, y = layer.overlay_xy
        pre = layer.pre_filter or "format=rgba"
        filters.append(f"[{input_idx}:v]{pre}[{ov}]")
        # eof_action=pass (NOT ffmpeg's default "repeat"): once this finite
        # layer's own local duration ends, revert to passing the
        # composition-so-far through unchanged. The default would otherwise
        # freeze this layer's LAST frame and keep compositing it for the
        # rest of the video — invisible where a later, opaque, identically-
        # bounded card happens to cover it, but a real bug wherever it
        # doesn't (e.g. a caption drawn below the card rect, never covered
        # by the next unrelated chapter's own — caption-less — card).
        filters.append(f"[{label}][{ov}]overlay={x}:{y}:eof_action=pass[{nxt}]")
        label = nxt
        input_idx += 1

    if on_progress:
        on_progress("Preparing composition layers…", 0.45)

    for i, (text, start, end) in enumerate(layout.title_windows):
        for title_layer in _title_reveal_layers(text, start, end, layout=layout, fps=fps, work_dir=work_dir, index=i):
            _chain_overlay(title_layer)

    media_tmp = work_dir / "_media_tmp"
    for node in scene_graph.nodes:
        media_path = resolved_media.get(node.id)
        is_live_video = _is_video_file(media_path) and node.type != "anchor"

        video_layer = _node_video_layer(
            node, layout=layout, resolved_media=resolved_media,
        ) if is_live_video else None
        if video_layer is not None:
            _chain_overlay(video_layer)

        media_image = None if is_live_video else load_media_image(media_path, media_tmp)
        for reveal_layer in _node_reveal_layers(
            node, layout=layout, style=style, media_image=media_image, hollow=is_live_video,
            fps=fps, work_dir=work_dir,
        ):
            _chain_overlay(reveal_layer)

    for edge in scene_graph.edges:
        for reveal_layer in _edge_reveal_layers(
            edge, layout=layout, style=style, fps=fps, work_dir=work_dir,
        ):
            _chain_overlay(reveal_layer)

    filters.append(
        f"[{label}]scale={out_width}:{out_height}:flags=lanczos,setsar=1,format=yuv420p,fps={fps}[outv]"
    )

    if on_progress:
        on_progress("Encoding final video…", 0.55)

    def _ffmpeg_progress(info: dict) -> None:
        if not on_progress:
            return
        time_str = info.get("time")
        if not time_str:
            return
        try:
            h, m, s = time_str.split(":")
            elapsed = int(h) * 3600 + int(m) * 60 + float(s)
        except ValueError:
            return
        fraction = 0.55 + 0.35 * max(0.0, min(1.0, elapsed / duration))
        on_progress(f"Encoding final video… ({elapsed:.0f}s/{duration:.0f}s)", fraction)

    cmd = ["ffmpeg", *inputs, "-filter_complex", ";".join(filters), "-map", "[outv]",
           "-t", f"{duration:.4f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out_path)]
    result = run_ffmpeg(
        cmd, owner="overscaled_render", media_duration_s=duration, label="overscaled_render",
        on_progress=_ffmpeg_progress,
    )
    if result.returncode != 0 or not out_path.is_file():
        raise RuntimeError(f"Overscaled render failed (rc={result.returncode}): {result.stderr[-2000:]}")

    shutil.rmtree(work_dir, ignore_errors=True)
    if on_progress:
        on_progress("Encoding final video… done", 0.90)
    return out_path
