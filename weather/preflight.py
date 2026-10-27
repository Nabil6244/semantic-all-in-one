"""The dry run: everything Generate does before it fetches a clip or draws a frame, in seconds, and every reason it would stop.

    report = preflight(project, words, duration, edit_style="teamplate")
    report.ok        False when Generate would stop
    report.stops     [(stage, message), ...] every stop, not only the first
    report.notes     every repair autofix made on the way

The stages are the generator's own (weather.generate.generate_forecast_video -> hybrid.generate -> pakmap.app_integration ->
weather.render), run on the same functions, with no network, no stock / YouTube / Flow and no browser:

    plan      weather.generate.plan_layers         (beats.csv, the layers, the data snapshot)
    footage   fix_footage / fix_relevance / footage_problems
    hybrid    hybrid.compile.plan_to_rows          (the Hybrid plan's own checks)
    compile   pakmap.compile.compile_csv           (pakMap's compiler and its spec checks; the clips are left as written)
    engine    weather-engine/tools/validate_weather.mjs  (the checks the renderer starts with, on the final spec)

It is also the stress test's oracle (weather/stress.py, test_weather_never_stops.py): a plan that passes here does not stop Generate before the render."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class PreflightReport:
    stops: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    plan: Any = None        # what the stages built (for the app's Check plan: the Visual Plan table, the numbers report)
    rows: Any = None
    payload: Any = None

    @property
    def ok(self) -> bool:
        return not self.stops

    def stop(self, stage: str, messages) -> None:
        for m in ([messages] if isinstance(messages, str) else list(messages) or ["(no message)"]):
            self.stops.append((stage, str(m)))

    def to_text(self) -> str:
        lines = [f"Dry run: {'OK, Generate will not stop before the render' if self.ok else f'{len(self.stops)} problem(s) would stop Generate'}"]
        lines += [f"  STOP [{s}] {m}" for s, m in self.stops]
        if self.stats:
            lines.append("  " + ", ".join(f"{k} {v}" for k, v in self.stats.items()))
        lines += [f"  fixed: {n}" for n in self.notes]
        return "\n".join(lines)


def _node_check(spec: Dict[str, Any]) -> Dict[str, Any]:
    from map_scene.render import _node

    from .render import engine_dir

    with tempfile.TemporaryDirectory(prefix="wx_preflight_") as tmp:
        p = Path(tmp) / "spec.json"
        p.write_text(json.dumps(spec), encoding="utf-8")
        tool = engine_dir() / "tools" / "validate_weather.mjs"
        out = subprocess.run([_node(), str(tool), str(p)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return {"ok": False, "errors": [f"the renderer's checks could not run: {(out.stderr or out.stdout).strip()[-400:]}"]}
    return json.loads(out.stdout.strip().splitlines()[-1])


def preflight(project, words: Sequence, duration: float, *, edit_style: str = "classic", library_dir=None, now=None,
              voiceover_path=None, engine: bool = True) -> PreflightReport:
    """Every stage Generate runs before fetching or rendering. Never raises: an unexpected error is a stop too."""
    from . import teamplate
    from .generate import plan_layers

    rep = PreflightReport()
    style = teamplate.normalize(edit_style)
    # 1. the plan
    try:
        plan, rows, snap, payload = plan_layers(project, words, duration, now=now, library_dir=library_dir, notes=rep.notes,
                                                edit_style=edit_style)
    except Exception as exc:   # PlanError / SidecarError carry every problem
        rep.stop("plan", getattr(exc, "problems", None) or [f"{type(exc).__name__}: {exc}"])
        return rep
    rep.notes += list(snap.notes)
    rep.plan, rep.rows, rep.payload = plan, rows, payload
    # 2. the footage rules
    try:
        from .autofix import fix_footage
        from .footage import footage_problems

        fix_footage(plan, project.root, rep.notes)
        bad = footage_problems(plan, project.root)
        if style == teamplate.KEY:
            from .teamplate.footage import fix_relevance

            fix_relevance(plan, rep.notes)
        if bad:   # as Generate: left out, never a stop
            from .guard import drop_clips

            drop_clips(plan, bad, rep.notes)
    except Exception as exc:
        rep.stop("footage", f"{type(exc).__name__}: {exc}")
    try:   # the last repair before Hybrid's checks (weather.guard), as Generate runs it
        from .guard import make_safe

        make_safe(plan, rep.notes)
    except Exception as exc:
        rep.stop("guard", f"{type(exc).__name__}: {exc}")
    total = plan.duration or 1.0
    try:   # the storm-scene clips that Generate will look for on YouTube (weather.ytfill); the dry run itself never touches the network
        from .ytfill import enabled as yt_on, wanted as yt_wanted

        if yt_on(project) and yt_wanted(plan):
            rep.notes.append(f"YouTube news footage: {len(yt_wanted(plan))} storm-scene clip(s) will be searched on YouTube at Generate "
                             "(stock footage where nothing relevant is found)")
    except Exception:
        pass
    rep.stats.update(beats=len(plan.beats), clips=sum(len(b.clips) for b in plan.beats),
                     map_share=f"{sum(b.end - b.start for b in plan.beats if b.mode != 'footage') / total:.0%}")
    # 3. Hybrid's compile (its own plan checks)
    try:
        from hybrid.compile import HybridCompileError, plan_to_rows, rows_to_csv, spec_extra

        if voiceover_path:
            from hybrid.generate import fit_to_audio

            plan = fit_to_audio(plan, voiceover_path, log=lambda *_: None)
        try:
            hrows, _line_map, _hnotes = plan_to_rows(plan)
        except HybridCompileError as exc:
            rep.stop("hybrid", exc.problems)
            return rep
        csv_text = rows_to_csv(hrows)
        extra = spec_extra(plan)
    except Exception as exc:
        rep.stop("hybrid", f"{type(exc).__name__}: {exc}")
        return rep
    # 4. pakMap's compiler (as Generate calls it, before the clips are swapped in)
    try:
        from pakmap.compile import CompileError, compile_csv
        from pakmap.schema import CsvError

        try:
            res = compile_csv(text=csv_text, words=list(words) or [("hybrid", 0.0, 0.1)], duration=duration, width=1920, height=1080,
                              fps=30, base_dir=str(project.root), spec_extra=extra)
        except CsvError as exc:
            rep.stop("compile", exc.problems)
            return rep
        except CompileError as exc:
            rep.stop("compile", exc.report.errors)
            return rep
    except Exception as exc:
        rep.stop("compile", f"{type(exc).__name__}: {exc}")
        return rep
    # 5. the renderer's own first checks, on the final spec
    if engine:
        try:
            from .render import with_weather

            spec, part = res.spec, payload.spec_part()
            if style == teamplate.KEY:
                spec, part = teamplate.apply_spec(spec, part)
            out = _node_check(with_weather(spec, part, payload.fills))
            if not out.get("ok"):
                rep.stop("engine", out.get("errors") or ["the renderer's checks failed"])
            rep.notes += list(out.get("dropped") or [])
        except Exception as exc:
            rep.stop("engine", f"{type(exc).__name__}: {exc}")
    return rep
