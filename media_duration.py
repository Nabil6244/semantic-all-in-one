"""Actual duration of a resolved media file — the file is authoritative.

Three durations exist in this system and must never be conflated:

    requested_duration   what the operator asked a generator for (a setting)
    actual_duration      what the delivered file really is (measured here)
    scene duration       what the narration needs (voiceover stays authoritative)

Flow in particular does not honour the requested video duration — Google
removed that parameter from the endpoint — so assuming the setting was applied
silently corrupts editorial timing. This module measures the delivered file
instead. It is deliberately provider-agnostic: Flow, stock, YouTube, archive
and manual clips all flow through the same probe.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional

# Canonical metadata key for the measured length of the delivered file.
ACTUAL_DURATION_KEY = "actual_duration"
# What the operator asked for, recorded alongside so the two are never confused.
REQUESTED_DURATION_KEY = "requested_duration"
# Pre-existing key several providers already populate; accepted as a cached
# measurement so a valid manifest never triggers a redundant ffprobe.
LEGACY_DURATION_KEY = "duration"

_PROBE_TIMEOUT_S = 30


def coerce_duration(value: Any) -> Optional[float]:
    """A duration is only usable if it is a finite, strictly positive number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds != seconds or seconds in (float("inf"), float("-inf")):
        return None
    if seconds <= 0:
        return None
    return round(seconds, 3)


def cached_duration(metadata: Optional[Mapping[str, Any]]) -> Optional[float]:
    """Reuse a duration already recorded, so cached assets are not re-probed."""
    if not isinstance(metadata, Mapping):
        return None
    for key in (ACTUAL_DURATION_KEY, LEGACY_DURATION_KEY):
        seconds = coerce_duration(metadata.get(key))
        if seconds is not None:
            return seconds
    return None


def probe_media_duration(path: Path | str) -> Optional[float]:
    """Measure a media file with ffprobe. None on any failure — never raises.

    Duration is advisory metadata: a probe that fails must leave the asset
    usable, not fail the scene.
    """
    try:
        media_path = Path(path)
        if not media_path.is_file():
            return None
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        proc = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
            check=False,
        )
        if proc.returncode != 0:
            return None
        payload = json.loads(proc.stdout or "{}")
        return coerce_duration((payload.get("format") or {}).get("duration"))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return None


def annotate_actual_duration(
    metadata: dict,
    path: Path | str | None,
    *,
    is_video: bool,
    requested: Any = None,
) -> Optional[float]:
    """Record the delivered file's real duration on an asset's metadata.

    Images are left alone — they have no intrinsic duration and the renderer
    decides how long they are shown. Returns the duration recorded, or None.
    """
    if not isinstance(metadata, dict):
        return None

    requested_seconds = coerce_duration(requested)
    if requested_seconds is not None:
        metadata[REQUESTED_DURATION_KEY] = requested_seconds

    if not is_video or path is None:
        return None

    seconds = cached_duration(metadata)
    if seconds is None:
        seconds = probe_media_duration(path)
    if seconds is None:
        return None

    metadata[ACTUAL_DURATION_KEY] = seconds
    # Keep the long-standing key in step for anything already reading it.
    metadata.setdefault(LEGACY_DURATION_KEY, seconds)
    return seconds
