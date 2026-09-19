"""Pure time/pixel math for the interactive timeline canvas (Phase 2).

No Tk import here on purpose — keeps this unit-testable without a display,
and keeps ui/timeline_canvas.py's Canvas wrapper a thin, mostly-untested-by-
necessity layer over logic that IS fully tested.

Zoom never changes actual timing (spec requirement M) — it only changes
PIXELS_PER_SECOND_AT_100, i.e. how many pixels represent one second.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

PIXELS_PER_SECOND_AT_100 = 20.0
ZOOM_LEVELS = (0.25, 0.5, 1.0, 2.0, 4.0)
TRACK_ORDER = ("VIDEO_1", "VIDEO_2", "IMAGE", "VOICEOVER", "MUSIC", "AMBIENCE", "SFX", "TEXT", "GRAPHICS")
# The two primary visual tracks always get a row, even with zero events on
# them yet, so the row layout never shifts around a project's own choice
# of VIDEO_1 vs IMAGE for its coverage (see timeline_canvas.py's redraw()/
# _event_at() — both union this in explicitly rather than slicing
# TRACK_ORDER positionally, which broke once VIDEO_2 was inserted into
# TRACK_ORDER ahead of IMAGE).
ALWAYS_PRESENT_TRACKS = ("VIDEO_1", "IMAGE")
TRACK_LABELS = {
    "VIDEO_1": "Video",
    "VIDEO_2": "B-Roll",
    "IMAGE": "Image",
    "VOICEOVER": "Voiceover",
    "MUSIC": "Music",
    "AMBIENCE": "Ambience",
    "SFX": "SFX",
    "TEXT": "Text",
    "GRAPHICS": "Graphics",
}
TRACK_HEIGHT = 34
TRACK_GAP = 2
RULER_HEIGHT = 24


def pixels_per_second(zoom: float) -> float:
    return PIXELS_PER_SECOND_AT_100 * max(0.01, float(zoom))


def time_to_x(t: float, zoom: float, scroll_x: float) -> float:
    return float(t) * pixels_per_second(zoom) - float(scroll_x)


def x_to_time(x: float, zoom: float, scroll_x: float) -> float:
    pps = pixels_per_second(zoom)
    return (float(x) + float(scroll_x)) / pps if pps else 0.0


def content_width(duration: float, zoom: float) -> float:
    return max(1.0, float(duration) * pixels_per_second(zoom))


def track_rows(tracks: Sequence[str]) -> List[str]:
    """Fixed, stable ordering — tracks present get a row; absent ones
    (e.g. no MUSIC in this project) are simply skipped, not blanked out."""
    present = set(tracks)
    ordered = [t for t in TRACK_ORDER if t in present]
    extra = sorted(present - set(TRACK_ORDER))
    return ordered + extra


def track_y(track: str, rows: Sequence[str]) -> float:
    idx = list(rows).index(track)
    return RULER_HEIGHT + idx * (TRACK_HEIGHT + TRACK_GAP)


def total_height(rows: Sequence[str]) -> float:
    return RULER_HEIGHT + len(rows) * (TRACK_HEIGHT + TRACK_GAP)


def nearest_zoom_index(zoom: float) -> int:
    return min(range(len(ZOOM_LEVELS)), key=lambda i: abs(ZOOM_LEVELS[i] - zoom))


def zoom_in(zoom: float) -> float:
    i = nearest_zoom_index(zoom)
    return ZOOM_LEVELS[min(i + 1, len(ZOOM_LEVELS) - 1)]


def zoom_out(zoom: float) -> float:
    i = nearest_zoom_index(zoom)
    return ZOOM_LEVELS[max(i - 1, 0)]


def ruler_ticks(duration: float, zoom: float) -> List[Tuple[float, str]]:
    """Pick a tick interval so labels stay legibly spaced regardless of
    zoom: denser at high zoom, sparser when zoomed out over a long video."""
    pps = pixels_per_second(zoom)
    min_px_between_ticks = 60.0
    candidate_intervals = (0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600)
    interval = candidate_intervals[-1]
    for c in candidate_intervals:
        if c * pps >= min_px_between_ticks:
            interval = c
            break
    ticks = []
    t = 0.0
    while t <= duration + 1e-6:
        ticks.append((round(t, 3), _format_timecode(t)))
        t += interval
    return ticks


def _format_timecode(t: float) -> str:
    t = max(0.0, float(t))
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def clip_rect(event_start: float, event_end: float, track: str, rows: Sequence[str], zoom: float, scroll_x: float):
    """(x0, y0, x1, y1) pixel rect for one event's clip block."""
    x0 = time_to_x(event_start, zoom, scroll_x)
    x1 = time_to_x(event_end, zoom, scroll_x)
    y0 = track_y(track, rows)
    y1 = y0 + TRACK_HEIGHT
    return (x0, y0, x1, y1)


def visible_time_range(canvas_width: float, zoom: float, scroll_x: float) -> Tuple[float, float]:
    return (x_to_time(0, zoom, scroll_x), x_to_time(canvas_width, zoom, scroll_x))
