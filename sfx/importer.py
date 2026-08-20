"""Import curated SFX into ~/.videogen/sfx/."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from sfx.audio_probe import convert_to_wav, is_supported_audio, probe_audio
from sfx.catalog_io import (
    load_catalog,
    merge_catalog_entries,
    normalize_entry,
    prune_missing_entries,
    save_catalog,
)
from smart_editing import SFX_CATEGORIES


@dataclass
class ImportResult:
    imported: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)


@dataclass
class ImportOptions:
    library_root: Path
    force: bool = False
    convert_wav: bool = True


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _existing_hashes(catalog_entries: Sequence[dict], root: Path) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for entry in catalog_entries:
        rel = str(entry.get("file") or "")
        path = root / rel
        if path.is_file():
            try:
                hashes[_file_hash(path)] = str(entry.get("id") or rel)
            except OSError:
                pass
    return hashes


def init_library(root: Path, *, from_template: bool = True, overwrite_catalog: bool = False) -> Path:
    """Create category folders and starter catalog.json (metadata only)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for category in SFX_CATEGORIES:
        (root / category).mkdir(parents=True, exist_ok=True)
    catalog_path = root / "catalog.json"
    if catalog_path.is_file() and not overwrite_catalog:
        return catalog_path
    if from_template:
        from sfx.catalog_io import load_template_catalog

        data = load_template_catalog()
    else:
        data = {"version": 1, "library_root": str(root), "sfx": []}
    data["library_root"] = str(root)
    return save_catalog(data, root)


def import_manifest(manifest_path: Path, options: ImportOptions) -> ImportResult:
    manifest_path = Path(manifest_path)
    result = ImportResult()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result.errors.append(f"Could not read manifest: {exc}")
        return result
    sounds = payload.get("sounds") if isinstance(payload, dict) else payload
    if not isinstance(sounds, list):
        result.errors.append("Manifest must contain a 'sounds' list.")
        return result
    manifest_dir = manifest_path.parent
    return import_sound_specs(sounds, options, base_dir=manifest_dir)


def _spec_from_audio_file(path: Path, category: str, meta: Optional[dict] = None) -> dict:
    meta = meta or {}
    entry_id = str(meta.get("id") or path.stem)
    return {
        "src": str(path),
        "id": entry_id,
        "category": str(meta.get("category") or category),
        "tags": meta.get("tags") or [],
        "intensity": meta.get("intensity") or "medium",
        "source": meta.get("source") or "",
        "license": meta.get("license") or "",
        "commercial_use": meta.get("commercial_use", False),
        "attribution_required": meta.get("attribution_required", False),
    }


def _load_sidecar(path: Path) -> dict:
    sidecar = path.with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def import_single_category_folder(
    source_dir: Path,
    category: str,
    options: ImportOptions,
) -> ImportResult:
    """Import audio files from one category folder (flat layout)."""
    source_dir = Path(source_dir)
    category = str(category).lower()
    if category not in SFX_CATEGORIES:
        result = ImportResult()
        result.errors.append(f"Unknown category '{category}'.")
        return result
    specs: List[dict] = []
    for path in sorted(source_dir.iterdir()):
        if not path.is_file() or not is_supported_audio(path):
            continue
        specs.append(_spec_from_audio_file(path, category, _load_sidecar(path)))
    return import_sound_specs(specs, options, base_dir=source_dir)


def import_category_folder(source_dir: Path, options: ImportOptions) -> ImportResult:
    """Import audio files from category subfolders; sidecar JSON supplies metadata when present."""
    source_dir = Path(source_dir)
    specs: List[dict] = []
    for category in SFX_CATEGORIES:
        cat_dir = source_dir / category
        if not cat_dir.is_dir():
            continue
        for path in sorted(cat_dir.iterdir()):
            if not path.is_file() or not is_supported_audio(path):
                continue
            specs.append(_spec_from_audio_file(path, category, _load_sidecar(path)))
    return import_sound_specs(specs, options, base_dir=source_dir)


def import_curated_library(curated_root: Path, options: ImportOptions) -> ImportResult:
    """Import all category subfolders from a curated staging directory."""
    return import_category_folder(curated_root, options)


def import_sound_specs(
    specs: Sequence[dict],
    options: ImportOptions,
    *,
    base_dir: Optional[Path] = None,
) -> ImportResult:
    result = ImportResult()
    root = Path(options.library_root)
    root.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(root)
    existing = list(catalog.get("sfx") or [])
    existing_ids = {str(e.get("id")) for e in existing if e.get("id")}
    existing_files = {str(e.get("file")) for e in existing if e.get("file")}
    content_hashes = _existing_hashes(existing, root)

    new_entries: List[dict] = []
    for raw in specs:
        spec = dict(raw)
        src_raw = str(spec.get("src") or spec.get("source_file") or "").strip()
        if not src_raw:
            result.errors.append("Sound spec missing 'src' path.")
            continue
        src_path = Path(src_raw)
        if not src_path.is_absolute() and base_dir is not None:
            src_path = (base_dir / src_path).resolve()
        if not src_path.is_file():
            result.errors.append(f"Source file not found: {src_path}")
            continue
        if not is_supported_audio(src_path):
            result.errors.append(f"Unsupported format: {src_path}")
            continue

        entry = normalize_entry(spec, default_category=str(spec.get("category") or ""))
        if not entry["id"]:
            result.errors.append(f"Missing id for source: {src_path}")
            continue
        if not entry["source"] or not entry["license"]:
            result.errors.append(
                f"{entry['id']}: source and license metadata are required before import."
            )
            continue
        dest_rel = f"{entry['category']}/{entry['id']}.wav"
        dest_path = root / dest_rel
        id_exists = entry["id"] in existing_ids
        file_missing = not dest_path.is_file()
        if id_exists and not options.force and not file_missing:
            result.skipped.append(f"{entry['id']}: id already exists (use --force to replace)")
            continue

        try:
            info = probe_audio(src_path)
        except (ValueError, RuntimeError, FileNotFoundError) as exc:
            result.errors.append(f"{entry['id']}: {exc}")
            continue

        try:
            src_hash = _file_hash(src_path)
        except OSError as exc:
            result.errors.append(f"{entry['id']}: could not hash source ({exc})")
            continue
        if src_hash in content_hashes and content_hashes[src_hash] != entry["id"]:
            result.duplicates.append(
                f"{entry['id']}: duplicate audio content matches existing '{content_hashes[src_hash]}'"
            )
            if not options.force:
                result.skipped.append(f"{entry['id']}: duplicate content")
                continue

        if dest_rel in existing_files and not options.force and not file_missing:
            result.skipped.append(f"{entry['id']}: destination already exists ({dest_rel})")
            continue

        if dest_path.is_file() and not options.force:
            result.skipped.append(f"{entry['id']}: file already on disk ({dest_rel})")
            continue

        try:
            if options.convert_wav:
                convert_to_wav(src_path, dest_path)
                info = probe_audio(dest_path)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dest_path)
        except (OSError, RuntimeError) as exc:
            result.errors.append(f"{entry['id']}: copy/convert failed ({exc})")
            continue

        entry["file"] = dest_rel
        entry["duration"] = round(info.duration_seconds, 3)
        new_entries.append(entry)
        result.imported.append(entry["id"])
        existing_ids.add(entry["id"])
        existing_files.add(dest_rel)
        content_hashes[src_hash] = entry["id"]

    if new_entries:
        merged, warnings = merge_catalog_entries(existing, new_entries)
        catalog["sfx"] = merged
        result.skipped.extend(warnings)
    # Drop stale starter placeholders / missing files so import-curated never leaves orphans.
    kept, removed = prune_missing_entries(list(catalog.get("sfx") or []), root)
    if removed or new_entries:
        catalog["sfx"] = kept
        save_catalog(catalog, root)
        for eid in removed:
            result.skipped.append(f"{eid}: removed missing catalog entry (no audio file)")
    return result
