"""Python entry for the voxelmap engine (the app's Voxel Map section calls this; nothing else in the app knows the engine's insides).
    check(...)    story CSV -> errors, warnings, length and the detail-tile download it would need (nothing is downloaded)
    prepare(...)  builds the detail terrain tiles the story's camera reaches (this downloads: the caller asks the user first)
    plan(...)     story CSV (+ voice-over) -> timeline.json (+ narration timing), no rendering
    render(...)   plan -> silent video (node render.mjs on the GPU) -> mix (music bed, sound effects, voice, -14 LUFS) -> final mp4
Every call takes progress(fraction, message) and cancel() callables. Work files go to the `work` folder."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MUSIC = ROOT / "assets" / "music" / "lost_frontier.opus"   # bundled bed (Kevin MacLeod, CC BY 4.0); the story's credits_lines carry the credit


class Cancelled(Exception):
    pass


def engine_dir() -> Path:
    return HERE


def _binaries():
    if str(ROOT) not in sys.path:
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
    """Runs `node render.mjs <args>` and collects its JSON event lines: {warnings, plan, check, clip, perf, tiles}."""
    node, ffmpeg = _binaries()
    env = None
    if ffmpeg and str(ffmpeg) not in ("ffmpeg", ""):
        import os
        env = dict(os.environ)
        env["PATH"] = str(Path(str(ffmpeg)).resolve().parent) + os.pathsep + env.get("PATH", "")
    proc = _popen([node, str(HERE / "render.mjs"), *args], cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                  encoding="utf-8", errors="replace", env=env)
    err: list = []
    threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True).start()
    timer = threading.Timer(timeout_s, proc.kill)
    timer.start()
    out: dict = {"warnings": [], "error": None}
    try:
        for raw in proc.stdout:
            if cancel and cancel():
                proc.kill()
                raise Cancelled("Voxel Map cancelled.")
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            k = ev.get("event")
            if k == "progress" and progress:
                progress(span[0] + (span[1] - span[0]) * ev["frame"] / max(1, ev["total"]), f"frame {ev['frame']}/{ev['total']}")
            elif k == "warning":
                out["warnings"].append(ev.get("message"))
                log(f"[Voxel Map] {ev.get('message')}")
            elif k == "error":
                out["error"] = ev.get("message")
            elif k:
                out[k] = ev
        try:
            proc.wait(timeout=60)      # stdout is closed: the renderer is ending
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
    if cancel and cancel():
        raise Cancelled("Voxel Map cancelled.")
    if out["error"] or (proc.returncode and "check" not in out):
        raise RuntimeError(out["error"] or "".join(err)[-600:] or f"renderer exited {proc.returncode}")
    return out


def _abs(p):
    """Absolute path (the helpers run from other folders); None stays None."""
    return str(Path(p).resolve()) if p else p


def check(csv: str, *, cancel=None, log=print) -> dict:
    """{errors, warnings, duration_s, beats, detail_tiles{to_build, downloads, download_mb_est}}; never downloads."""
    r = _run_node([_abs(csv), "--check"], cancel=cancel, log=log)
    c = dict(r.get("check") or {})
    c.pop("event", None)
    c.setdefault("errors", [])
    c.setdefault("warnings", r["warnings"])
    return c


def prepare(csv: str, *, progress=None, cancel=None, log=print) -> dict:
    """Builds the detail tiles the story needs. This DOWNLOADS elevation tiles: only call it after the user agreed."""
    if progress:
        progress(0.05, "Building the detail terrain (downloads elevation tiles)…")
    r = _run_node([_abs(csv), "--prepare"], progress=None, cancel=cancel, log=log, timeout_s=3600.0)
    if progress:
        progress(1.0, "Detail terrain ready")
    return r


def _transcribe(voice: str, out: Path) -> int:
    from importlib import util
    spec = util.spec_from_file_location("vme_narration_timing", HERE / "tools" / "narration_timing.py")
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if mod.main([voice, str(out)]):
        raise RuntimeError("Could not time the voice-over.")
    return len(json.loads(out.read_text(encoding="utf-8")).get("sentences", []))


def plan(csv: str, work: str, *, voiceover: Optional[str] = None, progress: Optional[Callable] = None, cancel: Optional[Callable] = None,
         log=print) -> dict:
    """Writes <work>/timeline.json (+ vo_timing.json when a voice-over is given). Returns {duration, beats, chapters, voiceTimed, warnings}."""
    csv, voiceover = _abs(csv), _abs(voiceover)
    w = Path(_abs(work))
    w.mkdir(parents=True, exist_ok=True)
    args = [csv, "--plan", "--out", str(w)]
    timed = False
    if voiceover:
        if progress:
            progress(0.05, "Timing the voice-over…")
        n = _transcribe(voiceover, w / "vo_timing.json")
        log(f"[Voxel Map] voice-over: {n} sentences timed")
        args += ["--narration", str(w / "vo_timing.json")]
        timed = True
    if cancel and cancel():
        raise Cancelled("Voxel Map cancelled.")
    r = _run_node(args, progress=progress, cancel=cancel, log=log)
    p = r.get("plan") or {}
    if progress:
        progress(1.0, "Planned")
    return {"duration": p.get("duration"), "beats": p.get("beats"), "chapters": p.get("chapters"), "voiceTimed": timed, "warnings": r["warnings"]}


def render(csv: str, work: str, *, output: str, voiceover: Optional[str] = None, resolution: int = 720,
           progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print) -> dict:
    """The film: frames (0-90%), the mix (to 95%), the mux. Without a voice-over the video has no sound. Returns {output, perf, warnings}."""
    csv, voiceover, output = _abs(csv), _abs(voiceover), _abs(output)
    w = Path(_abs(work))
    w.mkdir(parents=True, exist_ok=True)
    tl_file = w / "timeline.json"
    if not tl_file.is_file():
        raise RuntimeError("Click Generate first: Render needs the planned film.")
    duration = float(json.loads(tl_file.read_text(encoding="utf-8"))["duration"])
    mix = None
    if voiceover:
        mix = w / "mix.wav"
        if progress:
            progress(0.02, "Mixing the sound…")
        if not MUSIC.is_file():
            raise RuntimeError("The bundled music bed is missing (assets/music/lost_frontier.opus).")
        music_file = MUSIC
        cmd = [sys.executable, str(HERE / "tools" / "mix_audio.py"), voiceover, str(music_file), str(mix), "--timeline", str(tl_file),
               "--stems", str(w / "stems")]
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(HERE / "tools"), timeout=3600)
        if p.returncode:
            raise RuntimeError("audio mix failed: " + (p.stderr or p.stdout)[-500:])
    if cancel and cancel():
        raise Cancelled("Voxel Map cancelled.")
    height = 1080 if resolution >= 1080 else 720
    width = 1920 if height == 1080 else 1280
    args = [csv, "--clip", f"0:{duration:.1f}", "--width", str(width), "--height", str(height), "--out", str(w)]
    if voiceover:
        args += ["--narration", str(w / "vo_timing.json")]
    if mix:
        args += ["--audio", str(mix)]
    r = _run_node(args, progress=progress, cancel=cancel, log=log, span=(0.05, 0.95))
    clip = (r.get("clip_av") or r.get("clip") or {}).get("file")
    if not clip or not Path(clip).is_file():
        raise RuntimeError("The renderer finished but wrote no video.")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copyfile(clip, output)
    if progress:
        progress(1.0, "Done")
    return {"output": output, "perf": r.get("perf"), "warnings": r["warnings"], "silent": not mix}
