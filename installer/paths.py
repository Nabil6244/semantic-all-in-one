"""Install destinations for app, Qwen runtime, and Qwen model."""

from __future__ import annotations

import os
import sys
from pathlib import Path


MODEL_DIR_NAME = "Qwen3-TTS-12Hz-1.7B-Base"
APP_DISPLAY_NAME = "Semantic YT Studio"
APP_BUNDLE_NAME = "Semantic YT Studio.app"
WIN_APP_DIR_NAME = "Semantic YT Studio"
WIN_EXE_NAME = "Semantic YT Studio.exe"


def videogen_home() -> Path:
    return Path.home() / ".videogen"


def runtime_root(platform_id: str) -> Path:
    return videogen_home() / "runtime" / "qwen" / platform_id


def model_root() -> Path:
    return videogen_home() / "qwen3-tts" / MODEL_DIR_NAME


def app_install_dir(platform_id: str) -> Path:
    if platform_id == "win-amd64":
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / WIN_APP_DIR_NAME
    if platform_id == "darwin-arm64":
        return Path("/Applications") / APP_BUNDLE_NAME
    raise ValueError(f"Unknown platform_id: {platform_id}")


def download_cache_dir() -> Path:
    return videogen_home() / "installer-cache"


def provisioned_python(platform_id: str) -> Path | None:
    """Return the expected python binary path if it already exists."""
    root = runtime_root(platform_id)
    if platform_id == "win-amd64":
        candidates = [
            root / "python.exe",
            root / "Scripts" / "python.exe",
            root / "python" / "python.exe",
            root / "bin" / "python.exe",
        ]
        names = ("python.exe",)
    else:
        candidates = [
            root / "bin" / "python",
            root / "bin" / "python3",
            root / "bin" / "python3.12",
            root / "python" / "bin" / "python",
            root / "python" / "bin" / "python3",
            root / "python" / "bin" / "python3.12",
        ]
        names = ("python", "python3", "python3.12")
    for path in candidates:
        if _usable_python(path):
            return path
    if not root.is_dir():
        return None
    for name in names:
        for found in root.rglob(name):
            if _usable_python(found) and found.name in names:
                return found
    return None


def _usable_python(path: Path) -> bool:
    """True for a real python binary (not a broken symlink)."""
    try:
        if not path.is_file():
            return False
        if path.is_symlink() and not path.resolve().exists():
            return False
        return True
    except OSError:
        return False


def windows_start_menu_dir() -> Path:
    programs = os.environ.get("APPDATA")
    if programs:
        return Path(programs) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
