"""Weather's own HTTP cache: one folder per user, apart from every other style's cache.

A response is kept until the server's Expires (or Cache-Control max-age) says it is stale, else for `default_max_age_s`.
Asking again inside that window reads the file instead of the network, so a project re-checked a few times does not hit
api.weather.gov again. The cache never decides what is fresh enough for a video: that is weather.freshness, on the data's own
issue time."""

from __future__ import annotations

import email.utils
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional


def cache_root() -> Path:
    """Per-user cache folder for Weather (VIDEOGEN_WEATHER_CACHE overrides; tests use a temporary folder)."""
    override = os.environ.get("VIDEOGEN_WEATHER_CACHE")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "SemanticYTStudio" / "weather"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SemanticYTStudio" / "Cache" / "weather"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "semantic-yt-studio" / "weather"
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Response:
    status: int
    body: bytes
    headers: Dict[str, str]  # lower-case names
    fetched: datetime
    from_cache: bool = False


def expires_at(headers: Dict[str, str], fetched: datetime, default_max_age_s: float) -> datetime:
    cc = headers.get("cache-control", "")
    m = re.search(r"max-age=(\d+)", cc)
    if m:
        return fetched + timedelta(seconds=int(m.group(1)))
    exp = headers.get("expires")
    if exp:
        try:
            t = email.utils.parsedate_to_datetime(exp)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return t
        except (TypeError, ValueError):
            pass
    return fetched + timedelta(seconds=default_max_age_s)


class HttpCache:
    def __init__(self, root: Optional[Path] = None, *, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.root = Path(root) if root is not None else cache_root() / "http"
        self.root.mkdir(parents=True, exist_ok=True)
        self.now = now

    def _paths(self, url: str) -> "tuple[Path, Path]":
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.root / f"{key}.body", self.root / f"{key}.json"

    def get(self, url: str) -> Optional[Response]:
        """The cached response while it is still fresh by its own headers, else None."""
        body_p, meta_p = self._paths(url)
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            body = body_p.read_bytes()
        except (OSError, ValueError):
            return None
        if meta.get("url") != url:
            return None
        if datetime.fromisoformat(meta["expires"]) <= self.now():
            return None
        return Response(int(meta["status"]), body, dict(meta.get("headers") or {}), datetime.fromisoformat(meta["fetched"]), from_cache=True)

    def put(self, url: str, resp: Response, default_max_age_s: float) -> None:
        body_p, meta_p = self._paths(url)
        meta = {"url": url, "status": resp.status, "headers": resp.headers, "fetched": resp.fetched.isoformat(),
                "expires": expires_at(resp.headers, resp.fetched, default_max_age_s).isoformat()}
        tmp = body_p.with_suffix(".tmp")
        tmp.write_bytes(resp.body)
        os.replace(tmp, body_p)
        meta_p.write_text(json.dumps(meta), encoding="utf-8")
