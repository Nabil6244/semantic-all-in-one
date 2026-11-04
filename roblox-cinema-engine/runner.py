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


def plan(base: str, *, csv: Optional[str] = None, text_file: Optional[str] = None, voiceover: Optional[str] = None, resolution: int = 720,
         progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print) -> dict:
    """Writes <base>.plan.json (+ .cues.json, words.json) and returns {scenes, duration, voiceTimed, warnings, plan}."""
    Path(base).parent.mkdir(parents=True, exist_ok=True)
    args = _source_args(csv, text_file) + ['--out', base + '.mp4', '--plan-only', '--final' if resolution >= 1080 else '--preview']
    if voiceover:
        words = base + '.words.json'
        if progress: progress(0.05, 'Timing the voice-over…')
        n = _tools().transcribe(voiceover, words); log(f'[Roblox Cinema] voice-over: {n} words timed')
        args += ['--words', words]
    r = _run_node(args, progress=progress, cancel=cancel, log=log)
    p = r['plan'] or {}
    return {'scenes': p.get('scenes'), 'duration': p.get('duration'), 'voiceTimed': p.get('voiceTimed'), 'warnings': r['warnings'], 'plan': base + '.mp4.plan.json'}


def render(base: str, *, csv: Optional[str] = None, text_file: Optional[str] = None, voiceover: Optional[str] = None, output: str, resolution: int = 720,
           music: bool = True, progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print) -> dict:
    """Silent video, then the audio mix muxed in. Returns {output, perf, mix}."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    silent = base + '.silent.mp4'
    args = _source_args(csv, text_file) + ['--out', silent, '--final' if resolution >= 1080 else '--preview']
    if voiceover:
        words = base + '.words.json'
        if not Path(words).is_file():
            if progress: progress(0.02, 'Timing the voice-over…')
            _tools().transcribe(voiceover, words)
        args += ['--words', words]
    if not music: args += ['--no-music']
    r = _run_node(args, progress=progress, cancel=cancel, log=log, span=(0.05, 0.9))
    if progress: progress(0.92, 'Mixing the sound…')
    cmd = [sys.executable, str(HERE / 'tools' / 'mix_audio.py'), silent, '--video', silent, '--final', output] + (['--voice', voiceover] if voiceover else []) + ([] if music else ['--no-music'])
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode: raise RuntimeError('audio mix failed: ' + (p.stderr or p.stdout)[-500:])
    mix = json.loads(Path(silent + '.mix.json').read_text()) if Path(silent + '.mix.json').is_file() else {}
    if progress: progress(1.0, 'Done')
    return {'output': output, 'perf': r['perf'], 'mix': mix, 'warnings': r['warnings']}
