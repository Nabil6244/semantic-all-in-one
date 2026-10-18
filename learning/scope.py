"""Stable, normalized style scope: ``<mode>/<style>`` (e.g. ``normal/history``, ``overscaled/exp_solar``, ``weather/newsdoc``).

Derived from the real app/project state at the moment of the event. Fields that do not exist in a mode are skipped; the
fallback ``<mode>/default`` is used only when no more specific identity is available.
"""

from __future__ import annotations

import re
from typing import Any, Optional

KNOWN_MODES = ("normal", "overscaled", "pakmap", "hybrid", "starmap", "whatif", "weather")
_BAD = re.compile(r"[^a-z0-9_.+\-]+")


def _norm(value: Any) -> str:
    return _BAD.sub("_", str(value or "").strip().lower()).strip("_")[:60]


def build_scope(mode: Any, style: Any = None, extra: Any = None) -> str:
    m = _norm(mode) or "normal"
    s = _norm(style) or "default"
    scope = f"{m}/{s}"
    e = _norm(extra)
    return f"{scope}+{e}" if e else scope


def resolve_scope(app: Any = None, mode: Optional[str] = None, workspace: Any = None, style: Optional[str] = None) -> str:
    """Scope for ``mode`` (or app.generation_mode). ``style`` is an explicit style id from a caller that owns the style
    concept (Weather passes its editing style). Never raises."""
    m = _norm(mode or getattr(app, "generation_mode", "") or "normal") or "normal"
    try:
        ws = workspace if workspace is not None else getattr(app, "_workspace", None)
        meta = {}
        try:
            meta = ws.read_meta() if ws is not None else {}
        except Exception:
            meta = {}
        if m == "overscaled":
            style = getattr(app, "_overscaled_style_preset_id", None) or (meta.get("overscaled_settings") or {}).get("style_preset_id")
            return build_scope(m, style)
        if m == "weather":
            return build_scope(m, style)
        if m == "normal":
            vs = meta.get("video_style") if isinstance(meta.get("video_style"), dict) else {}
            res = meta.get("style_resolution") if isinstance(meta.get("style_resolution"), dict) else {}
            style = vs.get("style_id") or res.get("style_id") or res.get("detected_style_id")
            return build_scope(m, style, meta.get("editing_system"))
        if m in ("pakmap", "hybrid"):
            # the Graphics-tab "Doc Style" switch changes the look of these two (settings["doc_style"]); a real, persisted choice
            return build_scope(m, "doc" if (getattr(app, "_settings", None) or {}).get("doc_style") else None)
        if m == "starmap":
            cinema = (ws.starmap_settings().get("cinema") if ws is not None and hasattr(ws, "starmap_settings") else None) or {}
            return build_scope(m, "cinema" if isinstance(cinema, dict) and cinema.get("enabled") else None)
        return build_scope(m)   # What If: no verified sub-style identifier exists
    except Exception:
        return build_scope(m)
