"""Property-scoped media: gallery-boundary detection + per-media
property-match scoring + same-image/different-resolution merging.

This is the answer to "a beautiful farmhouse image is useless if it belongs
to another farmhouse." Every media candidate gets scored against the target
`PropertyIdentity`; only strong/medium evidence should let a candidate
survive — see `PROPERTY_MATCH_THRESHOLD`.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from app.models.media import MediaAsset
from app.models.property import PropertyIdentity, SamePropertyMatch
from app.ranking.relevance import text_similarity

# Below this score, media is excluded from the property-scoped set entirely
# — a hard gate, not just a ranking penalty (see researcher.py).
PROPERTY_MATCH_THRESHOLD = 0.35

_EXCLUDE_CONTAINER_RE = re.compile(
    r"(similar|recommended|related[-_]?listings?|nearby|also[-_]?like|"
    r"you[-_]?may|footer|header|\bnav\b|sidebar|agent[-_]?profile|"
    r"agent[-_]?card|broker[-_]?profile|neighborhood|more[-_]?homes)", re.I,
)
_GALLERY_CONTAINER_RE = re.compile(
    r"(gallery|photos?|images?|carousel|slider|media[-_]?viewer|"
    r"lightbox|slideshow|swiper)", re.I,
)
_AGENT_HEADSHOT_RE = re.compile(
    r"(agent|broker|realtor)[\w\s.,'-]{0,40}(headshot|photo|profile|portrait|picture)"
    r"|(headshot|photo|profile|portrait|picture)[\w\s.,'-]{0,40}(agent|broker|realtor)",
    re.I,
)
_SIMILAR_HOMES_RE = re.compile(r"(similar\s+home|recommended\s+propert|you\s+may\s+also\s+like|nearby\s+listing)", re.I)
_LOGO_TEXT_RE = re.compile(r"\blogo\b", re.I)

# CDN size-variant path segments — stripping these collapses "the same
# photo at different crop sizes" (observed on real listing CDNs, e.g.
# `/w440xh330xcrop/.../x.jpg` and `/w1920xh1440/.../x.jpg` being the exact
# same underlying image) to one comparison key.
_SIZE_TOKEN_RE = re.compile(r"/(w\d+xh\d+(?:xcrop)?|big|large|small|medium|thumbs?|thumbnails?|\d{2,4}x\d{2,4})/", re.I)

# Zillow encodes the size transform in the FILENAME, not a path segment:
#     /fp/<photo_hash>-<transform>.jpg
# e.g. <hash>-p_c.jpg (316x234) and <hash>-cc_ft_960.jpg are the same photo.
# The path-segment regex above cannot see that, so every derivative became
# its own "photo". The hash is the stable per-photo identity.
_ZILLOW_PHOTO_RE = re.compile(
    r"^(?P<prefix>https?://[^/]*zillowstatic\.com/.*?/)"
    r"(?P<hash>[0-9a-f]{16,64})-(?P<transform>[A-Za-z0-9_]+)"
    r"\.(?P<ext>jpg|jpeg|png|webp)(?P<query>\?.*)?$",
    re.I,
)


def zillow_photo_identity(url: str):
    """(photo_hash, transform, rebuild_fn) for a Zillow CDN photo URL, else
    None. `rebuild_fn(token)` returns the same photo at another transform.

    Deliberately narrow: only *.zillowstatic.com URLs matching the
    <hash>-<transform>.<ext> shape are recognised, so nothing else in the
    pipeline changes behaviour."""
    m = _ZILLOW_PHOTO_RE.match((url or "").strip())
    if not m:
        return None
    prefix, photo_hash, transform, ext = (
        m.group("prefix"), m.group("hash"), m.group("transform"), m.group("ext"),
    )

    def rebuild(token: str) -> str:
        return f"{prefix}{photo_hash}-{token}.{ext}"

    return photo_hash, transform, rebuild


def analyze_gallery_context(soup, base_url: str) -> Dict[str, dict]:
    """Walks each <img>'s ancestor chain looking for gallery vs. excluded
    (similar-listings/agent/footer/...) container signals. Returns a dict
    keyed by absolute image URL."""
    context: Dict[str, dict] = {}
    if soup is None:
        return context

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            continue
        abs_url = urljoin(base_url, src.strip())

        excluded_reason: Optional[str] = None
        in_gallery = False
        node = img
        depth = 0
        while node is not None and depth < 8:
            classes = node.get("class") if hasattr(node, "get") else None
            node_id = node.get("id") if hasattr(node, "get") else None
            haystack = " ".join(filter(None, [
                " ".join(classes) if isinstance(classes, list) else (classes or ""),
                node_id or "",
            ])).lower()
            if haystack:
                if excluded_reason is None:
                    m = _EXCLUDE_CONTAINER_RE.search(haystack)
                    if m:
                        excluded_reason = m.group(0)
                if _GALLERY_CONTAINER_RE.search(haystack):
                    in_gallery = True
            node = getattr(node, "parent", None)
            depth += 1

        context[abs_url] = {"in_gallery": in_gallery, "excluded": excluded_reason}

    return context


def score_media_property_match(
    asset: MediaAsset,
    target: PropertyIdentity,
    page_match: SamePropertyMatch,
    gallery_context: Optional[Dict[str, dict]] = None,
) -> Tuple[float, List[str]]:
    """Score how likely `asset` depicts the target property specifically
    (not just "came from a page that matched"). Returns (score, reasons)."""
    if not page_match.is_match:
        return 0.0, ["page did not match target property"]

    # "Image appears inside the property's listing page" is *strong*
    # evidence per spec, not a weak baseline — once a page has been
    # confirmed as the target property, media on it should generally pass
    # the gate on that alone, with exclusion signals (similar-listings/
    # agent/footer containers, headshots, logos) as the thing that pulls a
    # candidate back out. Real-world validation against a live listing page
    # with a non-standard gallery container naming convention showed a 0.3
    # baseline wrongly filtering out genuine, unambiguous property photos
    # (IMG_2703.jpg etc.) that simply weren't inside a container matching
    # our gallery-class heuristics.
    reasons: List[str] = [f"page-level property match ({page_match.match_score:.2f})"]
    score = 0.5 * page_match.match_score

    ctx = (gallery_context or {}).get(asset.source_url)
    haystack = " ".join(filter(None, [asset.alt, asset.caption, asset.title])).lower()

    # --- strong evidence ---
    if asset.provider == "json_ld":
        score += 0.35
        reasons.append("referenced in listing JSON-LD image array")
    if asset.provider == "og_image":
        score += 0.25
        reasons.append("page OpenGraph image")
    if asset.provider == "schema_video_object":
        score += 0.35
        reasons.append("referenced as listing JSON-LD VideoObject")

    all_ids = [i for i in (target.listing_ids + target.mls_ids) if i]
    if any(lid in asset.source_url for lid in all_ids):
        score += 0.3
        reasons.append("media URL contains listing/MLS ID")

    if ctx and ctx.get("in_gallery"):
        score += 0.25
        reasons.append("inside a property gallery container")

    # --- medium evidence ---
    if target.property_name and haystack:
        name_sim = text_similarity(target.property_name, haystack)
        if name_sim >= 0.3:
            score += 0.15
            reasons.append(f"alt/caption relates to property name (similarity={name_sim:.2f})")
    if target.street_number and target.street_number in haystack:
        score += 0.15
        reasons.append("alt/caption contains street number")
    if target.city and target.city.lower() in haystack:
        score += 0.1
        reasons.append("alt/caption mentions city")

    # --- strong negative evidence ---
    if ctx and ctx.get("excluded"):
        score -= 0.6
        reasons.append(f"inside an excluded container ('{ctx['excluded']}')")
    if _AGENT_HEADSHOT_RE.search(haystack) or _AGENT_HEADSHOT_RE.search(asset.source_url):
        score -= 0.5
        reasons.append("looks like an agent/broker headshot")
    if _SIMILAR_HOMES_RE.search(haystack):
        score -= 0.5
        reasons.append("looks like a similar/recommended listing")
    if _LOGO_TEXT_RE.search(haystack):
        score -= 0.5
        reasons.append("looks like a logo")

    score = round(max(0.0, min(score, 1.0)), 4)
    return score, reasons


def classify_rejection_reason(asset: MediaAsset) -> Optional[str]:
    """Maps a scored-but-gated-out media candidate to one of a small set of
    canonical rejection reasons, for acceptance-test reporting. Returns None
    if the asset actually passed the gate (not a rejection)."""
    if asset.property_match_score >= PROPERTY_MATCH_THRESHOLD:
        return None
    reasons = " | ".join(asset.property_match_reasons)
    if "did not match target property" in reasons:
        return "unrelated_property"
    if "logo" in reasons:
        return "site_logo"
    if "headshot" in reasons:
        return "agent_headshot"
    if "similar/recommended listing" in reasons:
        return "similar_property"
    if "excluded container" in reasons:
        return "excluded_container"
    return "low_property_match"


def apply_property_scope(
    assets: List[MediaAsset],
    target: PropertyIdentity,
    page_match: SamePropertyMatch,
    gallery_context: Optional[Dict[str, dict]] = None,
) -> List[MediaAsset]:
    """Mutates and returns `assets` with `property_match_score`/
    `property_match_reasons` set. Does not filter — the hard-gate cutoff
    (`PROPERTY_MATCH_THRESHOLD`) is applied by the caller so it can log what
    was rejected."""
    for asset in assets:
        score, reasons = score_media_property_match(asset, target, page_match, gallery_context)
        asset.property_match_score = score
        asset.property_match_reasons = reasons
    return assets


def _size_normalized_key(url: str) -> str:
    """Strips CDN size-variant path segments so the same underlying photo
    at different crop/resolution sizes collapses to one comparison key.

    Zillow is handled first because it encodes the transform in the
    filename rather than a path segment — without this, <hash>-p_c.jpg and
    <hash>-cc_ft_960.jpg (the same photo) were treated as two photos."""
    identity = zillow_photo_identity(url)
    if identity is not None:
        photo_hash, _transform, _rebuild = identity
        return f"zillow:{photo_hash}"
    return _SIZE_TOKEN_RE.sub("/", url).split("?")[0]


def _estimated_size_rank(asset: MediaAsset) -> tuple:
    """Size confidence, most trustworthy first. The leading element is the
    EVIDENCE class, so a weaker class can never outrank a stronger one no
    matter how large the number it claims:

        3 = measured pixels (probed the actual bytes)
        2 = declared metadata (srcset `w`, embedded-JSON width, <img width>)
        1 = parsed out of the URL/filename
        0 = nothing but a size-ish word in the URL

    URL/filename numbers are the least trustworthy signal there is — a
    `.../w1920xh1080/x.jpg` path routinely serves something far smaller —
    so they only ever break ties among candidates with no better evidence.
    """
    if asset.actual_width and asset.actual_height:
        return (3, asset.actual_width * asset.actual_height)
    if asset.declared_width and asset.declared_height:
        return (2, asset.declared_width * asset.declared_height)
    if asset.width and asset.height:
        return (2, asset.width * asset.height)
    url = asset.source_url
    m = re.search(r"w(\d+)xh(\d+)", url, re.I)
    if m:
        return (1, int(m.group(1)) * int(m.group(2)))
    if re.search(r"\bbig\b|\blarge\b", url, re.I):
        return (0, 10**9)
    if re.search(r"\bsmall\b|\bthumb", url, re.I):
        return (0, 1)
    return (0, 0)


def merge_same_image_size_variants(
    assets: List[MediaAsset], source_priority: Optional[Dict[str, float]] = None,
) -> List[MediaAsset]:
    """Collapses same-photo-different-CDN-size candidates into one, keeping
    the highest-resolution variant (never a tiny thumbnail when a full-size
    version is discoverable — see V3 download-policy requirement) and
    recording the others as `alternate_sources` for provenance."""
    source_priority = source_priority or {}
    groups: Dict[str, List[MediaAsset]] = {}
    for asset in assets:
        groups.setdefault(_size_normalized_key(asset.source_url), []).append(asset)

    merged: List[MediaAsset] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue

        def rank(a: MediaAsset):
            return (_estimated_size_rank(a), source_priority.get(a.source_id or "", 0.0))

        best = max(group, key=rank)
        for other in group:
            if other is best:
                continue
            best.alternate_sources.append({
                "source_id": other.source_id, "source_url": other.source_url,
                "source_page": other.source_page,
            })
        merged.append(best)
    return merged
