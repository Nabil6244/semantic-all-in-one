"""A Generate never sits on "still working" forever (News Doc waited 36 min on one download on Windows, 2026-10-19).

While a Generate runs, a background thread looks at the app's own child processes every few seconds. A download or media tool
(ffmpeg, ffprobe, yt-dlp) that has used no CPU for STALL_S while the app logged nothing real for STALL_S is stuck: a network read
that never returns, a pipe nobody reads. The watchdog saves a stall report (every thread's stack, the child processes, the last
step) and stops that process. The code that was waiting on it then gets an ordinary error and takes its usual fallback (skip the
clip, stock footage, retry) instead of waiting for good.

A quiet stretch with no stuck tool to stop (a wait inside Python itself) still gets a report after REPORT_S, so the exact line that
waited is known instead of guessed. Long renders are never touched: an encode always uses CPU. Without psutil (an old install) the
watchdog only writes reports."""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

STALL_S = 240.0          # a tool idle this long, with the app quiet this long, is stopped
REPORT_S = 600.0         # a quiet stretch this long gets a report even with nothing to stop
CHECK_EVERY_S = 15.0
IDLE_CPU_S = 0.05        # less CPU than this over the whole stretch counts as idle
WATCHED = ("ffmpeg", "ffprobe", "yt-dlp", "yt_dlp")


def _psutil():
    try:
        import psutil  # type: ignore

        return psutil
    except Exception:
        return None


def _watched(name: str) -> bool:
    n = (name or "").lower()
    if n.endswith(".exe"):
        n = n[:-4]
    return n in WATCHED


def thread_stacks() -> str:
    """Every Python thread's name and where it is right now."""
    names = {t.ident: t.name for t in threading.enumerate()}
    out = []
    for ident, frame in sys._current_frames().items():
        out.append(f"--- thread {names.get(ident, '?')} ({ident})\n" + "".join(traceback.format_stack(frame)))
    return "\n".join(out)


class StallWatchdog:
    def __init__(self, *, last_activity: Callable[[], float], is_running: Callable[[], bool], log: Callable[[str], None],
                 report_dir: Callable[[], Optional[Path]], last_step: Callable[[], str] = lambda: "",
                 stall_s: float = STALL_S, report_s: float = REPORT_S, check_every: float = CHECK_EVERY_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.last_activity, self.is_running, self.log = last_activity, is_running, log
        self.report_dir, self.last_step = report_dir, last_step
        self.stall_s, self.report_s, self.check_every, self.clock = stall_s, report_s, check_every, clock
        self._seen: Dict[Tuple[int, float], Tuple[float, float]] = {}   # (pid, start) -> (cpu seconds, when it last grew)
        self._reported_for: Optional[float] = None                     # the activity time the last quiet-stretch report was for
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._killed: set = set()                                       # (pid, start) already stopped: never stopped or reported twice
        self.stopped: List[str] = []                                    # what was stopped (tests, the report)

    def start(self) -> "StallWatchdog":
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="stall-watchdog", daemon=True)
            self._thread.start()
        return self

    def close(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.check_every):
            try:
                self.check_once()
            except Exception:
                pass   # the watchdog itself never takes the app down

    # ---- one look -----------------------------------------------------------------------------------------------------------

    def _children(self) -> list:
        ps = _psutil()
        if ps is None:
            return []
        try:
            kids = ps.Process(os.getpid()).children(recursive=True)
            return [p for p in kids if _watched(_safe(p.name, "")) and _safe(p.status, ps.STATUS_ZOMBIE) != ps.STATUS_ZOMBIE
                    and (p.pid, _safe(p.create_time, 0.0)) not in self._killed]
        except Exception:
            return []

    @staticmethod
    def _cpu(p) -> float:
        """The process's CPU seconds, its own children's included (yt-dlp waiting on its ffmpeg)."""
        total = 0.0
        for q in [p] + _safe(lambda: p.children(recursive=True), []):
            t = _safe(q.cpu_times, None)
            if t is not None:
                total += float(t.user) + float(t.system)
        return total

    def check_once(self) -> List[str]:
        """One look; the commands stopped this time (empty when nothing was stuck)."""
        if not self.is_running():
            self._seen.clear()
            self._reported_for = None
            return []
        now = self.clock()
        quiet = now - self.last_activity()
        alive, stuck, idle = set(), [], 0
        for p in self._children():
            key = (p.pid, _safe(p.create_time, 0.0))
            alive.add(key)
            cpu = self._cpu(p)
            prev = self._seen.get(key)
            if prev is None or cpu - prev[0] > IDLE_CPU_S:
                self._seen[key] = (cpu, now)
                idle += prev is None          # not measured yet: may be the stuck one
                continue
            idle += 1
            if now - prev[1] >= self.stall_s and quiet >= self.stall_s:
                stuck.append(p)
        for key in list(self._seen):
            if key not in alive:
                del self._seen[key]
        if stuck:
            cmds = [_cmd(p) for p in stuck]
            path = self._write_report(f"stuck tool(s) stopped after {self.stall_s / 60:.0f} min with no progress", stuck)
            for p in stuck:
                self._killed.add((p.pid, _safe(p.create_time, 0.0)))
                for q in _safe(lambda: p.children(recursive=True), []) + [p]:
                    _safe(q.kill, None)
            self.stopped += cmds
            self._reported_for = self.last_activity()
            self.log(f"[Watchdog] A step made no progress for {self.stall_s / 60:.0f} min: stopped {', '.join(c[:80] for c in cmds)}. "
                     f"The run continues with its fallback.{' Report: ' + str(path) if path else ''}\n")
            return cmds
        if quiet >= self.report_s and not idle and self._reported_for != self.last_activity():   # an idle tool: its stop report comes first
            self._reported_for = self.last_activity()
            path = self._write_report(f"no progress for {quiet / 60:.0f} min", [])
            if path:
                self.log(f"[Watchdog] No progress for {quiet / 60:.0f} min. Saved where it is waiting to {path} "
                         f"(send this file with the bug report). Press Stop to cancel the run.\n")
        return []

    def _write_report(self, why: str, stuck: list) -> Optional[Path]:
        try:
            folder = self.report_dir()
            if folder is None:
                import tempfile

                folder = Path(tempfile.gettempdir()) / "semantic_yt_stall_reports"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"stall_{datetime.now():%Y%m%d_%H%M%S}.txt"
            procs = "\n".join(f"  pid {p.pid}: {_cmd(p)}" for p in self._children()) or "  (none)"
            path.write_text(
                f"Stall report {datetime.now():%Y-%m-%d %H:%M:%S}\nWhy: {why}\nPlatform: {sys.platform} {sys.version.split()[0]}\n"
                f"Last step: {self.last_step()}\nStopped: {', '.join(_cmd(p) for p in stuck) or 'nothing'}\n"
                f"Media/download tools running:\n{procs}\n\n{thread_stacks()}", encoding="utf-8")
            return path
        except Exception:
            return None


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _cmd(p) -> str:
    parts = _safe(p.cmdline, None) or [_safe(p.name, "?")]
    return " ".join(str(x) for x in parts)[:300]


def install_for_app(app) -> Optional[StallWatchdog]:
    """The app's watchdog: active while any Generate flag is on, quiet measured from the last real log line."""
    try:
        def running() -> bool:
            return any(getattr(app, f, False) for f in getattr(app, "_RUN_FLAGS", ()))

        def report_dir() -> Optional[Path]:
            ws = getattr(app, "_workspace", None)
            return Path(ws.root) / "_work" / "stall_reports" if ws is not None and getattr(ws, "root", None) else None

        return StallWatchdog(last_activity=lambda: getattr(app, "_last_real_log_at", None) or getattr(app, "_last_log_at", time.monotonic()),
                             is_running=running, log=app._append_log, report_dir=report_dir,
                             last_step=lambda: str(getattr(app, "_last_log_line", "") or "")).start()
    except Exception:
        return None
