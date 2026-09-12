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

Caching: metadata may carry ``actual_duration`` or legacy ``duration`` so we
avoid redundant probes when the file is unavailable. When a real local file
exists, a successful ffprobe always wins over stale cached values (provider
catalog lengths and old requested-duration leaks must not masquerade as the
delivered file).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

# Canonical metadata key for the measured length of the delivered file.
ACTUAL_DURATION_KEY = "actual_duration"
# What the operator asked for, recorded alongside so the two are never confused.
REQUESTED_DURATION_KEY = "requested_duration"
# Pre-existing key several providers already populate; treated as a *hint*
# only. When a local file exists, ffprobe overrides this value.
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
    """Reuse a duration already recorded (hint for when no file can be probed)."""
    if not isinstance(metadata, Mapping):
        return None
    for key in (ACTUAL_DURATION_KEY, LEGACY_DURATION_KEY):
        seconds = coerce_duration(metadata.get(key))
        if seconds is not None:
            return seconds
    return None


def _ffprobe_candidates() -> list[Path]:
    """Ordered search paths for bundled / packaged / PATH-adjacent ffprobe."""
    names = ("ffprobe.exe", "ffprobe") if sys.platform == "win32" else ("ffprobe", "ffprobe.exe")
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        roots.extend([exe_dir / "bin", exe_dir])
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "bin")
            roots.append(Path(meipass))
    # Dev checkout / module next to repo ``bin/``
    module_root = Path(__file__).resolve().parent
    roots.extend([module_root / "bin", module_root])
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        for name in names:
            cand = root / name
            key = str(cand)
            if key in seen:
                continue
            seen.add(key)
            out.append(cand)
    return out


def _resolve_ffprobe() -> Optional[str]:
    """Locate ffprobe on PATH or next to bundled ffmpeg / app binaries."""
    found = shutil.which("ffprobe")
    if found:
        return found
    for candidate in _ffprobe_candidates():
        if candidate.is_file():
            if sys.platform != "win32":
                try:
                    mode = candidate.stat().st_mode
                    if not (mode & 0o111):
                        candidate.chmod(mode | 0o111)
                except OSError:
                    pass
            return str(candidate.resolve())
    return None


def _log_probe_failure(
    *,
    media_path: Path,
    ffprobe: Optional[str],
    reason: str,
    fallback: Optional[float] = None,
) -> None:
    """Surface probe failures — never silent in packaged / editorial paths."""
    exists = bool(ffprobe and Path(ffprobe).is_file())
    fb = f"{fallback:.3f}s" if fallback is not None else "none"
    print(
        f"[DURATION] probe_failed path={media_path} "
        f"ffprobe={ffprobe or '(unresolved)'} exists={exists} "
        f"reason={reason} fallback={fb}",
        flush=True,
    )


def probe_media_duration(
    path: Path | str,
    *,
    log_failures: bool = True,
    fallback_for_log: Optional[float] = None,
) -> Optional[float]:
    """Measure a media file with ffprobe. None on any failure — never raises.

    Duration is advisory metadata: a probe that fails must leave the asset
    usable, not fail the scene. Failures are logged when ``log_failures``.
    """
    media_path = Path(path)
    ffprobe: Optional[str] = None
    try:
        if not media_path.is_file():
            if log_failures:
                _log_probe_failure(
                    media_path=media_path,
                    ffprobe=None,
                    reason="media_file_missing",
                    fallback=fallback_for_log,
                )
            return None
        ffprobe = _resolve_ffprobe()
        if not ffprobe:
            if log_failures:
                _log_probe_failure(
                    media_path=media_path,
                    ffprobe=None,
                    reason="ffprobe_unresolved",
                    fallback=fallback_for_log,
                )
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
            err = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:240]
            if log_failures:
                _log_probe_failure(
                    media_path=media_path,
                    ffprobe=ffprobe,
                    reason=f"ffprobe_exit_{proc.returncode}:{err or 'no_stderr'}",
                    fallback=fallback_for_log,
                )
            return None
        payload = json.loads(proc.stdout or "{}")
        seconds = coerce_duration((payload.get("format") or {}).get("duration"))
        if seconds is None and log_failures:
            # Stills often have no format duration — not an operational failure.
            if media_path.suffix.lower() not in {
                ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif",
            }:
                _log_probe_failure(
                    media_path=media_path,
                    ffprobe=ffprobe,
                    reason="ffprobe_empty_duration",
                    fallback=fallback_for_log,
                )
        return seconds
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        if log_failures:
            _log_probe_failure(
                media_path=media_path,
                ffprobe=ffprobe,
                reason=f"{type(exc).__name__}:{exc}",
                fallback=fallback_for_log,
            )
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

    When ``path`` points at a real video file, a successful probe always
    overrides stale ``duration`` / ``actual_duration`` cache entries.
    Cached metadata is used only when there is no file, or when probing fails
    (fallback, with a diagnostic log).
    """
    if not isinstance(metadata, dict):
        return None

    requested_seconds = coerce_duration(requested)
    if requested_seconds is not None:
        metadata[REQUESTED_DURATION_KEY] = requested_seconds

    if not is_video or path is None:
        return None

    media_path = Path(path)
    cached = cached_duration(metadata)
    seconds: Optional[float] = None

    if media_path.is_file():
        probed = probe_media_duration(
            media_path,
            log_failures=True,
            fallback_for_log=cached,
        )
        if probed is not None:
            seconds = probed
        else:
            # Deterministic fallback: keep prior cache if any; never invent.
            seconds = cached
    else:
        # No local file to validate — reuse cache (manifest / offline).
        seconds = cached

    if seconds is None:
        return None

    metadata[ACTUAL_DURATION_KEY] = seconds
    # Keep the long-standing key in step with the authoritative measurement.
    metadata[LEGACY_DURATION_KEY] = seconds
    return seconds
