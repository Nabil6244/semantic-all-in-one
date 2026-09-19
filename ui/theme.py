"""Shared design tokens for Semantic YT Studio (Phase 2: dark/light/system).

Every existing named constant below (BG, PANEL, TEXT, ACCENT, ...) is kept —
nothing that already reads ``T.BG`` etc. needs to change — but each one is
now *derived* from a semantic token table (``LIGHT`` / ``DARK``) selected by
the persisted appearance mode, instead of being a single hardcoded hex
value. Dark is the default (matches the existing look when no preference is
saved yet).

Persistence reuses app.py's existing ``settings.json`` store (same file as
the Pexels/Gemini keys) under the ``"theme_mode"`` key — no new persistence
mechanism. To avoid a circular import with app.py, this module reads/writes
that one key with its own tiny, independent helpers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

MODES = ("dark", "light", "system")


def _settings_path() -> Path:
    """Same file app.py's load_settings()/save_settings() use. Duplicated
    (not imported) deliberately: app.py imports ui.theme, so importing app
    from here would be circular."""
    try:
        frozen = bool(getattr(__import__("sys"), "frozen", False))
    except Exception:
        frozen = False
    base = Path.home() / ".videogen" if frozen else Path(__file__).resolve().parent.parent
    return base / "settings.json"


def _read_saved_mode() -> Optional[str]:
    try:
        path = _settings_path()
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        mode = data.get("theme_mode") if isinstance(data, dict) else None
        return mode if mode in MODES else None
    except (OSError, ValueError, TypeError):
        return None


def _write_saved_mode(mode: str) -> None:
    try:
        path = _settings_path()
        data = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, ValueError):
                data = {}
        data["theme_mode"] = mode
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _detect_system_mode() -> str:
    """Best-effort OS appearance detection. Falls back to dark — the
    project's long-standing default — whenever detection isn't available,
    never guesses light."""
    try:
        import darkdetect  # optional; not a new hard dependency

        resolved = darkdetect.theme()
        if resolved and str(resolved).lower() == "light":
            return "light"
        return "dark"
    except Exception:
        pass
    try:
        import subprocess
        import sys

        if sys.platform == "darwin":
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2,
            )
            # Key is absent entirely in Light mode -> non-zero exit, no stdout.
            return "dark" if "dark" in (out.stdout or "").strip().lower() else "light"
    except Exception:
        pass
    return "dark"


def _resolve(mode: str) -> str:
    return _detect_system_mode() if mode == "system" else mode


# ---------------------------------------------------------------------------
# Semantic token tables. Every group the Phase 2 spec calls for by name.
# ---------------------------------------------------------------------------

DARK = {
    "background": "#0B0D10",
    "surface": "#12151A",
    "surface_alt": "#0F1218",
    "surface_elevated": "#181C24",
    "surface_elevated_hover": "#1E2430",
    "row_alt": "#141820",
    "border": "#2A3140",
    "text_primary": "#E8EAED",
    "text_secondary": "#8B95A8",
    "accent": "#4F6BF6",
    "accent_hover": "#3D56E8",
    "accent_on_accent": "#FFFFFF",
    "selected": "#1A2240",
    "accent_border": "#3D5080",
    "success": "#34D399",
    "processing": "#60A5FA",
    "queued": "#64748B",
    "warning": "#FBBF24",
    "error": "#F87171",
    "error_bg": "#2A1A1A",
    "skipped": "#6B7280",
    "stepper_done": "#2F8F6E",
    "hover": "#1E2430",
    "disabled": "#3A4150",
    "timeline_bg": "#0F1218",
    "track": "#161B22",
    "track_alt": "#12161C",
    "clip_video": "#3D5080",
    "clip_image": "#3D5080",
    "clip_text": "#7C5CFA",
    "clip_graphics": "#C2664B",
    "clip_sfx": "#34A0A4",
    "clip_ambience": "#2F8F6E",
    "clip_music": "#B08900",
    "clip_voiceover": "#4F6BF6",
    "playhead": "#F87171",
}

LIGHT = {
    "background": "#F5F6F8",
    "surface": "#FFFFFF",
    "surface_alt": "#F0F1F4",
    "surface_elevated": "#FFFFFF",
    "surface_elevated_hover": "#E9ECF2",
    "row_alt": "#F3F4F7",
    "border": "#D7DBE3",
    "text_primary": "#1B1F27",
    "text_secondary": "#5B6270",
    "accent": "#3654E0",
    "accent_hover": "#2A44C4",
    "accent_on_accent": "#FFFFFF",
    "selected": "#E4E9FF",
    "accent_border": "#AAB8F0",
    "success": "#0E9F6E",
    "processing": "#2F80D6",
    "queued": "#8891A0",
    "warning": "#B7791F",
    "error": "#D64545",
    "error_bg": "#FBEAEA",
    "skipped": "#9AA1AD",
    "stepper_done": "#1F8F5E",
    "hover": "#E9ECF2",
    "disabled": "#C7CCD6",
    "timeline_bg": "#F0F1F4",
    "track": "#FFFFFF",
    "track_alt": "#F5F6F8",
    "clip_video": "#AAB8F0",
    "clip_image": "#AAB8F0",
    "clip_text": "#C8B8FA",
    "clip_graphics": "#F0B79F",
    "clip_sfx": "#9FE0E2",
    "clip_ambience": "#9FE0C0",
    "clip_music": "#F0D98C",
    "clip_voiceover": "#AAB8F0",
    "playhead": "#D64545",
}

_TABLES = {"dark": DARK, "light": LIGHT}

# Resolved once at import time from the persisted preference — this is what
# lets app.py's own module-level color constants (copied from these at ITS
# import time) start correctly themed without any startup ordering hacks:
# ui.theme is always imported (and thus resolved) before app.py's later
# top-level lines copy these values. See ui/theme.py module docstring and
# the Phase 2 report's THEME section for the live-toggle scope note.
MODE = _read_saved_mode() or "dark"
_ACTIVE_MODE = _resolve(MODE)
_TOKENS = _TABLES[_ACTIVE_MODE]


def get_token(name: str) -> str:
    return _TOKENS.get(name, DARK.get(name, "#000000"))


def _apply_active_tokens() -> None:
    """(Re)bind every legacy T.XXX constant from the active token table."""
    global BG, PANEL, PANEL_ALT, CARD, CARD_HOVER, ROW_ALT, BORDER
    global TEXT, MUTED, ACCENT, ACCENT_HOV, ACCENT_DARK, ACCENT_SEL, ACCENT_BORDER
    global SUCCESS, PROCESSING, QUEUED, WARNING, DANGER, DANGER_BG, SKIPPED, STEPPER_DONE
    global HOVER, DISABLED
    global TIMELINE_BG, TRACK, TRACK_ALT, PLAYHEAD
    global CLIP_VIDEO, CLIP_IMAGE, CLIP_TEXT, CLIP_GRAPHICS, CLIP_SFX, CLIP_AMBIENCE, CLIP_MUSIC, CLIP_VOICEOVER

    BG = _TOKENS["background"]
    PANEL = _TOKENS["surface"]
    PANEL_ALT = _TOKENS["surface_alt"]
    CARD = _TOKENS["surface_elevated"]
    CARD_HOVER = _TOKENS["surface_elevated_hover"]
    ROW_ALT = _TOKENS["row_alt"]
    BORDER = _TOKENS["border"]
    TEXT = _TOKENS["text_primary"]
    MUTED = _TOKENS["text_secondary"]
    ACCENT = _TOKENS["accent"]
    ACCENT_HOV = _TOKENS["accent_hover"]
    ACCENT_DARK = _TOKENS["accent_on_accent"]
    ACCENT_SEL = _TOKENS["selected"]
    ACCENT_BORDER = _TOKENS["accent_border"]
    SUCCESS = _TOKENS["success"]
    PROCESSING = _TOKENS["processing"]
    QUEUED = _TOKENS["queued"]
    WARNING = _TOKENS["warning"]
    DANGER = _TOKENS["error"]
    DANGER_BG = _TOKENS["error_bg"]
    SKIPPED = _TOKENS["skipped"]
    STEPPER_DONE = _TOKENS["stepper_done"]
    HOVER = _TOKENS["hover"]
    DISABLED = _TOKENS["disabled"]
    TIMELINE_BG = _TOKENS["timeline_bg"]
    TRACK = _TOKENS["track"]
    TRACK_ALT = _TOKENS["track_alt"]
    PLAYHEAD = _TOKENS["playhead"]
    CLIP_VIDEO = _TOKENS["clip_video"]
    CLIP_IMAGE = _TOKENS["clip_image"]
    CLIP_TEXT = _TOKENS["clip_text"]
    CLIP_GRAPHICS = _TOKENS["clip_graphics"]
    CLIP_SFX = _TOKENS["clip_sfx"]
    CLIP_AMBIENCE = _TOKENS["clip_ambience"]
    CLIP_MUSIC = _TOKENS["clip_music"]
    CLIP_VOICEOVER = _TOKENS["clip_voiceover"]


_apply_active_tokens()


def set_mode(mode: str) -> str:
    """Persist + apply a new appearance mode. Returns the *resolved* mode
    ("system" resolves to "dark"/"light" immediately).

    Mutates this module's constants in place, so any code that reads
    ``ui.theme.BG`` (etc.) *after* this call — including app.py's own
    module-level copies, which are re-synced by app.py's theme-apply helper
    — sees the new palette. Widgets already built with the old literal
    color baked in do not repaint themselves (CustomTkinter has no reactive
    binding to plain module globals); the caller is responsible for
    reconfiguring/rebuilding whatever chrome it wants to update live. See
    the Phase 2 report's THEME section for exactly what updates live vs.
    on next launch."""
    global MODE, _ACTIVE_MODE, _TOKENS
    if mode not in MODES:
        mode = "dark"
    MODE = mode
    _ACTIVE_MODE = _resolve(mode)
    _TOKENS = _TABLES[_ACTIVE_MODE]
    _apply_active_tokens()
    _write_saved_mode(mode)
    return _ACTIVE_MODE


def current_mode() -> str:
    return MODE


def active_appearance() -> str:
    """The resolved dark/light in effect right now (never "system")."""
    return _ACTIVE_MODE


# Layout (unaffected by theme — kept exactly as before)
SIDEBAR_WIDTH = 148
INSPECTOR_WIDTH = 260
TOPBAR_HEIGHT = 44
STATUSBAR_HEIGHT = 32
PAD = 10
PAD_SM = 6
PAD_LG = 14
RADIUS = 4  # restrained, not pill-like

# ---------------------------------------------------------------------------
# Design system extension (premium UI/UX pass): a centralized spacing rhythm,
# typography hierarchy, and control-sizing scale so nothing new scatters its
# own one-off numbers. Existing PAD/PAD_SM/PAD_LG/RADIUS above are kept
# as-is for call sites that already use them.
# ---------------------------------------------------------------------------

# 4px spacing rhythm (spec item 15).
SPACE_XXS = 2
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

# Typography hierarchy (spec item 14) — (size, weight) pairs, consumed as
# ctk.CTkFont(size=FONT_X[0], weight=FONT_X[1]).
FONT_APP_TITLE = (16, "bold")
FONT_WORKSPACE_TITLE = (15, "bold")
FONT_SECTION_TITLE = (11, "bold")
FONT_CONTROL_LABEL = (12, "normal")
FONT_SECONDARY_LABEL = (11, "normal")
FONT_METADATA = (10, "normal")
FONT_TIMELINE_LABEL = (9, "normal")
FONT_STATUS = (11, "normal")

# Control sizing scale — every new button/entry/switch should pick one of
# these rather than an ad hoc height.
CONTROL_H_SM = 24
CONTROL_H = 28
CONTROL_H_LG = 34
ICON_BTN_W = 30

FOCUS_RING_WIDTH = 2

# Sidebar navigation, grouped into a small primary "workspace" flow (the
# Phase 2 script -> visuals -> timeline -> audio -> graphics -> export path)
# and an "advanced" group for everything that already existed. Nothing was
# removed — advanced items are the exact same views, just re-bucketed.
NAV_ITEMS = (
    ("script", "Script", "workspace"),
    ("visual_plan", "Visuals", "workspace"),
    ("timeline", "Timeline", "workspace"),
    ("audio", "Audio", "workspace"),
    ("editor", "Editor", "workspace"),
    ("graphics", "Graphics", "workspace"),
    ("render", "Export", "workspace"),
    ("brand_style", "Brand & Style", "advanced"),
    ("research", "Research", "advanced"),
    ("assets", "Assets", "advanced"),
    ("music", "Music", "advanced"),
    ("editorial", "Editorial Stats", "advanced"),
    ("qa", "QA", "advanced"),
    ("about", "About & Ownership", "advanced"),
)

WORKFLOW_STEPS = ("INPUT", "PLAN", "ASSETS", "AUDIO", "EDITORIAL", "RENDER", "QA")
