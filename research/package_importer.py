"""Reads a semantic-research-engine output directory (research.json +
metadata/media_manifest.json when the property pipeline produced one) into
a normalized ResearchResult. Never raises — a missing/malformed package
comes back as an empty, but not necessarily failed, result.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from research.models import MediaCandidate, PropertySummary, ResearchResult


def empty_result(error: Optional[str] = None) -> ResearchResult:
    return ResearchResult(property=PropertySummary(), media=[], sources=[], ok=error is None, error=error)


def _media_from_manifest_entry(entry: dict, output_dir: Path) -> MediaCandidate:
    local_path = entry.get("local_path")
    return MediaCandidate(
        local_path=(output_dir / local_path) if local_path else None,
        media_type=entry.get("media_type", "image"),
        source_url=entry.get("source_url", ""),
        title=entry.get("title"),
        role=entry.get("role"),
        property_match_score=float(entry.get("property_match_score") or 0.0),
        script_relevance=entry.get("script_relevance"),
        quality_score=float(entry.get("quality_score") or 0.0),
        width=entry.get("width"),
        height=entry.get("height"),
        license_status=entry.get("license_status", "unknown"),
        license_evidence=entry.get("license_evidence"),
        source_id=entry.get("source_id"),
        download_note=entry.get("download_note"),
    )


def _media_from_research_json_entry(entry: dict) -> MediaCandidate:
    local_path = entry.get("local_path")
    return MediaCandidate(
        local_path=Path(local_path) if local_path else None,
        media_type=entry.get("media_type", "image"),
        source_url=entry.get("source_url", ""),
        title=entry.get("title"),
        role=entry.get("role"),
        property_match_score=float(entry.get("property_match_score") or 0.0),
        script_relevance=entry.get("script_relevance"),
        quality_score=float(entry.get("quality_score") or 0.0),
        width=entry.get("width"),
        height=entry.get("height"),
        license_status=entry.get("license_status", "unknown"),
        license_evidence=entry.get("license_evidence"),
        source_id=entry.get("source_id"),
        download_note=entry.get("download_note"),
    )


def load_research_result(output_dir: Path) -> ResearchResult:
    output_dir = Path(output_dir)
    research_path = output_dir / "research.json"
    if not research_path.is_file():
        return empty_result(error=f"No research.json found in {output_dir}")

    try:
        data = json.loads(research_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return empty_result(error=f"Could not read research.json: {exc}")

    prop_block = data.get("property") or {}
    identity = prop_block.get("identity") or {}
    property_summary = PropertySummary(
        name=identity.get("property_name"),
        address=identity.get("canonical_address"),
        city=identity.get("city"),
        state=identity.get("state"),
        country=identity.get("country"),
        confidence=float(prop_block.get("confidence") or 0.0),
    )

    manifest_path = output_dir / "metadata" / "media_manifest.json"
    media = []
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {"media": []}
        media = [_media_from_manifest_entry(e, output_dir) for e in manifest.get("media", [])]
    else:
        # General (non-property) research runs have no manifest — fall back
        # to research.json's own media[] list.
        media = [_media_from_research_json_entry(m) for m in data.get("media", [])]

    downloadable = [m for m in media if m.local_path and Path(m.local_path).is_file()]
    statistics = data.get("statistics") or {}
    return ResearchResult(
        property=property_summary,
        media=downloadable,
        sources=data.get("sources", []),
        ok=True,
        error=None,
        property_ambiguous=bool(statistics.get("property_ambiguous", False)),
    )
