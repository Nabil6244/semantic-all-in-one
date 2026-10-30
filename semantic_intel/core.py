"""Shared parts of the Semantic Intelligence Engine: the per-decision cache, bounded concurrent batches with independent retries, telemetry,
and the central `ai_planning` setting.

Router order for every decision: cache -> deterministic engine (when it is confident) -> Gemini (only when it matters and is allowed) -> rules.
A failed AI call never cancels another one and never stops a render: its decisions simply fall back to the rules."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

CACHE_VERSION = 1
AI_MODES = ("auto", "off", "full")


def ai_mode(settings: Optional[Mapping[str, Any]] = None) -> str:
    """The central AI planning switch (settings.json "ai_planning"): "auto" (default) uses Gemini only where the rules are unsure or the AI
    adds something the rules cannot, "off" never calls Gemini for planning, "full" asks Gemini for every decision as before this engine.
    The older "editorial_ai": false still turns the editorial director off."""
    raw = str((settings or {}).get("ai_planning") or "auto").strip().lower()
    return raw if raw in AI_MODES else "auto"


def ai_allowed(settings: Optional[Mapping[str, Any]], task: str = "") -> bool:
    """True when Gemini may be asked for `task` ("editorial", "ambience", "sfx"): the mode is not off, a key exists, and (editorial) the old
    editorial_ai flag was not switched off. No key -> False, so a missing credential can never stop a render."""
    s = settings or {}
    if ai_mode(s) == "off":
        return False
    if task == "editorial":
        flag = s.get("editorial_ai")
        if flag is False or str(flag).strip().lower() in ("0", "false", "off", "disabled"):
            return False
    try:
        from visual_director.llm import gemini_configured

        return bool(gemini_configured(s))
    except Exception:
        return False


def stable_key(*parts: Any) -> str:
    """Hash of the parts (JSON, sorted keys): the same input always gives the same key."""
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class DecisionCache:
    """One JSON file of {key: decision}; thread-safe, written atomically. `path=None` is an in-memory cache (tests, no project open)."""

    def __init__(self, path: Optional[Path]):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._items: Dict[str, Any] = {}
        self._dirty = False
        if self.path is not None and self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("v") == CACHE_VERSION and isinstance(data.get("items"), dict):
                    self._items = data["items"]
            except (OSError, ValueError):
                self._items = {}

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._items

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._items.get(key, default)

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._items[key] = value
            self._dirty = True

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def flush(self) -> None:
        if self.path is None:
            return
        with self._lock:
            if not self._dirty:
                return
            payload = json.dumps({"v": CACHE_VERSION, "items": self._items}, ensure_ascii=False)
            self._dirty = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass   # a cache that cannot be written only costs a re-ask next time


class Telemetry:
    """Counters per task: decisions by source, AI calls (ok / failed), AI seconds, wall seconds. Read by the report and the tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tasks: Dict[str, Dict[str, float]] = {}

    def add(self, task: str, **counts: float) -> None:
        with self._lock:
            t = self.tasks.setdefault(task, {})
            for k, v in counts.items():
                t[k] = t.get(k, 0) + v

    def reset(self) -> None:
        with self._lock:
            self.tasks = {}

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return {k: dict(v) for k, v in self.tasks.items()}

    def line(self, task: str, since: Optional[Mapping[str, float]] = None) -> str:
        """One summary line; with `since` (an earlier snapshot of this task) only what happened after it."""
        now = self.snapshot().get(task, {})
        t = {k: v - (since or {}).get(k, 0) for k, v in now.items()}
        total = int(t.get("decisions", 0))
        return (f"[SEMANTIC] {task}: {total} decision(s): {int(t.get('cache', 0))} cached, {int(t.get('ai', 0))} AI, {int(t.get('rules', 0))} rules; "
                f"{int(t.get('calls', 0))} AI call(s), {int(t.get('failed', 0))} failed, AI {t.get('ai_s', 0.0):.1f}s, total {t.get('wall_s', 0.0):.1f}s")


TELEMETRY = Telemetry()


def is_quota_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(m in text for m in ("exceeded your current quota", "resource_exhausted", "quota exceeded", "429"))


class BatchResult:
    __slots__ = ("index", "ok", "value", "error", "attempts", "seconds")

    def __init__(self, index: int, ok: bool, value: Any = None, error: str = "", attempts: int = 0, seconds: float = 0.0):
        self.index, self.ok, self.value, self.error, self.attempts, self.seconds = index, ok, value, error, attempts, seconds


def run_batches(batches: Sequence[Any], call: Callable[[Any], Any], *, workers: int = 3, retries: int = 2, backoff: float = 2.0,
                sleep: Callable[[float], None] = time.sleep, task: str = "") -> List[BatchResult]:
    """Run `call(batch)` for every batch with at most `workers` at once. A batch that raises is retried (up to `retries` more times, with a
    growing pause) on its own; a batch that still fails is reported as failed and every other batch is unaffected. Results come back in the
    order of `batches`, whatever order they finished in."""
    results: List[Optional[BatchResult]] = [None] * len(batches)
    out_of_quota = threading.Event()   # a spent quota will not recover within this run: stop asking, let the rules decide

    def one(i: int) -> None:
        t0 = time.monotonic()
        err = ""
        if out_of_quota.is_set():
            results[i] = BatchResult(i, False, None, "skipped: quota exhausted", 0, 0.0)
            return
        for attempt in range(1, retries + 2):
            try:
                value = call(batches[i])
                dt = time.monotonic() - t0
                results[i] = BatchResult(i, True, value, "", attempt, dt)
                if task:
                    TELEMETRY.add(task, calls=attempt, failed=attempt - 1, ai_s=dt)
                return
            except Exception as exc:   # noqa: BLE001 - a failed batch must never take the others down
                err = f"{type(exc).__name__}: {exc}"
                if is_quota_error(exc):
                    out_of_quota.set()
                    results[i] = BatchResult(i, False, None, err, attempt, time.monotonic() - t0)
                    if task:
                        TELEMETRY.add(task, calls=attempt, failed=attempt, ai_s=time.monotonic() - t0)
                    return
                if attempt <= retries:
                    sleep(backoff * attempt)
        dt = time.monotonic() - t0
        results[i] = BatchResult(i, False, None, err, retries + 1, dt)
        if task:
            TELEMETRY.add(task, calls=retries + 1, failed=retries + 1, ai_s=dt)

    if not batches:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(batches)))) as ex:
        for f in [ex.submit(one, i) for i in range(len(batches))]:
            try:
                f.result(timeout=900)      # a batch stuck past 15 minutes is left out (its rows keep the rule-based reading), never waited on forever
            except FuturesTimeout:
                pass
    return [r for r in results if r is not None]
