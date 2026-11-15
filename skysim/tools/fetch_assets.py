"""Fetch Sky Sim's CC0 scene assets once (Poly Haven, CC0 1.0): terrain textures and sky HDRIs, ~39 MB.
python -m skysim.tools.fetch_assets      (files land in skysim/assets/, which git ignores; re-running skips what is there)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / 'assets'
UA = {'User-Agent': 'skysim-asset-fetch'}
TEXTURES = {                       # name -> what it is used for
    'aerial_rocks_02': 'cliff and slope rock',
    'aerial_grass_rock': 'grass on the gentle slopes',
    'mud_cracked_dry_03': 'the dried lake bed, cracked ground',
    'rock_face_03': 'scanned cliff faces (real-terrain fjord)',
    'cliff_side': 'scanned steep cliff rock (real-terrain fjord)',
    'forest_ground_04': 'forest floor under the trees (real-terrain fjord)',
}
MODELS = {                         # name -> what it is used for (the .blend at 1k with its textures; decimated once by the scene)
    'fir_tree_01': 'scanned spruce/fir trees for the forest',
}
MAPS = {'Diffuse': 'diff', 'nor_gl': 'nor', 'Rough': 'rough', 'Displacement': 'disp'}
HDRIS = {
    'kloofendal_43d_clear_puresky': 'clear daylight sky',
    'qwantani_dusk_2_puresky': 'dusk sky',
}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def _save(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_bytes(_get(url))
    tmp.rename(path)
    print(f'  {path.relative_to(DEST)}  {path.stat().st_size / 1e6:.1f} MB')


def main() -> int:
    credits = ['Sky Sim scene assets, all CC0 1.0 from Poly Haven (polyhaven.com):']
    for name, use in TEXTURES.items():
        files = json.loads(_get(f'https://api.polyhaven.com/files/{name}'))
        for key, short in MAPS.items():
            if key in files:
                _save(files[key]['2k']['jpg']['url'], DEST / 'textures' / name / f'{short}.jpg')
        credits.append(f'  textures/{name}: {use}')
    for name, use in MODELS.items():
        b = json.loads(_get(f'https://api.polyhaven.com/files/{name}'))['blend']['1k']['blend']
        _save(b['url'], DEST / 'models' / name / f'{name}.blend')
        for rel, inc in (b.get('include') or {}).items():
            _save(inc['url'], DEST / 'models' / name / rel)
        credits.append(f'  models/{name}: {use}')
    for name, use in HDRIS.items():
        files = json.loads(_get(f'https://api.polyhaven.com/files/{name}'))
        _save(files['hdri']['2k']['hdr']['url'], DEST / 'hdri' / f'{name}.hdr')
        credits.append(f'  hdri/{name}.hdr: {use}')
    (DEST / 'CREDITS.txt').write_text('\n'.join(credits) + '\n')
    print(f'Sky Sim assets ready in {DEST}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
