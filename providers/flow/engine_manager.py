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

from providers.playwright_chromium import (
    ensure_playwright_chromium,
    is_playwright_chromium_installed,
)
from providers import hidden_subprocess

from .client import FlowClient, FlowClientError

DEFAULT_PORT = 8787


class FlowEngineError(Exception):
    pass


def engine_code_version(engine_dir: Path) -> str:
    """Fingerprint of flow-engine's code on disk — MUST match server.js's
    ENGINE_CODE_VERSION (server.js + lib/*.js, sorted, sha256 of
    path\0content\0 for each)."""
    import hashlib

    root = Path(engine_dir)
    try:
        files = ["server.js"] + [f"lib/{p.name}" for p in sorted((root / "lib").glob("*.js"), key=lambda p: p.name)]
        digest = hashlib.sha256()
        for rel in files:
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            digest.update((root / rel).read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()[:16]
    except OSError:
        return "unknown"


def _pids_listening_on(port: int) -> list[int]:
    """PIDs listening on a local TCP port (macOS/Linux: lsof; Windows: netstat)."""
    try:
        if sys.platform == "win32":
            out = hidden_subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True, timeout=10)
            pids = set()
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
                    pids.add(int(parts[4]))
            return sorted(pids)
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True, timeout=10).stdout
        return sorted({int(x) for x in out.split() if x.strip().isdigit()})
    except Exception:
        return []


def _is_flow_engine_process(pid: int) -> bool:
    """Only ever terminate a Node process running flow-engine's server.js."""
    try:
        if sys.platform == "win32":
            out = hidden_subprocess.check_output(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"], text=True, timeout=10)
        else:
            out = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True,
                                 timeout=10).stdout
        low = out.lower()
        return "node" in low and "server.js" in low
    except Exception:
        return False


def _terminate_pid(pid: int, force: bool = False) -> None:
    try:
        if sys.platform == "win32":
            hidden_subprocess.check_output(["taskkill", "/PID", str(pid), "/T", "/F"], text=True, timeout=10)
        else:
            import signal

            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            out = hidden_subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/NH"], text=True, timeout=10)
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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
        """True when Playwright Chromium is in the user cache (shared with YouTube)."""
        return is_playwright_chromium_installed()

    def ensure_browser(self) -> None:
        """Ensure a browser exists for Flow (Chrome or Playwright Chromium).

        Packaged apps call this automatically before starting the Flow engine so
        users never need `npm run install-browser`. Skips download when system
        Chrome is present or Chromium is already cached.
        """
        node_bin = _find_node_binary()
        if node_bin is None:
            raise FlowEngineError(
                "Node.js was not found (bundled or on PATH). Cannot download "
                "Playwright Chromium for Flow/AI."
            )
        try:
            ensure_playwright_chromium(
                engine_dir=self.engine_dir,
                node_bin=node_bin,
                log=self.log,
            )
        except RuntimeError as exc:
            raise FlowEngineError(str(exc)) from exc

    def setup_instructions(self) -> str:
        # Packaged builds bundle node_modules already (see flow-engine/README.md and
        # VideoGenerator.spec) — this only fires for a dev checkout that hasn't run
        # `npm install` yet. Chromium itself is fetched on first Flow use via
        # ensure_browser() (same as `npm run install-browser`).
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
        cached = self._client
        if cached is not None and hasattr(cached, "is_alive") and not cached.is_alive():
            # The engine behind the cached connection is gone (exited,
            # restarted, or retired as outdated): connect afresh — through
            # the code-version check below — instead of returning a dead client.
            self._client = None
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

            # Chromium is not bundled in the DMG/zip (size); download once into the
            # user Playwright cache before the engine can open Flow browsers.
            # Prefer system Chrome when present (flow-engine/lib/accounts.js), but
            # Chromium must exist as the fallback on fresh machines without Chrome.
            self.ensure_browser()

            # Reuse an already-running engine on this port if one answers (e.g. a
            # prior app instance that wasn't cleanly stopped, or the engine started
            # manually for debugging) instead of unconditionally spawning a second
            # process — confirmed against a real engine that spawning blind wastes a
            # process and loses the port race unpredictably (see report).
            probe = FlowClient(self.url, log=self.log)
            try:
                probe.connect(timeout=1.5)
            except FlowClientError:
                probe = None
            if probe is not None and not self._running_engine_is_current(probe):
                # Node only loads code at start: an engine left running across
                # an app update keeps executing its OLD code (measured: a
                # 3-day-old engine still used the retired direct-RPC video path
                # after the app moved Flow video to the UI path). Replace it.
                self.log("[FLOW] The running Flow engine is from an older app version — restarting it.")
                self._retire_running_engine(probe)
                probe = None
            try:
                if probe is None:
                    raise FlowClientError("no reusable engine")
                self._client = probe
                self.log(f"[FLOW] Reusing an already-running engine on port {self.port}.")
                # App relaunch often leaves `running: true` with no live batch —
                # clear it so the first GENERATE does not fail every scene.
                try:
                    if probe.get_state().get("running"):
                        self.log("[FLOW] Clearing stuck running flag on reused engine...")
                        probe.reset_generate()
                except Exception:
                    pass
                return probe
            except FlowClientError:
                pass

            server_js = (self.engine_dir / "server.js").resolve()
            if not server_js.is_file():
                raise FlowEngineError(f"flow-engine server.js not found at {server_js}")

            self.log(f"[FLOW] Starting Flow engine ({self.engine_dir})...")
            env = dict(os.environ)
            env["SA_PORT"] = str(self.port)
            # Pass absolute server.js path so packaged Mac path checks always match
            # (relative argv + /var vs /private/var used to skip startServer → exit 0).
            # CREATE_NO_WINDOW on Windows — otherwise node.exe flashes a black CMD box.
            self._proc = hidden_subprocess.popen(
                [node_bin, str(server_js)],
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

    def _running_engine_is_current(self, client: "FlowClient", wait_s: float = 1.5) -> bool:
        """True when the engine answering on our port reports the same code
        fingerprint as the engine files on disk. The INFO message arrives
        right after connect; an engine from before fingerprints existed never
        sends one and is therefore treated as outdated."""
        expected = engine_code_version(self.engine_dir)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            reported = (client.get_info() or {}).get("codeVersion")
            if reported:
                return reported == expected
            time.sleep(0.05)
        return False

    def _retire_running_engine(self, client: "FlowClient") -> None:
        """Stop an outdated engine on our port so a current one can start.
        Asks it to exit (engines with SHUTDOWN support), then — for older
        engines that predate it — terminates the process that owns the port,
        but only after confirming it is a Node ``server.js``. If it still
        can't be freed, fail clearly rather than silently run old code."""
        old_pids = [pid for pid in _pids_listening_on(self.port) if _is_flow_engine_process(pid)]
        try:
            client.send({"type": "SHUTDOWN"})
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass
        if not self._wait_port_free(3.0):
            for pid in old_pids:
                _terminate_pid(pid)
        # A graceful stop frees the port but can hang while other clients
        # (e.g. another app window) keep their WebSocket open — measured: the
        # old engine lingered, still serving that client with outdated code.
        # Give it a moment, then force it (verified flow-engine PIDs only).
        deadline = time.time() + 4.0
        while old_pids and time.time() < deadline and any(_pid_alive(p) for p in old_pids):
            time.sleep(0.2)
        for pid in old_pids:
            if _pid_alive(pid):
                _terminate_pid(pid, force=True)
        if not self._wait_port_free(8.0):
            raise FlowEngineError(
                f"An older Flow engine is still running on port {self.port} and could not be stopped. "
                "Quit it (or restart the computer), then try again."
            )

    def _wait_port_free(self, timeout: float) -> bool:
        import socket

        deadline = time.time() + timeout
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.3)
                if sock.connect_ex(("127.0.0.1", self.port)) != 0:
                    return True
            time.sleep(0.2)
        return False

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
            pid = self._proc.pid
            if sys.platform == "win32":
                # Popen.terminate() on Windows is TerminateProcess on this PID only —
                # it does NOT kill the Chrome/Playwright children Node spawned under
                # it, so they're left running as orphans (confirmed: a single leftover
                # node.exe accumulated ~50 orphaned chrome.exe processes across
                # restarts because start() reuses a still-listening engine instead of
                # replacing it). taskkill /T kills the whole process tree.
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                        timeout=timeout,
                    )
                except Exception:
                    pass
                try:
                    self._proc.wait(timeout=timeout)
                except Exception:
                    pass
            else:
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
