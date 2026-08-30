"""Research package serialization: research.json/facts.json/sources.json/media.json
plus the media/images, media/videos directory layout."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from app.models.research import ResearchPackage

RESEARCH_FILENAME = "research.json"
FACTS_FILENAME = "facts.json"
SOURCES_FILENAME = "sources.json"
MEDIA_FILENAME = "media.json"


def package_output_dirs(output_dir: Path) -> dict[str, Path]:
    return {
        "root": output_dir,
        "images": output_dir / "media" / "images",
        "videos": output_dir / "media" / "videos",
    }


def ensure_output_dirs(output_dir: Path) -> dict[str, Path]:
    dirs = package_output_dirs(output_dir)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def write_package(package: ResearchPackage, output_dir: Path) -> None:
    ensure_output_dirs(output_dir)
    full = json.loads(package.model_dump_json())

    _write_json(output_dir / RESEARCH_FILENAME, full)
    _write_json(output_dir / FACTS_FILENAME, {"facts": full["facts"], "conflicts": full["conflicts"]})
    _write_json(output_dir / SOURCES_FILENAME, {"sources": full["sources"]})
    _write_json(output_dir / MEDIA_FILENAME, {"media": full["media"]})


def resolve_package_path(path: Path) -> Tuple[Path, Path]:
    """Accepts either a package directory or a direct path to research.json.
    Returns (research_json_path, package_dir)."""
    path = Path(path)
    if path.is_file():
        return path, path.parent
    return path / RESEARCH_FILENAME, path


def load_package(path: Path) -> ResearchPackage:
    research_path, _ = resolve_package_path(Path(path))
    if not research_path.exists():
        raise FileNotFoundError(f"No {RESEARCH_FILENAME} found at {path}")
    data = json.loads(research_path.read_text(encoding="utf-8"))
    return ResearchPackage.model_validate(data)


def summarize_package(package: ResearchPackage) -> str:
    downloaded_images = sum(1 for m in package.media if m.media_type.value == "image" and m.downloaded)
    downloaded_videos = sum(1 for m in package.media if m.media_type.value == "video" and m.downloaded)
    lines = [
        f"research_id: {package.research_id}",
        f"query: {package.query}",
        f"topic: {package.topic}",
        f"domain: {package.domain}",
        f"engine_version: {package.metadata.engine_version}  (schema {package.metadata.schema_version})",
        f"generated_at: {package.metadata.generated_at}",
        f"confidence: {package.confidence.confidence:.2f}  ({'; '.join(package.confidence.reasons) or 'no signal'})",
        "",
        f"queries ({len(package.queries)}):",
        *[f"  - {q}" for q in package.queries],
        "",
        f"sources: {len(package.sources)}",
        *[
            f"  - [{s.source_type.value}{' PRIMARY' if s.is_primary else ''}] {s.source_url} "
            f"(quality={s.quality_score:.2f}, access={s.access_status.value})"
            for s in package.sources
        ],
        "",
        f"entities: {len(package.normalized_entities)}",
        *[f"  - [{e.entity_type.value}] {e.name}" for e in package.normalized_entities[:10]],
        "",
        f"facts: {len(package.facts)}  (conflicts: {len(package.conflicts)})",
        *[f"  - {f.key} = {f.value} (source={f.source_id}, confidence={f.confidence:.2f})" for f in package.facts[:20]],
        *([f"  ! conflict on '{c.key}': " + ", ".join(f"{fa.value} ({fa.source_id})" for fa in c.facts) for c in package.conflicts] if package.conflicts else []),
        "",
        f"media: {len(package.media)}  (images downloaded={downloaded_images}, videos downloaded={downloaded_videos})",
        f"statistics: {json.dumps(package.statistics)}" if package.statistics else "",
    ]
    return "\n".join(line for line in lines if line is not None)
