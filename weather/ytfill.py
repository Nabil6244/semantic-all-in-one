"""YouTube news footage in Weather and Weather Teamplate (News Doc's search, now for every Weather style).

A storm's scenes (flooded streets, waves over a seawall, wrecked homes, a funnel over a town) are on YouTube, in local news reports and
storm chasers' uploads, not on the stock sites: a stock search for "storm" returns skies and time-lapses. Weather and Weather
Teamplate used to turn every `youtube_video:` into a stock search (weather.footage); News Doc alone searched YouTube.

    replaced, credits = fill_from_youtube(plan, project, words, duration, log, notes)

For the footage beats of a plan that ask for a weather impact by `stock_video:<request>` (a flooded street, damaged houses ...), the
searches News Doc makes for the story (weather.newsdoc.harvest: place + hazard, a local report first, cached in
_work/news_cache, paced, never another uploader's compilation) give runs of 5-12 s of the event; each such clip is replaced by a run
of ITS part of the story. A request with no run, a request that is not weather (a dam, a desk), a Forecast, your own clip, and every
failure (YouTube not answering, nothing relevant) keep the stock request: the video is always made. Off with weather.json
"youtube_news": false."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

EVENTS = {"tornado", "severe", "flood", "heavy_rain", "hurricane", "tropical_storm", "winter"}   # not "forecast" (a week ahead) or heat
MAX_DOWNLOADS = 24
MIN_SCENES = 2      # at least this many storm-scene clips ...
MIN_SHARE = 0.40    # ... and this share of the footage: a dam story that mentions a flood in passing (project #006: 7 of 81 clips) is not
                    # searched on YouTube ("North Carolina hurricane" would be footage of something else)


def enabled(project) -> bool:
    try:
        d = json.loads((Path(project.root) / "weather.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return d.get("youtube_news", True) is not False


def wanted(plan) -> List[Tuple[Any, Any]]:
    """[(beat, clip)] the footage clips that ask for a weather impact from the stock sites."""
    from .footage_geo import hazard_of

    out = []
    for b in plan.beats:
        if b.mode != "footage":
            continue
        for c in b.clips:
            kind, sep, req = str(c.asset).partition(":")
            if sep and kind == "stock_video" and hazard_of(req):
                out.append((b, c))
    return out


def _script(project) -> str:
    p = Path(project.root) / "script.txt"
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else ""
    except OSError:
        return ""


def _event(project) -> dict:
    try:
        from .intel.engine import load_auto_plan

        return dict((load_auto_plan(project) or {}).get("event") or {})
    except Exception:
        return {}


def fill_from_youtube(plan, project, words: Sequence, duration: float, log: Callable[[str], None] = print,
                      notes: Optional[List[str]] = None, *, backend=None, pause: float = 3.0, max_downloads: int = MAX_DOWNLOADS,
                      harvest_fn=None) -> Tuple[int, List[str]]:
    """Replace weather-impact stock clips by YouTube news runs. Returns (how many clips, the credit lines). Never raises."""
    notes = notes if notes is not None else []
    todo = wanted(plan)
    if not todo or not enabled(project):
        return 0, []
    total = sum(len(b.clips) for b in plan.beats if b.mode == "footage") or 1
    if len(todo) < MIN_SCENES or len(todo) / total < MIN_SHARE:
        notes.append(f"YouTube news footage: only {len(todo)} of {total} footage clips are storm scenes, so this is not a storm story "
                     "and stock footage is used")
        return 0, []
    try:
        from .newsdoc.harvest import harvest as harvest_news, usable
        from .newsdoc.story import read

        story = read(words, duration, _script(project))
        if story.category not in EVENTS:
            notes.append(f"YouTube news footage: this story is a {story.category}, not a storm event, so stock footage is used")
            return 0, []
        event = _event(project)
        got = (harvest_fn or harvest_news)(project.root, story, event, backend=backend, pause=pause, log=log, max_downloads=max_downloads)
    except Exception as exc:
        notes.append(f"YouTube news footage could not be searched ({type(exc).__name__}: {str(exc)[:100]}); stock footage is used")
        return 0, []
    notes += list(got.notes)
    root = Path(project.root)
    runs = [r for r in got.runs if (root / r.path).is_file() and usable(root / r.path, 1.0)]
    if not runs:
        return 0, []
    lines = list(story.lines)

    def part_at(t: float) -> int:
        for x in lines:
            if x.span_start - 1e-6 <= t < x.span_end:
                return x.part
        return lines[-1].part if lines else 0

    used, replaced, taken = set(), 0, []
    for b, c in todo:
        part = part_at((b.start + b.end) / 2.0)
        pool = [r for r in runs if r.part == part and r.path not in used] or [r for r in runs if r.path not in used]
        if not pool:
            continue
        run = pool[0]
        used.add(run.path)
        c.asset = run.path
        c.reason = f"YouTube news footage: {run.channel} — {run.title}"
        replaced += 1
        taken.append(run)
    credits: List[str] = []
    for r in taken:
        line = f"News footage: {r.channel} — \"{r.title}\" ({r.url})"
        if line not in credits:
            credits.append(line)
    if replaced:
        notes.append(f"YouTube news footage: {replaced} stock clip(s) of storm scenes were replaced by news footage of the event "
                     f"({len(credits)} video(s))")
    return replaced, credits
