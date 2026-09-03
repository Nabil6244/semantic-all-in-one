"""Research settings persistence — three different scopes, deliberately kept
separate:

- Engine path (interpreter + repo root): machine-level, lives in the
  existing global settings.json via app.load_settings()/save_settings() —
  the same place Pexels/Gemini API keys already live. It's "where is the
  tool installed on this machine," not a per-video choice.
- RealtyAPI API key: same machine-level global settings.json store as
  Pexels/Gemini (see load_realtyapi_key/with_realtyapi_key below), but
  unlike Pexels this key is deliberately NOT exposed through any
  general-purpose provider/config path — this module is the only supported
  way to read it, and the only caller today is ui.views.ResearchView (the
  Research / Analyze Script tab). A future RealtyAPI provider must import
  load_realtyapi_key from here rather than reading global_settings directly,
  so the property-research scoping stays enforced in one place. Phase 1
  only: nothing in this module calls RealtyAPI or performs any network
  request — this is configuration storage only.
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
import sys
from pathlib import Path
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


def _vendored_engine_root() -> str:
    """research/engine/app/ — the engine's own package, vendored directly
    into this repo (lightweight core deps only, see research/engine/README.md)
    so the default case needs no user-configured path at all."""
    vendored = Path(__file__).resolve().parent / "engine"
    return str(vendored) if (vendored / "app").is_dir() else ""


def load_engine_config(global_settings: Dict[str, Any]) -> Tuple[str, str]:
    """Returns (engine_root, engine_python) from the global settings dict
    (app.load_settings()) — an explicit saved override always wins.

    With nothing saved, defaults to the vendored engine run with this
    process's own interpreter (sys.executable), so Manual Research works
    with no configuration. That default is skipped for a frozen/packaged
    build: a PyInstaller executable can't be invoked as `<exe> -m
    some.module` the way a real `python` binary can, so a packaged build
    still needs an explicit external engine configured here until a bundled
    interpreter exists for this (separate, not-yet-done work) — leaving
    both empty in that case makes PropertyResearchProvider.is_configured()
    correctly report "not configured" instead of silently trying to run the
    frozen app's own executable as if it were `python`.
    """
    root = str(global_settings.get("research_engine_root") or "")
    python_path = str(global_settings.get("research_engine_python") or "")
    if not getattr(sys, "frozen", False):
        if not root:
            root = _vendored_engine_root()
        if not python_path:
            python_path = sys.executable or ""
    return root, python_path


def with_engine_config(global_settings: Dict[str, Any], engine_root: str, engine_python: str) -> Dict[str, Any]:
    """Returns a copy of global_settings with the engine path fields set —
    caller is responsible for calling app.save_settings(...) with the result."""
    updated = dict(global_settings)
    updated["research_engine_root"] = engine_root
    updated["research_engine_python"] = engine_python
    return updated


# --- RealtyAPI key (Phase 1: storage only, see module docstring) -----------
#
# Mirrors the Pexels key exactly in HOW it's stored (same global
# settings.json, same "explicit saved value, blank means unconfigured"
# semantics, same PEXELS_API_KEY-style environment fallback) — see
# app.py's pexels_key_var / save_key() for that pattern. It deliberately
# does NOT mirror WHERE Pexels is read from: Pexels is a general-purpose
# stock provider readable by any part of the app, RealtyAPI is not — this
# module (research.settings) is its only access path. A future Phase 2
# RealtyAPI provider must import load_realtyapi_key from here rather than
# reading app._settings/global_settings directly.

def load_realtyapi_key(global_settings: Dict[str, Any]) -> str:
    """The user's saved RealtyAPI key, or REALTYAPI_API_KEY from the
    environment when nothing is saved. Empty string when neither is set —
    never raises, never guesses a key. No network request is made here."""
    import os

    saved = str(global_settings.get("realtyapi_api_key") or "").strip()
    if saved:
        return saved
    return os.environ.get("REALTYAPI_API_KEY", "").strip()


def with_realtyapi_key(global_settings: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Returns a copy of global_settings with the RealtyAPI key set — caller
    is responsible for calling app.save_settings(...)/_persist_global_settings()
    with the result, exactly as with_engine_config() already works."""
    updated = dict(global_settings)
    updated["realtyapi_api_key"] = (api_key or "").strip()
    return updated


# --- Property Image Source switch (Phase 2) --------------------------------
#
# Controls ONLY which pipeline supplies property IMAGE candidates. Same
# storage convention as everything else above: global settings.json,
# explicit-value-or-default semantics, no new settings system.

PROPERTY_IMAGE_SOURCES = ("existing", "realtyapi", "both")
DEFAULT_PROPERTY_IMAGE_SOURCE = "existing"


def load_property_image_source(global_settings: Dict[str, Any]) -> str:
    """The saved Property Image Source, defaulting to "existing" (today's
    behavior, zero RealtyAPI calls) when unset or invalid."""
    value = str(global_settings.get("property_image_source") or "").strip().lower()
    return value if value in PROPERTY_IMAGE_SOURCES else DEFAULT_PROPERTY_IMAGE_SOURCE


def with_property_image_source(global_settings: Dict[str, Any], value: str) -> Dict[str, Any]:
    """Returns a copy of global_settings with the Property Image Source set
    — caller persists it exactly as with_engine_config()/with_realtyapi_key()
    already work. An invalid value is normalized to the default rather than
    stored as-is or rejected."""
    updated = dict(global_settings)
    normalized = str(value or "").strip().lower()
    updated["property_image_source"] = (
        normalized if normalized in PROPERTY_IMAGE_SOURCES else DEFAULT_PROPERTY_IMAGE_SOURCE
    )
    return updated
