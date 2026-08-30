"""Page fetching (via pluggable providers) and top-level page extraction.

The engine core never depends on a specific crawling backend. `CrawlProvider`
is the seam: `HttpxCrawlProvider` is the always-available default for plain
HTML pages; `Crawl4AIProvider` is the primary provider for JS-rendered pages
(used automatically by `EscalatingCrawlProvider` when a page looks like it
needs a browser); `FirecrawlProvider` is an optional fallback. A
`StaticHtmlProvider` exists so tests can exercise the full extraction
pipeline without any network access.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

import httpx
from bs4 import BeautifulSoup

from app.extraction.metadata import extract_page_metadata
from app.extraction.robots import DomainRateLimiter, RobotsCache
from app.extraction.structured_data import parse_json_ld, parse_opengraph
from app.models.source import AccessStatus

DEFAULT_USER_AGENT = (
    "SemanticResearchEngine/0.2 (+https://example.invalid/bot; research-only)"
)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def classify_access_status(status_code: Optional[int], error: Optional[str]) -> AccessStatus:
    if status_code is not None and status_code < 400:
        return AccessStatus.OK
    if status_code == 404:
        return AccessStatus.NOT_FOUND
    if status_code in (401, 403):
        return AccessStatus.FORBIDDEN
    err = (error or "").lower()
    if "robots" in err:
        return AccessStatus.ROBOTS_DISALLOWED
    if "timeout" in err or "timed out" in err:
        return AccessStatus.TIMEOUT
    if status_code is not None and status_code >= 400:
        return AccessStatus.NETWORK_ERROR
    if error:
        return AccessStatus.NETWORK_ERROR
    return AccessStatus.UNKNOWN_ERROR


@dataclass
class FetchResult:
    url: str
    final_url: str
    html: str
    status_code: Optional[int]
    accessible: bool
    error: Optional[str] = None
    access_status: AccessStatus = AccessStatus.OK
    fetched_at: float = field(default_factory=time.time)
    provider: str = "unknown"


class CrawlProvider(Protocol):
    """Fetches a URL and returns raw HTML. Implementations must not bypass
    login, CAPTCHAs, paywalls, or anti-bot protections."""

    name: str

    async def fetch(self, url: str) -> FetchResult: ...


class HttpxCrawlProvider:
    """Lightweight default provider: plain HTTP GET, no JS rendering.

    Polite by default: checks robots.txt (fail-open if unreachable) and
    applies a minimum per-domain interval between requests. Transient
    failures (timeouts, connection errors, 429/5xx) get a short retry with
    backoff before giving up.
    """

    name = "httpx"

    def __init__(
        self,
        timeout: float = 15.0,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_robots: bool = True,
        min_interval_seconds: float = 0.5,
        max_retries: int = 2,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self.max_retries = max_retries
        self.transport = transport
        self._robots = (
            RobotsCache(user_agent=user_agent, timeout=min(timeout, 5.0), transport=transport)
            if respect_robots else None
        )
        self._rate_limiter = DomainRateLimiter(min_interval_seconds=min_interval_seconds)

    async def fetch(self, url: str) -> FetchResult:
        if self._robots is not None and not await self._robots.is_allowed(url):
            return FetchResult(
                url=url, final_url=url, html="", status_code=None, accessible=False,
                error="disallowed by robots.txt", access_status=AccessStatus.ROBOTS_DISALLOWED,
                provider=self.name,
            )

        await self._rate_limiter.wait(url)
        headers = {"User-Agent": self.user_agent}
        last_error: Optional[str] = None
        last_status: Optional[int] = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, follow_redirects=True, headers=headers, transport=self.transport,
                ) as client:
                    resp = await client.get(url)
                accessible = resp.status_code < 400
                if not accessible and resp.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                    last_status, last_error = resp.status_code, f"HTTP {resp.status_code}"
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                return FetchResult(
                    url=url,
                    final_url=str(resp.url),
                    html=resp.text if accessible else "",
                    status_code=resp.status_code,
                    accessible=accessible,
                    error=None if accessible else f"HTTP {resp.status_code}",
                    access_status=classify_access_status(resp.status_code, None if accessible else f"HTTP {resp.status_code}"),
                    provider=self.name,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue

        return FetchResult(
            url=url, final_url=url, html="", status_code=last_status,
            accessible=False, error=last_error or "fetch_failed",
            access_status=classify_access_status(last_status, last_error),
            provider=self.name,
        )


class StaticHtmlProvider:
    """Serves pre-loaded HTML for a fixed set of URLs. Used in tests and for
    direct `--url file://...` fixture inspection — never touches the network."""

    name = "static"

    def __init__(self, pages: dict[str, str]):
        self._pages = pages

    async def fetch(self, url: str) -> FetchResult:
        if url in self._pages:
            return FetchResult(
                url=url, final_url=url, html=self._pages[url],
                status_code=200, accessible=True, provider=self.name,
            )
        path = url[len("file://"):] if url.startswith("file://") else url
        p = Path(path)
        if p.exists():
            return FetchResult(
                url=url, final_url=url, html=p.read_text(encoding="utf-8"),
                status_code=200, accessible=True, provider=self.name,
            )
        return FetchResult(
            url=url, final_url=url, html="", status_code=None,
            accessible=False, error="not found in static provider",
            access_status=AccessStatus.NOT_FOUND, provider=self.name,
        )


class Crawl4AIProvider:
    """Primary crawling provider for JS-rendered pages, backed by Crawl4AI
    (optional dependency).

    Install with: pip install "semantic-research-engine[crawl4ai]"
    Crawl4AI handles JS rendering, bot-friendly fetching, and markdown/media
    extraction. We only consume `.html` here; structured data / media
    discovery still run through our own domain-agnostic parsers so output
    shape does not depend on Crawl4AI internals.
    """

    name = "crawl4ai"

    def __init__(self, **crawler_kwargs):
        self._crawler_kwargs = crawler_kwargs
        self._crawler = None

    async def _get_crawler(self):
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as exc:
            raise RuntimeError(
                "crawl4ai is not installed. Install it with: "
                "pip install 'semantic-research-engine[crawl4ai]'"
            ) from exc
        if self._crawler is None:
            self._crawler = AsyncWebCrawler(**self._crawler_kwargs)
            await self._crawler.__aenter__()
        return self._crawler

    async def fetch(self, url: str) -> FetchResult:
        crawler = await self._get_crawler()
        try:
            result = await crawler.arun(url=url)
            accessible = bool(getattr(result, "success", True))
            html = getattr(result, "html", "") or ""
            status = getattr(result, "status_code", 200 if accessible else None)
            error = None if accessible else getattr(result, "error_message", "crawl4ai failure")
            return FetchResult(
                url=url,
                final_url=getattr(result, "url", url) or url,
                html=html,
                status_code=status,
                accessible=accessible and bool(html),
                error=error,
                access_status=classify_access_status(status, error),
                provider=self.name,
            )
        except Exception as exc:  # noqa: BLE001 - surface any backend failure as inaccessible
            return FetchResult(
                url=url, final_url=url, html="", status_code=None,
                accessible=False, error=str(exc),
                access_status=AccessStatus.UNKNOWN_ERROR, provider=self.name,
            )

    async def close(self):
        if self._crawler is not None:
            await self._crawler.__aexit__(None, None, None)
            self._crawler = None


class FirecrawlProvider:
    """Optional fallback provider for pages Crawl4AI struggles with (heavy
    JS, aggressive anti-bot). Requires FIRECRAWL_API_KEY."""

    name = "firecrawl"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def fetch(self, url: str) -> FetchResult:
        try:
            from firecrawl import FirecrawlApp
        except ImportError as exc:
            raise RuntimeError(
                "firecrawl-py is not installed. Install it with: "
                "pip install 'semantic-research-engine[firecrawl]'"
            ) from exc

        def _scrape():
            app = FirecrawlApp(api_key=self.api_key)
            return app.scrape_url(url, params={"formats": ["html"]})

        try:
            data = await asyncio.to_thread(_scrape)
            html = data.get("html", "") if isinstance(data, dict) else getattr(data, "html", "")
            return FetchResult(
                url=url, final_url=url, html=html or "", status_code=200,
                accessible=bool(html), provider=self.name,
            )
        except Exception as exc:  # noqa: BLE001
            return FetchResult(
                url=url, final_url=url, html="", status_code=None,
                accessible=False, error=str(exc),
                access_status=AccessStatus.UNKNOWN_ERROR, provider=self.name,
            )


# --- dynamic-page escalation -------------------------------------------------

_SPA_ROOT_RE = re.compile(
    r'<div[^>]+id=["\'](?:root|app|__next|___gatsby)["\']', re.I
)
_NOSCRIPT_WARNING_RE = re.compile(r"enable\s+javascript", re.I)


def needs_js_rendering(html: str) -> bool:
    """Cheap heuristic for "this page is probably a JS shell with no real
    content in the raw HTML" — used to decide whether it's worth escalating
    to a browser-rendering provider. Deliberately conservative: false
    negatives (missing a JS-only page) are fine, false positives make every
    page expensive."""
    if not html:
        return False
    body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.I | re.S)
    body = body_match.group(1) if body_match else html
    text_only = re.sub(r"<[^>]+>", " ", body)
    text_only = " ".join(text_only.split())

    if _NOSCRIPT_WARNING_RE.search(html):
        return True
    if len(text_only) < 200 and _SPA_ROOT_RE.search(html):
        return True
    return False


class EscalatingCrawlProvider:
    """Uses a cheap primary provider (typically `HttpxCrawlProvider`) for
    every page, and only escalates to a heavier secondary provider (typically
    `Crawl4AIProvider`) when the primary result looks like a JS-only shell.
    Keeps the default path lightweight — most pages never touch the
    secondary provider."""

    name = "auto"

    def __init__(self, primary: CrawlProvider, secondary: Optional[CrawlProvider] = None):
        self.primary = primary
        self.secondary = secondary

    async def fetch(self, url: str) -> FetchResult:
        result = await self.primary.fetch(url)
        if not result.accessible or not needs_js_rendering(result.html) or self.secondary is None:
            return result

        try:
            escalated = await self.secondary.fetch(url)
        except Exception:  # noqa: BLE001 - secondary provider not usable, keep primary result
            return result

        if escalated.accessible and escalated.html:
            return escalated
        return result

    async def close(self):
        for provider in (self.primary, self.secondary):
            close = getattr(provider, "close", None)
            if close is not None:
                await close()


@dataclass
class PageExtraction:
    """Everything extracted from a single fetched page, provider-agnostic."""

    url: str
    final_url: str
    accessible: bool
    status_code: Optional[int]
    error: Optional[str]
    access_status: AccessStatus = AccessStatus.OK
    title: Optional[str] = None
    description: Optional[str] = None
    canonical_url: Optional[str] = None
    published_date: Optional[str] = None
    visible_text: str = ""
    opengraph: dict = field(default_factory=dict)
    json_ld: list = field(default_factory=list)
    soup: Optional[BeautifulSoup] = None
    provider: str = "unknown"
    fetched_at: float = field(default_factory=time.time)


async def fetch_and_extract(url: str, provider: CrawlProvider) -> PageExtraction:
    """Fetch `url` via `provider` and run domain-agnostic extraction on the HTML."""
    result = await provider.fetch(url)
    if not result.accessible or not result.html:
        access_status = result.access_status
        error = result.error or "inaccessible"
        if result.accessible and not result.html:
            # Provider reported a successful status (e.g. HTTP 202) but the
            # body was empty — don't let that surface as access_status="ok".
            # Common with anti-bot challenge/interstitial responses.
            access_status = AccessStatus.EMPTY_RESPONSE
            error = f"empty response body (HTTP {result.status_code})"
        return PageExtraction(
            url=url,
            final_url=result.final_url,
            accessible=False,
            status_code=result.status_code,
            error=error,
            access_status=access_status,
            provider=result.provider,
        )

    soup = BeautifulSoup(result.html, "lxml")
    meta = extract_page_metadata(result.html)
    json_ld = parse_json_ld(soup)
    og = meta["opengraph"]

    return PageExtraction(
        url=url,
        final_url=result.final_url,
        accessible=True,
        status_code=result.status_code,
        error=None,
        access_status=AccessStatus.OK,
        title=meta["title"],
        description=meta["description"],
        canonical_url=meta["canonical_url"],
        published_date=meta["published_date"],
        visible_text=meta["visible_text"],
        opengraph=og,
        json_ld=json_ld,
        soup=soup,
        provider=result.provider,
    )
