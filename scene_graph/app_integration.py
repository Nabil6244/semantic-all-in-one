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
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional

from editorial.timeline import EditorialTimeline
from scene_graph.media_resolution import resolve_scene_graph_media
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline
from scene_graph.schema import SceneGraph
from scene_graph.voiceover_sync import WhisperWord

ProgressCallback = Callable[[str, float], None]


@dataclasses.dataclass
class OverscaledGenerationResult:
    ok: bool
    errors: List[str]
    output_path: Optional[Path] = None
    scene_graph: Optional[SceneGraph] = None
    timeline: Optional[EditorialTimeline] = None
    cancelled: bool = False


def _fail(errors: List[str]) -> OverscaledGenerationResult:
    return OverscaledGenerationResult(ok=False, errors=errors)


def _report(progress_cb: Optional[ProgressCallback], message: str, fraction: float) -> None:
    if progress_cb is not None:
        try:
            progress_cb(message, fraction)
        except Exception:
            pass  # a broken progress callback must never abort generation


def _scaled_resolution(resolution: str, pixel_scale: int) -> str:
    """"1920x1080" at pixel_scale 2 -> "3840x2160"."""
    if int(pixel_scale or 1) <= 1:
        return resolution
    w, h = (int(v) for v in resolution.lower().split("x"))
    return f"{w * int(pixel_scale)}x{h * int(pixel_scale)}"


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
    flow_video_account_ids: Optional[List[str]] = None,
    whisper_words: Optional[List[WhisperWord]] = None,
    progress_cb: Optional[ProgressCallback] = None,
    log: Callable[[str], None] = print,
    on_scene_start=None,
    on_scene_complete=None,
    on_scene_generating=None,
    on_manager_ready=None,
    use_local_planner: bool = False,
    cancel_check: Optional[Callable[[], bool]] = None,
    pixel_scale: int = 1,
) -> OverscaledGenerationResult:
    """Overscaled CSV + real voiceover -> a real, final MP4.

    ``pixel_scale`` 2 exports in 4K: laid out at ``resolution`` exactly as before, drawn with twice the pixels.

    Requires neither Gemini nor an API key for the deterministic parts
    (CSV compile / layout / composition / camera / retiming); real network
    media resolution (Flow/Pexels/YouTube) only runs for nodes whose
    asset_type actually calls for it, exactly like the normal pipeline.

    ``whisper_words`` is optional, real per-word (word, start, end) voiceover
    timestamps — the SAME shape/source the normal pipeline already produces
    (see app.py's existing get_cached_whisper_words/transcribe_audio call
    site). When given, run_overscaled_pipeline retimes every beat against
    real narration timing instead of the cruder proportional whole-segment
    scale; when omitted (the previous, still-default behavior), nothing
    changes here.

    ``use_local_planner`` (default False — every existing caller keeps its
    exact current behavior): the CSV at ``overscaled_csv_path`` only needs
    ``scene_number``/``script_segment`` columns (``asset_type``/``prompt``
    stay optional); the Local Visual Planner
    (scene_graph.generator.generate_scene_graph_local_planner) infers node/
    role/relationship/group structure from narration language instead of
    the dedicated Overscaled/Exp Solar CSV vocabulary (beat/node_id/
    relationship_to/chapter/...). Media resolution, retiming, layout,
    composition, rendering, and the final export are all completely
    unaffected — both paths converge on the same SceneGraph contract.
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

    from scene_graph.overscaled_csv import duplicate_scene_numbers

    dupes = duplicate_scene_numbers(csv_rows)
    if dupes:
        return _fail([f"each row needs its own scene_number; repeated: {', '.join(dupes[:10])}"])

    if style_preset_id == "exp_solar" and not use_local_planner:
        # Exp Solar CSVs use their own schema (beat/chapter/relationship_to/
        # ... — see scene_graph.exp_solar_csv) and must be adapted into
        # Overscaled-CSV-shaped rows BEFORE either compile_overscaled_csv
        # call below — otherwise those columns are silently ignored and the
        # render doesn't match the Visual Plan the operator already
        # reviewed (which DOES go through this same adapter, in app.py's
        # _load_overscaled_csv). No second SceneGraph/renderer: from here
        # on this is the exact same path Overscaled itself uses.
        #
        # Skipped entirely when use_local_planner is set: the planner needs
        # only scene_number/script_segment and infers its own structure —
        # it has no concept of Exp Solar's beat/chapter/relationship_to
        # vocabulary, so running the adapter against a bare narration CSV
        # would either no-op or reject rows that were never meant to have
        # those columns in the first place.
        #
        # This whole call runs on a background thread (app.py's
        # _run_overscaled_generation worker) with no wrapper of its own —
        # an uncaught exception here previously escaped this function
        # (breaking its own "never raises past this module" contract),
        # escaped the thread, and was silently dropped by Python's default
        # threading.excepthook, which is invisible in a windowed packaged
        # build. Converting any failure into the existing _fail() result
        # restores that contract and surfaces the real error through the
        # normal "Overscaled generation failed" dialog instead of hanging.
        try:
            from .exp_solar_csv import adapt_exp_solar_csv_rows

            adapted = adapt_exp_solar_csv_rows(csv_rows)
        except Exception as exc:
            return _fail([f"Exp Solar CSV adaptation failed: {exc}"])

        if not adapted.ok:
            return _fail(adapted.errors)
        for warning in adapted.warnings:
            log(f"[Exp Solar] {warning}")
        csv_rows = adapted.rows

    if use_local_planner:
        from scene_graph.generator import generate_scene_graph_local_planner, scene_rows_from_csv_rows

        compiled = generate_scene_graph_local_planner(
            segment_id, scene_rows_from_csv_rows(csv_rows), title=title, style_preset=style_preset_id
        )
    else:
        compiled = compile_overscaled_csv(csv_rows, segment_id=segment_id, title=title, style_preset=style_preset_id)
    if not compiled.ok:
        return _fail(compiled.errors)

    def _cancelled() -> bool:
        return bool(cancel_check is not None and cancel_check())

    # Checked BEFORE any media is fetched: when the voiceover says far fewer
    # words than the plan's script (a different/shorter take), word-timed
    # retiming runs out of speech and squeezes every remaining scene into
    # the audio's last instant — which surfaced only after every asset was
    # downloaded, as layout's cryptic "overlapping nodes" failure.
    voiceover_check = check_voiceover_matches_script(csv_rows, whisper_words)
    if voiceover_check is not None:
        log(voiceover_check.diagnostic())
        if os.environ.get("VIDEOGEN_VOICEOVER_DIAG", "").strip() in ("1", "true", "yes"):
            log(f"[VOICEOVER CHECK] script: {' '.join(_narration_rows_text(csv_rows))[:2000]}")
            log(f"[VOICEOVER CHECK] voiceover: {' '.join(str(w[0]) for w in whisper_words)[:2000]}")
        if voiceover_check.status == "fail":
            return _fail([voiceover_check.message])
        if voiceover_check.status == "warn":
            log(f"[VOICEOVER CHECK] {voiceover_check.message}")

    if _cancelled():
        return OverscaledGenerationResult(ok=False, errors=["Cancelled"], cancelled=True)

    _report(progress_cb, "Resolving media (Flow/stock/YouTube/local)…", 0.20)
    images_dir = work_dir_path / "media"
    try:
        resolved_media: Dict[str, str] = resolve_scene_graph_media(
            compiled.scene_graph, images_dir=images_dir,
            pexels_api_key=pexels_api_key, flow_engine_manager=flow_engine_manager,
            flow_settings=flow_settings, flow_video_account_ids=flow_video_account_ids, log=log,
            on_scene_start=on_scene_start, on_scene_complete=on_scene_complete,
            on_scene_generating=on_scene_generating, on_manager_ready=on_manager_ready,
        )
    except SystemExit as exc:
        return _fail([f"media resolution failed: {exc}"])
    except Exception as exc:
        return _fail([f"media resolution failed unexpectedly: {exc}"])
    if _cancelled():
        # Stopped during acquisition: don't go on to render a partial plan.
        return OverscaledGenerationResult(ok=False, errors=["Cancelled"], cancelled=True)

    # From here on, run_overscaled_pipeline reports its OWN finer-grained
    # progress (layout, composition, and — the genuinely long part — one
    # message per camera-leg render) straight through progress_cb, rather
    # than sitting on one flat "Building..." message for however many
    # minutes a real multi-node CSV's segment render actually takes.
    pipeline_result = run_overscaled_pipeline(
        csv_rows, segment_id=segment_id, title=title, style_preset_id=style_preset_id,
        voiceover_path=voiceover_path, out_dir=work_dir_path / "overscaled",
        resolved_media=resolved_media, resolution=resolution, fps=fps,
        whisper_words=whisper_words, progress_cb=progress_cb,
        use_local_planner=use_local_planner, cancel_check=cancel_check, pixel_scale=pixel_scale,
    )
    if pipeline_result.cancelled or _cancelled():
        return OverscaledGenerationResult(ok=False, errors=["Cancelled"], cancelled=True)
    if not pipeline_result.ok:
        return _fail(pipeline_result.errors)

    final_audio_path = voiceover_path
    if style_preset_id == "exp_solar":
        # Exp Solar's sound design layer: narration + deterministic SFX +
        # an optional ambience bed, via the EXISTING smart_editing FFmpeg
        # mixing pipeline (see scene_graph.exp_solar_audio) — never a
        # second audio engine. Overscaled (style_preset_id == "overscaled")
        # never reaches this branch, so its own plain voiceover mux below
        # is completely unaffected. Any failure here falls back to the
        # unmixed voiceover rather than failing the whole render.
        _report(progress_cb, "Building Exp Solar audio mix…", 0.93)
        try:
            from .exp_solar_audio import build_exp_solar_audio_mix

            mixed_path = build_exp_solar_audio_mix(
                pipeline_result.scene_graph, pipeline_result.layout,
                voiceover_path=Path(voiceover_path), output_path=work_dir_path / "exp_solar_audio_mix.wav",
            )
            final_audio_path = str(mixed_path)
        except Exception as exc:
            log(f"[Exp Solar] audio mix failed ({exc}); using narration only.")
            final_audio_path = voiceover_path

    _report(progress_cb, "Muxing final video with audio…", 0.97)
    try:
        _export_via_existing_renderer(
            pipeline_result.scene_graph, pipeline_result.segment_clip_path,
            voiceover_path=final_audio_path, output_path=Path(output_path),
            resolution=_scaled_resolution(resolution, pixel_scale), fps=fps, work_dir=work_dir_path,
        )
    except Exception as exc:
        return _fail([f"final export failed: {exc}"])

    if not Path(output_path).is_file():
        return _fail(["final export did not produce an output file"])
    problem = validate_rendered_output(Path(output_path), expected_duration_s=pipeline_result.scene_graph.duration)
    if problem:
        # Never report a broken file as success (a missing stream or a clip
        # far shorter than the narration is a failed render, not a result).
        return _fail([f"final video failed validation: {problem}"])

    _report(progress_cb, "Done.", 1.0)
    return OverscaledGenerationResult(
        ok=True, errors=[], output_path=Path(output_path),
        scene_graph=pipeline_result.scene_graph, timeline=pipeline_result.timeline,
    )


# --- Voiceover <-> script check ------------------------------------------
# Thresholds calibrated on real project recordings (script-word coverage by
# an order-preserving word alignment, after comparison-only normalization):
#   matching script <-> its voiceover .............. 0.90 - 1.00
#   revised / reworded take of the same story ....... 0.53 - 0.62
#   a different script's voiceover .................. 0.01 - 0.12
# Only a materially different script (or no usable speech) blocks Generate.
_VO_PASS_COVERAGE = 0.80
_VO_FAIL_COVERAGE = 0.35
_VO_TOKEN_RE = re.compile(r"[0-9a-z]+(?:['.-][0-9a-z]+)*")


def _comparison_tokens(text: str) -> List[str]:
    """Comparison-only normalization — never applied to narration or render
    text. Unicode NFKC, case-folded, curly quotes/apostrophes unified,
    punctuation and whitespace dropped; words, numbers, and in-word
    apostrophes/hyphens/decimal points kept ("nasa's artemis-iii 1931")."""
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")
    return _VO_TOKEN_RE.findall(text)


def _narration_rows_text(csv_rows) -> List[str]:
    """The SPOKEN narration only: each row's script_segment exactly once.
    Rows with no narration (visual-only / continuation / checklist members
    authored with an empty script_segment) contribute nothing, and a row
    repeating the previous row's text verbatim (one narration beat spread
    over several visual rows) is not counted twice. Visual metadata
    (prompt, visual_hint, captions, titles, [role] display prefixes — those
    exist only on UI rows, never in the CSV) is never read."""
    texts: List[str] = []
    for row in csv_rows:
        text = str(row.get("script_segment") or "").strip()
        if text and (not texts or text != texts[-1]):
            texts.append(text)
    return texts


@dataclasses.dataclass
class VoiceoverCheck:
    status: str  # "pass" | "warn" | "fail"
    coverage: float
    script_words: int
    spoken_words: int
    message: str

    def diagnostic(self) -> str:
        return (
            f"[VOICEOVER CHECK] {self.status.upper()} — {self.coverage:.0%} of {self.script_words} "
            f"script words found in order in {self.spoken_words} transcribed words "
            f"(pass >= {_VO_PASS_COVERAGE:.0%}, block < {_VO_FAIL_COVERAGE:.0%})"
        )


def check_voiceover_matches_script(csv_rows, whisper_words) -> Optional[VoiceoverCheck]:
    """Compare the plan's spoken narration with the transcribed voiceover by
    an order-preserving word alignment (difflib), NOT by word count or audio
    duration — natural pace, pauses, Whisper merges/splits, and numbers read
    aloud all change counts without meaning the recording is wrong. Returns
    None when there is nothing to compare (no transcript -> the proportional
    retime is used; no narration in the CSV)."""
    import difflib

    if whisper_words is None:
        return None
    script = [t for text in _narration_rows_text(csv_rows) for t in _comparison_tokens(text)]
    if not script:
        return None
    spoken = [t for word in whisper_words for t in _comparison_tokens(word[0] if word else "")]
    if not spoken:
        return VoiceoverCheck(
            "fail", 0.0, len(script), 0,
            "No speech was recognised in the voiceover (silent, corrupt, or not narration). "
            "Import the narration recording for this script, then Generate again.",
        )
    matcher = difflib.SequenceMatcher(a=script, b=spoken, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    coverage = matched / len(script)
    if coverage >= _VO_PASS_COVERAGE:
        return VoiceoverCheck("pass", coverage, len(script), len(spoken), "")
    if coverage >= _VO_FAIL_COVERAGE:
        return VoiceoverCheck(
            "warn", coverage, len(script), len(spoken),
            f"The voiceover's wording differs from the script ({coverage:.0%} of the script matches) — "
            "it looks like a different take of the same story. Generating anyway; scene timing may "
            "drift where the wording differs.",
        )
    return VoiceoverCheck(
        "fail", coverage, len(script), len(spoken),
        f"The voiceover doesn't match this plan's script: only {coverage:.0%} of the script's words "
        f"are spoken in it ({len(spoken)} transcribed words vs {len(script)} in the script). It looks "
        "like a recording of a different script. Import the voiceover recorded from this script, or "
        "import the CSV that belongs to this recording, then Generate again.",
    )


def validate_rendered_output(path: Path, *, expected_duration_s: float, tolerance_s: float = 1.5) -> Optional[str]:
    """ffprobe the final file. Returns a human-readable problem, or None when
    it has a decodable video stream with real frame size, an audio stream,
    and a duration within ``tolerance_s`` of the SceneGraph's own (i.e. the
    narration it was retimed to). Probe unavailable -> None (don't fail a
    render on a missing ffprobe; the file-exists check still applies)."""
    import json
    import subprocess

    from media_duration import _resolve_ffprobe
    from providers import hidden_subprocess as hs

    ffprobe = _resolve_ffprobe()
    if not ffprobe:
        return None
    try:
        out = hs.run(
            [ffprobe, "-v", "error", "-show_entries",
             "stream=codec_type,width,height:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        info = json.loads(out.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return f"could not be probed ({exc})"
    streams = info.get("streams") or []
    video = [s for s in streams if s.get("codec_type") == "video"]
    if not video or not (video[0].get("width") and video[0].get("height")):
        return "no decodable video stream"
    if not any(s.get("codec_type") == "audio" for s in streams):
        return "no audio stream (narration missing)"
    try:
        duration = float((info.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        return "duration unreadable"
    if expected_duration_s and abs(duration - float(expected_duration_s)) > tolerance_s:
        return f"duration {duration:.1f}s but the narration/plan is {float(expected_duration_s):.1f}s"
    return None


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
