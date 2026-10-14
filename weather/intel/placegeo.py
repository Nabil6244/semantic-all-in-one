"""Small geography from the county shapes Weather already bundles (weather/alerts.county_shapes): which state a point is in, a
state's centre, a bounding box around a point."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from ..news.timeline import STATE_NAMES


@lru_cache(maxsize=1)
def _counties() -> List[Tuple[str, list, Tuple[float, float, float, float]]]:
    from ..alerts import county_shapes

    out = []
    for c in county_shapes().values():
        st = STATE_NAMES.get(str(c["state"]).lower(), str(c["state"]))
        pts = [pt for poly in c["polys"] for pt in poly[0]]
        if not pts:
            continue
        box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        out.append((st, c["polys"], box))
    return out


def _inside(lon: float, lat: float, ring) -> bool:
    hit = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            hit = not hit
        j = i
    return hit


def state_of_point(lat: float, lon: float, *, tolerance_deg: float = 0.25) -> Optional[str]:
    """The state whose county holds the point; a coastal point just offshore (a landfall fix) takes the nearest county's state."""
    best, best_d = None, None
    for st, polys, box in _counties():
        if box[0] - tolerance_deg <= lon <= box[2] + tolerance_deg and box[1] - tolerance_deg <= lat <= box[3] + tolerance_deg:
            if any(_inside(lon, lat, poly[0]) for poly in polys):
                return st
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            d = (cx - lon) ** 2 + (cy - lat) ** 2
            if best_d is None or d < best_d:
                best, best_d = st, d
    return best


@lru_cache(maxsize=64)
def state_center(state: str) -> Optional[Tuple[float, float]]:
    boxes = [box for st, _p, box in _counties() if st == state]
    if not boxes:
        return None
    return (round((min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2, 3), round((min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2, 3))


def bbox_around(lat: float, lon: float, half_w: float = 2.5, half_h: float = 2.0) -> List[float]:
    """[west, south, east, north] around a point (a rain map's area: at most 12 x 10 degrees)."""
    return [round(lon - half_w, 2), round(lat - half_h, 2), round(lon + half_w, 2), round(lat + half_h, 2)]


def state_boxes() -> Dict[str, Tuple[float, float, float, float]]:
    out: Dict[str, list] = {}
    for st, _p, box in _counties():
        out.setdefault(st, []).append(box)
    return {st: (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)) for st, bs in out.items()}
