"""Windowed scene list helpers — materialize only a scroll window for large plans."""

from __future__ import annotations

from typing import Tuple

# Keep in sync with app.py batching / windowing constants.
SCENE_ROW_SYNC_LIMIT = 6   # rows built in one go; more are built a few at a time so the window keeps answering
SCENE_ROW_BATCH = 4        # a Windows PC took 0.6 s per 20 rows (freeze report 2026-11-25): 4 rows ~0.12 s per step
# Prefer batching over spacer-windowing — spacers create large empty gaps in CTk.
SCENE_WINDOW_THRESHOLD = 200  # effectively disable spacer-windowing for typical plans
SCENE_ROW_HEIGHT = 52   # the Visuals rows (ui/visuals_look.py): 16:9 thumbnail + two lines of narration
SCENE_WINDOW_BUFFER = 12


def should_window(n: int) -> bool:
    return n > SCENE_WINDOW_THRESHOLD


def window_bounds(
    *,
    total: int,
    scroll_top_px: float,
    viewport_h: float,
    row_h: int = SCENE_ROW_HEIGHT,
    buffer: int = SCENE_WINDOW_BUFFER,
) -> Tuple[int, int]:
    """Return [first, last) indices to materialize for the current scroll."""
    if total <= 0:
        return 0, 0
    rh = max(1, int(row_h))
    first = max(0, int(scroll_top_px // rh) - buffer)
    visible = max(1, int(viewport_h // rh) + 1)
    last = min(total, first + visible + 2 * buffer)
    if last - first < visible + buffer:
        last = min(total, first + visible + 2 * buffer)
    return first, last


def truncate(text: str, n: int = 36) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= n:
        return t
    return t[: max(0, n - 1)].rstrip() + "…"
