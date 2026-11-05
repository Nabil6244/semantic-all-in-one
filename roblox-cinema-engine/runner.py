"""Python entry for the Roblox Cinema engine (the app's section calls this; nothing else in the app knows the engine's insides).
    plan(...)   story CSV (+ voice-over) -> plan json + summary, no rendering
    render(...) plan -> silent video (node render.mjs on the GPU) -> mix (ambience, event sounds, music, voice, -14 LUFS) -> final mp4
Both take progress(fraction, message) and cancel() callables. Output files are named from `base` (a path without extension)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class Cancelled(Exception):
    pass


def engine_dir() -> Path:
    return HERE


def _tools():
    from importlib import util
    spec = util.spec_from_file_location('rce_narration_timing', HERE / 'tools' / 'narration_timing.py')
    mod = util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def _binaries():
    sys.path.insert(0, str(ROOT))
    from map_scene.render import _ffmpeg, _node
    return _node(), _ffmpeg()


def _popen(cmd, **kw):
    try:
        from providers import hidden_subprocess as hs
        return hs.popen(cmd, **kw)
    except Exception:
        return subprocess.Popen(cmd, **kw)


def _run_node(args: list, *, progress=None, cancel=None, log=print, span=(0.0, 1.0), timeout_s: float = 6 * 3600.0) -> dict:
    node, _ = _binaries()
    proc = _popen([node, str(HERE / 'render.mjs'), *args], cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    err: list = []
    threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True).start()
    timer = threading.Timer(timeout_s, proc.kill); timer.start()
    out = {'warnings': [], 'done': None, 'error': None, 'perf': None, 'plan': None}
    try:
        for raw in proc.stdout:
            if cancel and cancel():
                proc.kill(); raise Cancelled('Roblox Cinema render cancelled.')
            try: ev = json.loads(raw)
            except ValueError: continue
            k = ev.get('event')
            if k == 'progress' and progress: progress(span[0] + (span[1] - span[0]) * ev['frame'] / max(1, ev['total']), f"frame {ev['frame']}/{ev['total']} ({ev.get('scene', '')})")
            elif k == 'warning': out['warnings'].append(ev.get('message')); log(f"[Roblox Cinema] {ev.get('message')}")
            elif k in ('done', 'error', 'perf', 'plan'): out['error' if k == 'error' else k] = ev.get('message') if k == 'error' else ev
        try:
            proc.wait(timeout=60)      # stdout is closed: the renderer is ending
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        timer.cancel()
        if proc.poll() is None: proc.kill()
    if out['error'] or proc.returncode:
        raise RuntimeError(out['error'] or ''.join(err)[-600:] or f'renderer exited {proc.returncode}')
    return out


def _source_args(csv: Optional[str], text: Optional[str]) -> list:
    if csv: return ['--csv', os.path.abspath(csv)]
    if text: return ['--text', text]
    raise ValueError('Choose a story CSV or paste the narration first.')


def _voice_sig(voiceover: str) -> list:
    st = os.stat(voiceover)
    return [os.path.abspath(voiceover), st.st_size, st.st_mtime_ns, 'base']      # path, size, saved time, whisper model


def _voice_words(voiceover: str, words: str, progress=None, log=print) -> int:
    """Word times for the voice-over. Transcribing a long voice takes minutes, so the saved times are reused while the voice file
    (path, size, saved time) is exactly the one they were made from."""
    sig_file = words + '.sig'
    try:
        if os.path.isfile(words) and os.path.isfile(sig_file) and json.load(open(sig_file)) == _voice_sig(voiceover):
            n = len(json.load(open(words)).get('words', []))
            if n:
                log(f'[Roblox Cinema] voice-over: {n} words timed (saved timing reused, the voice file is unchanged)')
                return n
    except Exception:
        pass
    if progress: progress(0.05, 'Timing the voice-over…')
    n = _tools().transcribe(voiceover, words)
    try: json.dump(_voice_sig(voiceover), open(sig_file, 'w'))
    except Exception: pass
    log(f'[Roblox Cinema] voice-over: {n} words timed')
    return n


def plan(base: str, *, csv: Optional[str] = None, text_file: Optional[str] = None, voiceover: Optional[str] = None, resolution: int = 720,
         progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print) -> dict:
    """Writes <base>.plan.json (+ .cues.json, words.json) and returns {scenes, duration, voiceTimed, warnings, plan}."""
    Path(base).parent.mkdir(parents=True, exist_ok=True)
    args = _source_args(csv, text_file) + ['--out', base + '.mp4', '--plan-only', '--final' if resolution >= 1080 else '--preview']
    if voiceover:
        words = base + '.words.json'
        n = _voice_words(voiceover, words, progress, log)
        args += ['--words', words]
    r = _run_node(args, progress=progress, cancel=cancel, log=log)
    p = r['plan'] or {}
    return {'scenes': p.get('scenes'), 'duration': p.get('duration'), 'voiceTimed': p.get('voiceTimed'), 'warnings': r['warnings'], 'plan': base + '.mp4.plan.json'}


MIN_PARALLEL_FRAMES = 1200          # below ~50 s of film the start-up cost of extra browsers is not worth it


def auto_workers() -> int:
    """3 on a machine with 8+ cores, 2 on 4-7, else 1. (Measured on an M2: 2 browsers ~1.8x, 3-4 ~2x of one.)"""
    c = os.cpu_count() or 1
    return 3 if c >= 8 else 2 if c >= 4 else 1


def _render_parallel(args: list, silent: str, n: int, *, progress=None, cancel=None, log=print):
    """Renders the frames in `n` contiguous ranges at once, each into its own part with the SAME encoder settings, then joins the parts
    with a stream copy (no re-encode: nothing is recompressed). Returns the first part's result, or None when the film is too short
    (the caller then renders it in one piece). Every frame depends only on its own time, so the frames are the ones a single run draws."""
    plan_args = [a for a in args]
    i = plan_args.index('--out'); plan_args[i + 1] = silent
    r0 = _run_node(plan_args + ['--plan-only'], progress=None, cancel=cancel, log=log)        # writes silent.plan.json / .cues.json (the mix needs them)
    p = r0.get('plan') or {}
    fps = 24
    try: fps = int(json.load(open(silent + '.plan.json')).get('fps', 24))
    except Exception: pass
    total = int(-(-float(p.get('duration', 0)) * fps // 1))
    if total < MIN_PARALLEL_FRAMES: return None
    n = min(n, max(1, total // 600))
    if n < 2: return None
    cuts = [round(total * k / n) for k in range(n + 1)]
    parts = [f'{silent}.part{k}.mp4' for k in range(n)]
    frac = [0.0] * n; failed = threading.Event(); results = [None] * n; errors = []
    lock = threading.Lock()

    def report(k):
        def cb(f, msg=''):
            with lock:
                frac[k] = f
                if progress: progress(0.05 + 0.85 * sum(frac) / n, f'{n} renderers, {int(100 * sum(frac) / n)}% of the frames')
        return cb

    def work(k):
        a = list(args); j = a.index('--out'); a[j + 1] = parts[k]
        try:
            results[k] = _run_node(a + ['--range', f'{cuts[k]},{cuts[k + 1]}'], progress=report(k), cancel=lambda: (cancel and cancel()) or failed.is_set(), log=log)
        except BaseException as e:      # noqa: BLE001 - reported below, and the other renderers are told to stop
            errors.append(e); failed.set()

    log(f'[Roblox Cinema] rendering {total} frames in {n} parts at once')
    threads = [threading.Thread(target=work, args=(k,), daemon=True) for k in range(n)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=6 * 3600.0 + 120)      # each renderer is killed at 6 h (_run_node), so this only guards a stuck thread
    if any(t.is_alive() for t in threads):
        failed.set(); errors.append(RuntimeError('Roblox Cinema: a renderer did not finish within 6 hours.'))
    if errors:
        for q in parts:
            try: os.remove(q)
            except OSError: pass
        raise next((e for e in errors if not isinstance(e, Cancelled)), errors[0])
    lst = silent + '.parts.txt'
    open(lst, 'w').write(''.join(f"file '{os.path.abspath(q)}'\n" for q in parts))
    _, ffmpeg = _binaries()
    r = subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', '-movflags', '+faststart', silent], capture_output=True, text=True, timeout=1800)
    if r.returncode: raise RuntimeError('joining the parts failed: ' + (r.stderr or '')[-400:])
    import glob
    for q in parts + [lst] + glob.glob(glob.escape(silent) + '.part*'):
        try: os.remove(q)
        except OSError: pass
    perf = results[0].get('perf') or {}
    perf = {**perf, 'frames': total, 'parallel_parts': n}
    return {**results[0], 'perf': perf, 'warnings': [w for r_ in results for w in r_['warnings']]}


def render(base: str, *, csv: Optional[str] = None, text_file: Optional[str] = None, voiceover: Optional[str] = None, output: str, resolution: int = 720,
           music: bool = True, progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print, workers: Optional[int] = None) -> dict:
    """Silent video, then the audio mix muxed in. Returns {output, perf, mix}. `workers` > 1 renders the film in that many frame ranges at once
    (same frames, same encoder settings, joined without re-encoding); None = automatic."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    silent = base + '.silent.mp4'
    args = _source_args(csv, text_file) + ['--out', silent, '--final' if resolution >= 1080 else '--preview']
    if voiceover:
        words = base + '.words.json'
        _voice_words(voiceover, words, progress, log)
        args += ['--words', words]
    if not music: args += ['--no-music']
    n = auto_workers() if workers is None else max(1, int(workers))
    r = _render_parallel(args, silent, n, progress=progress, cancel=cancel, log=log) if n > 1 else None
    if r is None:
        r = _run_node(args, progress=progress, cancel=cancel, log=log, span=(0.05, 0.9))
    if progress: progress(0.92, 'Mixing the sound…')
    cmd = [sys.executable, str(HERE / 'tools' / 'mix_audio.py'), silent, '--video', silent, '--final', output] + (['--voice', voiceover] if voiceover else []) + ([] if music else ['--no-music'])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode: raise RuntimeError('audio mix failed: ' + (p.stderr or p.stdout)[-500:])
    mix = json.loads(Path(silent + '.mix.json').read_text()) if Path(silent + '.mix.json').is_file() else {}
    if progress: progress(1.0, 'Done')
    return {'output': output, 'perf': r['perf'], 'mix': mix, 'warnings': r['warnings']}
