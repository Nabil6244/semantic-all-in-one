"""Load/save catalog.json for ~/.videogen/sfx/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from smart_editing import SFX_CATEGORIES, catalog_template_path, sfx_catalog_path, sfx_library_root

REQUIRED_ENTRY_FIELDS = (
    "id",
    "file",
    "category",
    "tags",
    "intensity",
    "duration",
    "source",
    "license",
    "commercial_use",
    "attribution_required",
)

INTENSITY_VALUES = {"low", "medium", "high"}


def default_library_root() -> Path:
    return sfx_library_root()


def template_catalog_path() -> Path:
    return catalog_template_path()


def load_catalog(root: Optional[Path] = None) -> dict:
    path = sfx_catalog_path(root or default_library_root())
    if not path.is_file():
        return {"version": 1, "library_root": str(default_library_root()), "sfx": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Invalid catalog JSON: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Catalog root must be a JSON object: {path}")
    if "sfx" not in data or not isinstance(data["sfx"], list):
        data["sfx"] = []
    return data


def save_catalog(data: dict, root: Optional[Path] = None) -> Path:
    root = Path(root or default_library_root())
    root.mkdir(parents=True, exist_ok=True)
    for category in SFX_CATEGORIES:
        (root / category).mkdir(parents=True, exist_ok=True)
    path = sfx_catalog_path(root)
    payload = dict(data)
    payload.setdefault("version", 1)
    payload.setdefault("library_root", str(root))
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return path


def load_template_catalog() -> dict:
    path = template_catalog_path()
    if not path.is_file():
        raise FileNotFoundError(f"Starter catalog template not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sfx"), list):
        raise ValueError(f"Invalid starter catalog template: {path}")
    return data


def normalize_entry(raw: dict, *, default_category: str = "") -> dict:
    tags_raw = raw.get("tags") or []
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    else:
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    intensity = str(raw.get("intensity") or "medium").lower()
    if intensity not in INTENSITY_VALUES:
        intensity = "medium"
    category = str(raw.get("category") or default_category).lower()
    entry_id = str(raw.get("id") or "").strip()
    file_path = str(raw.get("file") or "").strip()
    if not file_path and entry_id and category:
        # An entry without an explicit path falls back to the catalog's own
        # declared container, NOT a hardcoded .wav — otherwise an opus/flac
        # library would synthesise paths that do not exist on disk.
        ext = str(raw.get("format") or "wav").strip().lstrip(".").lower() or "wav"
        file_path = f"{category}/{entry_id}.{ext}"
    try:
        duration = round(float(raw.get("duration") or 0.0), 3)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "id": entry_id,
        "file": file_path.replace("\\", "/"),
        "category": category,
        "tags": tags,
        "intensity": intensity,
        "duration": duration,
        "source": str(raw.get("source") or "").strip(),
        "license": str(raw.get("license") or "").strip(),
        "commercial_use": bool(raw.get("commercial_use", False)),
        "attribution_required": bool(raw.get("attribution_required", False)),
    }


def merge_catalog_entries(existing: List[dict], new_entries: List[dict]) -> Tuple[List[dict], List[str]]:
    by_id = {str(e.get("id")): e for e in existing if e.get("id")}
    warnings: List[str] = []
    for entry in new_entries:
        eid = str(entry.get("id") or "")
        if not eid:
            warnings.append("Skipped entry with empty id.")
            continue
        by_id[eid] = entry
    merged = list(by_id.values())
    merged.sort(key=lambda e: (str(e.get("category")), str(e.get("id"))))
    return merged, warnings


def prune_missing_entries(entries: List[dict], root: Path) -> Tuple[List[dict], List[str]]:
    """Drop catalog rows whose audio file is not on disk. Never invents replacement files."""
    root = Path(root)
    kept: List[dict] = []
    removed: List[str] = []
    for entry in entries:
        rel = str(entry.get("file") or "").strip()
        eid = str(entry.get("id") or rel or "(unknown)")
        if not rel or not (root / rel).is_file():
            removed.append(eid)
            continue
        kept.append(entry)
    return kept, removed


def prune_catalog(root: Optional[Path] = None) -> Tuple[dict, List[str]]:
    """Load catalog, remove missing-file stubs, save if anything changed."""
    root = Path(root or default_library_root())
    catalog = load_catalog(root)
    existing = list(catalog.get("sfx") or [])
    kept, removed = prune_missing_entries(existing, root)
    if removed:
        catalog["sfx"] = kept
        save_catalog(catalog, root)
    return catalog, removed


def entry_metadata_issues(entry: dict) -> List[str]:
    issues: List[str] = []
    for field in REQUIRED_ENTRY_FIELDS:
        if field not in entry:
            issues.append(f"missing field '{field}'")
    eid = str(entry.get("id") or "").strip()
    if not eid:
        issues.append("empty id")
    category = str(entry.get("category") or "").lower()
    if category not in SFX_CATEGORIES:
        issues.append(f"invalid category '{category}'")
    intensity = str(entry.get("intensity") or "").lower()
    if intensity not in INTENSITY_VALUES:
        issues.append(f"invalid intensity '{intensity}'")
    if not str(entry.get("source") or "").strip():
        issues.append("missing source")
    if not str(entry.get("license") or "").strip():
        issues.append("missing license")
    if bool(entry.get("commercial_use")) and not str(entry.get("license") or "").strip():
        issues.append("commercial_use=true requires license")
    rel = str(entry.get("file") or "").strip()
    if not rel:
        issues.append("missing file path")
    try:
        duration = float(entry.get("duration") or 0.0)
        if duration <= 0:
            issues.append("duration must be > 0")
    except (TypeError, ValueError):
        issues.append("invalid duration")
    return issues
