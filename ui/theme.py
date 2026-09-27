"""Shared design tokens for Semantic YT Studio (Phase 2: dark/light/system).

Every existing named constant below (BG, PANEL, TEXT, ACCENT, ...) is kept —
nothing that already reads ``T.BG`` etc. needs to change — but each one is
now *derived* from a semantic token table (``LIGHT`` / ``DARK``) selected by
the persisted appearance mode, instead of being a single hardcoded hex
value. System (follow the OS light/dark setting) is the default when no
preference is saved yet.

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
MODE = _read_saved_mode() or "system"  # follow the OS appearance unless the user picked one
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


def active_tokens() -> dict:
    """A copy of the token table currently in effect."""
    return dict(_TOKENS)


# ---------------------------------------------------------------------------
# Live re-theme of ALREADY-BUILT widgets.
#
# Every themed widget was built with a literal hex from the active token table
# baked in (CustomTkinter has no reactive binding to module globals), so a
# toggle used to repaint only the shell chrome and left every view's content in
# the old palette — the half-dark/half-light window users saw. Because each of
# those literals IS a token value, the old palette can be mapped 1:1 onto the
# new one and every existing widget/canvas item reconfigured in place.
# ---------------------------------------------------------------------------

_CTK_COLOR_OPTIONS = (
    "fg_color", "bg_color", "text_color", "text_color_disabled", "border_color",
    "hover_color", "button_color", "button_hover_color", "progress_color",
    "scrollbar_button_color", "scrollbar_button_hover_color", "placeholder_text_color",
    "selected_color", "selected_hover_color", "unselected_color", "unselected_hover_color",
    "dropdown_fg_color", "dropdown_hover_color", "dropdown_text_color", "checkmark_color",
    "label_fg_color",
)
_TK_COLOR_OPTIONS = (
    "background", "foreground", "highlightbackground", "highlightcolor",
    "insertbackground", "selectbackground", "selectforeground", "activebackground",
    "activeforeground", "troughcolor",
)
_CANVAS_ITEM_COLOR_OPTIONS = ("fill", "outline", "activefill", "activeoutline")


_TEXT_TOKEN_PRIORITY = ("accent_on_accent", "text_primary", "text_secondary")


def color_remap(old_tokens: dict, new_tokens: dict, role: str = "fill") -> dict:
    """{OLD_HEX_UPPER: new_hex}. Several tokens can share one hex (light
    "#FFFFFF" is both the surface AND the text-on-accent color), so the
    winner depends on how the color is used: role="text" prefers the text
    tokens, role="fill" prefers surfaces (text-on-accent last). Timeline
    clip tokens always lose to UI tokens."""

    def rank(key: str) -> tuple:
        is_text_token = key in _TEXT_TOKEN_PRIORITY
        text_rank = _TEXT_TOKEN_PRIORITY.index(key) if is_text_token else len(_TEXT_TOKEN_PRIORITY)
        if role == "text":
            return (key.startswith("clip_"), text_rank)
        return (key.startswith("clip_"), key == "accent_on_accent", 0)

    mapping: dict = {}
    for key in sorted(old_tokens, key=rank):
        old, new = old_tokens.get(key), new_tokens.get(key)
        if isinstance(old, str) and isinstance(new, str):
            mapping.setdefault(old.upper(), new)
    return mapping


def color_remaps(old_tokens: dict, new_tokens: dict) -> dict:
    return {role: color_remap(old_tokens, new_tokens, role) for role in ("fill", "text")}


_TEXT_ROLE_OPTIONS = frozenset({
    "text_color", "text_color_disabled", "placeholder_text_color", "dropdown_text_color",
    "checkmark_color", "foreground", "selectforeground", "activeforeground", "insertbackground",
})


def remap_color_value(value, mapping: dict):
    """Remap a hex string, or hexes nested in tuples/lists/dicts (module-level
    palettes like app.py's SOURCE_BADGE/STATUS_COLOR); anything else as-is."""
    if isinstance(value, str):
        return mapping.get(value.upper(), value)
    if isinstance(value, tuple):
        return tuple(remap_color_value(v, mapping) for v in value)
    if isinstance(value, list):
        return [remap_color_value(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: remap_color_value(v, mapping) for k, v in value.items()}
    return value


def _recolor_one(widget, maps: dict) -> None:
    # Try both vocabularies on every widget: CTk windows (the app root, CTk
    # dialogs) and CustomTkinter's own internal CTkCanvas only answer to some
    # of each; an option a widget doesn't support simply fails cget().
    is_ctk = type(widget).__module__.startswith("customtkinter") or hasattr(widget, "_fg_color")
    for opt in _CTK_COLOR_OPTIONS + _TK_COLOR_OPTIONS:
        try:
            current = widget.cget(opt)
        except Exception:
            continue  # widget doesn't have this option
        # (light, dark) tuples are CustomTkinter's own appearance-mode pairs —
        # ctk.set_appearance_mode() already handles those.
        mapping = maps["text" if opt in _TEXT_ROLE_OPTIONS else "fill"]
        if isinstance(current, str) and current.upper() in mapping:
            try:
                widget.configure(**{opt: mapping[current.upper()]})
            except Exception:
                pass
    if widget.winfo_class() == "Canvas" and not is_ctk:
        try:
            items = widget.find_all()
        except Exception:
            items = ()
        for item in items:
            try:
                mapping = maps["text" if widget.type(item) == "text" else "fill"]
            except Exception:
                mapping = maps["fill"]
            for opt in _CANVAS_ITEM_COLOR_OPTIONS:
                try:
                    current = widget.itemcget(item, opt)
                except Exception:
                    continue
                if isinstance(current, str) and current.upper() in mapping:
                    try:
                        widget.itemconfigure(item, **{opt: mapping[current.upper()]})
                    except Exception:
                        pass


def recolor_widget_tree(root, maps: dict) -> int:
    """Reconfigure every widget under (and including) ``root`` from the old
    palette to the new one (``maps`` from color_remaps()). Returns how many
    widgets were visited."""
    stack, seen = [root], 0
    while stack:
        widget = stack.pop()
        seen += 1
        _recolor_one(widget, maps)
        try:
            stack.extend(widget.winfo_children())
        except Exception:
            pass
    return seen


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
    ("visual_director", "Visual Director", "workspace"),
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
