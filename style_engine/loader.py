"""Load built-in and user VideoStyle / BrandKit JSON files."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from .schema import BrandKit, VideoStyle


def _package_root() -> Path:
    """Project / PyInstaller extract root (styles & brand_kits live here)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


_PKG_ROOT = _package_root()
_BUILTIN_STYLES_DIR = _PKG_ROOT / "styles"
_BUILTIN_BRANDS_DIR = _PKG_ROOT / "brand_kits"


def user_brand_kits_dir() -> Path:
    return Path.home() / ".videogen" / "brand_kits"


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _builtin_style_paths() -> tuple:
    if not _BUILTIN_STYLES_DIR.is_dir():
        return ()
    return tuple(sorted(_BUILTIN_STYLES_DIR.glob("*.json")))


def clear_loader_caches() -> None:
    _builtin_style_paths.cache_clear()
    list_builtin_styles.cache_clear()
    list_brand_kits.cache_clear()


@lru_cache(maxsize=1)
def list_builtin_styles() -> tuple:
    out: List[VideoStyle] = []
    for path in _builtin_style_paths():
        try:
            out.append(VideoStyle.from_dict(_read_json(path)))
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            continue
    return tuple(out)


def styles_by_id() -> Dict[str, VideoStyle]:
    return {s.id: s for s in list_builtin_styles()}


def load_style(style_id: str) -> Optional[VideoStyle]:
    key = str(style_id or "").strip()
    if not key:
        return None
    return styles_by_id().get(key)


def style_choices() -> List[tuple]:
    """(id, display name) for UI — built-ins only."""
    return [(s.id, s.name) for s in list_builtin_styles()]


@lru_cache(maxsize=1)
def list_brand_kits() -> tuple:
    kits: Dict[str, BrandKit] = {}
    # Built-ins first
    if _BUILTIN_BRANDS_DIR.is_dir():
        for path in sorted(_BUILTIN_BRANDS_DIR.glob("*.json")):
            try:
                kit = BrandKit.from_dict(_read_json(path))
                kits[kit.id] = kit
            except (OSError, ValueError, json.JSONDecodeError, TypeError):
                continue
    # User kits override same id
    udir = user_brand_kits_dir()
    if udir.is_dir():
        for path in sorted(udir.glob("*.json")):
            try:
                kit = BrandKit.from_dict(_read_json(path))
                kits[kit.id] = kit
            except (OSError, ValueError, json.JSONDecodeError, TypeError):
                continue
    return tuple(kits.values())


def brands_by_id() -> Dict[str, BrandKit]:
    return {k.id: k for k in list_brand_kits()}


def load_brand_kit(brand_kit_id: str) -> Optional[BrandKit]:
    key = str(brand_kit_id or "").strip()
    if not key or key.lower() in ("none", "null"):
        return None
    return brands_by_id().get(key)


def save_user_brand_kit(kit: BrandKit) -> Path:
    udir = user_brand_kits_dir()
    udir.mkdir(parents=True, exist_ok=True)
    path = udir / f"{kit.id}.json"
    path.write_text(json.dumps(kit.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    clear_loader_caches()
    return path


def brand_choices() -> List[tuple]:
    """(id, display name) including None sentinel handled by UI."""
    return [(k.id, k.name or k.id) for k in list_brand_kits()]
