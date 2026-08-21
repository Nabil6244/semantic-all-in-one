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

    Also unwraps nested GitHub Actions artifact zips that only contain an inner
    .tar.gz / .zip (+ optional .sha256 sidecar).
    """
    archive = Path(archive)
    dest = Path(dest)
    if not archive.is_file():
        raise ExtractError(f"Archive not found: {archive}")

    with tempfile.TemporaryDirectory(prefix="videogen-extract-") as tmp:
        staging = Path(tmp) / "out"
        staging.mkdir()
        _extract_into(archive, staging)
        staging = _unwrap_nested_archives(staging)
        payload = _unwrap_single_child(staging)

        if clear_dest and dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        dest.parent.mkdir(parents=True, exist_ok=True)

        # macOS .app destination
        if dest.suffix == ".app" or dest.name.endswith(".app"):
            app_payload = _find_app_bundle(payload)
            if app_payload is not None:
                shutil.move(str(app_payload), str(dest))
                return dest
            dmg = _find_dmg(payload)
            if dmg is not None:
                raise ExtractError(
                    f"{archive.name} contains a .dmg ({dmg.name}), not an .app bundle. "
                    "Re-publish the macOS install zip of the .app (not the DMG)."
                )
            # Contents were the .app internals — wrap unexpected; just copy tree
            dest.mkdir(parents=True, exist_ok=True)
            _copy_tree(payload, dest)
            return dest

        # Windows onedir zip: often contains product folder/* or flat files
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


def _is_archive_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar"))


def _unwrap_nested_archives(staging: Path) -> Path:
    """If staging only has archives (+ checksum sidecars), extract the largest archive."""
    for _ in range(3):  # allow zip → tar.gz → contents
        children = [p for p in staging.iterdir() if p.name not in (".", "..")]
        archives = [p for p in children if p.is_file() and _is_archive_file(p)]
        others = [
            p
            for p in children
            if not (
                p.is_file()
                and (
                    _is_archive_file(p)
                    or p.name.lower().endswith((".sha256", ".md5", ".sha1", ".txt"))
                )
            )
        ]
        if not archives or others:
            return staging
        inner = max(archives, key=lambda p: p.stat().st_size)
        nested = staging / "_nested"
        if nested.exists():
            shutil.rmtree(nested)
        nested.mkdir()
        _extract_into(inner, nested)
        # Replace staging contents with nested extraction
        for child in list(staging.iterdir()):
            if child.name == "_nested":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        for child in nested.iterdir():
            shutil.move(str(child), str(staging / child.name))
        shutil.rmtree(nested)
    return staging


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


def _find_app_bundle(root: Path) -> Path | None:
    if root.is_dir() and root.name.endswith(".app"):
        return root
    if not root.is_dir():
        return None
    apps = sorted(p for p in root.rglob("*.app") if p.is_dir())
    return apps[0] if apps else None


def _find_dmg(root: Path) -> Path | None:
    if root.is_file() and root.suffix.lower() == ".dmg":
        return root
    if not root.is_dir():
        return None
    dmgs = sorted(p for p in root.rglob("*.dmg") if p.is_file())
    return dmgs[0] if dmgs else None


def _copy_tree(src: Path, dest: Path) -> None:
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
