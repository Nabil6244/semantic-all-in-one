#!/usr/bin/env python3
"""Local SFX library setup: init, import curated sounds, validate catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sfx.curator import (
    DEFAULT_CURATED_ROOT,
    DEFAULT_SOURCE_ROOT,
    curate_sonniss_library,
    write_curation_report,
)
from sfx.catalog_io import prune_catalog
from sfx.importer import (
    ImportOptions,
    import_category_folder,
    import_curated_library,
    import_manifest,
    import_single_category_folder,
    init_library,
)
from sfx.starter_catalog import build_starter_catalog
from sfx.validator import validate_library
from smart_editing import sfx_library_root


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    if (root / "catalog.json").is_file() and not args.force:
        print(f"Catalog already exists: {root / 'catalog.json'}")
        print("Use --force to replace the catalog metadata (existing audio files are not deleted).")
        return 1
    if args.from_starter:
        from sfx.catalog_io import save_catalog

        data = build_starter_catalog()
        data["library_root"] = str(root)
        path = save_catalog(data, root)
    else:
        path = init_library(root, from_template=True, overwrite_catalog=args.force)
    print(f"Initialized SFX library at {root}")
    print(f"Catalog: {path}")
    print("Add curated licensed audio files, then run: python -m sfx import …")
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    options = ImportOptions(library_root=root, force=args.force, convert_wav=not args.no_convert)
    if args.manifest:
        result = import_manifest(Path(args.manifest).expanduser(), options)
    elif args.source and args.category:
        result = import_single_category_folder(
            Path(args.source).expanduser(),
            args.category,
            options,
        )
    elif args.source:
        result = import_category_folder(Path(args.source).expanduser(), options)
    else:
        print("Provide --manifest or --source.", file=sys.stderr)
        return 2
    if result.imported:
        print(f"Imported {len(result.imported)} sound(s): {', '.join(result.imported)}")
    if result.skipped:
        print("Skipped:")
        for line in result.skipped:
            print(f"  - {line}")
    if result.duplicates:
        print("Duplicates:")
        for line in result.duplicates:
            print(f"  - {line}")
    if result.errors:
        print("Errors:", file=sys.stderr)
        for line in result.errors:
            print(f"  - {line}", file=sys.stderr)
    return 0 if not result.errors else 1


def _cmd_import_curated(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    curated = Path(args.curated or DEFAULT_CURATED_ROOT).expanduser()
    options = ImportOptions(library_root=root, force=args.force, convert_wav=not args.no_convert)
    result = import_curated_library(curated, options)
    if result.imported:
        print(f"Imported {len(result.imported)} sound(s): {', '.join(result.imported)}")
    if result.skipped:
        print("Skipped:")
        for line in result.skipped:
            print(f"  - {line}")
    if result.duplicates:
        print("Duplicates:")
        for line in result.duplicates:
            print(f"  - {line}")
    if result.errors:
        print("Errors:", file=sys.stderr)
        for line in result.errors:
            print(f"  - {line}", file=sys.stderr)
    return 0 if not result.errors else 1


def _cmd_curate(args: argparse.Namespace) -> int:
    source = Path(args.source or DEFAULT_SOURCE_ROOT).expanduser()
    curated = Path(args.output or DEFAULT_CURATED_ROOT).expanduser()
    report = curate_sonniss_library(source, curated, dry_run=args.dry_run)
    print(report.format_summary())
    if args.report:
        path = write_curation_report(report, Path(args.report).expanduser())
        print(f"\nWrote report: {path}")
    if report.errors:
        return 1
    if not report.staged_files and not args.dry_run:
        print("\nNo files staged. Extract Sonniss GDC audio under the source directory first.")
        return 1
    if not args.dry_run:
        print(f"\nNext: python -m sfx import-curated --curated {curated}")
    return 0


def _cmd_prune(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    _catalog, removed = prune_catalog(root)
    if removed:
        print(f"Removed {len(removed)} missing catalog entr{'y' if len(removed) == 1 else 'ies'}:")
        for eid in removed:
            print(f"  - {eid}")
    else:
        print("No missing catalog entries.")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser() if args.root else sfx_library_root()
    report = validate_library(root)
    print(report.format_summary())
    return 0 if report.ok or args.allow_missing else 1


def _cmd_export_template(args: argparse.Namespace) -> int:
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_starter_catalog(), indent=2), encoding="utf-8")
    print(f"Wrote starter catalog template: {out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage the local ~/.videogen/sfx library (setup utility, not used during render)."
    )
    parser.add_argument(
        "--root",
        default=str(sfx_library_root()),
        help="SFX library root (default: ~/.videogen/sfx)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create library folders and starter catalog.json metadata")
    init_p.add_argument(
        "--from-starter",
        action="store_true",
        help="Write the full ~58-entry starter catalog metadata",
    )
    init_p.add_argument(
        "--force",
        action="store_true",
        help="Replace catalog.json if it already exists",
    )
    init_p.set_defaults(func=_cmd_init)

    import_p = sub.add_parser("import", help="Import curated SFX with license metadata")
    import_p.add_argument("--manifest", help="JSON manifest listing sounds to import")
    import_p.add_argument(
        "--source",
        help="Folder with category subfolders (whoosh/, impact/, …) or one category folder with --category",
    )
    import_p.add_argument(
        "--category",
        help="Import a single flat category folder (whoosh, impact, ui, …)",
    )
    import_p.add_argument(
        "--force",
        action="store_true",
        help="Replace existing ids/files without interactive confirmation",
    )
    import_p.add_argument(
        "--no-convert",
        action="store_true",
        help="Copy files as-is instead of converting to mono 48kHz WAV",
    )
    import_p.set_defaults(func=_cmd_import)

    import_all_p = sub.add_parser(
        "import-curated",
        help="Import all category folders from ~/Downloads/videogen-sfx-curated/",
    )
    import_all_p.add_argument(
        "--curated",
        default=str(DEFAULT_CURATED_ROOT),
        help="Curated staging root with category subfolders",
    )
    import_all_p.add_argument(
        "--force",
        action="store_true",
        help="Replace existing ids/files without interactive confirmation",
    )
    import_all_p.add_argument(
        "--no-convert",
        action="store_true",
        help="Copy files as-is instead of converting to mono 48kHz WAV",
    )
    import_all_p.set_defaults(func=_cmd_import_curated)

    curate_p = sub.add_parser(
        "curate",
        help="Scan Sonniss source tree and stage shortlisted SFX",
    )
    curate_p.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE_ROOT),
        help="Extracted Sonniss GDC source root",
    )
    curate_p.add_argument(
        "--output",
        default=str(DEFAULT_CURATED_ROOT),
        help="Curated staging output root",
    )
    curate_p.add_argument(
        "--report",
        help="Optional JSON report path",
    )
    curate_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and report without copying files",
    )
    curate_p.set_defaults(func=_cmd_curate)

    prune_p = sub.add_parser(
        "prune",
        help="Remove catalog entries whose audio files are missing (keeps valid sounds)",
    )
    prune_p.set_defaults(func=_cmd_prune)

    validate_p = sub.add_parser("validate", aliases=["validate-sfx"], help="Validate catalog and files")
    validate_p.add_argument(
        "--allow-missing",
        action="store_true",
        help="Exit 0 even when files are missing (metadata-only libraries)",
    )
    validate_p.set_defaults(func=_cmd_validate)

    export_p = sub.add_parser("export-template", help="Write sfx/catalog.template.json from starter metadata")
    export_p.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "catalog.template.json"),
    )
    export_p.set_defaults(func=_cmd_export_template)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
