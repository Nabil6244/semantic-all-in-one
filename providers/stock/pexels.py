"""Pexels stock backend — https://www.pexels.com/api/documentation/

Auth: a plain `Authorization: <API_KEY>` header (no OAuth). The key is passed in
by the caller (GUI settings / env var); this module never hardcodes one.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import requests

from ..base import MediaType
from .base import Candidate, StockBackend, StockProvider
from .cache import StockCache

PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"
VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"
TIMEOUT = 15


class PexelsBackend(StockBackend):
    name = "pexels"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Pexels API key is required")
        self.api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({"Authorization": api_key})

    def search(self, query: str, media_type: str = "all", per_page: int = 15) -> List[Candidate]:
        candidates: List[Candidate] = []
        if media_type in ("all", "image"):
            candidates.extend(self._search_photos(query, per_page))
        if media_type in ("all", "video"):
            candidates.extend(self._search_videos(query, per_page))
        return candidates

    def _search_photos(self, query: str, per_page: int) -> List[Candidate]:
        resp = self._session.get(
            PHOTO_SEARCH_URL,
            params={"query": query, "per_page": per_page, "orientation": "landscape"},
            timeout=TIMEOUT,
        )
        self._raise_for_status(resp)
        out: List[Candidate] = []
        for p in resp.json().get("photos", []):
            src = p.get("src", {})
            url = src.get("large2x") or src.get("original") or src.get("large")
            if not url:
                continue
            out.append(
                Candidate(
                    provider=self.name,
                    asset_id=str(p["id"]),
                    media_type=MediaType.IMAGE,
                    url=url,
                    width=p.get("width", 0),
                    height=p.get("height", 0),
                    author=p.get("photographer", ""),
                    source_url=p.get("url", ""),
                    thumbnail_url=src.get("tiny", ""),
                    extra={"alt": p.get("alt", "") or ""},
                )
            )
        return out

    def _search_videos(self, query: str, per_page: int) -> List[Candidate]:
        resp = self._session.get(
            VIDEO_SEARCH_URL,
            params={"query": query, "per_page": per_page, "orientation": "landscape"},
            timeout=TIMEOUT,
        )
        self._raise_for_status(resp)
        out: List[Candidate] = []
        for v in resp.json().get("videos", []):
            files = [f for f in v.get("video_files", []) if f.get("link") and f.get("width")]
            if not files:
                continue
            # Prefer the largest file at/under 1920w (avoids multi-GB 4K downloads);
            # fall back to the largest available if everything is smaller than that.
            under_hd = [f for f in files if f["width"] <= 1920]
            best_file = max(under_hd or files, key=lambda f: f["width"])
            pictures = v.get("video_pictures") or [{}]
            out.append(
                Candidate(
                    provider=self.name,
                    asset_id=str(v["id"]),
                    media_type=MediaType.VIDEO,
                    url=best_file["link"],
                    width=best_file.get("width", v.get("width", 0)),
                    height=best_file.get("height", v.get("height", 0)),
                    duration=v.get("duration"),
                    author=(v.get("user") or {}).get("name", ""),
                    source_url=v.get("url", ""),
                    thumbnail_url=pictures[0].get("picture", ""),
                    extra={},
                )
            )
        return out

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise RuntimeError("Pexels rejected the API key (401 Unauthorized).")
        if resp.status_code == 429:
            raise RuntimeError("Pexels rate limit reached (429) — try again later.")
        resp.raise_for_status()


def build_pexels_provider(images_dir, api_key: str) -> StockProvider:
    """Convenience factory: one Pexels backend, project-scoped used-asset cache."""
    cache = StockCache(used_ids_file=Path(images_dir) / ".stock_used_assets.json")
    return StockProvider(backends=[PexelsBackend(api_key)], cache=cache)
