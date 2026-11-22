"""PK: the Pakistan documentary style (first made for "Vietnam vs Pakistan"). The Normal video engine with one fixed recipe, so a PK
project always comes out the same without touching the app-wide switches:

- Hybrid Map graphics + sound design, drawn in the Doc Style look; graphics come from the CSV `gfx` column (charts, maps, lessons)
- no Smart Text word pop-ups (they flashed single words; the CSV graphics carry the text)
- the normal sound effects kept under the Hybrid sound design, at high intensity, with scene ambience
- the background music a little above the Music Director's level (the narration and music are levelled first: audio_level.py)
- Urdu (or any language) narration: the CSV's `on_screen_en` column gives the English on-screen text (english_overlay.py)

The pick is saved in project.json ("pk_style": true), so reopening the project keeps PK. Nothing runs until Generate.
app.py / style_pages call: is_active(app), remember(app, on), setting(app, key, default), smart_settings(settings)."""

from __future__ import annotations

import dataclasses
from typing import Any

STYLE = "PK"
META_KEY = "pk_style"

# settings.json keys PK decides for its own renders (the app-wide values are left as they are)
RECIPE = {
    "normal_hybrid_style": True,
    "doc_style": True,
    "smart_text_effects": False,
    "hybrid_keep_sfx": True,
    "normal_hybrid_fill": False,
    "smart_sound_effects_intensity": "high",
    "music_boost_db": 6.0,
}

BLURB = ("Pakistan documentaries in any language (Urdu narration welcome): footage and maps that follow the voice, English on-screen "
         "text, charts and numbers from the script, Hybrid Map graphics and sound, effects and music. From a scene CSV + your voiceover.")
CARD = ("☪", "Pakistan documentaries, maps, charts and English text", "A scene CSV (gfx + on_screen_en) + your voiceover",
        "Pakistan vs the world, economy, industry, history")


def is_active(app: Any) -> bool:
    """The open project's saved pick, else the session flag."""
    ws = getattr(app, "_workspace", None)
    if ws is not None and hasattr(ws, "read_meta"):
        try:
            return bool(ws.read_meta().get(META_KEY))
        except Exception:
            pass
    return getattr(app, "_pk_active", False) is True


def remember(app: Any, on: bool) -> None:
    """Save the pick in project.json (no project open: the session flag only)."""
    app._pk_active = bool(on)
    ws = getattr(app, "_workspace", None)
    if ws is None or not hasattr(ws, "read_meta") or not hasattr(ws, "_write_meta"):
        return
    try:
        data = ws.read_meta()
        if bool(data.get(META_KEY)) == bool(on):
            return
        if hasattr(ws, "to_dict"):
            data.update(ws.to_dict())
        if on:
            data[META_KEY] = True
        else:
            data.pop(META_KEY, None)
        ws._write_meta(data)
    except Exception:
        pass


def setting(app: Any, key: str, default: Any = None) -> Any:
    """A settings.json value as this render sees it: PK's recipe when PK is the project's style, else the app setting."""
    if key in RECIPE and is_active(app):
        return RECIPE[key]
    return (getattr(app, "_settings", None) or {}).get(key, default)


def smart_settings(settings: Any) -> Any:
    """The render's Smart Editing settings with PK's recipe: no word pop-ups, effects and ambience on, effects at high intensity."""
    try:
        return dataclasses.replace(settings, text_effects=False, sound_effects=True, scene_ambience=True,
                                   sound_effects_intensity="high", intensity="high")
    except Exception:
        return settings
