"""Internet Archive search backend — https://archive.org/help/aboutsearch.htm"""

from __future__ import annotations

import dataclasses
from typing import List, Optional
from urllib.parse import quote

import requests

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_BASE = "https://archive.org/download"
TIMEOUT = 20
USER_AGENT = "SemanticVideoGenerator/1.0 (documentary clip search; contact: local-app)"


@dataclasses.dataclass
class ArchiveCandidate:
    identifier: str
    title: str
    description: str = ""
    collection: str = ""
    download_url: str = ""
    filename: str = ""
    duration: Optional[float] = None
    width: int = 0
    height: int = 0
    source_url: str = ""

    @property
    def asset_id(self) -> str:
        return self.identifier


class InternetArchiveBackend:
    name = "archive"

    def __init__(self, max_results: int = 8):
        self.max_results = max(1, min(max_results, 25))
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def search(self, query: str, max_results: Optional[int] = None) -> List[ArchiveCandidate]:
        limit = max_results or self.max_results
        q = f'({query}) AND mediatype:(movies OR video)'
        resp = self._session.get(
            SEARCH_URL,
            params={
                "q": q,
                "fl[]": ["identifier", "title", "description", "collection"],
                "rows": limit,
                "page": 1,
                "output": "json",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        docs = (resp.json().get("response") or {}).get("docs") or []
        out: List[ArchiveCandidate] = []
        for doc in docs:
            ident = doc.get("identifier")
            if not ident:
                continue
            cand = self.resolve_identifier(str(ident))
            if cand:
                cand.title = cand.title or str(doc.get("title") or ident)
                cand.description = cand.description or str(doc.get("description") or "")
                col = doc.get("collection")
                if isinstance(col, list):
                    cand.collection = ", ".join(str(c) for c in col[:3])
                elif col:
                    cand.collection = str(col)
                out.append(cand)
        return out

    def resolve_identifier(self, identifier: str) -> Optional[ArchiveCandidate]:
        ident = identifier.strip()
        if not ident:
            return None
        resp = self._session.get(METADATA_URL.format(identifier=quote(ident)), timeout=TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files") or []
        pick = self._pick_video_file(files)
        if not pick:
            return None
        name = pick["name"]
        url = f"{DOWNLOAD_BASE}/{ident}/{quote(name)}"
        duration = None
        if pick.get("length"):
            try:
                duration = float(pick["length"])
            except (TypeError, ValueError):
                pass
        meta = data.get("metadata") or {}
        return ArchiveCandidate(
            identifier=ident,
            title=str(meta.get("title") or ident),
            description=str(meta.get("description") or ""),
            collection=str(meta.get("collection") or ""),
            download_url=url,
            filename=name,
            duration=duration,
            width=int(pick.get("width") or 0),
            height=int(pick.get("height") or 0),
            source_url=f"https://archive.org/details/{ident}",
        )

    @staticmethod
    def _pick_video_file(files: list) -> Optional[dict]:
        scored = []
        for f in files:
            name = (f.get("name") or "").lower()
            fmt = (f.get("format") or "").lower()
            if any(x in name for x in (".xml", ".torrent", ".gif", ".jpg", ".png", ".json", ".srt")):
                continue
            if any(x in name for x in ("thumb", "metadata", "preview", "sample", "proxy", "contact")):
                continue
            if not any(name.endswith(ext) for ext in (".mp4", ".mpeg", ".mpg", ".mov", ".ogv", ".webm", ".m4v")):
                if "h.264" not in fmt and "mpeg4" not in fmt and "video" not in fmt:
                    continue
            size = 0
            try:
                size = int(f.get("size") or 0)
            except (TypeError, ValueError):
                pass
            if size and size > 2 * 1024 * 1024 * 1024:
                continue
            score = 0
            width = int(f.get("width") or 0)
            height = int(f.get("height") or 0)
            if width and height:
                score += min(width * height // 100000, 30)
            if size:
                score += min(size // (10 * 1024 * 1024), 25)
            if name.endswith((".mpeg", ".mpg", ".mov", ".ogv")):
                score += 8
            if name.endswith(".mp4"):
                score += 4
            if any(x in name for x in ("512kb", "256kb", "128kb", "_480.", "-480.", "proxy")):
                score -= 20
            scored.append((score, f))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
