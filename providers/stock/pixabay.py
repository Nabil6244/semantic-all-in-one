"""Pixabay stock backend — https://pixabay.com/api/docs/

Auth: API key passed as the `key` query parameter. Free key from pixabay.com.
"""

from __future__ import annotations

from typing import List

import requests

from ..base import MediaType
from .base import Candidate, StockBackend

IMAGE_SEARCH_URL = "https://pixabay.com/api/"
VIDEO_SEARCH_URL = "https://pixabay.com/api/videos/"
TIMEOUT = 15


class PixabayBackend(StockBackend):
    name = "pixabay"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Pixabay API key is required")
        self.api_key = api_key
        self._session = requests.Session()

    def search(self, query: str, media_type: str = "all", per_page: int = 15) -> List[Candidate]:
        candidates: List[Candidate] = []
        if media_type in ("all", "image"):
            candidates.extend(self._search_images(query, per_page))
        if media_type in ("all", "video"):
            candidates.extend(self._search_videos(query, per_page))
        return candidates

    def _search_images(self, query: str, per_page: int) -> List[Candidate]:
        resp = self._session.get(
            IMAGE_SEARCH_URL,
            params={
                "key": self.api_key,
                "q": query,
                "image_type": "photo",
                "orientation": "horizontal",
                "per_page": min(max(per_page, 3), 200),
                "safesearch": "true",
            },
            timeout=TIMEOUT,
        )
        self._raise_for_status(resp)
        out: List[Candidate] = []
        for hit in resp.json().get("hits", []):
            url = (
                hit.get("imageURL")
                or hit.get("fullHDURL")
                or hit.get("largeImageURL")
                or hit.get("webformatURL")
            )
            if not url:
                continue
            # Dimensions must reflect the chosen download URL, not original catalog size.
            if hit.get("imageURL") or hit.get("fullHDURL"):
                w = hit.get("imageWidth", 0)
                h = hit.get("imageHeight", 0)
            elif hit.get("largeImageURL"):
                w = min(int(hit.get("imageWidth") or 0), 1280)
                h = min(int(hit.get("imageHeight") or 0), 853) if hit.get("imageHeight") else 0
            else:
                w = min(int(hit.get("imageWidth") or 0), 640)
                h = min(int(hit.get("imageHeight") or 0), 427) if hit.get("imageHeight") else 0
            out.append(
                Candidate(
                    provider=self.name,
                    asset_id=f"pixabay:{hit['id']}",
                    media_type=MediaType.IMAGE,
                    url=url,
                    width=w,
                    height=h,
                    author=hit.get("user", ""),
                    source_url=hit.get("pageURL", ""),
                    thumbnail_url=hit.get("previewURL", ""),
                    extra={"tags": hit.get("tags", "")},
                )
            )
        return out

    def _search_videos(self, query: str, per_page: int) -> List[Candidate]:
        resp = self._session.get(
            VIDEO_SEARCH_URL,
            params={
                "key": self.api_key,
                "q": query,
                "per_page": min(max(per_page, 3), 200),
                "safesearch": "true",
            },
            timeout=TIMEOUT,
        )
        self._raise_for_status(resp)
        out: List[Candidate] = []
        for hit in resp.json().get("hits", []):
            videos = hit.get("videos") or {}
            pick = None
            for key in ("large", "medium"):
                entry = videos.get(key) or {}
                if entry.get("url"):
                    pick = entry
                    break
            if not pick:
                continue
            out.append(
                Candidate(
                    provider=self.name,
                    asset_id=f"pixabay:{hit['id']}",
                    media_type=MediaType.VIDEO,
                    url=pick["url"],
                    width=int(pick.get("width") or 0),
                    height=int(pick.get("height") or 0),
                    duration=hit.get("duration"),
                    author=hit.get("user", ""),
                    source_url=hit.get("pageURL", ""),
                    thumbnail_url=(hit.get("picture_id") and "") or "",
                    extra={"tags": hit.get("tags", "")},
                )
            )
        return out

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.status_code == 401:
            raise RuntimeError("Pixabay rejected the API key (401 Unauthorized).")
        if resp.status_code == 429:
            raise RuntimeError("Pixabay rate limit reached (429) — try again later.")
        resp.raise_for_status()
