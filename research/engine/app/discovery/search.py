"""Search/discovery provider interface.

The engine core never depends on one search vendor. `DirectURLProvider`
requires no network and no API key (used whenever the caller already
supplies URLs). `TavilySearchProvider` is an optional adapter used to turn
generated queries into candidate URLs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Protocol
from urllib.parse import parse_qs, urlparse


@dataclass
class SearchResult:
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]: ...


class DirectURLProvider:
    """No-op provider: just wraps a fixed URL list. Used when the caller
    already knows the URLs to research (or for fixture/offline runs)."""

    name = "direct"

    def __init__(self, urls: List[str]):
        self._urls = urls

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        return [SearchResult(url=u) for u in self._urls[:max_results]]


class TavilySearchProvider:
    """Adapter over the Tavily search API. Requires `tavily-python` and a
    TAVILY_API_KEY (or explicit api_key). Import is lazy so the core engine
    never requires this dependency."""

    name = "tavily"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        if not self.api_key:
            raise RuntimeError(
                "Tavily search requires TAVILY_API_KEY (or api_key=...). "
                "Install with: pip install 'semantic-research-engine[tavily]'"
            )
        try:
            from tavily import TavilyClient
        except ImportError as exc:
            raise RuntimeError(
                "tavily-python is not installed. Install it with: "
                "pip install 'semantic-research-engine[tavily]'"
            ) from exc

        import asyncio

        def _run():
            client = TavilyClient(api_key=self.api_key)
            return client.search(query=query, max_results=max_results)

        response = await asyncio.to_thread(_run)
        results = response.get("results", []) if isinstance(response, dict) else []
        return [
            SearchResult(url=r.get("url"), title=r.get("title"), snippet=r.get("content"))
            for r in results if r.get("url")
        ]


class DuckDuckGoSearchProvider:
    """No-API-key web search: scrapes DuckDuckGo's HTML-only endpoint
    (html.duckduckgo.com), which is intentionally lightweight/unstyled and
    more tolerant of plain automated GET requests than the JS-heavy main
    site. Uses only core deps (httpx + BeautifulSoup) — no optional extra
    required, unlike TavilySearchProvider.

    Best-effort by design: any network/parse failure returns an empty list
    rather than raising, matching NullSearchProvider's safe-default
    behavior — a flaky scrape must never break a research run.
    """

    name = "duckduckgo"
    _ENDPOINT = "https://html.duckduckgo.com/html/"

    def __init__(self, timeout: float = 10.0, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (compatible; SemanticResearchEngine/1.0; +https://example.invalid/bot)"
        )

    def _resolve_url(self, href: str) -> Optional[str]:
        if not href:
            return None
        # DuckDuckGo's HTML results wrap outbound links in a redirect:
        # //duckduckgo.com/l/?uddg=<url-encoded-target>&rut=...
        if "duckduckgo.com/l/" in href or href.startswith("/l/"):
            parsed = urlparse(href if "://" in href else f"https:{href}")
            target = parse_qs(parsed.query).get("uddg", [None])[0]
            return target or None
        return href

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(
                    self._ENDPOINT, params={"q": query}, headers={"User-Agent": self.user_agent},
                )
                resp.raise_for_status()
                html = resp.text
        except Exception:  # noqa: BLE001 - best-effort search, never fatal to a research run
            return []

        try:
            soup = BeautifulSoup(html, "lxml")
            results: List[SearchResult] = []
            for result_div in soup.select("div.result"):
                link = result_div.select_one("a.result__a")
                if link is None or not link.get("href"):
                    continue
                url = self._resolve_url(link["href"])
                if not url:
                    continue
                title = link.get_text(strip=True) or None
                snippet_el = result_div.select_one(".result__snippet")
                snippet = snippet_el.get_text(strip=True) if snippet_el else None
                results.append(SearchResult(url=url, title=title, snippet=snippet))
                if len(results) >= max_results:
                    break
            return results
        except Exception:  # noqa: BLE001 - malformed/changed HTML must not raise
            return []


class NullSearchProvider:
    """Returns no results. Safe default when no search backend is configured
    and only direct URLs were supplied."""

    name = "null"

    async def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        return []
