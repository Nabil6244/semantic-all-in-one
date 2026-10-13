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


def read_layers(project: WeatherProject) -> List[WxRow]:
    if not project.layers_csv.is_file():
        raise FileNotFoundError(f"{project.layers_csv} is missing (the weather layers of this video)")
    return parse_sidecar(project.layers_csv.read_text(encoding="utf-8"))


def fetch(project: WeatherProject, contact: str, *, now: Optional[datetime] = None, client: Optional[NwsClient] = None, **kw) -> Snapshot:
    """Prep: fetch every product the layers need, check it is fresh, and write resolved.json."""
    rows = read_layers(project)
    snap = prepare(rows, client or (NwsClient(contact) if contact else None), now=now, **kw)
    project.resolved_json.write_text(snap.to_json(), encoding="utf-8")
    return snap


def load_snapshot(project: WeatherProject) -> Snapshot:
    if not project.resolved_json.is_file():
        raise FileNotFoundError("there is no weather data for this project yet: fetch it first (python -m weather fetch, or Fetch data in the app)")
    return Snapshot.from_json(project.resolved_json.read_text(encoding="utf-8"))


def plan_layers(project: WeatherProject, words: Sequence, duration: float, *, now: Optional[datetime] = None,
                library_dir: "str | Path | None" = None, notes: Optional[List[str]] = None, edit_style: str = "classic"):
    """(plan, rows, snapshot, payload): everything checked, nothing rendered. Raises with messages that name the row.
    With `library_dir`, stock footage requests are swapped for matching clips of yours (weather.footage_library).
    `edit_style` "teamplate" applies Weather Teamplate's edit to the plan (weather.teamplate); the default leaves it as written."""
    from . import teamplate

    tp = teamplate.normalize(edit_style) == teamplate.KEY
    from hybrid.beat_csv import plan_from_csv

    if not project.beats_csv.is_file():
        raise FileNotFoundError(f"{project.beats_csv} is missing (the Hybrid beat CSV of this video)")
    beats_text = project.beats_csv.read_text(encoding="utf-8")
    if library_dir:
        from .footage_library import prefer_library
        from .teamplate.footage import prefer_library_strict

        beats_text, swapped = (prefer_library_strict if tp else prefer_library)(beats_text, library_dir)
        if notes is not None:
            notes += swapped
    plan = plan_from_csv(beats_text, list(words), duration)
    # a weather map must stay where the narration is: pakMap's always-on drift (0.5 % of the view a second) carried a 2-minute hold
    # from Houston to Mississippi. Idle beats still get Hybrid's slow push in. A plan that sets its own drift keeps it.
    plan.settings.setdefault("drift_pct_per_s", 0.0)
    rows = read_layers(project)
    snap = load_snapshot(project)
    check_fresh(snap, now or datetime.now(timezone.utc))
    windows = layer_windows(rows, plan, words)
    payload = build(rows, snap, windows)
    if tp:   # after the windows: the sidecar's rows keep naming the beats as written
        from .teamplate.cutaways import add_cutaways

        add_cutaways(plan, words, payload, notes)
        teamplate.apply_plan(plan, notes)
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
    bad = footage_problems(plan, project.root)
    if style == teamplate.KEY:
        from .teamplate.footage import relevance_problems

        bad += relevance_problems(plan)
    if bad:
        return PakmapResult(False, bad)
    if style == teamplate.KEY:
        log(f"[Weather] Editing style: {teamplate.NAME}")
    for n in snap.notes + lib_notes:
        log(f"[Weather] {n}")
    project.work_dir.mkdir(parents=True, exist_ok=True)
    report = payload.report.to_text()
    (project.work_dir / "weather_numbers.txt").write_text(report, encoding="utf-8")
    result = generate_hybrid_video(plan, voiceover_path, output_path, work_dir=project.work_dir, whisper_words=list(whisper_words),
                                   base_dir=str(project.root), render=make_render(payload, look=style), log=log, **kw)
    if result.ok:
        output_path.with_suffix(".numbers.txt").write_text(report, encoding="utf-8")
    return result

