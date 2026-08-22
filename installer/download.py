"""Streamed downloads with .part files, Range resume, SHA-256, and progress."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Callable, Optional

import requests

ProgressFn = Callable[[int, Optional[int]], None]  # bytes_done_this_file, total_or_None
ShouldStopFn = Callable[[], bool]

CHUNK = 1 << 16
# (connect timeout, read timeout) — large HF weights need a long read window
TIMEOUT = (30, 300)
MAX_RETRIES = 8


class DownloadError(Exception):
    """Download or checksum failure."""


class DownloadCancelled(DownloadError):
    """User cancelled mid-download."""


def sha256_file(path: Path, *, should_stop: Optional[ShouldStopFn] = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            if should_stop and should_stop():
                raise DownloadCancelled("checksum cancelled")
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str, *, should_stop: Optional[ShouldStopFn] = None) -> None:
    expected = (expected or "").strip().lower()
    if not expected:
        raise DownloadError(f"Missing expected SHA-256 for {path.name}")
    actual = sha256_file(path, should_stop=should_stop)
    if actual != expected:
        raise DownloadError(
            f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}"
        )


def _content_length(resp: requests.Response, resume_from: int) -> Optional[int]:
    if resp.status_code == 206:
        cr = resp.headers.get("Content-Range") or ""
        # bytes start-end/total
        if "/" in cr:
            total_s = cr.rsplit("/", 1)[-1]
            if total_s.isdigit():
                return int(total_s)
        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit():
            return resume_from + int(cl)
        return None
    cl = resp.headers.get("Content-Length")
    if cl and cl.isdigit():
        return int(cl)
    return None


def download_file(
    url: str,
    dest: Path,
    *,
    expected_sha256: str = "",
    expected_size: int = 0,
    progress: Optional[ProgressFn] = None,
    should_stop: Optional[ShouldStopFn] = None,
    session: Optional[requests.Session] = None,
) -> Path:
    """
    Download url to dest using dest.with_suffix(dest.suffix + '.part') for resume.
    On success, verifies SHA-256 when expected_sha256 is set, then renames into place.
    Retries on transient network timeouts (keeps .part progress).
    """
    if not url:
        raise DownloadError("Empty download URL")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    if dest.is_file() and expected_sha256:
        try:
            verify_sha256(dest, expected_sha256, should_stop=should_stop)
            if progress:
                size = dest.stat().st_size
                progress(size, size)
            return dest
        except DownloadError:
            dest.unlink(missing_ok=True)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        if should_stop and should_stop():
            raise DownloadCancelled("download cancelled")
        try:
            return _download_once(
                url,
                dest,
                part,
                expected_sha256=expected_sha256,
                expected_size=expected_size,
                progress=progress,
                should_stop=should_stop,
                session=session,
            )
        except DownloadCancelled:
            raise
        except (DownloadError, requests.RequestException, OSError, TimeoutError) as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break
            # Brief backoff; Range resume continues from .part on the next try.
            time.sleep(min(30, 2 * attempt))
    raise DownloadError(f"Download failed after {MAX_RETRIES} attempts: {last_error}") from last_error


def _download_once(
    url: str,
    dest: Path,
    part: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    progress: Optional[ProgressFn],
    should_stop: Optional[ShouldStopFn],
    session: Optional[requests.Session],
    retried_416: bool = False,
) -> Path:
    resume_from = part.stat().st_size if part.is_file() else 0
    headers = {}
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"

    sess = session or requests.Session()
    try:
        with sess.get(url, stream=True, timeout=TIMEOUT, headers=headers) as resp:
            if resp.status_code == 416 and resume_from > 0 and not retried_416:
                # Stale .part from interrupted download — GitHub rejects resume past EOF.
                part.unlink(missing_ok=True)
                return _download_once(
                    url,
                    dest,
                    part,
                    expected_sha256=expected_sha256,
                    expected_size=expected_size,
                    progress=progress,
                    should_stop=should_stop,
                    session=sess,
                    retried_416=True,
                )
            if resume_from and resp.status_code == 200:
                # Server ignored Range — restart
                part.unlink(missing_ok=True)
                resume_from = 0
                headers.pop("Range", None)
                resp.close()
                with sess.get(url, stream=True, timeout=TIMEOUT) as resp2:
                    return _stream_body(
                        resp2,
                        dest,
                        part,
                        resume_from=0,
                        expected_sha256=expected_sha256,
                        expected_size=expected_size,
                        progress=progress,
                        should_stop=should_stop,
                    )
            if resp.status_code not in (200, 206):
                raise DownloadError(f"HTTP {resp.status_code} downloading {url}")
            return _stream_body(
                resp,
                dest,
                part,
                resume_from=resume_from,
                expected_sha256=expected_sha256,
                expected_size=expected_size,
                progress=progress,
                should_stop=should_stop,
            )
    except DownloadCancelled:
        raise
    except DownloadError:
        raise
    except requests.RequestException as exc:
        raise DownloadError(f"Download failed: {exc}") from exc


def _stream_body(
    resp: requests.Response,
    dest: Path,
    part: Path,
    *,
    resume_from: int,
    expected_sha256: str,
    expected_size: int,
    progress: Optional[ProgressFn],
    should_stop: Optional[ShouldStopFn],
) -> Path:
    total = _content_length(resp, resume_from)
    if total is None and expected_size > 0:
        total = expected_size
    mode = "ab" if resume_from and resp.status_code == 206 else "wb"
    if mode == "wb":
        resume_from = 0
    written = resume_from
    if progress:
        progress(written, total)

    with open(part, mode) as f:
        for chunk in resp.iter_content(chunk_size=CHUNK):
            if should_stop and should_stop():
                raise DownloadCancelled("download cancelled")
            if not chunk:
                continue
            f.write(chunk)
            written += len(chunk)
            if progress:
                progress(written, total)

    if expected_sha256:
        verify_sha256(part, expected_sha256, should_stop=should_stop)
    part.replace(dest)
    if progress and total:
        progress(total, total)
    return dest


def head_content_length(url: str, session: Optional[requests.Session] = None) -> Optional[int]:
    if not url:
        return None
    sess = session or requests.Session()
    try:
        resp = sess.head(url, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code >= 400:
            return None
        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit():
            return int(cl)
    except requests.RequestException:
        return None
    return None


def sleep_brief() -> None:
    time.sleep(0.05)
