"""News Doc from start to finish: script + voiceover -> a footage-first news documentary (docs/weather/news_footage_plan.md).

    generate_newsdoc_video(project, voiceover, output, whisper_words=..., ...) -> pakmap.app_integration.PakmapResult
    plan_newsdoc(project, words, duration, ...) -> (NdPlan, payload, notes, harvest)      everything but the render (Check plan)

  1. the story (weather.newsdoc.story)
  2. the event's data: Weather Intelligence on a sentence-by-sentence map plan, to see where each data graphic belongs
  3. news footage of the event (weather.newsdoc.harvest; cached)
  4. the timeline (weather.newsdoc.plan): map shots at the strongest data moments within MAP_SHARE, news runs, stock b-roll
  5. footage and map rendered by the shared renderer (hybrid -> weather-engine)
  6. News Doc's graphics drawn (weather.newsdoc.graphics) and laid over it (weather.newsdoc.finish)
Never raises; a part that cannot be done is a note, and the video is still made (the news footage falls back to stock, the
graphics to none, the data map to a short opening of the region). Next to the video: the credits, the numbers on screen with their
sources, and a News Doc report (shares, shots, graphics, searches, notes)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import KEY, NAME


def _script(project) -> str:
    p = Path(project.root) / "script.txt"
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else ""
    except OSError:
        return ""


def plan_newsdoc(project, words: Sequence, duration: float, *, fmt: str = "news", contact: str = "", voiceover: Optional[Path] = None,
                 news: bool = True, backend=None, pause: float = 3.0, log: Callable[[str], None] = print, engine_kw: Optional[dict] = None):
    from ..autofix import build as build_payload, windows
    from ..events import WeatherPayload
    from ..intel.engine import draft_row, run as run_engine
    from .harvest import Harvest, harvest
    from .plan import NOT_NEWSDOC, build, discovery_plan
    from .story import read

    notes: List[str] = []
    story = read(words, duration, _script(project))
    log(f"[Weather] {NAME}: {len(story.lines)} sentences, {len(story.parts)} part(s); reading the event and its data…")
    from .story_csv import load as load_csv, match as match_csv

    csv = match_csv(load_csv(project.root, notes), story, notes)   # the optional story CSV (weather/newsdoc_story.csv)
    if csv:
        notes.append(f"{NAME}: the story CSV sets {len(csv)} sentence(s); the rest is chosen automatically")
    extra: Dict[int, list] = {}
    for i, r in csv.items():
        if r.shot == "news" and r.search:
            extra.setdefault(story.lines[i].part, []).append(r.search)
    plan_a = discovery_plan(story)
    rows, wins, event = [], {}, {}
    try:
        res = run_engine(project, plan_a, words, fmt=fmt, contact=contact, voiceover=voiceover, log=log, **(engine_kw or {}))
        event = res.event or {}
        for d in res.added:
            if d.type in NOT_NEWSDOC:
                continue
            try:
                rows.append(draft_row(d))
            except (ValueError, KeyError):
                continue
        rows, wins = windows(rows, plan_a, words, [])
        notes.append(f"{NAME}: the event — {event.get('category')}, {event.get('main_day') or 'date not said'}, "
                     f"{', '.join(event.get('states') or [])}; {len(rows)} data graphic(s) found")
    except Exception as exc:   # no data: the video is still made, footage-first
        notes.append(f"{NAME}: the event's data could not be read ({exc!r}); the video has no data map shots")
    got = Harvest()
    if news:
        try:
            got = harvest(project.root, story, event, backend=backend, pause=pause, log=log, extra=extra)
        except Exception as exc:
            got.notes.append(f"news footage could not be searched ({exc!r}); stock footage is used")
    notes += got.notes
    nd = build(story, words, rows, wins, got.runs, notes=notes, csv=csv)
    payload = WeatherPayload()
    if nd.rows:
        try:
            from ..generate import load_snapshot

            snap = load_snapshot(project)
            frows, fwins = windows(nd.rows, nd.hybrid, words, [])
            _r, payload = build_payload(frows, snap, fwins, notes)
        except Exception as exc:
            notes.append(f"{NAME}: the map's data could not be drawn ({exc!r}); the map shots show the place only")
            payload = WeatherPayload()
    return nd, payload, notes, got


def _retry_unresolved(plan, unresolved: Sequence[str], category: str, round_no: int) -> int:
    """Stock clips no provider had: asked again with a broader request of the same subject (never something unrelated)."""
    from hybrid.app_integration import _scene_map

    from .plan import DEFAULT_STOCK

    want = {str(s) for s in unresolved}
    beats = {b.id: b for b in plan.beats}
    changed = 0
    for item in _scene_map(plan):
        if str(item["occ"].scene_number) not in want or item["card"]:
            continue
        b = beats.get(item["beat"])
        if b is None or not b.clips:
            continue
        c = b.clips[max(0, int(item.get("clip") or 1) - 1)]
        if not str(c.asset).startswith("stock_video:"):
            continue
        base = DEFAULT_STOCK.get(category, "dark storm clouds rolling")
        c.asset = f"stock_video:{base}" if round_no == 0 else f"stock_video:{base}, {['wide shot', 'aerial view', 'close up'][changed % 3]}"
        changed += 1
    return changed


def _grab(video: Path, t: float, out_dir: Path) -> Optional[str]:
    import subprocess

    from .graphics import _ffmpeg

    out = Path(out_dir) / f"still_{int(t * 1000)}.png"
    try:
        subprocess.run([_ffmpeg(), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(out)], timeout=60)
    except Exception:
        return None
    return str(out) if out.is_file() else None


def generate_newsdoc_video(project, voiceover_path: "str | Path", output_path: "str | Path", *, whisper_words: Sequence,
                           log: Callable[[str], None] = print, fmt: str = "news", contact: str = "", news: bool = True, backend=None,
                           pause: float = 3.0, engine_kw: Optional[dict] = None, progress_cb: Optional[Callable[[str, float], None]] = None,
                           cancel_check: Optional[Callable[[], bool]] = None, on_plan: Optional[Callable[[Any], None]] = None,
                           **kw: Any):
    """`on_plan(hybrid_plan)`: called once the plan is final, before footage is fetched (the app lists its clips in Visuals)."""
    from hybrid.generate import generate_hybrid_video
    from hybrid.plan import validate_plan
    from pakmap.app_integration import PakmapResult, voiceover_duration

    from ..render import make_render
    from . import finish, graphics

    def progress(msg: str, frac: float) -> None:
        if progress_cb is not None:
            try:
                progress_cb(msg, frac)
            except Exception:
                pass

    output_path, voiceover_path = Path(output_path), Path(voiceover_path)
    try:
        duration = voiceover_duration(voiceover_path)
        progress(f"{NAME}: planning", 0.02)
        nd, payload, notes, got = plan_newsdoc(project, whisper_words, duration, fmt=fmt, contact=contact, voiceover=voiceover_path,
                                               news=news, backend=backend, pause=pause, log=log, engine_kw=engine_kw)
    except Exception as exc:
        return PakmapResult(False, [f"{NAME} could not plan this video: {exc}"])
    from .harvest import usable
    from .plan import DEFAULT_STOCK

    for b in nd.hybrid.beats:   # a news file that cannot be read is never handed to the renderer: b-roll of the subject instead
        for c in b.clips:
            if not str(c.asset).startswith("stock_") and not usable(Path(project.root) / c.asset, 1.0):
                notes.append(f"{NAME}: the news clip {c.asset} could not be read; b-roll is used there instead")
                c.asset = f"stock_video:{DEFAULT_STOCK.get(nd.category, 'dark storm clouds rolling')}"
    problems = validate_plan(nd.hybrid)
    if problems:   # the shared never-stop repairs (weather.guard), then check again
        try:
            from ..guard import make_safe

            make_safe(nd.hybrid, notes)
        except Exception as exc:
            notes.append(f"{NAME}: the plan could not be repaired ({exc!r})")
        problems = validate_plan(nd.hybrid)
    if problems:
        return PakmapResult(False, [f"{NAME} plan: {p}" for p in problems])
    if cancel_check is not None and cancel_check():
        return PakmapResult(False, ["Cancelled"], cancelled=True)
    if on_plan is not None:
        try:
            on_plan(nd.hybrid)
        except Exception as exc:
            log(f"[Weather] {NAME}: the clips could not be listed in Visuals ({exc!r})")
    for n in notes:
        log(f"[Weather] {n}")
    sh = nd.shares()
    log(f"[Weather] {NAME}: {len(nd.shots)} shots — map {sh['map']:.0%}, news {sh['news']:.0%}, stock {sh['stock']:.0%}; "
        f"{len(nd.overlays)} graphic(s)")
    work = Path(project.root) / "_work" / KEY
    work.mkdir(parents=True, exist_ok=True)
    base = work / "base.mp4"
    result = None
    wm = kw.pop("watermark", None)   # drawn by News Doc itself, so pure footage frames skip the renderer's page entirely
    if kw.get("media_resolver") is None:   # every stock clip is checked for where it was filmed and what it shows (weather.footage_geo)
        from ..footage_geo import make_resolver

        kw["media_resolver"] = make_resolver(log)
    for attempt in range(3):
        result = generate_hybrid_video(nd.hybrid, voiceover_path, base, work_dir=work / "hybrid", whisper_words=list(whisper_words),
                                       base_dir=str(project.root), render=make_render(payload, look="classic"), log=log,
                                       progress_cb=(lambda m, f: progress(m, 0.05 + 0.8 * f)), cancel_check=cancel_check, **kw)
        if result.ok or not getattr(result, "unresolved", None) or getattr(result, "cancelled", False):
            break
        n = _retry_unresolved(nd.hybrid, result.unresolved, nd.category, attempt) if attempt == 0 else 0
        if n:
            log(f"[Weather] {NAME}: {n} stock clip(s) were not found; asking again with a broader request of the same subject")
            continue
        try:   # still missing: those clips are left out and the plan repaired around them (weather.guard), one last run
            from ..guard import drop_unfound, make_safe

            n = drop_unfound(nd.hybrid, work / "hybrid" / "hybrid_script.csv", result.unresolved, notes)
            make_safe(nd.hybrid, notes, new_requests=False)
        except Exception as exc:
            notes.append(f"{NAME}: the missing clips could not be left out ({exc!r})")
            n = 0
        if not n:
            break
        log(f"[Weather] {NAME}: {n} clip(s) could not be found anywhere; they are left out and the video is made without them")
    if result is None or not result.ok:
        return result
    progress(f"{NAME}: drawing the graphics", 0.88)
    tmp = Path(tempfile.mkdtemp(prefix="newsdoc_", dir=str(work)))
    clips = []
    try:
        for ov in nd.overlays:
            if cancel_check is not None and cancel_check():
                return PakmapResult(False, ["Cancelled"], cancelled=True)
            if ov.params.get("still_t"):   # framed picture / polaroids: stills of the story's own footage, from the rendered video
                ov.params["stills"] = [p for p in (_grab(base, t, tmp) for t in ov.params["still_t"]) if p]
            path = graphics.render(ov, tmp)
            if path is None:
                notes.append(f"{NAME}: the {ov.kind} graphic at {ov.t0:.1f}s could not be drawn and is left out")
                continue
            clips.append((path, ov.t0))
        if isinstance(wm, dict) and str(wm.get("text") or "").strip() and wm.get("enabled", True) is not False:
            from .plan import Overlay

            still = tmp / "watermark.png"
            graphics.watermark(0.0, 1.0, {"text": str(wm["text"]).strip()}).save(still)
            clips.append((still, 0.0))
        progress(f"{NAME}: adding the graphics", 0.93)
        ok, more = finish.composite(base, clips, output_path)
        notes += more
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    credits = list(result.credits or []) + got.credits()
    try:
        output_path.with_name(f"{output_path.stem} - credits.txt").write_text("\n".join(credits) + "\n", encoding="utf-8")
        output_path.with_suffix(".numbers.txt").write_text(payload.report.to_text(), encoding="utf-8")
        report = {"style": NAME, "duration": round(duration, 2), "shares": sh,
                  "shots": [{"t0": s.t0, "t1": s.t1, "kind": s.kind, "asset": s.asset, "rows": s.rows, **({"source": s.meta} if s.meta else {})}
                            for s in nd.shots],
                  "graphics": [{"kind": o.kind, "t0": o.t0, "t1": o.t1} for o in nd.overlays],
                  "map_rows": [r.id for r in nd.rows], "searches": got.searches, "news_downloads": got.downloads, "notes": notes}
        output_path.with_suffix(".newsdoc.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass
    progress(f"{NAME}: done", 1.0)
    return PakmapResult(True, output_path=output_path, credits=credits, warnings=list(result.warnings or []) + notes,
                        report=getattr(result, "report", None), audio=getattr(result, "audio", None))
