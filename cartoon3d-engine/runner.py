"""Python entry for Kids Learn lessons (ui/kids_learn_section.py calls this; nothing else in the app knows the engine's insides).
    plan(...)   lesson CSV -> voice lines + plan json (the free Edge voice is spoken here), no rendering
    render(...) the same lesson -> frames on the GPU -> voice, music and sound effects (kids_audio) -> final mp4
Both take progress(fraction, message), cancel() and log(message). Voice lines are cached in `work`, so Render reuses Generate's voice."""
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


def _node() -> str:
    sys.path.insert(0, str(ROOT))
    from map_scene.render import _node as find
    return find()


def _popen(cmd, **kw):
    try:
        from providers import hidden_subprocess as hs
        return hs.popen(cmd, **kw)
    except Exception:
        return subprocess.Popen(cmd, **kw)


def host_ready() -> bool:
    return (HERE / "assets" / "host" / "host.glb").is_file()


def args(csv: str, *, out: str, work: str, plan_file: str, host: str = "host3d", world: str = "playroom", music: str = "auto",
         sfx: bool = True, voice: str = "en-US-JennyNeural", resolution: int = 720, plan_only: bool = False, voiceover: str = "") -> list:
    w, h = (1920, 1080) if resolution >= 1080 else (1280, 720)
    a = [str(HERE / "lesson.mjs"), "--csv", os.path.abspath(csv), "--out", os.path.abspath(out), "--work", os.path.abspath(work),
         "--plan-file", os.path.abspath(plan_file), "--host", host, "--world", world, "--music", music, "--sfx", "on" if sfx else "off",
         "--voice", voice, "--w", str(w), "--h", str(h)]
    if voiceover:                                        # your recording: the lesson follows it and Edge is not used
        a += ["--voiceover", os.path.abspath(voiceover)]
    return a + (["--plan-only"] if plan_only else [])


def _run(a: list, *, progress=None, cancel=None, log=print, span=(0.0, 1.0), timeout_s: float = 3 * 3600.0) -> dict:
    env = dict(os.environ, LESSON_PYTHON=sys.executable if not getattr(sys, "frozen", False) else os.environ.get("LESSON_PYTHON", "python3"))
    proc = _popen([_node(), *a], cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env)
    err: list = []
    threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True).start()
    timer = threading.Timer(timeout_s, proc.kill); timer.start()
    out = {"warnings": [], "plan": None, "audio": None, "done": None, "voiceover": None, "error": None}
    try:
        for raw in proc.stdout:
            if cancel and cancel():
                proc.kill(); raise Cancelled("Kids Learn stopped.")
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            k = ev.get("event")
            if k == "progress" and progress:
                progress(span[0] + (span[1] - span[0]) * ev["frame"] / max(1, ev["total"]), f"frame {ev['frame']}/{ev['total']}")
            elif k == "warning":
                out["warnings"].append(ev.get("message")); log(f"[KIDS LEARN] {ev.get('message')}")
            elif k in ("plan", "audio", "done", "voiceover"):
                out[k] = ev
            elif k == "error":
                out["error"] = ev.get("message")
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
    if cancel and cancel():
        raise Cancelled("Kids Learn stopped.")
    if out["error"] or proc.returncode:
        raise RuntimeError((out["error"] or "".join(err)[-600:] or f"lesson renderer exited {proc.returncode}").strip().splitlines()[0][:400])
    return out


def plan(csv: str, work: str, *, progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print, **opt) -> dict:
    """Speak the lines and plan the lesson. Returns {duration, lines, props, cards, warnings, plan_file}."""
    if not os.path.isfile(csv):
        raise FileNotFoundError(f"The lesson CSV is not there: {csv}")
    os.makedirs(work, exist_ok=True); pf = os.path.join(work, "lesson.plan.json")
    if progress:
        progress(0.1, "Timing your voice-over…" if opt.get("voiceover") else "Speaking the lines…")
    r = _run(args(csv, out=os.path.join(work, "lesson.mp4"), work=os.path.join(work, "voice_cache"), plan_file=pf, plan_only=True, **opt), cancel=cancel, log=log)
    p = r["plan"] or {}
    if progress:
        progress(1.0, "Planned")
    return {"duration": p.get("duration", 0), "lines": p.get("lines", 0), "props": p.get("props", 0), "cards": p.get("cards", 0), "warnings": r["warnings"], "plan_file": pf,
            "voiceover": r["voiceover"]}


def render(csv: str, work: str, output: str, *, progress: Optional[Callable] = None, cancel: Optional[Callable] = None, log=print, **opt) -> dict:
    """Render the lesson to `output`. Returns {output, frames, wall_s, audio}."""
    os.makedirs(work, exist_ok=True)
    r = _run(args(csv, out=output, work=os.path.join(work, "voice_cache"), plan_file=os.path.join(work, "lesson.plan.json"), **opt),
             progress=progress, cancel=cancel, log=log, span=(0.02, 0.97))
    if not os.path.isfile(output):
        raise RuntimeError("The lesson finished, but no video was written.")
    d = r["done"] or {}
    if progress:
        progress(1.0, "Done")
    return {"output": output, "frames": d.get("frames"), "wall_s": d.get("wall_s"), "audio": r["audio"], "errors": d.get("errors") or []}
