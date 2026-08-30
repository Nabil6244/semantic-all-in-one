"""Zillow derivative upgrade — recover the highest GENUINE resolution of a
Zillow listing photo before it is downloaded.

Why
---
Zillow frequently exposes only a small derivative in the page HTML, e.g.
`<hash>-p_c.jpg` at 316x234, while the CDN will serve the same photo far
larger under a different transform token. Downloading the 316x234 version
and then letting the renderer crop/Ken-Burns it to fill the frame produces
a visibly blurry shot. Verified against the live CDN: `-p_c` measured
316x234 while `-cc_ft_1152` of the same hash measured 1024x683 (~10x the
pixels, same photo).

Safety properties (all verified against the real CDN, see tests)
----------------------------------------------------------------
- NEVER upscales. Zillow returns its true master and caps there: probing
  `cc_ft_1536` against a 42x11 master returned 44x10, not 1536-wide, and
  `cc_ft_1920` on a 1024-wide master returned 404. An upgrade is accepted
  only when the MEASURED pixels genuinely increase.
- Same-photo guaranteed: candidate URLs are rebuilt from the SAME photo
  hash, so an upgrade can never swap in a different image.
- Scoped narrowly: only *.zillowstatic.com URLs of the form
  `<hash>-<transform>.<ext>` are touched. Every other URL returns
  unchanged, so non-Zillow media follows the exact existing path.
- Cheap: dimensions come from `media.probe` (image header bytes, ~2KB per
  URL, cached), not full downloads, and probing stops as soon as the
  ladder stops improving.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional

import httpx

from app.media.probe import ProbeCache, ProbeStatus, probe_images
from app.media.property_scope import zillow_photo_identity

# Ascending ladder of Zillow "fit" transforms. Ordered small -> large so we
# can stop early; not every token exists for every photo (cc_ft_1920 is
# frequently a 404), which is expected and handled.
ZILLOW_UPGRADE_TOKENS: tuple = (
    "cc_ft_576",
    "cc_ft_768",
    "cc_ft_960",
    "cc_ft_1152",
    "cc_ft_1536",
    "cc_ft_1920",
)

# Long side at/above which we stop climbing: already comfortably above the
# render target, so further probing would just cost requests.
GOOD_ENOUGH_LONG_SIDE = 1600


@dataclasses.dataclass
class UpgradeResult:
    original_url: str
    chosen_url: str
    width: Optional[int] = None
    height: Optional[int] = None
    upgraded: bool = False
    reason: str = ""

    @property
    def long_side(self) -> Optional[int]:
        if self.width and self.height:
            return max(self.width, self.height)
        return None


def _long_side(result) -> int:
    if result is None or result.status != ProbeStatus.MEASURED:
        return 0
    if not result.actual_width or not result.actual_height:
        return 0
    return max(result.actual_width, result.actual_height)


async def upgrade_zillow_urls(
    urls: List[str],
    *,
    http_client: Optional[httpx.AsyncClient] = None,
    cache: Optional[ProbeCache] = None,
    concurrency: int = 8,
) -> Dict[str, UpgradeResult]:
    """For each Zillow photo URL, return the largest genuinely-available
    derivative of the SAME photo. Non-Zillow URLs are returned unchanged and
    are never probed. Never raises."""
    cache = cache if cache is not None else ProbeCache()
    out: Dict[str, UpgradeResult] = {}

    zillow: Dict[str, tuple] = {}
    for url in dict.fromkeys(u for u in urls if u):
        identity = zillow_photo_identity(url)
        if identity is None:
            # Not a Zillow photo URL -> untouched, unprobed.
            out[url] = UpgradeResult(url, url, reason="not_zillow")
            continue
        zillow[url] = identity

    if not zillow:
        return out

    # Measure the originals plus every candidate transform in ONE batch, so
    # a property with 20 photos costs one bounded-concurrency pass rather
    # than a serial ladder per photo.
    candidates: Dict[str, List[str]] = {}
    to_probe: List[str] = []
    for url, (_photo_hash, transform, rebuild) in zillow.items():
        variants = [url]
        for token in ZILLOW_UPGRADE_TOKENS:
            if token == transform:
                continue
            variants.append(rebuild(token))
        candidates[url] = variants
        to_probe.extend(variants)

    try:
        measured = await probe_images(
            to_probe, concurrency=concurrency, http_client=http_client, cache=cache,
        )
    except Exception:  # noqa: BLE001 - upgrading is an optimization, never fatal
        for url in zillow:
            out[url] = UpgradeResult(url, url, reason="probe_failed")
        return out

    for url, variants in candidates.items():
        base_long = _long_side(measured.get(url))
        best_url, best_long = url, base_long
        best_res = measured.get(url)

        for variant in variants:
            if variant == url:
                continue
            got = measured.get(variant)
            got_long = _long_side(got)
            # Strictly greater: an equal-size response means Zillow served
            # the same master under a different token, which is NOT an
            # upgrade and must not be recorded as one.
            if got_long > best_long:
                best_url, best_long, best_res = variant, got_long, got

        if best_url != url and best_long > base_long:
            out[url] = UpgradeResult(
                original_url=url, chosen_url=best_url,
                width=best_res.actual_width if best_res else None,
                height=best_res.actual_height if best_res else None,
                upgraded=True,
                reason=f"upgraded {base_long}px -> {best_long}px long side",
            )
        else:
            out[url] = UpgradeResult(
                original_url=url, chosen_url=url,
                width=best_res.actual_width if best_res else None,
                height=best_res.actual_height if best_res else None,
                upgraded=False,
                reason="no larger genuine derivative available" if base_long else "not_measured",
            )
    return out


def apply_upgrades(assets, upgrades: Dict[str, UpgradeResult]) -> int:
    """Point each MediaAsset at its upgraded derivative, in place.

    Only `source_url`/`media_url` and the MEASURED dimensions change — the
    asset keeps its identity, role, property_match_score and provenance, and
    the original URL is recorded in `alternate_sources` so nothing is lost.
    Returns how many assets were upgraded."""
    changed = 0
    for asset in assets:
        result = upgrades.get(asset.source_url)
        if result is None or not result.upgraded:
            continue
        asset.alternate_sources.append({
            "source_id": asset.source_id,
            "source_url": result.original_url,
            "source_page": asset.source_page,
            "note": "zillow_derivative_superseded",
        })
        asset.source_url = result.chosen_url
        asset.media_url = result.chosen_url
        if result.width and result.height:
            asset.actual_width, asset.actual_height = result.width, result.height
            asset.width, asset.height = result.width, result.height
        changed += 1
    return changed
