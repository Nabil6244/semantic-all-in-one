"""pakMap's place lookup, remembered. `pakmap.geo.resolve` is a pure function of its arguments but searches polygons on every call (about a
quarter of a second for an area), and a long documentary asks about the same few hundred places thousands of times while it is
validated, repaired and compiled. This keeps each answer (or each failure) for the life of the process."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from pakmap.geo import GeoError
from pakmap.geo import resolve as _resolve

_CACHE: Dict[Tuple[str, str], Any] = {}


def resolve(name: str, prefer: str = "area"):
    key = (str(name), prefer)
    hit = _CACHE.get(key)
    if hit is None:
        try:
            hit = _resolve(name, prefer)
        except GeoError as exc:
            hit = exc
        _CACHE[key] = hit
    if isinstance(hit, GeoError):
        raise hit
    return hit


__all__ = ["GeoError", "resolve"]
