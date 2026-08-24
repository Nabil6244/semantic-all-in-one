"""Windows: hide black console windows for Node / ffmpeg / ffprobe / ffplay / yt-dlp.

Console-subsystem .exe children still flash a CMD window on Windows even when
stdout/stderr are redirected, unless CREATE_NO_WINDOW is set. macOS/Linux are
no-ops.

`install()` patches ``subprocess.Popen`` globally so third-party code (yt-dlp's
ffmpeg spawns, etc.) also stays silent. Safe to call more than once.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

_CREATE_NO_WINDOW = 0x08000000
_installed = False


def create_no_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW))


def hidden_kwargs() -> dict[str, Any]:
    if sys.platform != "win32":
        return {}
    return {"creationflags": create_no_window_flag()}


def _merge_creationflags(kwargs: dict[str, Any]) -> dict[str, Any]:
    if sys.platform != "win32":
        return kwargs
    flag = create_no_window_flag()
    # Preserve caller flags (e.g. CREATE_NEW_PROCESS_GROUP) and always OR in
    # CREATE_NO_WINDOW so console .exes never flash a black box.
    kwargs = dict(kwargs)
    kwargs["creationflags"] = int(kwargs.get("creationflags") or 0) | flag
    return kwargs


def run(cmd, **kwargs):
    return subprocess.run(cmd, **_merge_creationflags(kwargs))


def popen(cmd, **kwargs):
    return subprocess.Popen(cmd, **_merge_creationflags(kwargs))


def check_output(cmd, **kwargs):
    return subprocess.check_output(cmd, **_merge_creationflags(kwargs))


def install() -> None:
    """Patch subprocess.Popen so every Windows child process is console-hidden.

    yt-dlp's FFmpegFD calls subprocess without CREATE_NO_WINDOW; without this
    patch, Generate Assets flashes a black CMD box on every YouTube/ffmpeg
    probe. Call once at app startup (before any generation work).
    """
    global _installed
    if sys.platform != "win32" or _installed:
        return
    _installed = True

    flag = create_no_window_flag()
    _OrigPopen = subprocess.Popen

    class _HiddenPopen(_OrigPopen):
        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = int(kwargs.get("creationflags") or 0) | flag
            super().__init__(*args, **kwargs)

    subprocess.Popen = _HiddenPopen  # type: ignore[misc, assignment]
    # Keep a handle for tests / debugging.
    subprocess._videogen_orig_popen = _OrigPopen  # type: ignore[attr-defined]
    subprocess._videogen_no_console = True  # type: ignore[attr-defined]


# Install on import for any code path that pulls this module in.
install()
