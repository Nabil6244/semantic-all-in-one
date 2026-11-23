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
    st = M.read_status(p) or {"state": "starting"}
    st["job"] = p.name
    st["log_tail"] = _tail(p.with_name(p.stem + ".log"), max(0, min(int(log_lines), 80)))
    return json.dumps(st, indent=2)


def list_jobs(limit: int = 10) -> str:
    jobs = sorted((p for p in JOBS_DIR.glob("job_*.json") if not p.name.endswith(".status.json")), key=lambda p: p.stat().st_mtime,
                  reverse=True)[:max(1, min(int(limit), 50))]
    rows = []
    for p in jobs:
        st = M.read_status(p)
        rows.append({"job": p.name, "state": st.get("state", "unknown"), "step": st.get("step", st.get("message", "")),
                     "video": st.get("video", "")})
    batches = sorted(JOBS_DIR.glob("batch_*_report.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    return json.dumps({"jobs": rows, "recent_batch_reports": [str(b) for b in batches]}, indent=2)


def stop_job(job: str) -> str:
    p = _job(job)
    pf = _pid_file(p)
    if not pf.is_file():
        raise ValueError("this job was not started by this server, so it is left alone; stop it in the app")
    pid = int(pf.read_text().strip())
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
        else:
            os.killpg(pid, signal.SIGTERM)               # its own process group: the app and what it started, nothing else
    except ProcessLookupError:
        pf.unlink(missing_ok=True)
        return f"{p.name} had already finished"
    pf.unlink(missing_ok=True)
    return f"stopped {p.name} (pid {pid})"


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
                   "serverInfo": {"name": "semantic-yt-studio", "version": "1.0"}})
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
