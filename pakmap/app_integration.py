"""The UI-independent entry points the app's pakMap mode calls (no Tk, like scene_graph.app_integration):

    check_pakmap_plan(...)       CSV + the narration's words -> the plan report (no rendering)
    generate_pakmap_video(...)   CSV + voiceover -> compile -> render with pakmap-engine -> mux the narration -> a final MP4

Never raises past this module: every failure comes back as ok=False with messages written for the author."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, List, Optional, Sequence

from .anchor import Word
from .compile import CompileError, CompileResult, Report, compile_csv
from .pacing import apply_pacing
from .schema import CsvError

ProgressCallback = Callable[[str, float], None]
MEDIA_DIRNAME = "media"  # inside the work folder when the app does not give one: the Visual Plan's pictures and their .asset_manifest.json


@dataclass
class PakmapResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    output_path: Optional[Path] = None
    report: Optional[Report] = None
    credits: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cancelled: bool = False
    unresolved: List[str] = field(default_factory=list)  # Visual Plan scene numbers that still have no picture (fix them in the Visual tab)
    audio: Optional[object] = None  # pakmap.audio_plan.AudioPlan (cues, beds, missing/approximate sounds)
    audio_mix: Optional[object] = None  # pakmap.audio_mix.MixResult
    # Sound design was asked for but is not in the video (the mix failed, so the video has the narration only): why.
    sound_failed: Optional[str] = None


def _report(cb: Optional[ProgressCallback], message: str, fraction: float) -> None:
    if cb is not None:
        try:
            cb(message, fraction)
        except Exception:
            pass  # a broken progress callback must never abort generation


def voiceover_duration(path: "str | Path") -> Optional[float]:
    from media_duration import probe_media_duration

    value = probe_media_duration(str(path))
    return float(value) if value and value > 0 else None


def visual_plan_dicts(csv_path: "str | Path") -> List[dict]:
    """The pictures this script asks for, as rows for the app's Visual Plan table (scene_number, script_segment, asset_type,
    prompt). Local files are not listed: they are the author's own choice."""
    from .schema import parse_csv
    from .sourcing import find_occurrences, scene_row_dicts

    return scene_row_dicts(find_occurrences(parse_csv(csv_path)[0]))


def friendly_problems(csv_path: "str | Path", errors: Sequence[str]) -> List[str]:
    """Tie each `row N: ...` problem to the layer it is about ("Row 12 (marker NAIROBI): ..."), so the author is told which
    visual to fix and not just a row number. The raw messages stay available to the caller for debugging."""
    import re

    from .schema import parse_csv

    try:
        by_line = {r.line: r for r in parse_csv(csv_path)[0]}
    except Exception:
        by_line = {}
    out = []
    for e in errors:
        m = re.match(r"^(?:renderer rule: )?row (\d+): (.*)$", str(e), re.S)
        row = by_line.get(int(m.group(1))) if m else None
        if m and row is not None:
            what = row.layer_type + (f" {row.label_text}" if row.label_text else (f" {row.geo_ref}" if row.geo_ref else ""))
            out.append(f"Row {m.group(1)} ({what}): {m.group(2)}")
        else:
            out.append(str(e))
    return out


def row_times(report) -> dict:
    """CSV row number -> the second its layer appears (from a compiled plan), to label Visual Plan rows."""
    return {e.row: e.t_in for e in getattr(report, "events", [])}


def describe_sourced(csv_path: "str | Path", images_dir: "str | Path | None" = None) -> List[str]:
    """Plain-language lines about pictures that will be fetched from stock / Flow / YouTube (and which are already saved)."""
    from .schema import parse_csv
    from .sourcing import find_occurrences

    try:
        occs = find_occurrences(parse_csv(csv_path)[0])
    except Exception:
        return []
    saved = set()
    if images_dir and occs:
        try:
            from asset_manager import AssetManifest

            man = AssetManifest(Path(images_dir))
            saved = {str(o.scene_number) for o in occs if (man.get(str(o.scene_number)) or {}).get("status") == "complete"}
        except Exception:
            saved = set()
    lines = []
    for o in occs:
        state = "already saved" if str(o.scene_number) in saved else ("will be GENERATED with Flow (uses credits)" if o.uses_flow else "will be fetched")
        lines.append(f"picture {o.scene_number}: {o.kind}:{o.prompt!r} (row {o.line}) {state}; change it in the Visual Plan tab")
    return lines


def check_pakmap_plan(csv_path: "str | Path", words: Sequence[Word], *, duration: Optional[float] = None, base_dir: "str | Path | None" = None,
                      watermark: Optional[dict] = None, images_dir: "str | Path | None" = None) -> "tuple[Optional[CompileResult], Optional[Report], List[str]]":
    """Compile only. Returns (result, report, problems): result is None when there are problems; the report
    (when there is one) explains each issue."""
    try:
        res = compile_csv(csv_path, words, duration=duration, base_dir=base_dir, watermark=watermark)
        apply_pacing(res, csv_path)  # PakMap only: card handoff + picture-density warnings (pakmap/pacing.py)
        res.report.info.extend(describe_sourced(csv_path, images_dir))
        return res, res.report, []
    except CsvError as exc:
        return None, None, list(exc.problems)
    except CompileError as exc:
        return None, exc.report, list(exc.report.errors)
    except OSError as exc:
        return None, None, [f"could not read the CSV: {exc}"]
    except Exception as exc:  # never escape into the UI thread
        return None, None, [f"unexpected error while reading the script: {exc!r}"]


def plan_pakmap_sound(result: CompileResult, *, enabled: bool = True, catalog: object = None):
    """The sound plan for a compiled script, with library files found (and missing ones reported). No audio is read."""
    from .audio_mix import resolve_assets
    from .audio_plan import plan_audio

    plan = plan_audio(result.spec, result.audio_hints, enabled=enabled, duration=result.spec.get("duration"))
    return resolve_assets(plan, catalog)


def credits_text(credits: Sequence[str], warnings: Sequence[str] = ()) -> str:
    lines = ["Credits to include in the video description or end card:", ""] + [f"- {c}" for c in credits]
    if warnings:
        lines += ["", "Notes from the renderer:"] + [f"- {w}" for w in warnings]
    return "\n".join(lines) + "\n"


def generate_pakmap_video(
    csv_path: "str | Path", voiceover_path: "str | Path", output_path: "str | Path", *,
    work_dir: "str | Path", whisper_words: Sequence[Word], base_dir: "str | Path | None" = None,
    watermark: Optional[dict] = None, resolution: str = "1920x1080", fps: int = 30, title: str = "",
    progress_cb: Optional[ProgressCallback] = None, log: Callable[[str], None] = print,
    cancel_check: Optional[Callable[[], bool]] = None, render: Optional[Callable[..., object]] = None,
    sound_design: bool = True, sound_catalog: object = None,
    pexels_api_key: Optional[str] = None, flow_engine_manager: object = None, flow_settings: Optional[dict] = None,
    flow_video_account_ids: Optional[list] = None, media_callbacks: Optional[dict] = None, media_resolver: Optional[Callable[..., object]] = None,
    media_find_file: Optional[Callable[..., object]] = None, scene_rows: Optional[Sequence[object]] = None,
    media_dir: "str | Path | None" = None, media_manifest_cls: object = None, spec_extra: Optional[dict] = None,
    media_options: Optional[dict] = None, pixel_scale: int = 1,
) -> PakmapResult:
    """`pixel_scale` 2 exports in 4K: the script is laid out at `resolution` (cards, camera and zoom are unchanged) and every
    frame is drawn with twice the pixels, so a 1920x1080 layout comes out 3840x2160."""
    csv_path, voiceover_path, output_path = Path(csv_path), Path(voiceover_path), Path(output_path)
    if not csv_path.is_file():
        return PakmapResult(False, [f"pakMap CSV not found: {csv_path}"])
    if not voiceover_path.is_file():
        return PakmapResult(False, [f"voiceover file not found: {voiceover_path}"])
    if not whisper_words:
        return PakmapResult(False, ["the narration could not be transcribed, so there are no word times to anchor the script to"])
    cancelled = lambda: bool(cancel_check is not None and cancel_check())  # noqa: E731
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    try:
        width, height = (int(v) for v in resolution.lower().split("x"))
    except ValueError:
        return PakmapResult(False, [f"bad resolution {resolution!r}"])

    _report(progress_cb, "Reading the pakMap script…", 0.03)
    duration = voiceover_duration(voiceover_path)
    # Pictures named by source (stock_image:..., flow_image:...) are the Visual Plan table's rows. They are resolved by the existing
    # AssetManager into one images folder (a scene the table already holds, or one the user replaced there, is reused, not fetched
    # again), then read back by scene number and swapped into the script. `scene_rows` is the table as the user left it; without it
    # the rows are derived from the script.
    media_map = None
    unresolved: List[str] = []
    try:
        from .schema import parse_csv
        from .sourcing import fetch_scenes, find_occurrences

        occs = find_occurrences(parse_csv(csv_path)[0])
        if occs:
            from providers.base import SceneRow

            rows = list(scene_rows) if scene_rows else [SceneRow.from_csv_row(d) for d in visual_plan_dicts(csv_path)]
            wanted = {str(o.scene_number) for o in occs}
            rows = [r for r in rows if str(r.scene_number) in wanted]
            _report(progress_cb, f"Getting {len(rows)} picture(s) from stock / Flow / YouTube…", 0.05)
            got = fetch_scenes(
                rows, media_dir or (work / MEDIA_DIRNAME), resolver=media_resolver, find_file=media_find_file, manifest_cls=media_manifest_cls, log=log,
                pexels_api_key=pexels_api_key, flow_engine_manager=flow_engine_manager, flow_settings=flow_settings,
                flow_video_account_ids=flow_video_account_ids, **(media_callbacks or {}), **(media_options or {}),
            )
            if cancelled():
                return PakmapResult(False, ["Cancelled"], cancelled=True)
            if got.missing:
                by_n = {str(o.scene_number): o for o in occs}
                lines = [f"Picture {n} ({by_n[n].description}, script row {by_n[n].line}): {why}" for n, why in got.missing.items()]
                unresolved = list(got.missing)
                return PakmapResult(False, lines + ["Open the Visual Plan tab to Retry, Change source or Skip these pictures, then Generate again. Pictures that were fetched are kept."],
                                    unresolved=unresolved)
            media_map = {}
            for o in occs:
                n = str(o.scene_number)
                media_map[(o.line, o.part)] = got.paths.get(n) if n not in got.skipped else None
    except CsvError as exc:
        return PakmapResult(False, list(exc.problems))
    except Exception as exc:
        return PakmapResult(False, [f"could not get the pictures: {exc!r}"])
    try:
        res = compile_csv(csv_path, whisper_words, duration=duration, width=width, height=height, fps=fps, base_dir=base_dir, watermark=watermark, media_map=media_map, spec_extra=spec_extra)
        if not spec_extra:  # PakMap only: Hybrid Map renders through here too (with spec_extra) and keeps its own pacing
            apply_pacing(res, csv_path)  # the same card handoff as Check plan showed
    except CsvError as exc:
        return PakmapResult(False, list(exc.problems))
    except CompileError as exc:
        return PakmapResult(False, list(exc.report.errors), report=exc.report)
    except Exception as exc:
        return PakmapResult(False, [f"unexpected error while compiling the script: {exc!r}"])
    spec = res.spec
    pixel_scale = 2 if int(pixel_scale or 1) >= 2 else 1
    if pixel_scale > 1:
        spec["pixel_scale"] = pixel_scale
    for w in res.report.warnings:
        log(f"[pakMap] {w}")
    (work / "pakmap_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    (work / "pakmap_plan.txt").write_text(res.report.to_text(), encoding="utf-8")
    if cancelled():
        return PakmapResult(False, ["Cancelled"], report=res.report, cancelled=True)

    if render is None:
        from .engine_runner import render_spec as render
    from .engine_runner import PakmapRenderCancelled, PakmapRenderError

    silent = work / "pakmap_map.mp4"
    _report(progress_cb, "Drawing the map…", 0.08)

    def on_frame(done: int, total: int) -> None:
        _report(progress_cb, f"Drawing the map… frame {done}/{total}", 0.08 + 0.80 * (done / max(1, total)))

    try:
        outcome = render(spec, silent, progress=on_frame, cancel_check=cancel_check, log=log)
    except PakmapRenderCancelled:
        return PakmapResult(False, ["Cancelled"], report=res.report, cancelled=True)
    except PakmapRenderError as exc:
        return PakmapResult(False, [str(exc)], report=res.report)
    except Exception as exc:
        return PakmapResult(False, [f"unexpected error while drawing the map: {exc!r}"], report=res.report)
    if cancelled():
        return PakmapResult(False, ["Cancelled"], report=res.report, cancelled=True)

    # ---- Phase 7: pakMap's own sound design (narration + SFX + ambience; generic SFX/ambience/zoom-blur are not used) ----
    audio_plan, mix, narration_for_export, sound_notes, sound_failed = None, None, voiceover_path, [], None
    _report(progress_cb, "Designing the sound…" if sound_design else "Adding the narration…", 0.90)
    try:
        audio_plan = plan_pakmap_sound(res, enabled=sound_design, catalog=sound_catalog)
        (work / "pakmap_sound_plan.txt").write_text(audio_plan.to_text(), encoding="utf-8")
        for sid, what in sorted(audio_plan.missing.items()):
            sound_notes.append(f"missing sound {sid}: {what}")
        for sid, what in sorted(audio_plan.approximate.items()):
            log(f"[pakMap] sound {sid} is an approximation: {what}")
        if sound_design:
            from .audio_mix import mix_pakmap_audio

            mix = mix_pakmap_audio(audio_plan, voiceover_path, work / "pakmap_audio.wav", duration=spec["duration"])
            narration_for_export = mix.path
            log(f"[pakMap] sound design: {len(audio_plan.cues)} effect(s), {len(audio_plan.beds)} ambience bed(s)" + (f", {len(audio_plan.missing)} sound(s) missing" if audio_plan.missing else ""))
            if mix.changed and mix.bus_scale == 0.0:  # the mixer never turns the narration down, so a too-loud voice mutes the bed
                sound_failed = (f"the narration itself peaks above the mixer's limit ({mix.peak:.3f}), so the effects and ambience were turned "
                                "all the way down to keep it from clipping. Lower the voiceover's level slightly and Generate again")
                sound_notes.append(f"sound design is silent: {sound_failed}")
    except Exception as exc:  # the video is still made, with the narration alone, and the author is told (warnings and sound_failed)
        narration_for_export, mix = voiceover_path, None
        reason = str(exc) or f"{type(exc).__name__} (no message)"
        if isinstance(exc, MemoryError):
            reason = f"not enough memory to mix the sound ({type(exc).__name__}) {exc}".rstrip()
        sound_failed = reason
        sound_notes.append(f"sound design failed, so the video has the narration only: {reason}")
    for note in sound_notes:
        log(f"[pakMap] {note}")
    _report(progress_cb, "Adding the narration…", 0.92)
    try:
        from scene_graph.app_integration import _export_via_existing_renderer

        _export_via_existing_renderer(
            SimpleNamespace(duration=spec["duration"], title=title or csv_path.stem, segment_id="pakmap"), silent,
            voiceover_path=str(narration_for_export), output_path=output_path, resolution=f"{width * pixel_scale}x{height * pixel_scale}",
            fps=fps, work_dir=work,
        )
    except Exception as exc:
        return PakmapResult(False, [f"final export failed: {exc}"], report=res.report)
    if not output_path.is_file():
        return PakmapResult(False, ["final export did not produce an output file"], report=res.report)
    from scene_graph.app_integration import validate_rendered_output

    problem = validate_rendered_output(output_path, expected_duration_s=spec["duration"])
    if problem:
        return PakmapResult(False, [f"final video failed validation: {problem}"], report=res.report)

    sidecar = getattr(outcome, "sidecar", {}) or {}
    credits = list((sidecar.get("credits") or {}).get("attribution") or []) + list((sidecar.get("credits") or {}).get("notes") or [])
    renderer_notes = [w.get("message", str(w)) if isinstance(w, dict) else str(w) for w in sidecar.get("warnings", [])]
    try:
        output_path.with_name(output_path.stem + " - credits.txt").write_text(credits_text(credits, renderer_notes), encoding="utf-8")
    except OSError:
        pass
    _report(progress_cb, "Done.", 1.0)
    return PakmapResult(True, [], output_path, res.report, credits, res.report.warnings + sound_notes + renderer_notes, audio=audio_plan, audio_mix=mix,
                        sound_failed=sound_failed if sound_design else None)
