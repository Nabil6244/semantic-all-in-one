"""Media asset models (images, videos) and license provenance."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class LicenseStatus(str, Enum):
    """We never assert reuse rights without evidence. Anything beyond
    `unknown` requires a concrete signal captured in `license_evidence`."""

    UNKNOWN = "unknown"
    OBSERVED_LICENSE = "observed_license"
    """A rel="license" link or similar was found but doesn't map to a known scheme."""
    CREATIVE_COMMONS = "creative_commons"
    PUBLIC_DOMAIN = "public_domain"
    RESTRICTED = "restricted"
    """Explicit copyright/all-rights-reserved evidence found — treat as NOT reusable."""


class MediaAsset(BaseModel):
    media_id: str
    media_type: MediaType
    source_url: str
    """Direct URL to the media file/embed."""
    source_page: str
    """The page the media was discovered on."""
    source_id: Optional[str] = None
    """Source (page) provenance id, links back to sources.json."""
    property_id: Optional[str] = None
    """Which researched listing this media belongs to. Stamped by the
    multi-property job layer (research/property_job.py) so every asset stays
    traceable to exactly one listing even if packages are later merged by a
    consumer. None for a single-property run that never went through the job
    layer — backward compatible."""
    source_type: Optional[str] = None
    """Denormalized copy of the owning Source's source_type, for convenience."""

    title: Optional[str] = None
    description: Optional[str] = None
    alt: Optional[str] = None
    caption: Optional[str] = None
    thumbnail: Optional[str] = None
    """Poster/thumbnail URL, when the page or structured data provides one."""
    page_position: Optional[int] = None
    """0-based order this media was encountered on the page — a coarse proxy
    for prominence (hero images tend to appear first)."""
    role: Optional[str] = None
    """Domain-adapter-assigned tag, e.g. hero/gallery/floor_plan/map/aerial/video.
    Deliberately kept coarse and backward compatible — see `role_detail`."""
    role_detail: Optional[str] = None
    """Finer role within the coarse `role`, when the adapter can tell:
    approach / exterior / interior / structure / construction_detail /
    water / waterfront / boundary_map / land / recreation. None when no
    confident signal was found — never guessed. Lets a consumer request a
    specific authentic shot instead of falling back to generic stock."""

    width: Optional[int] = None
    height: Optional[int] = None
    """Best currently-known dimensions: the measured values once this asset
    has been probed or downloaded, otherwise whatever the page declared.
    Kept as-is for backward compatibility with existing consumers — use
    `actual_*`/`declared_*` when the distinction matters."""
    declared_width: Optional[int] = None
    declared_height: Optional[int] = None
    """Dimensions the PAGE claimed (srcset `w` descriptor, embedded-JSON
    width/height, `<img width>`). Provenance only — never proof of
    resolution, and never used for ranking when a measurement exists."""
    actual_width: Optional[int] = None
    actual_height: Optional[int] = None
    """Dimensions MEASURED from the image's own header bytes
    (media/probe.py) or from the downloaded file. The only size signal
    ranking is allowed to trust."""
    probe_status: str = "not_probed"
    """See media.probe.ProbeStatus: measured | unsupported_format |
    fetch_failed | not_probed."""
    quality_tier: Optional[int] = None
    """1 (>=1600px long side) .. 4 (<960px), from MEASURED dimensions.
    None means "not measured" — deliberately distinct from tier 4."""
    variant_group: Optional[str] = None
    """Identity of the underlying photo this URL is one rendition of. All
    size variants of one photo share a group; the highest measured variant
    is elected and the rest become `alternate_sources`."""
    duration_seconds: Optional[float] = None
    mime_type: Optional[str] = None

    local_path: Optional[str] = None
    file_hash: Optional[str] = None
    perceptual_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None

    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    license_evidence: Optional[str] = None
    """The concrete evidence (URL/snippet) backing `license_status`, if any."""
    download_note: Optional[str] = None
    """Free-text note about the download attempt: duplicate_skipped,
    perceptual_duplicate_of:<id>, download_failed:<reason>, etc."""

    retrieved_at: Optional[datetime] = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    relevance_score: float = 0.0
    quality_score: float = 0.0
    property_match_score: float = 0.0
    """How likely this specific media depicts the *target property* (V3) —
    separate from `relevance_score`'s topical text match. A hard gate is
    applied at `media.property_scope.PROPERTY_MATCH_THRESHOLD` before this
    asset is even considered a candidate for the property-scoped package."""
    property_match_reasons: List[str] = Field(default_factory=list)
    script_relevance: Optional[float] = None
    """V4: bag-of-words similarity of this asset's title/alt/caption/role
    against the narration script text, when one was supplied. Ranking
    metadata only — not a second visual-selection engine, and never used to
    gate/filter media the way property_match_score does."""
    downloaded: bool = False
    provider: Optional[str] = None
    """Where the media reference came from: og_image, json_ld, img_tag,
    img_tag_srcset, embedded_json, flight_data, script_state, gallery,
    video_tag, youtube_embed, vimeo_embed, schema_video_object."""

    media_url: Optional[str] = None
    """Alias of `source_url`, kept in sync — some consumers key off this name."""
    alternate_sources: List[Dict[str, Any]] = Field(default_factory=list)
    """Other (source_id, source_url, source_page) references where this same
    underlying photo/video was also found — e.g. a syndicated copy on an
    aggregator, or a different CDN crop size of the same photo. This asset's
    own `source_url`/`source_id` remain the canonical (highest-priority)
    reference; these are kept purely for provenance."""

    def model_post_init(self, __context) -> None:  # noqa: D401
        if self.media_url is None:
            self.media_url = self.source_url
