"""Video generation tracking -> Supabase ``video_generation_events``.

Telemetry only. Nothing here may change a generation's outcome:
  * every public method returns immediately and never raises; the network
    call runs on a daemon thread,
  * an unreachable/erroring Supabase leaves the event in a small local
    pending file (next to the session) that is re-sent on the next event,
  * user_id comes from the signed-in AuthSession (never the UI) and RLS
    rejects any other value server-side,
  * generation_id is the idempotency key: every send is an upsert on it, the
    server ignores updates to an already-finished row, and a run can only be
    finished once in-process, so a completed video is counted exactly once.

Reuses the existing Supabase REST conventions from licensing.terms /
auth_client (anon key + the user's access token, same timeout).
"""
from __future__ import annotations

import json
import platform
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from .config import supabase_credentials

TABLE = "video_generation_events"
_TIMEOUT = 20
_PENDING_FILE = "pending_generation_events.json"
_MAX_PENDING = 500
_MAX_ERROR_CHARS = 500

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def app_version() -> Optional[str]:
    """The app's version (app_version.py); None if it can't be read."""
    try:
        from app_version import APP_VERSION

        return str(APP_VERSION or "").strip() or None
    except Exception:
        return None


def platform_label() -> str:
    try:
        return f"{platform.system()} {platform.release()} {platform.machine()}".strip()[:80]
    except Exception:
        return ""


def categorize_error(message: str) -> str:
    """Coarse category for analytics, keyed off the same failure texts the app
    already distinguishes (overscaled_failure_summary, the normal pipeline's
    sys.exit/RuntimeError messages). The full text stays in the app log."""
    low = (message or "").lower()
    if "voiceover" in low or "narration" in low or "whisper" in low or "audio" in low:
        return "audio"
    if "flow" in low:
        return "flow"
    if "resource temporarily unavailable" in low or "no space left" in low or "memoryerror" in low \
            or "cannot allocate" in low or "too many open files" in low:
        return "resource"
    if "failed validation" in low or "no decodable video" in low or "duration unreadable" in low \
            or "could not be probed" in low or "csv" in low or "scene_number" in low \
            or "missing required column" in low:
        return "validation"
    if "media resolution failed" in low or "pexels" in low or "asset" in low or "scenes ready" in low \
            or "stock" in low or "youtube" in low:
        return "asset"
    if "ffmpeg" in low or "encoder" in low or "segment join failed" in low:
        return "ffmpeg"
    if "render failed" in low or "export failed" in low or "pipeline failed" in low \
            or "overlapping nodes" in low or "render" in low:
        return "render"
    return "unknown"


def _short_error(message: str) -> str:
    """First meaningful line, bounded — tracebacks/ffmpeg stderr stay local."""
    lines = [ln.strip() for ln in str(message or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    # A traceback's useful part is its last line ("ValueError: ...").
    text = lines[-1] if lines[0].startswith("Traceback") else lines[0]
    return text if len(text) <= _MAX_ERROR_CHARS else text[: _MAX_ERROR_CHARS - 1] + "…"


@dataclass
class GenerationRun:
    generation_id: str
    user_id: str
    project_id: Optional[str]
    render_engine: str
    started_at: str
    started_mono: float
    finished: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


class GenerationTracker:
    """One per app. ``session_provider`` returns the current AuthSession (or
    None when signed out / auth not configured -> tracking is skipped)."""

    def __init__(
        self,
        session_provider: Callable[[], Any],
        *,
        pending_dir: Optional[Callable[[], Path]] = None,
        refresh_session: Optional[Callable[[], Any]] = None,
        log: Optional[Callable[[str], None]] = None,
        http_post: Optional[Callable[..., Any]] = None,
        background: bool = True,
    ):
        self._session_provider = session_provider
        self._pending_dir = pending_dir or _default_pending_dir
        self._refresh_session = refresh_session
        self._log = log or (lambda _m: None)
        self._post = http_post or requests.post
        self._background = background
        self._lock = threading.Lock()  # guards run.finished + the pending file

    # ---- lifecycle -------------------------------------------------------

    def start(self, *, render_engine: str, project_id: Optional[str]) -> Optional[GenerationRun]:
        try:
            session = self._session_provider()
            user_id = str(getattr(session, "user_id", "") or "")
            if not user_id:
                return None
            run = GenerationRun(
                generation_id=str(uuid.uuid4()),
                user_id=user_id,
                project_id=(str(project_id) if project_id else None),
                render_engine=render_engine,
                started_at=_now_iso(),
                started_mono=time.monotonic(),
            )
            self._submit(self._payload(run, STATUS_RUNNING))
            return run
        except Exception as exc:
            self._safe_log(f"[TRACKING] start skipped: {exc}")
            return None

    def complete(self, run: Optional[GenerationRun], output_path, *, validated: bool,
                 expected_duration_s: float = 0.0) -> None:
        """Count one generated video — only once the final file passed validation.

        ``validated=True`` means the caller already ran the app's final output
        validation (Overscaled/Exp Solar). Otherwise the same validator
        (scene_graph.app_integration.validate_rendered_output) is run here,
        off the UI thread; a file that fails it is recorded as failed and
        NOT counted. The user-facing result is never changed either way.
        """
        if not self._claim(run):
            return

        def work() -> None:
            path = Path(str(output_path or ""))
            problem = None
            if not path.is_file() or path.stat().st_size == 0:
                problem = "output file missing or empty"
            elif not validated:
                try:
                    from scene_graph.app_integration import validate_rendered_output

                    problem = validate_rendered_output(path, expected_duration_s=expected_duration_s)
                except Exception as exc:
                    problem = f"could not be probed ({exc})"
            if problem:
                self._send(self._payload(run, STATUS_FAILED, error_category="validation",
                                         error_message=f"Final video failed validation: {problem}"))
                return
            duration = None
            try:
                from media_duration import probe_media_duration

                duration = probe_media_duration(path, log_failures=False)
            except Exception:
                duration = None
            self._send(self._payload(run, STATUS_COMPLETED,
                                     video_duration_seconds=round(float(duration), 3) if duration else None))

        self._dispatch(work)

    def fail(self, run: Optional[GenerationRun], message: str, *, category: Optional[str] = None) -> None:
        if not self._claim(run):
            return
        self._submit(self._payload(
            run, STATUS_FAILED,
            error_category=category or categorize_error(message),
            error_message=_short_error(message) or None,
        ))

    def cancel(self, run: Optional[GenerationRun]) -> None:
        if not self._claim(run):
            return
        self._submit(self._payload(run, STATUS_CANCELLED))

    def flush_pending(self) -> None:
        """Re-send queued events for the signed-in user (background)."""
        self._dispatch(lambda: self._send_pending())

    # ---- internals -------------------------------------------------------

    def _claim(self, run: Optional[GenerationRun]) -> bool:
        """A run is finished exactly once, whatever calls arrive after."""
        if run is None:
            return False
        with self._lock:
            if run.finished:
                return False
            run.finished = True
        return True

    def _payload(self, run: GenerationRun, status: str, **fields) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "generation_id": run.generation_id,
            "user_id": run.user_id,
            "project_id": run.project_id,
            "status": status,
            "started_at": run.started_at,
            "render_engine": run.render_engine,
            "app_version": app_version(),
            "platform": platform_label() or None,
        }
        if status != STATUS_RUNNING:
            payload["completed_at"] = _now_iso()
            payload["render_time_seconds"] = round(time.monotonic() - run.started_mono, 3)
        payload.update(fields)
        return payload

    def _submit(self, payload: Dict[str, Any]) -> None:
        self._dispatch(lambda: self._send(payload))

    def _dispatch(self, fn: Callable[[], None]) -> None:
        def guarded() -> None:
            try:
                fn()
            except Exception as exc:  # telemetry must never surface
                self._safe_log(f"[TRACKING] skipped: {exc}")

        if self._background:
            threading.Thread(target=guarded, daemon=True, name="generation-tracking").start()
        else:
            guarded()

    def _send(self, payload: Dict[str, Any]) -> None:
        self._send_pending()
        if not self._upsert(payload):
            self._queue(payload)

    def _upsert(self, payload: Dict[str, Any]) -> bool:
        session = self._session_provider()
        if session is None or str(getattr(session, "user_id", "") or "") != payload.get("user_id"):
            return False  # signed out, or another account: keep it for its owner
        url, key = supabase_credentials()
        if not url or not key:
            return False
        for attempt in range(2):
            try:
                resp = self._post(
                    f"{url}/rest/v1/{TABLE}",
                    headers={
                        "apikey": key,
                        "Authorization": f"Bearer {session.access_token}",
                        "Content-Type": "application/json",
                        "Prefer": "resolution=merge-duplicates,return=minimal",
                    },
                    params={"on_conflict": "generation_id"},
                    json=payload,
                    timeout=_TIMEOUT,
                )
            except requests.RequestException as exc:
                self._safe_log(f"[TRACKING] Supabase unreachable ({exc.__class__.__name__}); queued.")
                return False
            status = getattr(resp, "status_code", 0)
            if status < 400:
                return True
            if status == 401 and attempt == 0 and self._refresh_session is not None:
                # Access tokens expire (~1h); a long render outlives one.
                try:
                    session = self._refresh_session() or session
                except Exception:
                    return False
                continue
            self._safe_log(f"[TRACKING] Supabase rejected the event ({status}); queued.")
            return False
        return False

    # ---- pending file ----------------------------------------------------

    def _pending_path(self) -> Path:
        return Path(self._pending_dir()) / _PENDING_FILE

    def _read_pending(self) -> List[Dict[str, Any]]:
        try:
            data = json.loads(self._pending_path().read_text(encoding="utf-8"))
            return [p for p in data if isinstance(p, dict)] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _write_pending(self, items: List[Dict[str, Any]]) -> None:
        path = self._pending_path()
        try:
            if not items:
                if path.exists():
                    path.unlink()
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(items[-_MAX_PENDING:]), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    def _queue(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            items = self._read_pending()
            for i, item in enumerate(items):
                if item.get("generation_id") == payload.get("generation_id"):
                    # A finished state is never replaced by an older/running one.
                    if item.get("status") != STATUS_RUNNING and payload.get("status") == STATUS_RUNNING:
                        return
                    items[i] = payload
                    break
            else:
                items.append(payload)
            self._write_pending(items)

    def _send_pending(self) -> None:
        with self._lock:
            items = self._read_pending()
        if not items:
            return
        sent = set()
        for item in items:
            if self._upsert(item):
                sent.add((item.get("generation_id"), item.get("status")))
        if not sent:
            return
        with self._lock:
            remaining = [p for p in self._read_pending()
                         if (p.get("generation_id"), p.get("status")) not in sent]
            self._write_pending(remaining)

    def _safe_log(self, message: str) -> None:
        try:
            self._log(message)
        except Exception:
            pass


def _default_pending_dir() -> Path:
    from .session_store import store_dir

    return store_dir()
