"""Small UI preferences (recent styles, pinned styles, Tools section open/closed) kept in the app's own settings.json.

They go through app._settings and the app module's save_settings, never a separate write: the app saves its whole
settings dict, so a key written to the file behind its back would be lost on its next save.
"""

from __future__ import annotations

import sys
from typing import Any, List

RECENT_KEY = "ui_recent_styles"
PINNED_KEY = "ui_pinned_styles"
TOOLS_OPEN_KEY = "ui_tools_open"
RECENT_MAX = 6


def get(app: Any, key: str, default: Any = None) -> Any:
    data = getattr(app, "_settings", None)
    if not isinstance(data, dict):
        return default
    return data.get(key, default)


def put(app: Any, key: str, value: Any) -> None:
    data = getattr(app, "_settings", None)
    if not isinstance(data, dict):
        return
    data[key] = value
    try:
        saver = getattr(sys.modules.get(type(app).__module__), "save_settings", None)
        if callable(saver):
            saver(data)
    except Exception:
        pass


def names(app: Any, key: str) -> List[str]:
    raw = get(app, key, [])
    return [str(n) for n in raw if isinstance(n, str)] if isinstance(raw, list) else []


def note_recent_style(app: Any, name: str) -> None:
    if not name:
        return
    recent = [n for n in names(app, RECENT_KEY) if n != name]
    recent.insert(0, name)
    put(app, RECENT_KEY, recent[:RECENT_MAX])


def toggle_pinned(app: Any, name: str) -> bool:
    """Pin or unpin a style; True when it is now pinned."""
    pinned = names(app, PINNED_KEY)
    if name in pinned:
        pinned.remove(name)
        now = False
    else:
        pinned.append(name)
        now = True
    put(app, PINNED_KEY, pinned)
    return now
