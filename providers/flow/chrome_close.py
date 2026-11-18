"""Close leftover Flow-profile Chrome without losing its Google sign-in.

Chrome keeps cookies in a helper process and writes them to disk on its own
schedule. Killing every Chrome process (or force-killing the main one) can
drop the newest Google cookie, and Google then signs the account out. Here
only the main browser process is asked to quit, Chrome is given time to
save, and force is the last resort.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

MARKER = "semantic-automator-desktop"


def is_flow_chrome_main(cmdline: str) -> bool:
    """A Chrome/Chromium main browser process on a Flow profile dir."""
    low = (cmdline or "").lower()
    if MARKER not in low or "profiles" not in low:
        return False
    if not any(x in low for x in ("chrome", "chromium")):
        return False
    return "--type=" not in low  # helpers (renderer, network, gpu) carry --type=


def _list_processes() -> list[tuple[int, str]]:
    if sys.platform == "win32":
        from providers import hidden_subprocess

        ps = (
            "Get-CimInstance Win32_Process -Filter \"name='chrome.exe' OR name='chromium.exe'\" "
            "| ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"
        )
        out = hidden_subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=15
        ).stdout or ""
    else:
        out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True, timeout=10)
    procs = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            procs.append((int(parts[0]), parts[1]))
    return procs


def _flow_mains() -> list[int]:
    try:
        return [pid for pid, cmd in _list_processes() if is_flow_chrome_main(cmd)]
    except Exception:
        return []


def _ask_quit(pid: int, force: bool) -> None:
    try:
        if sys.platform == "win32":
            from providers import hidden_subprocess

            args = ["taskkill", "/PID", str(pid), "/T"] + (["/F"] if force else [])
            hidden_subprocess.run(args, capture_output=True, text=True, timeout=10)
        else:
            os.kill(pid, 9 if force else 15)  # SIGTERM: Chrome's normal quit
    except Exception:
        pass


def close_flow_chrome(grace: float = 15.0) -> int:
    """Quit leftover Flow Chrome browsers cleanly. Returns how many were stopped."""
    mains = _flow_mains()
    if not mains:
        return 0
    for pid in mains:
        _ask_quit(pid, force=False)
    deadline = time.time() + grace
    while time.time() < deadline:
        still = set(_flow_mains()) & set(mains)
        if not still:
            break
        time.sleep(0.3)
    for pid in set(_flow_mains()) & set(mains):
        _ask_quit(pid, force=True)
    return len(mains)
