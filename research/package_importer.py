"""Reads a semantic-research-engine output directory (research.json +
metadata/media_manifest.json when the property pipeline produced one) into
a normalized ResearchResult. Never raises — a missing/malformed package
comes back as an empty, but not necessarily failed, result.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from research.models import MediaCandidate, PropertyFact, PropertySummary, ResearchResult


def _load_facts(output_dir: Path, data: dict, sources: list) -> list:
    """Structured facts from the engine's facts.json, falling back to the
    `facts` block inside research.json (write_package writes the full
    package there, so both carry the same list).

    Every field the engine recorded is preserved — attribution, confidence,
    unit, original text — and source_url is resolved from sources[] via
    source_id so a fact can be traced to its page without a second lookup.
    Never raises and never invents a fact."""
    raw_facts = None
    facts_path = output_dir / "facts.json"
    if facts_path.is_file():
        try:
            payload = json.loads(facts_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                raw_facts = payload.get("facts")
            elif isinstance(payload, list):
                raw_facts = payload
        except (json.JSONDecodeError, OSError):
            raw_facts = None
    if raw_facts is None:
        raw_facts = data.get("facts")
    if not isinstance(raw_facts, list):
        return []

    url_by_source = {}
    for source in sources or []:
        if isinstance(source, dict) and source.get("source_id"):
            url_by_source[source["source_id"]] = source.get("source_url") or ""

    out = []
    for entry in raw_facts:
        if not isinstance(entry, dict) or not entry.get("key"):
            continue
        source_id = entry.get("source_id")
        try:
            confidence = float(entry.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        out.append(
            PropertyFact(
                key=str(entry.get("key")),
                value=str(entry.get("value") if entry.get("value") is not None else ""),
                normalized_value=entry.get("normalized_value"),
                unit=entry.get("unit"),
                original_text=entry.get("original_text"),
                source_id=source_id,
                source_type=entry.get("source_type"),
                confidence=confidence,
                context=entry.get("context"),
                source_url=url_by_source.get(source_id, ""),
            )
        )
    return out


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
        role_detail=entry.get("role_detail"),
        property_match_score=float(entry.get("property_match_score") or 0.0),
        script_relevance=entry.get("script_relevance"),
        quality_score=float(entry.get("quality_score") or 0.0),
        width=entry.get("actual_width") or entry.get("width"),
        height=entry.get("actual_height") or entry.get("height"),
        quality_tier=entry.get("quality_tier"),
        probe_status=entry.get("probe_status"),
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
        role_detail=entry.get("role_detail"),
        property_match_score=float(entry.get("property_match_score") or 0.0),
        script_relevance=entry.get("script_relevance"),
        quality_score=float(entry.get("quality_score") or 0.0),
        width=entry.get("actual_width") or entry.get("width"),
        height=entry.get("actual_height") or entry.get("height"),
        quality_tier=entry.get("quality_tier"),
        probe_status=entry.get("probe_status"),
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
        facts=_load_facts(output_dir, data, data.get("sources", [])),
        rejected_media_count=int(statistics.get("rejected_media") or 0),
    )
