"""NASA Image and Video Library backend — https://images.nasa.gov/docs/images.nasa.gov_public_api.html"""

from __future__ import annotations

import dataclasses
from typing import List, Optional

import requests

SEARCH_URL = "https://images-api.nasa.gov/search"
ASSET_URL = "https://images-api.nasa.gov/asset/{nasa_id}"
METADATA_URL = "https://images-api.nasa.gov/metadata/{nasa_id}"
TIMEOUT = 20
USER_AGENT = "SemanticVideoGenerator/1.0 (documentary clip search; local-app)"


@dataclasses.dataclass
class NasaCandidate:
    nasa_id: str
    title: str
    description: str = ""
    download_url: str = ""
    duration: Optional[float] = None
    source_url: str = ""

    @property
    def asset_id(self) -> str:
        return self.nasa_id


class NasaMediaBackend:
    name = "nasa"

    def __init__(self, max_results: int = 8):
        self.max_results = max(1, min(max_results, 25))
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def search(self, query: str, max_results: Optional[int] = None) -> List[NasaCandidate]:
        limit = max_results or self.max_results
        resp = self._session.get(
            SEARCH_URL,
            params={"q": query, "media_type": "video", "page_size": limit},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        items = (resp.json().get("collection") or {}).get("items") or []
        out: List[NasaCandidate] = []
        for item in items:
            data = item.get("data") or [{}]
            meta = data[0] if data else {}
            nasa_id = str(meta.get("nasa_id") or "").strip()
            if not nasa_id:
                for link in item.get("links") or []:
                    href = link.get("href") or ""
                    if "/asset/" in href:
                        nasa_id = href.rstrip("/").split("/")[-1]
                        break
            if not nasa_id:
                continue
            cand = self.resolve_nasa_id(nasa_id)
            if cand:
                cand.title = str(meta.get("title") or cand.title or nasa_id)
                cand.description = str(
                    meta.get("description") or meta.get("description_508") or cand.description
                )
                out.append(cand)
        return out

    def resolve_nasa_id(self, nasa_id: str) -> Optional[NasaCandidate]:
        ident = nasa_id.strip()
        if not ident:
            return None
        resp = self._session.get(ASSET_URL.format(nasa_id=ident), timeout=TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        items = (resp.json().get("collection") or {}).get("items") or []
        pick_url = None
        best_score = -1
        for item in items:
            href = item.get("href") or ""
            if not href:
                continue
            lower = href.lower()
            if not any(lower.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".m4v")):
                continue
            score = 0
            if "~orig" in lower:
                score += 100
            elif "~large" in lower:
                score += 40
            elif "~medium" in lower:
                score += 20
            elif "~small" in lower or "~mobile" in lower or "~thumb" in lower:
                score -= 50
            if lower.endswith(".mp4"):
                score += 5
            if score > best_score:
                best_score = score
                pick_url = href
        if not pick_url:
            return None
        return NasaCandidate(
            nasa_id=ident,
            title=ident,
            download_url=pick_url,
            source_url=f"https://images.nasa.gov/details/{ident}",
        )
