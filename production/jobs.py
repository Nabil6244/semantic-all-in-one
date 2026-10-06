"""The production job ledger: ONE status model for every unit of production work.

Before this, run state lived in several places at once — the asset manifest (per scene), scene_state.json (attempts,
skips), the Tk scene rows, Flow's batch state, the render cache, the log text. The ledger does not replace any of those
stores (they stay the canonical owners of WHAT was produced); it is the canonical owner of the WORK: what ran, in what
state it is now, how long it waited and ran, how many attempts it took, why it failed, and whether it can be retried.

The executors are unchanged: AssetManager still schedules its own workers (and Flow its batches); the pipeline still
runs whisper / editorial / render in order. They report into the ledger through ``begin`` / ``finish`` (or the
``track`` context manager), which is why there is no second scheduler competing with the existing ones.

States: pending -> running -> completed | failed | cancelled, with retrying (an automatic retry is waiting) and
blocked (a dependency failed). A job still "running" when the ledger is loaded belonged to a session that ended
without finishing it (crash, closed laptop, force quit): it is marked failed / interrupted and is retryable.

Stored at <project>/state/jobs.json (atomic writes, throttled; finished history capped so a 40-minute documentary
with hundreds of scenes stays small).
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import events
from .recovery import classify_failure, policy_for

JOBS_NAME = "jobs.json"
SCHEMA_VERSION = 1
STATES = ("pending", "running", "completed", "failed", "retrying", "blocked", "cancelled")
ACTIVE = frozenset({"pending", "running", "retrying", "blocked"})
TERMINAL = frozenset({"completed", "failed", "cancelled"})
MAX_FINISHED = 3000
_SAVE_INTERVAL_S = 0.75


@dataclass
class Job:
    id: str
    type: str  # asset | align | editorial | graphics | map | audio_mix | render | mux | dataviz | cleanup | <mode>_run
    project: str = ""
    scene: str = ""
    depends_on: List[str] = field(default_factory=list)
    state: str = "pending"
    progress: float = 0.0
    attempts: int = 0
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str = ""
    error_class: str = ""
    retryable: bool = False
    source: str = ""
    outputs: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def wait_s(self) -> float:
        return max(0.0, (self.started_at or 0) - (self.created_at or 0)) if self.started_at else 0.0

    @property
    def exec_s(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.time()
        return max(0.0, end - self.started_at)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        data = {k: v for k, v in (d or {}).items() if k in known}
        job = cls(**data)
        if job.state not in STATES:
            job.state = "failed"
        return job


class JobLedger:
    """Thread-safe; every method is safe to call from worker threads. Persistence is best-effort."""

    def __init__(self, state_dir: Optional[Path] = None, *, project: str = "") -> None:
        self.state_dir = Path(state_dir) if state_dir else None
        self.project = project
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._lock = threading.RLock()
        self._dirty = False
        self._last_save = 0.0
        self._listeners: List[Any] = []
        self._interrupted: List[str] = []
        self._load()

    # ------------------------------------------------------------------ persistence
    @property
    def path(self) -> Optional[Path]:
        return self.state_dir / JOBS_NAME if self.state_dir else None

    def _load(self) -> None:
        p = self.path
        if p is None or not p.is_file():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if int(data.get("schema_version") or 0) != SCHEMA_VERSION:
                return
            for d in data.get("jobs") or []:
                job = Job.from_dict(d)
                self._jobs[job.id] = job
                self._order.append(job.id)
        except (OSError, ValueError, TypeError):
            self._jobs, self._order = {}, []
            return
        now = time.time()
        for job in self._jobs.values():
            if job.state in ("running", "retrying", "pending", "blocked"):
                # Belonged to a session that ended without finishing it.
                job.state = "failed"
                job.error = job.error or "Interrupted — the app closed while this was running."
                job.error_class = "interrupted"
                job.retryable = True
                job.finished_at = job.finished_at or now
                self._interrupted.append(job.id)
        if self._interrupted:
            self._dirty = True
            self.flush()

    def _save_locked(self, force: bool = False) -> None:
        p = self.path
        if p is None:
            self._dirty = False
            return
        now = time.monotonic()
        if not force and now - self._last_save < _SAVE_INTERVAL_S:
            return
        self._prune_locked()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema_version": SCHEMA_VERSION, "project": self.project,
                       "jobs": [self._jobs[i].to_dict() for i in self._order if i in self._jobs]}
            tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, p)
            self._dirty = False
            self._last_save = now
        except OSError:
            pass

    def flush(self) -> None:
        with self._lock:
            if self._dirty:
                self._save_locked(force=True)

    def _prune_locked(self) -> None:
        finished = [i for i in self._order if self._jobs.get(i) and self._jobs[i].state in TERMINAL]
        extra = len(finished) - MAX_FINISHED
        if extra > 0:
            drop = set(finished[:extra])
            self._order = [i for i in self._order if i not in drop]
            for i in drop:
                self._jobs.pop(i, None)

    def _changed(self, job: Job, *, terminal: bool = False) -> None:
        self._dirty = True
        self._save_locked(force=terminal)
        snapshot = job.to_dict()
        for cb in list(self._listeners):
            try:
                cb(snapshot)
            except Exception:
                pass

    def subscribe(self, callback) -> None:
        """callback(job_dict) after every state change (called on the worker thread — marshal to Tk yourself)."""
        with self._lock:
            self._listeners.append(callback)

    def unsubscribe(self, callback) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    # ------------------------------------------------------------------ lifecycle
    def create(self, type: str, *, scene: Any = "", depends_on: Iterable[str] = (), source: str = "",
               meta: Optional[dict] = None, reuse_active: bool = True) -> Job:
        """A new pending job. With ``reuse_active`` an already-active job of the same type and scene is returned
        instead, so a double click or a re-entrant call never creates a duplicate."""
        scene_s = _scene_key(scene)
        with self._lock:
            if reuse_active:
                for jid in reversed(self._order):
                    j = self._jobs.get(jid)
                    if j and j.type == type and j.scene == scene_s and j.state in ACTIVE:
                        return j
            job = Job(id=f"{type}-{scene_s + '-' if scene_s else ''}{uuid.uuid4().hex[:8]}", type=type,
                      project=self.project, scene=scene_s, depends_on=list(depends_on), source=source,
                      created_at=time.time(), meta=dict(meta or {}))
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._changed(job)
            return job

    def start(self, job_id: str, *, source: str = "") -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state in TERMINAL:
                return job
            blocker = self._failed_dependency_locked(job)
            if blocker:
                job.state = "blocked"
                job.error = f"Waiting on {blocker}, which failed."
                self._changed(job)
                return job
            job.state = "running"
            job.attempts += 1
            job.started_at = job.started_at or time.time()
            if source:
                job.source = source
            self._changed(job)
        return job

    def progress(self, job_id: str, fraction: float) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state != "running":
                return
            job.progress = max(0.0, min(1.0, float(fraction)))
            self._dirty = True
            self._save_locked()

    def complete(self, job_id: str, *, outputs: Iterable[Any] = (), meta: Optional[dict] = None) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.state = "completed"
            job.progress = 1.0
            job.finished_at = time.time()
            job.error = job.error_class = ""
            job.retryable = False
            job.outputs = [str(o) for o in outputs if o]
            if meta:
                job.meta.update(meta)
            self._changed(job, terminal=True)
        self._emit(job)
        return job

    def fail(self, job_id: str, error: Any, *, will_retry: bool = False, meta: Optional[dict] = None) -> Optional[Job]:
        """Record a failure. ``will_retry``: the caller is about to retry by itself (state "retrying")."""
        fc = classify_failure(error, "")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.error = str(error or "")[:800]
            job.error_class = fc.kind
            job.retryable = fc.retryable or fc.kind == "interrupted"
            if meta:
                job.meta.update(meta)
            if fc.kind == "cancelled":
                job.state = "cancelled"
                job.finished_at = time.time()
            elif will_retry:
                job.state = "retrying"
            else:
                job.state = "failed"
                job.finished_at = time.time()
            terminal = job.state in TERMINAL
            self._changed(job, terminal=terminal)
            if terminal:
                self._block_dependents_locked(job)
        if job.state in TERMINAL:
            self._emit(job)
        return job

    def cancel(self, job_id: str, reason: str = "Cancelled.") -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.state in TERMINAL:
                return job
            job.state = "cancelled"
            job.error = reason
            job.error_class = "cancelled"
            job.finished_at = time.time()
            self._changed(job, terminal=True)
        self._emit(job)
        return job

    def cancel_active(self, *, type: Optional[str] = None, reason: str = "Cancelled.") -> int:
        with self._lock:
            ids = [i for i in self._order if self._jobs[i].state in ACTIVE and (type is None or self._jobs[i].type == type)]
        for i in ids:
            self.cancel(i, reason)
        return len(ids)

    def _failed_dependency_locked(self, job: Job) -> str:
        for dep in job.depends_on:
            d = self._jobs.get(dep)
            if d is not None and d.state in ("failed", "cancelled"):
                return f"{d.type}{' ' + d.scene if d.scene else ''}"
        return ""

    def _block_dependents_locked(self, failed: Job) -> None:
        for jid in self._order:
            j = self._jobs.get(jid)
            if j and j.state == "pending" and failed.id in j.depends_on:
                j.state = "blocked"
                j.error = f"Waiting on {failed.type}{' ' + failed.scene if failed.scene else ''}, which failed."
                self._changed(j)

    def _emit(self, job: Job) -> None:
        events.emit("job", job=job.id, type=job.type, scene=job.scene or None, state=job.state, attempt=job.attempts,
                    wait_s=round(job.wait_s, 3), exec_s=round(job.exec_s, 3), source=job.source or None,
                    error_class=job.error_class or None, outcome=job.meta.get("outcome"))

    @contextlib.contextmanager
    def track(self, type: str, *, scene: Any = "", source: str = "", depends_on: Iterable[str] = (), meta: Optional[dict] = None):
        """``with ledger.track("render"): ...`` — completed on success, failed (re-raised) on an exception."""
        job = self.create(type, scene=scene, source=source, depends_on=depends_on, meta=meta, reuse_active=False)
        self.start(job.id)
        try:
            yield job
        except BaseException as exc:
            name = type_name = exc.__class__.__name__
            self.fail(job.id, "Cancelled." if name in ("_PipelineCancelled", "KeyboardInterrupt") else f"{type_name}: {exc}")
            raise
        else:
            if self._jobs.get(job.id) is not None and self._jobs[job.id].state == "running":
                self.complete(job.id)

    # ------------------------------------------------------------------ queries
    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def jobs(self, *, type: Optional[str] = None, state: Optional[str] = None, scene: Any = None) -> List[Job]:
        scene_s = _scene_key(scene) if scene not in (None, "") else None
        with self._lock:
            out = [self._jobs[i] for i in self._order if i in self._jobs]
        return [j for j in out if (type is None or j.type == type) and (state is None or j.state == state)
                and (scene_s is None or j.scene == scene_s)]

    def latest_for_scene(self, scene: Any, type: str = "asset") -> Optional[Job]:
        found = self.jobs(type=type, scene=scene)
        return found[-1] if found else None

    def interrupted(self) -> List[Job]:
        with self._lock:
            return [self._jobs[i] for i in self._interrupted if i in self._jobs and self._jobs[i].state == "failed"]

    def retryable_failures(self, type: Optional[str] = None) -> List[Job]:
        latest: Dict[tuple, Job] = {}
        for j in self.jobs(type=type):
            latest[(j.type, j.scene)] = j
        return [j for j in latest.values() if j.state == "failed" and j.retryable]

    def counts(self) -> Dict[str, int]:
        out = {s: 0 for s in STATES}
        with self._lock:
            for j in self._jobs.values():
                out[j.state] = out.get(j.state, 0) + 1
        return out

    def status(self) -> dict:
        """One coherent production status for the UI: what is running now, what failed, what can be retried."""
        with self._lock:
            jobs = [self._jobs[i] for i in self._order if i in self._jobs]
        active = [j for j in jobs if j.state in ACTIVE]
        latest: Dict[tuple, Job] = {}
        for j in jobs:
            latest[(j.type, j.scene)] = j
        failed = [j for j in latest.values() if j.state == "failed"]
        return {
            "active": len(active),
            "running": [j.to_dict() for j in active if j.state == "running"][:20],
            "retrying": sum(1 for j in active if j.state == "retrying"),
            "blocked": sum(1 for j in active if j.state == "blocked"),
            "failed": len(failed),
            "retryable": sum(1 for j in failed if j.retryable),
            "failed_by_class": _count(j.error_class or "unknown" for j in failed),
            "counts": self.counts(),
        }


def _count(items: Iterable[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in items:
        out[i] = out.get(i, 0) + 1
    return out


def _scene_key(scene: Any) -> str:
    if scene in (None, ""):
        return ""
    try:
        return f"{int(str(scene).strip()):03d}"
    except ValueError:
        return str(scene).strip()


# ---------------------------------------------------------------------- the ledger of the open project
_current: Optional[JobLedger] = None
_current_lock = threading.Lock()


def bind_project(state_dir: Optional[Path], project: str = "") -> JobLedger:
    """Open (or switch to) the ledger of the active project. Flushes the previous one."""
    global _current
    with _current_lock:
        if _current is not None:
            _current.flush()
            if _current.state_dir == (Path(state_dir) if state_dir else None):
                return _current
        _current = JobLedger(state_dir, project=project)
        return _current


def current() -> JobLedger:
    """The ledger of the open project (an in-memory one when no project is open)."""
    global _current
    with _current_lock:
        if _current is None:
            _current = JobLedger(None)
        return _current


__all__ = ["Job", "JobLedger", "STATES", "bind_project", "current", "policy_for"]
