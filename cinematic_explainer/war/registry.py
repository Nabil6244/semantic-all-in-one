"""Sidecar provenance registry: one small versioned JSON file in the per-user cache area, keyed by the file's content identity.

The scene manifest replaces a scene's record wholesale on every write, so anything stored there can vanish on a retry. This registry is
keyed by the asset file's own content (sha1 of the first 16 MB plus the size), so it survives renames, retries and manifest rewrites.
No database and no migration; a missing or corrupt file is treated as empty.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = 1
_HEAD_BYTES = 16 * 1024 * 1024
_LOCK = threading.RLock()


def content_key(path: Any) -> Optional[str]:
    """sha1(first 16 MB) + size, shortened; None when the file cannot be read. Independent of the file name and folder."""
    try:
        p = Path(path)
        size = p.stat().st_size
        h = hashlib.sha1()
        with open(p, "rb") as fh:
            h.update(fh.read(_HEAD_BYTES))
        return hashlib.sha1(f"{h.hexdigest()}:{size}".encode()).hexdigest()[:24]
    except OSError:
        return None


def default_path() -> Path:
    """Per-user file next to the map cache (same per-user location convention as boundary_source)."""
    try:
        from map_scene.render import cache_dir

        return Path(cache_dir()).parent / "war_registry.json"
    except Exception:
        return Path(tempfile.gettempdir()) / "semantic_yt_war_registry.json"


class Registry:
    def __init__(self, path: Optional[Any] = None):
        self.path = Path(path) if path else default_path()

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get("schema") == SCHEMA_VERSION and isinstance(data.get("assets"), dict):
                return data
        except (OSError, ValueError):
            pass
        return {"schema": SCHEMA_VERSION, "assets": {}}

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".war_registry_", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def get(self, key_or_path: Any) -> Optional[Dict[str, Any]]:
        key = key_or_path if isinstance(key_or_path, str) and len(key_or_path) == 24 and not os.path.exists(key_or_path) else content_key(key_or_path)
        if not key:
            return None
        with _LOCK:
            rec = self._read()["assets"].get(key)
        return dict(rec) if isinstance(rec, dict) else None

    def put(self, key_or_path: Any, record: Dict[str, Any]) -> Optional[str]:
        key = key_or_path if isinstance(key_or_path, str) and len(key_or_path) == 24 and not os.path.exists(key_or_path) else content_key(key_or_path)
        if not key:
            return None
        with _LOCK:
            data = self._read()
            data["assets"][key] = dict(record)
            self._write(data)
        return key

    def update(self, key_or_path: Any, **fields: Any) -> Optional[Dict[str, Any]]:
        key = key_or_path if isinstance(key_or_path, str) and len(key_or_path) == 24 and not os.path.exists(key_or_path) else content_key(key_or_path)
        if not key:
            return None
        with _LOCK:
            data = self._read()
            rec = dict(data["assets"].get(key) or {})
            rec.update(fields)
            data["assets"][key] = rec
            self._write(data)
        return rec


def all_cards() -> Dict[str, Any]:
    """Phase 1 cards plus the war cards and map cards, whichever modules exist (imported lazily; a missing module is skipped)."""
    from .. import cards as base

    out: Dict[str, Any] = dict(base.CARDS)
    for mod, attr in (("cards", "WAR_CARDS"), ("maps", "MAP_CARDS")):
        try:
            m = __import__(f"{__package__}.{mod}", fromlist=[attr])
            out.update(getattr(m, attr))
        except Exception:
            continue
    return out
