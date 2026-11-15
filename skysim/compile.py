"""Sky Sim: planner spec -> the What If engine's spec (whatif-engine renders shot kind `sky` and the sk_* layers).

compile_spec() only reshapes; stills() and render() run whatif-engine/render.mjs (stills = a few JPEG frames, no video).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / 'whatif-engine'
# the held scene is the picture: no colour grade, a light vignette, almost no grain
LOOK = {'saturate': 1.0, 'contrast': 1.0, 'lift': None, 'vignette': 0.22, 'grain': 0.015}
FADES = {'sk_subtitle': (0.15, 0.2), 'sk_title': (0.6, 0.6), 'sk_stats': (0.4, 0.35), 'sk_readout': (0.4, 0.35),
         'sk_clocks': (0.4, 0.35), 'sk_rungcard': (0.5, 0.8), 'sk_scalering': (0.5, 0.4), 'sk_leader': (0.4, 0.4)}


def compile_spec(plan: Dict[str, Any], output: str | Path, log=print) -> Dict[str, Any]:
    shots: List[Dict[str, Any]] = []
    ridges_by_place: Dict[str, Any] = {}
    for s in plan.get('shots', []):
        s = dict(s)
        if s.get('look') == 'lake' and not s.get('ridges'):       # real mountain silhouettes (skysim/ridges.py), once per place
            from . import ridges
            place = s.get('place') or 'lake'
            if place not in ridges_by_place:
                ridges_by_place[place] = ridges.load(place, log=log)
            if ridges_by_place[place]:
                s['ridges'] = {'az_deg': ridges_by_place[place]['az_deg'], 'layers': ridges_by_place[place]['layers']}
        if s.get('enter') == 'fade' and s.get('fade_s'):
            s['dissolve_in'] = s['fade_s']          # whatif-engine page.js: a real cross-dissolve into this shot
            s['dissolve_style'] = 'fade'
        shots.append(s)
    layers = []
    for L in plan.get('layers', []):
        L = dict(L)
        fi, fo = FADES.get(L['type'], (0.4, 0.4))
        L.setdefault('fade_in', fi)
        L.setdefault('fade_out', fo)
        layers.append(L)
    return {'width': plan.get('width', 1920), 'height': plan.get('height', 1080), 'fps': plan.get('fps', 30),
            'duration': plan['duration'], 'style': 'skysim', 'title': plan.get('title', ''), 'look': dict(LOOK),
            'shots': shots, 'layers': layers, 'output': str(output)}


def _node() -> str:
    return os.environ.get('NODE_BIN') or 'node'


def write_spec(spec: Dict[str, Any], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spec, indent=1))
    return p


def stills(spec: Dict[str, Any], spec_path: str | Path, times: Iterable[float], timeout: float = 600) -> List[Path]:
    """Render just these moments as JPEGs next to spec['output'] (<output>.t<time>.jpg)."""
    times = [round(float(t), 2) for t in times]
    p = write_spec(spec, spec_path)
    env = {**os.environ, 'WHATIF_STILLS': ','.join(str(t) for t in times)}
    proc = subprocess.run([_node(), str(ENGINE / 'render.mjs'), str(p)], cwd=ENGINE, env=env, capture_output=True, text=True, timeout=timeout)
    events = [json.loads(ln) for ln in proc.stdout.splitlines() if ln.startswith('{')]
    errors = [e for e in events if e.get('event') in ('error', 'warning')]
    if proc.returncode != 0 or any(e.get('event') == 'error' for e in errors):
        raise RuntimeError(f'stills failed: {errors or proc.stderr[-800:]}')
    for e in errors:
        print('warning:', e.get('message'))
    return [Path(f"{spec['output']}.t{t}.jpg") for t in times]


def render(plan: Dict[str, Any], out_mp4: str | Path, work: str | Path, *, audio: str | Path | None = None, use_blender: bool = True,
           log=print, timeout: float = 8 * 3600, **blender_kw) -> Dict[str, Any]:
    """The whole video: Blender clips for the realistic looks, the What If engine for the rest and every sk_* layer, then the voice.
    -> {'path', 'notes'}"""
    from . import blender_runner

    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    out_mp4 = Path(out_mp4)
    picture = work / 'picture.mp4'
    spec = compile_spec(plan, picture)
    media = work / 'media'
    spec['media_dir'] = str(media)
    notes = blender_runner.apply(spec, media, log=log, **blender_kw) if use_blender else []
    for n in notes:
        log(n)
    sp = write_spec(spec, work / 'spec.json')
    proc = subprocess.Popen([_node(), str(ENGINE / 'render.mjs'), str(sp), str(picture)], cwd=ENGINE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    last = 0
    tail: List[str] = []
    for line in proc.stdout:  # type: ignore[union-attr]
        tail = (tail + [line.rstrip()])[-20:]
        if line.startswith('{'):
            ev = json.loads(line)
            if ev.get('event') == 'progress' and ev['frame'] - last >= 300:
                last = ev['frame']
                log(f"engine: frame {ev['frame']}/{ev['total']}")
            elif ev.get('event') in ('warning', 'error'):
                log(f"engine {ev['event']}: {ev.get('message')}")
    if proc.wait(timeout=timeout) != 0 or not picture.exists():
        raise RuntimeError('engine render failed: ' + ' | '.join(tail[-5:]))
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    if audio:
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(picture), '-i', str(audio), '-map', '0:v', '-map', '1:a',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', str(out_mp4)], check=True)
    else:
        shutil.copyfile(picture, out_mp4)
    return {'path': out_mp4, 'notes': notes}
