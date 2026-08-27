"""Openverse API backend — https://api.openverse.org/v1/ (CC image search)."""

from __future__ import annotations

from typing import List

import requests

from ..base import MediaType
from .base import Candidate, StockBackend

from providers.media_quality.scoring import is_preview_or_derivative_url

SEARCH_URL = "https://api.openverse.org/v1/images/"
TIMEOUT = 20
USER_AGENT = "SemanticVideoGenerator/1.0 (documentary/educational; local-app)"


class OpenverseBackend(StockBackend):
    name = "openverse"

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def search(self, query: str, media_type: str = "all", per_page: int = 15) -> List[Candidate]:
        if media_type == "video":
            return []
        if media_type not in ("all", "image"):
            return []
        resp = self._session.get(
            SEARCH_URL,
            params={
                "q": query,
                "page_size": min(max(per_page, 3), 20),
                "license": "cc0,pdm,by,by-sa",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code == 429:
            raise RuntimeError("Openverse rate limit reached (429) — try again later.")
        resp.raise_for_status()
        out: List[Candidate] = []
        for hit in resp.json().get("results") or []:
            url = hit.get("url")
            if not url or is_preview_or_derivative_url(url):
                continue
            w = int(hit.get("width") or 0)
            h = int(hit.get("height") or 0)
            if w <= 640 or h <= 480:
                if is_preview_or_derivative_url(url) or "thumb" in (hit.get("thumbnail") or ""):
                    continue
            out.append(
                Candidate(
                    provider=self.name,
                    asset_id=f"openverse:{hit.get('id', hit.get('identifier', url))}",
                    media_type=MediaType.IMAGE,
                    url=url,
                    width=w,
                    height=h,
                    author=(hit.get("creator") or ""),
                    source_url=hit.get("foreign_landing_url") or hit.get("detail_url") or "",
                    thumbnail_url=hit.get("thumbnail") or "",
                    extra={
                        "license": hit.get("license") or "",
                        "license_version": hit.get("license_version") or "",
                    },
                )
            )
        return out
