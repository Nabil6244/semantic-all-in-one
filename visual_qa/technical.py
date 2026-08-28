"""Deterministic technical QA — no vision API."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from providers.base import MediaType


@dataclass
class TechnicalReport:
    ok: bool
    score: float
    duration: Optional[float]
    width: int
    height: int
    issues: list[str]


def _ffprobe() -> str:
    import shutil

    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe not available")
    return path


def probe_local_media(path: Path) -> Tuple[Optional[float], int, int]:
    """Return (duration_sec, width, height) for a local media file."""
    path = Path(path)
    if not path.is_file():
        return None, 0, 0
    try:
        proc = subprocess.run(
            [
                _ffprobe(),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return None, 0, 0
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        w = h = 0
        if streams and isinstance(streams[0], dict):
            w = int(streams[0].get("width") or 0)
            h = int(streams[0].get("height") or 0)
        dur_raw = (data.get("format") or {}).get("duration")
        dur = float(dur_raw) if dur_raw else None
        return dur, w, h
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return None, 0, 0


def check_technical(
    path: Path,
    media_type: MediaType,
    *,
    is_archival: bool = False,
) -> TechnicalReport:
    issues: list[str] = []
    path = Path(path)
    if not path.is_file():
        return TechnicalReport(False, 0.0, None, 0, 0, ["missing file"])

    dur, w, h = probe_local_media(path)
    if media_type == MediaType.VIDEO:
        if dur is None or dur <= 0.05:
            issues.append("invalid or zero duration")
        elif dur < 0.8:
            issues.append("clip very short")
    if w <= 0 or h <= 0:
        issues.append("missing dimensions")
    else:
        if h > w * 1.15:
            issues.append("vertical framing")
        min_w = 480 if is_archival else 640
        min_h = 270 if is_archival else 360
        if w < min_w or h < min_h:
            issues.append(f"low resolution ({w}x{h})")

    score = 1.0
    if "missing file" in issues:
        score = 0.0
    else:
        if "invalid or zero duration" in issues:
            score -= 0.6
        if "clip very short" in issues:
            score -= 0.15
        if "vertical framing" in issues:
            score -= 0.35
        if any("low resolution" in i for i in issues):
            score -= 0.25 if is_archival else 0.4
        if w > 0 and h > 0 and w >= h:
            score = min(1.0, score + 0.05)
    score = max(0.0, min(1.0, score))
    return TechnicalReport(
        ok=score >= 0.5 and "missing file" not in issues,
        score=score,
        duration=dur,
        width=w,
        height=h,
        issues=issues,
    )
