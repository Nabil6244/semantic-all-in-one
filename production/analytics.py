"""Production analytics, computed from real production events (production.events) and the existing state files.

Nothing here keeps its own counters: run the same function on the same event log and you get the same numbers.

  summarize(events, ...)      -> ProductionReport (project, assets, providers, queue, rendering, regeneration, AI)
  project_report(workspace)   -> the report for one project folder
  format_report(report)       -> the plain-text block the UI and the log show
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import events as _events

# Rough per-call figures used only to express "avoided" AI calls as time; clearly labelled as estimates in the UI.
EST_AI_CALL_S = 25.0
# Caches whose hit means an AI call that did not have to be made.
AI_CACHES = ("ai", "editorial_ai", "script_analysis", "map_place")


@dataclass
class ProductionReport:
    project: Dict[str, Any] = field(default_factory=dict)
    assets: Dict[str, Any] = field(default_factory=dict)
    providers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    queue: Dict[str, Any] = field(default_factory=dict)
    rendering: Dict[str, Any] = field(default_factory=dict)
    regeneration: Dict[str, Any] = field(default_factory=dict)
    ai: Dict[str, Any] = field(default_factory=dict)
    caches: Dict[str, Dict[str, int]] = field(default_factory=dict)
    recovery: Dict[str, int] = field(default_factory=dict)
    runs: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _rate(n: int, d: int) -> Optional[float]:
    return round(n / d, 3) if d else None


def _mean(values: List[float]) -> Optional[float]:
    return round(statistics.fmean(values), 2) if values else None


def summarize(evts: Iterable[dict], *, scenes: Optional[int] = None, duration_s: Optional[float] = None,
              last_run_only: bool = False) -> ProductionReport:
    evts = [e for e in evts if isinstance(e, dict)]
    if last_run_only:
        runs = [e.get("run") for e in evts if e.get("kind") == "run_start" and e.get("run")]
        if runs:
            evts = [e for e in evts if e.get("run") == runs[-1]]
    r = ProductionReport()
    run_ends = [e for e in evts if e.get("kind") == "run_end"]
    r.runs = len(run_ends)
    r.project = {
        "scenes": scenes,
        "video_duration_s": round(duration_s, 1) if duration_s else None,
        "production_s": round(sum(float(e.get("duration_s") or 0) for e in run_ends), 1),
        "runs_ok": sum(1 for e in run_ends if e.get("outcome") == "ok"),
        "runs_failed": sum(1 for e in run_ends if e.get("outcome") == "error"),
        "runs_cancelled": sum(1 for e in run_ends if e.get("outcome") == "cancelled"),
    }

    # ---- assets
    outcomes: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    for e in (e for e in evts if e.get("kind") == "asset"):
        o = str(e.get("outcome") or "unknown")
        outcomes[o] = outcomes.get(o, 0) + 1
        if o in ("generated", "reused", "replaced"):
            s = str(e.get("source") or "unknown")
            by_source[s] = by_source.get(s, 0) + 1
    produced = outcomes.get("generated", 0) + outcomes.get("replaced", 0)
    r.assets = {
        "generated": outcomes.get("generated", 0),
        "reused": outcomes.get("reused", 0),
        "failed": outcomes.get("failed", 0),
        "replaced": outcomes.get("replaced", 0),
        "skipped": outcomes.get("skipped", 0),
        "source_mix": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        "reuse_rate": _rate(outcomes.get("reused", 0), outcomes.get("reused", 0) + produced),
    }

    # ---- providers (asset jobs by source) and queue
    jobs = [e for e in evts if e.get("kind") == "job"]
    prov: Dict[str, Dict[str, Any]] = {}
    for e in (j for j in jobs if j.get("type") == "asset"):
        s = str(e.get("source") or "unknown")
        p = prov.setdefault(s, {"ok": 0, "failed": 0, "retries": 0, "_d": []})
        if e.get("state") == "completed":
            p["ok"] += 1
            p["_d"].append(float(e.get("exec_s") or 0))
        elif e.get("state") == "failed":
            p["failed"] += 1
        p["retries"] += max(0, int(e.get("attempt") or 1) - 1)
    for s, p in prov.items():
        d = p.pop("_d")
        p["avg_s"] = _mean(d)
        p["success_rate"] = _rate(p["ok"], p["ok"] + p["failed"])
    r.providers = dict(sorted(prov.items()))
    waits = [float(j.get("wait_s") or 0) for j in jobs if j.get("state") in ("completed", "failed")]
    execs = [float(j.get("exec_s") or 0) for j in jobs if j.get("state") in ("completed", "failed")]
    r.queue = {
        "jobs": len(jobs),
        "completed": sum(1 for j in jobs if j.get("state") == "completed"),
        "failed": sum(1 for j in jobs if j.get("state") == "failed"),
        "cancelled": sum(1 for j in jobs if j.get("state") == "cancelled"),
        "retries": sum(max(0, int(j.get("attempt") or 1) - 1) for j in jobs),
        "avg_wait_s": _mean(waits),
        "avg_exec_s": _mean(execs),
        "failures_by_class": _count(j.get("error_class") or "unknown" for j in jobs if j.get("state") == "failed"),
    }

    # ---- rendering
    renders = [e for e in evts if e.get("kind") == "render"]
    if renders:
        last = renders[-1]
        reused = sum(int(e.get("clips_reused") or 0) for e in renders)
        rendered = sum(int(e.get("clips_rendered") or 0) for e in renders)
        r.rendering = {
            "renders": len(renders),
            "last_duration_s": last.get("duration_s"),
            "last_frames": last.get("frames"),
            "last_fps": last.get("fps"),
            "last_speed_x": last.get("speed_x"),
            "avg_duration_s": _mean([float(e.get("duration_s") or 0) for e in renders]),
            "clips_reused": reused,
            "clips_rendered": rendered,
            "rerender_rate": _rate(rendered, reused + rendered),
            "failed_segments": sum(int(e.get("failed_segments") or 0) for e in renders),
        }

    # ---- regeneration
    regen = [e for e in evts if e.get("kind") == "regeneration"]
    if regen:
        last = regen[-1]
        r.regeneration = {
            "plans": len(regen),
            "last_changed": last.get("changed"),
            "last_assets_regenerated": last.get("assets"),
            "last_clips_rerendered": last.get("clips"),
            "last_assets_reused": last.get("assets_reused"),
            "last_clips_reused": last.get("clips_reused"),
            "est_saved_s": round(sum(float(e.get("est_saved_s") or 0) for e in regen), 1),
        }

    # ---- caches
    caches: Dict[str, Dict[str, int]] = {}
    for e in (e for e in evts if e.get("kind") == "cache"):
        c = caches.setdefault(str(e.get("cache") or "?"), {"hits": 0, "misses": 0})
        c["hits" if e.get("hit") else "misses"] += int(e.get("n") or 1)
    r.caches = caches

    # ---- AI
    ai = [e for e in evts if e.get("kind") == "ai_call"]
    live = [e for e in ai if not e.get("cached")]
    cached = [e for e in ai if e.get("cached")]
    tasks: Dict[str, int] = {}
    for e in live:
        t = str(e.get("task") or "other")
        tasks[t] = tasks.get(t, 0) + 1
    avoided = len(cached) + sum(int(c.get("hits", 0)) for k, c in caches.items() if k in AI_CACHES)
    r.ai = {
        "calls": len(live),
        "failed": sum(1 for e in live if not e.get("ok")),
        "cached_calls": len(cached),
        "avoided_calls": avoided,
        "seconds": round(sum(float(e.get("duration_s") or 0) for e in live), 1),
        "tokens_in": sum(int(e.get("tokens_in") or 0) for e in live),
        "tokens_out": sum(int(e.get("tokens_out") or 0) for e in live),
        "by_task": dict(sorted(tasks.items(), key=lambda kv: -kv[1])),
        "est_saved_s": round(avoided * EST_AI_CALL_S, 0),
    }

    # ---- recovery
    r.recovery = _count(str(e.get("action") or "?") for e in evts if e.get("kind") == "recovery")
    return r


def _count(items: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def project_report(workspace: Any, *, last_run_only: bool = False) -> ProductionReport:
    state_dir = Path(getattr(workspace, "state_dir", "") or "")
    evts = _events.read(state_dir) if state_dir else []
    scenes = duration = None
    try:
        plan = json.loads((state_dir / "editorial_plan.json").read_text(encoding="utf-8"))
        sc = plan.get("scenes") or []
        scenes = len(sc)
        duration = max((float(s.get("end") or 0) for s in sc), default=None)
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return summarize(evts, scenes=scenes, duration_s=duration, last_run_only=last_run_only)


def _fmt_s(v: Any) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v < 60:
        return f"{v:.1f}s"
    m, s = divmod(int(round(v)), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def _pct(v: Any) -> str:
    return "—" if v is None else f"{float(v) * 100:.0f}%"


def format_report(r: ProductionReport) -> str:
    lines = []
    p = r.project
    lines.append("PROJECT")
    lines.append(f"  Scenes {p.get('scenes') or '—'} · video {_fmt_s(p.get('video_duration_s'))} · "
                 f"{r.runs} run(s), production time {_fmt_s(p.get('production_s'))}")
    if p.get("runs_failed") or p.get("runs_cancelled"):
        lines.append(f"  Runs: {p.get('runs_ok', 0)} ok, {p.get('runs_failed', 0)} failed, {p.get('runs_cancelled', 0)} cancelled")
    a = r.assets
    lines.append("ASSETS")
    lines.append(f"  {a.get('generated', 0)} generated · {a.get('reused', 0)} reused · {a.get('replaced', 0)} replaced · "
                 f"{a.get('failed', 0)} failed · reuse {_pct(a.get('reuse_rate'))}")
    if a.get("source_mix"):
        lines.append("  Sources: " + ", ".join(f"{k} {v}" for k, v in a["source_mix"].items()))
    if r.providers:
        lines.append("PROVIDERS")
        for s, pv in r.providers.items():
            lines.append(f"  {s}: {pv['ok']} ok / {pv['failed']} failed ({_pct(pv.get('success_rate'))}), "
                         f"avg {_fmt_s(pv.get('avg_s'))}, {pv['retries']} retr{'y' if pv['retries'] == 1 else 'ies'}")
    q = r.queue
    if q.get("jobs"):
        lines.append("JOBS")
        lines.append(f"  {q['completed']} completed · {q['failed']} failed · {q['cancelled']} cancelled · {q['retries']} automatic retries · "
                     f"avg wait {_fmt_s(q.get('avg_wait_s'))}, avg run {_fmt_s(q.get('avg_exec_s'))}")
        if q.get("failures_by_class"):
            lines.append("  Failures: " + ", ".join(f"{k} {v}" for k, v in q["failures_by_class"].items()))
    if r.rendering:
        g = r.rendering
        lines.append("RENDERING")
        lines.append(f"  Last render {_fmt_s(g.get('last_duration_s'))} · {g.get('last_frames') or '—'} frames · "
                     f"{g.get('last_fps') or '—'} fps · {g.get('last_speed_x') or '—'}x real time")
        lines.append(f"  Clips: {g.get('clips_rendered', 0)} rendered, {g.get('clips_reused', 0)} reused from cache "
                     f"(re-render {_pct(g.get('rerender_rate'))})")
    if r.regeneration:
        g = r.regeneration
        lines.append("REGENERATION")
        lines.append(f"  Last change: {g.get('last_changed') or 0} scene(s) changed → {g.get('last_assets_regenerated') or 0} asset(s) and "
                     f"{g.get('last_clips_rerendered') or 0} clip(s) rebuilt; {g.get('last_assets_reused') or 0} assets and "
                     f"{g.get('last_clips_reused') or 0} clips kept · est. {_fmt_s(g.get('est_saved_s'))} saved overall")
    if r.caches:
        lines.append("CACHES")
        lines.append("  " + ", ".join(f"{k} {c['hits']}/{c['hits'] + c['misses']}" for k, c in sorted(r.caches.items())))
    ai = r.ai
    lines.append("AI")
    lines.append(f"  {ai.get('calls', 0)} live call(s) ({ai.get('failed', 0)} failed, {_fmt_s(ai.get('seconds'))}) · "
                 f"{ai.get('avoided_calls', 0)} avoided by caches (est. {_fmt_s(ai.get('est_saved_s'))})")
    if ai.get("by_task"):
        lines.append("  For: " + ", ".join(f"{k} {v}" for k, v in ai["by_task"].items()))
    if r.recovery:
        lines.append("RECOVERY")
        lines.append("  " + ", ".join(f"{k} {v}" for k, v in r.recovery.items()))
    return "\n".join(lines)
