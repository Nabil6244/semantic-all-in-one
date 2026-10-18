"""Event builders, app adapters and the video-rating API. Everything here fails open (returns False/None/a result, never raises).

Event types: ``csv_import``, ``render_outcome``, ``video_rating``. Stored fields never include raw CSV text, narration,
prompts, paths, hostnames or credentials (see ledger.scrub_payload).

Deduplication
  * csv_import:     event_id = ``csv_import:<import_op_id>`` -- an operation id minted per user action, so a redelivered
                    callback is ignored but a deliberate re-import of the same file is a new row.
  * render_outcome: event_id = ``render:<generation_id>`` -- first terminal outcome wins (same rule as GenerationTracker);
                    every new render has a new generation_id and is recorded.
  * video_rating:   append-only; a changed rating for the same render is a new revision that names the one it supersedes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import ledger as _ledger
from .scope import resolve_scope

CATEGORIES = ("visual_relevance", "footage_selection", "animations_graphics", "typography_transitions", "pacing")
ISSUE_TAGS = ("wrong_visuals", "repetitive_scenes", "bad_transitions", "weak_graphics", "poor_pacing", "excellent_result")
MAX_COMMENT_CHARS = 500
STALE_TYPES = ("csv_import", "render_outcome", "render_validation", "scene_failure", "video_rating")
KNOWN_FAILURE_CATEGORIES = ("audio", "flow", "resource", "validation", "asset", "ffmpeg", "render", "unknown")
_OUTCOMES = {"completed": "success", "failed": "failure", "cancelled": "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Any) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def sha256_files(paths: Iterable[Any]) -> Optional[str]:
    try:
        h = hashlib.sha256()
        for p in paths:
            with open(p, "rb") as f:
                h.update(f.read())
        return h.hexdigest()
    except Exception:
        return None


def csv_structure(text: str) -> Dict[str, Any]:
    """Safe structural metadata only: row count, column names, asset_type counts. Lenient; {} when unreadable."""
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        cols = [str(c)[:64] for c in (reader.fieldnames or []) if c][:60]
        rows = 0
        types: Counter = Counter()
        for row in reader:
            rows += 1
            t = str(row.get("asset_type") or "").strip().lower()[:32]
            if t:
                types[t] += 1
        return {"rows": rows, "columns": cols, "asset_types": dict(types.most_common(20))}
    except Exception:
        return {}


def record_event(event_type: str, *, style_scope: str, event_id: Optional[str] = None, project_id: Optional[str] = None,
                 generation_id: Optional[str] = None, csv_sha256: Optional[str] = None,
                 payload: Optional[Dict[str, Any]] = None, ledger: Optional[_ledger.Ledger] = None) -> bool:
    """Append one event. True only when a new row was written. Never raises."""
    try:
        led = ledger or _ledger.default_ledger()
        ok = led.append({
            "event_id": event_id or uuid.uuid4().hex, "event_type": event_type, "schema_version": _ledger.ENVELOPE_VERSION,
            "occurred_at": _now(), "style_scope": style_scope, "project_id": project_id, "generation_id": generation_id,
            "csv_sha256": csv_sha256, "payload": payload or {},
        })
        if ok and event_type in STALE_TYPES:
            led.set_meta("analysis_stale", "1")     # a flag only: the scan itself is manual or scheduled, never per event
        return ok
    except Exception:
        return False


def _project_id(app: Any) -> Optional[str]:
    return getattr(getattr(app, "_workspace", None), "project_id", None)


def _app_version() -> Optional[str]:
    try:
        from app_version import APP_VERSION

        return str(APP_VERSION or "") or None
    except Exception:
        return None


def _read_text(path: Any) -> str:
    return Path(path).read_text(encoding="utf-8-sig", errors="replace")


def _safe_structure(path: Any) -> Dict[str, Any]:
    try:
        return csv_structure(_read_text(path))
    except Exception:
        return {}


def note_import(app: Any, mode: str, *, path: Any = None, paths: Optional[List[Any]] = None, text: Optional[str] = None,
                final_path: Any = None, op_id: Optional[str] = None, style: Optional[str] = None, ledger: Optional[_ledger.Ledger] = None) -> bool:
    """Record a user-initiated CSV import. ``path``/``paths``/``text`` are the ORIGINAL data (hashed before the app changes
    anything); ``final_path`` is the project's copy after the app's own transformations (hashed separately).
    Call only from genuine import actions, never from project reopen/reload paths."""
    try:
        raw = None
        struct: Dict[str, Any] = {}
        if text is not None:
            raw = sha256_bytes(text.encode("utf-8"))
            struct = csv_structure(text)
        elif paths:
            raw = sha256_files(paths)
            if len(paths) == 1:
                struct = _safe_structure(paths[0])
        elif path is not None:
            raw = sha256_file(path)
            struct = _safe_structure(path)
        final = sha256_file(final_path) if final_path is not None else None
        payload = {"final_csv_sha256": final, "app_version": _app_version(), **struct}
        scope = resolve_scope(app, mode, style=style)
        ok = record_event("csv_import", style_scope=scope, project_id=_project_id(app), csv_sha256=raw,
                          event_id="csv_import:" + (op_id or uuid.uuid4().hex), payload=payload, ledger=ledger)
        if ok:
            try:    # non-blocking, style-scoped advisory lines from an approved package (nothing without one)
                from .guidance import log_advisories
                log_advisories(app, scope, struct)
            except Exception:
                pass
        return ok
    except Exception:
        return False


def _bind_import(led: _ledger.Ledger, pid: Optional[str], scope: str) -> Dict[str, Any]:
    imp = led.latest(event_type="csv_import", project_id=pid, style_scope=scope) if pid else None
    if not imp:
        return {"association": "unknown"}
    return {"import_event_id": imp["event_id"], "csv_sha256": imp.get("csv_sha256"),
            "final_csv_sha256": (imp.get("payload") or {}).get("final_csv_sha256")}


def begin_render_op(app: Any, engine: str, run: Any = None, ledger: Optional[_ledger.Ledger] = None) -> Optional[Dict[str, Any]]:
    """Call when a full render starts (after GenerationTracker.start, whose run may be None when signed out). Freezes the
    style scope and the CSV the render will actually use, so a later import cannot change what this render is linked to.
    Stores a local operation on the app; the matching terminal call consumes it."""
    try:
        led = ledger or _ledger.default_ledger()
        scope = resolve_scope(app, engine)
        pid = getattr(run, "project_id", None) or _project_id(app)
        op = {"op_id": uuid.uuid4().hex, "engine": engine, "scope": scope, "project_id": pid, "started": time.time(),
              "generation_id": getattr(run, "generation_id", None), "association_point": "render_start",
              **_bind_import(led, pid, scope)}
        if engine == "weather" and op.get("association") == "unknown" and pid:
            for e in led.events(event_type="csv_import", project_id=pid, newest_first=True, limit=20):
                if e["style_scope"].startswith("weather/"):
                    op.update(scope=e["style_scope"], import_event_id=e["event_id"], csv_sha256=e.get("csv_sha256"),
                              final_csv_sha256=(e.get("payload") or {}).get("final_csv_sha256"))
                    op.pop("association", None)
                    break
        app._learning_op = op
        return op
    except Exception:
        return None


def note_import_failed(app: Any, mode: str, *, path: Any = None, paths: Optional[List[Any]] = None, text: Optional[str] = None,
                       error: Any = None, ledger: Optional[_ledger.Ledger] = None) -> bool:
    """A user CSV import that the app rejected (the user already saw the app's own message; this stores only a code).
    Same file + mode + project within 30 s is one event, so repeated callbacks do not multiply."""
    try:
        raw = (sha256_bytes(text.encode("utf-8")) if text is not None
               else sha256_files(paths) if paths else sha256_file(path) if path is not None else None)
        et = _token(type(error).__name__, 40) if isinstance(error, BaseException) else "rejected"
        eid = f"csv_import_failed:{mode}:{_project_id(app)}:{raw or 'nohash'}:{int(time.time() // 30)}"
        return record_event("csv_import_failed", style_scope=resolve_scope(app, mode), project_id=_project_id(app), csv_sha256=raw,
                            event_id=eid, payload={"stage": "load", "error_type": et, "app_version": _app_version()}, ledger=ledger)
    except Exception:
        return False


def note_render_outcome(app: Any, run: Any, outcome: str, category: Optional[str] = None, message: str = "",
                        ledger: Optional[_ledger.Ledger] = None) -> bool:
    """Record one terminal FULL-render outcome. Identity: the tracker's generation_id when there is one, else the local
    operation id from begin_render_op (signed-out sessions). Neither -> nothing is recorded. The failure message is never
    stored, only a category from a fixed list. First terminal outcome per key wins."""
    try:
        if outcome not in _OUTCOMES:
            return False
        op = getattr(app, "_learning_op", None)
        try:
            app._learning_op = None
        except Exception:
            pass
        gid = getattr(run, "generation_id", None) or (op or {}).get("generation_id")
        key = gid or (op or {}).get("op_id")
        if not key:
            return False
        led = ledger or _ledger.default_ledger()
        engine = getattr(run, "render_engine", None) or (op or {}).get("engine") or getattr(app, "generation_mode", "normal")
        pid = getattr(run, "project_id", None) or (op or {}).get("project_id") or _project_id(app)
        if op and op.get("scope"):
            scope = op["scope"]
        else:
            scope = resolve_scope(app, engine)
        bound = ({k: op[k] for k in ("association", "association_point", "import_event_id", "csv_sha256", "final_csv_sha256") if k in op}
                 if op else {**_bind_import(led, pid, scope), "association_point": "render_end"})
        payload: Dict[str, Any] = {"outcome": _OUTCOMES[outcome], "app_version": _app_version(), "render_engine": engine,
                                   "operation_id": (op or {}).get("op_id"), "generation_tracked": bool(gid),
                                   "validation": "pending" if outcome == "completed" else "not_applicable"}
        if outcome == "failed":
            payload["failure_category"] = category if category in KNOWN_FAILURE_CATEGORIES else "unknown"
        for k in ("association", "import_event_id", "final_csv_sha256", "association_point"):
            if bound.get(k) is not None:
                payload[k] = bound[k]
        if op is None:
            payload.setdefault("association_point", "render_end")
        ok = record_event("render_outcome", style_scope=scope, event_id="render:" + key, project_id=pid, generation_id=gid,
                          csv_sha256=bound.get("csv_sha256"), payload=payload, ledger=led)
        if ok:
            _record_scene_failures(app, led, key, gid, scope, pid, bound.get("csv_sha256"), (op or {}).get("started"))
        return ok
    except Exception:
        return False


_SAFE_TOKEN = re.compile(r"[^a-z0-9_.\-]+")


def _token(v: Any, n: int = 40) -> str:
    return _SAFE_TOKEN.sub("_", str(v or "").strip().lower())[:n]


def _record_scene_failures(app: Any, led: _ledger.Ledger, key: str, gid: Optional[str], scope: str, pid: Optional[str],
                           csv_sha: Optional[str], started: Optional[float]) -> int:
    """Sanitized per-scene failures of THIS operation, read from the project's production event log (time window = the
    operation). Scene, provider key, error class and attempt only; never error text. Idempotent per (operation, scene, kind)."""
    try:
        ws = getattr(app, "_workspace", None)
        if ws is None or not started:
            return 0
        from production import events as pe

        n = 0
        for e in pe.read(ws.state_dir, kinds=("asset", "job")):
            if float(e.get("t") or 0) < float(started) - 1:
                continue
            failed = (e.get("kind") == "asset" and e.get("outcome") == "failed") or (e.get("kind") == "job" and e.get("state") == "failed")
            scene = e.get("scene")
            if not failed or scene in (None, ""):
                continue
            payload = {"scene": _token(scene, 16), "source": _token(e.get("source") or e.get("type")),
                       "error_class": _token(e.get("error_class") or "unknown"), "attempt": int(e.get("attempt") or 0),
                       "event_kind": e.get("kind")}
            eid = f"scene_failure:{key}:{payload['scene']}:{payload['event_kind']}:{payload['attempt']}"
            if record_event("scene_failure", style_scope=scope, event_id=eid, project_id=pid, generation_id=gid,
                            csv_sha256=csv_sha, payload=payload, ledger=led):
                n += 1
            if n >= 200:
                break
        return n
    except Exception:
        return 0


def note_validation(payload: Dict[str, Any], ledger: Optional[_ledger.Ledger] = None) -> bool:
    """Observer for GenerationTracker terminal payloads: records the tracker's final verdict (which includes output
    validation) as its own event next to the earlier render_outcome. History is never rewritten."""
    try:
        gid = payload.get("generation_id")
        led = ledger or _ledger.default_ledger()
        base = led.latest(event_type="render_outcome", generation_id=gid) if gid else None
        if not base:
            return False
        status = str(payload.get("status") or "")
        return record_event("render_validation", style_scope=base["style_scope"], event_id=f"render_validation:{gid}:{status}",
                            project_id=base.get("project_id"), generation_id=gid, csv_sha256=base.get("csv_sha256"),
                            payload={"tracker_status": status, "validated": status == "completed",
                                     "error_category": payload.get("error_category")}, ledger=led)
    except Exception:
        return False


def note_prerender_failure(app: Any, mode: str, stage: str, *, error: Any = None, path: Any = None, text: Optional[str] = None,
                           ledger: Optional[_ledger.Ledger] = None) -> bool:
    """A failure before any render started (CSV unreadable/invalid, Generate refused). Not a render outcome."""
    try:
        raw = sha256_bytes(text.encode("utf-8")) if text is not None else (sha256_file(path) if path is not None else None)
        cat = type(error).__name__ if isinstance(error, BaseException) else None
        return record_event("pre_render_failure", style_scope=resolve_scope(app, mode), project_id=_project_id(app), csv_sha256=raw,
                            payload={"stage": _token(stage, 24), "error_type": cat, "app_version": _app_version()}, ledger=ledger)
    except Exception:
        return False


def note_assets_outcome(app: Any, ok: bool, ready: int = 0, total: int = 0, ledger: Optional[_ledger.Ledger] = None) -> bool:
    """An assets-only run finished (no video was rendered): its own event type, never a render success."""
    try:
        return record_event("assets_outcome", style_scope=resolve_scope(app), project_id=_project_id(app),
                            payload={"ok": bool(ok), "ready": int(ready or 0), "total": int(total or 0)}, ledger=ledger)
    except Exception:
        return False


@dataclass
class RatingResult:
    ok: bool
    status: str            # "recorded" | "revised" | "unchanged" | "invalid" | "error"
    event_id: Optional[str] = None
    revision: int = 0
    error: str = ""        # a fixed reason code, never user text


def _score(v: Any) -> Optional[int]:
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 5:
        return None
    return v


def record_video_rating(project_id: str, style_scope: str, rating: int, *, generation_id: Optional[str] = None,
                        categories: Optional[Dict[str, int]] = None, tags: Optional[Iterable[str]] = None,
                        comment: Optional[str] = None, occurred_at: Optional[str] = None,
                        ledger: Optional[_ledger.Ledger] = None) -> RatingResult:
    """Record a 1-5 rating of one finished render (``generation_id``; without it, of the project in that style scope).

    Append-only: re-rating the same render adds a new revision (``supersedes`` = the previous event) and never edits or
    deletes the earlier one; resubmitting identical content is "unchanged". Unknown tags are ignored (duplicates removed);
    unknown category names or out-of-range category scores make the whole rating "invalid". Comments are trimmed to
    500 characters and never logged. Never raises."""
    try:
        if not project_id or not style_scope:
            return RatingResult(False, "invalid", error="missing_project_or_scope")
        if _score(rating) is None:
            return RatingResult(False, "invalid", error="rating_out_of_range")
        cats: Dict[str, int] = {}
        for k, v in (categories or {}).items():
            if k not in CATEGORIES:
                return RatingResult(False, "invalid", error="unknown_category")
            if _score(v) is None:
                return RatingResult(False, "invalid", error="category_out_of_range")
            cats[k] = v
        clean_tags = sorted({str(t).strip().lower() for t in (tags or [])} & set(ISSUE_TAGS))
        text = str(comment).strip()[:MAX_COMMENT_CHARS] if comment else ""
        content = {"rating": rating, "categories": cats, "tags": clean_tags, "comment": text}
        led = ledger or _ledger.default_ledger()

        def build(prev: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            prev_p = (prev or {}).get("payload") or {}
            if prev and all(prev_p.get(k) == v for k, v in content.items()):
                return None
            rev = int(prev_p.get("revision") or 0) + 1 if prev else 1
            return {"event_id": uuid.uuid4().hex, "event_type": "video_rating", "schema_version": _ledger.ENVELOPE_VERSION,
                    "occurred_at": occurred_at or _now(), "style_scope": style_scope, "project_id": project_id,
                    "generation_id": generation_id, "csv_sha256": None,
                    "payload": {**content, "revision": rev, "supersedes": prev["event_id"] if prev else None}}

        ev = led.append_revisioned(project_id, style_scope, "video_rating", generation_id, build)
        if ev is None:
            last = _latest_rating(led, project_id, style_scope, generation_id)
            return RatingResult(True, "unchanged", last["event_id"] if last else None,
                                int(((last or {}).get("payload") or {}).get("revision") or 0))
        rev = ev["payload"]["revision"]
        try:
            led.set_meta("analysis_stale", "1")
        except Exception:
            pass
        return RatingResult(True, "recorded" if rev == 1 else "revised", ev["event_id"], rev)
    except Exception:
        return RatingResult(False, "error", error="ledger_unavailable")


def _latest_rating(led: _ledger.Ledger, project_id: str, scope: str, generation_id: Optional[str]) -> Optional[Dict[str, Any]]:
    for e in led.events(event_type="video_rating", project_id=project_id, style_scope=scope, newest_first=True, limit=200):
        if (e.get("generation_id") or None) == (generation_id or None):
            return e
    return None
