#!/usr/bin/env python3
"""Semantic YT Studio as an MCP server, so Claude (Claude Code or Claude Desktop) can make videos from a chat.

    claude mcp add studio --scope project -- python3 /path/to/studio_mcp.py

It wraps make_video.py (same engine, same speed) and speaks MCP over stdin/stdout. Standard library only: nothing to install.
Videos and overnight batches are started in their own process group, so they keep going if Claude or this server closes.
Stop only touches the processes this server started (their pid is kept next to the job file)."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_video as M  # noqa: E402

JOBS_DIR = Path(os.environ.get("SYT_JOBS_DIR", "") or Path.home() / ".videogen" / "jobs").expanduser()
PROTOCOL = "2025-06-18"


def _path(s: str) -> str:
    """Relative paths are read from the project folder, not from wherever Claude started the server."""
    if not s:
        return ""
    p = Path(s).expanduser()
    return str(p if p.is_absolute() else (HERE / p).resolve())


def _pid_file(job: Path) -> Path:
    return job.with_name(job.stem + ".mcp_pid")


def _spawn(cmd: list, env: dict | None = None, log: Path | None = None) -> subprocess.Popen:
    out = open(log, "a", encoding="utf-8") if log else subprocess.DEVNULL
    kw = {"creationflags": 0x00000200} if os.name == "nt" else {"start_new_session": True}   # survives this server closing
    return subprocess.Popen(cmd, env=env, cwd=str(HERE), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, **kw)


def _tail(p: Path, n: int) -> list:
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def _job(job: str) -> Path:
    p = Path(job).expanduser()
    if not p.is_absolute():
        p = JOBS_DIR / p
    if p.suffix != ".json":
        p = p.with_suffix(".json")
    return p


# ---- tools ---------------------------------------------------------------------------------------------------------

def list_styles() -> str:
    rows = [f"{k}: CSV {c}, voiceover {v} ({card})" for k, (c, v, _, card) in M.STYLES.items()]
    return "Styles that run without clicks:\n" + "\n".join(rows)


def get_csv_prompt(style: str) -> str:
    s = M.norm_style(style)
    if s not in M.STYLES:
        raise ValueError(f"unknown style {style!r}; call list_styles")
    f = M.find_prompt(s, M.find_app(""))
    if f is None:
        raise ValueError(f"the CSV prompt file for {s} was not found")
    return f.read_text(encoding="utf-8")


def start_video(style: str, voice: str = "", script: str = "", csv: str = "", music: str = "", title: str = "", out: str = "",
                force: bool = False) -> str:
    a = argparse.Namespace(style=style, voice=_path(voice), script=_path(script), csv=_path(csv), music=_path(music), title=title,
                           out=_path(out), project="")
    bad = M.check_args(a)
    if bad:
        raise ValueError(bad)
    app = M.find_app("")
    if not app:
        raise ValueError(f"{M.APP_NAME} was not found")
    if M.other_app_running() and not force:
        raise ValueError(f"{M.APP_NAME} is already open (a render or an overnight batch may be running). Close it or wait; "
                         "pass force=true only if the user says to run alongside it.")
    job = M.write_job(a, JOBS_DIR)
    proc = _spawn(app, env=dict(os.environ, SYT_AUTORUN=str(job)))
    _pid_file(job).write_text(str(proc.pid), encoding="utf-8")
    return json.dumps({"job": job.name, "job_file": str(job), "log": str(job.with_name(job.stem + ".log")), "pid": proc.pid,
                       "next": "check it with job_status"}, indent=2)


def job_status(job: str, log_lines: int = 15) -> str:
    p = _job(job)
    if not p.is_file():
        raise ValueError(f"no such job: {job}")
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    if info.get("kind") == "ai_director":
        return json.dumps(_ai_status(p, info, max(0, min(int(log_lines), 80))), indent=2)
    st = M.read_status(p) or {"state": "starting"}
    st["job"] = p.name
    st["log_tail"] = _tail(p.with_name(p.stem + ".log"), max(0, min(int(log_lines), 80)))
    return json.dumps(st, indent=2)


def list_jobs(limit: int = 10) -> str:
    jobs = sorted((p for p in JOBS_DIR.glob("job_*.json") if not p.name.endswith(".status.json")), key=lambda p: p.stat().st_mtime,
                  reverse=True)[:max(1, min(int(limit), 50))]
    rows = []
    for p in jobs:
        if p.name.startswith("ai_"):
            continue
        st = M.read_status(p)
        rows.append({"job": p.name, "state": st.get("state", "unknown"), "step": st.get("step", st.get("message", "")),
                     "video": st.get("video", "")})
    for p in sorted(JOBS_DIR.glob("ai_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        try:
            st = _ai_status(p, json.loads(p.read_text(encoding="utf-8")), 0)
            rows.append({"job": p.name, "state": st["state"], "step": "AI Director", "video": st.get("video", "")})
        except (OSError, ValueError, KeyError):
            pass
    batches = sorted(JOBS_DIR.glob("batch_*_report.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    return json.dumps({"jobs": rows, "recent_batch_reports": [str(b) for b in batches]}, indent=2)


def stop_job(job: str) -> str:
    p = _job(job)
    pf = _pid_file(p)
    if not pf.is_file():
        raise ValueError("this job was not started by this server, so it is left alone; stop it in the app")
    pid = int(pf.read_text().strip())
    st = M.read_status(p) or {}
    if p.name.startswith("ai_") and not _alive(pid):
        pf.unlink(missing_ok=True)
        return f"{p.name} had already finished"
    if st.get("state") in ("done", "failed"):
        pf.unlink(missing_ok=True)                       # finished on its own: its pid may belong to another program now
        return f"{p.name} had already finished ({st.get('state')})"
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
        else:
            os.killpg(pid, signal.SIGTERM)               # its own process group: the app and what it started, nothing else
    except ProcessLookupError:
        pf.unlink(missing_ok=True)
        return f"{p.name} had already finished"
    pf.unlink(missing_ok=True)
    try:                                                 # the killed app cannot say so itself: without this it shows "running" forever
        sp = p.with_name(p.stem + ".status.json")
        st.update(state="failed", message="stopped by user", updated=time.time())
        tmp = sp.with_name(sp.name + ".stop.tmp")
        tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
        os.replace(tmp, sp)
    except OSError:
        pass
    return f"stopped {p.name} (pid {pid})"


AI_PACKS = ("doodle_dark", "history_toon", "city_lens", "doc_teal")
AI_AGENTS = ("claude", "gemini", "antigravity")


def _ai_runner() -> list:
    """The command that runs the AI Director headless (no window): from a source folder a child Python with
    agent_kit.runner; else the installed app with --run-script on the runner bundled inside it (the app has every library
    it needs, which a plain Python on this Mac may not)."""
    if (HERE / "agent_kit" / "runner.py").is_file() and (HERE / "app.py").is_file():
        return [sys.executable, "-u", "-m", "agent_kit.runner"]
    app = M.find_app("")
    if not app:
        raise ValueError(f"{M.APP_NAME} was not found (install it in /Applications)")
    exe = Path(app[-1])
    for up in (exe.parent, exe.parent.parent, exe.parent.parent.parent):
        for f in (up / "agent_kit" / "runner.py", up / "Resources" / "agent_kit" / "runner.py", up / "_internal" / "agent_kit" / "runner.py"):
            if f.is_file():
                return [*app, "--run-script", str(f)]
    raise ValueError(f"the AI Director is not in this copy of {M.APP_NAME}; install the latest version")


def start_ai_director(script: str, voice: str = "", look_pack: str = "doodle_dark", agent: str = "claude", minutes: float = 0,
                      model: str = "fast", notes: str = "", out: str = "") -> str:
    script, voice = _path(script), _path(voice)
    if not script or not Path(script).is_file():
        raise ValueError(f"script file not found: {script or '(none)'}")
    if voice and (not Path(voice).is_file() or Path(voice).suffix.lower() not in M.VOICE_EXT):
        raise ValueError(f"voice must be an audio file ({', '.join(M.VOICE_EXT)})")
    if look_pack not in AI_PACKS:
        raise ValueError(f"look_pack must be one of {', '.join(AI_PACKS)}")
    if agent not in AI_AGENTS:
        raise ValueError(f"agent must be one of {', '.join(AI_AGENTS)}")
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    project = Path(_path(out)) if out else Path.home() / "Downloads" / M.APP_NAME / f"AI_Director_{stamp}_{Path(script).stem[:40]}"
    cmd = [*_ai_runner(), "--agent", agent, "--script", script, "--out", str(project), "--pack", look_pack,
           "--model", model if agent != "gemini" else "", "--minutes", str(float(minutes or 0))]
    if voice:
        cmd += ["--voice", voice]
    if notes:
        cmd += ["--look", notes]
    job = JOBS_DIR / f"ai_{stamp}.json"
    log = job.with_suffix(".log")
    job.write_text(json.dumps({"kind": "ai_director", "project": str(project), "started": time.time(), "agent": agent,
                               "look_pack": look_pack, "command": cmd}, indent=2), encoding="utf-8")
    proc = _spawn(cmd, env=dict(os.environ, PYTHONUNBUFFERED="1"), log=log)
    _pid_file(job).write_text(str(proc.pid), encoding="utf-8")
    time.sleep(3)
    if proc.poll() not in (None, 0):
        raise ValueError("the AI Director did not start:\n" + "\n".join(_tail(log, 20)))
    return json.dumps({"job": job.name, "project": str(project), "video": str(project / "final.mp4"), "log": str(log),
                       "agent_log": str(project / "agent.log"), "pid": proc.pid,
                       "next": "check it with job_status (it takes a while: the AI plans, draws and renders every scene)"}, indent=2)


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=20).stdout
        return str(pid) in out
    try:
        os.killpg(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def _ai_status(p: Path, info: dict, log_lines: int) -> dict:
    final = Path(info["project"]) / "final.mp4"
    pf = _pid_file(p)
    running = pf.is_file() and _alive(int(pf.read_text().strip() or 0))
    tail = _tail(p.with_suffix(".log"), log_lines)
    if final.is_file() and final.stat().st_mtime > info.get("started", 0) and not running:
        state = "done"
    elif running:
        state = "running"
    else:
        state = "failed"
    st = {"job": p.name, "state": state, "project": info["project"], "log_tail": tail,
          "agent_log_tail": _tail(Path(info["project"]) / "agent.log", min(log_lines, 10))}
    if state == "done":
        st["video"] = str(final)
    return st


BATCH_COLS = ("style", "voice", "script", "csv", "music", "title", "out", "channel", "description", "tags", "thumbnail", "publish_at")


def queue_overnight(videos: list, max_hours: float = 6.0, skip_bad: bool = False) -> str:
    if not videos:
        raise ValueError("videos is empty")
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    src = JOBS_DIR / f"mcp_batch_{stamp}.csv"
    with open(src, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=BATCH_COLS)
        w.writeheader()
        for v in videos:
            row = {k: str(v.get(k, "") or "") for k in BATCH_COLS}
            for k in ("voice", "script", "csv", "music", "out", "thumbnail"):
                row[k] = _path(row[k])
            w.writerow(row)
    report = JOBS_DIR / f"batch_{stamp}_report.txt"
    log = JOBS_DIR / f"mcp_batch_{stamp}.log"
    cmd = [sys.executable, str(HERE / "make_video.py"), "batch", str(src), "--report", str(report), "--max-hours", str(max_hours)]
    if skip_bad:
        cmd.append("--skip-bad")
    proc = _spawn(cmd, log=log)
    time.sleep(2)
    if proc.poll() is not None:                          # bad rows or the app already open: nothing started
        raise ValueError("the batch did not start:\n" + "\n".join(_tail(log, 20)))
    (JOBS_DIR / f"mcp_batch_{stamp}.mcp_pid").write_text(str(proc.pid), encoding="utf-8")
    return json.dumps({"batch_file": str(src), "report": str(report), "log": str(log), "pid": proc.pid, "videos": len(videos),
                       "next": "read the report or call list_jobs to follow it"}, indent=2)


S, I, B, N = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}, {"type": "number"}
TOOLS = {
    "list_styles": (list_styles, "List the video styles Semantic YT Studio can make without clicks, and whether each needs a CSV and a voiceover.", {}, []),
    "get_csv_prompt": (get_csv_prompt, "Get the CSV-writing rules for a style. Read them before writing that style's scene CSV.", {"style": S}, ["style"]),
    "start_video": (start_video, "Start rendering one video in the background (the app opens and presses its own buttons). Paths may be "
                    "absolute or relative to the project folder. Only call this when the user asked for the render. Returns a job id.",
                    {"style": S, "voice": S, "script": S, "csv": S, "music": S, "title": S, "out": S, "force": B}, ["style"]),
    "start_ai_director": (start_ai_director, "Start the AI Director (the app's Visual Director / AI Director page) headless, with "
                          "no window and no screen control: an AI agent (Claude Code by default) plans, draws and renders the whole "
                          "video from a script (.txt) and an optional voiceover (else a free Edge voice is made). look_pack: "
                          "doodle_dark (Doodle night story, drawn), history_toon, city_lens or doc_teal. minutes>0 = a test of the "
                          "first N minutes. model: fast or best. Only call this when the user asked for the video. Returns a job id "
                          "for job_status / stop_job.",
                          {"script": S, "voice": S, "look_pack": S, "agent": S, "minutes": N, "model": S, "notes": S, "out": S},
                          ["script"]),
    "job_status": (job_status, "Where a video job is: state, current step, the finished video path or the failure, and the last log lines.",
                   {"job": S, "log_lines": I}, ["job"]),
    "list_jobs": (list_jobs, "Recent video jobs with their state, plus recent overnight batch reports.", {"limit": I}, []),
    "stop_job": (stop_job, "Stop a video job this server started (only when the user asks).", {"job": S}, ["job"]),
    "queue_overnight": (queue_overnight, "Start an overnight batch: several videos one after another with make_video.py batch (one failure "
                        "never stops the rest, the computer is kept awake, a report is written). Each video is an object with style, "
                        "voice, script, csv, music, title, out and optional channel/description/tags/thumbnail/publish_at for the upload queue.",
                        {"videos": {"type": "array", "items": {"type": "object"}}, "max_hours": N, "skip_bad": B}, ["videos"]),
}


# ---- MCP over stdio (JSON-RPC 2.0, one message per line) -----------------------------------------------------------

def handle(msg: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if mid is None:                                      # a notification (e.g. notifications/initialized): no reply
        return None
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}   # noqa: E731
    if method == "initialize":
        return ok({"protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "semantic-yt-studio", "version": "1.1"},
                   "instructions": "Every Semantic YT Studio action is a tool here: CSV styles with start_video / queue_overnight, the "
                                   "AI Director (Visual Director page) with start_ai_director. Never control the screen or the app "
                                   "window (no computer use) to press its buttons."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": props, "required": req}}
                             for n, (_, d, props, req) in TOOLS.items()]})
    if method == "tools/call":
        name = params.get("name", "")
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        fn, _, props, _ = TOOLS[name]
        args = {k: v for k, v in (params.get("arguments") or {}).items() if k in props}
        try:
            return ok({"content": [{"type": "text", "text": fn(**args)}], "isError": False})
        except Exception as exc:                         # the tool's own error goes back to Claude to read and fix
            return ok({"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
