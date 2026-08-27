"""Normalized visual roles for smart clip selection (Style Intelligence 3.0)."""

from __future__ import annotations

VISUAL_ROLES = frozenset({
    "establishing",
    "event",
    "archival_evidence",
    "person",
    "character",
    "location",
    "object",
    "process",
    "mechanism",
    "map",
    "timeline",
    "comparison",
    "scale",
    "data",
    "document",
    "quote",
    "atmosphere",
    "abstract",
    "reaction",
    "scientific_visualization",
    "transition",
})

EVIDENCE_LEVELS = frozenset({"high", "medium", "low"})
