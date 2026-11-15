"""Real places for the Sky Sim valley (realism: memory skysim-realism). Every future video gets them with no hand work:

  ensure('lake_valley')  -> the real place behind that CSV place, fetched once and cached, with its camera found by code
  python -m skysim.tools.fetch_terrain [real place ...]   (fetch ahead of time; re-running skips what is there)

Elevation: the public AWS Terrain Tiles (terrarium PNG, SRTM/GMTED/ETOPO open data, no key). Writes
skysim/assets/terrain/<real>.npy (float32 metres, row 0 = north) + <real>.json (metres per pixel, the camera spot).
No internet or a failed fetch: ensure() returns None and the code-made valley is used (the render never stops for it).
"""
from __future__ import annotations

import io
import json
import math
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

DEST = Path(__file__).resolve().parent.parent / 'assets' / 'terrain'
UA = {'User-Agent': 'skysim-terrain-fetch'}
TILE = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
FINDER_VERSION = 2

# real places: centre, zoom 13 (~9 m a pixel at 60 N), crop size. The camera spot is found by find_camera().
REAL = {
    'oldevatnet': {'lat': 61.775, 'lon': 6.795, 'zoom': 13, 'km': 9.0, 'note': 'Oldevatnet, Norway: a green glacial lake valley'},
    'lovatnet': {'lat': 61.855, 'lon': 6.915, 'zoom': 13, 'km': 9.0, 'note': 'Lovatnet, Norway: a lake under steep green walls'},
    'geiranger': {'lat': 62.112, 'lon': 7.08, 'zoom': 13, 'km': 8.0, 'note': 'Geirangerfjord, Norway: a steep fjord'},
    'tinnsjo': {'lat': 59.88, 'lon': 8.92, 'zoom': 13, 'km': 10.0, 'note': 'Tinnsjå, Norway: a long lake between forested hills'},
    'walensee': {'lat': 47.125, 'lon': 9.21, 'zoom': 13, 'km': 10.0, 'note': 'Walensee, Switzerland: a lake under a mountain wall'},
    'hallstatt': {'lat': 47.575, 'lon': 13.655, 'zoom': 13, 'km': 9.0, 'note': 'Hallstätter See, Austria: an alpine lake'},
}
# CSV place (skysim/steps.py PLACES) -> real places to use, first that works wins. Places not listed keep the code-made scene.
FOR_PLACE = {
    'lake_valley': ('oldevatnet', 'lovatnet', 'geiranger'),
}
FOR_SILHOUETTE = ('tinnsjo', 'walensee', 'hallstatt', 'oldevatnet', 'lovatnet', 'geiranger')   # the lake look, any place


def real_for(place: str) -> tuple:
    return FOR_PLACE.get(place or 'lake_valley', ())


# ---- fetching ----------------------------------------------------------------------------------------------------
def _tile_xy(lat: float, lon: float, z: int):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _tile(z: int, x: int, y: int) -> np.ndarray:
    from PIL import Image
    with urllib.request.urlopen(urllib.request.Request(TILE.format(z=z, x=x, y=y), headers=UA), timeout=60) as r:
        a = np.asarray(Image.open(io.BytesIO(r.read())).convert('RGB'), dtype=np.float32)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


def fetch_dem(real: str) -> np.ndarray:
    P = REAL[real]
    z = P['zoom']
    m_px = 40075016.7 * math.cos(math.radians(P['lat'])) / (2 ** z * 256)
    half = P['km'] * 1000 / m_px / 2
    fx, fy = _tile_xy(P['lat'], P['lon'], z)
    cx, cy = fx * 256, fy * 256
    x0, x1, y0, y1 = int((cx - half) // 256), int((cx + half) // 256), int((cy - half) // 256), int((cy + half) // 256)
    big = np.concatenate([np.concatenate([_tile(z, tx, ty) for tx in range(x0, x1 + 1)], axis=1) for ty in range(y0, y1 + 1)], axis=0)
    ox, oy, n = int(cx - half - x0 * 256), int(cy - half - y0 * 256), int(2 * half)
    return big[oy:oy + n, ox:ox + n].astype(np.float32), m_px


def lake_level(h: np.ndarray, m: float) -> float:
    """The water surface height: inland lakes sit hundreds of metres up. Elevation data stores a lake as a dead-flat
    area, so the level is the most common height among flat cells (the biggest flat body)."""
    gy, gx = np.gradient(h, m)
    flat = np.hypot(gx, gy) < 0.004
    if flat.mean() < 0.01:
        return float(max(h.min(), 0.0))
    vals = np.round(h[flat]).astype(int)
    lv, counts = np.unique(vals, return_counts=True)
    return float(lv[counts.argmax()])


# ---- the camera spot, found by code ---------------------------------------------------------------------------------
def find_camera(h: np.ndarray, m: float, step_px: int = 0, mode: str = 'valley') -> Optional[Dict[str, Any]]:
    """The reference's view, searched for on any terrain: the camera on the water a short way off one shore (so trees stand
    close on that side), looking up a long stretch of water to a far ridge 5-13 degrees high, with walls on both sides.
    mode 'silhouette' (the lake look): open water in the middle of a wide lake, every ridge within 40 degrees of ahead lower
    than 16 degrees (a low dark skyline under a big sky), the ridge ahead 3-11 degrees.
    -> {cam_px: [col, row], axis_deg, shore: 'left'|'right', water_m, ridge_deg, score} or None."""
    n = h.shape[0]
    water = h < 2.0
    step_px = step_px or max(4, int(150 / m))

    def at(c, r):
        return h[min(max(int(r), 0), n - 1), min(max(int(c), 0), n - 1)]

    def ray(c0, r0, b, d_max, dd):
        s, co = math.sin(math.radians(b)), math.cos(math.radians(b))
        for d in range(int(dd), int(d_max), int(dd)):
            c, r = c0 + s * d / m, r0 - co * d / m
            if not (0 <= c < n - 1 and 0 <= r < n - 1):
                return
            yield d, at(c, r)

    best = None
    margin = int(300 / m)
    for r0 in range(margin, n - margin, step_px):
        for c0 in range(margin, n - margin, step_px):
            if not water[r0, c0]:
                continue
            for b in range(0, 360, 6):
                run, ridge, closed = 0, 0.0, False
                for d, v in ray(c0, r0, b, 7000, 50):
                    if v < 2 and run == d - 50:
                        run = d
                    ridge = max(ridge, math.degrees(math.atan2(v - 3, d)))
                    closed |= v > 300 and d > run
                if mode == 'silhouette':
                    if run < 1500 or not (3.0 <= ridge <= 11.0):
                        continue
                    side = max(max((math.degrees(math.atan2(v - 3, d)) for d, v in ray(c0, r0, b + off, 7000, 60)), default=0.0)
                               for off in (-40, -25, 25, 40))
                    near = min(next((d for d, v in ray(c0, r0, b + off, 3000, 20) if v >= 2), 3000) for off in (-90, 90))
                    if side > 16.0 or near < 250:
                        continue
                    score = min(run, 5000) / 1000 - abs(ridge - 7.0) * 0.2 - max(0.0, side - 12.0) * 0.3
                    if not best or score > best['score']:
                        best = {'cam_px': [c0, r0], 'axis_deg': float(b), 'water_m': run, 'ridge_deg': round(ridge, 2),
                                'side_deg': round(side, 2), 'score': round(score, 3)}
                    continue
                if run < 1500 or not closed or not (5.0 <= ridge <= 13.0):
                    continue
                sides = {}
                for name, off in (('left', -90), ('right', 90)):
                    shore = next((d for d, v in ray(c0, r0, b + off, 2500, 20) if v >= 2), None)
                    wall = max((v for d, v in ray(c0, r0, b + off, 2500, 100)), default=0)
                    sides[name] = (shore, wall)
                if min(w for _, w in sides.values()) < 250:
                    continue
                near = min(sides, key=lambda k: sides[k][0] or 1e9)
                dist = sides[near][0] or 1e9
                if not (40 <= dist <= 220):                       # trees close on one side, but the camera is on the water
                    continue
                # a gentle shore by the camera grows grass and forest (the reference's beach), not a cliff
                d_up = next(((d, v) for d, v in ray(c0, r0, b - 90 if near == 'left' else b + 90, dist + 400, 20) if d > dist + 300), None)
                gentle = 1.0 if d_up and d_up[1] < 160 else 0.4
                score = min(run, 5000) / 1000 + 2.0 * gentle - abs(ridge - 9.0) * 0.15 - abs(dist - 110) / 200
                if not best or score > best['score']:
                    best = {'cam_px': [c0, r0], 'axis_deg': float(b), 'shore': near, 'water_m': run, 'ridge_deg': round(ridge, 2),
                            'shore_m': dist, 'score': round(score, 3)}
    return best


def ensure(place: str, log=print, mode: str = 'valley') -> Optional[str]:
    """The real place to build for this CSV place, fetched and its camera found once (cached). None -> the code-made valley."""
    for real in (FOR_SILHOUETTE if mode == 'silhouette' else real_for(place)):
        meta_p, dem_p = DEST / (f'{real}.json' if mode == 'valley' else f'{real}.{mode}.json'), DEST / f'{real}.npy'
        try:
            if meta_p.exists() and dem_p.exists():
                meta = json.loads(meta_p.read_text())
                if meta.get('finder') == FINDER_VERSION and meta.get('cam_px'):
                    return real
                if meta.get('finder') == FINDER_VERSION and not meta.get('cam_px'):
                    continue                                   # searched before: no usable view here
                h, m = np.load(dem_p), meta['m_per_px']
            elif dem_p.exists():                                # the elevation is here; only this mode's camera is new
                P = REAL[real]
                h, m = np.load(dem_p), 40075016.7 * math.cos(math.radians(P['lat'])) / (2 ** P['zoom'] * 256)
            else:
                log(f'Sky Sim: fetching the real place {real} ({REAL[real]["note"]}) once')
                h, m = fetch_dem(real)
                DEST.mkdir(parents=True, exist_ok=True)
                np.save(dem_p, h)
            level = lake_level(h, m)
            cam = find_camera(h - level, m, mode=mode)
            meta = {'place': real, 'm_per_px': m, 'size_px': int(h.shape[0]), 'size_m': h.shape[0] * m, 'min_m': float(h.min()),
                    'max_m': float(h.max()), 'level_m': level, 'note': REAL[real]['note'], 'finder': FINDER_VERSION,
                    'source': 'AWS Terrain Tiles (terrarium), open data', 'mode': mode, **(cam or {})}
            meta_p.write_text(json.dumps(meta, indent=1))
            if cam:
                log(f'Sky Sim: {real} camera {cam}')
                return real
            log(f'Sky Sim: no reference-like view found in {real}')
        except Exception as e:  # noqa: BLE001 - offline or a bad tile: try the next place, then the code-made valley
            log(f'Sky Sim: real place {real} unavailable ({e})')
    return None


if __name__ == '__main__':
    for p in sys.argv[1:] or list(REAL):
        FOR_PLACE['_cli'] = (p,)
        print(p, '->', ensure('_cli'))
