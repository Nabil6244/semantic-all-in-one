"""The app's Kids Stories page runs a .kidstory file (kidstory.py) through the 2D cartoon engine.

generate(story_file, work)  unpack -> voice every line (free Edge voices) -> storycheck (the story rules).
                            Returns the length and the checker's result; nothing is drawn yet.
render(work, out)           draw the video in pieces side by side (one process each: the installed app has no child
                            Python, so each piece is the app itself with --run-script, see script_runner.command),
                            join the pieces, mix music + sounds under the voices, mux -> out.

Every step is its own process, so Stop kills it at once. No Gemini, no Flow: the story file carries everything.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

C2D = Path(__file__).resolve().parent
ROOT = C2D.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(C2D))
import kidstory  # noqa: E402
import script_runner  # noqa: E402


class Stopped(Exception):
    pass


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _popen(script, args):
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {"start_new_session": True}
    return subprocess.Popen(script_runner.command(C2D / script, args), cwd=str(ROOT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=_env(), bufsize=1, **kw)


def _run(script, args, cancel=None, log=None, on_line=None):
    """One step in its own process; its lines go to the log. Raises on failure (with the last lines) or on Stop."""
    p = _popen(script, args)
    tail = []
    try:
        for ln in p.stdout:
            if cancel and cancel():
                raise Stopped()
            ln = ln.rstrip()
            if not ln:
                continue
            tail = (tail + [ln])[-12:]
            if on_line:
                on_line(ln)
            elif log:
                log(ln)
        p.wait()
    finally:
        if p.poll() is None:
            p.kill()
    if cancel and cancel():
        raise Stopped()
    if p.returncode != 0:
        raise RuntimeError(f"{script} failed:\n" + "\n".join(tail[-8:]))
    return tail


def check(story_file):
    return kidstory.check(story_file)


def generate(story_file, work, progress=None, cancel=None, log=None):
    c = kidstory.check(story_file)
    if c["errors"]:
        raise ValueError("Not ready:\n" + "\n".join(c["errors"][:8]))
    work = Path(work)
    if work.exists():
        for old in (work / "bg", work / "build" / "pieces"):
            shutil.rmtree(old, ignore_errors=True)       # the voice cache in build/audio/cache is kept: edits re-voice only what changed
    rp = kidstory.unpack(story_file, work)
    progress and progress(0.05, "voicing the lines")
    n = max(1, c["lines"])
    done = [0]

    def voiced(ln):
        if ln.startswith("VOIC") or ln.startswith("TOTAL"):
            log and log(ln)
        done[0] += 1
        progress and progress(0.05 + 0.8 * min(1.0, done[0] / (2 * n)), "voicing the lines")

    _run("voice.py", [work / "script.json", work / "build" / "audio"], cancel, log, on_line=voiced)
    progress and progress(0.9, "checking the story")
    probs = []
    try:
        _run("storycheck.py", [rp], cancel, log)
    except RuntimeError as e:
        probs = [ln for ln in str(e).splitlines() if ln.startswith("PROBLEM")] or [str(e)]
    tl = json.loads((work / "build" / "audio" / "timeline.json").read_text())
    progress and progress(1.0, "ready")
    return {**c, "seconds": tl["total"], "problems": probs, "render": str(rp)}


def _pieces(n, k):
    step = -(-n // k)
    return [(a, min(n, a + step)) for a in range(0, n, step)]


def render(work, out, draft=False, workers=None, progress=None, cancel=None, log=None):
    work = Path(work)
    rp = work / "render.json"
    if not (work / "build" / "audio" / "timeline.json").is_file():
        raise ValueError("Click Generate first: the story is not voiced yet.")
    lines = _run("render.py", [rp, "--frames", "--allow-place-rules"], cancel, log)
    n = int(next(ln.split()[1] for ln in lines if ln.startswith("FRAMES")))
    k = workers or max(1, min(7, (os.cpu_count() or 4) - 1))
    pdir = work / "build" / "pieces"
    shutil.rmtree(pdir, ignore_errors=True)
    pdir.mkdir(parents=True)
    parts = _pieces(n, k)
    log and log(f"drawing {n} frames in {len(parts)} pieces at once")
    procs, done = [], [0] * len(parts)
    for i, (a, b) in enumerate(parts):
        args = [rp, "--range", f"{a},{b}", "--out", pdir / f"piece_{i:02d}.mp4", "--allow-place-rules"] + (["--fast"] if draft else [])
        procs.append(_popen("render.py", args))
    t0 = time.time()
    try:
        import threading

        def read(i, p):
            for ln in p.stdout:
                if ln.startswith("FRAME"):
                    done[i] = int(ln.split()[1])
                elif ln.strip() and not ln.startswith("PIECE"):
                    log and log(f"piece {i}: {ln.rstrip()}")
        th = [threading.Thread(target=read, args=(i, p), daemon=True) for i, p in enumerate(procs)]
        for t in th:
            t.start()
        while any(p.poll() is None for p in procs):
            if cancel and cancel():
                raise Stopped()
            f = sum(done) / max(1, n)
            eta = (time.time() - t0) * (1 - f) / f if f > 0.02 else 0
            progress and progress(0.02 + 0.88 * f, f"drawing {sum(done)}/{n} frames" + (f", ~{eta / 60:.0f} min left" if eta else ""))
            time.sleep(1.0)
        for t in th:
            t.join(timeout=5)
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
    bad = [i for i, p in enumerate(procs) if p.returncode != 0]
    if bad:
        raise RuntimeError(f"pieces {bad} of the video failed (see the log)")
    lst = pdir / "list.txt"
    lst.write_text("".join(f"file '{(pdir / f'piece_{i:02d}.mp4').as_posix()}'\n" for i in range(len(parts))))
    silent = work / "build" / "video_silent.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    shutil.rmtree(pdir, ignore_errors=True)
    progress and progress(0.93, "mixing music and sounds")
    _run("mix.py", [rp, "--mux"], cancel, log)
    name = json.loads(rp.read_text()).get("name", "story")
    made = work / "build" / f"{name}.mp4"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(made), str(out))
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                                capture_output=True, text=True).stdout.strip() or 0)
    progress and progress(1.0, "done")
    return {"seconds": secs, "path": str(out)}
