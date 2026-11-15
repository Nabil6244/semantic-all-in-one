"""Sky Sim picture check against the competitor (docs/skysim/QUALITY.md).

python -m skysim.tools.quality_check <video.mp4 | frame.png ...>        -> per-frame numbers + what is out of range
python -m skysim.tools.quality_check --learn <competitor frames ...>    -> print new TARGETS from reference frames

The targets were measured on 97 frames from 9 Lightbound videos (2026-11-14). They describe how the competitor's picture
reads, not what it shows: dark with real blacks, a clean sky gradient, little fine detail (haze and silhouettes, not texture).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import numpy as np

# metric -> (low, high): the competitor's 20th-80th percentile (see --learn)
TARGETS: Dict[str, tuple] = {       # medians: lum 0.24, contrast 0.16, sat 0.24, sky_noise 1.46, detail 2.21, black 0.19
    'lum': (0.064, 0.417),        # mean brightness 0..1
    'contrast': (0.083, 0.227),   # brightness spread
    'sat': (0.112, 0.478),        # colour strength
    'sky_noise': (0.0, 3.018),    # roughness of the top third (clean gradient = low)
    'detail': (0.0, 4.408),       # fine pixel detail / grain over the whole frame (their subtitles included)
    'black': (0.005, 1.0),        # share of near-black pixels (silhouettes, night, space)
}
# night frames (mean brightness under 0.15) are held to the competitor's own night-lake frames (TON 618 opening,
# Night Sky Elsewhere, Smallest vs Largest): darker and flatter than the whole-video range, calmer skies, mostly black
NIGHT_TARGETS: Dict[str, tuple] = {
    'lum': (0.03, 0.13), 'contrast': (0.05, 0.12), 'sat': (0.04, 0.62), 'sky_noise': (0.0, 2.0), 'detail': (0.0, 2.2), 'black': (0.25, 0.8),
}


def measure(img) -> Dict[str, float]:
    from PIL import Image
    im = img if isinstance(img, Image.Image) else Image.open(img)
    a = np.asarray(im.convert('RGB').resize((640, 360)), dtype=np.float32) / 255
    lum = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    mx, mn = a.max(-1), a.min(-1)
    sat = np.where(mx > 0.02, (mx - mn) / np.maximum(mx, 1e-3), 0)
    top = lum[:120]
    sky = (np.abs(np.diff(top, axis=0)).mean() + np.abs(np.diff(top, axis=1)).mean()) * 100
    lap = np.abs(lum[1:-1, 1:-1] * 4 - lum[:-2, 1:-1] - lum[2:, 1:-1] - lum[1:-1, :-2] - lum[1:-1, 2:]).mean() * 100
    return {'lum': float(lum.mean()), 'contrast': float(lum.std()), 'sat': float(sat.mean()), 'sky_noise': float(sky),
            'detail': float(lap), 'black': float((lum < 0.04).mean())}


def problems(m: Dict[str, float], night_or_space: bool = None) -> List[str]:
    out = []
    for k, (lo, hi) in (NIGHT_TARGETS if m['lum'] < 0.15 else TARGETS).items():
        if k == 'black' and night_or_space is False:
            continue                                   # a bright day scene may have no blacks
        if not (lo <= m[k] <= hi):
            out.append(f'{k} {m[k]:.3f} (competitor {lo}-{hi})')
    return out


def frames_of(video: Path, n: int = 8) -> List[Path]:
    dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(video)],
                               capture_output=True, text=True).stdout.strip() or 0)
    tmp = Path(tempfile.mkdtemp(prefix='skysim_qc_'))
    outs = []
    for i in range(n):
        p = tmp / f'f{i:02d}.png'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{dur * (i + 0.5) / n:.2f}', '-i', str(video), '-frames:v', '1', str(p)])
        if p.exists():
            outs.append(p)
    return outs


def check(paths: List[str]) -> Dict[str, object]:
    files: List[Path] = []
    for p in map(Path, paths):
        files += frames_of(p) if p.suffix.lower() in ('.mp4', '.mov', '.webm') else [p]
    rows = []
    for f in files:
        m = measure(f)
        rows.append({'frame': f.name, **{k: round(v, 3) for k, v in m.items()}, 'problems': problems(m, None if m['lum'] < 0.3 else False)})
    bad = sum(1 for r in rows if r['problems'])
    return {'frames': rows, 'out_of_range': bad, 'passed': bad <= len(rows) // 4}


def learn(paths: List[str]) -> Dict[str, tuple]:
    ms = [measure(p) for p in paths]
    return {k: (round(float(np.percentile([m[k] for m in ms], 20)), 3), round(float(np.percentile([m[k] for m in ms], 80)), 3)) for k in ms[0]}


if __name__ == '__main__':
    if sys.argv[1:2] == ['--learn']:
        print(json.dumps(learn(sys.argv[2:]), indent=1))
    else:
        r = check(sys.argv[1:])
        for row in r['frames']:
            print(row['frame'], ' '.join(f'{k}={row[k]}' for k in TARGETS), '|', '; '.join(row['problems']) or 'ok')
        print('PASS' if r['passed'] else 'FAIL', f"({r['out_of_range']}/{len(r['frames'])} frames out of the competitor's range)")
