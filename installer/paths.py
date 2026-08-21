"""Install destinations for app, Qwen runtime, and Qwen model."""

from __future__ import annotations

import os
import sys
from pathlib import Path


MODEL_DIR_NAME = "Qwen3-TTS-12Hz-1.7B-Base"
APP_BUNDLE_NAME = "SemanticAllInOne.app"
WIN_APP_DIR_NAME = "VideoGenerator"
WIN_EXE_NAME = "SemanticAllInOne.exe"


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
        ]
    else:
        candidates = [
            root / "bin" / "python",
            root / "bin" / "python3",
        ]
    for path in candidates:
        if path.is_file():
            return path
    if not root.is_dir():
        return None
    names = ("python.exe",) if platform_id == "win-amd64" else ("python", "python3")
    for name in names:
        for found in root.rglob(name):
            if found.is_file() and found.name in names:
                return found
    return None


def windows_start_menu_dir() -> Path:
    programs = os.environ.get("APPDATA")
    if programs:
        return Path(programs) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
