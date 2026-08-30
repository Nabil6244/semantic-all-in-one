"""Bounded-concurrency media downloader with retries, size/MIME validation,
and exact + perceptual dedup.

Only called with an already-ranked, already-filtered subset of media
candidates — discovery and ranking happen first so we never download
everything we find. Discovery and downloading are intentionally separate
entry points (`discover_media` vs `download_media`) so callers can run
discovery-only passes.
"""
from __future__ import annotations

import asyncio
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import httpx

from app.dedup.media import MediaDeduplicator, hash_bytes, hash_file, perceptual_hash
from app.models.media import MediaAsset, MediaType

# Embeds we can identify but should not attempt to fetch as binary files
# (no reliable, ToS-respecting way to extract the underlying video file).
_EMBED_PROVIDERS = {"youtube_embed", "vimeo_embed"}

_DEFAULT_HEADERS = {"User-Agent": "SemanticResearchEngine/0.2 (research-only)"}
_DEFAULT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB per asset
_DEFAULT_MAX_RETRIES = 2
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_MIME_PREFIX = {MediaType.IMAGE: "image/", MediaType.VIDEO: "video/"}
_MIME_PASSTHROUGH = {"application/octet-stream", "binary/octet-stream"}


def _guess_extension(url: str, content_type: Optional[str], default: str) -> str:
    suffix = Path(url.split("?")[0]).suffix
    if suffix and len(suffix) <= 6:
        return suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return default


def _mime_is_acceptable(media_type: MediaType, content_type: Optional[str]) -> bool:
    if not content_type:
        return True  # no signal either way — don't reject on absence
    ct = content_type.split(";")[0].strip().lower()
    if ct in _MIME_PASSTHROUGH:
        return True
    return ct.startswith(_MIME_PREFIX[media_type])


async def _fetch_with_retry(
    client: httpx.AsyncClient, url: str, max_bytes: int, max_retries: int,
) -> tuple[Optional[bytes], Optional[httpx.Response], Optional[str]]:
    """Streams the response, enforcing `max_bytes`, with retry+backoff on
    transient failures (timeouts, connection errors, 429/5xx). Returns
    (data, response, error). `data` is None on any unrecoverable failure."""
    last_error: Optional[str] = None
    for attempt in range(max_retries + 1):
        try:
            async with client.stream("GET", url, timeout=30.0) as resp:
                if resp.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                    last_error = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    return None, resp, f"HTTP {resp.status_code}"
                else:
                    chunks = bytearray()
                    async for chunk in resp.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > max_bytes:
                            return None, resp, f"exceeds max_file_size ({max_bytes} bytes)"
                    return bytes(chunks), resp, None
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = str(exc)

        if attempt < max_retries:
            await asyncio.sleep(0.5 * (2 ** attempt))
    return None, None, last_error or "download_failed"


def _try_reuse_existing(dedup: MediaDeduplicator, file_hash: str, asset: MediaAsset) -> bool:
    """When a duplicate is detected, resolve it back to the existing file
    instead of just skipping with no usable path. Returns True (and mutates
    `asset` in place) only when the recorded path genuinely exists and still
    hashes to the same content — a missing/corrupt/modified file is treated
    as "not actually reusable," never reported as a valid path."""
    existing_path = dedup.existing_local_path(file_hash)
    if not existing_path:
        return False
    path = Path(existing_path)
    if not path.is_file():
        return False
    try:
        if hash_file(path) != file_hash:
            return False
    except OSError:
        return False

    asset.local_path = str(path)
    asset.file_hash = file_hash
    try:
        asset.file_size_bytes = path.stat().st_size
    except OSError:
        pass
    if asset.media_type == MediaType.IMAGE and not (asset.width and asset.height):
        asset.width, asset.height = _probe_image_dims(path) or (asset.width, asset.height)
    asset.downloaded = True
    asset.download_note = "duplicate_reused"
    return True


async def _download_one(
    client: httpx.AsyncClient,
    asset: MediaAsset,
    out_dir: Path,
    dedup: MediaDeduplicator,
    semaphore: asyncio.Semaphore,
    max_bytes: int,
    max_retries: int,
) -> MediaAsset:
    if asset.provider in _EMBED_PROVIDERS:
        asset.downloaded = False
        asset.download_note = "embed_reference_only"
        return asset

    async with semaphore:
        data, resp, error = await _fetch_with_retry(client, asset.source_url, max_bytes, max_retries)
        if data is None:
            asset.downloaded = False
            asset.download_note = f"download_failed: {error}"
            return asset

        content_type = resp.headers.get("content-type") if resp is not None else None
        if not _mime_is_acceptable(asset.media_type, content_type):
            asset.downloaded = False
            asset.download_note = f"unexpected_mime_type: {content_type}"
            return asset

        file_hash = hash_bytes(data)
        if dedup.is_exact_duplicate(file_hash):
            asset.file_hash = file_hash
            reused = _try_reuse_existing(dedup, file_hash, asset)
            if reused:
                return asset
            # Recorded as a duplicate, but the existing file is missing,
            # unreadable, or no longer matches its recorded hash — never
            # write a false local_path. Fall through to the normal save
            # path below so this asset still ends up with a real, valid
            # file instead of silently having none.
            asset.download_note = "duplicate_hash_stale_redownloaded"

        default_ext = ".jpg" if asset.media_type == MediaType.IMAGE else ".mp4"
        ext = _guess_extension(asset.source_url, content_type, default_ext)
        local_path = out_dir / f"{asset.media_id}{ext}"

        if local_path.exists():
            # Never silently overwrite. If it's byte-identical, treat it as
            # already-downloaded; otherwise pick a fresh, distinct name.
            existing_hash = hash_bytes(local_path.read_bytes())
            if existing_hash == file_hash:
                asset.local_path = str(local_path)
                asset.file_hash = file_hash
                asset.file_size_bytes = local_path.stat().st_size
                asset.downloaded = True
                asset.download_note = "already_exists"
                dedup.register(file_hash, asset.media_id, local_path=str(local_path))
                return asset
            local_path = out_dir / f"{asset.media_id}-{file_hash[:8]}{ext}"

        local_path.write_bytes(data)

        phash = None
        if asset.media_type == MediaType.IMAGE:
            phash = perceptual_hash(local_path)
            if phash:
                dup_id = dedup.find_perceptual_duplicate(phash)
                if dup_id:
                    local_path.unlink(missing_ok=True)
                    asset.file_hash = file_hash
                    asset.perceptual_hash = phash
                    asset.downloaded = False
                    asset.download_note = f"perceptual_duplicate_of:{dup_id}"
                    return asset
            asset.width, asset.height = _probe_image_dims(local_path) or (asset.width, asset.height)

        dedup.register(file_hash, asset.media_id, phash, local_path=str(local_path))
        asset.local_path = str(local_path)
        asset.file_hash = file_hash
        asset.perceptual_hash = phash
        asset.file_size_bytes = len(data)
        asset.mime_type = asset.mime_type or content_type
        asset.downloaded = True
        asset.retrieved_at = datetime.now(timezone.utc)
        return asset


def _probe_image_dims(path: Path):
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:  # noqa: BLE001
        return None


async def download_media(
    assets: List[MediaAsset],
    output_dir: Path,
    concurrency: int = 5,
    dedup: Optional[MediaDeduplicator] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> List[MediaAsset]:
    """`http_client` is an injection point for tests (e.g. an
    `httpx.AsyncClient(transport=httpx.MockTransport(...))`) so the download
    pipeline can be exercised without real network access."""
    dedup = dedup or MediaDeduplicator()
    images_dir = output_dir / "images"
    videos_dir = output_dir / "videos"
    images_dir.mkdir(parents=True, exist_ok=True)
    videos_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(concurrency)

    async def _run(client: httpx.AsyncClient) -> List[MediaAsset]:
        tasks = []
        for asset in assets:
            target_dir = images_dir if asset.media_type == MediaType.IMAGE else videos_dir
            tasks.append(_download_one(client, asset, target_dir, dedup, semaphore, max_bytes, max_retries))
        return await asyncio.gather(*tasks)

    if http_client is not None:
        return await _run(http_client)

    async with httpx.AsyncClient(headers=_DEFAULT_HEADERS, follow_redirects=True) as client:
        return await _run(client)
