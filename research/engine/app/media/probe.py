"""Actual image dimension probing — measures real pixel dimensions from an
image's header bytes, without downloading the whole file.

Why this exists
---------------
A URL is never evidence of resolution. `house_2048.jpg` may really be
640x480, and `Content-Length` only tells you how many bytes there are, not
how many pixels. Ranking media by declared/guessed size therefore selects
the wrong variant. This module fetches the smallest prefix of each image
that still contains its dimension header and reports the MEASURED size, so
ranking and variant election can run on facts.

Header parsing is delegated to `imagesize` (MIT, pure-Python, no
dependencies) rather than reimplemented: it covers JPEG/PNG/WebP(VP8,
VP8L, VP8X)/GIF/BMP/TIFF/AVIF/HEIC/SVG and parses correctly from as little
as ~1KB. The progressive-Range fetch strategy below follows the approach
FastImage (MIT, Ruby) established: ask for a small prefix, and only escalate
when the parser says it needs more.

Everything here is best-effort and never raises: an unprobeable image keeps
whatever declared dimensions it already had and is marked accordingly, so a
blocked CDN or an exotic format degrades one candidate rather than failing
the scrape (see `ProbeStatus`).
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional

import httpx

# Progressive prefix sizes. Almost every JPEG/PNG/WebP/GIF resolves at the
# first step; the larger steps exist for files carrying a big EXIF/ICC block
# ahead of the SOF marker. The last value is a hard ceiling — we never fetch
# a whole image just to measure it.
PROBE_STEPS = (2048, 16384, 65536)
MAX_PROBE_BYTES = PROBE_STEPS[-1]

DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT_SECONDS = 10.0

_PROBE_HEADERS = {
    "User-Agent": "SemanticResearchEngine/0.2 (research-only)",
    "Accept": "image/*,*/*;q=0.8",
}


class ProbeStatus(str, Enum):
    """Outcome of a probe attempt. Anything other than MEASURED means the
    asset's dimensions are NOT verified and must not be treated as such."""

    MEASURED = "measured"
    """Actual dimensions parsed from real header bytes."""
    UNSUPPORTED_FORMAT = "unsupported_format"
    """Bytes were fetched, but no parser recognized the header."""
    FETCH_FAILED = "fetch_failed"
    """Network error, timeout, or an HTTP error status."""
    NOT_PROBED = "not_probed"
    """Never attempted (e.g. a video, or an embed reference)."""


@dataclass
class ProbeResult:
    url: str
    status: ProbeStatus = ProbeStatus.NOT_PROBED
    actual_width: Optional[int] = None
    actual_height: Optional[int] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    """Reported byte size. Recorded for diagnostics only — byte size is
    never used as a resolution signal."""
    bytes_fetched: int = 0
    used_range: bool = False
    """False when the server ignored our Range header and streamed a 200;
    we stop reading early either way, but this shows which happened."""
    error: Optional[str] = None

    @property
    def measured(self) -> bool:
        return self.status is ProbeStatus.MEASURED and bool(self.actual_width and self.actual_height)

    @property
    def long_side(self) -> Optional[int]:
        if not self.measured:
            return None
        return max(int(self.actual_width or 0), int(self.actual_height or 0))


def parse_dimensions(data: bytes) -> Optional[tuple[int, int]]:
    """Dimensions from raw header bytes, or None if this prefix isn't
    enough (or isn't a recognized image). Never raises."""
    if not data:
        return None
    try:
        import imagesize
    except ImportError:
        return None
    try:
        width, height = imagesize.get(io.BytesIO(data))
    except Exception:  # noqa: BLE001 - malformed/truncated/unsupported header
        return None
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


async def _fetch_prefix(
    client: httpx.AsyncClient, url: str, max_bytes: int, timeout: float,
) -> tuple[Optional[bytes], Optional[httpx.Response], bool, Optional[str]]:
    """Fetch at most `max_bytes` from `url`. Returns (data, response,
    used_range, error). Sends a Range header; if the server ignores it and
    replies 200 we stop reading the stream ourselves, so an oversized image
    still costs only `max_bytes` off the wire."""
    headers = dict(_PROBE_HEADERS)
    headers["Range"] = f"bytes=0-{max_bytes - 1}"
    try:
        async with client.stream("GET", url, headers=headers, timeout=timeout) as resp:
            if resp.status_code >= 400:
                return None, resp, False, f"HTTP {resp.status_code}"
            used_range = resp.status_code == 206
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                if len(buf) >= max_bytes:
                    break
            return bytes(buf[:max_bytes]), resp, used_range, None
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        return None, None, False, str(exc)
    except Exception as exc:  # noqa: BLE001 - probing must never be fatal
        return None, None, False, str(exc)


async def probe_image(
    client: httpx.AsyncClient,
    url: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    steps: Iterable[int] = PROBE_STEPS,
) -> ProbeResult:
    """Measure one image's real dimensions. Escalates through `steps` only
    while the parser reports it needs more bytes."""
    result = ProbeResult(url=url)
    last_error: Optional[str] = None

    for max_bytes in steps:
        data, resp, used_range, error = await _fetch_prefix(client, url, max_bytes, timeout)
        if error is not None:
            last_error = error
            # An HTTP error status won't improve with a bigger Range.
            if error.startswith("HTTP "):
                break
            continue
        if resp is not None:
            result.content_type = resp.headers.get("content-type") or result.content_type
            raw_len = resp.headers.get("content-range") or resp.headers.get("content-length")
            if raw_len:
                total = str(raw_len).split("/")[-1].strip()
                if total.isdigit():
                    result.content_length = int(total)
        result.bytes_fetched = len(data or b"")
        result.used_range = used_range

        dims = parse_dimensions(data or b"")
        if dims is not None:
            result.actual_width, result.actual_height = dims
            result.status = ProbeStatus.MEASURED
            return result

        # Parser couldn't resolve it AND the server already gave us the
        # entire file — more bytes are not available, so stop escalating.
        if result.content_length is not None and result.bytes_fetched >= result.content_length:
            break
        if data is not None and len(data) < max_bytes:
            break

    if last_error is not None and result.bytes_fetched == 0:
        result.status = ProbeStatus.FETCH_FAILED
        result.error = last_error
    else:
        result.status = ProbeStatus.UNSUPPORTED_FORMAT
        result.error = last_error
    return result


class ProbeCache:
    """Process-local URL -> ProbeResult memo. The same photo commonly shows
    up under several discovery sources within one run, and variant families
    re-probe the same members; measuring each URL once keeps the added
    request count proportional to distinct URLs, not candidates."""

    def __init__(self) -> None:
        self._results: Dict[str, ProbeResult] = {}
        self.hits = 0
        self.misses = 0

    def get(self, url: str) -> Optional[ProbeResult]:
        found = self._results.get(url)
        if found is not None:
            self.hits += 1
        return found

    def put(self, url: str, result: ProbeResult) -> None:
        self._results[url] = result
        self.misses += 1

    def __len__(self) -> int:
        return len(self._results)


async def probe_images(
    urls: List[str],
    concurrency: int = DEFAULT_CONCURRENCY,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    http_client: Optional[httpx.AsyncClient] = None,
    cache: Optional[ProbeCache] = None,
) -> Dict[str, ProbeResult]:
    """Probe many URLs under bounded concurrency. Returns url -> result for
    every input URL (duplicates collapse). `http_client` is the injection
    point for tests (httpx.MockTransport), so the suite needs no network."""
    cache = cache if cache is not None else ProbeCache()
    unique = list(dict.fromkeys(u for u in urls if u))
    out: Dict[str, ProbeResult] = {}

    pending: List[str] = []
    for url in unique:
        cached = cache.get(url)
        if cached is not None:
            out[url] = cached
        else:
            pending.append(url)

    if not pending:
        return out

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(client: httpx.AsyncClient, url: str) -> tuple[str, ProbeResult]:
        async with semaphore:
            return url, await probe_image(client, url, timeout=timeout)

    async def run(client: httpx.AsyncClient) -> None:
        for url, result in await asyncio.gather(*[one(client, u) for u in pending]):
            cache.put(url, result)
            out[url] = result

    if http_client is not None:
        await run(http_client)
    else:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            await run(client)
    return out
