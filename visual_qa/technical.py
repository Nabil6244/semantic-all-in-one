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


# Header-only fast path for complete, ordinary still images.
#
# Spawning ffprobe costs ~27 ms per file, and every local still is probed
# once per scene (1200-row CSV of stills: ~33 s of a 44 s asset pass). For the
# three formats below the answer is fully determined by the file header, so
# it is read in-process with Pillow's format plugin (header parse only, no
# pixel decode). The fast path returns EXACTLY what ffprobe would, verified
# against ffprobe 8.x (test_perf_visual_qa.py):
#   * width/height are the stored (coded) dimensions — EXIF orientation is
#     NOT applied by either tool; CMYK / grayscale / palette / 16-bit / alpha
#     are irrelevant to the size;
#   * duration: a .jpg/.jpeg is opened by ffprobe's image2 demuxer, which
#     reports one frame at its default 25 fps -> 0.04 s; .png (png_pipe) and
#     .webp (webp_pipe) report no duration -> None. A JPEG small enough to
#     fit whole in ffprobe's first 2048-byte probe buffer is instead claimed
#     by jpeg_pipe (no duration) — measured: <=1863 B jpeg_pipe, >=2285 B
#     image2 — so JPEGs under _JPEG_MIN_FAST_BYTES always use ffprobe.
# Anything uncertain falls through to ffprobe unchanged: other extensions,
# content that does not match its extension, animated PNG/WebP, MPO JPEGs,
# truncated or trailing-data files, zero sizes, any parse error. Video never
# takes this path.
_STILL_EXT_FORMAT = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}
_STILL_DURATION = {"PNG": None, "JPEG": 0.04, "WEBP": None}
_JPEG_MIN_FAST_BYTES = 16 * 1024
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def _still_file_complete(fmt: str, fp, size: int) -> bool:
    """Signature matches the extension's format and the file ends where
    that format says it must (no truncation, no trailing data)."""
    fp.seek(0)
    head = fp.read(16)
    if fmt == "PNG":
        if not head.startswith(_PNG_SIG) or size < 8 + 25 + 12:
            return False
        fp.seek(size - 12)
        return fp.read(12) == _PNG_IEND
    if fmt == "JPEG":
        if not head.startswith(b"\xff\xd8\xff") or size < _JPEG_MIN_FAST_BYTES:
            return False
        fp.seek(size - 2)
        return fp.read(2) == b"\xff\xd9"
    if fmt == "WEBP":
        return (
            len(head) >= 16
            and head[:4] == b"RIFF"
            and head[8:12] == b"WEBP"
            and int.from_bytes(head[4:8], "little") + 8 == size
        )
    return False


def _probe_still_header(path: Path) -> Optional[Tuple[Optional[float], int, int]]:
    """(duration, width, height) identical to ffprobe's, or None when the
    file is not one this fast path is certain about (caller uses ffprobe)."""
    fmt = _STILL_EXT_FORMAT.get(path.suffix.lower())
    if fmt is None:
        return None
    try:
        size = path.stat().st_size
        with open(path, "rb") as fp:
            if not _still_file_complete(fmt, fp, size):
                return None
            fp.seek(0)
            # The plugin class directly (not Image.open): header parse only,
            # no format guessing and no decompression-bomb warning side effect.
            if fmt == "PNG":
                from PIL import PngImagePlugin

                im = PngImagePlugin.PngImageFile(fp)
                if getattr(im, "is_animated", False) or getattr(im, "n_frames", 1) != 1:
                    return None  # APNG -> ffprobe's apng demuxer
            elif fmt == "JPEG":
                from PIL import JpegImagePlugin

                im = JpegImagePlugin.JpegImageFile(fp)
                for marker, data in getattr(im, "applist", []) or []:
                    if marker == "APP2" and data[:4] == b"MPF\x00":
                        return None  # multi-picture JPEG
            else:
                from PIL import WebPImagePlugin

                if not getattr(WebPImagePlugin, "SUPPORTED", True):
                    return None
                im = WebPImagePlugin.WebPImageFile(fp)
                if getattr(im, "is_animated", False) or getattr(im, "n_frames", 1) != 1:
                    return None  # ffprobe reports 0x0 for animated WebP
            if im.format != fmt:
                return None
            w, h = (int(v) for v in im.size)
            try:
                im.close()
            except Exception:
                pass
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return _STILL_DURATION[fmt], w, h


def probe_local_media(path: Path) -> Tuple[Optional[float], int, int]:
    """Return (duration_sec, width, height) for a local media file."""
    path = Path(path)
    if not path.is_file():
        return None, 0, 0
    # Resolve ffprobe first even on the fast path so a machine without it
    # still fails exactly as before (RuntimeError) instead of silently
    # passing stills.
    ffprobe = _ffprobe()
    fast = _probe_still_header(path)
    if fast is not None:
        return fast
    try:
        proc = subprocess.run(
            [
                ffprobe,
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
