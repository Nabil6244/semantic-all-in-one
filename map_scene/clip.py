"""Recognize a rendered map clip (it carries a marker in its MP4 metadata)."""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path

MAP_CLIP_MARKER = "semantic-yt-studio:map-scene"


def is_map_clip(path) -> bool:
    """True for a map-scene MP4. Map clips hold their last frame when the
    scene is longer than the clip — never loop or cut into replayed shots."""
    try:
        p = Path(path)
        if p.suffix.lower() not in (".mp4", ".mov", ".m4v") or not p.is_file():
            return False
        st = p.stat()
    except (OSError, TypeError, ValueError):
        return False
    return _probe_marker(str(p), st.st_size, st.st_mtime_ns)


@lru_cache(maxsize=512)
def _probe_marker(path: str, _size: int, _mtime_ns: int) -> bool:
    try:
        from media_duration import _resolve_ffprobe
        from providers import hidden_subprocess as hs

        ffprobe = _resolve_ffprobe()
        if not ffprobe:
            return False
        out = hs.run([ffprobe, "-v", "error", "-show_entries", "format_tags=comment", "-of", "json", path],
                     capture_output=True, text=True, timeout=20)
        tags = (json.loads(out.stdout or "{}").get("format") or {}).get("tags") or {}
        return any(str(v).strip() == MAP_CLIP_MARKER for k, v in tags.items() if k.lower() == "comment")
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
