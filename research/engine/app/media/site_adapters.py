"""Site-specific media adapters.

Adapters only ever ADD information on top of generic discovery — they never
replace it. If no adapter matches a host, or an adapter declines to answer,
the generic behaviour is used unchanged, so a site redesign degrades this
layer to "no extra help" rather than breaking extraction.

Today each adapter contributes one thing: a better VARIANT KEY. Generic
grouping (media/variants.py) recognizes size markers that are encoded in a
filename suffix or path segment, which covers most CDNs. Some sites instead
encode the rendition in a *renderer prefix*, which no generic rule can infer
without guessing — and guessing is exactly what must not happen here, since
a false merge deletes a real photograph.

The Redfin rule below was derived from live observation, not assumption:
probing redfin.com's own CDN showed

    .../photo/9/bcsphoto/580/genBcs.426157580_1.webp          -> 320x230
    .../photo/9/islphoto/580/genIslnoResize.426157580_1.webp  -> 640x460

i.e. one photo (id 426157580, index 1) served by two renderers at two sizes.
Both are genuine, site-exposed URLs; nothing is rewritten or invented.
"""
from __future__ import annotations

import re
from typing import List, Optional, Protocol
from urllib.parse import urlparse


class SiteAdapter(Protocol):
    name: str

    def matches(self, url: str) -> bool: ...

    def variant_key(self, url: str) -> Optional[str]:
        """A grouping key for this URL, or None to defer to generic logic."""
        ...


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""


class RedfinAdapter:
    """Redfin photo CDN: `gen<Renderer>.<photo_id>_<index...>.<ext>` under
    `/photo/<n>/<renderer>photo/<bucket>/`. The renderer segment and prefix
    determine the rendition; the photo id + index determine WHICH photo."""

    name = "redfin"
    _HOSTS = ("redfin.com", "rdcpix.com", "ssl.cdn-redfin.com")
    _FILE_RE = re.compile(
        r"^gen[A-Za-z]+\.(?P<pid>\d+(?:_\d+)*)\.(?P<ext>\w+)$", re.I,
    )
    _PATH_RE = re.compile(r"/photo/\d+/[a-z]+photo/\d+/", re.I)

    def matches(self, url: str) -> bool:
        host = _host(url)
        return any(host == h or host.endswith("." + h) for h in self._HOSTS)

    def variant_key(self, url: str) -> Optional[str]:
        base = url.split("#", 1)[0].split("?", 1)[0]
        filename = base.rsplit("/", 1)[-1]
        match = self._FILE_RE.match(filename)
        if not match:
            return None
        if not self._PATH_RE.search(base):
            return None
        # Collapse the renderer-specific path segment and filename prefix;
        # keep host + photo identity so different photos never merge.
        return f"redfin://{_host(url)}/{match.group('pid')}"


class ZillowAdapter:
    """Zillow photo CDN. The generic suffix rules already cover `-cc_ft_<w>`
    and `-uncropped_scaled_within_<w>_<h>`; this adapter exists to pin that
    behaviour to the host and to strip the `-p_<letter>` profile suffix that
    generic rules deliberately will not touch (a bare `-p_e` carries no
    plausible dimension, so generic logic cannot tell it is a rendition)."""

    name = "zillow"
    _HOSTS = ("zillowstatic.com", "zillow.com")
    _RENDITION_RE = re.compile(
        r"(-cc_ft_\d{2,5}|-uncropped_scaled_within_\d{2,5}_\d{2,5}|-p_[a-z])+$", re.I,
    )

    def matches(self, url: str) -> bool:
        host = _host(url)
        return any(host == h or host.endswith("." + h) for h in self._HOSTS)

    def variant_key(self, url: str) -> Optional[str]:
        base = url.split("#", 1)[0].split("?", 1)[0]
        head, dot, ext = base.rpartition(".")
        if not dot or len(ext) > 5:
            return None
        stripped = self._RENDITION_RE.sub("", head)
        if stripped == head:
            return None
        if len(stripped.rsplit("/", 1)[-1]) < 3:
            return None
        return f"{stripped}.{ext}"


DEFAULT_ADAPTERS: List[SiteAdapter] = [RedfinAdapter(), ZillowAdapter()]


def adapter_for(url: str, adapters: Optional[List[SiteAdapter]] = None) -> Optional[SiteAdapter]:
    for adapter in (adapters if adapters is not None else DEFAULT_ADAPTERS):
        try:
            if adapter.matches(url):
                return adapter
        except Exception:  # noqa: BLE001 - a broken adapter must not break discovery
            continue
    return None


def adapter_variant_key(url: str, adapters: Optional[List[SiteAdapter]] = None) -> Optional[str]:
    """Site-specific grouping key, or None to fall back to generic logic."""
    adapter = adapter_for(url, adapters)
    if adapter is None:
        return None
    try:
        return adapter.variant_key(url)
    except Exception:  # noqa: BLE001
        return None
