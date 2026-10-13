"""The daily prep at 5:30 AM Central, as an OS task the app can switch on (and off) when the user asks, plus the catch-up rule.

The computer may not be in Central time, and Central time moves an hour twice a year, so the OS task does not fire at a fixed
local clock time: it wakes every 15 minutes (macOS launchd StartInterval; Windows Task Scheduler, a daily trigger repeated every
15 minutes) and runs `python -m weather.automation due --root DIR`, which prepares today's forecast only when it is due:
    due  = it is 5:30 AM Central or later, and today's folder (DIR/YYYY-MM-DD, the Central date) has no prep.json yet.
The same rule is the catch-up when the app opens (catch_up_offer): the machine may have been asleep at 5:30.

Building the task text (launchd_plist, windows_task_xml, the commands) changes nothing. install() and uninstall() do change the
user's computer: the app calls them only when the user switches the schedule on or off. Tests never call them."""

from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import List, Optional, Sequence
from xml.sax.saxutils import escape

from ..tz import to_local

LABEL = "com.semanticytstudio.weather.prep"
TASK_NAME = "SemanticYTStudio Weather Prep"
PREP_AT = time(5, 30)  # Central
CENTRAL = "America/Chicago"
EVERY_S = 900


def central_now(now: Optional[datetime] = None) -> datetime:
    return to_local(now or datetime.now(timezone.utc), CENTRAL)[0]


def day_folder(root: "str | Path", on: date) -> Path:
    return Path(root) / on.isoformat()


def is_due(root: "str | Path", now: Optional[datetime] = None, at: time = PREP_AT) -> bool:
    """5:30 AM Central or later, and today's (Central) folder has no prep yet."""
    local = central_now(now)
    if local.time() < at:
        return False
    return not (day_folder(root, local.date()) / "prep.json").is_file()


def catch_up_offer(root: "str | Path", now: Optional[datetime] = None, at: time = PREP_AT) -> Optional[str]:
    """When the app opens: a message offering to prepare today's forecast now, or None when there is nothing to catch up."""
    if not is_due(root, now, at):
        return None
    local = central_now(now)
    return (f"Today's forecast ({local.strftime('%A, %B')} {local.day}) has not been prepared yet: the {at.strftime('%I:%M %p').lstrip('0')} "
            "Central prep did not run (the computer may have been asleep). Prepare it now?")


def command(root: "str | Path", contact: str, python: Optional[str] = None, app_root: Optional["str | Path"] = None) -> List[str]:
    """The command the OS task runs (from source: this Python with -m; a packaged app passes its own command to the builders)."""
    return [python or sys.executable, "-m", "weather.automation", "due", "--root", str(root), "--contact", contact, "--notify"]


def launchd_plist(cmd: Sequence[str], workdir: "str | Path", log_path: "str | Path") -> str:
    args = "\n".join(f"\t\t<string>{escape(str(a))}</string>" for a in cmd)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>Label</key>
\t<string>{LABEL}</string>
\t<key>ProgramArguments</key>
\t<array>
{args}
\t</array>
\t<key>WorkingDirectory</key>
\t<string>{escape(str(workdir))}</string>
\t<key>StartInterval</key>
\t<integer>{EVERY_S}</integer>
\t<key>RunAtLoad</key>
\t<true/>
\t<key>StandardOutPath</key>
\t<string>{escape(str(log_path))}</string>
\t<key>StandardErrorPath</key>
\t<string>{escape(str(log_path))}</string>
</dict>
</plist>
"""


def windows_task_xml(cmd: Sequence[str], workdir: "str | Path", start: date = date(2026, 1, 1)) -> str:
    """Task Scheduler XML: every day from midnight, repeated every 15 minutes for the whole day (the job decides if it is due)."""
    exe, args = cmd[0], " ".join(_win_quote(a) for a in cmd[1:])
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Prepares the daily Weather forecast (Semantic YT Studio) at 5:30 AM Central.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start.isoformat()}T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
      <Repetition><Interval>PT15M</Interval><Duration>P1D</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(exe)}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(workdir))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _win_quote(a: str) -> str:
    a = str(a)
    return f'"{a}"' if (" " in a or not a) else a


def windows_commands(xml_path: "str | Path") -> "tuple[List[str], List[str]]":
    """(create, delete) schtasks commands."""
    return (["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"], ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install(root: "str | Path", contact: str, *, cmd: Optional[Sequence[str]] = None, workdir: Optional["str | Path"] = None,
            run=subprocess.run) -> str:
    """Switch the daily prep ON for this user (the app calls this on the user's click). Returns what was done."""
    cmd = list(cmd or command(root, contact))
    workdir = Path(workdir or Path(__file__).resolve().parents[2])
    Path(root).mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        p = plist_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(launchd_plist(cmd, workdir, Path(root) / "prep.log"), encoding="utf-8")
        run(["launchctl", "unload", str(p)], capture_output=True)
        run(["launchctl", "load", str(p)], check=True, capture_output=True)
        return f"daily prep switched on ({p})"
    if sys.platform == "win32":
        xml = Path(root) / "weather_prep_task.xml"
        xml.write_text(windows_task_xml(cmd, workdir), encoding="utf-16")
        run(windows_commands(xml)[0], check=True, capture_output=True)
        return f"daily prep switched on (Task Scheduler: {TASK_NAME})"
    raise RuntimeError("the daily prep schedule is available on macOS and Windows")


def uninstall(*, run=subprocess.run) -> str:
    """Switch the daily prep OFF (the app calls this on the user's click)."""
    if sys.platform == "darwin":
        p = plist_path()
        if p.exists():
            run(["launchctl", "unload", str(p)], capture_output=True)
            p.unlink()
        return "daily prep switched off"
    if sys.platform == "win32":
        run(windows_commands("")[1], capture_output=True)
        return "daily prep switched off"
    return "nothing to switch off"


def notify(title: str, message: str, *, run=subprocess.run) -> None:
    """A desktop notification when the scheduled prep finishes (macOS only; elsewhere the app shows the prep status)."""
    if sys.platform == "darwin":
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
        run(["osascript", "-e", f'display notification "{esc(message)}" with title "{esc(title)}"'], capture_output=True)
