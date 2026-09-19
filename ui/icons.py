"""Lightweight, dependency-free icon glyphs (Premium UI/UX pass).

No icon font, no image assets, no new UI framework — just a centralized
Unicode-glyph map so every button that needs "the split icon" or "the undo
icon" draws the SAME character, in the SAME place, instead of every call
site picking its own text. Works anywhere a CTkLabel/CTkButton text= would.
"""

from __future__ import annotations

GLYPHS = {
    "play": "▶",
    "pause": "⏸",
    "stop": "⏹",
    "undo": "↶",
    "redo": "↷",
    "split": "✂",
    "cut": "✂",
    "delete": "🗑",
    "duplicate": "⧉",
    "zoom_in": "+",
    "zoom_out": "−",
    "snap": "⌁",
    "mute": "🔇",
    "unmute": "🔊",
    "solo": "S",
    "lock": "🔒",
    "unlock": "🔓",
    "settings": "⚙",
    "export": "⬆",
    "search": "🔍",
    "add": "+",
    "replace": "⇄",
    "close": "✕",
    "expand": "⤢",
    "collapse": "⤡",
    "chevron_down": "▾",
    "chevron_right": "▸",
    "theme_dark": "🌙",
    "theme_light": "☀",
    "theme_system": "🖥",
    "seek_back": "⏮",
    "seek_fwd": "⏭",
    "info": "ⓘ",
    "warning": "⚠",
    "error": "✕",
    "success": "✓",
}


def icon(name: str, fallback: str = "") -> str:
    return GLYPHS.get(name, fallback or "•")
