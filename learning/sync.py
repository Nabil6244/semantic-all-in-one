"""Background upload of the local ledger to Supabase (``learning_events``) and download of published knowledge packages.

* Uses the app's existing session provider / token refresh and the anon key (never a service-role key); skips quietly when
  signed out, unconfigured, disabled in settings, or offline. Production never waits for it.
* Pending = ``sync_state='local_only'``. An event becomes ``synced`` only after a 2xx from the server; a permanent 400/413/422
  on a single event marks it ``rejected`` (kept, never retried); network/429/5xx/401 leave events pending and back off.
* Server idempotency: unique (user_id, event_id) + ``Prefer: resolution=ignore-duplicates``.
* Only the allow-listed fields of ``to_remote`` leave the device (see docs/learning/README.md). Rating comments stay local.
"""

from __future__ import annotations

import random
import threading
from typing import Any, Callable, Dict, List, Optional

import requests

from . import ledger as _ledger

TABLE = "learning_events"
PACKAGE_TABLE = "knowledge_packages"
BATCH = 100
MAX_BATCHES_PER_CYCLE = 5
INTERVAL_S = 300.0
BACKOFF_BASE_S = 30.0
BACKOFF_CAP_S = 1800.0
TIMEOUT_S = 20

# payload keys allowed to leave the device, per event type. Anything else (including rating comments) is dropped.
REMOTE_PAYLOAD_KEYS: Dict[str, tuple] = {
    "csv_import": ("final_csv_sha256", "rows", "columns", "asset_types", "app_version"),
    "render_outcome": ("outcome", "failure_category", "render_engine", "operation_id", "generation_tracked", "validation", "association",
                       "association_point", "import_event_id", "final_csv_sha256", "app_version"),
    "render_validation": ("tracker_status", "validated", "error_category"),
    "scene_failure": ("scene", "source", "error_class", "attempt", "event_kind"),
    "pre_render_failure": ("stage", "error_type", "app_version"),
    "csv_import_failed": ("stage", "error_type", "app_version"),
    "assets_outcome": ("ok", "ready", "total"),
    "video_rating": ("rating", "categories", "tags", "revision", "supersedes"),
}


def to_remote(ev: Dict[str, Any], user_id: str, device_id: Optional[str]) -> Optional[Dict[str, Any]]:
    keys = REMOTE_PAYLOAD_KEYS.get(ev.get("event_type"))
    if keys is None:
        return None          # unknown (future) event types are never uploaded by an older client
    payload = ev.get("payload") or {}
    return {"event_id": ev["event_id"], "user_id": user_id, "device_id": device_id, "event_type": ev["event_type"],
            "schema_version": ev.get("schema_version") or 1, "occurred_at": ev["occurred_at"], "style_scope": ev["style_scope"],
            "project_id": ev.get("project_id"), "generation_id": ev.get("generation_id"), "csv_sha256": ev.get("csv_sha256"),
            "payload": {k: payload[k] for k in keys if k in payload}}


class Backoff(Exception):
    def __init__(self, reason: str, retry_after: Optional[float] = None):
        super().__init__(reason)
        self.reason, self.retry_after = reason, retry_after


def _creds():
    from licensing.config import supabase_credentials
    return supabase_credentials()


class SyncWorker:
    def __init__(self, session_provider: Callable[[], Any], *, refresh_session: Optional[Callable[[], Any]] = None,
                 ledger: Optional[_ledger.Ledger] = None, post: Optional[Callable[..., Any]] = None,
                 get: Optional[Callable[..., Any]] = None, enabled: Callable[[], bool] = lambda: True,
                 device_id: Optional[str] = None, creds: Optional[Callable[[], Any]] = None,
                 interval: float = INTERVAL_S, batch: int = BATCH, log: Optional[Callable[[str], None]] = None):
        self._session = session_provider
        self._refresh = refresh_session
        self._ledger = ledger
        self._post = post or requests.post
        self._get = get or requests.get
        self._enabled = enabled
        self._device_id = device_id
        self._creds = creds or _creds
        self.interval, self.batch = interval, batch
        self._log = log or (lambda m: None)
        self._failures = 0
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def ledger(self) -> _ledger.Ledger:
        return self._ledger or _ledger.default_ledger()

    # ---- one cycle (synchronous; the thread calls it) -----------------------------------------------------------
    def sync_once(self) -> Dict[str, Any]:
        out = {"sent": 0, "rejected": 0, "skipped": None, "backoff": None}
        try:
            if not self._enabled():
                out["skipped"] = "disabled"
                return out
            session = self._session()
            url, key = self._creds()
            if session is None or not getattr(session, "user_id", ""):
                out["skipped"] = "signed_out"
                return out
            if not url or not key:
                out["skipped"] = "not_configured"
                return out
            if self._device_id is None:
                try:
                    from licensing.device import get_or_create_device_id
                    self._device_id = get_or_create_device_id()
                except Exception:
                    self._device_id = ""
            self.ledger.claim_unowned(session.user_id)
            for _ in range(MAX_BATCHES_PER_CYCLE):
                events = self.ledger.pending(self.batch, owner=session.user_id)   # only THIS account's events
                if not events:
                    break
                rows, skip_ids = [], []
                for ev in events:
                    r = to_remote(ev, session.user_id, self._device_id or None)
                    (rows if r else skip_ids).append(r or ev["event_id"])
                if skip_ids:     # unknown types stay local; mark so the queue cannot stall on them
                    self.ledger.set_sync_state(skip_ids, "rejected")
                sent, rejected, session = self._upload(rows, url, key, session)
                out["sent"] += sent
                out["rejected"] += rejected
                if len(events) < self.batch:
                    break
            self._failures = 0
        except Backoff as b:
            out["backoff"] = b.reason
            self._failures += 1
            out["retry_after"] = b.retry_after
        except Exception as exc:     # never raises into the app
            out["backoff"] = type(exc).__name__
            self._failures += 1
        return out

    def _upload(self, rows: List[Dict[str, Any]], url: str, key: str, session: Any):
        if not rows:
            return 0, 0, session
        refreshed = False
        while True:
            try:
                resp = self._post(f"{url}/rest/v1/{TABLE}", headers={
                    "apikey": key, "Authorization": f"Bearer {session.access_token}", "Content-Type": "application/json",
                    "Prefer": "resolution=ignore-duplicates,return=minimal"},
                    params={"on_conflict": "user_id,event_id"}, json=rows, timeout=TIMEOUT_S)
            except requests.RequestException:
                raise Backoff("network")
            code = getattr(resp, "status_code", 0)
            if code < 300:
                self.ledger.set_sync_state([r["event_id"] for r in rows], "synced")
                return len(rows), 0, session
            if code == 401 and not refreshed and self._refresh is not None:
                refreshed = True
                try:
                    session = self._refresh() or session
                except Exception:
                    raise Backoff("auth")
                continue
            if code in (401, 403):
                raise Backoff("auth")
            if code == 429 or code >= 500:
                try:
                    ra = float(getattr(resp, "headers", {}).get("Retry-After", ""))
                except (TypeError, ValueError):
                    ra = None
                raise Backoff(f"http_{code}", ra)
            # 4xx validation failure: isolate the bad event(s) by halving; a single bad event is rejected for good
            if len(rows) == 1:
                self.ledger.set_sync_state([rows[0]["event_id"]], "rejected")
                return 0, 1, session
            mid = len(rows) // 2
            s1, r1, session = self._upload(rows[:mid], url, key, session)
            s2, r2, session = self._upload(rows[mid:], url, key, session)
            return s1 + s2, r1 + r2, session

    # ---- packages ---------------------------------------------------------------------------------------------------
    def refresh_packages(self, scopes: List[str]) -> int:
        """Download the newest published package for each of the user's own style scopes (only those)."""
        from . import packages
        session = self._session()
        url, key = self._creds()
        if session is None or not url or not key:
            return 0
        n = 0
        for scope in scopes[:10]:
            try:
                resp = self._get(f"{url}/rest/v1/{PACKAGE_TABLE}", headers={"apikey": key, "Authorization": f"Bearer {session.access_token}"},
                                 params={"style_scope": f"eq.{scope}", "status": "eq.published", "order": "version.desc", "limit": "1",
                                         "select": "package"}, timeout=TIMEOUT_S)
                if getattr(resp, "status_code", 0) >= 300:
                    continue
                rows = resp.json()
                if rows and packages.install(rows[0].get("package"), expected_scope=scope).ok:
                    n += 1
            except Exception:
                continue
        return n

    def _own_scopes(self) -> List[str]:
        try:
            seen: List[str] = []
            for e in self.ledger.events(event_type="csv_import", newest_first=True, limit=300):
                if e["style_scope"] not in seen:
                    seen.append(e["style_scope"])
            return seen
        except Exception:
            return []

    # ---- thread -----------------------------------------------------------------------------------------------------
    def next_delay(self, result: Optional[Dict[str, Any]] = None) -> float:
        if self._failures <= 0:
            return self.interval
        base = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** (self._failures - 1)))
        ra = (result or {}).get("retry_after")
        return max(float(ra or 0), base * random.uniform(0.5, 1.5))

    def _run(self) -> None:
        while not self._stop.is_set():
            res = self.sync_once()
            if not res.get("skipped") and not res.get("backoff"):
                try:
                    self.refresh_packages(self._own_scopes())
                except Exception:
                    pass
            self._wake.wait(self.next_delay(res))
            self._wake.clear()

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="learning-sync")
            self._thread.start()
            return True

    def kick(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()


_worker: Optional[SyncWorker] = None
_worker_lock = threading.Lock()


def ensure_worker(session_provider, **kw) -> SyncWorker:
    """The single process-wide worker; repeated calls (every project switch) never create a second thread."""
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = SyncWorker(session_provider, **kw)
        _worker.start()
        return _worker


def kick() -> None:
    if _worker is not None:
        _worker.kick()
