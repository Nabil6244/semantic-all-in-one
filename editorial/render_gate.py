"""Render-time gates for editorial timeline payloads.

Kept free of Tk / CustomTkinter so CI and headless unit tests can import it.
"""

from __future__ import annotations

from typing import Any, Optional


MAP_NICHE_TEMPLATES = frozenset({"countdown_tag", "countdown_hook", "keyword_callout"})


def is_map_niche_graphic(event_metadata: dict) -> bool:
    """The countdown fact tag, hook and yellow keyword callouts."""
    payload = (event_metadata or {}).get("payload") or {}
    return str(payload.get("template") or "") in MAP_NICHE_TEMPLATES


def editorial_timeline_for_render(
    editorial_plan: Any,
    *,
    text_effects: bool = True,
    graphics: Optional[bool] = None,
    map_niche: Optional[bool] = None,
) -> Optional[dict]:
    """The editorial timeline graphics to render, per the Smart Editing
    switches: "Graphics" (lower thirds, statistic cards, titles) and "Map
    Niche" (countdown fact tag, hook, keyword callouts). Each defaults to the
    old single Text Effects switch when not given. None when nothing shows."""
    show_graphics = text_effects if graphics is None else bool(graphics)
    show_map_niche = text_effects if map_niche is None else bool(map_niche)
    if not (show_graphics or show_map_niche):
        return None
    timeline = getattr(editorial_plan, "timeline", None) if editorial_plan is not None else None
    if not isinstance(timeline, dict):
        return None
    if show_graphics and show_map_niche:
        return timeline
    events = []
    for event in timeline.get("events") or []:
        meta = (event or {}).get("metadata") or {} if isinstance(event, dict) else {}
        if isinstance(event, dict) and meta.get("graphic"):
            if is_map_niche_graphic(meta) and not show_map_niche:
                continue
            if not is_map_niche_graphic(meta) and not show_graphics:
                continue
        events.append(event)
    return dict(timeline, events=events)
