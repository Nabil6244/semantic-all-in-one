"""Sky Sim: realistic scenes from Blender (skysim/blender/valley.py) for the planner's landscape steps.

A held landscape scene (consecutive steps with the same look and place) is rendered as ONE clip: every frame is the sky at
that moment (the same easing as whatif-engine/lib/skysim_sky.mjs skyAt) seen through the same camera move (cameraAt).
apply() then turns those steps into the What If engine's `video` shots, so the sk_* text layers draw on top as before, and
gives each shot the sky object's screen position (`_anchor`) for titles and pointers.

No Blender on this machine, or a Blender run that fails: the steps stay 2D `sky` shots (the render never stops for it).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
VALLEY = HERE / 'blender' / 'valley.py'
BLENDER_LOOKS = ('landscape',)
BLENDER_CANDIDATES = ('/Applications/Blender.app/Contents/MacOS/Blender', 'blender',
                      r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe')


def find_blender() -> Optional[str]:
    env = os.environ.get('BLENDER_BIN')
    for c in ([env] if env else []) + list(BLENDER_CANDIDATES):
        if c and (Path(c).exists() or shutil.which(c)):
            return c if Path(c).exists() else shutil.which(c)
    return None


# ---- the engine's easing, in Python ------------------------------------------------------------------------------
def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _smooth(x: float) -> float:
    k = _clamp01(x)
    return k * k * (3 - 2 * k)


def _log_lerp(a: float, b: float, k: float) -> float:
    if a and b and a > 0 and b > 0:
        return math.exp(math.log(a) + (math.log(b) - math.log(a)) * k)
    return (a or 0) + ((b or 0) - (a or 0)) * k


def sky_at(shot: Dict[str, Any], t: float) -> Dict[str, Any]:
    """lib/skysim_sky.mjs skyAt: sky_from eases into sky over the first 70 % of the step."""
    to, fr = shot.get('sky') or {}, shot.get('sky_from')
    if not fr:
        return dict(to)
    k = _smooth((t - shot['start']) / max(0.5, (shot['end'] - shot['start']) * 0.7))
    return {**to, 'angular_deg': _log_lerp(fr.get('angular_deg', 0), to.get('angular_deg', 0), k),
            'flux_x': _log_lerp(fr.get('flux_x', 0), to.get('flux_x', 0), k)}


def camera_at(shot: Dict[str, Any], t: float) -> Dict[str, float]:
    """lib/skysim_sky.mjs cameraAt."""
    k = _clamp01((t - shot['start']) / max(0.5, shot['end'] - shot['start']))
    e = _smooth(k)
    lerp = lambda a, b, x: a + (b - a) * x  # noqa: E731
    cam = shot.get('camera', 'drift')
    if cam == 'push':
        return {'scale': lerp(1, 1.14, e), 'dx': 0.0, 'dy': 0.0}
    if cam == 'pullback':
        return {'scale': lerp(1.12, 1, e), 'dx': 0.0, 'dy': 0.0}
    if cam == 'rise':
        return {'scale': 1.02, 'dx': 0.0, 'dy': lerp(0.05, -0.02, e)}
    if cam == 'orbit':
        return {'scale': 1.03, 'dx': lerp(-0.03, 0.03, e), 'dy': 0.0}
    if cam == 'static':
        return {'scale': 1.0, 'dx': 0.0, 'dy': 0.0}
    return {'scale': lerp(1, 1.045, k), 'dx': lerp(0.008, -0.008, k), 'dy': 0.0}


# ---- scenes ------------------------------------------------------------------------------------------------------
def scenes(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Consecutive Blender-look shots of the same scene -> [{scene, place, start, end, shots}]."""
    out: List[Dict[str, Any]] = []
    for s in spec.get('shots', []):
        if s.get('kind') != 'sky' or s.get('look') not in BLENDER_LOOKS:
            continue
        if out and out[-1]['scene'] == s.get('scene') and abs(out[-1]['end'] - s['start']) < 1e-6:
            out[-1]['shots'].append(s)
            out[-1]['end'] = s['end']
        else:
            out.append({'scene': s.get('scene'), 'place': s.get('place') or 'lake_valley', 'start': s['start'], 'end': s['end'], 'shots': [s]})
    return out


# ---- adaptive keyframes ------------------------------------------------------------------------------------------
# Blender renders a frame only when the picture would visibly change; the frames between are blended. The blend is invisible
# because two neighbouring keyframes are never more than MAX_SHIFT_PX of camera/object motion and MAX_LIGHT of light apart.
MAX_SHIFT_PX = 1.0           # camera or sky object movement between two keyframes, in output pixels
MAX_LIGHT = 0.02             # change of any light-ladder value (0..1) between two keyframes
MIN_GAP, MAX_GAP = 1 / 15, 0.25    # never denser than 15 fps, never sparser than 4 fps (water and haze keep moving)
FIRE_GAP = 1 / 10            # burning: the flicker needs 10 fps
LENS_PX_PER_DEG_1080 = 1920 / 84.0 * (1080 / 1080)   # valley.py: 20 mm on a 36 mm sensor = 84 degrees across


def _heat(flux: float) -> Dict[str, float]:
    """skysim/blender/valley.py heat(), the values that change the picture."""
    L = math.log10(max(flux or 0.0, 1e-30))
    raw = _smooth((L + 4.5) / 4.5)
    return {'raw': raw, 'stop': _smooth((L - 1.5) / 3), 'scorch': _smooth((L - 0.45) / 0.6), 'burn': _smooth((L - 0.85) / 0.4),
            'melt': _smooth((L - 2.4) / 2), 'evap': _smooth((L - 0.6) / 0.7), 'seen': _smooth((L + 15) / 2)}


VIEWS = ('shore', 'high', 'mirror', 'wide', 'low_left')   # skysim/blender/valley.py VIEWS
VIEW_CYCLE = ('shore', 'high', 'mirror', 'wide', 'low_left')
VIEW_GLIDE_S = 4.0                          # a new view glides in over this long (or 60 % of a shorter step)


def views_for(shots: List[Dict[str, Any]]) -> List[str]:
    """One view per step. The reference changes the angle every rung, so a step that would repeat the step before it (or names
    no view) takes the next view in VIEW_CYCLE; camera 'hold' keeps the previous view on purpose."""
    out: List[str] = []
    for i, s in enumerate(shots):
        cam = s.get('camera')
        if cam == 'hold' and out:
            out.append(out[-1]); continue
        v = cam if cam in VIEWS else (VIEW_CYCLE[i % len(VIEW_CYCLE)] if i else 'shore')
        if out and v == out[-1]:
            v = VIEW_CYCLE[(VIEW_CYCLE.index(v) + 1) % len(VIEW_CYCLE)]
        out.append(v)
    return out


def view_of(shot: Dict[str, Any], group: Optional[Dict[str, Any]] = None) -> str:
    if group:
        return views_for(group['shots'])[group['shots'].index(shot)]
    return shot.get('camera') if shot.get('camera') in VIEWS else 'shore'


def _state(group: Dict[str, Any], t: float) -> Dict[str, Any]:
    i = next((k for k, s in enumerate(group['shots']) if s['start'] <= t < s['end']), len(group['shots']) - 1)
    shot = group['shots'][i]
    sky = sky_at(shot, t)
    cam = camera_at(shot, t)
    vs = group.get('_views') or views_for(group['shots'])
    view, before = vs[i], vs[i - 1] if i else vs[i]
    glide = min(VIEW_GLIDE_S, 0.6 * (shot['end'] - shot['start']))
    cam.update(view=view, view_from=before, view_k=round(_smooth((t - shot['start']) / glide), 5) if before != view else 1.0)
    return {'t': round(t, 4), 'flux_x': sky.get('flux_x', 0.0), 'angular_deg': sky.get('angular_deg', 0.0), 'kind': sky.get('kind', 'star'),
            'object': sky.get('object', ''), 'cam': cam}


def _shift_px(a: Dict[str, Any], b: Dict[str, Any], W: int) -> float:
    """How far the picture moves between two states, in output pixels (the largest of camera zoom, pan, tilt and object size)."""
    ca, cb = a['cam'], b['cam']
    zoom = abs(cb['scale'] - ca['scale']) / max(ca['scale'], 1e-6) * W / 2
    pan = abs(cb['dx'] - ca['dx']) * 300 / 1450 * W            # valley.py moves the camera 300 m per unit, ~1.4 km from the far end
    tilt = abs(cb['dy'] - ca['dy']) * 0.3 / math.radians(53.7) * W * 9 / 16
    px_deg = LENS_PX_PER_DEG_1080 * W / 1920
    size = abs(b['angular_deg'] - a['angular_deg']) * px_deg / 2 * 80    # the accretion disc reaches 80 horizon radii
    glide = 0.0 if (ca.get('view'), ca.get('view_from')) != (cb.get('view'), cb.get('view_from')) and ca.get('view') != cb.get('view') \
        else abs(cb.get('view_k', 1) - ca.get('view_k', 1)) * W * 0.6          # a view glide moves the whole picture
    if ca.get('view') != cb.get('view'):
        glide = W
    return max(zoom, pan, tilt, size, glide)


def keyframe_times(group: Dict[str, Any], fps: int = 30, W: int = 1920) -> List[float]:
    """The moments Blender must render for this scene; every output frame lies between two of them."""
    n = max(1, int(math.ceil((group['end'] - group['start']) * fps)))
    ts = [group['start'] + i / fps for i in range(n + 1)]
    keys = [ts[0]]
    key = _state(group, ts[0]); kh = _heat(key['flux_x'])
    prev_t = ts[0]
    for t in ts[1:]:
        st = _state(group, t); h = _heat(st['flux_x'])
        gap = t - keys[-1]
        limit = FIRE_GAP if max(h['burn'], kh['burn']) * (1 - h['melt']) > 0.05 else MAX_GAP
        light = max(abs(h[k] - kh[k]) for k in h)
        if gap >= limit - 1e-9 or (gap >= MIN_GAP - 1e-9 and (light > MAX_LIGHT or _shift_px(key, st, W) > MAX_SHIFT_PX)):
            keys.append(t if gap <= limit + 1e-9 else prev_t)
            key = _state(group, keys[-1]); kh = _heat(key['flux_x'])
        prev_t = t
    if keys[-1] < ts[-1] - 1e-9:
        keys.append(ts[-1])
    return keys


def frame_states(group: Dict[str, Any], render_fps: float = 0, fps: int = 30, W: int = 1920) -> List[Dict[str, Any]]:
    """Blender states for a scene: adaptive keyframes (render_fps 0), or a fixed rate when render_fps is given."""
    if render_fps:
        n = max(1, int(math.ceil((group['end'] - group['start']) * render_fps)) + 1)
        times = [group['start'] + i / render_fps for i in range(n)]
    else:
        times = keyframe_times(group, fps, W)
    return [{'name': f'k{int(round((t - group["start"]) * 1000)):07d}', **_state(group, t)} for t in times]


def _blend_to_video(states: List[Dict[str, Any]], fdir: Path, start: float, end: float, fps: int, mp4: Path) -> None:
    """Keyframe PNGs -> a constant-fps clip: each output frame is the mix of the two keyframes around it."""
    import numpy as np
    from PIL import Image

    keys = [(s['t'], fdir / f"{s['name']}.png") for s in states]
    first = Image.open(keys[0][1]); W, H = first.size
    enc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(fps),
                            '-i', '-', '-c:v', 'libx264', '-crf', '15', '-preset', 'medium', '-pix_fmt', 'yuv420p', str(mp4)], stdin=subprocess.PIPE)
    cache: Dict[int, Any] = {}

    def img(i):
        if i not in cache:
            if len(cache) > 3:
                cache.pop(min(cache))
            cache[i] = np.asarray(Image.open(keys[i][1]).convert('RGB'), dtype=np.float32)
        return cache[i]

    j = 0
    for f in range(int(round((end - start) * fps))):
        t = start + f / fps
        while j + 1 < len(keys) - 1 and keys[j + 1][0] <= t:
            j += 1
        t0, t1 = keys[j][0], keys[min(j + 1, len(keys) - 1)][0]
        k = 0.0 if t1 <= t0 else min(1.0, max(0.0, (t - t0) / (t1 - t0)))
        a = img(j)
        out = a if k < 1e-3 else (a * (1 - k) + img(j + 1) * k) if k < 0.999 else img(j + 1)
        enc.stdin.write(np.clip(out + 0.5, 0, 255).astype(np.uint8).tobytes())  # type: ignore[union-attr]
    enc.stdin.close()  # type: ignore[union-attr]
    if enc.wait() != 0:
        raise RuntimeError('encoding the scene clip failed')


def _run_blender(blender: str, jobs: List[Path], log: Callable[[str], None], label: str, total: int, timeout: float) -> None:
    """Run one Blender per job at the same time (each renders its share of the keyframes)."""
    procs = [subprocess.Popen([blender, '-b', '--factory-startup', '-P', str(VALLEY), '--', str(j)], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True) for j in jobs]
    import threading
    done = [0]
    tails: List[List[str]] = [[] for _ in procs]
    lock = threading.Lock()

    def pump(i, p):
        for line in p.stdout:
            tails[i] = (tails[i] + [line.rstrip()])[-30:]
            if line.startswith('rendered '):
                with lock:
                    done[0] += 1
                    if done[0] % 25 == 0 or done[0] == total:
                        log(f'{label}: {done[0]}/{total} keyframes')

    threads = [threading.Thread(target=pump, args=(i, p), daemon=True) for i, p in enumerate(procs)]
    for th in threads:
        th.start()
    bad = [i for i, p in enumerate(procs) if p.wait(timeout=timeout) != 0]
    for th in threads:
        th.join(timeout=5)
    if bad:
        raise RuntimeError(f'Blender failed on {label}: ' + ' | '.join(tails[bad[0]][-6:]))


# Blender settings benchmarked as invisible (skysim/tools/bench_blender.py, 2026-11-14: each >= 45 dB PSNR on every frame;
# 8 samples and half-resolution shadows were visible and are not used). Together ~1.5x faster per frame.
SAFE_QUALITY = {'volumetric_tile_size': '16', 'volumetric_samples': 32, 'rt_trace_max_roughness': 0.3, 'cull_trees': True}


def render_scene(group: Dict[str, Any], work: Path, *, res=(1920, 1080), fps: int = 30, render_fps: float = 0, samples: int = 12,
                 trees: int = 70000, workers: int = 2, quality: Optional[Dict[str, Any]] = None, blender: Optional[str] = None,
                 log: Callable[[str], None] = print, timeout: float = 6 * 3600) -> Dict[str, Any]:
    """Blender keyframes for one held scene (in `workers` parallel Blenders) -> <work>/<scene>.mp4 at `fps`."""
    blender = blender or find_blender()
    if not blender:
        raise RuntimeError('Blender not found (set BLENDER_BIN)')
    fdir = work / f"{group['scene']}_frames"
    fdir.mkdir(parents=True, exist_ok=True)
    states = frame_states(group, render_fps, fps, res[0])
    todo = [s for s in states if not (fdir / f"{s['name']}.png").exists()]           # a stopped run resumes where it was
    log(f"{group['scene']}: {len(states)} keyframes for {round((group['end'] - group['start']) * fps)} frames"
        + (f", {len(todo)} to render in {min(workers, len(todo))} Blenders" if todo else ', all rendered already'))
    if todo:
        n = max(1, min(workers, len(todo)))
        jobs = []
        for w in range(n):
            share = todo[w::n]
            jp = work / f"{group['scene']}_job{w}.json"
            jp.write_text(json.dumps({'out': str(fdir), 'res': list(res), 'samples': samples, 'place': group['place'], 'trees': trees,
                                      'quality': SAFE_QUALITY if quality is None else quality, 'anchors_file': f'anchors_{w}.json', 'states': share}))
            jobs.append(jp)
        _run_blender(blender, jobs, log, group['scene'], len(todo), timeout)
    anchors: Dict[str, Any] = {}
    for af in sorted(fdir.glob('anchors*.json')):
        anchors.update(json.loads(af.read_text()))
    mp4 = work / f"{group['scene']}.mp4"
    _blend_to_video(states, fdir, group['start'], group['end'], fps, mp4)
    return {'file': mp4, 'anchors': anchors, 'states': states}


def apply(spec: Dict[str, Any], media_dir: Path, **kw) -> List[str]:
    """Render every Blender-look scene and swap its steps for video shots. -> notes (what was rendered or left 2D)."""
    notes: List[str] = []
    groups = scenes(spec)
    if not groups:
        return notes
    blender = kw.pop('blender', None) or find_blender()
    if not blender:
        return ['Blender not found: landscape steps drawn by the 2D look']
    media_dir.mkdir(parents=True, exist_ok=True)
    W, H = spec.get('width', 1920), spec.get('height', 1080)
    for g in groups:
        try:
            r = render_scene(g, media_dir, res=(W, H), fps=spec.get('fps', 30), blender=blender, **kw)
        except Exception as e:  # noqa: BLE001 - one scene that will not render stays 2D; the video still finishes
            notes.append(f"{g['scene']}: {e}; drawn by the 2D look")
            continue
        for s in g['shots']:
            t_mid = s['start'] + 0.7 * (s['end'] - s['start'])
            near = min(r['states'], key=lambda x: abs(x['t'] - t_mid))
            a = r['anchors'].get(near['name'])
            s.update(kind='video', file=r['file'].name, in_s=round(s['start'] - g['start'], 3), drift={'from': 1.0, 'to': 1.0})
            if a:
                s['_anchor'] = {'x': a['x'] * W, 'y': a['y'] * H, 'r': a['r'] * W}
        notes.append(f"{g['scene']}: {len(g['shots'])} steps rendered in Blender ({r['file'].name})")
    return notes
