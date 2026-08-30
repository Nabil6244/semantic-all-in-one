"""Shared access to the Semantic YT Studio brand assets.

Kept separate from app.py so the login dialog and the views can show the
wordmark without importing the application module (which would be circular).

  assets/logo.png            square "S" mark — app icon source, topbar avatar
  assets/logo_wordmark.png   full lockup — login, About & Ownership
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

APP_NAME = "Semantic YT Studio"

_CACHE: dict = {}


def _assets_dir() -> Path:
    """Works in dev and inside a PyInstaller bundle."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "assets"
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent.parent / "assets"


def wordmark_path() -> Optional[Path]:
    p = _assets_dir() / "logo_wordmark.png"
    return p if p.is_file() else None


def mark_path() -> Optional[Path]:
    p = _assets_dir() / "logo.png"
    return p if p.is_file() else None


def wordmark_image(height: int = 40):
    """CTkImage of the full lockup scaled to `height`, aspect preserved.

    Returns None when the asset or Pillow is unavailable so every caller can
    fall back to a text title rather than failing to build its window.
    """
    key = ("wordmark", int(height))
    if key in _CACHE:
        return _CACHE[key]
    path = wordmark_path()
    image = None
    if path is not None:
        try:
            import customtkinter as ctk
            from PIL import Image

            src = Image.open(path).convert("RGBA")
            w, h = src.size
            scaled = (max(1, round(w * (height / h))), max(1, int(height)))
            image = ctk.CTkImage(light_image=src, dark_image=src, size=scaled)
        except Exception:
            image = None
    _CACHE[key] = image
    return image
