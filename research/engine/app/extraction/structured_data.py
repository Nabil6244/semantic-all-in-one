"""JSON-LD (schema.org), OpenGraph, and microdata-lite extraction from raw HTML.

Pure functions operating on an HTML string — no network access — so they can
be exercised directly against local fixtures in tests.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup


def parse_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract all JSON-LD blocks, flattening @graph arrays. Skips malformed blocks."""
    results: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if "@graph" in item and isinstance(item["@graph"], list):
                for sub in item["@graph"]:
                    if isinstance(sub, dict):
                        results.append(sub)
            else:
                results.append(item)
    return results


def find_entities_by_type(json_ld_blocks: List[Dict[str, Any]], *types: str) -> List[Dict[str, Any]]:
    """Return JSON-LD entities whose @type matches any of `types` (case-insensitive)."""
    wanted = {t.lower() for t in types}
    matches = []
    for block in json_ld_blocks:
        raw_type = block.get("@type")
        block_types = raw_type if isinstance(raw_type, list) else [raw_type]
        block_types = {str(t).lower() for t in block_types if t}
        if block_types & wanted:
            matches.append(block)
    return matches


def parse_opengraph(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract og:* and twitter:* meta tags into a flat dict."""
    og: Dict[str, str] = {}
    for tag in soup.find_all("meta"):
        prop = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if not prop or content is None:
            continue
        prop = prop.strip().lower()
        if prop.startswith("og:") or prop.startswith("twitter:"):
            og.setdefault(prop, content.strip())
    return og


def opengraph_images(og: Dict[str, str]) -> List[str]:
    urls = []
    for key in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
        val = og.get(key)
        if val:
            urls.append(val)
    return urls


def opengraph_videos(og: Dict[str, str]) -> List[str]:
    urls = []
    for key in ("og:video", "og:video:url", "og:video:secure_url"):
        val = og.get(key)
        if val:
            urls.append(val)
    return urls


def jsonld_images(entity: Dict[str, Any]) -> List[str]:
    """Normalize a JSON-LD `image` field (str, list, or ImageObject) to URLs."""
    raw = entity.get("image")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    urls = []
    for item in items:
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict):
            url = item.get("url") or item.get("contentUrl")
            if url:
                urls.append(url)
    return urls


def jsonld_video_objects(json_ld_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return find_entities_by_type(json_ld_blocks, "VideoObject")


# Many modern sites (Zillow among them — a Next.js/React app) render their
# gallery UI client-side from a JSON payload embedded in the page, separate
# from any <img>/srcset markup: Next.js's own SSR hydration script
# (`<script id="__NEXT_DATA__" type="application/json">`) is the most common
# shape, but this deliberately matches *any* `type="application/json"` script
# tag rather than hardcoding that one id — other frameworks (Nuxt, custom
# SSR setups) use the same "application/json" convention with a different
# id. Full-resolution originals are frequently only present here, never as a
# rendered <img> at all (e.g. a lightbox's images that only mount on click).
_IMAGE_URL_RE = re.compile(r"^https?://\S+\.(?:jpe?g|png|webp|gif)(?:\?\S*)?$", re.I)
_WIDTH_KEYS = ("width", "w", "originalWidth", "imageWidth")
_HEIGHT_KEYS = ("height", "h", "originalHeight", "imageHeight")
_URL_KEYS = ("url", "src", "href", "imageUrl", "photoUrl", "large", "original", "fullUrl", "highRes")


def parse_embedded_json_blocks(soup: BeautifulSoup) -> List[Any]:
    """All `<script type="application/json">` blocks, parsed. Malformed
    blocks are skipped, never raise."""
    blocks: List[Any] = []
    for tag in soup.find_all("script", type="application/json"):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
    return blocks


def _first_int(d: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[int]:
    for key in keys:
        val = d.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0:
            return int(val)
    return None


def embedded_json_images(blocks: List[Any]) -> List[Tuple[str, Optional[int], Optional[int]]]:
    """Recursively walks embedded JSON for image URLs — generic across
    sites, no assumption about a specific schema/key path (that varies per
    site and changes over time). A URL is only kept if it matches a real
    image file extension, not any arbitrary JSON string. When an object
    describing one image also carries width/height alongside its URL (a
    common shape: {"url": "...", "width": 2048, "height": 1536}), that real,
    declared size is captured — never inferred or guessed. Returns
    (url, width_or_None, height_or_None), deduped by URL, keeping the
    largest declared width seen for a given URL."""
    found: Dict[str, Tuple[Optional[int], Optional[int]]] = {}

    def consider(url: str, width: Optional[int], height: Optional[int]) -> None:
        existing = found.get(url)
        if existing is None or (width or 0) > (existing[0] or 0):
            found[url] = (width, height)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in _URL_KEYS:
                val = node.get(key)
                if isinstance(val, str) and _IMAGE_URL_RE.match(val.strip()):
                    consider(val.strip(), _first_int(node, _WIDTH_KEYS), _first_int(node, _HEIGHT_KEYS))
                    break
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            candidate = node.strip()
            if _IMAGE_URL_RE.match(candidate) and candidate not in found:
                found[candidate] = (None, None)

    for block in blocks:
        walk(block)
    return [(url, w, h) for url, (w, h) in found.items()]
