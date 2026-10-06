"""Append-only production event log: <project>/state/production_events.jsonl.

Every analytics number is computed from these events (plus the existing state files), never from hand-kept counters.
Producers call ``emit(kind, **fields)``; nothing here can raise into the pipeline (a failed write only loses one event).

The log follows the open project: ``bind_project(state_dir)`` when a project is activated. With no project bound,
events go to an in-memory ring only (tests, the CLI, the first seconds of start-up).

Event kinds (fields are free-form but these are the ones analytics reads):
  run_start / run_end        run, mode, outcome, duration_s
  job                        job, type, scene, state, attempt, wait_s, exec_s, source, error_class
  asset                      scene, source, outcome (generated|reused|failed|replaced|skipped), duration_s
  cache                      cache (whisper|editorial|smart_plan|render_clip|asset|ai), hit
  ai_call                    task, model, duration_s, ok, cached, tokens_in, tokens_out, error_class
  render                     duration_s, frames, fps, scenes, clips_reused, clips_rendered, output_s
  regeneration               changed, invalidated, reused, est_saved_s
  recovery                   action, scene, detail
"""

from __future__ import annotations

import collections
import contextlib
import contextvars
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, List, Optional

EVENTS_NAME = "production_events.jsonl"
MAX_BYTES = 8 * 1024 * 1024  # rotate to .1 past this; a 40-minute documentary writes well under 1 MB per run
_RING = 4000

_lock = threading.RLock()
_state_dir: Optional[Path] = None
_ring: collections.deque = collections.deque(maxlen=_RING)
_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("production_run_id", default="")
# Worker threads (AssetManager's pool, Flow batches) do not inherit context variables: their events are
# attributed to the run that is active process-wide.
_active_runs: List[str] = []


def bind_project(state_dir: Optional[Path]) -> None:
    """Send events to this project's state folder (None: memory only)."""
    global _state_dir
    with _lock:
        _state_dir = Path(state_dir) if state_dir else None


def events_path(state_dir: Path) -> Path:
    return Path(state_dir) / EVENTS_NAME


def emit(kind: str, **fields: Any) -> dict:
    """Record one event. Never raises."""
    try:
        event = {"t": round(time.time(), 3), "kind": str(kind)}
        run = fields.pop("run", None) or _run_id.get() or (_active_runs[-1] if _active_runs else "")
        if run:
            event["run"] = run
        for key, value in fields.items():
            if value is not None:
                event[key] = value if isinstance(value, (str, int, float, bool, list, dict)) else str(value)
        with _lock:
            _ring.append(event)
            target = _state_dir
        if target is not None:
            _append(target, event)
        return event
    except Exception:
        return {}


def _append(state_dir: Path, event: dict) -> None:
    try:
        path = events_path(state_dir)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if path.stat().st_size > MAX_BYTES:
                    os.replace(path, path.with_suffix(path.suffix + ".1"))
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass


def read(state_dir: Optional[Path] = None, *, kinds: Optional[Iterable[str]] = None, include_rotated: bool = True) -> List[dict]:
    """Events of a project (oldest first); with no folder, the in-memory ring. Corrupt lines are skipped."""
    wanted = set(kinds) if kinds else None
    out: List[dict] = []
    if state_dir is None:
        with _lock:
            items = list(_ring)
        return [e for e in items if wanted is None or e.get("kind") in wanted]
    path = events_path(Path(state_dir))
    files = [path.with_suffix(path.suffix + ".1"), path] if include_rotated else [path]
    for p in files:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(e, dict) and (wanted is None or e.get("kind") in wanted):
                        out.append(e)
        except OSError:
            continue
    return out


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


@contextlib.contextmanager
def run(mode: str, **fields: Any):
    """Bracket one production run: run_start ... run_end (with outcome and duration). Yields the run id.

    The body sets ``outcome`` on the yielded dict-like holder when it knows better than "ok"/"error"."""
    run_id = new_run_id(mode)
    token = _run_id.set(run_id)
    with _lock:
        _active_runs.append(run_id)
    holder = {"id": run_id, "outcome": "ok"}
    start = time.monotonic()
    emit("run_start", mode=mode, **fields)
    try:
        yield holder
    except BaseException as exc:
        holder["outcome"] = "cancelled" if type(exc).__name__ in ("_PipelineCancelled", "KeyboardInterrupt") else "error"
        raise
    finally:
        emit("run_end", mode=mode, outcome=holder.get("outcome", "ok"), duration_s=round(time.monotonic() - start, 3))
        with _lock:
            if run_id in _active_runs:
                _active_runs.remove(run_id)
        _run_id.reset(token)


def current_run() -> str:
    return _run_id.get() or (_active_runs[-1] if _active_runs else "")


def start_run(mode: str, **fields: Any) -> dict:
    """Non-context-manager form of ``run`` for code whose try/except shape cannot wrap a ``with`` (app._run_pipeline).
    Pair with ``end_run(token, outcome)``."""
    run_id = new_run_id(mode)
    token = {"id": run_id, "mode": mode, "start": time.monotonic(), "var": _run_id.set(run_id)}
    with _lock:
        _active_runs.append(run_id)
    emit("run_start", mode=mode, **fields)
    return token


def end_run(token: Optional[dict], outcome: str = "ok", **fields: Any) -> None:
    if not token:
        return
    try:
        emit("run_end", mode=token.get("mode"), outcome=outcome,
             duration_s=round(time.monotonic() - float(token.get("start") or time.monotonic()), 3), **fields)
    finally:
        with _lock:
            if token.get("id") in _active_runs:
                _active_runs.remove(token["id"])
        try:
            _run_id.reset(token["var"])
        except (ValueError, KeyError, RuntimeError):
            _run_id.set("")
