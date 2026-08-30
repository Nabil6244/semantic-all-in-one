"""Normalized entities — a domain-agnostic shape that domain adapters
populate from extracted facts. Deliberately generic (a flexible `attributes`
bag) rather than a rigid per-domain schema, so new domains don't require
model changes."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    PROPERTY = "property"
    PRODUCT = "product"
    EVENT = "event"
    ARTICLE = "article"
    VIDEO = "video"
    UNKNOWN = "unknown"


class Location(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class NormalizedEntity(BaseModel):
    entity_id: str
    entity_type: EntityType = EntityType.UNKNOWN
    name: Optional[str] = None
    location: Optional[Location] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    """Flexible bag for domain-specific fields not worth a first-class column
    (price, acreage, bedrooms, ...) — mirrors the facts a domain adapter
    considered defining for this entity."""
    source_ids: List[str] = Field(default_factory=list)
