"""A Weather Forecast video, end to end: a project folder -> fetch (prep) -> your voiceover -> the video.

A Weather project folder holds:
    beats.csv            the Hybrid beat CSV (read by hybrid.beat_csv, unchanged)
    weather_layers.csv   the weather layers (weather.sidecar)
    resolved.json        the data snapshot written by fetch (weather.resolve.Snapshot)
    _work/               render scratch (Hybrid's work files, the compiled spec)

fetch() reads the layers and freezes the data they need; generate_forecast_video() re-checks freshness, places the layers on
the narration and renders through Hybrid's own generator (hybrid.generate.generate_hybrid_video, imported unchanged) with
Weather's renderer passed in through its existing `render=` option. Next to the video: <video>.numbers.txt, every number on
screen with its source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

from .events import build
from .nws import NwsClient
from .resolve import Snapshot, check_fresh, prepare
from .sidecar import WxRow, parse_sidecar
from .timing import layer_windows


@dataclass(frozen=True)
class WeatherProject:
    root: Path

    @property
    def beats_csv(self) -> Path:
        return self.root / "beats.csv"

    @property
    def layers_csv(self) -> Path:
        return self.root / "weather_layers.csv"

    @property
    def resolved_json(self) -> Path:
        return self.root / "resolved.json"

    @property
    def work_dir(self) -> Path:
        return self.root / "_work"


def read_layers(project: WeatherProject, *, strict: bool = False, notes: Optional[List[str]] = None) -> List[WxRow]:
    """The weather rows; repaired the forgiving way (weather.autofix) unless `strict`."""
    if not project.layers_csv.is_file():
        raise FileNotFoundError(f"{project.layers_csv} is missing (the weather layers of this video)")
    text = project.layers_csv.read_text(encoding="utf-8")
    if strict:
        return parse_sidecar(text)
    from .autofix import repair_layers

    return repair_layers(text, notes if notes is not None else [])


def layer_rows(project: WeatherProject, *, strict: bool = False, notes: Optional[List[str]] = None, aliases=None) -> List[WxRow]:
    """The user's weather rows (weather_layers.csv) followed by the Weather Intelligence engine's (intel/auto_plan.json, ids auto_*).
    A project may have only the engine's rows (no weather_layers.csv: the engine found every graphic itself)."""
    from .intel.engine import load_auto_plan, merge_rows

    auto = load_auto_plan(project) is not None
    if not project.layers_csv.is_file():
        if not auto:
            if strict:
                raise FileNotFoundError(f"{project.layers_csv} is missing (the weather layers of this video)")
            if notes is not None:   # never a reason to stop: the video is made without weather graphics
                notes.append(f"there is no {project.layers_csv.name}: this video has no weather graphics (load a plan with them to add some)")
            return []
        return merge_rows(project, [], notes)
    text = project.layers_csv.read_text(encoding="utf-8")
    if strict:
        rows = parse_sidecar(text)
    else:
        from .autofix import repair_layers

        rows = repair_layers(text, notes if notes is not None else [], aliases)
    return merge_rows(project, rows, notes) if auto else rows


def fetch(project: WeatherProject, contact: str, *, now: Optional[datetime] = None, client: Optional[NwsClient] = None, **kw) -> Snapshot:
    """Prep: fetch every product the layers need and write resolved.json. Each graphic is fetched on its own: one that cannot be
    fetched (a server that does not answer, a blocked connection) is left out with the reason in snap.notes, and the others are
    kept, so one download never stops the video. Only when NOTHING could be fetched does this raise."""
    from .intel.engine import Net, acquire
    from .intel.evidence import Evidence

    rows = layer_rows(project)
    now = now or datetime.now(timezone.utc)
    net = Net(Evidence(), get_text=kw.get("get_text"), get_bytes=kw.get("get_bytes"), now=now)
    snap, failed = acquire(rows, net, contact=contact, now=now, nws_client=client or (NwsClient(contact) if contact else None),
                           gibs_get=kw.get("gibs_get"))
    wanted = [r for r in rows if r.data_source is not None]
    if wanted and len([r for r in wanted if r.id in failed]) == len(wanted):
        raise RuntimeError("none of the weather data could be fetched: " + "; ".join(f"{k}: {v}" for k, v in list(failed.items())[:3]))
    for rid, why in failed.items():
        snap.notes.append(f"weather graphic {rid} is left out of this video: its data could not be fetched ({why})")
    project.resolved_json.write_text(snap.to_json(), encoding="utf-8")
    return snap


def load_snapshot(project: WeatherProject) -> Snapshot:
    if not project.resolved_json.is_file():
        raise FileNotFoundError("there is no weather data for this project yet: fetch it first (python -m weather fetch, or Fetch data in the app)")
    return Snapshot.from_json(project.resolved_json.read_text(encoding="utf-8"))


def plan_layers(project: WeatherProject, words: Sequence, duration: float, *, now: Optional[datetime] = None,
                library_dir: "str | Path | None" = None, notes: Optional[List[str]] = None, edit_style: str = "classic",
                autofix: bool = True):
    """(plan, rows, snapshot, payload): everything checked, nothing rendered. Raises with messages that name the row.
    With `library_dir`, stock footage requests are swapped for matching clips of yours (weather.footage_library).
    `edit_style` "teamplate" applies Weather Teamplate's edit to the plan (weather.teamplate); the default leaves it as written.
    `autofix` (the default): small problems are repaired and described in `notes` (weather.autofix) instead of raised."""
    from . import teamplate

    tp = teamplate.normalize(edit_style) == teamplate.KEY
    if not project.beats_csv.is_file():
        from .intel.engine import load_auto_plan

        if load_auto_plan(project) is None:
            raise FileNotFoundError("Weather could not make a plan from your script and voiceover yet: Weather Intelligence has not run "
                                    "on this project (see the log for why). Make sure the script names the date and the state in its first "
                                    f"sentences and try again, or load a CSV plan ({project.beats_csv.name} is missing).")
        # no beat plan: Weather Intelligence made the beats from the narration (weather.intel.beats), the same way again here
        from .intel.engine import _script_text
        from .intel.beats import plan_from_narration, use_library

        fixes: List[str] = notes if notes is not None else []
        plan, aliases = plan_from_narration(words, duration, fixes, script=_script_text(project)), {}
        if library_dir:
            use_library(plan, library_dir, fixes, strict=tp)
    else:
        plan, aliases, fixes = _beat_plan(project, words, duration, notes, library_dir, tp, autofix)
    # a weather map must stay where the narration is: pakMap's always-on drift (0.5 % of the view a second) carried a 2-minute hold
    # from Houston to Mississippi. Idle beats still get Hybrid's slow push in. A plan that sets its own drift keeps it.
    plan.settings.setdefault("drift_pct_per_s", 0.0)
    return _finish_plan(project, plan, aliases, words, now, fixes, tp, autofix, notes)


def _beat_plan(project: WeatherProject, words, duration, notes, library_dir, tp: bool, autofix: bool):
    from hybrid.beat_csv import plan_from_csv

    beats_text = project.beats_csv.read_text(encoding="utf-8")
    if library_dir:
        from .footage_library import prefer_library
        from .teamplate.footage import prefer_library_strict

        beats_text, swapped = (prefer_library_strict if tp else prefer_library)(beats_text, library_dir)
        if notes is not None:
            notes += swapped
    fixes: List[str] = notes if notes is not None else []
    if autofix:
        from .autofix import repair_beats

        plan, aliases = repair_beats(beats_text, words, duration, fixes)
    else:
        plan, aliases = plan_from_csv(beats_text, list(words), duration), {}
    return plan, aliases, fixes


def _finish_plan(project: WeatherProject, plan, aliases, words, now, fixes: List[str], tp: bool, autofix: bool, notes):
    from . import teamplate

    if autofix:
        from . import autofix as fix

        rows = layer_rows(project, notes=fixes, aliases=aliases)
    else:
        rows = layer_rows(project, strict=True)
    if autofix and not project.resolved_json.is_file():
        snap = Snapshot(prepared=(now or datetime.now(timezone.utc)).isoformat())   # no data fetched: the data graphics are left out
        fixes.append("no weather data has been fetched for this project: the graphics that need data are left out (Fetch data to add them)")
    else:
        snap = load_snapshot(project)
    if autofix:
        from .resolve import prune_stale

        prune_stale(snap, now or datetime.now(timezone.utc), fixes)   # data too old to show is left out, never a reason to stop
    check_fresh(snap, now or datetime.now(timezone.utc))
    if autofix:
        rows, windows = fix.windows(rows, plan, words, fixes)
        rows, payload = fix.build(rows, snap, windows, fixes)
    else:
        windows = layer_windows(rows, plan, words)
        payload = build(rows, snap, windows)
    if tp:   # after the windows: the sidecar's rows keep naming the beats as written
        from .teamplate.cutaways import add_cutaways

        add_cutaways(plan, words, payload, notes)
        teamplate.apply_plan(plan, notes)
    # after the cutaways (which already break up long maps in Weather Teamplate): what is still a still map gets slow motion
    from .motion import keep_map_under, keep_moving, vary_repeats

    keep_map_under(plan, words, payload, fixes)   # the map at most half the video (both Weather styles)
    vary_repeats(plan, fixes)                      # no stock clip shown twice
    keep_moving(plan, fixes)
    if autofix:   # the last repair: whatever Hybrid's own checks would still stop on is repaired (weather.guard)
        from .guard import make_safe

        make_safe(plan, fixes)
    return plan, rows, snap, payload


def generate_forecast_video(project: WeatherProject, voiceover_path: "str | Path", output_path: "str | Path", *, whisper_words: Sequence,
                            now: Optional[datetime] = None, log: Callable[[str], None] = print, library_dir: "str | Path | None" = None,
                            edit_style: str = "classic", **kw: Any):
    """`kw` goes to hybrid.generate.generate_hybrid_video (sound_design, watermark, progress_cb, cancel_check, media options ...).
    `edit_style`: "classic" (the Weather style) or "teamplate" (Weather Teamplate, weather.teamplate).
    Returns pakMap's PakmapResult; never raises for a problem in the plan or the data (ok=False with the messages)."""
    from . import teamplate
    from hybrid.generate import generate_hybrid_video
    from hybrid.plan import PlanError
    from pakmap.app_integration import PakmapResult, voiceover_duration

    from .render import make_render
    from .resolve import StaleDataError
    from .sidecar import SidecarError

    output_path = Path(output_path)
    try:
        duration = voiceover_duration(Path(voiceover_path))
        lib_notes: List[str] = []
        plan, rows, snap, payload = plan_layers(project, whisper_words, duration, now=now, library_dir=library_dir, notes=lib_notes,
                                                edit_style=edit_style)
    except (PlanError, SidecarError) as exc:
        return PakmapResult(False, list(exc.problems))
    except (StaleDataError, FileNotFoundError, ValueError, KeyError) as exc:
        return PakmapResult(False, [str(exc)])
    from .footage import footage_problems

    style = teamplate.normalize(edit_style)
    from .autofix import fix_footage

    fix_footage(plan, project.root, lib_notes)   # a source Weather never uses becomes a stock request, never a reason to stop
    bad = footage_problems(plan, project.root)
    if style == teamplate.KEY:
        from .teamplate.footage import fix_relevance

        fix_relevance(plan, lib_notes)   # footage that does not match its beat is re-asked for, never a reason to stop
    if bad:   # a clip Weather may not use that autofix could not turn into stock footage: left out, never a reason to stop
        from .guard import drop_clips, make_safe

        drop_clips(plan, bad, lib_notes)
        make_safe(plan, lib_notes)
    if style == teamplate.KEY:
        log(f"[Weather] Editing style: {teamplate.NAME}")
    for n in snap.notes + lib_notes:
        log(f"[Weather] {n}")
    from .selfcheck import checks

    for ok, line in checks(plan, payload):
        log(f"[Weather] check: {'ok' if ok else 'WARNING'} — {line}")
    project.work_dir.mkdir(parents=True, exist_ok=True)
    report = payload.report.to_text()
    (project.work_dir / "weather_numbers.txt").write_text(report, encoding="utf-8")
    if kw.get("media_resolver") is None:   # every stock clip is checked for where it was filmed and what it shows (weather.footage_geo)
        from .footage_geo import make_resolver

        kw["media_resolver"] = make_resolver(log)
    result = generate_hybrid_video(plan, voiceover_path, output_path, work_dir=project.work_dir, whisper_words=list(whisper_words),
                                   base_dir=str(project.root), render=make_render(payload, look=style), log=log, **kw)
    if not result.ok and result.unresolved and not result.cancelled and (project.work_dir / "hybrid_script.csv").is_file():
        # some clips could not be found: the video is made without them (the clips that were found are reused, not fetched again)
        from .guard import drop_unfound, make_safe

        again: List[str] = []
        if drop_unfound(plan, project.work_dir / "hybrid_script.csv", result.unresolved, again):
            make_safe(plan, again, new_requests=False)
            for n in again:
                log(f"[Weather] {n}")
            rest = {k: v for k, v in kw.items() if k != "scene_rows"}   # the clips are numbered again from the new script
            result = generate_hybrid_video(plan, voiceover_path, output_path, work_dir=project.work_dir, whisper_words=list(whisper_words),
                                           base_dir=str(project.root), render=make_render(payload, look=style), log=log, **rest)
    if result.ok and not getattr(result, "media_ready", 0):   # media_only: the clips are fetched, nothing was drawn yet
        output_path.with_suffix(".numbers.txt").write_text(report, encoding="utf-8")
    return result

