"""A scene file's real picture size, and the short tag the Visual Plan shows for it ("4K", "1080p", "720p ⚠" ...).

Sizes are read from the file itself (an image header, or ffprobe for video), not from what a provider advertised, and
memoized per (path, size, mtime) like media_metadata_cache, so a long Visual Plan costs one probe per file per session.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Optional, Tuple

_lock = threading.Lock()
_cache: dict[tuple, Optional[Tuple[int, int]]] = {}

# The default export height (1080p); a project exporting in 4K passes 2160. The tag warns below it.
EXPORT_HEIGHT = 1080


def _identity(path) -> Optional[tuple]:
    try:
        p = Path(path)
        st = p.stat()
        return (str(p.resolve()), st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def _probe(path: Path) -> Optional[Tuple[int, int]]:
    try:
        from PIL import Image

        with Image.open(path) as im:   # reads the header only
            return int(im.width), int(im.height)
    except Exception:
        pass
    try:
        from providers.media_clip.ffmpeg_clip import _ffprobe
        from providers import hidden_subprocess

        out = hidden_subprocess.run(
            [_ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
        s = (json.loads(out or "{}").get("streams") or [{}])[0]
        w, h = int(s.get("width") or 0), int(s.get("height") or 0)
        return (w, h) if w and h else None
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return None


def probe_size(path) -> Optional[Tuple[int, int]]:
    """(width, height) of an image or video file, or None when it cannot be read."""
    key = _identity(path)
    if key is None:
        return None
    with _lock:
        if key in _cache:
            return _cache[key]
    size = _probe(Path(path))
    with _lock:
        _cache[key] = size
    return size


def equivalent_height(width: int, height: int) -> int:
    """The 16:9 height this picture can fill: a 3840x1600 frame is as sharp across a 16:9 screen as 2160 lines."""
    return int(max(min(width, height), max(width, height) * 9 / 16))


def resolution_tag(width: int, height: int, export_height: int = EXPORT_HEIGHT) -> str:
    """"4K" / "1440p" / "1080p" / "720p" / "SD", with " ⚠" when it is below the video's export size."""
    eq = equivalent_height(width, height)
    tag = "4K" if eq >= 2160 else "1440p" if eq >= 1440 else "1080p" if eq >= 1080 else "720p" if eq >= 720 else "SD"
    return f"{tag} ⚠" if eq < export_height else tag


def clear() -> None:
    with _lock:
        _cache.clear()
