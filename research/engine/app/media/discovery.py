"""Media discovery: find candidate images/videos on an already-fetched page.

Discovery only builds candidate `MediaAsset` records (no downloading here).
Ranking happens afterwards, then only the selected subset is downloaded —
see media/downloader.py.
"""
from __future__ import annotations

import mimetypes
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from app.extraction.structured_data import (
    embedded_json_images,
    jsonld_images,
    jsonld_video_objects,
    opengraph_images,
    opengraph_videos,
    parse_embedded_json_blocks,
)
from app.extraction.flight_data import flight_data_blocks
from app.extraction.script_state import script_state_blocks
from app.extraction.webpage import PageExtraction
from app.models.media import MediaAsset, MediaType

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}
_VIMEO_HOSTS = {"vimeo.com", "player.vimeo.com", "www.vimeo.com"}

# Filenames/URL fragments that are near-certainly UI chrome, not content —
# excluded even if dimensions look plausible (an SVG sprite sheet can be big).
# `\blogo\b` deliberately targets "logo" as an isolated path/filename
# segment (site-logo.png, social-logo.jpg, mop-logo-header.png) rather than
# any substring match, so it won't misfire on unrelated words. Confirmed
# against real listing pages (see README real-world validation notes) where
# site/social-share logos were otherwise being discovered as media
# candidates — exactly the "logos when irrelevant" case the spec calls out.
_SKIP_IMAGE_PATTERNS = re.compile(
    r"(1x1|pixel\.(gif|png)|spacer|space\.(gif|png)|blank\.(gif|png)|tracking|doubleclick|favicon|"
    r"placeholder|no[-_]?image|default[-_]?avatar|sprite|\blogo\b)", re.I,
)
_MIN_DIM = 80  # px; below this an <img> is almost certainly chrome/UI, not content


def _abs_url(base: str, url: str) -> str:
    if not url:
        return url
    url = url.strip()
    if url.startswith("data:"):
        return url
    return urljoin(base, url)


def _new_media_id() -> str:
    return f"media_{uuid4().hex[:12]}"


def _guess_mime(url: str) -> Optional[str]:
    guessed, _ = mimetypes.guess_type(url.split("?")[0])
    return guessed


_SRCSET_ENTRY_RE = re.compile(r"(\S+)(?:\s+(\d+(?:\.\d+)?)([wx]))?", re.I)


def _parse_srcset(srcset: str) -> List[tuple]:
    """Standard `srcset` syntax (https://html.spec.whatwg.org/#srcset-attributes):
    comma-separated "url [Nw | Nx]" entries. Returns [(url, width_px_or_None), ...].
    A bare pixel-density descriptor ("2x") carries no absolute width we can
    trust, so it's returned with width=None rather than guessing one — the
    existing ranking/merge logic already handles unknown-width candidates
    without needing every entry to have a number."""
    out: List[tuple] = []
    if not srcset:
        return out
    for raw in srcset.split(","):
        raw = raw.strip()
        if not raw:
            continue
        m = _SRCSET_ENTRY_RE.match(raw)
        if not m:
            continue
        url = m.group(1)
        descriptor_value, descriptor_unit = m.group(2), m.group(3)
        width = int(float(descriptor_value)) if (descriptor_value and descriptor_unit and descriptor_unit.lower() == "w") else None
        out.append((url, width))
    return out


def _find_caption(img_tag) -> Optional[str]:
    figure = img_tag.find_parent("figure")
    if figure is not None:
        figcaption = figure.find("figcaption")
        if figcaption is not None:
            text = figcaption.get_text(" ", strip=True)
            if text:
                return text
    sibling = img_tag.find_next_sibling(class_=re.compile(r"caption", re.I))
    if sibling is not None:
        text = sibling.get_text(" ", strip=True)
        if text:
            return text
    return None


class _PositionCounter:
    def __init__(self):
        self.value = -1

    def next(self) -> int:
        self.value += 1
        return self.value


def discover_images(page: PageExtraction, source_id: str) -> List[MediaAsset]:
    if not page.accessible:
        return []
    base = page.final_url
    candidates: dict[str, MediaAsset] = {}
    position = _PositionCounter()

    def add(url: str, provider: str, **kwargs):
        if not url or url.startswith("data:"):
            return
        abs_url = _abs_url(base, url)
        if abs_url in candidates:
            return
        if _SKIP_IMAGE_PATTERNS.search(abs_url):
            return
        candidates[abs_url] = MediaAsset(
            media_id=_new_media_id(),
            media_type=MediaType.IMAGE,
            source_url=abs_url,
            source_page=page.url,
            source_id=source_id,
            provider=provider,
            page_position=position.next(),
            mime_type=_guess_mime(abs_url),
            **kwargs,
        )

    for url in opengraph_images(page.opengraph):
        add(url, "og_image", title=page.title)

    for entity in page.json_ld:
        for url in jsonld_images(entity):
            add(url, "json_ld", title=page.title)

    if page.soup is not None:
        for img in page.soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if not src:
                continue
            width = _safe_int(img.get("width"))
            height = _safe_int(img.get("height"))
            if width is not None and width < _MIN_DIM and height is not None and height < _MIN_DIM:
                continue
            alt = img.get("alt") or None
            title = img.get("title") or None
            caption = _find_caption(img)
            add(
                src, "img_tag",
                alt=alt, title=title, caption=caption,
                width=width, height=height,
            )

            # The plain `src` above is frequently a low-resolution default
            # (a lazy-load placeholder or the smallest responsive variant) —
            # `srcset`/`data-srcset` carry the actual higher-resolution
            # sources per the HTML spec's srcset syntax. Every variant is
            # added as its own candidate (not just the widest) so the
            # existing merge_same_image_size_variants()/ranking pipeline
            # (app/media/property_scope.py) — which already prefers larger
            # width*height — has real higher-resolution options to choose
            # from, instead of only ever seeing the one low-res default.
            for attr in ("srcset", "data-srcset"):
                for variant_url, variant_width in _parse_srcset(img.get(attr) or ""):
                    add(
                        variant_url, "img_tag_srcset",
                        alt=alt, title=title, caption=caption,
                        width=variant_width, height=None,
                    )

        # <picture><source srcset="..."> — same responsive-image pattern as
        # <img srcset>, for pages using <picture> instead.
        for picture in page.soup.find_all("picture"):
            fallback_img = picture.find("img")
            p_alt = fallback_img.get("alt") if fallback_img is not None else None
            p_title = fallback_img.get("title") if fallback_img is not None else None
            for source_tag in picture.find_all("source"):
                for attr in ("srcset", "data-srcset"):
                    for variant_url, variant_width in _parse_srcset(source_tag.get(attr) or ""):
                        add(
                            variant_url, "img_tag_srcset",
                            alt=p_alt, title=p_title,
                            width=variant_width, height=None,
                        )

        # common gallery containers: data-full / data-src on anchors/divs
        for tag in page.soup.select("[data-full], [data-large], [data-zoom-image]"):
            for attr in ("data-full", "data-large", "data-zoom-image"):
                if tag.get(attr):
                    add(tag[attr], "gallery", alt=tag.get("alt") or tag.get("title"))

        # Embedded JSON (e.g. Next.js __NEXT_DATA__) — the actual
        # full-resolution originals for a gallery are frequently only present
        # here, never as a rendered <img>/srcset at all (a lightbox's images
        # that only mount into the DOM on click, for example). See
        # app/extraction/structured_data.py::embedded_json_images() for why
        # this is a generic walk, not a hardcoded schema for one site.
        for url, width, height in embedded_json_images(parse_embedded_json_blocks(page.soup)):
            add(url, "embedded_json", width=width, height=height)

        # Next.js / RSC "Flight" payloads. On App Router listing sites the
        # gallery is streamed here and assembled client-side — it is often
        # absent from the DOM, from srcset, and from any
        # <script type="application/json"> block, so without this layer only
        # the hero image is ever discovered. Each layer is independent: if
        # this one finds nothing (or the payload is malformed) the layers
        # above have already contributed their candidates.
        for url, width, height in embedded_json_images(flight_data_blocks(page.soup)):
            add(url, "flight_data", width=width, height=height)

        # Hydration state assigned in a plain <script>: window.__INITIAL_STATE__,
        # var PAGE_MODEL = {...}, JSON.parse("..."). Frequently not valid
        # JSON (unquoted keys, single quotes, trailing commas).
        for url, width, height in embedded_json_images(script_state_blocks(page.soup)):
            add(url, "script_state", width=width, height=height)

    return list(candidates.values())


def _safe_int(val) -> Optional[int]:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _embed_provider(url: str) -> Optional[str]:
    host = urlparse(url).netloc.lower()
    if host in _YOUTUBE_HOSTS or "youtube.com" in host or "youtu.be" in host:
        return "youtube_embed"
    if host in _VIMEO_HOSTS or "vimeo.com" in host:
        return "vimeo_embed"
    return None


def discover_videos(page: PageExtraction, source_id: str) -> List[MediaAsset]:
    if not page.accessible:
        return []
    base = page.final_url
    candidates: dict[str, MediaAsset] = {}
    position = _PositionCounter()
    page_thumbnail = next(iter(opengraph_images(page.opengraph)), None)

    def add(url: str, provider: str, **kwargs):
        if not url or url.startswith("data:"):
            return
        abs_url = _abs_url(base, url)
        if abs_url in candidates:
            return
        kwargs.setdefault("thumbnail", page_thumbnail)
        kwargs.setdefault("mime_type", _guess_mime(abs_url))
        candidates[abs_url] = MediaAsset(
            media_id=_new_media_id(),
            media_type=MediaType.VIDEO,
            source_url=abs_url,
            source_page=page.url,
            source_id=source_id,
            provider=provider,
            page_position=position.next(),
            **kwargs,
        )

    for url in opengraph_videos(page.opengraph):
        add(url, "og_video", title=page.title)

    for entity in jsonld_video_objects(page.json_ld):
        content_url = entity.get("contentUrl") or entity.get("embedUrl")
        if not content_url:
            continue
        duration = _parse_iso_duration(entity.get("duration"))
        add(
            content_url,
            "schema_video_object",
            title=entity.get("name"),
            description=entity.get("description"),
            duration_seconds=duration,
            thumbnail=entity.get("thumbnailUrl") or page_thumbnail,
        )

    if page.soup is not None:
        for video in page.soup.find_all("video"):
            poster = _abs_url(base, video.get("poster")) if video.get("poster") else page_thumbnail
            src = video.get("src") or video.get("data-src")
            if src:
                add(src, "video_tag", thumbnail=poster)
            for source in video.find_all("source"):
                source_src = source.get("src") or source.get("data-src")
                if source_src:
                    add(source_src, "video_tag", thumbnail=poster, mime_type=source.get("type"))

        for iframe in page.soup.find_all("iframe"):
            # Lazy-loaded embeds (loading="lazy") commonly ship the real
            # video URL in data-src rather than src until JS swaps it in —
            # found via real-world validation: a genuine Vimeo property-tour
            # embed (`data-src="https://player.vimeo.com/video/..."`) was
            # being missed entirely because only `src` was checked.
            src = iframe.get("src") or iframe.get("data-src") or ""
            provider = _embed_provider(src)
            if provider:
                add(src, provider, title=iframe.get("title"))

    return list(candidates.values())


def _parse_iso_duration(value) -> Optional[float]:
    """Parse a subset of ISO-8601 durations, e.g. PT1H2M3S. Returns seconds."""
    if not value or not isinstance(value, str):
        return None
    match = re.match(r"^P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", value)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    total = 0.0
    if hours:
        total += int(hours) * 3600
    if minutes:
        total += int(minutes) * 60
    if seconds:
        total += float(seconds)
    return total or None


def discover_media(page: PageExtraction, source_id: str) -> List[MediaAsset]:
    return discover_images(page, source_id) + discover_videos(page, source_id)
