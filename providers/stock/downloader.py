"""Downloads a selected stock Candidate to Images/00N.<ext>, streamed with a size
cap. Extension is inferred from response Content-Type, falling back to the URL."""

from __future__ import annotations

import mimetypes
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .base import Candidate

TIMEOUT = 30
MAX_BYTES = 200 * 1024 * 1024  # 200MB safety cap against a runaway/huge response
UHD_MAX_BYTES = 1024 * 1024 * 1024  # 1GB per clip when the project accepts Ultra HD (4K) footage


# A 4K stock clip longer than this is cut to its first UHD_KEEP_SECONDS while downloading. Footage is fetched before scene
# lengths are known; the longest scene measured across 17 real projects (801 scenes) was 19.6 s.
UHD_KEEP_SECONDS = 30.0
# Rough size of one 4K stock clip once cut (for the disk-space warning) and the free space kept for the render.
UHD_CLIP_ESTIMATE_BYTES = 300 * 1024 * 1024
RENDER_MARGIN_BYTES = 2 * 1024 * 1024 * 1024


class DownloadCancelled(IOError):
    """The scene was stopped while downloading (never a reason to try another file)."""


def uhd_space_needed(stock_clips: int) -> int:
    """Free disk space a 4K-footage run should have: its stock clips plus room to render."""
    return max(0, int(stock_clips)) * UHD_CLIP_ESTIMATE_BYTES + RENDER_MARGIN_BYTES


def free_bytes(path: Path) -> int:
    """Free space on the disk holding `path` (or its nearest existing parent); a very large number when unknown."""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 1 << 62
_OK_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _extension_for(candidate: "Candidate", content_type: str) -> str:
    if candidate.media_type.value == "video":
        return ".mp4"
    guess = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    if guess == ".jpe":
        guess = ".jpg"
    if guess in _OK_IMAGE_EXTS:
        return guess
    suffix = Path(candidate.url.split("?")[0]).suffix.lower()
    return suffix if suffix in _OK_IMAGE_EXTS else ".jpg"


def download_candidate(
    candidate: "Candidate",
    images_dir: Path,
    scene_number: str,
    log=print,
    should_stop=None,
    *,
    max_bytes: int = MAX_BYTES,
    url: str = "",
) -> Path:
    """Download ``url`` (default: the candidate's own) to images_dir/00N.<ext>, aborting past ``max_bytes``."""
    n = int(str(scene_number).strip())
    with requests.get(url or candidate.url, stream=True, timeout=(15, 60)) as resp:
        resp.raise_for_status()
        ext = _extension_for(candidate, resp.headers.get("Content-Type", ""))
        target = Path(images_dir) / f"{n:03d}{ext}"
        written = 0
        tmp_target = target.with_suffix(target.suffix + ".part")
        with open(tmp_target, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if should_stop and should_stop():
                    tmp_target.unlink(missing_ok=True)
                    raise DownloadCancelled("download cancelled")
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    tmp_target.unlink(missing_ok=True)
                    raise IOError(f"stock asset exceeded {max_bytes // (1024*1024)}MB, aborted")
                f.write(chunk)
        tmp_target.replace(target)
    return target


def download_first_seconds(
    candidate: "Candidate",
    images_dir: Path,
    scene_number: str,
    seconds: float = UHD_KEEP_SECONDS,
    *,
    max_bytes: int = UHD_MAX_BYTES,
    should_stop=None,
    timeout_s: float = 1800.0,
) -> Path:
    """Save only the first `seconds` of a remote video as images_dir/00N.mp4, copied as-is (no re-encode, no quality loss).

    ffmpeg reads just the part of the file it needs, so a long 4K clip costs a fraction of its full size. Raises
    DownloadCancelled when the scene is stopped, IOError past `max_bytes`, RuntimeError when ffmpeg fails.
    """
    from providers import hidden_subprocess
    from providers.media_clip.ffmpeg_clip import _ffmpeg

    n = int(str(scene_number).strip())
    target = Path(images_dir) / f"{n:03d}.mp4"
    tmp = target.with_name(f"{target.stem}_part.mp4")   # ffmpeg picks the container from the extension
    tmp.unlink(missing_ok=True)
    cmd = [
        _ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-rw_timeout", "60000000",   # 60 s without data = a stalled connection
        "-i", candidate.url, "-t", f"{float(seconds):.3f}",
        "-map", "0:v:0", "-map", "0:a?", "-dn", "-c", "copy", "-movflags", "+faststart", "-y", str(tmp),
    ]
    proc = hidden_subprocess.popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.monotonic() + timeout_s
    problem = None
    try:
        while proc.poll() is None:
            if should_stop and should_stop():
                problem = DownloadCancelled("download cancelled")
            elif tmp.is_file() and tmp.stat().st_size > max_bytes:
                problem = IOError(f"stock asset exceeded {max_bytes // (1024 * 1024)}MB, aborted")
            elif time.monotonic() > deadline:
                problem = IOError(f"download took longer than {int(timeout_s)}s, aborted")
            if problem is not None:
                proc.kill()
                proc.wait(timeout=30)
                break
            time.sleep(0.25)
        err = (proc.stderr.read() or b"").decode("utf-8", "replace").strip() if proc.stderr else ""
    finally:
        if proc.stderr:
            proc.stderr.close()
    if problem is None and (proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0):
        problem = RuntimeError(f"ffmpeg could not save the first {seconds:.0f}s: {err[-300:] or 'no output'}")
    if problem is None and tmp.stat().st_size > max_bytes:   # finished before the next size check
        problem = IOError(f"stock asset exceeded {max_bytes // (1024 * 1024)}MB, aborted")
    if problem is not None:
        tmp.unlink(missing_ok=True)
        raise problem
    tmp.replace(target)
    return target
