"""What the Hybrid log says about 'Add graphics from the narration', and how the switch is remembered per project (kept out of app.py so it is testable)."""

from __future__ import annotations

from typing import Any, Mapping, Optional

ADDED_NOTE = "added from the narration"


def narration_graphics_line(on: bool, report: Optional[Any]) -> str:
    """One log line: the switch state and, when it was on, how many graphics the narration produced."""
    if not on:
        return ("[HYBRID] Graphics from the narration: OFF. Numbers, quotes, names and dates the narration states got no graphic of their own "
                "(switch on 'Add graphics from the narration' in the Hybrid block and render again to add them).\n")
    n = sum(1 for e in (getattr(report, "events", None) or []) if getattr(e, "note", "") == ADDED_NOTE)
    if n == 0:
        return "[HYBRID] Graphics from the narration: ON, but none were found: the narration states no number, quote, name or date a graphic could show.\n"
    return f"[HYBRID] Graphics from the narration: ON, {n} added.\n"


def restored_switch(saved: Mapping[str, Any], app_default: bool) -> bool:
    """The project's own choice when it made one, otherwise the app-wide setting."""
    return bool(saved["auto_graphics"]) if "auto_graphics" in saved else bool(app_default)
