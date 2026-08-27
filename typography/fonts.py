"""Font registry — prefer bundled assets/fonts, then system fallbacks."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Bundled filenames under assets/fonts/ (latin static TTFs).
_BUNDLED: Dict[str, Dict[str, str]] = {
    "Manrope": {
        "Bold": "Manrope-Bold.ttf",
        "ExtraBold": "Manrope-ExtraBold.ttf",
    },
    "Inter": {
        "Regular": "Inter-Regular.ttf",
        "SemiBold": "Inter-SemiBold.ttf",
        "Bold": "Inter-Bold.ttf",
    },
    "Plus Jakarta Sans": {
        "Bold": "PlusJakartaSans-Bold.ttf",
        "ExtraBold": "PlusJakartaSans-ExtraBold.ttf",
    },
    "Space Grotesk": {
        "Bold": "SpaceGrotesk-Bold.ttf",
    },
    "DM Sans": {
        "Medium": "DMSans-Medium.ttf",
        "Bold": "DMSans-Bold.ttf",
    },
    "Outfit": {
        "Bold": "Outfit-Bold.ttf",
        "ExtraBold": "Outfit-ExtraBold.ttf",
    },
}

_WEIGHT_FALLBACK_ORDER = ("ExtraBold", "Bold", "SemiBold", "Medium", "Regular")

_SYSTEM_FALLBACKS: List[str] = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]


def _repo_root() -> Path:
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def bundled_fonts_dir() -> Path:
    return _repo_root() / "assets" / "fonts"


class FontRegistry:
    """Resolve family + weight to a real on-disk font file."""

    families = tuple(_BUNDLED.keys())

    def __init__(self, fonts_dir: Optional[Path] = None) -> None:
        self.fonts_dir = Path(fonts_dir) if fonts_dir else bundled_fonts_dir()

    def candidates(self, family: str, weight: str = "Bold") -> List[Path]:
        family = (family or "Inter").strip()
        weight = (weight or "Bold").strip()
        paths: List[Path] = []
        family_map = _BUNDLED.get(family, {})
        # Preferred weight, then other bundled weights for that family.
        ordered_weights = [weight] + [w for w in _WEIGHT_FALLBACK_ORDER if w != weight]
        for w in ordered_weights:
            name = family_map.get(w)
            if name:
                paths.append(self.fonts_dir / name)
        # Any other bundled family as soft fallback (prefer Inter/Manrope).
        for alt in ("Inter", "Manrope", "DM Sans", "Outfit", "Plus Jakarta Sans", "Space Grotesk"):
            if alt == family:
                continue
            for w in ordered_weights:
                name = _BUNDLED.get(alt, {}).get(w)
                if name:
                    paths.append(self.fonts_dir / name)
        for sys_path in _SYSTEM_FALLBACKS:
            paths.append(Path(sys_path))
        # Deduplicate while preserving order.
        seen = set()
        unique: List[Path] = []
        for p in paths:
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)
        return unique

    def resolve(self, family: str, weight: str = "Bold") -> Optional[Path]:
        for path in self.candidates(family, weight):
            if path.is_file():
                return path.resolve()
        return None

    def resolve_or_raise(self, family: str, weight: str = "Bold") -> Path:
        path = self.resolve(family, weight)
        if path is None:
            raise FileNotFoundError(f"No font file for {family!r} {weight!r}")
        return path


_DEFAULT_REGISTRY = FontRegistry()


@lru_cache(maxsize=64)
def resolve_font_path(family: str, weight: str = "Bold") -> Optional[str]:
    path = _DEFAULT_REGISTRY.resolve(family, weight)
    return str(path) if path else None


def reset_font_cache() -> None:
    resolve_font_path.cache_clear()


def list_bundled_fonts() -> List[Tuple[str, str, Path]]:
    root = bundled_fonts_dir()
    out: List[Tuple[str, str, Path]] = []
    for family, weights in _BUNDLED.items():
        for weight, filename in weights.items():
            path = root / filename
            if path.is_file():
                out.append((family, weight, path))
    return out
