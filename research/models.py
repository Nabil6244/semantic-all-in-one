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
    property_id: str = ""
    """Stable per-listing identity. Every MediaCandidate researched for this
    property carries the same value, and Research candidate filtering is done
    by property_id BEFORE ranking (see ResearchAssetProvider) so one
    listing's photos can never be selected for another listing's scene."""
    source_url: str = ""
    """The listing URL this property was researched from, when URL-supplied."""


@dataclasses.dataclass
class PropertyFact:
    """One structured, source-attributed claim about a property, as extracted
    by the research engine (see its facts.json / RealEstateAdapter).

    Everything the engine knows about the claim is preserved verbatim —
    attribution, confidence, unit and the original matched text — so the
    property-video layer never has to re-derive a fact from narration text,
    and a fact can always be traced back to the page it came from."""

    key: str
    value: str
    normalized_value: Optional[Any] = None
    unit: Optional[str] = None
    original_text: Optional[str] = None
    source_id: Optional[str] = None
    source_type: Optional[str] = None
    confidence: float = 0.0
    context: Optional[str] = None
    property_id: str = ""
    source_url: str = ""
    """URL of the page this fact was extracted from, resolved from the
    package's sources[] via source_id when available."""

    @property
    def display_value(self) -> str:
        """Human/searchable form — prefers the original matched text (e.g.
        "57 acres") over the normalized scalar (57)."""
        return self.original_text or self.value


@dataclasses.dataclass
class MediaCandidate:
    """One property-scoped media candidate, already downloaded to disk by
    the research engine. `used` is mutated in place by ResearchAssetProvider
    as candidates get assigned to scenes, so the same photo isn't handed to
    every scene about the property."""

    local_path: Optional[Path]
    media_type: str  # "image" | "video"
    source_url: str
    property_id: str = ""
    """Which researched listing this media belongs to. Never blank in a
    multi-listing project; a scene scoped to property X must only ever be
    offered candidates whose property_id == X (hard filter, applied before
    ranking — not a ranking penalty)."""
    title: Optional[str] = None
    role: Optional[str] = None
    role_detail: Optional[str] = None
    """Granular scraper-side role (approach/interior/water/structure/
    construction_detail/boundary_map/land/recreation/...) when the
    research engine could tell. None when unknown — never guessed."""
    property_match_score: float = 0.0
    script_relevance: Optional[float] = None
    quality_score: float = 0.0
    width: Optional[int] = None
    height: Optional[int] = None
    quality_tier: Optional[int] = None
    """Measured-pixel tier from the research engine: 1 (>=1600px long
    side), 2 (>=1200), 3 (>=960), 4 (<960). None when the engine could
    not measure it — never inferred from a URL or filename."""
    probe_status: Optional[str] = None
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
    facts: List[PropertyFact] = dataclasses.field(default_factory=list)
    """Structured property facts from the engine (facts.json). Empty when the
    package predates fact extraction — never fabricated."""
    rejected_media_count: int = 0
    """From the engine's statistics.rejected_media — media found on the
    property's page(s) but excluded before download (failed the property-
    match gate, looked like a logo/headshot/similar-listing, etc.). 0 when
    the engine's output doesn't include this statistic, never a guess."""

    def has_media(self) -> bool:
        # NOTE: plain method, not @property — a dataclass field literally
        # named `property` shadows the `property` builtin for the rest of
        # this class body, so `@property` cannot be used here.
        return any(m.local_path for m in self.media)

    def facts_dict(self) -> Dict[str, str]:
        """Flat {key: display_value} view, which is exactly the shape the
        Property Script Analyzer's existing `property_facts` parameter
        already expects — so wiring facts through needs no planner change.

        Multi-valued keys (a listing has many `feature` facts) are joined
        rather than overwritten, so no extracted fact is silently dropped.
        Highest-confidence fact wins for single-valued keys."""
        best: Dict[str, PropertyFact] = {}
        multi: Dict[str, List[str]] = {}
        for fact in self.facts:
            if not fact.key:
                continue
            multi.setdefault(fact.key, []).append(fact.display_value)
            current = best.get(fact.key)
            if current is None or fact.confidence > current.confidence:
                best[fact.key] = fact
        out: Dict[str, str] = {}
        for key, values in multi.items():
            unique = list(dict.fromkeys(v for v in values if v))
            out[key] = "; ".join(unique) if len(unique) > 1 else (unique[0] if unique else "")
        return out

    def facts_for_key(self, key: str) -> List[PropertyFact]:
        return [f for f in self.facts if f.key == key]


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
