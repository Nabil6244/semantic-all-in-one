"""robots.txt compliance and polite per-domain rate limiting.

Both are in-memory, scoped to a single crawl-provider instance (i.e. a
single research run). That's a deliberate simplification: runs are
short-lived CLI/library calls, not a long-running crawler daemon, so there's
no need to persist robots.txt or request-timing state across runs.
"""
from __future__ import annotations

import asyncio
import time
import urllib.robotparser
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx


class RobotsCache:
    """Fetches and caches robots.txt per host. Fails open: if robots.txt is
    unreachable or absent, the fetch is allowed (this is the conventional
    interpretation — no robots.txt means no stated restriction)."""

    def __init__(
        self,
        user_agent: str,
        timeout: float = 5.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.transport = transport
        self._parsers: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    async def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        lock = self._locks.setdefault(host_key, asyncio.Lock())

        async with lock:
            if host_key not in self._parsers:
                self._parsers[host_key] = await self._fetch(host_key)

        parser = self._parsers[host_key]
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:  # noqa: BLE001 - malformed robots.txt content
            return True

    async def _fetch(self, host_key: str) -> Optional[urllib.robotparser.RobotFileParser]:
        robots_url = f"{host_key}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                resp = await client.get(robots_url)
            if resp.status_code >= 400:
                return None
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(resp.text.splitlines())
            return parser
        except httpx.HTTPError:
            return None


class DomainRateLimiter:
    """Enforces a minimum interval between requests to the same host."""

    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval_seconds = min_interval_seconds
        self._last_request: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    async def wait(self, url: str) -> None:
        if self.min_interval_seconds <= 0:
            return
        host = urlparse(url).netloc
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            last = self._last_request.get(host)
            now = time.monotonic()
            if last is not None:
                elapsed = now - last
                if elapsed < self.min_interval_seconds:
                    await asyncio.sleep(self.min_interval_seconds - elapsed)
            self._last_request[host] = time.monotonic()
