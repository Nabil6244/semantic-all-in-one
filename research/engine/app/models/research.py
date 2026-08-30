"""Top-level research input/output models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.entity import NormalizedEntity
from app.models.fact import Fact, FactConflict
from app.models.media import MediaAsset
from app.models.property import PropertyIdentity
from app.models.source import Source

ENGINE_VERSION = "0.3.0"
SCHEMA_VERSION = "3"
"""V2 -> V3: research.json gained a top-level `property` block (identity +
confidence) for the property-centric pipeline. All v1/v2 fields are
unchanged, so older readers that ignore unknown keys still work."""


class PropertyPackage(BaseModel):
    """The property-centric pipeline's headline output: what property this
    research run believes it's about, and how confident it is. Empty/default
    when the run wasn't property-focused (e.g. a general topic search)."""

    identity: PropertyIdentity = Field(default_factory=PropertyIdentity)
    confidence: float = 0.0


class ResearchInput(BaseModel):
    """Normalized input to a research run."""

    topic: Optional[str] = None
    script: Optional[str] = None
    urls: List[str] = Field(default_factory=list)
    domain: str = "auto"


class ExtractedEntities(BaseModel):
    """Entities identified from a topic/script, used to drive research.
    Raw planning signal — see `NormalizedEntity` for the structured,
    domain-adapter-built entity representation in the output package."""

    entities: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    dates: List[str] = Field(default_factory=list)
    numbers: List[str] = Field(default_factory=list)
    subjects: List[str] = Field(default_factory=list)
    claims: List[str] = Field(default_factory=list)
    visual_requirements: List[str] = Field(default_factory=list)


class ResearchConfidence(BaseModel):
    """A bounded, explained heuristic — never a precise fake probability."""

    confidence: float = 0.0
    reasons: List[str] = Field(default_factory=list)


class ResearchMetadata(BaseModel):
    engine_version: str = ENGINE_VERSION
    schema_version: str = SCHEMA_VERSION
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    elapsed_seconds: Optional[float] = None


class ResearchPackage(BaseModel):
    """The full output of a research run — serialized to research.json.

    v1 fields (research_id, topic, domain, facts, sources, media, conflicts,
    queries, entities, metadata) are preserved as-is. v2 adds `query`,
    `normalized_entities`, `confidence`, and `statistics` — additive only.
    """

    research_id: str
    topic: Optional[str] = None
    query: Optional[str] = None
    """The resolved query this run was driven by (topic, or the first
    generated query when only a script/URLs were given)."""
    domain: str = "auto"
    facts: List[Fact] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)
    media: List[MediaAsset] = Field(default_factory=list)
    conflicts: List[FactConflict] = Field(default_factory=list)
    queries: List[str] = Field(default_factory=list)
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    normalized_entities: List[NormalizedEntity] = Field(default_factory=list)
    confidence: ResearchConfidence = Field(default_factory=ResearchConfidence)
    property: PropertyPackage = Field(default_factory=PropertyPackage)
    """V3: set when this run targeted one specific property (script/URL/topic
    naming a specific listing). See `research/property_researcher.py`."""
    statistics: Dict[str, Any] = Field(default_factory=dict)
    metadata: ResearchMetadata = Field(default_factory=ResearchMetadata)
