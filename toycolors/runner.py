"""Toy Vehicles runner for the app page (ui/toy_vehicles_section.py): two modes, both rendered in Blender.

  Songs    a colour list -> sung colour song, one scene template per colour (toycolors/director.py)
  Stories  a story or episode file (toycolors/stories/*.json) -> narrated adventure with voices (toycolors/story.py)

  check(mode, source)                                   -> {"ok", "errors", "title", "seconds", "shots"}
  render(mode, source, output, draft, progress, cancel, log) -> {"seconds", "output"}

All heavy work runs as child processes, so Stop ends them. No Gemini: songs come from a colour list, stories from a
written script. Shots are cached (toycolors/out/shot_cache), so a re-render only makes what changed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TC = Path(__file__).resolve().parent
ROOT = TC.parent
PY = sys.executable
COLOURS = ("red", "orange", "yellow", "green", "blue")


def _env():
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def colours_of(text):
    return [c.strip().lower() for c in re.split(r"[,\s]+", text or "") if c.strip()]


def check(mode, source):
    if mode == "Songs":
        cs = colours_of(source)
        bad = [c for c in cs if c not in COLOURS]
        errors = ([f"Unknown colour(s): {', '.join(bad)}. Use: {', '.join(COLOURS)}."] if bad else []) + \
                 (["Give at least two colours."] if len(cs) < 2 else [])
        verse = 16 * 60 / 112
        return {"ok": not errors, "errors": errors, "title": "Colour song: " + ", ".join(cs),
                "seconds": round(len(cs) * verse, 1), "shots": len(cs)}
    sys.path.insert(0, str(ROOT))
    from toycolors import story as S
    errors = []
    try:
        st = S.load(source)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"Cannot read the story: {type(exc).__name__}: {exc}"], "title": "", "seconds": 0, "shots": 0}
    for i, sh in enumerate(st["shots"], 1):
        if sh.get("action") not in S.MIN_DUR:
            errors.append(f"shot {i}: unknown action {sh.get('action')!r}")
        for ln in sh.get("lines", []):
            if ln[0] not in st["voices"]:
                errors.append(f"shot {i}: no voice for {ln[0]!r}")
        for cid in sh.get("cast", {}):
            if cid not in st["cast"]:
                errors.append(f"shot {i}: {cid!r} is not in the cast")
    # ~0.4 s per word plus pauses (the zip_mud pilot: 76 s actual)
    est = sum(max(S.MIN_DUR.get(sh.get("action"), 3), 1.1 + sum(0.4 * len(ln[1].split()) + 0.3 for ln in sh.get("lines", [])))
              for sh in st["shots"])
    return {"ok": not errors, "errors": errors, "title": st["title"], "seconds": round(est, 1), "shots": len(st["shots"])}


def _run(cmd, cancel, log, on_line=None):
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_env(),
                            start_new_session=True)
    try:
        for ln in proc.stdout:
            if cancel and cancel():
                break
            ln = ln.rstrip()
            if on_line:
                on_line(ln)
            if ln:
                log and log(ln)
    finally:
        if proc.poll() is None:
            _stop(proc)
        proc.wait()
    if cancel and cancel():
        raise RuntimeError("Stopped.")
    if proc.returncode:
        raise RuntimeError(f"{' '.join(cmd[1:3])} stopped with code {proc.returncode}")


def _stop(proc):
    import os
    import signal
    try:
        os.killpg(proc.pid, signal.SIGTERM)   # its own group: the Blender child ends with it
    except Exception:  # noqa: BLE001 - Windows has no process groups
        proc.terminate()


def render(mode, source, output, draft=False, progress=None, cancel=None, log=None):
    found = {}

    def on_line(ln):
        m = re.match(r"shot (\d+)/(\d+)", ln)
        if m and progress:
            i, n = int(m.group(1)), int(m.group(2))
            progress(0.03 + 0.9 * (i - 1) / n, f"shot {i} of {n}")
        m = re.match(r"(?:video|sheet): (.+)$", ln)
        if m:
            found["mp4"] = m.group(1).strip()

    if mode == "Songs":
        cs = colours_of(source)
        out = TC / "out" / "app_songs" / "_".join(cs)
        cmd = [PY, "-m", "toycolors.director", "--colours", ",".join(cs), "--out", str(out), "--tune", "none", "--render"]
        if draft:
            cmd.append("--fast")
        progress and progress(0.02, "planning the song")
        n = len(cs)

        def song_line(ln):
            on_line(ln)
            m = re.search(r"verses[/\\]v(\d+)_", ln)
            if m and progress:
                progress(0.05 + 0.85 * int(m.group(1)) / n, f"verse {int(m.group(1)) + 1} of {n}")
        _run(cmd, cancel, log, song_line)
    else:
        name = Path(source).stem
        out = TC / "out" / "stories" / name
        cmd = [PY, "-m", "toycolors.story", str(Path(source).resolve()), "--out", str(out), "--render",
               "--quality", "720" if draft else "1080"]
        progress and progress(0.02, "voices")
        _run(cmd, cancel, log, on_line)
    mp4 = found.get("mp4")
    if not mp4 or not Path(mp4).is_file():
        raise RuntimeError("The render finished but no video was written.")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mp4, output)
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", output],
                                capture_output=True, text=True).stdout.strip() or 0)
    progress and progress(1.0, "done")
    return {"seconds": secs, "output": str(output)}
