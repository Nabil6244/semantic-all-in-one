"""The single UI-independent entry point the application's "Generate" button
calls for the Overscaled workflow.

    Overscaled CSV + voiceover path + output path
        -> compile_overscaled_csv          (scene_graph.overscaled_csv)
        -> resolve_scene_graph_media        (scene_graph.media_resolution —
                                              the EXISTING Flow/Pexels/YouTube/
                                              local provider stack)
        -> run_overscaled_pipeline          (scene_graph.pipeline: retime to
                                              voiceover, layout, composition,
                                              camera, rendered segment clip,
                                              EditorialTimeline)
        -> video_generator.render_video()   (the EXISTING, unmodified FFmpeg
                                              exporter — same call shape
                                              proven in
                                              test_overscaled_pipeline_e2e.py)

Kept as a plain function (no Tk/CTk imports) so it is fully unit-testable
without a display, and so app.py's own responsibility stays limited to
thin UI glue: reading widget state, calling this function on a background
thread, and reporting the result through the EXISTING progress/log queue —
never re-implementing any of the above.

Never calls Gemini, never touches Visual Director, never touches the normal
CSV parser. On any failure this returns ``ok=False`` with a clear message —
it never raises past this module and never leaves a half-written output
file in place of a real one.
"""

from __future__ import annotations

import csv
import dataclasses
import os
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from editorial.timeline import EditorialTimeline
from scene_graph.media_resolution import resolve_scene_graph_media
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline
from scene_graph.schema import SceneGraph

ProgressCallback = Callable[[str, float], None]


@dataclasses.dataclass
class OverscaledGenerationResult:
    ok: bool
    errors: List[str]
    output_path: Optional[Path] = None
    scene_graph: Optional[SceneGraph] = None
    timeline: Optional[EditorialTimeline] = None


def _fail(errors: List[str]) -> OverscaledGenerationResult:
    return OverscaledGenerationResult(ok=False, errors=errors)


def _report(progress_cb: Optional[ProgressCallback], message: str, fraction: float) -> None:
    if progress_cb is not None:
        try:
            progress_cb(message, fraction)
        except Exception:
            pass  # a broken progress callback must never abort generation


def generate_overscaled_video(
    overscaled_csv_path: str,
    voiceover_path: str,
    output_path: str,
    *,
    resolution: str = "1920x1080",
    fps: int = 30,
    segment_id: str = "overscaled_segment",
    title: str = "",
    style_preset_id: str = "overscaled",
    work_dir: Optional[str] = None,
    pexels_api_key: Optional[str] = None,
    flow_engine_manager=None,
    flow_settings: Optional[dict] = None,
    progress_cb: Optional[ProgressCallback] = None,
    log: Callable[[str], None] = print,
) -> OverscaledGenerationResult:
    """Overscaled CSV + real voiceover -> a real, final MP4.

    Requires neither Gemini nor an API key for the deterministic parts
    (CSV compile / layout / composition / camera / retiming); real network
    media resolution (Flow/Pexels/YouTube) only runs for nodes whose
    asset_type actually calls for it, exactly like the normal pipeline.
    """

    csv_path = Path(overscaled_csv_path)
    if not csv_path.is_file():
        return _fail([f"Overscaled CSV not found: {csv_path}"])
    if not Path(voiceover_path).is_file():
        return _fail([f"voiceover file not found: {voiceover_path}"])

    work_dir_path = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="overscaled_"))
    work_dir_path.mkdir(parents=True, exist_ok=True)

    _report(progress_cb, "Parsing Overscaled CSV…", 0.05)
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            csv_rows = list(csv.DictReader(f))
    except OSError as exc:
        return _fail([f"could not read Overscaled CSV: {exc}"])

    compiled = compile_overscaled_csv(csv_rows, segment_id=segment_id, title=title, style_preset=style_preset_id)
    if not compiled.ok:
        return _fail(compiled.errors)

    _report(progress_cb, "Resolving media (Flow/stock/YouTube/local)…", 0.20)
    images_dir = work_dir_path / "media"
    try:
        resolved_media: Dict[str, str] = resolve_scene_graph_media(
            compiled.scene_graph, images_dir=images_dir,
            pexels_api_key=pexels_api_key, flow_engine_manager=flow_engine_manager,
            flow_settings=flow_settings, log=log,
        )
    except SystemExit as exc:
        return _fail([f"media resolution failed: {exc}"])
    except Exception as exc:
        return _fail([f"media resolution failed unexpectedly: {exc}"])

    # From here on, run_overscaled_pipeline reports its OWN finer-grained
    # progress (layout, composition, and — the genuinely long part — one
    # message per camera-leg render) straight through progress_cb, rather
    # than sitting on one flat "Building..." message for however many
    # minutes a real multi-node CSV's segment render actually takes.
    pipeline_result = run_overscaled_pipeline(
        csv_rows, segment_id=segment_id, title=title, style_preset_id=style_preset_id,
        voiceover_path=voiceover_path, out_dir=work_dir_path / "overscaled",
        resolved_media=resolved_media, resolution=resolution, fps=fps,
        progress_cb=progress_cb,
    )
    if not pipeline_result.ok:
        return _fail(pipeline_result.errors)

    _report(progress_cb, "Muxing final video with voiceover…", 0.97)
    try:
        _export_via_existing_renderer(
            pipeline_result.scene_graph, pipeline_result.segment_clip_path,
            voiceover_path=voiceover_path, output_path=Path(output_path),
            resolution=resolution, fps=fps, work_dir=work_dir_path,
        )
    except Exception as exc:
        return _fail([f"final export failed: {exc}"])

    if not Path(output_path).is_file():
        return _fail(["final export did not produce an output file"])

    _report(progress_cb, "Done.", 1.0)
    return OverscaledGenerationResult(
        ok=True, errors=[], output_path=Path(output_path),
        scene_graph=pipeline_result.scene_graph, timeline=pipeline_result.timeline,
    )


def _export_via_existing_renderer(
    scene_graph: SceneGraph,
    segment_clip_path: Path,
    *,
    voiceover_path: str,
    output_path: Path,
    resolution: str,
    fps: int,
    work_dir: Path,
) -> None:
    """The exact call shape proven in
    test_overscaled_pipeline_e2e.py::TestRealExistingFFmpegExport — the
    UNMODIFIED video_generator.render_video(), fed one SINGLE_SHOT scene
    whose source is the already fully-composed Overscaled clip."""

    from PIL import Image

    import video_generator as vg

    duration = scene_graph.duration
    # render_video's own missing-asset precondition check wants a numbered
    # file to exist; the REAL source rendered is EditDecision.shots[].source_path.
    stub_images_dir = work_dir / "stub_images"
    stub_images_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 9), (0, 0, 0)).save(stub_images_dir / "1.png")

    aligned_rows = [{"scene_number": "1", "start_time": 0.0, "script_segment": scene_graph.title or scene_graph.segment_id}]
    decision_map = {
        "1": {
            "scene_number": "1", "required_duration": duration, "strategy": "SINGLE_SHOT",
            "shots": [{"shot_id": "s1", "output_duration": duration, "source_path": str(segment_clip_path),
                       "transition_in": "cut", "transition_duration": 0.0}],
            "source_asset": str(segment_clip_path),
        }
    }

    old_cwd = os.getcwd()
    try:
        os.chdir(stub_images_dir)
        vg.render_video(
            aligned_rows, duration, stub_images_dir, str(voiceover_path), str(output_path),
            resolution, fps, zoom=False, visual_transitions=False,
            edit_decisions_by_scene=decision_map,
        )
    finally:
        os.chdir(old_cwd)
