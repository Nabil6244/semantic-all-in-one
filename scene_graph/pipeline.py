"""End-to-end Overscaled orchestration:

    Overscaled CSV + voiceover + style
        -> compile_overscaled_csv        (scene_graph.overscaled_csv)
        -> retime to real voiceover       (scene_graph.voiceover_sync)
        -> deterministic fixed-canvas layout (scene_graph.layout)
        -> ONE fixed-canvas ffmpeg encode (scene_graph.render — no camera,
                                            no per-object intermediate files)
        -> EditorialTimeline              (scene_graph.timeline)

No Gemini, no network, no randomness beyond whatever the caller's own
resolved_media/voiceover files contain. Every step before rendering is pure
data; rendering is the only step that touches disk/ffmpeg. On any failure
this returns ``ok=False`` with a clear ``errors`` list and never raises past
this module and never hands back a partially-built result — the caller can
safely keep using the existing (non-Overscaled) pipeline instead.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from editorial.timeline import EditorialTimeline

from .layout import SceneGraphLayout, compute_layout, find_overlaps
from .overscaled_csv import compile_overscaled_csv
from .render import render_overscaled_segment
from .schema import SceneGraph
from .style_presets import StylePreset, load_style_preset
from .timeline import compile_segment_to_timeline
from .voiceover_sync import WhisperWord, retime_to_audio_duration, retime_to_whisper_words


@dataclasses.dataclass
class OverscaledPipelineResult:
    ok: bool
    errors: List[str]
    scene_graph: Optional[SceneGraph] = None
    layout: Optional[SceneGraphLayout] = None
    segment_clip_path: Optional[Path] = None
    timeline: Optional[EditorialTimeline] = None


def _fail(errors: Sequence[str]) -> OverscaledPipelineResult:
    return OverscaledPipelineResult(ok=False, errors=list(errors))


def _sync_grouped_node_timing(scene_graph: SceneGraph) -> SceneGraph:
    """Exp Solar ONLY (never called for style_preset_id != "exp_solar", so
    Overscaled's own layout stays byte-identical): nodes chained into one
    on-screen composition -- a two_panel pair, a four_row/index_grid run,
    joined by "group"/"group_grid" edges (see scene_graph.exp_solar_csv's
    _chain_two_panel_beats/_chain_four_row_beats/_chain_index_grid_beats
    and scene_graph.layout._connected_chapters) -- are meant to appear
    TOGETHER as a single grouped beat. But each CSV row still compiles to
    its OWN narration beat with its OWN appear_at (overscaled_csv.py /
    voiceover_sync.py, shared with Overscaled, unchanged here), so a
    continuation row (the 2nd/3rd/4th member, typically authored with an
    empty script_segment) only becomes visible partway through the
    group's own on-screen span -- for most of a four_row chapter's
    duration only the first member is on screen alone, and
    layout.compute_layout's adaptive sizing (_peak_concurrent) sees low
    real overlap and can shrink the composition's slot template to match.

    This is a purely additive post-retiming pass: every member of a
    group/group_grid connected set gets its appear_at snapped to the
    EARLIEST member's appear_at, so they all become visible at the same
    instant (still only for the group's real on-screen span -- nothing
    about WHEN that span ends changes). A causal ("sequential"/"callout")
    edge between two otherwise-independent nodes is untouched -- only the
    two group-edge kinds unify timing, never causal storytelling pacing."""

    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for edge in scene_graph.edges:
        if edge.kind in ("group", "group_grid"):
            union(edge.from_node, edge.to_node)

    if not parent:
        return scene_graph

    groups: Dict[str, List[str]] = {}
    for node in scene_graph.nodes:
        if node.id in parent:
            groups.setdefault(find(node.id), []).append(node.id)

    data = scene_graph.to_dict()
    node_by_id = {n["id"]: n for n in data["nodes"]}
    for member_ids in groups.values():
        if len(member_ids) < 2:
            continue
        earliest = min(float(node_by_id[nid]["appear_at"]) for nid in member_ids)
        for nid in member_ids:
            node_by_id[nid]["appear_at"] = round(earliest, 4)
    return SceneGraph.from_dict(data)


def _merge_grouped_beats_for_retime(scene_graph: SceneGraph) -> SceneGraph:
    """Exp Solar ONLY, called BEFORE retime_to_whisper_words (never for
    Overscaled, never for the no-whisper retime_to_audio_duration path,
    which has no per-beat word-consumption logic to begin with):
    compile_overscaled_csv builds one SceneGraphBeat per CSV row
    (shared with Overscaled, unmodified here), and voiceover_sync.py's
    retime_to_whisper_words claims real Whisper words per beat via
    ``word_count = max(1, len(narration.split()))`` -- so a continuation
    row (empty script_segment, the correct way to author a two_panel/
    four_row/index_grid member per the CSV-authoring guidance) still
    steals exactly 1 real word it never actually needed. Across a video
    with several such groups this compounds: every beat AFTER a group
    drifts a little further from the real audio for each continuation
    row that preceded it.

    This purely additive pre-pass (only scene_graph.beats is touched;
    every node/edge is untouched here and re-positioned correctly
    afterward by _sync_grouped_node_timing, which already overwrites
    every group member's appear_at to the group's own earliest anyway)
    merges each group's continuation beats into their group's own
    primary beat -- the first member in CSV order, whose start/end widen
    to cover the whole group's original placeholder span -- and drops
    the continuation beats from the list entirely, so
    retime_to_whisper_words's sequential word-count loop consumes real
    words ONCE per group, never once per row."""
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for edge in scene_graph.edges:
        if edge.kind in ("group", "group_grid"):
            union(edge.from_node, edge.to_node)

    if not parent:
        return scene_graph

    groups: Dict[str, List[str]] = {}
    for node in scene_graph.nodes:
        if node.id in parent:
            groups.setdefault(find(node.id), []).append(node.id)

    node_scene_number = {n.id: n.metadata.get("scene_number") for n in scene_graph.nodes}
    data = scene_graph.to_dict()
    beat_by_id = {b["beat_id"]: b for b in data["beats"]}

    drop_beat_ids: set = set()
    for member_ids in groups.values():
        if len(member_ids) < 2:
            continue
        member_beat_ids = [f"beat_{node_scene_number[nid]}" for nid in member_ids]
        member_beats = [beat_by_id[bid] for bid in member_beat_ids if bid in beat_by_id]
        if len(member_beats) < 2:
            continue
        primary = member_beats[0]
        primary["start"] = min(float(b["start"]) for b in member_beats)
        primary["end"] = max(float(b["end"]) for b in member_beats)
        for bid in member_beat_ids[1:]:
            if bid in beat_by_id:
                drop_beat_ids.add(bid)

    data["beats"] = [b for b in data["beats"] if b["beat_id"] not in drop_beat_ids]
    return SceneGraph.from_dict(data)


def run_overscaled_pipeline(
    csv_rows: Sequence[Mapping[str, str]],
    *,
    segment_id: str,
    voiceover_path: str,
    out_dir: Path,
    title: str = "",
    style_preset_id: str = "overscaled",
    resolved_media: Optional[Dict[str, str]] = None,
    whisper_words: Optional[Sequence[WhisperWord]] = None,
    canvas_width: Optional[int] = None,
    canvas_height: Optional[int] = None,
    resolution: str = "1920x1080",
    fps: int = 30,
    write_debug_files: bool = True,
    progress_cb: Optional[Callable[[str, float], None]] = None,
) -> OverscaledPipelineResult:
    """``progress_cb(message, fraction)`` is optional and best-effort —
    scene_graph.render does the whole segment in ONE ffmpeg encode (no
    camera, no per-leg re-encodes), so progress here is coarse: layout,
    then composing/writing the reveal layers, then the single encode's own
    ffmpeg ``time=`` progress (see render_overscaled_segment's on_progress).
    A broken callback must never abort a real render."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _report(message: str, fraction: float) -> None:
        if progress_cb is not None:
            try:
                progress_cb(message, fraction)
            except Exception:
                pass

    style = load_style_preset(style_preset_id)
    if style is None:
        return _fail([f"unknown style preset: {style_preset_id!r}"])

    compiled = compile_overscaled_csv(csv_rows, segment_id=segment_id, title=title, style_preset=style_preset_id)
    if not compiled.ok:
        return _fail(compiled.errors)
    scene_graph = compiled.scene_graph

    # Everything below touches real files/Pillow/ffmpeg at production scale
    # (a real user's canvas/media set is far bigger than anything exercised
    # in tests) — the module docstring promises "never raises past this
    # module"; a single top-level guard is what actually makes that true,
    # rather than each risky call needing its own try/except (a real bug:
    # compute_layout/render_overscaled_segment ran completely unguarded, so an
    # exception there escaped all the way up into an unguarded UI worker
    # thread and looked like the app had silently frozen).
    try:
        _report("Synchronizing with voiceover…", 0.35)
        if whisper_words:
            retime_input = (
                _merge_grouped_beats_for_retime(scene_graph)
                if style_preset_id == "exp_solar" else scene_graph
            )
            scene_graph = retime_to_whisper_words(retime_input, whisper_words)
        else:
            scene_graph = retime_to_audio_duration(scene_graph, voiceover_path)

        if style_preset_id == "exp_solar":
            scene_graph = _sync_grouped_node_timing(scene_graph)

        if write_debug_files:
            (out_dir / "overscaled_scene_graph.json").write_text(
                json.dumps(scene_graph.to_dict(), indent=2), encoding="utf-8"
            )

        _report("Computing layout…", 0.40)
        # Only a style preset's metadata can raise this above the default
        # 3-card cap (see layout.compute_layout's own docstring) — absent
        # for every existing preset except exp_solar.json, so Overscaled's
        # own layout is byte-identical to before this existed.
        max_active_per_chapter = (style.metadata or {}).get("max_active_per_chapter")
        layout = compute_layout(
            scene_graph, resolved_media=resolved_media,
            canvas_width=canvas_width, canvas_height=canvas_height,
            max_active_per_chapter=max_active_per_chapter,
        )
        overlaps = find_overlaps(layout)
        if overlaps:
            return _fail([f"layout produced overlapping nodes: {overlaps}"])

        if write_debug_files:
            (out_dir / "overscaled_layout.json").write_text(json.dumps(layout.to_dict(), indent=2), encoding="utf-8")

        clip_path = out_dir / "overscaled_segment.mp4"
        render_overscaled_segment(
            scene_graph, layout, style,
            out_path=clip_path, resolved_media=resolved_media, resolution=resolution, fps=fps,
            work_dir=out_dir / "_render",
            on_progress=lambda message, fraction: _report(message, fraction),
        )

        _report("Building timeline…", 0.95)
        timeline = compile_segment_to_timeline(
            segment_clip_path=str(clip_path),
            voiceover_path=voiceover_path,
            duration=scene_graph.duration,
            scene_number=segment_id,
        )
    except Exception as exc:
        return _fail([f"Overscaled pipeline failed: {exc}"])

    return OverscaledPipelineResult(
        ok=True, errors=[], scene_graph=scene_graph, layout=layout,
        segment_clip_path=clip_path, timeline=timeline,
    )
