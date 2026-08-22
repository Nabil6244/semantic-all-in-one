"""Seed ~/.videogen/sfx from the bundled starter library on first run."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Optional

from smart_editing import SFX_CATEGORIES, SfxCatalog, sfx_library_root


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def bundled_sfx_source() -> Optional[Path]:
    """Return bundled SFX tree (catalog + wavs) if shipped with the app."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / "bundled-sfx")
    candidates.append(_repo_root() / "assets" / "bundled-sfx")
    for path in candidates:
        if (path / "catalog.json").is_file():
            return path
    return None


def count_resolvable_sfx(root: Optional[Path] = None) -> int:
    catalog = SfxCatalog.load(root)
    if not catalog.entries:
        return 0
    return sum(1 for entry in catalog.entries if entry.resolved_path(catalog.root).is_file())


def ensure_sfx_library(*, force: bool = False) -> Path:
    """Copy bundled wavs into ~/.videogen/sfx when the user library is empty."""
    dest = sfx_library_root()
    if not force and count_resolvable_sfx(dest) > 0:
        return dest

    src = bundled_sfx_source()
    if src is None:
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    dest.mkdir(parents=True, exist_ok=True)
    catalog_src = src / "catalog.json"
    if catalog_src.is_file():
        data = json.loads(catalog_src.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["library_root"] = str(dest)
            (dest / "catalog.json").write_text(
                json.dumps(data, indent=2, sort_keys=False),
                encoding="utf-8",
            )

    for category in SFX_CATEGORIES:
        cat_src = src / category
        if not cat_src.is_dir():
            continue
        cat_dest = dest / category
        cat_dest.mkdir(parents=True, exist_ok=True)
        for wav in cat_src.glob("*.wav"):
            target = cat_dest / wav.name
            if force or not target.is_file():
                shutil.copy2(wav, target)

    return dest
