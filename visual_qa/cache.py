"""Deterministic QA result cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from .models import QA_ENGINE_VERSION, VisualQAResult

CACHE_FILE = ".visual_qa_cache.json"


def _file_identity(asset_path: Path) -> str:
    """Cheap content identity: size + nanosecond mtime.

    The cache key used to be the PATH alone, but a retry regenerates a
    DIFFERENT image to the SAME path (001.png), so the re-evaluation after a
    retry was served the previous image's verdict. Both stat fields change
    when a file is rewritten, so a regenerated asset misses the cache and is
    scored fresh. Returns "" when the file is unreadable, which simply falls
    back to the old path-only behaviour rather than raising."""
    try:
        st = Path(asset_path).stat()
    except OSError:
        return ""
    return f"{st.st_size}:{st.st_mtime_ns}"


def _fingerprint(
    asset_path: str,
    scene_number: str,
    style_id: str = "",
    coverage_version: str = "",
    file_identity: str = "",
) -> str:
    raw = (
        f"{QA_ENGINE_VERSION}|{asset_path}|{file_identity}"
        f"|{scene_number}|{style_id}|{coverage_version}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def load_cache(images_dir: Path) -> dict:
    path = Path(images_dir) / CACHE_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(images_dir: Path, cache: dict) -> None:
    path = Path(images_dir) / CACHE_FILE
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def get_cached(
    images_dir: Path,
    asset_path: Path,
    scene_number: str,
    *,
    style_id: str = "",
) -> Optional[VisualQAResult]:
    cache = load_cache(images_dir)
    fp = _fingerprint(
        str(asset_path.resolve()), scene_number, style_id,
        file_identity=_file_identity(asset_path),
    )
    raw = cache.get(fp)
    if not isinstance(raw, dict):
        return None
    return VisualQAResult.from_dict(raw)


def store_cached(
    images_dir: Path,
    asset_path: Path,
    scene_number: str,
    result: VisualQAResult,
    *,
    style_id: str = "",
) -> None:
    cache = load_cache(images_dir)
    fp = _fingerprint(
        str(Path(asset_path).resolve()), scene_number, style_id,
        file_identity=_file_identity(Path(asset_path)),
    )
    cache[fp] = result.to_dict()
    save_cache(images_dir, cache)


def invalidate_scene(images_dir: Path, scene_number: str) -> None:
    cache = load_cache(images_dir)
    suffix = f"|{scene_number}|"
    keys = [k for k, v in cache.items() if isinstance(v, dict) and suffix in json.dumps(v)]
    for k in keys:
        cache.pop(k, None)
    if keys:
        save_cache(images_dir, cache)
