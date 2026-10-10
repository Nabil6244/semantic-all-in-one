"""The UI-independent entry points the app's StarMap mode calls (no Tk, like hybrid.app_integration):

    load_plan(...)              a beat CSV read against the narration (raises PlanError naming the rows)
    visual_dicts(plan)          the plan's pictures and clips as rows for the EXISTING Visual Plan table
    check_text(...)             the Check plan report (text, ok)
    generate_starmap_video(...) beat CSV + voiceover -> pictures -> compile -> render (starmap-engine) -> sound -> final MP4

Never raises past generate_starmap_video: failures come back as ok=False with messages written for the author (the same result
shape as pakMap's and Hybrid's, so the app's finish handling is shared)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .beat_csv import Plan, PlanError, read_plan
from .catalog import Catalog, CatalogError
from .check import check_csv
from .compile import CompileError, compile_plan, strip_private

ProgressCallback = Callable[[str, float], None]


def share_missing_clip_time(footage: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The footage entries that have a file. A footage beat that lost a clip (no picture found, or skipped) gives its time
    to the clips it still has -- they share the beat's whole stretch in order -- so the map is not left frozen in the gap.
    A beat with no clip at all is unchanged (its time goes to the map, as before)."""
    beats: Dict[str, List[Dict[str, Any]]] = {}
    for f in footage:
        beats.setdefault(str(f.get("id", "")).rsplit("_", 1)[0], []).append(f)
    out: List[Dict[str, Any]] = []
    for fs in beats.values():
        fs = sorted(fs, key=lambda f: f["start"])
        have = [f for f in fs if f.get("file") or f.get("image")]
        if have and len(have) < len(fs):
            a, b = fs[0]["start"], fs[-1]["end"]
            step = (b - a) / len(have)
            for i, f in enumerate(have):
                f["start"], f["end"] = round(a + i * step, 3), round(a + (i + 1) * step, 3)
        out += have
    return sorted(out, key=lambda f: f["start"])


def _report(cb: Optional[ProgressCallback], message: str, fraction: float) -> None:
    if cb is not None:
        try:
            cb(message, fraction)
        except Exception:
            pass


def load_plan(csv_text: str, words: Sequence = (), duration: Optional[float] = None) -> Plan:
    return read_plan(csv_text, words, duration)


def visual_dicts(plan: Plan) -> List[Dict[str, str]]:
    from .media import visual_dicts as _vd

    return _vd(plan)


def visual_dicts_from_csv(csv_text: str) -> List[Dict[str, str]]:
    """The Visual Plan rows straight from the CSV (instant, no narration needed; numbered like the plan's)."""
    from .media import media_rows_from_csv

    return [m.as_dict() for m in media_rows_from_csv(csv_text)]


def summary(csv_text: str) -> str:
    """What a just-loaded CSV holds, before it is timed against the narration."""
    import csv
    import io
    from collections import Counter

    rows = list(csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff"))))
    beats = [r for r in rows if (r.get("row") or "").lower() == "beat"]
    modes = Counter((r.get("mode") or "?").lower() for r in beats)
    kinds = Counter((r.get("type") or "?").lower() for r in rows if (r.get("row") or "").lower() == "layer")
    lines = [f"{len(beats)} beats: " + ", ".join(f"{n} {m}" for m, n in sorted(modes.items()))]
    if kinds:
        lines.append("layers: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))
    media = visual_dicts_from_csv(csv_text)
    lines.append(f"{len(media)} picture(s) and clip(s) for the Visual Plan")
    lines.append("Missions, spacecraft and their dates are found from the CSV when you click Check plan (nothing to select).")
    return "\n".join(lines)


def check_text(csv_text: str, words: Sequence = (), duration: Optional[float] = None, *, pack: Optional[str] = None,
               scene_status: Optional[Dict[str, str]] = None, reference_now: Optional[str] = None) -> "tuple[str, bool]":
    """The Check plan view: the summary, the datasets found, every problem by row, the plan beat by beat, and the pictures
    still to find. `reference_now` is the project's saved "now" (the plan row's date wins)."""
    try:
        rep = check_csv(csv_text, words, duration, pack=pack, reference_now=reference_now)
    except Exception as exc:   # never escape into the UI thread
        return f"The plan could not be checked: {exc!r}", False
    lines = [rep.to_text()]
    if rep.plan is not None:
        lines.append("")
        lines += plan_lines(rep.plan, scene_status=scene_status)
    return "\n".join(lines), rep.ok


def plan_lines(plan: Plan, *, scene_status: Optional[Dict[str, str]] = None) -> List[str]:
    from .media import media_rows

    span = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"  # noqa: E731
    scene_of = {}
    for m in media_rows(plan):
        scene_of.setdefault(m.beat, []).append(m.scene_number)
    out = []
    for i, b in enumerate(plan.beats, 1):
        head = f"#{i:<2} {span(b.start)}-{span(b.end)} ({b.end - b.start:4.1f}s)  {b.mode.upper():<11}"
        view = f"{b.place} ({b.frame}{', ' + b.move if b.move else ''})" if b.mode != "footage" else ""
        out.append(f"{head} {view}" + (f"  date {b.date}" if b.date else ""))
        if b.why:
            out.append(f"      why: {b.why}")
        if b.layers:
            out.append("      layers: " + ", ".join(f"{L.type} {L.id or L.label or L.place or L.text}".strip() + f" @{span(L.t or b.start)}" for L in b.layers))
        for c in b.cards:
            out.append(f"      card: {c.asset}" + (f"  — {c.label}" if c.label else ""))
        for c in b.clips:
            out.append(f"      clip: {c.asset}" + (f"  — {c.why}" if c.why else ""))
        for n in scene_of.get(b.id, []):
            st = (scene_status or {}).get(n)
            out.append(f"      Visual Plan scene {n}" + (f": {st}" if st else ""))
    return out


BASIS_WORDS = {
    "observed": "trajectory from observed data (telemetry / ephemeris samples)",
    "modelled": "trajectory modelled from the published plan and orbits",
    "illustrated": "flight paths are illustrated from the mission's published times and orbits, not flight data",
    "illustrative": "illustrative geometry made for the story, not a real trajectory",
}


def dataset_credits(cat: Catalog, res: Any) -> List[str]:
    """One line per dataset the video draws on: what it is, how certain, how its geometry is known, its source and date."""
    out = []
    for did in res.used:
        ds = cat.index.datasets[did]
        statuses = sorted({c.status for c in res.contexts.values() if did in c.datasets and c.status}) or [ds.status]
        bases = sorted({b for c in res.contexts.values() if did in c.datasets for b in c.basis}) or sorted({t.basis for t in ds.trajectories.values()})
        parts = [f"{ds.name}: " + "/".join(statuses)]
        parts += [BASIS_WORDS[b] for b in bases]
        for t in ds.trajectories.values():
            if t.observed_until:
                parts.append(f"observed through {t.observed_until[:10]}" + (f"; positions after that are estimated by linear extrapolation"
                                                                         if t.extrapolate else ""))
        if ds.source:
            parts.append(f"source: {ds.source}")
        if ds.as_of:
            parts.append(f"as of {ds.as_of[:10]}")
        if "planned" in statuses:
            parts.append("a plan, not a completed mission; dates marked NET are no-earlier-than")
        if "hypothetical" in statuses:
            parts.append("a hypothetical scenario, not a real mission")
        out.append("; ".join(parts))
    if res.reference_now:
        out.append(f"\"Now\" in this video means {res.reference_now[:10]} (the project's reference date)")
    return out


def gather_media(spec: Dict[str, Any], folder: Path) -> Path:
    """Every picture and clip the spec uses, in ONE folder the renderer serves (hard links where possible, so nothing is copied
    twice on disk); the spec then names them by file name."""
    import os
    import shutil

    folder = Path(folder)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    names: Dict[str, str] = {}

    def place(src: str) -> str:
        if not src:
            return src
        p = Path(src).resolve()
        if str(p) not in names:
            name = f"{len(names) + 1:03d}_{p.name}"
            try:
                os.link(p, folder / name)
            except OSError:
                shutil.copy2(p, folder / name)
            names[str(p)] = name
        return names[str(p)]

    for L in spec.get("layers", []):
        if L.get("type") == "photo_card":
            for k in ("image", "video"):
                if L.get(k):
                    L[k] = place(L[k])
    for f in spec.get("footage", []):
        for k in ("file", "image"):
            if f.get(k):
                f[k] = place(f[k])
    return folder


def generate_starmap_video(
    csv_path: "str | Path", voiceover_path: "str | Path", output_path: "str | Path", *, work_dir: "str | Path",
    whisper_words: Sequence, images_dir: "str | Path", scene_rows: Optional[Sequence[Any]] = None, pack: Optional[str] = None,
    reference_now: Optional[str] = None,
    watermark: Optional[dict] = None, title: str = "", sound_design: bool = True, pixel_scale: int = 1, fps: int = 30,
    progress_cb: Optional[ProgressCallback] = None, log: Callable[[str], None] = print, cancel_check: Optional[Callable[[], bool]] = None,
    media_callbacks: Optional[dict] = None, render: Optional[Callable[..., Any]] = None, fetch: Optional[Callable[..., Any]] = None,
    sound_catalog: Any = None, **provider_kwargs: Any,
):
    """`provider_kwargs` go to the shared media resolver (pexels_api_key, flow_engine_manager, flow_settings, flow_video_account_ids,
    youtube_clip_duration ...). `render` / `fetch` are injectable for tests. Datasets are found from the CSV (`pack` is only an
    optional starting context for old callers); `reference_now` is the project's saved "now" (the plan row's date wins)."""
    from pakmap.app_integration import PakmapResult, credits_text, voiceover_duration

    csv_path, voiceover_path, output_path = Path(csv_path), Path(voiceover_path), Path(output_path)
    cancelled = lambda: bool(cancel_check is not None and cancel_check())  # noqa: E731
    if not csv_path.is_file():
        return PakmapResult(False, [f"StarMap beat CSV not found: {csv_path}"])
    if not voiceover_path.is_file():
        return PakmapResult(False, [f"voiceover file not found: {voiceover_path}"])
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _report(progress_cb, "Reading the StarMap plan…", 0.02)
    duration = voiceover_duration(voiceover_path)
    try:
        plan = read_plan(csv_path.read_text(encoding="utf-8"), whisper_words, duration)
        if pack and not plan.pack:
            plan.pack = pack
        cat = Catalog()
    except PlanError as exc:
        return PakmapResult(False, list(exc.problems))
    except CatalogError as exc:
        return PakmapResult(False, [str(exc)])
    except Exception as exc:
        return PakmapResult(False, [f"could not read the plan: {exc!r}"])
    if duration:
        plan.duration = duration            # the video ends with the narration
        if plan.beats and plan.beats[-1].end > duration:
            plan.beats[-1].end = max(plan.beats[-1].start + 0.5, duration)
    for n in plan.notes:
        log(f"[StarMap] {n}")
    from .resolve import resolve

    res = resolve(plan, cat, reference_now=plan.reference_now or reference_now)
    if res.errors:
        return PakmapResult(False, list(res.errors))
    for line in res.detected(cat):
        log(f"[StarMap] dataset:{line}")
    # NASA picture search: each row is matched against its own beat's mission (Apollo 8's photo, not Apollo 11's)
    from .media import media_rows

    mission_of = {}
    for m in media_rows(plan):
        c = res.contexts.get(m.beat)
        if c is None:                                    # a footage beat: the mission of the map beat before it
            prev = [b for b in plan.beats[:[x.id for x in plan.beats].index(m.beat)] if b.id in res.contexts]
            c = res.contexts[prev[-1].id] if prev else None
        if c is not None and len(c.datasets) == 1:
            mission_of[m.scene_number] = cat.index.datasets[c.datasets[0]].name

    _report(progress_cb, "Getting the pictures and clips (NASA / stock / Flow)…", 0.05)
    try:
        from .media import fetch_media

        got = (fetch or fetch_media)(plan, Path(images_dir), scene_rows=scene_rows, log=log, cancel_check=cancel_check,
                                     stills_dir=work / "stills", mission=mission_of, **(media_callbacks or {}), **provider_kwargs)
    except Exception as exc:
        return PakmapResult(False, [f"could not get the pictures and clips: {exc!r}"])
    if cancelled():
        return PakmapResult(False, ["Cancelled"], cancelled=True)
    if got.missing:
        return PakmapResult(False, got.missing + ["Open the Visual Plan tab to Retry, Change source or Skip these, then Generate again. "
                                                  "Pictures and clips already found are kept."], unresolved=list(got.unresolved))

    # the author's own files (file:<name>) sit next to the CSV
    media = dict(got.media)
    for n in getattr(got, "notes", []):
        log(f"[StarMap] {n}")
    for b in plan.beats:
        for it in b.cards + b.clips:
            if it.asset.lower().startswith("file:"):
                f = Path(it.asset[5:].strip())
                f = f if f.is_absolute() else csv_path.parent / f
                if not f.is_file():
                    return PakmapResult(False, [f"row {it.row}: file {f} not found (file: names a file next to the CSV)"])
                media[f"row:{it.row}"] = {"file": str(f)}
    scale = 2 if int(pixel_scale or 1) >= 2 else 1
    try:
        comp = compile_plan(plan, cat, media=media, width=1920 * scale, height=1080 * scale, fps=fps, watermark=watermark, resolution=res)
    except CompileError as exc:
        return PakmapResult(False, list(exc.problems))
    except Exception as exc:
        return PakmapResult(False, [f"unexpected error while compiling the plan: {exc!r}"])
    # skipped pictures: a card without a file is left out, a clip without one leaves its time to the map
    spec = strip_private(comp.spec)
    spec["layers"] = [L for L in spec["layers"] if not (L["type"] == "photo_card" and not (L.get("image") or L.get("video")))]
    spec["footage"] = share_missing_clip_time(spec["footage"])
    spec["media_dir"] = str(gather_media(spec, work / "render_media"))
    # chunks drawn before are reused when nothing that shows in them changed (an edit redraws only the seconds it touches)
    spec["segment_cache"] = str(work / "render_chunks")
    if title:
        spec.setdefault("starmap", {})["title"] = title
    (work / "starmap_spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    for n in comp.notes:
        log(f"[StarMap] {n}")
    if cancelled():
        return PakmapResult(False, ["Cancelled"], cancelled=True)

    if render is None:
        from .engine_runner import render_spec as render
    from .engine_runner import StarmapRenderCancelled, StarmapRenderError

    silent = work / "starmap_video.mp4"
    _report(progress_cb, "Drawing space…", 0.10)

    def on_frame(done: int, total: int) -> None:
        _report(progress_cb, f"Drawing space… frame {done}/{total}", 0.10 + 0.78 * (done / max(1, total)))

    try:
        outcome = render(spec, silent, progress=on_frame, cancel_check=cancel_check, log=log)
    except StarmapRenderCancelled:
        return PakmapResult(False, ["Cancelled"], cancelled=True)
    except StarmapRenderError as exc:
        return PakmapResult(False, [str(exc)])
    except Exception as exc:
        return PakmapResult(False, [f"unexpected error while drawing space: {exc!r}"])
    if cancelled():
        return PakmapResult(False, ["Cancelled"], cancelled=True)

    audio_plan, mix, narration, sound_notes = None, None, voiceover_path, []
    # render QC: a report only (frozen stretches, near-black footage), never a change to the video
    if silent.is_file():
        try:
            from .qc import check_render

            for q in check_render(silent, spec, plan.beats):
                sound_notes.append(q.text())
        except Exception as exc:
            log(f"[StarMap] render QC skipped: {exc}")
    _report(progress_cb, "Designing the sound…" if sound_design else "Adding the narration…", 0.90)
    try:
        from .sound import plan_sound

        audio_plan = plan_sound(spec, enabled=sound_design, catalog=sound_catalog)
        (work / "starmap_sound_plan.txt").write_text(audio_plan.to_text(), encoding="utf-8")
        for sid, what in sorted(audio_plan.missing.items()):
            sound_notes.append(f"missing sound {sid}: {what}")
        if sound_design:
            from pakmap.audio_mix import mix_pakmap_audio

            mix = mix_pakmap_audio(audio_plan, voiceover_path, work / "starmap_audio.wav", duration=spec["duration"])
            narration = mix.path
            log(f"[StarMap] sound design: {len(audio_plan.cues)} effect(s), {len(audio_plan.beds)} ambience bed(s)")
    except Exception as exc:     # the video is still made, with the narration alone, and the author is told
        narration, mix = voiceover_path, None
        sound_notes.append(f"sound design failed, so the video has the narration only: {exc}")
    for note in sound_notes:
        log(f"[StarMap] {note}")

    _report(progress_cb, "Adding the narration…", 0.93)
    try:
        from types import SimpleNamespace

        from scene_graph.app_integration import _export_via_existing_renderer, validate_rendered_output

        _export_via_existing_renderer(
            SimpleNamespace(duration=spec["duration"], title=title or csv_path.stem, segment_id="starmap"), silent,
            voiceover_path=str(narration), output_path=output_path, resolution=f"{spec['width']}x{spec['height']}", fps=fps, work_dir=work,
        )
    except Exception as exc:
        return PakmapResult(False, [f"final export failed: {exc}"])
    if not output_path.is_file():
        return PakmapResult(False, ["final export did not produce an output file"])
    problem = validate_rendered_output(output_path, expected_duration_s=spec["duration"])
    if problem:
        return PakmapResult(False, [f"final video failed validation: {problem}"])

    credits = list(got.credits) + dataset_credits(cat, res)
    credits.append("Star positions: Yale Bright Star Catalogue (via CDS). Planet positions: astronomy-engine (MIT). Textures: NASA, NASA/JPL-Caltech, Solar System Scope (CC BY 4.0)")
    try:
        output_path.with_name(output_path.stem + " - credits.txt").write_text(credits_text(credits, outcome.warnings), encoding="utf-8")
    except OSError:
        pass
    _report(progress_cb, "Done.", 1.0)
    return PakmapResult(True, [], output_path, None, credits, list(getattr(got, "notes", [])) + comp.notes + sound_notes + list(outcome.warnings), audio=audio_plan, audio_mix=mix)
