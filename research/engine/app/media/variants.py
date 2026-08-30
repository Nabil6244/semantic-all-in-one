"""Image variant grouping: collapse several URLs that are renditions of ONE
underlying photo, and elect the genuinely largest one.

The problem this solves
-----------------------
A listing page exposes the same photo at several sizes:

    .../fp/abc123-cc_ft_384.jpg
    .../fp/abc123-cc_ft_960.jpg
    .../fp/abc123-cc_ft_1536.jpg

Left ungrouped these compete as four separate "photos" for a bounded media
budget, and — since none of them carries a trustworthy declared size — the
one that wins is arbitrary, frequently the smallest (srcset lists ascending,
so the smallest is simply seen first). That is the mechanism behind a hero
image looking sharp while the gallery looks soft.

Two rules keep grouping honest:

1. Only tokens that are unambiguously SIZE markers are stripped, and only
   when the numbers involved are plausible pixel dimensions. Grouping is
   never allowed to be clever — a false merge silently deletes a real photo,
   which is far worse than failing to merge.

2. Measured dimensions VETO a bad merge. Genuine renditions of one photo
   differ in size; two files with identical measured dimensions are not
   size variants of each other, so they are split back apart. This is what
   stops `img_640.jpg` / `img_480.jpg`-style sequential names from being
   merged when they are actually different photographs.

No URL is ever rewritten or invented here. Every original URL is preserved:
the elected asset keeps its own, and the rest are recorded on it as
`alternate_sources` for provenance.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app.media.site_adapters import adapter_variant_key
from app.models.media import MediaAsset

_MIN_PLAUSIBLE_DIM = 100
_MAX_PLAUSIBLE_DIM = 10000

# Size markers appearing as a whole PATH SEGMENT, e.g. /w440xh330xcrop/,
# /large/, /thumbs/. These are unambiguous.
_PATH_SIZE_RE = re.compile(
    r"/(?:w\d+xh\d+(?:xcrop)?|\d{2,4}x\d{2,4}|"
    r"big|large|small|medium|thumb|thumbs|thumbnail|thumbnails|orig|original)/",
    re.I,
)

# Size markers appearing as a FILENAME SUFFIX, immediately before the
# extension. Ordered most-specific first. Each pattern's numeric groups are
# validated as plausible dimensions before the token is stripped, so a
# sequence number like `-1` or `_002` is never mistaken for a size.
_SUFFIX_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"(?P<tok>-uncropped_scaled_within_(?P<a>\d{2,5})_(?P<b>\d{2,5}))$", re.I),
    re.compile(r"(?P<tok>-cc_ft_(?P<a>\d{2,5}))$", re.I),
    re.compile(r"(?P<tok>[-_](?P<a>\d{3,5})x(?P<b>\d{3,5}))$", re.I),
    re.compile(r"(?P<tok>[-_](?P<a>\d{3,5})w)$", re.I),
    re.compile(r"(?P<tok>[-_]w(?P<a>\d{3,5}))$", re.I),
    re.compile(r"(?P<tok>[-_](?P<a>\d{3,5}))$", re.I),
)


def _plausible(*values: Optional[str]) -> bool:
    for raw in values:
        if raw is None:
            continue
        try:
            num = int(raw)
        except (TypeError, ValueError):
            return False
        if not (_MIN_PLAUSIBLE_DIM <= num <= _MAX_PLAUSIBLE_DIM):
            return False
    return True


def strip_size_tokens(url: str) -> str:
    """The URL with recognized size markers removed. Query strings and
    fragments are dropped; the path identity is what matters."""
    if not url:
        return url
    base = url.split("#", 1)[0].split("?", 1)[0]
    base = _PATH_SIZE_RE.sub("/", base)

    head, dot, ext = base.rpartition(".")
    if not dot or len(ext) > 5 or "/" in ext:
        head, ext = base, ""

    for pattern in _SUFFIX_PATTERNS:
        match = pattern.search(head)
        if not match:
            continue
        groups = match.groupdict()
        if not _plausible(groups.get("a"), groups.get("b")):
            continue
        stripped = head[: match.start("tok")]
        # Refuse to strip down to nothing meaningful — without a residual
        # identity the "group" would swallow unrelated images.
        if len(stripped.rsplit("/", 1)[-1]) < 3:
            continue
        head = stripped
        break

    return f"{head}.{ext}" if ext else head


def variant_key(url: str) -> str:
    """Grouping key for `url`. A site adapter gets first refusal — it can
    recognize rendition schemes (renderer prefixes, profile suffixes) that
    no generic rule could infer without guessing. When no adapter matches,
    or it declines, generic size-token stripping applies."""
    site_key = adapter_variant_key(url)
    if site_key:
        return site_key
    return strip_size_tokens(url)


def _measured(asset: MediaAsset) -> Optional[Tuple[int, int]]:
    if asset.actual_width and asset.actual_height:
        return int(asset.actual_width), int(asset.actual_height)
    return None


def _election_rank(asset: MediaAsset, source_priority: Dict[str, float]) -> tuple:
    """Highest MEASURED pixel count wins. Declared numbers only ever break
    ties among assets that could not be measured, and are ranked in a
    strictly lower band so a measured image always beats an unmeasured
    claim — a URL saying `2048` must never outrank a file measured at
    1536."""
    measured = _measured(asset)
    if measured is not None:
        return (2, measured[0] * measured[1], source_priority.get(asset.source_id or "", 0.0))
    if asset.declared_width and asset.declared_height:
        return (1, int(asset.declared_width) * int(asset.declared_height),
                source_priority.get(asset.source_id or "", 0.0))
    if asset.declared_width:
        return (1, int(asset.declared_width), source_priority.get(asset.source_id or "", 0.0))
    return (0, 0, source_priority.get(asset.source_id or "", 0.0))


def _split_identical_sizes(group: List[MediaAsset]) -> List[List[MediaAsset]]:
    """Veto rule: assets in a group with IDENTICAL measured dimensions are
    not renditions of each other, so they become their own groups. Assets
    with no measurement stay with the main group (we have no evidence to
    separate them, and the URL evidence said they belong together)."""
    if len(group) < 2:
        return [group]

    primary: List[MediaAsset] = []
    seen_sizes: Dict[Tuple[int, int], MediaAsset] = {}
    split_off: List[List[MediaAsset]] = []

    for asset in group:
        size = _measured(asset)
        if size is None:
            primary.append(asset)
            continue
        existing = seen_sizes.get(size)
        if existing is None:
            seen_sizes[size] = asset
            primary.append(asset)
        else:
            split_off.append([asset])

    return [primary] + split_off if primary else split_off


def group_variants(
    assets: List[MediaAsset], source_priority: Optional[Dict[str, float]] = None,
) -> List[MediaAsset]:
    """Collapse size variants, keeping the largest MEASURED rendition of each
    photo and recording the others as `alternate_sources`.

    Stamps `variant_group` on every returned asset so the grouping decision
    is auditable in the output package rather than invisible."""
    source_priority = source_priority or {}
    buckets: Dict[str, List[MediaAsset]] = {}
    order: List[str] = []
    for asset in assets:
        key = variant_key(asset.source_url)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(asset)

    elected: List[MediaAsset] = []
    for key in order:
        # Exact same URL is definitively the same image (it may simply have
        # been discovered on several pages, or by several layers). Collapse
        # those FIRST — otherwise the identical-size veto below would see
        # matching dimensions and wrongly split them back apart.
        deduped: List[MediaAsset] = []
        by_url: Dict[str, MediaAsset] = {}
        for asset in buckets[key]:
            existing = by_url.get(asset.source_url)
            if existing is None:
                by_url[asset.source_url] = asset
                deduped.append(asset)
            else:
                existing.alternate_sources.append({
                    "source_id": asset.source_id,
                    "source_url": asset.source_url,
                    "source_page": asset.source_page,
                    "provider": asset.provider,
                    "note": "same_url_other_source",
                })

        for subgroup in _split_identical_sizes(deduped):
            if not subgroup:
                continue
            best = max(subgroup, key=lambda a: _election_rank(a, source_priority))
            best.variant_group = key
            for other in subgroup:
                if other is best:
                    continue
                best.alternate_sources.append({
                    "source_id": other.source_id,
                    "source_url": other.source_url,
                    "source_page": other.source_page,
                    "declared_width": other.declared_width,
                    "actual_width": other.actual_width,
                    "provider": other.provider,
                })
            elected.append(best)
    return elected
