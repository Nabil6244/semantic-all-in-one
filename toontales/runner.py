"""Toon Tales runner for the app page (ui/toon_tales_section.py): check a story plan, paint its places, render the Short.

All heavy work runs as child processes (Flow painter in node, Blender shots, ffmpeg edit) so Stop can end them.
No Gemini: the plan is written by Claude (.claude/skills/toon-tales) and only checked/rendered here.

  check(plan)                    -> {"ok", "errors", "warnings", "title", "shots", "seconds", "places", "missing"}
  paint(plan, progress, cancel, log)                      paints the places that have no picture yet (Flow credits)
  render(plan, output, draft, progress, cancel, log)      -> {"seconds", "output"}
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TT = Path(__file__).resolve().parent
ROOT = TT.parent
FLOW = ROOT / "flow-engine"
PY = sys.executable


def _env():
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def check(plan_path):
    sys.path.insert(0, str(ROOT))
    from toontales.plan import check as C
    from toontales.plan import schema as S
    plan = S.load_plan(plan_path)
    r = C.check(plan, fix=False)
    p = r["plan"]
    places = list((plan.get("places") or {}).keys())
    missing = [n for n in places if not S.is_world(plan, n) and not S.place_image(plan, n).exists()]
    issues = r["issues"]
    return {"ok": r["ok"], "title": plan.get("title", plan.get("id")), "id": plan.get("id"),
            "errors": [f"{x['shot'] or '--'} {x['rule']}: {x['msg']}" for x in issues if x["level"] == "error"],
            "warnings": [f"{x['shot'] or '--'} {x['rule']}: {x['msg']}" for x in issues if x["level"] == "warn"],
            "shots": len(p.get("shots", [])), "seconds": p.get("est_total", 0), "places": places, "missing": missing,
            # the painted places (worlds are 3D, not pictures): the Visuals tab lists these
            "images": {n: {"path": str(S.place_image(plan, n)), "prompt": _place_prompt(plan, n)} for n in places if not S.is_world(plan, n)}}


def _place_prompt(plan, name):
    v = (plan.get("places") or {}).get(name)
    if isinstance(v, dict):
        return str(v.get("prompt") or v.get("paint") or v.get("description") or name)
    return str(v or name)


def _run(cmd, cwd, cancel, log, on_line=None, env=None):
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                            start_new_session=True)
    try:
        for ln in proc.stdout:
            if cancel and cancel():
                break
            ln = ln.rstrip()
            if on_line:
                on_line(ln)
            if ln and not ln.startswith("FRAME"):
                log and log(ln)
    finally:
        if proc.poll() is None:
            _stop(proc)
        proc.wait()
    if cancel and cancel():
        raise RuntimeError("Stopped.")
    if proc.returncode:
        raise RuntimeError(f"{Path(cmd[1]).name if len(cmd) > 1 else cmd[0]} stopped with code {proc.returncode}")


def _stop(proc):
    import os
    import signal
    try:
        os.killpg(proc.pid, signal.SIGTERM)   # its own group: Blender workers / node children end with it
    except Exception:  # noqa: BLE001
        proc.terminate()


def _flow_up():
    try:
        urllib.request.urlopen("http://127.0.0.1:8787/", timeout=2)
        return True
    except urllib.error.HTTPError:
        return True          # the server answers (404 on /): it is up
    except Exception:  # noqa: BLE001
        return False


def paint(plan_path, progress=None, cancel=None, log=None):
    """Paint the places with no picture yet. Starts the Flow server for the run if it is not up, and stops only that one."""
    started = None
    if not _flow_up():
        log and log("Starting the Flow server…")
        started = subprocess.Popen(["node", "server.js"], cwd=str(FLOW), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        for _ in range(30):
            if _flow_up():
                break
            time.sleep(1)
        else:
            _stop(started)
            raise RuntimeError("The Flow server did not start (flow-engine/server.js).")
    try:
        import os
        env = dict(os.environ, FLOW_ALLOW_REAL_CREDITS="1")
        n = {"done": 0}
        total = max(1, len(check(plan_path)["missing"]))

        def on_line(ln):
            if ln.startswith("PLACE"):
                n["done"] += 1
                progress and progress(n["done"] / total, f"painted {ln.split()[1]}")
        progress and progress(0.02, "painting the places with Flow")
        _run(["node", str(TT / "sets" / "paint_places.mjs"), str(Path(plan_path).resolve())], FLOW, cancel, log, on_line, env)
    finally:
        if started is not None:
            _stop(started)
    left = check(plan_path)["missing"]
    if left:
        raise RuntimeError(f"Flow did not paint: {', '.join(left)}. Click Generate again to retry them.")


def render(plan_path, output, draft=False, progress=None, cancel=None, log=None):
    plan = json.loads(Path(plan_path).read_text())
    n_shots = max(1, len(plan.get("shots", [])))
    st = {"done": 0}

    def on_build(ln):
        if "SHOT DONE" in ln or ln.startswith("SCREEN"):
            st["done"] += 1
            progress and progress(0.05 + 0.8 * min(1.0, st["done"] / n_shots), f"shot {st['done']}/{n_shots}")
        m = re.match(r"(\d+) shots, (\d+) to render", ln)
        if m:
            log and log(f"{m.group(2)} of {m.group(1)} shots need rendering (the rest are cached)")

    def on_edit(ln):
        if ln.startswith("SHOT"):
            progress and progress(0.88, "edit: captions, overlays, sound")

    progress and progress(0.02, "voices and shots")
    flag = ["--draft"] if draft else []
    _run([PY, "-m", "toontales.shots.build_story", str(Path(plan_path).resolve()), *flag], ROOT, cancel, log, on_build, _env())
    progress and progress(0.86, "editing")
    _run([PY, "-m", "toontales.edit.edit", str(Path(plan_path).resolve()), *flag], ROOT, cancel, log, on_edit, _env())
    made = ROOT / "out" / f"toontales_{plan['id']}{'_draft_edit' if draft else ''}.mp4"
    if not made.is_file():
        raise RuntimeError("The edit finished but no video was written.")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(made, output)
    secs = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                          str(output)], text=True).strip() or 0)
    progress and progress(1.0, "done")
    return {"seconds": secs, "output": str(output)}
