"""The UI-independent entry points the app's What If mode calls (no Tk, like starmap.app_integration):

    plan_from(...)               narration (+ optional shot CSV) -> ShotPlan
    check_text(...)              the Check plan report
    visual_dicts(plan)           the shots' pictures and clips as rows for the EXISTING Visual Plan table
    generate_whatif_video(...)   voiceover + script (+ shot CSV) -> shots -> pictures -> render (whatif-engine) -> sound -> final MP4

Never raises past generate_whatif_video: failures come back as ok=False with messages written for the author (the same result
shape as pakMap's, Hybrid's and StarMap's, so the app's finish handling is shared)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import compile as wc
from . import media as wm
from . import planner
from .shot_csv import PlanError, is_whatif_csv, layers_from_rows, read_shots

ProgressCallback = Callable[[str, float], None]

# the references' music+ambience bed sits 13.8 / 15.3 / 18.9 dB under the voice (measured); StarMap's 0.2 gave 20.4 dB, so this is ~5 dB louder
MUSIC_GAIN = 0.36


def _report(cb: Optional[ProgressCallback], message: str, fraction: float) -> None:
    if cb is not None:
        try:
            cb(message, fraction)
        except Exception:
            pass


def plan_from(words: Sequence[Any], script: str, duration: float, title: str = "", csv_text: str = "", *, flow_video: "bool | str" = "both") -> planner.ShotPlan:
    """The shot plan: from the shot CSV as written when there is one, else built from the narration alone."""
    if csv_text and csv_text.strip() and is_whatif_csv(csv_text):
        shots, rows, info, notes = read_shots(csv_text, words, duration)
        layers, plates = layers_from_rows(rows, shots, words, script)
        p = planner.plan(words, script, duration, info.get("title") or title, shots=shots, extra_layers=layers, extra_plates=plates, auto=info.get("auto", True),
                         flow_video=flow_video)
        p.notes = notes + p.notes
        return p
    return planner.plan(words, script, duration, title, flow_video=flow_video)


def check_text(words: Sequence[Any], script: str, duration: float, title: str = "", csv_text: str = "", *, flow_video: "bool | str" = "both") -> "tuple[str, bool]":
    try:
        p = plan_from(words, script, duration, title, csv_text, flow_video=flow_video)
    except PlanError as exc:
        return "\n".join(f"ERROR {x}" for x in exc.problems), False
    except Exception as exc:
        return f"The plan could not be checked: {exc!r}", False
    rep = planner.report(p)
    lines = [f"{len(p.shots)} shots, median {rep['median_shot_s']} s, {rep['hard_cuts_per_min']} cuts/min, "
             f"{rep['visual_changes_per_min']} visual changes/min (longest gap {rep['max_gap_between_changes_s']} s), "
             f"diagram plates {int(rep['plate_share'] * 100)}% of the video"]
    if rep["cuts_inside_speech"]:
        lines.append(f"WARNING: {rep['cuts_inside_speech']} cut(s) land inside speech")
    lines += [f"note: {n}" for n in p.notes]
    span = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"      # noqa: E731
    for s in p.shots:
        what = s.model or s.texture or s.asset or s.title or ""
        lines.append(f"{s.id:<4}{span(s.start)}-{span(s.end)} ({s.length:4.1f}s) {s.kind.upper():<6} {what[:70]}")
    return "\n".join(lines), True


def visual_dicts(p: planner.ShotPlan) -> List[Dict[str, str]]:
    return wm.visual_dicts(p.shots)


def _at(segment: str) -> Optional[float]:
    import re

    m = re.match(r"\s*(\d+):(\d\d)", segment or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def remap_rows(plan_rows: Sequence[Dict[str, str]], saved: Sequence[Any], log: Callable[[str], None] = print) -> List[Any]:
    """The Visual Plan as the author left it, matched to THIS plan's rows by when they play, not by number. The plan is built from
    the script, and a script pasted differently moves a cut and renumbers every later row (145 shots one run, 144 the next): matched
    by number, every saved picture and every changed source landed one row off. A saved row takes the number of the plan row that
    plays at the same second (the nearest within 2 s, in order); a plan row with no saved row keeps its own."""
    import copy

    from providers.base import SceneRow

    pool = sorted(((_at(r.script_segment), i, r) for i, r in enumerate(saved) if _at(r.script_segment) is not None), key=lambda x: (x[0], x[1]))
    used, out, kept = set(), [], 0
    for d in plan_rows:
        t = _at(d.get("script_segment", ""))
        best = None
        if t is not None:
            for at, i, r in pool:
                if i in used or abs(at - t) > 2:
                    continue
                if best is None or abs(at - t) < abs(best[0] - t):
                    best = (at, i, r)
        if best is not None:
            used.add(best[1])
            r = copy.copy(best[2])
            r.scene_number, r.script_segment = str(d["scene_number"]), d.get("script_segment", r.script_segment)
            out.append(r)
            kept += 1
        else:
            out.append(SceneRow.from_csv_row(d))
    log(f"[What If] The shot list changed since the Visual Plan was listed (the script or a source changed): {kept} of {len(plan_rows)} "
        f"rows matched by their time in the video, so every saved picture and every source you set stays on its shot")
    return out


def generate_whatif_video(
    voiceover_path: "str | Path", output_path: "str | Path", *, work_dir: "str | Path", whisper_words: Sequence, images_dir: "str | Path",
    script: str = "", csv_path: "str | Path | None" = None, title: str = "", scene_rows: Optional[Sequence[Any]] = None,
    sound_design: bool = True, pixel_scale: int = 1, fps: int = 30, flow_video: "bool | str" = "both",
    progress_cb: Optional[ProgressCallback] = None, log: Callable[[str], None] = print, cancel_check: Optional[Callable[[], bool]] = None,
    media_callbacks: Optional[dict] = None, render: Optional[Callable[..., Any]] = None, fetch: Optional[Callable[..., Any]] = None,
    sound_catalog: Any = None, on_plan: Optional[Callable[[Any], None]] = None, **provider_kwargs: Any,
):
    from pakmap.app_integration import PakmapResult, credits_text, voiceover_duration

    voiceover_path, output_path = Path(voiceover_path), Path(output_path)
    cancelled = lambda: bool(cancel_check is not None and cancel_check())  # noqa: E731
    if not voiceover_path.is_file():
        return PakmapResult(False, [f"voiceover file not found: {voiceover_path}"])
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _report(progress_cb, "Planning the shots…", 0.03)
    duration = voiceover_duration(voiceover_path)
    csv_text = ""
    if csv_path and Path(csv_path).is_file():
        csv_text = Path(csv_path).read_text(encoding="utf-8")
    try:
        p = plan_from(whisper_words, script, duration, title, csv_text, flow_video=flow_video)
    except PlanError as exc:
        return PakmapResult(False, list(exc.problems))
    except Exception as exc:
        return PakmapResult(False, [f"could not plan the shots: {exc!r}"])
    for n in p.notes:
        log(f"[What If] {n}")
    rep = planner.report(p)
    log(f"[What If] plan: {rep}")
    if scene_rows:
        # the Visual Plan's rows are matched to this plan by number: rows listed for another plan (another Flow mode, another CSV)
        # would put pictures on the wrong shots, so they are set aside and this plan's own rows are used
        mine = {str(d["scene_number"]): d for d in visual_dicts(p)}
        theirs = {str(r.scene_number): r for r in scene_rows}
        same = set(mine) == set(theirs) and all(
            (mine[n]["prompt"] or "")[:40] in ((theirs[n].prompt or theirs[n].stock or "") + (theirs[n].prompt or ""))
            or theirs[n].asset_type in ("local", "local_video", "local_image") or not (mine[n]["prompt"] or "")
            for n in mine if (mine[n]["asset_type"] in ("flow_image", "flow_video")) == (theirs[n].asset_type in ("image", "video")))
        if not same:
            scene_rows = remap_rows(list(mine.values()), list(scene_rows), log)
    if on_plan is not None:            # the app shows the shots in the Visual Plan before the pictures are fetched
        try:
            on_plan(p)
        except Exception as exc:
            log(f"[What If] the plan could not be shown in the Visual Plan ({exc!r})")

    _report(progress_cb, "Getting the pictures and clips (NASA / Flow / stock)…", 0.08)
    got = None
    try:
        got = wm.fetch(p.shots, Path(images_dir), log=log, fetcher=fetch, scene_rows=scene_rows, cancel_check=cancel_check,
                       stills_dir=work / "stills", **(media_callbacks or {}), **provider_kwargs)
    except Exception as exc:       # a failed fetch never stops the video: those shots get their fallback
        log(f"[What If] fetching pictures failed ({exc!r}); the shots that needed them use their fallbacks")
    if cancelled():
        return PakmapResult(False, ["Cancelled"], cancelled=True)
    for n in getattr(got, "notes", []) or []:
        log(f"[What If] {n}")
    for s in p.shots:             # a row switched to Flow Video in the Visual Plan on a long shot: the planner could not split it
        if s.kind == "video" and s.file and s.length > planner.FLOW_VIDEO_MAX_S + 0.05 and s.asset.lower().startswith("flow_"):
            log(f"[What If] shot {s.id} is {s.length:.1f} s, longer than a Flow clip should run ({planner.FLOW_VIDEO_MAX_S:.0f} s): its clip loops. "
                f"Plan the shots again with Flow videos chosen to split it, or keep it a Flow Image in the Visual Plan.")

    media_dir = work / "render_media"
    if media_dir.exists():
        import shutil

        shutil.rmtree(media_dir, ignore_errors=True)
    scale = 2 if int(pixel_scale or 1) >= 2 else 1
    spec = wc.compile_spec(p, width=1920 * scale, height=1080 * scale, fps=fps, media_dir=media_dir, title=title)
    for n in spec["whatif"]["notes"]:
        if n not in p.notes:
            log(f"[What If] {n}")
    (work / "whatif_spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")

    if render is None:
        from .engine_runner import render_spec as render
    from .engine_runner import WhatifRenderCancelled, WhatifRenderError

    silent = work / "whatif_video.mp4"
    _report(progress_cb, "Drawing the shots…", 0.15)

    def on_frame(done: int, total: int) -> None:
        _report(progress_cb, f"Drawing the shots… frame {done}/{total}", 0.15 + 0.73 * (done / max(1, total)))

    outcome = None
    for attempt in (1, 2):         # a browser or GPU hiccup: once more (no paid call is involved in rendering)
        try:
            outcome = render(spec, silent, progress=on_frame, cancel_check=cancel_check, log=log)
            break
        except WhatifRenderCancelled:
            return PakmapResult(False, ["Cancelled"], cancelled=True)
        except Exception as exc:
            if attempt == 2 or cancelled():
                return PakmapResult(False, [str(exc) if isinstance(exc, WhatifRenderError) else f"unexpected error while drawing: {exc!r}"])
            log(f"[What If] the render stopped ({exc}); trying once more")
    if cancelled():
        return PakmapResult(False, ["Cancelled"], cancelled=True)

    audio_plan, mix, narration, sound_notes = None, None, voiceover_path, []
    music_credits: List[str] = []
    _report(progress_cb, "Designing the sound…" if sound_design else "Adding the narration…", 0.90)
    try:
        from .sound import plan_sound

        audio_plan = plan_sound(spec, enabled=sound_design, catalog=sound_catalog)
        for sid, what in sorted(audio_plan.missing.items()):
            sound_notes.append(f"missing sound {sid}: {what}")
        if sound_design:
            from pakmap.audio_mix import mix_pakmap_audio

            mix = mix_pakmap_audio(audio_plan, voiceover_path, work / "whatif_audio.wav", duration=spec["duration"])
            narration = mix.path
            try:
                from map_scene.render import _ffmpeg as _ff

                ff = _ff()
            except Exception:
                ff = "ffmpeg"
            from starmap.music import add_music

            with_music, music_credits = add_music(Path(narration), work / "whatif_audio_music.wav", spec["duration"], " ".join(s.text for s in p.shots),
                                                  seed=title or p.title, ffmpeg=ff, log=log, mood="ambient", gain=MUSIC_GAIN)
            if with_music:
                narration = with_music
    except Exception as exc:
        narration, mix = voiceover_path, None
        sound_notes.append(f"sound design failed, so the video has the narration only: {exc}")
    for note in sound_notes:
        log(f"[What If] {note}")

    # the references are all -14 LUFS integrated (loudness range ~4, true peak ~-1.5 dBFS): the final audio is set to that
    try:
        from map_scene.render import _ffmpeg as _ff2

        from .sound import measure_loudness, normalize_loudness

        ffm = _ff2()
        before = measure_loudness(narration, ffm)
        normalised = normalize_loudness(narration, work / "whatif_audio_final.wav", ffm)
        if normalised is not narration:
            after = measure_loudness(normalised, ffm)
            log(f"[What If] loudness {before['lufs']:.1f} LUFS -> {after['lufs']:.1f} LUFS (peak {after['peak']:.1f} dBFS, range {after['lra']:.1f} LU)")
            narration = normalised
    except Exception as exc:
        log(f"[What If] loudness normalisation skipped: {exc}")

    _report(progress_cb, "Adding the narration…", 0.93)
    try:
        from types import SimpleNamespace

        from scene_graph.app_integration import _export_via_existing_renderer, validate_rendered_output

        _export_via_existing_renderer(SimpleNamespace(duration=spec["duration"], title=title or "What If", segment_id="whatif"), silent,
                                      voiceover_path=str(narration), output_path=output_path, resolution=f"{spec['width']}x{spec['height']}", fps=fps, work_dir=work)
    except Exception as exc:
        return PakmapResult(False, [f"final export failed: {exc}"])
    if not output_path.is_file():
        return PakmapResult(False, ["final export did not produce an output file"])
    problem = validate_rendered_output(output_path, expected_duration_s=spec["duration"])
    if problem:
        return PakmapResult(False, [f"final video failed validation: {problem}"])
    credits = list(getattr(got, "credits", []) or []) + music_credits
    credits.append("3D models: NASA 3D Resources (public domain). Planet textures: NASA, Solar System Scope (CC BY 4.0). Fonts: Montserrat, Inter, JetBrains Mono (OFL).")
    try:
        output_path.with_name(output_path.stem + " - credits.txt").write_text(credits_text(credits, outcome.warnings), encoding="utf-8")
    except OSError:
        pass
    _report(progress_cb, "Done.", 1.0)
    return PakmapResult(True, [], output_path, None, credits, list(spec["whatif"]["notes"]) + sound_notes + list(outcome.warnings),
                        audio=audio_plan, audio_mix=mix, unresolved=list(getattr(got, "unresolved", []) or []))
