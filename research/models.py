"""Normalized subset of the standalone semantic-research-engine's output —
only what Semantic YT Studio's asset pipeline actually needs. Deliberately
does NOT mirror the engine's full research.json schema; that stays the
engine's own concern (see package_importer.py for the mapping).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class PropertySummary:
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    property_type: Optional[str] = None
    confidence: float = 0.0


@dataclasses.dataclass
class MediaCandidate:
    """One property-scoped media candidate, already downloaded to disk by
    the research engine. `used` is mutated in place by ResearchAssetProvider
    as candidates get assigned to scenes, so the same photo isn't handed to
    every scene about the property."""

    local_path: Optional[Path]
    media_type: str  # "image" | "video"
    source_url: str
    title: Optional[str] = None
    role: Optional[str] = None
    property_match_score: float = 0.0
    script_relevance: Optional[float] = None
    quality_score: float = 0.0
    width: Optional[int] = None
    height: Optional[int] = None
    license_status: str = "unknown"
    license_evidence: Optional[str] = None
    source_id: Optional[str] = None
    used: bool = False
    download_note: Optional[str] = None
    """The engine's own classification of how this file ended up on disk —
    e.g. "duplicate_reused" (byte-identical to media already downloaded,
    reused rather than re-fetched) vs. None (freshly downloaded this run).
    Used only for the Research UI's reused/new breakdown — never affects
    candidate selection."""


@dataclasses.dataclass
class ResearchResult:
    property: PropertySummary = dataclasses.field(default_factory=PropertySummary)
    media: List[MediaCandidate] = dataclasses.field(default_factory=list)
    sources: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    ok: bool = True
    error: Optional[str] = None
    property_ambiguous: bool = False
    """True when topic/script-only discovery found multiple plausible-but-
    different candidate properties close in confidence (see the engine's
    statistics.property_ambiguous / candidate_properties) — the caller must
    surface this, never silently treat `property` as the confirmed target.
    Always False for URL-supplied research (a URL is canonical by definition)."""

    def has_media(self) -> bool:
        # NOTE: plain method, not @property — a dataclass field literally
        # named `property` shadows the `property` builtin for the rest of
        # this class body, so `@property` cannot be used here.
        return any(m.local_path for m in self.media)


@dataclasses.dataclass
class ResearchSettings:
    """Per-run inputs for the Manual Research UI. All four combinations
    (topic only / topic+script / topic+urls / topic+script+urls) are valid —
    topic is the only input the UI treats as required."""

    topic: str = ""
    script_text: str = ""
    script_path: str = ""
    urls: List[str] = dataclasses.field(default_factory=list)
    domain: str = "auto"
    max_media_per_property: int = 20
    script_fingerprint: Optional[str] = None
    """SHA-256 of the exact script text this research run was bound to (see
    research/settings.py::compute_script_fingerprint). None when the run had
    no script (URL/topic-only) — that research is property-bound, not
    script-bound, and must never be invalidated by a script written later."""
