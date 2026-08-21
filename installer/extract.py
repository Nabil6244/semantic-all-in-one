"""Extract zip / tar archives into install destinations."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path


class ExtractError(Exception):
    """Archive extraction failure."""


def extract_archive(archive: Path, dest: Path, *, clear_dest: bool = True) -> Path:
    """
    Extract archive into dest.
    If the archive contains a single top-level folder matching dest.name (e.g. .app),
    contents are placed so dest ends up as that folder (or its contents for onedir zips).
    """
    archive = Path(archive)
    dest = Path(dest)
    if not archive.is_file():
        raise ExtractError(f"Archive not found: {archive}")

    with tempfile.TemporaryDirectory(prefix="videogen-extract-") as tmp:
        staging = Path(tmp) / "out"
        staging.mkdir()
        _extract_into(archive, staging)
        payload = _unwrap_single_child(staging)

        if clear_dest and dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        dest.parent.mkdir(parents=True, exist_ok=True)

        # macOS .app: if payload is SemanticAllInOne.app, move to /Applications/SemanticAllInOne.app
        if dest.suffix == ".app" or dest.name.endswith(".app"):
            if payload.name.endswith(".app"):
                shutil.move(str(payload), str(dest))
                return dest
            # Contents were the .app internals — wrap unexpected; just copy tree
            dest.mkdir(parents=True, exist_ok=True)
            _copy_tree(payload, dest)
            return dest

        # Windows onedir zip: often contains SemanticAllInOne/* or flat files
        if payload.is_dir() and not any(payload.iterdir()):
            raise ExtractError(f"Archive {archive.name} is empty")

        if payload.is_file():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(payload), str(dest / payload.name))
            return dest

        # Prefer merging children into dest (flat install dir)
        dest.mkdir(parents=True, exist_ok=True)
        for child in payload.iterdir():
            target = dest / child.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(child), str(target))
        return dest


def _extract_into(archive: Path, staging: Path) -> None:
    name = archive.name.lower()
    try:
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(staging)
        elif name.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar")):
            with tarfile.open(archive, "r:*") as tf:
                tf.extractall(staging)
        else:
            # Try zip then tar
            try:
                with zipfile.ZipFile(archive, "r") as zf:
                    zf.extractall(staging)
            except zipfile.BadZipFile:
                with tarfile.open(archive, "r:*") as tf:
                    tf.extractall(staging)
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
        raise ExtractError(f"Failed to extract {archive.name}: {exc}") from exc


def _unwrap_single_child(staging: Path) -> Path:
    children = [p for p in staging.iterdir() if p.name not in (".", "..")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return staging


def _copy_tree(src: Path, dest: Path) -> None:
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
