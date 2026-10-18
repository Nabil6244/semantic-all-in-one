"""The Normal Video side of the gfx-core graphics, in the order app.py runs it.

    prepared = prepare(...)            plan from the narration, draw the sequences (cached), keep what is safe to show
    prepared.hook_specs(specs)         (inside video_generator's graphics lookup) the plain stats a template replaced are left out
    prepared.filter_smart_text(fx)     Smart Text steps aside where a template graphic is on screen
    prepared.composite(video, ...)     after the render: the layer goes over the finished video

Nothing here is imported, and nothing runs, unless the "Use Hybrid Map Graphics & Sound" switch is on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import captions as _captions
from . import composite as _composite
from . import planner as _planner
from . import runner as _runner


@dataclass
class Prepared:
    events: List[Dict[str, Any]] = field(default_factory=list)                 # the events that will really be drawn (rendered, caption-safe)
    placed: List[Tuple[float, _runner.Result]] = field(default_factory=list)
    replaced_ids: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    report: List[Dict[str, Any]] = field(default_factory=list)                 # one row per planned graphic: id, template, t_in, t_out, status, reason, moved_up
    status: str = "none_planned"        # none_planned | ok | partial | all_skipped | unavailable (no browser / renderer)
    width: int = 1920
    height: int = 1080
    fps: int = 30
    total: float = 0.0

    def __bool__(self) -> bool:
        return bool(self.placed)

    def hook_specs(self, specs: Sequence[Any]) -> List[Any]:
        gone = set(self.replaced_ids)
        return [s for s in specs if getattr(s, "graphic_id", None) not in gone] if gone else list(specs)

    def filter_smart_text(self, scene_text_fx: Optional[list], display_timeline: Sequence[Tuple[float, float]]) -> int:
        """In place: drop the Smart Text effects that fall inside a template graphic's window. Returns how many were dropped."""
        if not scene_text_fx or not self.events:
            return 0
        from graphics.conflicts import filter_smart_text_for_graphics

        wins = []
        for e in self.events:
            blob = " ".join(str(v) for v in (e.get("slots") or {}).values() if isinstance(v, (str, int, float)))
            wins.append(SimpleNamespace(start=e["t_in"], end=e["t_out"], role="CALLOUT", decision="TEXT", source="",
                                        text=SimpleNamespace(text=blob, secondary_text="", tertiary_text=""), payload={}))
        dropped = 0
        for i, fx in enumerate(scene_text_fx):
            if not fx or i >= len(display_timeline):
                continue
            kept = filter_smart_text_for_graphics(list(fx), wins, scene_start=display_timeline[i][0], scene_end=display_timeline[i][1])
            dropped += len(fx) - len(kept)
            fx[:] = kept
        return dropped

    def summary_lines(self) -> List[str]:
        """What the user is told: how many graphics were planned, drawn and skipped, each skip with its template, time and reason, and what to do."""
        rendered = [r for r in self.report if r["status"] == "rendered"]
        skipped = [r for r in self.report if r["status"] == "skipped"]
        moved = [r for r in rendered if r.get("adjusted")]
        lines = [f"[GFX] Template graphics: {len(self.report)} planned, {len(rendered)} drawn, {len(skipped)} skipped"
                 + (f" ({len(moved)} moved, scaled or lightened to clear a caption)" if moved else "") + "."]
        for r in moved:
            lines.append(f"[GFX]   adjusted {r['template']} at {r['t_in']:.1f}s: {r['reason']}")
        for r in skipped:
            lines.append(f"[GFX]   skipped {r['template']} at {r['t_in']:.1f}s: {r['reason']}")
        if self.status == "unavailable":
            lines.append("[GFX] WARNING: the graphics renderer could not start, so this video uses the plain Doc Style look instead of the animated template "
                         "graphics. It needs Google Chrome or the one-time browser download (about 150 MB): check the internet connection, or install "
                         "Google Chrome, then render again. Nothing else needs installing.")
        elif self.status == "all_skipped":
            lines.append("[GFX] WARNING: none of the planned template graphics could be shown, so this video uses the plain Doc Style look instead (reasons above).")
        elif self.status == "none_planned":
            lines.append("[GFX] No sentence in this narration called for a template graphic; the Doc Style look is used.")
        return lines

    def final_line(self, composited: bool) -> str:
        """The one line that says what the finished video really got, so a fallback is never reported as a success."""
        if composited:
            return f"[GFX] RESULT: the video has {len(self.placed)} animated template graphic(s) (Hybrid Map graphics)."
        if self.status == "unavailable":
            return "[GFX] RESULT: the animated template graphics could NOT be drawn (graphics renderer unavailable); the video uses the Doc Style look. Render again to retry."
        if self.status in ("all_skipped", "none_planned"):
            return "[GFX] RESULT: no animated template graphics are in this video; it uses the Doc Style look (see the reasons above)."
        return "[GFX] RESULT: the template graphics were drawn but could not be added to the video; it uses the Doc Style look. Render again to retry."

    def composite(self, video: Any, log: Callable[[str], None] = print) -> bool:
        if not self.placed:
            return False
        ok = _composite.composite(video, self.placed, video, self.width, self.height, self.fps, self.total, log=log)
        if ok:
            log(f"[GFX] {len(self.placed)} gfx-core graphic(s) composited over the video.")
        return ok


ENTRY_LEAD_S = 0.02


def _aligned(e: Dict[str, Any], res: "_runner.Result") -> Dict[str, Any]:
    """The event with its sound cues set to the moment the graphic really appears in the rendered frames (res.entry_s), keeping the spacing between its
    own cues. Left as the template's own timing when the render did not see it enter."""
    import gfx_templates as G

    if res.entry_s is None:
        return e
    cues = G.sfx_cues(e)
    if not cues:
        return e
    shift = float(res.entry_s) - ENTRY_LEAD_S - cues[0][0]
    tpl = dict(e["template"], sfx=[{"at": round(max(0.0, at + shift), 3), "sound": sound} for at, sound, _why in cues])
    return dict(e, template=tpl)


def prepare(words: Sequence[Tuple[str, float, float]], total: float, aligned_rows: Sequence[dict], display_timeline: Sequence[Tuple[float, float]],
            existing_specs: Sequence[Any], *, width: int, height: int, fps: int = 30, captions: bool = False, caption_style: str = "classic",
            log: Callable[[str], None] = print, cancel_check: Optional[Callable[[], bool]] = None, cache_root: Any = None) -> Prepared:
    out = Prepared(width=width, height=height, fps=fps, total=float(total))
    try:
        plan = _planner.plan_graphics(words, total, aligned_rows, display_timeline, existing_specs, captions=captions, log=log)
    except Exception as exc:
        log(f"[GFX] graphics planning skipped ({exc})")
        return out
    out.notes += plan.notes
    if not plan.events:
        for line in out.summary_lines():
            log(line)
        return out

    def job_for(e: Dict[str, Any], f: Optional[_captions.Fit] = None) -> _runner.Job:
        return _runner.Job(template=e["template"], slots=e.get("slots") or {}, len=float(e["t_out"]) - float(e["t_in"]), cues=e.get("cues") or {},
                           dy=f.dy if f else 0.0, scale=f.scale if f else 1.0, anchor=f.anchor if f else (0.0, 0.0))

    def row(e: Dict[str, Any], status: str, reason: str = "", adjusted: bool = False) -> None:
        out.report.append({"id": e["id"], "template": e["template"].get("id"), "t_in": float(e["t_in"]), "t_out": float(e["t_out"]), "status": status,
                           "reason": reason, "adjusted": adjusted})

    results = _runner.render_overlays([job_for(e) for e in plan.events], width, height, fps, root=cache_root, log=log, cancel_check=cancel_check)
    key0 = {e["id"]: _runner.job_key(job_for(e), width, height, fps) for e in plan.events}
    caps = []
    if captions:
        try:
            caps = _captions.scene_masks(aligned_rows, display_timeline, width, height, caption_style)
        except Exception as exc:
            out.notes.append(f"captions could not be located ({exc}); graphics are kept away from the bottom of the frame")
    keep: List[Tuple[Dict[str, Any], _runner.Result]] = []
    reshift: List[Tuple[Dict[str, Any], float]] = []
    browser_down = 0
    for e in plan.events:
        res = results.get(key0[e["id"]])
        if res is None or not res.ok:
            err = res.error if res else "no result"
            browser_down += 1 if "unavailable" in err else 0
            row(e, "skipped", f"it could not be drawn ({err})")
            continue
        if not captions:
            keep.append((e, res))
            row(e, "rendered")
            continue
        f = _captions.fit(res, e["t_in"], e["t_out"], caps, width, height) if caps else _captions.Fit(False, reason="the captions could not be located")
        if f.ok and not f.changed:
            keep.append((e, res))
            row(e, "rendered", f.reason)
        elif f.ok:
            reshift.append((e, f))
            row(e, "rendered", f.reason, True)          # provisional: corrected below if the adjusted version fails
        else:
            row(e, "skipped", f.reason)
    if reshift:
        moved = _runner.render_overlays([job_for(e, f) for e, f in reshift], width, height, fps, root=cache_root, log=log, cancel_check=cancel_check)
        for e, f in reshift:
            res = moved.get(_runner.job_key(job_for(e, f), width, height, fps))
            r = next(r for r in out.report if r["id"] == e["id"])
            f2 = _captions.fit(res, e["t_in"], e["t_out"], caps, width, height) if res is not None and res.ok else _captions.Fit(False, reason="the adjusted version could not be drawn")
            if f2.ok and not f2.changed:
                keep.append((e, res))
            else:
                r.update(status="skipped", reason=f"adjusted ({f.reason}) but still not clear: {f2.reason}", adjusted=False)
    # a soft backing that is the only thing over a caption (and cannot be moved clear): the same graphic with a smaller backing, type and animation unchanged
    again = [(e, f) for e, f in ((e, _captions.fit(results[key0[e["id"]]], e["t_in"], e["t_out"], caps, width, height)) for e in plan.events
                                 if results.get(key0[e["id"]]) is not None and results[key0[e["id"]]].ok and captions and caps
                                 and next(r for r in out.report if r["id"] == e["id"])["status"] == "skipped")
             if not f.ok and f.kind in ("backing", "offscreen") and e["template"].get("shade")]
    for e, _f in again:
        r = next(r for r in out.report if r["id"] == e["id"])
        for factor in (0.75, 0.55, 0.4):
            tpl = dict(e["template"], shade=dict(e["template"]["shade"], rx=e["template"]["shade"].get("rx", 0.34) * factor, ry=e["template"]["shade"].get("ry", 0.26) * factor))
            e2 = dict(e, template=tpl)
            got = _runner.render_overlays([job_for(e2)], width, height, fps, root=cache_root, log=log, cancel_check=cancel_check)
            res = got.get(_runner.job_key(job_for(e2), width, height, fps))
            if res is None or not res.ok:
                continue
            f3 = _captions.fit(res, e["t_in"], e["t_out"], caps, width, height)
            if f3.ok and not f3.changed:
                keep.append((e2, res))
                r.update(status="rendered", reason=f"its backing was reduced to {factor:.0%} of its size to stay off the caption", adjusted=True)
                break
    keep.sort(key=lambda p: p[0]["t_in"])
    keep = [(_aligned(e, res), res) for e, res in keep]
    out.events = [e for e, _ in keep]
    out.placed = [(float(e["t_in"]), res) for e, res in keep]
    out.replaced_ids = sorted({i for e in out.events for i in e.get("replaces", [])})
    out.notes += [f"{r['id']} ({r['template']}) skipped: {r['reason']}" for r in out.report if r["status"] == "skipped"]
    out.status = ("unavailable" if browser_down and browser_down == len(plan.events) else "all_skipped" if not out.placed
                  else "ok" if all(r["status"] == "rendered" for r in out.report) else "partial")
    for line in out.summary_lines():
        log(line)
    return out
