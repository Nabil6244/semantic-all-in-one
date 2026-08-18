"""
FlowEngineManager: launches/health-checks/stops the flow-engine Node sidecar
(flow-engine/server.js) as a background subprocess bound to 127.0.0.1, and
hands back a connected FlowClient. Video Generator never talks to Node
directly — everything goes through this manager + FlowClient.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .client import FlowClient, FlowClientError

DEFAULT_PORT = 8787


class FlowEngineError(Exception):
    pass


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _candidate_roots() -> list[Path]:
    """Places flow-engine/ and bin/node might live: dev checkout, PyInstaller's
    extracted bundle dir, or next to the packaged executable (onedir builds)."""
    here = Path(__file__).resolve()
    dev_root = here.parent.parent.parent  # providers/flow/engine_manager.py -> project root
    roots = [dev_root]
    if _is_frozen():
        if hasattr(sys, "_MEIPASS"):
            roots.insert(0, Path(sys._MEIPASS))
        roots.insert(0, Path(sys.executable).resolve().parent)
    return roots


def _find_flow_engine_dir() -> Path:
    for root in _candidate_roots():
        candidate = root / "flow-engine"
        if (candidate / "server.js").is_file():
            return candidate
    return _candidate_roots()[-1] / "flow-engine"


def _find_node_binary() -> Optional[str]:
    """Prefer the bundled portable Node runtime (bin/node, bin/node.exe) so users
    never need Node.js installed — same pattern as app.py's ensure_ffmpeg_on_path().
    Falls back to PATH for local development."""
    name = "node.exe" if sys.platform == "win32" else "node"
    for root in _candidate_roots():
        candidate = root / "bin" / name
        if candidate.is_file():
            if sys.platform != "win32":
                mode = candidate.stat().st_mode
                if not (mode & 0o111):
                    candidate.chmod(mode | 0o111)
            return str(candidate)
    which = shutil.which("node")
    return which


class FlowEngineManager:
    def __init__(self, engine_dir: Optional[Path] = None, port: int = DEFAULT_PORT, log: Callable[[str], None] = print):
        self.engine_dir = Path(engine_dir) if engine_dir else _find_flow_engine_dir()
        self.port = port
        self.log = log
        self._proc: Optional[subprocess.Popen] = None
        self._log_thread: Optional[threading.Thread] = None
        self._client: Optional[FlowClient] = None
        # start()/ensure_running() get called from multiple GUI threads (Settings'
        # auto-connect on open races a user immediately clicking Add Account) —
        # without this lock, two threads can both decide "nothing running yet" and
        # both spawn `node server.js`, and the second one crashes with EADDRINUSE,
        # silently failing whatever it was trying to send. Confirmed via a real
        # concurrent-thread reproduction (see report).
        self._start_lock = threading.Lock()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws"

    # ---------- setup checks ----------

    def is_installed(self) -> bool:
        return (self.engine_dir / "node_modules" / "ws").is_dir()

    def is_browser_installed(self) -> bool:
        """Best-effort check for Playwright's downloaded Chromium. Not exhaustive
        (Playwright's cache layout can vary by OS/version) — a real check happens
        implicitly the first time the engine tries to launch a browser; this is
        just enough to give an early, clearer error than a raw Node stack trace."""
        cache_candidates = [
            Path.home() / "Library" / "Caches" / "ms-playwright",  # macOS
            Path.home() / ".cache" / "ms-playwright",  # Linux
            Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",  # Windows
        ]
        return any(p.is_dir() and any(p.iterdir()) for p in cache_candidates if p.is_dir())

    def setup_instructions(self) -> str:
        # Packaged builds bundle node_modules already (see flow-engine/README.md and
        # VideoGenerator.spec) — this only fires for a dev checkout that hasn't run
        # `npm install` yet.
        return (
            f"Flow engine dependencies not installed. Run in a terminal:\n"
            f"  cd \"{self.engine_dir}\"\n"
            f"  npm install\n"
        )

    @staticmethod
    def node_available() -> bool:
        return _find_node_binary() is not None

    # ---------- lifecycle ----------

    def start(self, timeout: float = 20.0) -> FlowClient:
        if self._client is not None:
            return self._client

        with self._start_lock:
            # Re-check: another thread may have finished starting the engine while
            # we were waiting for the lock (e.g. Settings' auto-connect racing a
            # user clicking Add Account right away) — don't spawn a second one.
            if self._client is not None:
                return self._client

            node_bin = _find_node_binary()
            if node_bin is None:
                raise FlowEngineError(
                    "Node.js was not found (bundled or on PATH). Flow/AI generation needs it — "
                    "Stock and Manual scenes work fine without it. This shouldn't happen in a "
                    "packaged build; if you're running from source, install Node.js "
                    "(https://nodejs.org)."
                )
            if not self.engine_dir.is_dir():
                raise FlowEngineError(f"flow-engine directory not found at {self.engine_dir}")
            if not self.is_installed():
                raise FlowEngineError(self.setup_instructions())

            # Reuse an already-running engine on this port if one answers (e.g. a
            # prior app instance that wasn't cleanly stopped, or the engine started
            # manually for debugging) instead of unconditionally spawning a second
            # process — confirmed against a real engine that spawning blind wastes a
            # process and loses the port race unpredictably (see report).
            probe = FlowClient(self.url, log=self.log)
            try:
                probe.connect(timeout=1.5)
                self._client = probe
                self.log(f"[FLOW] Reusing an already-running engine on port {self.port}.")
                return probe
            except FlowClientError:
                pass

            self.log(f"[FLOW] Starting Flow engine ({self.engine_dir})...")
            env = dict(os.environ)
            env["SA_PORT"] = str(self.port)
            self._proc = subprocess.Popen(
                [node_bin, "server.js"],
                cwd=str(self.engine_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._log_thread = threading.Thread(target=self._pump_logs, daemon=True)
            self._log_thread.start()

            client = FlowClient(self.url, log=self.log)
            deadline = time.time() + timeout
            last_error: Optional[str] = None
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    raise FlowEngineError(
                        f"Flow engine process exited immediately (code {self._proc.returncode}). "
                        f"Check the log above for the Node error."
                    )
                try:
                    client.connect(timeout=2.0)
                    self._client = client
                    self.log("[FLOW] Engine connected.")
                    return client
                except FlowClientError as exc:
                    last_error = str(exc)
                    time.sleep(0.5)

            raise FlowEngineError(f"Flow engine did not become ready in time: {last_error}")

    def _pump_logs(self) -> None:
        if not self._proc or not self._proc.stdout:
            return
        for line in self._proc.stdout:
            line = line.rstrip()
            if line:
                self.log(f"[FLOW-ENGINE] {line}")

    def health_check(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self, timeout: float = 5.0) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=timeout)
        self._proc = None
        self.log("[FLOW] Engine stopped.")

    def ensure_running(self) -> FlowClient:
        if self._client is not None and self.health_check():
            return self._client
        self.log("[FLOW] Engine not running — starting it now.")
        return self.start()
