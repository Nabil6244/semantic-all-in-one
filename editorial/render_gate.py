"""Render-time gates for editorial timeline payloads.

Kept free of Tk / CustomTkinter so CI and headless unit tests can import it.
"""

from __future__ import annotations

from typing import Any, Optional


def editorial_timeline_for_render(
    editorial_plan: Any,
    *,
    text_effects: bool,
) -> Optional[dict]:
    """Pass editorial timeline graphics into render only when Smart Text is on.

    Lower-thirds / callouts / stats live on the editorial TEXT/GRAPHICS tracks.
    They must follow the same user switch as Smart Editing → Text Effects so
    turning text off yields a clean picture (Captions is a separate burn-in).
    """
    if not text_effects:
        return None
    timeline = getattr(editorial_plan, "timeline", None) if editorial_plan is not None else None
    return timeline if isinstance(timeline, dict) else None
