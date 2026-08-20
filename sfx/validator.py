"""Validate ~/.videogen/sfx/catalog.json and files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from sfx.audio_probe import is_supported_audio, probe_audio
from sfx.catalog_io import entry_metadata_issues, load_catalog
from smart_editing import SFX_CATEGORIES


@dataclass
class ValidationIssue:
    entry_id: str
    message: str


@dataclass
class ValidationReport:
    library_root: Path
    total_entries: int = 0
    valid_files: int = 0
    missing_files: int = 0
    invalid_files: int = 0
    duplicate_ids: int = 0
    duplicate_files: int = 0
    invalid_metadata: int = 0
    invalid_licenses: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.total_entries > 0
            and self.missing_files == 0
            and self.invalid_files == 0
            and self.duplicate_ids == 0
            and self.duplicate_files == 0
            and self.invalid_metadata == 0
            and self.invalid_licenses == 0
        )

    def format_summary(self) -> str:
        lines = ["SFX LIBRARY"]
        if self.ok:
            lines.append(f"✓ {self.total_entries} sounds")
            lines.append(f"✓ {self.valid_files} files valid")
            lines.append("✓ 0 missing")
            lines.append("✓ 0 duplicate IDs")
            lines.append("✓ 0 invalid licenses")
        else:
            lines.append(f"{'✓' if self.total_entries else '⚠'} {self.total_entries} sounds")
            lines.append(
                f"{'✓' if self.valid_files == self.total_entries and self.invalid_files == 0 else '⚠'} "
                f"{self.valid_files} files valid"
            )
            lines.append(f"{'✓' if self.missing_files == 0 else '⚠'} {self.missing_files} missing")
            lines.append(f"{'✓' if self.duplicate_ids == 0 else '⚠'} {self.duplicate_ids} duplicate IDs")
            lines.append(f"{'✓' if self.invalid_licenses == 0 else '⚠'} {self.invalid_licenses} invalid licenses")
            if self.duplicate_files:
                lines.append(f"⚠ {self.duplicate_files} duplicate file paths")
            if self.invalid_metadata:
                lines.append(f"⚠ {self.invalid_metadata} metadata issues")
            if self.invalid_files:
                lines.append(f"⚠ {self.invalid_files} unreadable files")
        if self.issues:
            lines.append("")
            lines.append("Details:")
            for issue in self.issues[:20]:
                label = issue.entry_id or "(catalog)"
                lines.append(f"  - {label}: {issue.message}")
            if len(self.issues) > 20:
                lines.append(f"  … and {len(self.issues) - 20} more")
        return "\n".join(lines)


def validate_library(root: Optional[Path] = None) -> ValidationReport:
    root = Path(root) if root else Path(load_catalog().get("library_root") or "")
    if not root.is_dir():
        root = Path.home() / ".videogen" / "sfx"
    report = ValidationReport(library_root=root)
    try:
        catalog = load_catalog(root)
    except ValueError as exc:
        report.issues.append(ValidationIssue("", str(exc)))
        return report

    entries = list(catalog.get("sfx") or [])
    report.total_entries = len(entries)
    seen_ids: dict[str, int] = {}
    seen_files: dict[str, int] = {}

    for entry in entries:
        eid = str(entry.get("id") or "")
        seen_ids[eid] = seen_ids.get(eid, 0) + 1
        rel = str(entry.get("file") or "")
        seen_files[rel] = seen_files.get(rel, 0) + 1

        meta_issues = entry_metadata_issues(entry)
        if meta_issues:
            report.invalid_metadata += 1
            for msg in meta_issues:
                report.issues.append(ValidationIssue(eid, msg))

        if bool(entry.get("commercial_use")):
            if not str(entry.get("license") or "").strip() or not str(entry.get("source") or "").strip():
                report.invalid_licenses += 1
                report.issues.append(
                    ValidationIssue(
                        eid,
                        "commercial_use=true requires both source and license metadata",
                    )
                )

        category = str(entry.get("category") or "").lower()
        if category and category not in SFX_CATEGORIES:
            report.issues.append(ValidationIssue(eid, f"unknown category '{category}'"))

        if not rel:
            report.missing_files += 1
            continue
        path = root / rel
        if not path.is_file():
            report.missing_files += 1
            report.issues.append(ValidationIssue(eid, f"missing file: {rel}"))
            continue
        if not is_supported_audio(path):
            report.invalid_files += 1
            report.issues.append(ValidationIssue(eid, f"unsupported format: {path.suffix}"))
            continue
        try:
            info = probe_audio(path)
            report.valid_files += 1
            catalog_duration = float(entry.get("duration") or 0.0)
            if catalog_duration <= 0:
                report.issues.append(ValidationIssue(eid, "catalog duration must be > 0"))
            elif abs(catalog_duration - info.duration_seconds) > 0.25:
                report.issues.append(
                    ValidationIssue(
                        eid,
                        f"duration mismatch (catalog={catalog_duration:.2f}s, file={info.duration_seconds:.2f}s)",
                    )
                )
        except (ValueError, RuntimeError, FileNotFoundError) as exc:
            report.invalid_files += 1
            report.issues.append(ValidationIssue(eid, str(exc)))

    report.duplicate_ids = sum(1 for count in seen_ids.values() if count > 1)
    report.duplicate_files = sum(1 for count in seen_files.values() if count > 1)
    for eid, count in seen_ids.items():
        if count > 1:
            report.issues.append(ValidationIssue(eid, f"duplicate id ({count} entries)"))
    for rel, count in seen_files.items():
        if count > 1:
            report.issues.append(ValidationIssue(rel, f"duplicate file path ({count} entries)"))
    return report
