"""RealtyAPI photo supplement — additive-only property image candidates.

Optional, non-critical: this module contributes MORE MediaAsset candidates
to the existing acquisition pipeline (property_researcher.py inserts them
into `all_media` before Zillow-derivative-upgrade/probing/variant-election),
it never removes or replaces anything the existing scraper already found.
Every genuine safety property downstream (probing, grouping, dedup,
download) is untouched and applies to these candidates exactly as it does
to scraped ones.

Failure handling: ANY problem (no key configured, HTTP error, timeout,
malformed response, missing/malformed photo data) returns an empty list.
Never raises, never logs the API key, never invents a URL or a resolution
that wasn't literally present in the response.

Request shape verified 2026-09 against RealtyAPI's own published OpenAPI 3.1
spec (https://zillow.realtyapi.io/openapi.json): GET /pro/byurl on the
zillow.realtyapi.io subdomain, a single required `url` query parameter (a
Zillow listing URL containing a zpid — NOT an address, and NOT an apartment
listing URL containing "/b/" or "/apartment/", which the spec says needs a
different endpoint this module does not implement), authenticated via the
`x-realtyapi-key` header. The spec's response schema for a 200 was empty
(not published there), so the RESPONSE shape parsed here
(`originalPhotos[].mixedSources.jpeg[]`) remains exactly as given/specified
and is NOT independently verified against a documented response schema.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.models.media import MediaAsset, MediaType

REALTYAPI_BASE_URL = "https://zillow.realtyapi.io"
REALTYAPI_PROPERTY_ENDPOINT = "/pro/byurl"

_TIMEOUT_SECONDS = 15.0


def _new_media_id() -> str:
    return f"realtyapi_{uuid4().hex[:12]}"


def _select_largest_jpeg(mixed_sources: Any) -> Optional[Dict[str, Any]]:
    """The largest genuinely-present JPEG variant for one photo entry, or
    None. Only ever picks among (url, width) pairs literally present in the
    response — never invents a URL, never invents a width, never upscales."""
    if not isinstance(mixed_sources, dict):
        return None
    jpeg_list = mixed_sources.get("jpeg")
    if not isinstance(jpeg_list, list):
        return None

    best_url: Optional[str] = None
    best_width: Optional[int] = None
    have_measured = False
    for entry in jpeg_list:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        width = entry.get("width")
        try:
            width_val: Optional[int] = int(width)
        except (TypeError, ValueError):
            width_val = None

        if width_val is not None:
            # A variant with a real, larger width always wins — mirrors the
            # "measured beats declared beats unknown" convention the rest
            # of the pipeline (app/media/variants.py::_election_rank) uses.
            if not have_measured or width_val > (best_width or 0):
                best_url, best_width, have_measured = url.strip(), width_val, True
        elif best_url is None:
            # No width-carrying entry seen yet — an unknown-width entry is
            # still a genuine, present URL, so it's kept as a fallback
            # rather than discarding the photo entirely.
            best_url, best_width = url.strip(), None

    if best_url is None:
        return None
    return {"url": best_url, "width": best_width}


def _photos_to_media_assets(photos: Any, *, source_page: str, source_id: str) -> List[MediaAsset]:
    """originalPhotos[] -> MediaAsset list, preserving original order. Any
    malformed entry is skipped rather than raising or guessing."""
    out: List[MediaAsset] = []
    if not isinstance(photos, list):
        return out
    for position, photo in enumerate(photos):
        if not isinstance(photo, dict):
            continue
        chosen = _select_largest_jpeg(photo.get("mixedSources"))
        if chosen is None:
            continue
        out.append(MediaAsset(
            media_id=_new_media_id(),
            media_type=MediaType.IMAGE,
            source_url=chosen["url"],
            source_page=source_page,
            source_id=source_id,
            provider="realtyapi",
            page_position=position,
            declared_width=chosen["width"],
            width=chosen["width"],
            # Fetched by explicit lookup for THIS property (not page-scored
            # like scraped media) — treated as a confirmed match, same as a
            # scraped page whose URL == target_url (see property_researcher.
            # py's is_match=True / match_score=1.0 for that exact case).
            property_match_score=1.0,
        ))
    return out


async def fetch_realtyapi_photos(
    *,
    listing_url: str = "",
    address: str = "",
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[MediaAsset]:
    """Returns RealtyAPI photo candidates for one property, or [] on any
    failure. Makes a network request ONLY when REALTYAPI_API_KEY is set in
    the environment AND listing_url is given — /pro/byurl (the only
    documented endpoint this module calls) accepts a Zillow listing URL
    only, not an address; `address` is accepted for call-site compatibility
    but is not currently usable against this endpoint and is ignored."""
    api_key = os.environ.get("REALTYAPI_API_KEY", "").strip()
    if not api_key:
        return []
    listing_url = (listing_url or "").strip()
    address = (address or "").strip()
    if not listing_url:
        return []

    params: Dict[str, str] = {"url": listing_url}

    own_client = http_client is None
    client = http_client or httpx.AsyncClient()
    try:
        response = await client.get(
            f"{REALTYAPI_BASE_URL}{REALTYAPI_PROPERTY_ENDPOINT}",
            params=params,
            headers={"x-realtyapi-key": api_key},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError:
        # Covers connection errors and timeouts alike — RealtyAPI is
        # optional/non-critical, so any transport failure just yields no
        # candidates rather than propagating.
        return []
    except Exception:  # noqa: BLE001 - never fatal to research
        return []
    finally:
        if own_client:
            await client.aclose()

    if response.status_code != 200:
        # 401/403/404/429/500+ all treated identically: no candidates,
        # never raises. The response body/status is not logged here, so the
        # api_key (sent only as a request header, never in the URL/body)
        # can never end up in a log line via this function.
        return []
    try:
        data = response.json()
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []

    source_page = listing_url or address
    return _photos_to_media_assets(
        data.get("originalPhotos"), source_page=source_page, source_id="realtyapi",
    )
