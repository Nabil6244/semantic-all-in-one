"""Doodle Survival: an AI (Gemini CLI or Claude Code) makes the whole video itself through the videokit MCP tools.

make() = copy the script, make the voice (your file or a free Edge voice), write the brief, then run the chosen AI
headless in the project folder with videokit connected. The AI aligns the voice, plans, draws every scene in the
doodle_dark look (agent_kit/looks/doodle_dark), renders and joins final.mp4. We only watch the folder for progress.

Nothing here calls Gemini or Claude APIs directly: the user's own CLI does, signed in with the user's own account."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
LOOK = ROOT / "agent_kit" / "looks" / "doodle_dark"
MCP_SERVER = ROOT / "agent_kit_mcp.py"
MUSIC = ROOT / "assets" / "music" / "dark_fog.opus"
ENGINES = ("gemini", "claude")
MAX_MINUTES = 90

Log = Callable[[str], None]


# ------------------------------------------------------------------ finding the CLIs
def _python() -> str:
    """A real Python for the videokit MCP server (the packaged app's own executable is not one)."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    for c in ("python3", "python"):
        p = shutil.which(c)
        if p:
            return p
    for c in ("/opt/miniconda3/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"):
        if Path(c).is_file():
            return c
    return "python3"


def find_cli(engine: str) -> Optional[str]:
    """Path of the `gemini` or `claude` command, or None if it is not installed."""
    p = shutil.which(engine)
    if p:
        return p
    home = Path.home()
    extra = []
    if engine == "gemini":
        extra = [home / ".npm-global/bin/gemini", Path("/opt/homebrew/bin/gemini"), Path("/usr/local/bin/gemini"),
                 home / "AppData/Roaming/npm/gemini.cmd"]
        extra += sorted(home.glob(".nvm/versions/node/*/bin/gemini"), reverse=True)
    else:
        extra = [home / ".claude/local/claude", home / ".local/bin/claude", Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude")]
        extra += sorted((home / "Library/Application Support/Claude/claude-code").glob("*/*/claude.app/Contents/MacOS/claude"), reverse=True)
    for c in extra:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def install_hint(engine: str) -> str:
    if engine == "gemini":
        return ("Gemini CLI is not installed. In Terminal run:\n\n    npm install -g @google/gemini-cli\n    gemini\n\n"
                "and sign in with your Google account once (the free tier works), then click Generate again.")
    return ("Claude Code is not installed. In Terminal run:\n\n    npm install -g @anthropic-ai/claude-code\n    claude\n\n"
            "and sign in once, then click Generate again.")


# ------------------------------------------------------------------ the project folder
def _edge_voice(text_file: Path, out: Path, voice: str) -> None:
    exe = shutil.which("edge-tts")
    cmd = [exe, "--voice", voice, "--rate=-4%", "-f", str(text_file), "--write-media", str(out)] if exe else \
          [_python(), "-m", "edge_tts", "--voice", voice, "--rate=-4%", "-f", str(text_file), "--write-media", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.is_file() or out.stat().st_size < 1000:
        raise RuntimeError(f"the free voice could not be made: {(r.stderr or r.stdout)[-300:]}")


def brief(project: Path, notes: str = "") -> str:
    """The instructions the AI gets (also saved as BRIEF.md in the project)."""
    readme = (LOOK / "README.md").read_text(encoding="utf-8")
    extra = f"\n## Notes from the owner for this video\n{notes.strip()}\n" if notes.strip() else ""
    return f"""# Make a Doodle Survival video, start to finish, without asking anything

Project folder: {project}
Script: {project}/script.txt
Voice: {project}/voice/voice.mp3
Look pack: {LOOK}  (README below; example scenes from a finished video in {LOOK}/examples/ — read 2 of them first)
Music bed: {MUSIC}

Use only the videokit tools for video work (guide, align, check_plan, scene, look, join) and your file tools to write
scene pages. Steps:
1. Call `guide` and follow it.
2. `align` the voice with the script (project = the project folder above, voice and script = the paths above).
3. Write {project}/plan.json with "look": "doodle_dark", the story, and every scene (2.5–6 s each, start = its first
   word). Run `check_plan` and fix every problem until it says OK.
4. For each scene write {project}/scenes/<name>.html in the doodle_dark look, drawn new from what its sentence says
   (README rules below). `look` at 2–3 stills (pass `at` and `duration`), fix what is wrong, then `scene` with
   html = the absolute path of the page, at = the scene's start, duration = end - start, grade = none.
5. `join` every clip in order with voice = the voice above, music = the music bed above (music_db -22), tail 1, and
   sound effects on the hooks (impact on slams, whoosh on cuts, ui/text on counters, riser before reveals).
6. Stop only when {project}/final.mp4 exists. Do not ask the owner questions; decide yourself.
{extra}
---
{readme}
"""


def prepare(project: Path, *, script: str, voice_file: Optional[str], edge_voice: str, notes: str, log: Log) -> None:
    project.mkdir(parents=True, exist_ok=True)
    (project / "voice").mkdir(exist_ok=True)
    (project / "scenes").mkdir(exist_ok=True)
    shutil.copyfile(script, project / "script.txt")
    vo = project / "voice" / "voice.mp3"
    if voice_file:
        src = Path(voice_file)
        if src.suffix.lower() == ".mp3":
            shutil.copyfile(src, vo)
        else:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-c:a", "libmp3lame", "-q:a", "2", str(vo)],
                           check=True, timeout=600)
        log("voice: your file")
    elif not vo.is_file():
        log(f"voice: free Edge voice {edge_voice}…")
        _edge_voice(project / "script.txt", vo, edge_voice)
    (project / "BRIEF.md").write_text(brief(project, notes), encoding="utf-8")


def _mcp_entry() -> dict:
    return {"command": _python(), "args": [str(MCP_SERVER)], "cwd": str(ROOT)}


def command(engine: str, cli: str, project: Path) -> list[str]:
    """The headless command line for the chosen AI, with videokit connected and tools pre-approved."""
    prompt = (f"Read {project}/BRIEF.md and do exactly what it says: make the Doodle Survival video in {project} with the "
              f"videokit tools until {project}/final.mp4 exists. Do not ask questions.")
    if engine == "gemini":
        cfg = project / ".gemini" / "settings.json"          # project-level settings: Gemini CLI reads them from its cwd
        cfg.parent.mkdir(exist_ok=True)
        cfg.write_text(json.dumps({"mcpServers": {"videokit": {**_mcp_entry(), "timeout": 900000, "trust": True}}}, indent=1), encoding="utf-8")
        return [cli, "--yolo", "--include-directories", str(LOOK), "-p", prompt]
    cfg = project / "videokit_mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"videokit": {"type": "stdio", **_mcp_entry()}}}, indent=1), encoding="utf-8")
    return [cli, "-p", prompt, "--mcp-config", str(cfg), "--add-dir", str(LOOK),
            "--allowedTools", "mcp__videokit", "Read", "Write", "Edit", "Glob", "Grep",
            "--permission-mode", "acceptEdits", "--output-format", "stream-json", "--verbose"]


# ------------------------------------------------------------------ watching the AI work
def _progress_of(project: Path) -> tuple[float, str]:
    if (project / "final.mp4").is_file():
        return 1.0, "joined final.mp4"
    plan = project / "plan.json"
    clips = list((project / "clips").glob("*.mp4")) if (project / "clips").is_dir() else []
    pages = list((project / "scenes").glob("*.html"))
    if plan.is_file():
        try:
            n = max(1, len(json.loads(plan.read_text(encoding="utf-8")).get("scenes") or []))
        except Exception:  # noqa: BLE001 - the AI may be mid-write
            n = max(1, len(pages))
        if clips:
            return 0.25 + 0.65 * min(1.0, len(clips) / n), f"{len(clips)}/{n} scenes rendered"
        return 0.15 + 0.1 * min(1.0, len(pages) / n), f"{len(pages)}/{n} scenes drawn"
    if (project / "voice" / "words.json").is_file():
        return 0.1, "voice aligned, planning"
    return 0.05, "reading the brief"


def _say(engine: str, line: str) -> str:
    """One readable log line from the CLI's output (Claude streams JSON; Gemini prints text)."""
    line = line.strip()
    if engine != "claude" or not line.startswith("{"):
        return line[:300]
    try:
        ev = json.loads(line)
    except Exception:  # noqa: BLE001
        return line[:300]
    if ev.get("type") == "assistant":
        out = []
        for c in (ev.get("message") or {}).get("content") or []:
            if c.get("type") == "tool_use":
                arg = c.get("input") or {}
                what = arg.get("name") or Path(str(arg.get("file_path") or arg.get("path") or "")).name
                out.append(f"→ {c.get('name', '').replace('mcp__videokit__', 'videokit ')} {what}".rstrip())
            elif c.get("type") == "text" and c.get("text", "").strip():
                out.append(c["text"].strip()[:300])
        return "\n".join(out)
    if ev.get("type") == "result":
        return f"AI finished: {ev.get('subtype', '')} {str(ev.get('result', ''))[:200]}"
    return ""


def run_ai(engine: str, project: Path, *, log: Log, progress: Callable[[float, str], None], cancel: Callable[[], bool]) -> Path:
    cli = find_cli(engine)
    if not cli:
        raise RuntimeError(install_hint(engine))
    cmd = command(engine, cli, project)
    log(f"starting {engine} in {project}")
    env = dict(os.environ, NO_COLOR="1")
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    proc = subprocess.Popen(cmd, cwd=str(project), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", env=env, **kw)
    (project / "ai.log").write_text("", encoding="utf-8")

    def pump() -> None:
        with open(project / "ai.log", "a", encoding="utf-8") as f:
            for raw in proc.stdout:            # type: ignore[union-attr]
                f.write(raw)
                msg = _say(engine, raw)
                if msg:
                    log(msg)

    threading.Thread(target=pump, name="doodle-ai-log", daemon=True).start()
    t0, last = time.time(), None
    try:
        while proc.poll() is None:
            if cancel():
                raise RuntimeError("Stopped.")
            if time.time() - t0 > MAX_MINUTES * 60:
                raise RuntimeError(f"the AI took more than {MAX_MINUTES} minutes; see ai.log in {project}")
            pr = _progress_of(project)
            if pr != last:
                progress(*pr)
                last = pr
            time.sleep(2)
    finally:
        if proc.poll() is None:                # stop only the AI process this run started (its own process group)
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.terminate()
                proc.wait(10)
            except Exception:  # noqa: BLE001
                proc.kill()
    final = project / "final.mp4"
    if not final.is_file():
        raise RuntimeError(f"{engine} stopped (exit {proc.returncode}) before final.mp4 was made; see ai.log in {project}")
    progress(1.0, "done")
    return final


def make(*, project: str, script: str, voice_file: Optional[str], edge_voice: str, engine: str, notes: str = "",
         out_path: Optional[str] = None, log: Log = print, progress: Callable[[float, str], None] = lambda f, m="": None,
         cancel: Callable[[], bool] = lambda: False) -> dict:
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}")
    p = Path(project)
    progress(0.02, "preparing")
    prepare(p, script=script, voice_file=voice_file, edge_voice=edge_voice, notes=notes, log=log)
    final = run_ai(engine, p, log=log, progress=progress, cancel=cancel)
    if out_path:
        shutil.copyfile(final, out_path)
        final = Path(out_path)
    secs = 0.0
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(final)],
                           capture_output=True, text=True, timeout=60)
        secs = float(r.stdout.strip() or 0)
    except Exception:  # noqa: BLE001
        pass
    return {"final": str(final), "seconds": secs, "project": str(p)}


if __name__ == "__main__":   # python -m doodle_ai.runner <script.txt> <project_dir> [gemini|claude]
    a = sys.argv[1:]
    r = make(project=a[1], script=a[0], voice_file=None, edge_voice="en-US-AndrewNeural", engine=a[2] if len(a) > 2 else "gemini",
             progress=lambda f, m="": print(f"{int(f * 100)}% {m}"))
    print(r)
