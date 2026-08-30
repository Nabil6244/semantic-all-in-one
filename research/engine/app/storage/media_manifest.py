"""V4: production media package layout for the property-centric pipeline.

Produces, alongside the existing (unmodified) research.json/facts.json/
sources.json/media.json:

    research_output/
        media/001.jpg, 002.jpg, ...      (sequential, ranked, downloaded only)
        metadata/media_manifest.json

This never touches the existing `media/images/`, `media/videos/` layout
written by `download_media`/`write_package` — it only adds numbered copies
alongside it, so nothing in the core schema is removed or broken.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.models.research import ResearchPackage

MANIFEST_FILENAME = "media_manifest.json"


def write_media_manifest(
    package: ResearchPackage,
    output_dir: Path,
    property_id: str = "",
    source_url: str = "",
) -> Path:
    """`property_id`/`source_url` are supplied by the multi-property job
    layer. They default to empty so every existing single-property caller
    keeps working unchanged."""
    output_dir = Path(output_dir)
    media_dir = output_dir / "media"
    metadata_dir = output_dir / "metadata"
    media_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    # package.media is already ranked (quality_score desc) by the researcher.
    for index, asset in enumerate(package.media, start=1):
        local_path = None
        if asset.downloaded and asset.local_path and Path(asset.local_path).exists():
            ext = Path(asset.local_path).suffix or (".jpg" if asset.media_type.value == "image" else ".mp4")
            numbered_name = f"{index:03d}{ext}"
            shutil.copy2(asset.local_path, media_dir / numbered_name)
            local_path = f"media/{numbered_name}"

        entries.append({
            "local_path": local_path,
            "media_type": asset.media_type.value,
            "role": asset.role,
            "role_detail": asset.role_detail,
            # Measured-pixel quality tier (1 = >=1600px long side .. 4 = <960px),
            # plus the measured/declared split so a consumer can tell a real
            # measurement from a page's claim about itself.
            "quality_tier": asset.quality_tier,
            "actual_width": asset.actual_width,
            "actual_height": asset.actual_height,
            "declared_width": asset.declared_width,
            "declared_height": asset.declared_height,
            "probe_status": asset.probe_status,
            "title": asset.title,
            "source_url": asset.source_url,
            "source_id": asset.source_id,
            "property_id": asset.property_id,
            "variant_group": asset.variant_group,
            "alternate_sources": asset.alternate_sources,
            "property_match_score": asset.property_match_score,
            "relevance_score": asset.relevance_score,
            "script_relevance": asset.script_relevance,
            "quality_score": asset.quality_score,
            "width": asset.width,
            "height": asset.height,
            "duration_seconds": asset.duration_seconds,
            "mime_type": asset.mime_type,
            "license_status": asset.license_status.value,
            "license_evidence": asset.license_evidence,
            "downloaded": asset.downloaded,
            "download_note": asset.download_note,
        })

    # Facts are exported at FULL fidelity — value, normalized_value, unit,
    # the original matched text, the source it came from and its confidence.
    # research.json already carries them, but the manifest is what a
    # property-scoped consumer reads, and dropping the units/evidence here
    # would force it to re-derive facts it cannot re-derive correctly.
    facts = [
        {
            "key": fact.key,
            "value": fact.value,
            "normalized_value": fact.normalized_value,
            "unit": fact.unit,
            "original_text": fact.original_text,
            "source_id": fact.source_id,
            "source_type": fact.source_type,
            "confidence": fact.confidence,
            "context": fact.context,
        }
        for fact in package.facts
    ]
    conflicts = [
        {
            "key": conflict.key,
            "note": conflict.note,
            "facts": [
                {"value": f.value, "source_id": f.source_id, "confidence": f.confidence}
                for f in conflict.facts
            ],
        }
        for conflict in package.conflicts
    ]

    manifest = {
        "property": json.loads(package.property.model_dump_json()),
        "property_id": property_id,
        "source_url": source_url,
        "facts": facts,
        "conflicts": conflicts,
        "media": entries,
    }
    manifest_path = metadata_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest_path
