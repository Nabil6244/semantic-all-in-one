"""Seed ~/.videogen/sfx from the bundled starter library (SFX + ambience + all categories)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from smart_editing import SFX_CATEGORIES, SfxCatalog, sfx_library_root

# Packaged builds must ship at least this many wavs (catalog currently has 62).
MIN_BUNDLED_WAVS = 40


def _repo_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def bundled_sfx_source() -> Optional[Path]:
    """Return bundled SFX tree (catalog + wavs) if shipped with the app."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / "bundled-sfx")
    # Dev / non-frozen: next to package
    candidates.append(Path(__file__).resolve().parent.parent / "assets" / "bundled-sfx")
    for path in candidates:
        if (path / "catalog.json").is_file():
            return path
    return None


def bundled_sfx_inventory(src: Optional[Path] = None) -> Dict[str, Any]:
    """Describe the shipped library (used by build checks + diagnostics)."""
    root = src or bundled_sfx_source()
    if root is None:
        return {"ok": False, "path": None, "wav_count": 0, "categories": {}, "error": "missing"}
    wavs = list(root.rglob("*.wav"))
    cats: Dict[str, int] = {}
    for cat in SFX_CATEGORIES:
        cats[cat] = len(list((root / cat).glob("*.wav"))) if (root / cat).is_dir() else 0
    catalog_ok = (root / "catalog.json").is_file()
    ambience_ok = cats.get("ambience", 0) > 0
    ok = catalog_ok and len(wavs) >= MIN_BUNDLED_WAVS and ambience_ok
    return {
        "ok": ok,
        "path": str(root),
        "wav_count": len(wavs),
        "categories": cats,
        "catalog": catalog_ok,
        "error": None if ok else "incomplete bundled-sfx",
    }


def count_resolvable_sfx(root: Optional[Path] = None) -> int:
    catalog = SfxCatalog.load(root)
    if not catalog.entries:
        return 0
    return sum(1 for entry in catalog.entries if entry.resolved_path(catalog.root).is_file())


def _copy_category_wavs(src: Path, dest: Path, *, force: bool = False) -> int:
    """Copy every *.wav under known categories. Returns number of files written."""
    written = 0
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
                written += 1
    return written


def ensure_sfx_library(*, force: bool = False) -> Path:
    """
    Ensure ~/.videogen/sfx has catalog + ambience/SFX wavs from the bundled pack.

    - Empty library → full copy
    - Partial library → copy any missing wavs (repair)
    - force=True → overwrite wavs from bundle
    """
    dest = sfx_library_root()
    dest.mkdir(parents=True, exist_ok=True)

    src = bundled_sfx_source()
    if src is None:
        return dest

    existing = count_resolvable_sfx(dest)
    need_catalog = force or not (dest / "catalog.json").is_file()
    # Repair when empty OR clearly incomplete vs bundled inventory
    inv = bundled_sfx_inventory(src)
    bundled_n = int(inv.get("wav_count") or 0)
    need_wavs = force or existing < max(1, bundled_n // 2)

    if not need_catalog and not need_wavs:
        # Still fill any missing individual files (e.g. new ambience added in an update)
        _copy_category_wavs(src, dest, force=False)
        return dest

    catalog_src = src / "catalog.json"
    if catalog_src.is_file() and (need_catalog or need_wavs or force):
        try:
            data = json.loads(catalog_src.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            data["library_root"] = str(dest)
            (dest / "catalog.json").write_text(
                json.dumps(data, indent=2, sort_keys=False),
                encoding="utf-8",
            )

    _copy_category_wavs(src, dest, force=force)
    return dest
