"""SQLite learning ledger at ``store_dir()/learning.sqlite`` (per user, outside every project folder).

Append-only ``events`` table, versioned schema (``meta.schema_version``) with an ordered migration list, WAL + busy timeout,
parameterized SQL. ``INSERT OR IGNORE`` on ``event_id`` makes redelivery of the same event a no-op.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DB_NAME = "learning.sqlite"
ENVELOPE_VERSION = 1
MAX_PAYLOAD_BYTES = 8192
SYNC_LOCAL_ONLY = "local_only"
_BUSY_MS = 5000

_BLOCKED_KEY_PARTS = ("token", "secret", "password", "api_key", "apikey", "hostname", "path", "prompt", "narration",
                      "script", "segment")

# Ordered migrations: index i upgrades schema version i -> i+1. Future phases append here, never edit.
_MIGRATIONS: List[Callable[[sqlite3.Connection], None]] = [
    lambda c: _run_statements(c,
        """
        CREATE TABLE IF NOT EXISTS events (
            seq            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id       TEXT NOT NULL UNIQUE,
            event_type     TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            occurred_at    TEXT NOT NULL,
            style_scope    TEXT NOT NULL,
            project_id     TEXT,
            generation_id  TEXT,
            csv_sha256     TEXT,
            payload_json   TEXT NOT NULL,
            sync_state     TEXT NOT NULL DEFAULT 'local_only',
            created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE INDEX IF NOT EXISTS events_scope_type_idx ON events (style_scope, event_type);
        CREATE INDEX IF NOT EXISTS events_project_idx ON events (project_id, event_type);
        CREATE INDEX IF NOT EXISTS events_generation_idx ON events (generation_id);
        """
    ),
    # v2: which signed-in account created the event (NULL = created signed out / before ownership existed)
    lambda c: _run_statements(c,
        """
        ALTER TABLE events ADD COLUMN owner_user_id TEXT;
        CREATE INDEX IF NOT EXISTS events_owner_sync_idx ON events (owner_user_id, sync_state)
        """),
]
SCHEMA_VERSION = len(_MIGRATIONS)

_owner_provider: Optional[Callable[[], Optional[str]]] = None


def set_owner_provider(fn: Optional[Callable[[], Optional[str]]]) -> None:
    """The app registers a callable returning the signed-in user id (or None). Events are stamped with it when written."""
    global _owner_provider
    _owner_provider = fn


def _current_owner() -> Optional[str]:
    try:
        return (_owner_provider() or None) if _owner_provider else None
    except Exception:
        return None


def _run_statements(conn: sqlite3.Connection, script: str) -> None:
    # executescript() would COMMIT the surrounding migration transaction; run statements one by one instead.
    for stmt in script.split(";"):
        if stmt.strip():
            conn.execute(stmt)


def default_db_path() -> Path:
    from licensing.session_store import store_dir

    return store_dir() / DB_NAME


def scrub_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Drop top-level keys that could carry secrets, paths, prompts or narration; bound the serialized size."""
    clean = {k: v for k, v in (payload or {}).items()
             if not any(p in str(k).lower() for p in _BLOCKED_KEY_PARTS)}
    if len(dumps(clean).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return {"truncated": True}
    return clean


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class Ledger:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_db_path()
        self._init_lock = threading.Lock()
        self._ready = False

    # ---- connection -------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=_BUSY_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={_BUSY_MS}")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        return conn

    def _open(self) -> sqlite3.Connection:
        conn = self._connect()
        if not self._ready:
            with self._init_lock:
                if not self._ready:
                    try:
                        self._migrate(conn)
                    except BaseException:
                        conn.close()
                        raise
                    self._ready = True
        return conn

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            current = int(row["value"]) if row else 0
            for version in range(current, SCHEMA_VERSION):
                _MIGRATIONS[version](conn)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                         (str(max(current, SCHEMA_VERSION)),))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    def schema_version(self) -> int:
        conn = self._open()
        try:
            return int(conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()["value"])
        finally:
            conn.close()

    # ---- writes -------------------------------------------------------------
    @staticmethod
    def _insert(conn: sqlite3.Connection, ev: Dict[str, Any]) -> bool:
        cur = conn.execute(
            "INSERT OR IGNORE INTO events (event_id, event_type, schema_version, occurred_at, style_scope, project_id,"
            " generation_id, csv_sha256, payload_json, sync_state, owner_user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ev["event_id"], ev["event_type"], int(ev.get("schema_version") or ENVELOPE_VERSION), ev["occurred_at"],
             ev["style_scope"], ev.get("project_id"), ev.get("generation_id"), ev.get("csv_sha256"),
             dumps(scrub_payload(ev.get("payload"))), SYNC_LOCAL_ONLY, ev.get("owner_user_id") or _current_owner()),
        )
        return cur.rowcount == 1

    def append(self, ev: Dict[str, Any]) -> bool:
        """Insert one event; False when the event_id already exists (redelivery)."""
        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                inserted = self._insert(conn, ev)
                conn.execute("COMMIT")
                return inserted
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    def append_revisioned(self, project_id: str, style_scope: str, event_type: str, generation_id: Optional[str],
                          build: Callable[[Optional[Dict[str, Any]]], Optional[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
        """Atomically read the latest event of this (project, scope, type, generation) and append what ``build(prev)``
        returns (None: nothing to add). Used for ratings, so revisions cannot race."""
        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM events WHERE event_type=? AND project_id=? AND style_scope=? AND COALESCE(generation_id,'')=?"
                    " ORDER BY seq DESC LIMIT 1", (event_type, project_id, style_scope, generation_id or "")).fetchone()
                ev = build(_row(row) if row else None)
                if ev is not None:
                    self._insert(conn, ev)
                conn.execute("COMMIT")
                return ev
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()

    # ---- sync bookkeeping (Phase 4) ------------------------------------------
    # sync_state: 'local_only' = not uploaded yet (the pending queue), 'synced' = server confirmed, 'rejected' = the server
    # refused this event permanently (never retried, never deleted).
    def pending(self, limit: int = 100, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        """Events waiting for upload. With ``owner``: only that account's events (never another account's)."""
        conn = self._open()
        try:
            if owner is None:
                cur = conn.execute("SELECT * FROM events WHERE sync_state='local_only' ORDER BY seq LIMIT ?", (int(limit),))
            else:
                cur = conn.execute("SELECT * FROM events WHERE sync_state='local_only' AND owner_user_id=? ORDER BY seq LIMIT ?",
                                   (owner, int(limit)))
            return [_row(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def claim_unowned(self, user_id: str) -> int:
        """Events made while signed out (or before ownership existed) go to the FIRST account that ever syncs on this
        computer, and to no other: a second, different account never inherits them (they stay local)."""
        claimant = self.get_meta("unowned_claimant")
        if claimant is None:
            self.set_meta("unowned_claimant", user_id)
            claimant = user_id
        if claimant != user_id:
            return 0
        conn = self._open()
        try:
            return conn.execute("UPDATE events SET owner_user_id=? WHERE owner_user_id IS NULL AND sync_state='local_only'",
                                (user_id,)).rowcount
        finally:
            conn.close()

    def pending_count(self) -> int:
        conn = self._open()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM events WHERE sync_state='local_only'").fetchone()[0])
        finally:
            conn.close()

    def set_sync_state(self, event_ids: List[str], state: str) -> int:
        if state not in ("synced", "rejected", "local_only") or not event_ids:
            return 0
        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            n = 0
            for i in range(0, len(event_ids), 200):
                chunk = list(event_ids[i:i + 200])
                n += conn.execute(f"UPDATE events SET sync_state=? WHERE event_id IN ({','.join('?' * len(chunk))})",
                                  (state, *chunk)).rowcount
            conn.execute("COMMIT")
            return n
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = self._open()
        try:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()

    def set_meta(self, key: str, value: str) -> None:
        conn = self._open()
        try:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))
        finally:
            conn.close()

    def prune_synced(self, older_than_days: int = 365) -> int:
        """Retention: delete only server-confirmed, bulky diagnostic events. Never touches unsynced events, ratings,
        render outcomes or imports (the evidence behind package decisions)."""
        conn = self._open()
        try:
            return conn.execute(
                "DELETE FROM events WHERE sync_state='synced' AND event_type IN ('scene_failure','render_validation','assets_outcome',"
                "'pre_render_failure','csv_import_failed') AND created_at < strftime('%Y-%m-%dT%H:%M:%fZ','now', ?)", (f"-{int(older_than_days)} days",)).rowcount
        finally:
            conn.close()

    # ---- reads --------------------------------------------------------------
    def events(self, *, event_type: Optional[str] = None, style_scope: Optional[str] = None,
               project_id: Optional[str] = None, generation_id: Optional[str] = None,
               limit: int = 1000, newest_first: bool = False) -> List[Dict[str, Any]]:
        where, args = [], []
        for col, val in (("event_type", event_type), ("style_scope", style_scope), ("project_id", project_id),
                         ("generation_id", generation_id)):
            if val is not None:
                where.append(f"{col}=?")
                args.append(val)
        sql = "SELECT * FROM events" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY seq " + ("DESC" if newest_first else "ASC") + " LIMIT ?"
        conn = self._open()
        try:
            return [_row(r) for r in conn.execute(sql, (*args, int(limit))).fetchall()]
        finally:
            conn.close()

    def latest(self, **kw) -> Optional[Dict[str, Any]]:
        got = self.events(limit=1, newest_first=True, **kw)
        return got[0] if got else None


def _row(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["payload"] = json.loads(d.pop("payload_json"))
    except ValueError:
        d["payload"] = {}
    return d


_default: Optional[Ledger] = None
_default_lock = threading.Lock()


def default_ledger() -> Ledger:
    global _default
    with _default_lock:
        if _default is None:
            _default = Ledger()
        return _default


def set_default_ledger(ledger: Optional[Ledger]) -> None:
    """Tests (or a future relocation) replace the process-wide ledger."""
    global _default
    with _default_lock:
        _default = ledger
