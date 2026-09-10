"""Owned child-process registry for hang detection and clean shutdown.

Every long-lived FFmpeg / Node / helper process should register here so the
app can terminate *owned* children on quit without touching unrelated PIDs.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProcessRecord:
    owner: str
    pid: int
    kind: str  # ffmpeg | node | python | chrome | other
    command: str
    started_at: float
    state: str = "running"  # running | stalled_suspected | stopping | exited
    last_progress_at: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)
    popen: Any = None  # optional live Popen handle

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner": self.owner,
            "pid": self.pid,
            "kind": self.kind,
            "command": self.command[:240],
            "started_at": self.started_at,
            "state": self.state,
            "last_progress_at": self.last_progress_at,
            "age_s": round(time.time() - self.started_at, 1),
            "meta": dict(self.meta),
        }


class ProcessRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._procs: Dict[int, ProcessRecord] = {}

    def register(
        self,
        popen: subprocess.Popen,
        *,
        owner: str,
        kind: str = "other",
        command: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> int:
        pid = int(getattr(popen, "pid", 0) or 0)
        if pid <= 0:
            return 0
        now = time.time()
        rec = ProcessRecord(
            owner=owner,
            pid=pid,
            kind=kind,
            command=command or str(getattr(popen, "args", "")),
            started_at=now,
            last_progress_at=now,
            meta=dict(meta or {}),
            popen=popen,
        )
        with self._lock:
            self._procs[pid] = rec
        return pid

    def note_progress(self, pid: int, **meta: Any) -> None:
        with self._lock:
            rec = self._procs.get(pid)
            if not rec:
                return
            rec.last_progress_at = time.time()
            rec.state = "running"
            if meta:
                rec.meta.update(meta)

    def mark_stalled(self, pid: int) -> None:
        with self._lock:
            rec = self._procs.get(pid)
            if rec and rec.state == "running":
                rec.state = "stalled_suspected"

    def unregister(self, pid: int, *, state: str = "exited") -> None:
        with self._lock:
            rec = self._procs.pop(pid, None)
            if rec:
                rec.state = state
                rec.popen = None

    def list_active(self) -> List[ProcessRecord]:
        with self._lock:
            live: List[ProcessRecord] = []
            for pid, rec in list(self._procs.items()):
                proc = rec.popen
                if proc is not None and proc.poll() is not None:
                    self._procs.pop(pid, None)
                    continue
                live.append(rec)
            return list(live)

    def find_stalled(self, *, grace_s: float = 90.0) -> List[ProcessRecord]:
        now = time.time()
        out: List[ProcessRecord] = []
        for rec in self.list_active():
            if now - rec.last_progress_at >= grace_s:
                rec.state = "stalled_suspected"
                out.append(rec)
        return out

    def terminate_owned(
        self,
        *,
        owner: Optional[str] = None,
        kind: Optional[str] = None,
        grace_s: float = 2.0,
    ) -> int:
        """Terminate matching owned processes. Returns number signaled."""
        targets = []
        with self._lock:
            for rec in list(self._procs.values()):
                if owner and rec.owner != owner:
                    continue
                if kind and rec.kind != kind:
                    continue
                targets.append(rec)
        killed = 0
        for rec in targets:
            if _terminate_record(rec, grace_s=grace_s):
                killed += 1
            self.unregister(rec.pid, state="stopping")
        return killed

    def terminate_all(self, *, grace_s: float = 2.0) -> int:
        return self.terminate_owned(grace_s=grace_s)

    def to_list(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.list_active()]


def _terminate_record(rec: ProcessRecord, *, grace_s: float) -> bool:
    proc = rec.popen
    pid = rec.pid
    try:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=max(0.2, grace_s))
            except Exception:
                proc.kill()
            return True
        if pid > 0:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    return False
            return True
    except Exception:
        try:
            if proc is not None:
                proc.kill()
        except Exception:
            pass
    return False


_REGISTRY: Optional[ProcessRegistry] = None
_REG_LOCK = threading.Lock()


def get_registry() -> ProcessRegistry:
    global _REGISTRY
    with _REG_LOCK:
        if _REGISTRY is None:
            _REGISTRY = ProcessRegistry()
        return _REGISTRY


def reset_registry_for_tests() -> ProcessRegistry:
    global _REGISTRY
    with _REG_LOCK:
        _REGISTRY = ProcessRegistry()
        return _REGISTRY
