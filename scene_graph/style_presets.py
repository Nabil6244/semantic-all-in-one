"""Composition StylePreset abstraction + JSON registry.

Mirrors style_engine/loader.py's pattern (built-in JSON dir + lru_cache'd
registry) but for composition/canvas style, which has no home in
style_engine (editorial pacing/camera/audio) or graphics/design_system.py
(a single hardcoded singleton) today. This does not touch either of those
systems — it is a new, additive registry.

Preset content is deliberately kept as loose, style-specific dict buckets
(canvas/nodes/typography/arrows/camera/transitions) rather than fully typed
nested dataclasses: nothing consumes these fields yet (layout/rendering are
later phases), so over-specifying their shape now would be speculative.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

STYLE_PRESET_VERSION = 1


def _package_root() -> Path:
    """Project / PyInstaller extract root (composition_styles/ lives here)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


_PKG_ROOT = _package_root()
_BUILTIN_PRESETS_DIR = _PKG_ROOT / "composition_styles"


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


@dataclasses.dataclass
class StylePreset:
    """A named bundle of Overscaled-style composition rules (versioned JSON)."""

    id: str
    version: int = STYLE_PRESET_VERSION
    name: str = ""
    description: str = ""
    canvas: Dict[str, Any] = dataclasses.field(default_factory=dict)
    nodes: Dict[str, Any] = dataclasses.field(default_factory=dict)
    typography: Dict[str, Any] = dataclasses.field(default_factory=dict)
    arrows: Dict[str, Any] = dataclasses.field(default_factory=dict)
    camera: Dict[str, Any] = dataclasses.field(default_factory=dict)
    transitions: Dict[str, Any] = dataclasses.field(default_factory=dict)
    segment_structure_guidance: List[str] = dataclasses.field(default_factory=list)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "canvas": dict(self.canvas or {}),
            "nodes": dict(self.nodes or {}),
            "typography": dict(self.typography or {}),
            "arrows": dict(self.arrows or {}),
            "camera": dict(self.camera or {}),
            "transitions": dict(self.transitions or {}),
            "segment_structure_guidance": list(self.segment_structure_guidance or []),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "StylePreset":
        if not isinstance(data, dict):
            data = {}
        guidance = data.get("segment_structure_guidance")
        return cls(
            id=str(data.get("id") or ""),
            version=int(data.get("version") or STYLE_PRESET_VERSION),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            canvas=_as_dict(data.get("canvas")),
            nodes=_as_dict(data.get("nodes")),
            typography=_as_dict(data.get("typography")),
            arrows=_as_dict(data.get("arrows")),
            camera=_as_dict(data.get("camera")),
            transitions=_as_dict(data.get("transitions")),
            segment_structure_guidance=[str(s) for s in guidance] if isinstance(guidance, (list, tuple)) else [],
            metadata=_as_dict(data.get("metadata")),
        )


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _builtin_preset_paths() -> tuple:
    if not _BUILTIN_PRESETS_DIR.is_dir():
        return ()
    return tuple(sorted(_BUILTIN_PRESETS_DIR.glob("*.json")))


def clear_style_preset_cache() -> None:
    _builtin_preset_paths.cache_clear()
    list_style_presets.cache_clear()


@lru_cache(maxsize=1)
def list_style_presets() -> tuple:
    out: List[StylePreset] = []
    for path in _builtin_preset_paths():
        try:
            out.append(StylePreset.from_dict(_read_json(path)))
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            continue
    return tuple(out)


def style_presets_by_id() -> Dict[str, StylePreset]:
    return {p.id: p for p in list_style_presets()}


def load_style_preset(preset_id: str) -> Optional[StylePreset]:
    key = str(preset_id or "").strip()
    if not key:
        return None
    return style_presets_by_id().get(key)
