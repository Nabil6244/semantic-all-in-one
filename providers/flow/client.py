"""
Synchronous Python client for the flow-engine's WebSocket protocol
(ws://127.0.0.1:<port>/ws). Message shapes match flow-engine/server.js exactly
— that file is the single source of truth for the protocol, not this one.

The underlying `websockets` library is asyncio-based; this class runs its own
event loop on a dedicated background thread and exposes plain blocking methods,
so callers (video_generator.py, app.py's worker thread) never need to touch
asyncio.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Callable, Dict, List, Optional

import websockets


class FlowClientError(Exception):
    pass


class FlowClient:
    def __init__(self, url: str, log: Callable[[str], None] = print):
        self.url = url
        self.log = log
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._connected = threading.Event()
        self._connect_error: Optional[str] = None
        self._state: Dict = {}
        self._info: Dict = {}
        self._state_lock = threading.Lock()
        self._subscribers: List[Callable[[dict], None]] = []
        self._closed = False

    # ---------- lifecycle ----------

    def connect(self, timeout: float = 10.0) -> None:
        """Idempotent once actually connected; otherwise (re-)attempts a connection.

        Bug fixed here: the old guard was `if self._thread is not None: return`,
        which made this a no-op on ANY second call — including a retry after a
        failed first attempt (the normal case: the engine's Node process is still
        booting when the first connect attempt happens, so callers like
        FlowEngineManager.start() retry in a loop). That silently "succeeded"
        without ever actually connecting (self._ws stayed None), so send() failed
        with "not connected" right after a log line saying the engine connected.
        Confirmed via direct reproduction — see report.
        """
        if self._ws is not None:
            return
        self._connect_error = None
        self._connected.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout):
            raise FlowClientError(f"Timed out connecting to {self.url}")
        if self._connect_error:
            raise FlowClientError(self._connect_error)

    def close(self) -> None:
        self._closed = True
        if self._loop is not None and self._ws is not None:
            fut = asyncio.run_coroutine_threadsafe(self._safe_close(), self._loop)
            try:
                fut.result(timeout=5)
            except Exception:
                pass

    async def _safe_close(self) -> None:
        try:
            await self._ws.close()
        except Exception:
            pass

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_and_listen())
        except Exception as exc:  # connection never established, or dropped
            self._connect_error = self._connect_error or str(exc)
            self._connected.set()

    async def _connect_and_listen(self) -> None:
        try:
            async with websockets.connect(self.url, open_timeout=10) as ws:
                self._ws = ws
                self._connected.set()
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    self._handle_message(msg)
        except Exception as exc:
            self._connect_error = str(exc)
            self._connected.set()

    def _handle_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == "STATE":
            with self._state_lock:
                self._state = msg
        elif mtype == "INFO":
            with self._state_lock:
                self._info = msg
        for fn in list(self._subscribers):
            try:
                fn(msg)
            except Exception as exc:
                self.log(f"[FLOW] subscriber error: {exc}")

    # ---------- low-level ----------

    def subscribe(self, fn: Callable[[dict], None]) -> Callable[[], None]:
        self._subscribers.append(fn)

        def unsubscribe() -> None:
            if fn in self._subscribers:
                self._subscribers.remove(fn)

        return unsubscribe

    def get_state(self) -> dict:
        with self._state_lock:
            return dict(self._state)

    def get_info(self) -> dict:
        with self._state_lock:
            return dict(self._info)

    def send(self, message: dict) -> None:
        if not self._loop or not self._ws:
            raise FlowClientError("FlowClient is not connected")
        fut = asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(message)), self._loop)
        fut.result(timeout=10)

    def wait_for(self, predicate: Callable[[dict], bool], timeout: float = 600.0) -> dict:
        """Block the calling (non-async) thread until a message matching `predicate`
        arrives, or raise FlowClientError on timeout."""
        result_q: "queue.Queue[dict]" = queue.Queue()

        def watcher(msg: dict) -> None:
            if predicate(msg):
                result_q.put(msg)

        unsubscribe = self.subscribe(watcher)
        try:
            return result_q.get(timeout=timeout)
        except queue.Empty:
            raise FlowClientError("Timed out waiting for the Flow engine to respond.")
        finally:
            unsubscribe()

    # ---------- protocol convenience wrappers (mirror server.js message types) ----------

    def add_account(self, label: str) -> None:
        self.send({"type": "ADD_ACCOUNT", "label": label})

    def login(self, account_id: str) -> None:
        self.send({"type": "LOGIN", "accountId": account_id})

    def refresh(self, account_id: Optional[str] = None) -> None:
        self.send({"type": "REFRESH", "accountId": account_id})

    def rename(self, account_id: str, label: str) -> None:
        self.send({"type": "RENAME", "accountId": account_id, "label": label})

    def delete_account(self, account_id: str) -> None:
        self.send({"type": "DELETE", "accountId": account_id})

    def stop(self) -> None:
        self.send({"type": "STOP"})

    def generate(
        self,
        prompts: List[str],
        settings: Optional[dict] = None,
        account_ids: Optional[List[str]] = None,
    ) -> None:
        """`prompts` is newline-joined — server.js splits on \\r?\\n, matching the
        original HUD's textarea input exactly (see flow-engine/server.js GENERATE)."""
        self.send(
            {
                "type": "GENERATE",
                "prompts": "\n".join(prompts),
                "settings": settings or {},
                "accountIds": account_ids,
            }
        )
