"""AI Director runner: a script (+ a voiceover, or a free Edge voice made here) -> an AI agent (Claude Code or Gemini CLI)
makes the whole video itself with the Video Kit tools (agent_kit_mcp.py), headless, in a project folder -> final.mp4.

    python3 -m agent_kit.runner --agent claude --script s.txt [--voice v.mp3] --out ~/Downloads/agent_videos/name [--minutes 2]

What the agent may do, and nothing else:
  Claude Code: the videokit tools + Read/Write/Edit/Glob/Grep (edits only in the project folder: --permission-mode acceptEdits,
               cwd = the project). No shell.
  Gemini CLI:  the videokit tools (server trusted in the project's .gemini/settings.json) + file edits (--approval-mode auto_edit).
               Shell commands need approval, which a headless run cannot give, so they are refused.
The app's AI Director page (ui/ai_director_section.py) calls prepare() and run(); both also work from the command line."""

from __future__ import annotations

import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SERVER = REPO / "agent_kit_mcp.py"
AGENTS = ("claude", "gemini")


def find_agent(agent: str) -> Optional[str]:
    """The agent's command: on PATH, else (Claude) the copy bundled with the Claude desktop app, newest first."""
    hit = shutil.which(agent)
    if hit:
        return hit
    home, appdata = Path.home(), Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
    extra = {"claude": [home / ".local/bin/claude", home / ".local/bin/claude.exe", appdata / "npm/claude.cmd"],
             "gemini": [appdata / "npm/gemini.cmd"]}.get(agent, [])
    for p in extra:
        if p.exists():
            return str(p)
    if agent == "claude":
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData/Local")))
        pats = [str(appdata / "Claude/claude-code/**/claude.exe"), str(local / "AnthropicClaude/**/claude-code/**/claude.exe"),
                str(local / "Claude/claude-code/**/claude.exe")] if sys.platform == "win32" else []
        found = [p for pat in pats for p in glob.glob(pat, recursive=True) if os.path.isfile(p)]
        if found:
            return max(found, key=os.path.getmtime)
        pats = [str(Path.home() / ".claude/local/claude"),
                str(Path.home() / "Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude")]
        found = [p for pat in pats for p in glob.glob(pat) if os.access(p, os.X_OK)]
        if found:
            def ver(p):
                parts = [x for x in Path(p).parts if x[:1].isdigit() and "." in x]
                return tuple(int(n) for n in parts[0].split(".") if n.isdigit()) if parts else (0,)
            return max(found, key=ver)
    if agent == "gemini":
        for p in (Path.home() / ".npm-global/bin/gemini", Path("/opt/homebrew/bin/gemini"), Path("/usr/local/bin/gemini")):
            if p.exists():
                return str(p)
    return None


def setup_command(agent: str) -> str:
    """One shell line that installs the agent if it is missing, then starts it once (its first start asks you to sign in)."""
    win = sys.platform == "win32"
    exe = find_agent(agent)
    if exe:
        return f'"{exe}"'
    if agent == "gemini":
        return "npm install -g @google/gemini-cli && gemini"
    if win:
        return ('powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex" && '
                '"%USERPROFILE%\\.local\\bin\\claude.exe"')
    return 'curl -fsSL https://claude.ai/install.sh | bash && "$HOME/.local/bin/claude"'


def open_setup_terminal(agent: str) -> str:
    """Open a visible Terminal / Command Prompt window that installs (if needed) and starts the agent so you can sign in."""
    cmd = setup_command(agent)
    if sys.platform == "darwin":
        esc = cmd.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{esc}"', "-e", 'tell application "Terminal" to activate'])
    elif sys.platform == "win32":
        subprocess.Popen(f'start "Set up {agent}" cmd /k {cmd}', shell=True)
    else:
        term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
        if not term:
            raise RuntimeError(f"open a terminal and run:  {cmd}")
        subprocess.Popen([term, "--", "bash", "-lc", cmd + "; exec bash"])
    return cmd


def check_ready(agent: str, timeout: float = 120) -> tuple:
    """(ok, message): installed AND signed in, tested with one tiny request."""
    exe = find_agent(agent)
    if not exe:
        return False, "not installed yet: click Set up / sign in"
    try:
        r = subprocess.run([exe, "-p", "Reply with the single word READY."], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, cwd=str(Path.home()))
    except subprocess.TimeoutExpired:
        return False, "no answer in time: click Set up / sign in and finish signing in"
    except OSError as exc:
        return False, f"could not start it ({exc})"
    out = (r.stdout or "") + (r.stderr or "")
    if "READY" in out.upper() and r.returncode == 0:
        return True, "ready: installed and signed in"
    low = out.lower()
    if any(k in low for k in ("login", "log in", "sign in", "api key", "auth", "credential")):
        return False, "installed but not signed in: click Set up / sign in and sign in there"
    return False, "it answered with an error: " + out.strip()[-200:]


def install_hint(agent: str) -> str:
    if agent == "gemini":
        return "Gemini CLI is not installed yet. Click Set up / sign in: it installs it and asks you to sign in with Google."
    return "Claude Code is not installed yet. Click Set up / sign in: it installs it and opens the Claude sign-in."


def make_voice(script: Path, out: Path, voice: str = "en-US-AndrewNeural", rate: str = "-4%", log: Callable = print) -> Path:
    """The free Edge voice for the whole script (edge-tts)."""
    log(f"making the voiceover with {voice} (free Edge voice)…")
    r = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, f"--rate={rate}", "-f", str(script), "--write-media", str(out)],
                       capture_output=True, text=True, timeout=3600)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("the Edge voice failed: " + (r.stderr or r.stdout)[-400:])
    return out


TASK = """You are the director, editor and motion designer of a YouTube documentary video. Make the whole video yourself with
the videokit tools, from start to finish, without asking me anything: if something fails, fix it and carry on.

Project folder (work only inside it): {project}
Script: {project}/script.txt
Voiceover: {project}/voice{voice_ext}
{scope}
Look and notes from the owner: {look}

1. Call the videokit `guide` tool first and follow it exactly: align -> story pass -> plan.json -> check_plan until it says OK ->
   for each scene write scenes/<name>.html, look at its stills (pass `at`), fix, render with `scene` (pass `at`) -> join -> look.
2. {pack_rules}
3. Write every file inside the project folder. Scene pages go in scenes/. Do not run shell commands: the tools do everything.
4. The finished video must be {project}/final.mp4 (join with out="{project}/final.mp4"{voice_end_hint}).
5. End with a short report: scenes made, length, anything you could not do.
"""


PACKS = {
    "doc_teal": ("teal documentary (doc_teal), calm and cinematic",
                 "Use the doc_teal look pack: 3D first (terrain3d for seas, coasts and lands named; block3d for anything underground or\n"
                 "   underwater; globe for the planet), at most 6 words on screen, real animal footage whenever an animal is named or the\n"
                 "   narration is about the sea or nature. What is said is what is seen."),
    "history_toon": ("illustrated cartoon history (history_toon)",
                     "Use the history_toon look pack and read " + str(REPO / "agent_kit/looks/history_toon/README.md") + " before the first scene. Everything\n"
                     "   is drawn in SVG: no footage, no photos. This video is NEW: design its own cast (era, clothes, colours) from the\n"
                     "   script in scenes/common.js and draw every place fresh from its sentence. Mix story shots, paper inserts, maps,\n"
                     "   cards, object metaphors and titles, never the same kind twice in a row. What is said is what is seen."),
    "doodle_dark": ("flat doodle story at night (doodle_dark)",
                    "Use the doodle_dark look pack and read " + str(REPO / "agent_kit/looks/doodle_dark/README.md") + " before the first scene. Everything is\n"
                    "   drawn, no footage; draw every sentence new. What is said is what is seen."),
}


def prepare(project: str | Path, script: str | Path, voice: str | Path = "", edge_voice: str = "en-US-AndrewNeural", look: str = "",
            minutes: float = 0.0, log: Callable = print, pack: str = "doc_teal") -> dict:
    """Set up the project folder: script.txt, the voice (copied, or made with Edge), TASK.md, and the kit's server config for
    Claude (mcp.json) and Gemini (.gemini/settings.json, GEMINI.md). Returns the job description run() needs."""
    P = Path(project).expanduser().resolve()
    P.mkdir(parents=True, exist_ok=True)
    src = Path(script).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"no script file: {src}")
    if src.resolve() != (P / "script.txt").resolve():
        shutil.copyfile(src, P / "script.txt")
    if voice:
        v = Path(voice).expanduser()
        if not v.is_file():
            raise FileNotFoundError(f"no voice file: {v}")
        dst = P / ("voice" + v.suffix.lower())
        if v.resolve() != dst.resolve():
            shutil.copyfile(v, dst)
    else:
        dst = next((P / f"voice{e}" for e in (".mp3", ".wav", ".m4a") if (P / f"voice{e}").exists()), None)
        if dst is None:
            dst = make_voice(P / "script.txt", P / "voice.mp3", edge_voice, log=log)
    scope = ("Scope: the WHOLE script and voice." if not minutes else
             f"Scope: a TEST of the first ~{minutes:g} minutes only. Plan and make scenes only up to the end of the sentence "
             f"nearest {minutes:g}:00 in the voice, set plan.json \"end\" to that time + 0.6 s, and join with voice_end at that "
             f"sentence's end so the voice stops cleanly.")
    task = TASK.format(project=P, voice_ext=dst.suffix, scope=scope, look=look.strip() or PACKS.get(pack, PACKS["doc_teal"])[0],
                       pack_rules=PACKS.get(pack, PACKS["doc_teal"])[1],
                       voice_end_hint=", voice_end=<the last sentence's end>" if minutes else "")
    (P / "TASK.md").write_text(task, encoding="utf-8")
    server = {"command": sys.executable, "args": [str(SERVER)]}
    (P / "mcp.json").write_text(json.dumps({"mcpServers": {"videokit": {"type": "stdio", **server}}}, indent=1), encoding="utf-8")
    (P / ".gemini").mkdir(exist_ok=True)
    (P / ".gemini" / "settings.json").write_text(json.dumps({"mcpServers": {"videokit": {**server, "trust": True, "timeout": 3600000}}},
                                                            indent=1), encoding="utf-8")
    (P / "GEMINI.md").write_text("Read TASK.md and do it with the videokit tools. Call the videokit `guide` tool first.\n", encoding="utf-8")
    log(f"project ready: {P}")
    return {"project": str(P), "task": task, "minutes": minutes}


def _cmd(agent: str, exe: str, job: dict) -> list:
    P = job["project"]
    prompt = f"Read {P}/TASK.md and do exactly what it says. The task, in full:\n\n{job['task']}"
    if agent == "claude":
        return [exe, "-p", prompt, "--mcp-config", str(Path(P) / "mcp.json"), "--strict-mcp-config",
                "--allowedTools", "mcp__videokit", "Read", "Write", "Edit", "Glob", "Grep",
                "--permission-mode", "acceptEdits", "--output-format", "stream-json", "--verbose"]
    return [exe, "-p", prompt, "--approval-mode", "auto_edit", "--allowed-mcp-server-names", "videokit", "--output-format", "stream-json"]


def _say(agent: str, line: str) -> str:
    """One readable log line from the agent's stream-json output ('' to skip)."""
    try:
        ev = json.loads(line)
    except ValueError:
        return line.strip()[:300]
    t = ev.get("type", "")
    if agent == "claude":
        if t == "assistant":
            out = []
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "text" and c.get("text", "").strip():
                    out.append(c["text"].strip()[:300])
                elif c.get("type") == "tool_use":
                    args = json.dumps(c.get("input") or {})[:140]
                    out.append(f"→ {c.get('name', '').replace('mcp__videokit__', '')} {args}")
            return "\n".join(out)
        if t == "result":
            return f"finished: {ev.get('subtype', '')} {str(ev.get('result', ''))[:400]}"
        return ""
    if t == "tool_use":
        return f"→ {ev.get('tool_name') or ev.get('name', '')} {json.dumps(ev.get('parameters') or ev.get('args') or {})[:140]}"
    if t == "message" and ev.get("role") == "assistant":
        return str(ev.get("content", "")).strip()[:300]
    if t in ("error", "result"):
        return f"{t}: {json.dumps(ev)[:400]}"
    return ""


def run(agent: str, job: dict, log: Callable = print, cancel: Callable[[], bool] = lambda: False) -> Path:
    """Run the agent headless until it finishes (or Stop). Returns final.mp4. The agent's own log: <project>/agent.log."""
    if agent not in AGENTS:
        raise ValueError(f"agent must be one of {AGENTS}")
    exe = find_agent(agent)
    if not exe:
        raise RuntimeError(install_hint(agent))
    P = Path(job["project"])
    final = P / "final.mp4"
    before = final.stat().st_mtime if final.exists() else 0
    cmd = _cmd(agent, exe, job)
    log(f"starting {agent} ({Path(exe).name}) in {P}")
    env = dict(os.environ)
    kw = {"creationflags": 0x00000200} if os.name == "nt" else {"start_new_session": True}
    with open(P / "agent.log", "a", encoding="utf-8") as raw:
        raw.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {agent}\n")
        proc = subprocess.Popen(cmd, cwd=str(P), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, **kw)
        try:
            for line in proc.stdout:
                raw.write(line)
                raw.flush()
                msg = _say(agent, line)
                if msg:
                    log(msg)
                if agent == "claude" and ("Not logged in" in line or "Please run /login" in line):
                    raise RuntimeError(f"Claude Code is not signed in. Once, in Terminal, run:\n  \"{exe}\"\nthen type /login, sign in, "
                                       "and type /exit. After that the AI Director page works.")
                if agent == "gemini" and ("GEMINI_API_KEY" in line or "Please set an Auth method" in line):
                    raise RuntimeError("Gemini CLI is not signed in. Once, in Terminal, run:  gemini   and choose Login with Google.")
                if cancel():
                    break
        finally:
            if proc.poll() is None:        # Stop: only this agent's own process group
                try:
                    os.killpg(proc.pid, signal.SIGTERM) if os.name != "nt" else proc.terminate()
                    proc.wait(timeout=15)
                except Exception:  # noqa: BLE001
                    proc.kill()
    if cancel():
        raise RuntimeError("Stopped.")
    if proc.returncode not in (0, None):
        tail = (P / "agent.log").read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
        raise RuntimeError(f"{agent} exited with code {proc.returncode}:\n" + "\n".join(tail))
    if not final.exists() or final.stat().st_mtime <= before:
        raise RuntimeError(f"{agent} finished but did not write final.mp4; see {P / 'agent.log'}")
    return final


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="An AI agent makes the video itself with the Video Kit.")
    ap.add_argument("--agent", choices=AGENTS, default="claude")
    ap.add_argument("--script", required=True)
    ap.add_argument("--voice", default="")
    ap.add_argument("--edge-voice", default="en-US-AndrewNeural")
    ap.add_argument("--look", default="")
    ap.add_argument("--pack", choices=list(PACKS), default="doc_teal", help="look pack")
    ap.add_argument("--minutes", type=float, default=0.0, help="test only the first N minutes (0 = all)")
    ap.add_argument("--out", required=True, help="the project folder")
    ap.add_argument("--prepare-only", action="store_true")
    a = ap.parse_args()
    job = prepare(a.out, a.script, a.voice, a.edge_voice, a.look, a.minutes, pack=a.pack)
    if a.prepare_only:
        print(json.dumps({"project": job["project"], "command": _cmd(a.agent, find_agent(a.agent) or a.agent, job)[:1]}))
        return 0
    print(run(a.agent, job))
    return 0


if __name__ == "__main__":
    sys.exit(main())
