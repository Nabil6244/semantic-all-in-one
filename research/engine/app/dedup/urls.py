"""URL normalization and duplicate-page prevention."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Query params that carry no semantic meaning (tracking/session noise).
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref", "ref_src",
    "igshid", "spm", "_ga", "session_id", "sid",
}


def normalize_url(url: str) -> str:
    """Produce a canonical form of a URL for dedup/comparison purposes.

    - lowercases scheme/host
    - strips default ports, fragment, trailing slash
    - drops known tracking query params
    - sorts remaining query params
    """
    url = (url or "").strip()
    if not url:
        return url
    if "://" not in url:
        url = f"https://{url}"

    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if ":" in netloc:
        host, _, port = netloc.partition(":")
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    query_pairs = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query_pairs.sort()
    query = urlencode(query_pairs)

    return urlunparse((scheme, netloc, path, "", query, ""))


def url_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


class SeenUrls:
    """Tracks normalized URLs already visited/queued to avoid re-crawling."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_new(self, url: str) -> bool:
        return normalize_url(url) not in self._seen

    def mark(self, url: str) -> None:
        self._seen.add(normalize_url(url))

    def add_if_new(self, url: str) -> bool:
        """Returns True and marks it if unseen; False if already seen."""
        norm = normalize_url(url)
        if norm in self._seen:
            return False
        self._seen.add(norm)
        return True

    def __contains__(self, url: str) -> bool:
        return normalize_url(url) in self._seen
