"""Centralized FFmpeg execution with timeouts, stall detection, and cleanup.

Existing call sites should prefer ``run_ffmpeg`` over raw ``subprocess.run``
for long encodes. Probe helpers may keep short dedicated timeouts.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from providers import hidden_subprocess as hs

try:
    from hardware.governor import get_governor
    from hardware.process_registry import get_registry
except Exception:  # pragma: no cover
    get_governor = None  # type: ignore
    get_registry = None  # type: ignore


_FRAME_RE = re.compile(r"frame=\s*(\d+)")
_TIME_RE = re.compile(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


@dataclass
class FFmpegResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    stalled: bool = False
    duration_s: float = 0.0


class FFmpegError(RuntimeError):
    def __init__(self, message: str, *, result: Optional[FFmpegResult] = None):
        super().__init__(message)
        self.result = result


def encode_argv(*, quality: str = "documentary") -> List[str]:
    if get_governor is not None:
        try:
            return list(get_governor().encode_argv(quality=quality))
        except Exception:
            pass
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


def default_timeout_for_duration(media_duration_s: float, *, base: float = 90.0) -> float:
    """Wall-clock budget for filter+encode work.

    Documentary clips are short but filter graphs (Ken Burns, overlays) can be
    CPU-heavy. Bound runaway jobs without killing healthy slow encodes.
    """
    d = max(0.1, float(media_duration_s or 0.0))
    # ~25x realtime + base, floor 120s, cap 45min for a single clip.
    return float(min(45 * 60, max(120.0, base + d * 25.0)))


def run_ffmpeg(
    cmd: Sequence[str],
    *,
    owner: str = "render",
    timeout: Optional[float] = None,
    stall_s: float = 120.0,
    media_duration_s: float = 0.0,
    on_progress: Optional[Callable[[dict], None]] = None,
    check: bool = False,
    label: str = "",
) -> FFmpegResult:
    """Run an FFmpeg command with timeout + stall detection.

    Progress is inferred from stderr ``frame=`` / ``time=`` lines. If neither
    advances for ``stall_s`` while the process is alive, the job is treated as
    stalled (HEALTHY → STALLED SUSPECTED → terminate after grace).
    """
    argv = [str(c) for c in cmd]
    if not argv:
        raise ValueError("empty ffmpeg command")

    if timeout is None:
        timeout = default_timeout_for_duration(media_duration_s)

    acquired = False
    if get_governor is not None:
        try:
            acquired = bool(get_governor().acquire("ffmpeg", block=True, timeout=min(60.0, timeout)))
        except Exception:
            acquired = False

    t0 = time.monotonic()
    stdout_chunks: List[str] = []
    stderr_chunks: List[str] = []
    last_progress = time.monotonic()
    last_frame = -1
    stalled = False
    timed_out = False
    proc: Optional[subprocess.Popen] = None
    pid = 0

    try:
        proc = hs.popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if get_registry is not None and proc is not None:
            try:
                pid = get_registry().register(
                    proc,
                    owner=owner,
                    kind="ffmpeg",
                    command=" ".join(argv[:8]),
                    meta={"label": label},
                )
            except Exception:
                pid = int(getattr(proc, "pid", 0) or 0)

        stop_readers = threading.Event()

        def _reader(stream, sink: List[str], is_err: bool) -> None:
            nonlocal last_progress, last_frame
            try:
                assert stream is not None
                for line in iter(stream.readline, ""):
                    if stop_readers.is_set():
                        break
                    sink.append(line)
                    if not is_err:
                        continue
                    m = _FRAME_RE.search(line)
                    if m:
                        frame = int(m.group(1))
                        if frame != last_frame:
                            last_frame = frame
                            last_progress = time.monotonic()
                            if get_registry is not None and pid:
                                get_registry().note_progress(pid, frame=frame)
                            if on_progress:
                                on_progress({"frame": frame, "line": line.strip()})
                        continue
                    m2 = _TIME_RE.search(line)
                    if m2:
                        last_progress = time.monotonic()
                        if get_registry is not None and pid:
                            get_registry().note_progress(pid, time=m2.group(0))
                        if on_progress:
                            on_progress({"time": m2.group(0), "line": line.strip()})
            except Exception:
                pass

        threads = []
        if proc.stdout is not None:
            threads.append(threading.Thread(target=_reader, args=(proc.stdout, stdout_chunks, False), daemon=True))
        if proc.stderr is not None:
            threads.append(threading.Thread(target=_reader, args=(proc.stderr, stderr_chunks, True), daemon=True))
        for th in threads:
            th.start()

        grace_after_stall = min(30.0, max(5.0, stall_s * 0.25))
        stall_since: Optional[float] = None

        while True:
            rc = proc.poll()
            if rc is not None:
                break
            now = time.monotonic()
            if timeout and (now - t0) >= timeout:
                timed_out = True
                _kill_proc(proc)
                break
            if (now - last_progress) >= stall_s:
                if stall_since is None:
                    stall_since = now
                    if get_registry is not None and pid:
                        get_registry().mark_stalled(pid)
                elif (now - stall_since) >= grace_after_stall:
                    stalled = True
                    _kill_proc(proc)
                    break
            else:
                stall_since = None
            time.sleep(0.15)

        stop_readers.set()
        for th in threads:
            th.join(timeout=1.0)
        try:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            _kill_proc(proc)

        result = FFmpegResult(
            returncode=int(proc.returncode if proc.returncode is not None else -1),
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            timed_out=timed_out,
            stalled=stalled,
            duration_s=time.monotonic() - t0,
        )
        if get_registry is not None and pid:
            get_registry().unregister(pid)

        if check and result.returncode != 0:
            why = "timed out" if timed_out else ("stalled" if stalled else f"exit {result.returncode}")
            raise FFmpegError(
                f"ffmpeg failed ({why}) for {label or argv[0]}",
                result=result,
            )
        return result
    finally:
        if acquired and get_governor is not None:
            try:
                get_governor().release("ffmpeg")
            except Exception:
                pass


def _kill_proc(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
            return
        except Exception:
            pass
        proc.kill()
    except Exception:
        pass
