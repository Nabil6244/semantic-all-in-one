"""Research settings persistence — two different scopes, deliberately kept
separate:

- Engine path (interpreter + repo root): machine-level, lives in the
  existing global settings.json via app.load_settings()/save_settings() —
  the same place Pexels/Gemini API keys already live. It's "where is the
  tool installed on this machine," not a per-video choice.
- Per-project last-used inputs (topic/script path/urls/domain/max media):
  project.json["research_media"], namespaced exactly like
  visual_allocation's settings block (see visual_allocation/settings.py).

Script *text* is never persisted verbatim into project.json (it can be
large, and if loaded from a file the file itself is the source of truth) —
only the script file path, if one was used, plus a SHA-256 fingerprint of
the exact script text research was run against (see script_fingerprint
below) for staleness detection.

Staleness rule (deliberately asymmetric — see compute_script_fingerprint /
is_research_stale): research run WITH a script is bound to that exact
script text; a later edit invalidates it. Research run URL-only (no script
at the time) is property-bound, not script-bound — writing a script
afterwards must never invalidate it. That's why script_fingerprint is only
ever set when a script was actually part of the research input.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from research.models import ResearchSettings

if TYPE_CHECKING:
    from project_workspace import ProjectWorkspace

_META_KEY = "research_media"


def compute_script_fingerprint(script_text: str) -> str:
    """SHA-256 of the exact script text, normalized just enough (stripped)
    that trailing-whitespace-only edits don't spuriously mark research
    stale."""
    return hashlib.sha256((script_text or "").strip().encode("utf-8")).hexdigest()


def is_research_stale(stored_fingerprint: Optional[str], current_script_text: Optional[str]) -> bool:
    """Research is stale only when it WAS bound to a script (stored_fingerprint
    set) and the current script text no longer matches. URL-only research
    (stored_fingerprint is None/empty) is property-bound, not script-bound,
    and is never considered stale by this check — a script written or
    changed afterwards doesn't invalidate it."""
    if not stored_fingerprint:
        return False
    return compute_script_fingerprint(current_script_text or "") != stored_fingerprint


def load_project_research_settings(ws: "ProjectWorkspace") -> ResearchSettings:
    raw = (ws.read_meta() or {}).get(_META_KEY)
    if not isinstance(raw, dict):
        return ResearchSettings()
    return ResearchSettings(
        topic=str(raw.get("topic") or ""),
        script_path=str(raw.get("script_path") or ""),
        urls=list(raw.get("urls") or []),
        domain=str(raw.get("domain") or "auto"),
        max_media_per_property=int(raw.get("max_media_per_property") or 20),
        script_fingerprint=(str(raw["script_fingerprint"]) if raw.get("script_fingerprint") else None),
    )


def save_project_research_settings(ws: "ProjectWorkspace", settings: ResearchSettings) -> None:
    data = ws.read_meta() or {}
    data.update(ws.to_dict())
    data[_META_KEY] = {
        "topic": settings.topic,
        "script_path": settings.script_path,
        "urls": settings.urls,
        "domain": settings.domain,
        "max_media_per_property": settings.max_media_per_property,
        "script_fingerprint": settings.script_fingerprint,
    }
    ws._write_meta(data)


def load_engine_config(global_settings: Dict[str, Any]) -> Tuple[str, str]:
    """Returns (engine_root, engine_python) from the global settings dict
    (app.load_settings())."""
    return (
        str(global_settings.get("research_engine_root") or ""),
        str(global_settings.get("research_engine_python") or ""),
    )


def with_engine_config(global_settings: Dict[str, Any], engine_root: str, engine_python: str) -> Dict[str, Any]:
    """Returns a copy of global_settings with the engine path fields set —
    caller is responsible for calling app.save_settings(...) with the result."""
    updated = dict(global_settings)
    updated["research_engine_root"] = engine_root
    updated["research_engine_python"] = engine_python
    return updated
