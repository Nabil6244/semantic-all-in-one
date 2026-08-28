"""Deterministic QA result cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from .models import QA_ENGINE_VERSION, VisualQAResult

CACHE_FILE = ".visual_qa_cache.json"


def _fingerprint(
    asset_path: str,
    scene_number: str,
    style_id: str = "",
    coverage_version: str = "",
) -> str:
    raw = f"{QA_ENGINE_VERSION}|{asset_path}|{scene_number}|{style_id}|{coverage_version}"
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
    fp = _fingerprint(str(asset_path.resolve()), scene_number, style_id)
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
    fp = _fingerprint(str(Path(asset_path).resolve()), scene_number, style_id)
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
