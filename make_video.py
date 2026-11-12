#!/usr/bin/env python3
"""Make a video with no clicks (for Claude Code, Claude Cowork, a script, or a person in a terminal).

    python3 make_video.py styles                                   the styles that run without clicks
    python3 make_video.py prompt --style explainer                 the CSV prompt to write the style's scene CSV with
    python3 make_video.py run --style explainer --voice vo.mp3 --script script.txt [--csv scenes.csv] [--title T] [--out film.mp4]
    python3 make_video.py status <job.json>                        where a running job is
    python3 make_video.py batch videos.csv                         several videos one after another (overnight): one failure never
                                                                   stops the rest; the computer is kept awake; a report is written
                                                                   after every video (columns: style,voice,script,csv,music,title,out)

`run` writes a job file, starts the app with SYT_AUTORUN=<job> and waits: the app opens, makes a new project, and presses its own buttons
(Direct with Explainer / Load CSV, Generate for the scenes, Generate again to render). Progress is printed and kept in <job>.status.json
and <job>.log; the app closes when the video is ready. Exit code 0 = video made, 1 = failed, 2 = bad arguments.

The app it starts: this folder's app.py (a development copy), else the installed "Semantic YT Studio" (or --app PATH). It must be signed
in once (the window asks; the job waits up to 30 minutes for the sign-in). Flow accounts and keys are the app's own settings.
Only this file is needed next to an installed app: it uses nothing outside the Python standard library."""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_NAME = "Semantic YT Studio"
STYLES = {   # kept in step with autorun/job.py (test_autorun.py checks it): name -> (csv, voice, prompt file, card name in the app)
    "normal": ("required", "required", "composition_styles/normal_csv_prompt.txt", "Normal video"),
    "story-motion": ("required", "required", "composition_styles/normal_csv_prompt.txt", "Story Motion"),
    "modern-tech-news": ("required", "required", "composition_styles/normal_csv_prompt.txt", "Modern Tech News"),
    "overscaled": ("required", "required", "composition_styles/overscaled_csv_prompt.txt", "Overscaled"),
    "exp-solar": ("required", "required", "composition_styles/exp_solar_csv_prompt.txt", "Exp Solar"),
    "pakmap": ("required", "required", "composition_styles/pakmap_csv_prompt.txt", "pakMap"),
    "hybrid": ("required", "required", "composition_styles/hybrid_csv_prompt.txt", "Hybrid Map"),
    "explainer": ("optional", "required", "composition_styles/explainer_scene_csv_prompt.txt", "Explainer"),
    "voxel-map": ("required", "required", "voxelmap-engine/tools/story_prompt.md", "Voxel Map"),
    "city-timelapse": ("required", "optional", "citygrow-engine/tools/story_prompt.md", "City Timelapse"),
    "starmap": ("required", "required", "composition_styles/starmap_beats_prompt.txt", "StarMap"),
    "starmap-cinema": ("required", "required", "composition_styles/starmap_beats_prompt.txt", "StarMap Cinema"),
    "what-if": ("required", "required", "composition_styles/whatif_csv_prompt.txt", "What If"),
    "rep-theory": ("optional", "required", "reptheory/scenes_csv_prompt.txt", "Rep Theory"),
    "cat-theory": ("optional", "required", "reptheory/cat_scenes_csv_prompt.txt", "Cat Theory"),
    "carl-jung-theory": ("optional", "required", "reptheory/jung_scenes_csv_prompt.txt", "Carl Jung Theory"),
    "elder-health-theory": ("optional", "required", "reptheory/elder_scenes_csv_prompt.txt", "Elder Health Theory"),
    "survival": ("optional", "required", "reptheory/survival_scenes_csv_prompt.txt", "Survival"),
    "product-trailer": ("required", "optional", "docs/product_trailer/CSV_prompt.txt", "Product Trailer"),
    "war": ("optional", "required", "cinematic_explainer/war/data/war_csv_prompt.txt", "War Documentary"),
    "enoch-template": ("required", "required", "composition_styles/enoch_template_csv_prompt.txt", "Enoch Template"),
    "roblox-cinema": ("optional", "required", "roblox-cinema-engine/docs/story_prompt.md", "Roblox Cinema"),
    "health-cinema": ("optional", "required", "composition_styles/health_cinema_csv_prompt.txt", "Health Cinema"),
    "weather": ("required", "required", "weather/prompts/forecast_csv_prompt.txt", "Weather"),
    "rules-horror": ("required", "required", "rules_horror/prompt.txt", "Rules Horror"),
    "kids-learn": ("required", "optional", "cartoon3d-engine/samples/chant_lesson.csv", "Kids Learn"),
    "aviation": ("optional", "required", "aviation/data/aviation_csv_prompt.txt", "Aviation"),
}
VOICE_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")


def find_app(explicit: str = "") -> list:
    """The command that starts the app: [python, app.py] for a development folder, else the installed executable."""
    if explicit:
        p = Path(explicit).expanduser()
        if p.suffix == ".app" and p.is_dir():
            exe = sorted((p / "Contents" / "MacOS").glob("*"))
            return [str(exe[0])] if exe else []
        if p.name == "app.py":
            return [sys.executable, str(p)]
        return [str(p)] if p.exists() else []
    if (HERE / "app.py").is_file() and (HERE / "autorun").is_dir():
        return [sys.executable, str(HERE / "app.py")]
    cands = []
    if sys.platform == "darwin":
        for root in ("/Applications", str(Path.home() / "Applications")):
            cands += glob.glob(f"{root}/{APP_NAME}.app/Contents/MacOS/*")
    elif os.name == "nt":
        for root in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")):
            if root:
                cands += glob.glob(os.path.join(root, "**", f"{APP_NAME}.exe"), recursive=True)
    return [cands[0]] if cands else []


def find_prompt(style: str, app_cmd: list) -> Path | None:
    rel = STYLES[style][2]
    places = [HERE / rel]
    if app_cmd:   # an installed app: its bundled data folder
        exe = Path(app_cmd[-1])
        for up in (exe.parent, exe.parent.parent, exe.parent.parent.parent):
            places += [up / rel, up / "Resources" / rel, up / "_internal" / rel]
    return next((p for p in places if p.is_file()), None)


def norm_style(s: str) -> str:
    return (s or "").strip().lower().replace("_", "-").replace(" ", "-")


def check_args(a) -> str:
    a.style = norm_style(a.style)
    if a.style not in STYLES:
        return f"unknown style {a.style!r}; choose one of: {', '.join(STYLES)}"
    csv_need, voice_need = STYLES[a.style][0], STYLES[a.style][1]
    if not a.voice and voice_need == "required":
        return f"the {a.style} style needs --voice (the voiceover audio)"
    for flag in ("voice", "music"):
        val = getattr(a, flag, "")
        if val and (not Path(val).expanduser().is_file() or Path(val).suffix.lower() not in VOICE_EXT):
            return f"--{flag} must be an audio file ({', '.join(VOICE_EXT)})"
    for flag in ("script", "csv"):
        val = getattr(a, flag)
        if val and not Path(val).expanduser().is_file():
            return f"--{flag} file not found: {val}"
    if csv_need == "required" and not a.csv:
        return f"the {a.style} style needs --csv (write it with: make_video.py prompt --style {a.style})"
    if a.out and not a.out.lower().endswith(".mp4"):
        return "--out must end in .mp4"
    return ""


def read_status(job: Path) -> dict:
    try:
        return json.loads(job.with_name(job.stem + ".status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_job(a, jobs_dir: Path) -> Path:
    abspath = lambda s: str(Path(s).expanduser().resolve()) if s else ""   # noqa: E731
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job = jobs_dir / f"job_{time.strftime('%Y%m%d-%H%M%S')}_{a.style}.json"
    n = 1
    while job.exists():                                  # two jobs in the same second (a batch)
        n += 1
        job = jobs_dir / f"job_{time.strftime('%Y%m%d-%H%M%S')}_{a.style}_{n}.json"
    job.write_text(json.dumps({"style": a.style, "voice": abspath(a.voice), "script": abspath(a.script), "csv": abspath(a.csv),
                               "music": abspath(a.music), "title": a.title or Path(a.voice or a.csv or a.script or a.style).stem,
                               "out": abspath(a.out)}, indent=2), encoding="utf-8")
    return job


def follow(job: Path, proc, *, max_s: float = 0, say=print) -> dict:
    """Wait for the job, printing each step. Returns its last status. max_s > 0: the app is closed after that long (a batch never hangs)."""
    t0, last, st = time.time(), None, {}
    while True:
        st = read_status(job)
        line = (st.get("state"), st.get("step"), st.get("message"))
        if st and line != last:
            say(f"[{time.strftime('%H:%M:%S')}] {line[0]}: {line[1]}" + (f" - {line[2]}" if line[2] else ""))
            last = line
        if st.get("state") in ("done", "failed"):
            break
        if proc.poll() is not None:
            time.sleep(2)
            st = read_status(job)
            if st.get("state") not in ("done", "failed"):
                st = dict(st, state="failed", message="the app closed before the job finished; see the log")
            break
        if max_s and time.time() - t0 > max_s:
            stop_app(proc)
            st = dict(read_status(job), state="failed", message=f"stopped after {max_s / 3600:.1f} hours (--max-hours)")
            break
        time.sleep(5)
    if proc.poll() is None:                              # the app closes itself a few seconds after done/failed
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            stop_app(proc)
    return st


def stop_app(proc) -> None:
    """Closes only the app this command started (its own process), never another copy."""
    try:
        proc.terminate()
        proc.wait(timeout=30)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def start_app(app: list, job: Path):
    env = dict(os.environ, SYT_AUTORUN=str(job))
    return subprocess.Popen(app, env=env, cwd=str(Path(app[-1]).parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_run(a) -> int:
    bad = check_args(a)
    if bad:
        print(f"make_video: {bad}", file=sys.stderr)
        return 2
    app = find_app(a.app)
    if not app:
        print(f"make_video: {APP_NAME} was not found; install it or pass --app PATH", file=sys.stderr)
        return 2
    job = write_job(a, Path(a.jobs_dir).expanduser() if a.jobs_dir else Path.home() / ".videogen" / "jobs")
    print(f"job: {job}")
    print(f"log: {job.with_name(job.stem + '.log')}")
    proc = start_app(app, job)
    if a.detach:
        print(f"started (pid {proc.pid}); follow it with: python3 {Path(__file__).name} status {job}")
        return 0
    st = follow(job, proc, say=lambda m: print(m, flush=True))
    if st.get("state") == "done":
        print(f"VIDEO: {st.get('video')}")
        print(f"project: {st.get('project')}")
        return 0
    print(f"FAILED: {st.get('message')}", file=sys.stderr)
    for s in st.get("failed_scenes") or []:
        print(f"  {s}", file=sys.stderr)
    if st.get("project"):
        print(f"project (open it in the app to fix and Render): {st.get('project')}", file=sys.stderr)
    return 1


JOB_FIELDS = ("style", "voice", "script", "csv", "music", "title", "out")


def read_batch(path: Path) -> list:
    """The videos of a batch file: a JSON list of {style, voice, script, csv, music, title, out}, or a CSV with those columns.
    Relative paths are read from the batch file's folder."""
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        rows = json.loads(text)
        if isinstance(rows, dict):
            rows = rows.get("videos") or rows.get("jobs") or []
    else:
        import csv as _csv
        rows = list(_csv.DictReader(text.splitlines()))
    out = []
    for r in rows:
        r = {k: str((r or {}).get(k) or "").strip() for k in JOB_FIELDS}
        if not any(r.values()):
            continue
        for k in ("voice", "script", "csv", "music", "out"):
            if r[k] and not Path(r[k]).expanduser().is_absolute():
                r[k] = str((path.parent / r[k]).resolve())
        out.append(r)
    return out


def keep_awake():
    """The computer stays awake while the batch runs (display may sleep). macOS: caffeinate tied to this process; Windows: the
    system-required flag. Returns something to undo it, or None."""
    if sys.platform == "darwin":
        try:
            return subprocess.Popen(["caffeinate", "-i", "-m", "-w", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return None
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            return "windows"
        except Exception:
            return None
    return None


def other_app_running() -> bool:
    """Another copy of the app is open (a batch would share its settings and Flow accounts)."""
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=20).stdout
            return f"{APP_NAME}.exe" in out
        out = subprocess.run(["ps", "-Ao", "command"], capture_output=True, text=True, timeout=20).stdout
        return any((line.rstrip().endswith("/app.py") and "python" in line) or f"{APP_NAME}.app/Contents/MacOS" in line for line in out.splitlines())
    except Exception:
        return False


def write_report(report: Path, started: float, results: list, total: int) -> None:
    done = [r for r in results if r["state"] == "done"]
    lines = [f"Video batch started {time.strftime('%Y-%m-%d %H:%M', time.localtime(started))}, updated {time.strftime('%H:%M')}",
             f"{len(done)} of {total} video(s) made" + (f", {len(results) - len(done)} failed" if len(results) > len(done) else "")
             + (f", {total - len(results)} still to do" if len(results) < total else ""), ""]
    for i, r in enumerate(results, 1):
        mins = r.get("minutes")
        lines.append(f"{i}. {r['title']} ({r['style']}): " + ("DONE" if r["state"] == "done" else "FAILED") + (f" in {mins:.0f} min" if mins else ""))
        if r["state"] == "done":
            lines.append(f"   video: {r.get('video')}")
        else:
            lines.append(f"   why: {r.get('message')}")
            lines += [f"   {s}" for s in (r.get("failed_scenes") or [])[:20]]
            if r.get("project"):
                lines.append(f"   project (open it in the app to fix and Render): {r['project']}")
        if r.get("log"):
            lines.append(f"   log: {r['log']}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report.with_suffix(".json").write_text(json.dumps({"started": started, "total": total, "results": results}, indent=2), encoding="utf-8")


def cmd_batch(a) -> int:
    src = Path(a.file).expanduser().resolve()
    if not src.is_file():
        print(f"make_video: batch file not found: {a.file}", file=sys.stderr)
        return 2
    try:
        rows = read_batch(src)
    except Exception as exc:
        print(f"make_video: the batch file could not be read: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("make_video: the batch file lists no videos", file=sys.stderr)
        return 2
    jobs = [argparse.Namespace(**r, app=a.app, jobs_dir=a.jobs_dir, detach=False) for r in rows]
    problems = [(i, check_args(j)) for i, j in enumerate(jobs, 1)]
    problems = [(i, p) for i, p in problems if p]
    for i, p in problems:
        print(f"video {i}: {p}", file=sys.stderr)
    if problems and not a.skip_bad:
        print("make_video: fix the batch file first (nothing was started), or pass --skip-bad to run the others", file=sys.stderr)
        return 2
    app = find_app(a.app)
    if not app:
        print(f"make_video: {APP_NAME} was not found; install it or pass --app PATH", file=sys.stderr)
        return 2
    if other_app_running() and not a.force:
        print(f"make_video: {APP_NAME} is open. Close it first (the batch drives the app and its Flow accounts), or pass --force.", file=sys.stderr)
        return 2
    jobs_dir = Path(a.jobs_dir).expanduser() if a.jobs_dir else Path.home() / ".videogen" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    report = Path(a.report).expanduser().resolve() if a.report else jobs_dir / f"batch_{time.strftime('%Y%m%d-%H%M%S')}_report.txt"
    awake = None if a.allow_sleep else keep_awake()
    started, results = time.time(), []
    bad = {i for i, _ in problems}
    say = lambda m: print(m, flush=True)   # noqa: E731
    say(f"batch: {len(jobs)} video(s); report: {report}" + ("; keeping the computer awake" if awake else ""))
    try:
        for i, j in enumerate(jobs, 1):
            title = j.title or Path(j.voice or j.csv or j.script or j.style).stem
            if i in bad:
                results.append({"title": title, "style": j.style, "state": "failed", "message": "not started: " + check_args(j)})
                write_report(report, started, results, len(jobs))
                continue
            say(f"\n=== video {i} of {len(jobs)}: {title} ({j.style}) ===")
            job = write_job(j, jobs_dir)
            t0 = time.time()
            st = follow(job, start_app(app, job), max_s=a.max_hours * 3600, say=say)
            results.append({"title": title, "style": j.style, "state": st.get("state"), "message": st.get("message", ""), "video": st.get("video", ""),
                            "project": st.get("project", ""), "failed_scenes": st.get("failed_scenes") or [], "minutes": (time.time() - t0) / 60,
                            "log": str(job.with_name(job.stem + ".log"))})
            say(f"video {i}: " + (f"DONE {st.get('video')}" if st.get("state") == "done" else f"FAILED {st.get('message')}"))
            write_report(report, started, results, len(jobs))
            if i < len(jobs):
                time.sleep(10)                           # the app has closed; Flow's browsers are let go before the next start
    finally:
        if awake is not None and awake != "windows":
            awake.terminate()
    made = sum(1 for r in results if r["state"] == "done")
    say(f"\nBATCH DONE: {made} of {len(jobs)} video(s) made. Report: {report}")
    return 0 if made == len(jobs) else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="make_video.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("styles", help="styles that run without clicks")
    pp = sub.add_parser("prompt", help="print the CSV prompt for a style")
    pp.add_argument("--style", required=True)
    pp.add_argument("--app", default="")
    r = sub.add_parser("run", help="make a video")
    r.add_argument("--style", required=True)
    r.add_argument("--voice", default="", help="the voiceover audio (needed by most styles; see: styles)")
    r.add_argument("--script", default="", help="the narration script (.txt)")
    r.add_argument("--csv", default="", help="the style's scene CSV (see: prompt)")
    r.add_argument("--music", default="", help="a music track (Product Trailer, Kids Learn, City Timelapse, Roblox Cinema, Health Cinema)")
    r.add_argument("--title", default="")
    r.add_argument("--out", default="", help="copy the finished video here (.mp4)")
    r.add_argument("--app", default="", help="the app to run (app.py, the .app or the .exe)")
    r.add_argument("--jobs-dir", default="")
    r.add_argument("--detach", action="store_true", help="start and return; follow with: status")
    b = sub.add_parser("batch", help="make several videos one after another (e.g. overnight)")
    b.add_argument("file", help="a .json list or .csv with columns style,voice,script,csv,music,title,out (paths may be relative to it)")
    b.add_argument("--report", default="", help="where the report goes (default: ~/.videogen/jobs/batch_<time>_report.txt)")
    b.add_argument("--max-hours", type=float, default=6.0, help="a video still running after this long is stopped and the batch goes on")
    b.add_argument("--skip-bad", action="store_true", help="run the valid videos even if some lines of the file are wrong")
    b.add_argument("--allow-sleep", action="store_true", help="do not keep the computer awake")
    b.add_argument("--force", action="store_true", help="start even though the app is open")
    b.add_argument("--app", default="")
    b.add_argument("--jobs-dir", default="")
    s = sub.add_parser("status", help="state of a job")
    s.add_argument("job")
    a = p.parse_args(argv)
    if a.cmd == "styles":
        print(f"{'style':20s} {'CSV':9s} {'voiceover':9s} card in the app")
        for k, (csv, voice, _, card) in STYLES.items():
            print(f"{k:20s} {csv:9s} {voice:9s} {card}")
        return 0
    if a.cmd == "prompt":
        a.style = norm_style(a.style)
        if a.style not in STYLES:
            print(f"make_video: unknown style {a.style!r}", file=sys.stderr)
            return 2
        f = find_prompt(a.style, find_app(a.app))
        if f is None:
            print("make_video: the prompt file was not found", file=sys.stderr)
            return 1
        print(f.read_text(encoding="utf-8"))
        return 0
    if a.cmd == "status":
        print(json.dumps(read_status(Path(a.job).expanduser()), indent=2))
        return 0
    if a.cmd == "batch":
        return cmd_batch(a)
    return cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())
