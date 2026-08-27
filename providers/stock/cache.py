"""In-memory cache for stock search results within a single run (avoids re-querying
the same keyword string, e.g. on a Regenerate that broadens through the same
fallback queries), plus an on-disk record of which provider asset IDs have already
been used in this project — feeds the ranking repeat-penalty and persists across runs
so a second render of the same project doesn't reuse the same footage twice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Set


class StockCache:
    def __init__(self, used_ids_file: Optional[Path] = None):
        self.used_ids_file = Path(used_ids_file) if used_ids_file else None
        self._search: Dict[str, list] = {}
        self._used_ids: Set[str] = set()
        self._load_used_ids()

    def _load_used_ids(self) -> None:
        if self.used_ids_file and self.used_ids_file.is_file():
            try:
                data = json.loads(self.used_ids_file.read_text(encoding="utf-8"))
                self._used_ids = set(data.get("used_ids", []))
            except (json.JSONDecodeError, OSError):
                pass

    def _save_used_ids(self) -> None:
        if not self.used_ids_file:
            return
        try:
            self.used_ids_file.write_text(
                json.dumps({"used_ids": sorted(self._used_ids)}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    @staticmethod
    def _key(backend: str, query: str, media_type: str = "all") -> str:
        # media_type is part of the key — a "video"-only search and an "all"
        # search for the same query text are genuinely different requests.
        return f"{backend}:{media_type}:{query.strip().lower()}"

    def get_search(self, backend: str, query: str, media_type: str = "all") -> Optional[list]:
        return self._search.get(self._key(backend, query, media_type))

    def set_search(self, backend: str, query: str, results: list, media_type: str = "all") -> None:
        self._search[self._key(backend, query, media_type)] = results

    def used_asset_ids(self) -> Set[str]:
        return set(self._used_ids)

    def record_used(self, asset_id: str) -> None:
        self._used_ids.add(str(asset_id))
        self._save_used_ids()

    def provider_use_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for asset_id in self._used_ids:
            provider = str(asset_id).split(":", 1)[0]
            if provider.isdigit():
                provider = "pexels"
            counts[provider] = counts.get(provider, 0) + 1
        return counts
