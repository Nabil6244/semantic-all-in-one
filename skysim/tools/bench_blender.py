"""Benchmark Sky Sim's Blender settings: the same frames under each setting -> seconds per frame and picture change vs the full settings.
python -m skysim.tools.bench_blender <states.json> <out_dir>      (states.json: a list of valley.py states)
A setting is kept only when it changes the picture by less than the eye can see (PSNR >= 45 dB on every frame).
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path

from skysim.blender_runner import VALLEY, find_blender

CONFIGS = {
    'full': {},
    'samples12': {'taa_render_samples': 12},
    'samples8': {'taa_render_samples': 8},
    'vol_tile16': {'volumetric_tile_size': '16'},
    'vol_samples32': {'volumetric_samples': 32},
    'shadow_half': {'shadow_resolution_scale': 0.5},
    'shadow_steps3': {'shadow_step_count': 3},
    'rt_rough03': {'rt_trace_max_roughness': 0.3},
    'cull_trees': {'cull_trees': True},
}


def psnr(a: Path, b: Path) -> float:
    import numpy as np
    from PIL import Image
    x = np.asarray(Image.open(a).convert('RGB'), dtype=np.float64)
    y = np.asarray(Image.open(b).convert('RGB'), dtype=np.float64)
    mse = float(((x - y) ** 2).mean())
    return 99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse)


def run(states, out: Path, name: str, quality: dict, res=(1920, 1080), samples=16) -> dict:
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    q = dict(quality)
    smp = q.pop('taa_render_samples', samples)
    job = d / 'job.json'
    job.write_text(json.dumps({'out': str(d), 'res': list(res), 'samples': smp, 'quality': q, 'states': states}))
    t0 = time.time()
    p = subprocess.run([find_blender(), '-b', '--factory-startup', '-P', str(VALLEY), '--', str(job)], capture_output=True, text=True)
    total = time.time() - t0
    times = [float(ln.split()[-1].rstrip('s')) for ln in p.stdout.splitlines() if ln.startswith('rendered ')]
    if p.returncode != 0 or not times:
        raise RuntimeError(p.stdout[-800:])
    return {'per_frame': sum(times) / len(times), 'total': total, 'dir': d}


def main() -> int:
    states = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    only = sys.argv[3].split(',') if len(sys.argv) > 3 else list(CONFIGS)
    res = {}
    for name in ['full'] + [c for c in only if c != 'full']:
        cfg = CONFIGS.get(name)
        if cfg is None:                                     # a combination: a+b+c
            cfg = {}
            for part in name.split('+'):
                cfg.update(CONFIGS[part])
        r = run(states, out, name, cfg)
        if name != 'full':
            r['psnr'] = min(psnr(res['full']['dir'] / f"{s['name']}.png", r['dir'] / f"{s['name']}.png") for s in states)
        res[name] = r
        base = res['full']['per_frame']
        print(f"{name:40s} {r['per_frame']:.2f} s/frame  x{base / r['per_frame']:.2f}  setup+all {r['total']:.0f} s"
              + (f"  min PSNR {r['psnr']:.1f} dB" if 'psnr' in r else ''), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
