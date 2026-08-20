"""Manual local clip recovery: validate a user-picked file and copy it into Images/.

Does not acquire assets from YouTube/Pexels/Flow. The renderer still finds the
scene via the existing ``001.mp4`` / ``001.jpg`` convention.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import video_generator as vg
from providers.base import MediaType, sniff_media_kind

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS

FILE_DIALOG_TYPES = [
    ("Media", "*.mp4 *.mov *.webm *.mkv *.avi *.m4v *.png *.jpg *.jpeg *.webp"),
    ("Video", "*.mp4 *.mov *.webm *.mkv *.avi *.m4v"),
    ("Images", "*.png *.jpg *.jpeg *.webp"),
    ("All files", "*.*"),
]


class ManualClipError(ValueError):
    """User-facing reason the selected file cannot be used."""


@dataclass
class ManualClipInfo:
    path: Path
    media_type: MediaType
    suffix: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


def normalize_picked_path(raw) -> Path:
    """Turn a file-dialog return value into a Path. Empty/cancel is an error."""
    text = str(raw or "").strip()
    if not text:
        raise ManualClipError("No file was selected.")
    return Path(text).expanduser()


def _unique_name(images_dir: Path, stem: str, suffix: str) -> Path:
    candidate = images_dir / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        candidate = images_dir / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _probe_media(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration:format=duration",
        "-of", "default=noprint_wrappers=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out = {}
    for line in (proc.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if key == "width":
            try:
                out["width"] = int(float(value))
            except ValueError:
                pass
        elif key == "height":
            try:
                out["height"] = int(float(value))
            except ValueError:
                pass
        elif key == "duration" and "duration" not in out:
            try:
                dur = float(value)
                if dur > 0:
                    out["duration"] = dur
            except ValueError:
                pass
    return out


def validate_local_media(raw) -> ManualClipInfo:
    """Raise ManualClipError with a clear reason, or return inspected media info."""
    path = normalize_picked_path(raw)
    if not path.exists():
        raise ManualClipError(f"File does not exist:\n{path}")
    if not path.is_file():
        raise ManualClipError(f"That path is not a file:\n{path}")
    try:
        with open(path, "rb") as fh:
            fh.read(1)
    except OSError as exc:
        raise ManualClipError(f"File is not readable:\n{path}\n{exc}") from exc

    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTS:
        raise ManualClipError(
            f"Unsupported file type ({suffix or 'no extension'}).\n"
            "Use MP4, MOV, WEBM, MKV, AVI, PNG, JPG, or WEBP."
        )

    sniffed = sniff_media_kind(path)
    wants_video = suffix in VIDEO_EXTS
    wants_image = suffix in IMAGE_EXTS
    if sniffed == "video" and wants_image:
        raise ManualClipError("This file is a video, but the extension is an image type.")
    if sniffed == "image" and wants_video:
        raise ManualClipError("This file is an image, but the extension is a video type.")
    if sniffed is None and wants_video:
        # RIFF/AVI and some MOV files are not in the magic sniffer; ffprobe may still work.
        probe = _probe_media(path)
        if not probe:
            raise ManualClipError(
                "Could not confirm this is a valid video.\n"
                "Try exporting as MP4."
            )
    if sniffed is None and wants_image:
        raise ManualClipError("This image file is damaged or not a real PNG/JPG/WEBP.")

    media_type = MediaType.VIDEO if wants_video else MediaType.IMAGE
    probe = _probe_media(path) if media_type == MediaType.VIDEO else {}
    duration = probe.get("duration")
    if media_type == MediaType.VIDEO and duration is not None and duration <= 0:
        raise ManualClipError("This video has no usable duration.")

    return ManualClipInfo(
        path=path,
        media_type=media_type,
        suffix=suffix,
        duration=duration,
        width=probe.get("width"),
        height=probe.get("height"),
    )


def install_manual_clip(images_dir: Path, scene_number, source_path) -> tuple[Path, ManualClipInfo]:
    """Copy a validated file into Images/ as the scene's canonical asset.

    Archives a unique ``047_manual.ext`` copy (never overwritten). The renderer
    still reads ``047.ext``. Any other file for this scene number is removed so
    lookup cannot pick a leftover skip placeholder.
    """
    info = validate_local_media(source_path)
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    n = int(str(scene_number).strip())
    archive = _unique_name(images_dir, f"{n:03d}_manual", info.suffix)
    shutil.copy2(info.path, archive)
    canonical = images_dir / f"{n:03d}{info.suffix}"
    if canonical.exists() and canonical.resolve() != archive.resolve():
        backup = _unique_name(images_dir, f"{n:03d}_replaced", canonical.suffix)
        canonical.replace(backup)
    if canonical.resolve() != archive.resolve():
        shutil.copy2(archive, canonical)
    while True:
        existing = vg.find_image_for_scene(images_dir, str(n))
        if existing is None or existing.resolve() == canonical.resolve():
            break
        existing.unlink()
    return canonical, info
