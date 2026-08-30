"""Media deduplication: exact hashing (always) + perceptual hashing (optional)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Iterable, Optional, Union


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def perceptual_hash(path: str | Path) -> Optional[str]:
    """Best-effort perceptual hash for images. Returns None if Pillow/imagehash
    are not installed (optional `media` extra) or the file isn't a decodable
    image — never raises."""
    try:
        from PIL import Image
        import imagehash
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:  # noqa: BLE001 - corrupt/unsupported image, treat as no hash
        return None


def hamming_distance(hash_a: str, hash_b: str) -> int:
    try:
        import imagehash
        return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - malformed/mismatched-shape hash strings
        pass
    # Fallback: plain hex hamming distance (also used when imagehash can't
    # parse the given hex strings, e.g. non-square-shaped test/cache data).
    a, b = int(hash_a, 16), int(hash_b, 16)
    return bin(a ^ b).count("1")


class MediaDeduplicator:
    """Tracks hashes seen so far in a research run (or across runs, via cache)
    to avoid downloading/storing the same media twice.

    Each known hash maps to the local_path of an existing file for it, when
    known (None if we only know the hash was seen before but not where the
    file lives — e.g. legacy cache data). This lets a downloader resolve a
    detected duplicate back to a reusable file instead of just skipping it
    with nothing to show for it.
    """

    def __init__(self, perceptual_threshold: int = 6):
        self._file_hashes: Dict[str, Optional[str]] = {}
        self._perceptual_hashes: dict[str, str] = {}  # phash -> media_id
        self.perceptual_threshold = perceptual_threshold

    def seed(
        self,
        file_hashes: Optional[Union[Iterable[str], Dict[str, Optional[str]]]] = None,
        perceptual: dict[str, str] | None = None,
    ):
        """`file_hashes` accepts either a plain iterable of hashes (path
        unknown) or a dict of hash -> local_path (preferred — e.g. from
        ResearchCache.all_items("media_hash"), so a cross-run duplicate can
        be resolved back to its existing file)."""
        if file_hashes:
            if isinstance(file_hashes, dict):
                for file_hash, path in file_hashes.items():
                    self._file_hashes[file_hash] = path
            else:
                for file_hash in file_hashes:
                    self._file_hashes.setdefault(file_hash, None)
        if perceptual:
            self._perceptual_hashes.update(perceptual)

    def is_exact_duplicate(self, file_hash: str) -> bool:
        return file_hash in self._file_hashes

    def existing_local_path(self, file_hash: str) -> Optional[str]:
        """The known local_path for a previously-seen hash, if any. Callers
        must still verify the file actually exists and is unmodified before
        trusting it — a stale/deleted/corrupted entry returns whatever path
        was recorded, not a guarantee it's still valid."""
        return self._file_hashes.get(file_hash)

    def find_perceptual_duplicate(self, phash: str) -> Optional[str]:
        for existing_hash, media_id in self._perceptual_hashes.items():
            if hamming_distance(phash, existing_hash) <= self.perceptual_threshold:
                return media_id
        return None

    def register(self, file_hash: str, media_id: str, phash: Optional[str] = None, local_path: Optional[str] = None):
        self._file_hashes[file_hash] = local_path
        if phash:
            self._perceptual_hashes[phash] = media_id
