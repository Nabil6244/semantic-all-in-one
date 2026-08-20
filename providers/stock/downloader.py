"""Downloads a selected stock Candidate to Images/00N.<ext>, streamed with a size
cap. Extension is inferred from response Content-Type, falling back to the URL."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .base import Candidate

TIMEOUT = 30
MAX_BYTES = 200 * 1024 * 1024  # 200MB safety cap against a runaway/huge response
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
) -> Path:
    n = int(str(scene_number).strip())
    with requests.get(candidate.url, stream=True, timeout=(15, 60)) as resp:
        resp.raise_for_status()
        ext = _extension_for(candidate, resp.headers.get("Content-Type", ""))
        target = Path(images_dir) / f"{n:03d}{ext}"
        written = 0
        tmp_target = target.with_suffix(target.suffix + ".part")
        with open(tmp_target, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if should_stop and should_stop():
                    tmp_target.unlink(missing_ok=True)
                    raise IOError("download cancelled")
                if not chunk:
                    continue
                written += len(chunk)
                if written > MAX_BYTES:
                    tmp_target.unlink(missing_ok=True)
                    raise IOError(f"stock asset exceeded {MAX_BYTES // (1024*1024)}MB, aborted")
                f.write(chunk)
        tmp_target.replace(target)
    return target
