"""Resolve supported installer platforms; reject unsupported machines."""

from __future__ import annotations

import platform
import sys
from typing import Optional


SUPPORTED = frozenset({"win-amd64", "darwin-arm64"})


class UnsupportedPlatformError(Exception):
    """Raised when this machine cannot run the online installer."""


def detect_platform() -> str:
    """Return win-amd64 or darwin-arm64, or raise UnsupportedPlatformError."""
    system = sys.platform
    machine = platform.machine().lower()

    if system == "win32":
        if machine in ("amd64", "x86_64", "x64"):
            return "win-amd64"
        raise UnsupportedPlatformError(
            f"Windows {machine} is not supported. Video Generator requires a 64-bit (x64) PC."
        )

    if system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "darwin-arm64"
        raise UnsupportedPlatformError(
            "Intel Macs are not supported. Video Generator requires an Apple Silicon Mac "
            "(M1, M2, M3, or newer)."
        )

    raise UnsupportedPlatformError(
        f"Unsupported operating system ({system}). "
        "Video Generator supports Windows x64 and macOS Apple Silicon only."
    )


def try_detect_platform() -> Optional[str]:
    try:
        return detect_platform()
    except UnsupportedPlatformError:
        return None
