"""Filesystem/SQLite cache for pages, facts, media metadata, and downloads.

No external database server — a single SQLite file per cache directory, per
the V1 constraint. Values are stored as JSON so callers can cache arbitrary
serializable payloads (raw HTML, extracted facts, media metadata records)
under a small set of namespaces.

Namespaces used by the engine:
- `page_html` — raw fetched HTML + fetch metadata, keyed by URL
- `search_results` — search provider results, keyed by query text
- `page_data` — extracted page metadata/facts, keyed by URL
- `media_hash` — file hash -> local path, for exact dedup
- `research_result` — a full research run's output, keyed by an input hash

Entries carry a schema `version` (defaults to the engine's SCHEMA_VERSION).
Reads silently miss on a version mismatch, so bumping the engine's schema
version auto-invalidates stale cache entries from a previous release instead
of serving them.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from app.dedup.urls import normalize_url

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_entries (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    version TEXT NOT NULL,
    cached_at REAL NOT NULL,
    PRIMARY KEY (namespace, key)
);
"""

# Default max-age per namespace, applied by the convenience get_/set_ methods
# when the caller doesn't pass an explicit max_age_seconds. Raw page HTML
# and search results churn faster than, say, a media hash (content-addressed
# — never goes stale).
_DEFAULT_TTL_SECONDS = {
    "page_html": 6 * 3600,
    "search_results": 6 * 3600,
    "page_data": 6 * 3600,
    "research_result": 24 * 3600,
    "media_hash": None,
}


class ResearchCache:
    def __init__(self, cache_path: str | Path, version: str = "2"):
        self.path = Path(cache_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.version = version
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _norm_key(self, key: str) -> str:
        return normalize_url(key) if "://" in key or "." in key else key

    def get(self, namespace: str, key: str, max_age_seconds: Optional[float] = None) -> Optional[Any]:
        cur = self._conn.execute(
            "SELECT value, version, cached_at FROM cache_entries WHERE namespace = ? AND key = ?",
            (namespace, self._norm_key(key)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        value, version, cached_at = row
        if version != self.version:
            return None
        if max_age_seconds is not None and (time.time() - cached_at) > max_age_seconds:
            return None
        return json.loads(value)

    def set(self, namespace: str, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO cache_entries (namespace, key, value, version, cached_at) VALUES (?, ?, ?, ?, ?)",
            (namespace, self._norm_key(key), json.dumps(value, default=str), self.version, time.time()),
        )
        self._conn.commit()

    def delete(self, namespace: str, key: str) -> None:
        self._conn.execute(
            "DELETE FROM cache_entries WHERE namespace = ? AND key = ?",
            (namespace, self._norm_key(key)),
        )
        self._conn.commit()

    def all_keys(self, namespace: str) -> list[str]:
        cur = self._conn.execute(
            "SELECT key FROM cache_entries WHERE namespace = ? AND version = ?", (namespace, self.version),
        )
        return [r[0] for r in cur.fetchall()]

    def all_values(self, namespace: str) -> list[Any]:
        cur = self._conn.execute(
            "SELECT value FROM cache_entries WHERE namespace = ? AND version = ?", (namespace, self.version),
        )
        return [json.loads(r[0]) for r in cur.fetchall()]

    def all_items(self, namespace: str) -> dict[str, Any]:
        cur = self._conn.execute(
            "SELECT key, value FROM cache_entries WHERE namespace = ? AND version = ?", (namespace, self.version),
        )
        return {key: json.loads(value) for key, value in cur.fetchall()}

    # --- namespace convenience wrappers (apply the namespace's default TTL) --

    def _get_ns(self, namespace: str, key: str) -> Optional[Any]:
        return self.get(namespace, key, max_age_seconds=_DEFAULT_TTL_SECONDS.get(namespace))

    def get_page_html(self, url: str) -> Optional[dict]:
        return self._get_ns("page_html", url)

    def set_page_html(self, url: str, html: str, final_url: str, status_code: Optional[int]) -> None:
        self.set("page_html", url, {"html": html, "final_url": final_url, "status_code": status_code})

    def get_search_results(self, query: str) -> Optional[list]:
        return self._get_ns("search_results", query)

    def set_search_results(self, query: str, results: list) -> None:
        self.set("search_results", query, results)

    def get_research_result(self, input_hash: str) -> Optional[dict]:
        return self._get_ns("research_result", input_hash)

    def set_research_result(self, input_hash: str, package: dict) -> None:
        self.set("research_result", input_hash, package)
