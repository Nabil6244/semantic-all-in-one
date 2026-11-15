"""Real mountain silhouettes for the Sky Sim lake look (docs/skysim/QUALITY.md: the competitor's most used look).

From a real place's elevation (skysim/tools/fetch_terrain.py) and its camera spot, the skyline as seen from just above the
water, in three depth layers (near, mid, far) so the engine can fade the far ones into haze:
  {'az_deg': [...], 'layers': [{'max_km', 'deg': [...]} far -> near], 'place': real}
Angles are degrees above the water horizon for each azimuth (0 = straight ahead). Cached in skysim/assets/ridges/.
No place or no internet -> None, and the engine draws its own seeded ridges.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

ASSETS = Path(__file__).resolve().parent / 'assets'
HALF_FOV = 52.0            # degrees each side (the engine's lens shows ~42; the rest is room for camera drift)
STEP = 0.25                # degrees per sample
BANDS_KM = (9.0, 3.2, 1.1)  # far, mid, near
EYE_M = 2.0
VERSION = 1


def profile(h: np.ndarray, m: float, cam_px, axis_deg: float, eye_m: float = EYE_M) -> Dict[str, Any]:
    n = h.shape[0]
    c0, r0 = cam_px
    az = np.arange(-HALF_FOV, HALF_FOV + 1e-9, STEP)
    dists = np.concatenate([np.arange(30, 1000, 10), np.arange(1000, 4000, 25), np.arange(4000, 9000, 60)]).astype(np.float64)
    b = np.radians(axis_deg + az)[:, None]
    c = c0 + np.sin(b) * dists[None, :] / m
    r = r0 - np.cos(b) * dists[None, :] / m
    inside = (c >= 0) & (c < n - 1) & (r >= 0) & (r < n - 1)
    ci, ri = np.clip(c, 0, n - 1.001), np.clip(r, 0, n - 1.001)
    i0, j0 = ri.astype(int), ci.astype(int)
    fr, fc = ri - i0, ci - j0
    z = (h[i0, j0] * (1 - fr) * (1 - fc) + h[i0, j0 + 1] * (1 - fr) * fc + h[i0 + 1, j0] * fr * (1 - fc) + h[i0 + 1, j0 + 1] * fr * fc)
    z = np.maximum(z, 0.0)
    curve = dists ** 2 / (2 * 6371000.0) * 0.87                         # earth curvature with refraction
    ang = np.degrees(np.arctan2(z - eye_m - curve[None, :], dists[None, :]))
    ang = np.where(inside, ang, -90.0)
    layers = []
    for km in BANDS_KM:
        sel = dists <= km * 1000
        deg = np.maximum(ang[:, sel].max(axis=1), 0.0)
        layers.append({'max_km': km, 'deg': [round(float(x), 3) for x in deg]})
    return {'az_deg': [round(float(a), 3) for a in az], 'layers': layers, 'version': VERSION}


def load(place: str, log=print) -> Optional[Dict[str, Any]]:
    """Ridges for a CSV place, built once from its real terrain. None when there is no real place to use."""
    try:
        from .tools import fetch_terrain
        real = fetch_terrain.ensure(place, log=log, mode='silhouette')
        if not real:
            return None
        out = ASSETS / 'ridges' / f'{real}.json'
        mpath = ASSETS / 'terrain' / f'{real}.silhouette.json'
        if out.exists():
            d = json.loads(out.read_text())
            if d.get('version') == VERSION:
                return d
        meta = json.loads(mpath.read_text())
        h = np.load(ASSETS / 'terrain' / f'{real}.npy')
        d = {**profile(h - meta.get('level_m', 0.0), meta['m_per_px'], meta['cam_px'], meta['axis_deg']), 'place': real, 'note': meta.get('note', '')}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(d))
        return d
    except Exception as e:  # noqa: BLE001 - the engine's own ridges are the fallback
        log(f'Sky Sim: real ridges unavailable for {place} ({e})')
        return None


def peak_deg(ridges: Dict[str, Any], half_width: float = 20.0) -> float:
    """The highest skyline angle within half_width of straight ahead (the object is placed above it)."""
    az, deg = ridges['az_deg'], ridges['layers'][0]['deg']
    return max((d for a, d in zip(az, deg) if abs(a) <= half_width), default=0.0)


if __name__ == '__main__':
    import sys
    d = load(sys.argv[1] if len(sys.argv) > 1 else 'lake_valley')
    if d:
        for L in d['layers']:
            print(L['max_km'], 'km: max', max(L['deg']), 'deg, mean', round(sum(L['deg']) / len(L['deg']), 2))
        print('peak ahead', peak_deg(d))
