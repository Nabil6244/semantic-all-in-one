"""Fact models — normalized, source-attributed factual claims."""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class Fact(BaseModel):
    """A single normalized factual claim, always attributed to a source."""

    key: str
    value: str
    normalized_value: Optional[Any] = None
    unit: Optional[str] = None
    original_text: Optional[str] = None
    """The raw matched text before normalization, e.g. '20 acres' for value=20/unit=acres."""
    source_id: str
    source_type: Optional[str] = None
    """Denormalized copy of the owning Source's source_type, for convenience
    when reading facts.json without cross-referencing sources.json."""
    confidence: float = 0.5
    context: Optional[str] = None

    def dedup_key(self) -> tuple:
        return (self.key, self.value)


class FactConflict(BaseModel):
    """Two or more sources disagree on the value for the same fact key."""

    key: str
    facts: List[Fact]
    note: Optional[str] = None
