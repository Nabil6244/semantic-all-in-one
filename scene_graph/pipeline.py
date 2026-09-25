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
            scene_graph = retime_to_whisper_words(scene_graph, whisper_words)
        else:
            scene_graph = retime_to_audio_duration(scene_graph, voiceover_path)

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
