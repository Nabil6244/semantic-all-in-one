"""Surgical regeneration: what a change actually requires, computed from the dependency graph.

The executors already reuse what they can (AssetManager's manifest cache, the render cache, the whisper / editorial /
smart-editing caches). This module makes that reuse DECIDED and VISIBLE before a run starts:

  plan_for(graph, previous_snapshot, history) -> RegenerationPlan
      which scenes changed and how, which assets will be fetched/generated again, which clips re-rendered, whether the
      narration must be re-aligned — and everything that is kept, with an estimate of the time that saves (from this
      project's own measured timings, falling back to conservative defaults).

  record_render(...)
      after a successful render: save the graph snapshot the next run diffs against, and emit the regeneration and
      render events analytics reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from . import events
from .graph import ASPECT_LABELS, ChangeSet, ProductionGraph

# Used only when the project has no measurements yet (seconds).
DEFAULT_ASSET_S = {"flow_video": 150.0, "flow_image": 45.0, "youtube_video": 40.0, "stock_video": 12.0,
                   "stock_image": 4.0, "map": 35.0}
DEFAULT_ASSET_FALLBACK_S = 20.0
DEFAULT_CLIP_S = 6.0


@dataclass
class RegenerationPlan:
    changes: ChangeSet
    total_scenes: int
    assets_regenerate: List[str] = field(default_factory=list)
    assets_reuse: List[str] = field(default_factory=list)
    clips_render: List[str] = field(default_factory=list)
    clips_reuse: List[str] = field(default_factory=list)
    est_saved_s: float = 0.0  # rendering avoided by reusing cached clips
    est_asset_s: float = 0.0  # expected time to fetch/generate the assets that must be regenerated

    @property
    def nothing_changed(self) -> bool:
        return not self.changes.first_run and not self.changes.changed and not self.changes.global_changes \
            and not self.assets_regenerate and not self.clips_render

    def lines(self, limit: int = 8) -> List[str]:
        cs = self.changes
        out: List[str] = []
        if cs.first_run:
            out.append(f"First production run for this plan: {len(self.assets_reuse)} of {self.total_scenes} scene "
                       f"asset(s) already on disk will be kept.")
            return out
        if self.nothing_changed:
            out.append("Nothing changed since the last render: every asset and clip is reused.")
            return out
        for gid in cs.global_changes:
            out.append({"audio": "Narration recording changed: words are re-aligned; only scenes whose length "
                                 "changes are re-rendered.",
                        "settings": "Render settings changed: every clip is re-rendered (assets are kept).",
                        "scene list": f"Scenes added: {len(cs.added_scenes)}, removed: {len(cs.removed_scenes)}."}.get(gid, gid))
        shown = 0
        for scene, aspects in sorted(cs.changed.items()):
            if shown >= limit:
                out.append(f"... and {len(cs.changed) - limit} more changed scene(s)")
                break
            out.append(f"Scene {scene}: {', '.join(ASPECT_LABELS.get(a, a) for a in aspects)} changed")
            shown += 1
        out.append(f"Regenerate {len(self.assets_regenerate)} asset(s)"
                   + (f" (about {_fmt(self.est_asset_s)})" if self.assets_regenerate and self.est_asset_s >= 1 else "")
                   + f", re-render {len(self.clips_render)} clip(s); keep {len(self.assets_reuse)} asset(s) and "
                   f"{len(self.clips_reuse)} clip(s)"
                   + (f" — about {_fmt(self.est_saved_s)} less rendering." if self.est_saved_s >= 1 else "."))
        return out

    def to_event(self) -> dict:
        return {"changed": len(self.changes.changed), "assets": len(self.assets_regenerate),
                "clips": len(self.clips_render), "assets_reused": len(self.assets_reuse),
                "clips_reused": len(self.clips_reuse), "est_saved_s": round(self.est_saved_s, 1),
                "global": list(self.changes.global_changes), "first_run": self.changes.first_run}


def _fmt(s: float) -> str:
    s = float(s)
    if s < 90:
        return f"{s:.0f}s"
    m = s / 60
    return f"{m:.0f} min" if m < 90 else f"{m / 60:.1f} h"


def measured_timings(history: Iterable[dict]) -> Dict[str, float]:
    """Average seconds per asset by source and per rendered clip, from this project's own events."""
    per_source: Dict[str, List[float]] = {}
    clip: List[float] = []
    for e in history:
        if e.get("kind") == "job" and e.get("type") == "asset" and e.get("state") == "completed":
            s = str(e.get("source") or "")
            if s and float(e.get("exec_s") or 0) > 0:
                per_source.setdefault(s, []).append(float(e["exec_s"]))
        elif e.get("kind") == "render":
            n = int(e.get("clips_rendered") or 0)
            # Wall-clock seconds per rendered clip (clips may render in parallel); older events only have the sum.
            spent = float(e.get("duration_s") or 0) - float(e.get("mux_s") or 0) if e.get("mux_s") is not None \
                else float(e.get("scene_render_s") or 0)
            if n and spent > 0:
                clip.append(spent / n)
    out = {s: sum(v) / len(v) for s, v in per_source.items() if v}
    if clip:
        out["__clip__"] = sum(clip) / len(clip)
    return out


def _asset_seconds(source: str, timings: Dict[str, float]) -> float:
    return timings.get(source) or DEFAULT_ASSET_S.get(source, DEFAULT_ASSET_FALLBACK_S)


def plan_for(graph: ProductionGraph, previous: Optional[dict], *, history: Iterable[dict] = (),
             sources: Optional[Dict[str, str]] = None) -> RegenerationPlan:
    """``sources``: scene -> the source each scene resolves from (for time estimates)."""
    cs = graph.diff(previous)
    regen = cs.assets_to_regenerate
    clips = cs.clips_to_render
    plan = RegenerationPlan(
        changes=cs,
        total_scenes=len(graph.scenes),
        assets_regenerate=regen,
        assets_reuse=[s for s in graph.scenes if s not in regen],
        clips_render=clips,
        clips_reuse=[s for s in graph.scenes if s not in clips],
    )
    if not cs.first_run:
        # Only the work this layer actually avoids: re-rendering the clips the render cache serves. (Kept assets are
        # not counted — the asset manifest kept them before this layer existed.) Per-clip time is this project's own.
        timings = measured_timings(history)
        plan.est_saved_s = len(plan.clips_reuse) * timings.get("__clip__", DEFAULT_CLIP_S)
        plan.est_asset_s = sum(_asset_seconds((sources or {}).get(s, ""), timings) for s in plan.assets_regenerate)
    return plan


def emit_plan(plan: RegenerationPlan) -> None:
    events.emit("regeneration", **plan.to_event())


def render_stats(perf: Any, *, video_s: float, fps: int = 30, clips_total: Optional[int] = None) -> dict:
    """Render metrics from the existing PerfRecorder of the run (scene_render + mux spans, render-cache tallies)."""
    try:
        scene_s = float(perf.total_for("scene_render"))
        mux_s = float(perf.total_for("mux"))
        wall_s = float(perf.total_for("render_wall"))
        hits, misses = int(perf.cache_hits), int(perf.cache_misses)
    except Exception:
        scene_s = mux_s = wall_s = 0.0
        hits = misses = 0
    duration = wall_s or (scene_s + mux_s)  # parallel clip renders overlap: wall clock when the renderer measured it
    frames = int(round(float(video_s or 0) * fps))
    return {
        "duration_s": round(duration, 2),
        "scene_render_s": round(scene_s, 2),
        "mux_s": round(mux_s, 2),
        "frames": frames,
        "fps": round(frames / duration, 1) if duration > 0 else None,
        "speed_x": round(float(video_s) / duration, 2) if duration > 0 and video_s else None,
        "clips_reused": hits,
        "clips_rendered": misses,
        "scenes": clips_total if clips_total is not None else hits + misses,
        "output_s": round(float(video_s or 0), 2),
    }


# ---------------------------------------------------------------------- pipeline entry points
def _load_manifest(images_dir) -> dict:
    import json
    from pathlib import Path

    try:
        from asset_manager import MANIFEST_NAME

        data = json.loads((Path(images_dir) / MANIFEST_NAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, ImportError):
        return {}


def _sources(rows, manifest: dict) -> Dict[str, str]:
    from .graph import scene_key

    out: Dict[str, str] = {}
    try:
        from providers.base import AssetSource, SceneRow
        from providers.router import SceneAssetRouter
    except ImportError:
        return out
    for row in rows:
        try:
            scene = row if isinstance(row, SceneRow) else SceneRow.from_csv_row(dict(row))
            n = scene_key(scene.scene_number)
            rec = manifest.get(n) or manifest.get(str(scene.scene_number)) or {}
            out[n] = str(rec.get("source") or (SceneAssetRouter.classify(scene) or AssetSource.LOCAL).value)
        except Exception:
            continue
    return out


def build_graph(rows, *, images_dir, audio_key: str = "", timings=None, settings=None) -> ProductionGraph:
    rows = list(rows)
    return ProductionGraph.build(rows, manifest=_load_manifest(images_dir), images_dir=images_dir,
                                 audio_key=audio_key, timings=timings, settings=settings)


def prepare(rows, *, images_dir, state_dir, audio_key: str = "", timings=None, settings=None):
    """(graph, plan) for the run about to start. Never raises: on any failure returns (None, None)."""
    try:
        from .graph import load_snapshot

        rows = list(rows)
        graph = build_graph(rows, images_dir=images_dir, audio_key=audio_key, timings=timings, settings=settings)
        history = events.read(state_dir, kinds=["job", "render"]) if state_dir else []
        plan = plan_for(graph, load_snapshot(state_dir), history=history,
                        sources=_sources(rows, _load_manifest(images_dir)))
        _only_cached_clips_are_reused(plan, state_dir)
        return graph, plan
    except Exception:
        return None, None


def _only_cached_clips_are_reused(plan: RegenerationPlan, state_dir) -> None:
    """A clip can only come from the render cache if the cache holds one for that scene (it may have been cleared from
    Settings → Cache & Storage). Clips without an entry move to the render list."""
    if plan is None or state_dir is None:
        return
    import json
    from pathlib import Path

    try:
        index = json.loads((Path(state_dir) / "render_cache.json").read_text(encoding="utf-8"))
        cached = {str(k).lstrip("0") or "0" for k in (index.get("entries") or {})}
    except (OSError, ValueError, AttributeError):
        cached = set()
    missing = [s for s in plan.clips_reuse if (s.lstrip("0") or "0") not in cached]
    if missing:
        plan.clips_reuse = [s for s in plan.clips_reuse if s not in missing]
        plan.clips_render = sorted(set(plan.clips_render) | set(missing))
        plan.est_saved_s = plan.est_saved_s * (len(plan.clips_reuse) / max(1, len(plan.clips_reuse) + len(missing)))


def commit(graph: Optional[ProductionGraph], state_dir) -> None:
    """After a successful render: this graph is what the next run compares against."""
    if graph is None or state_dir is None:
        return
    from .graph import save_snapshot

    save_snapshot(state_dir, graph)
