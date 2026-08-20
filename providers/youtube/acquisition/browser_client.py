"""Python sidecar for the persistent Chrome YouTube capture worker."""

from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

LogFn = Callable[[str], None]

_DIR = Path(__file__).resolve().parent
_WORKER = _DIR / "browser_worker.mjs"
_PROJECT_ROOT = _DIR.parent.parent.parent
_lock = threading.Lock()
_log: LogFn = print
_client: Optional["BrowserPlaybackClient"] = None


def set_log(log: LogFn) -> None:
    global _log
    _log = log


def _emit(msg: str) -> None:
    _log(msg)


def _find_node() -> Optional[str]:
    name = "node.exe" if sys.platform == "win32" else "node"
    bundled = _PROJECT_ROOT / "bin" / name
    if bundled.is_file():
        return str(bundled)
    return shutil.which("node")


def _chrome_available() -> bool:
    env = os.environ.get("YOUTUBE_CHROME_PATH")
    if env and Path(env).is_file():
        return True
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.is_file():
        return True
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return True
    cache_candidates = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
        Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",
    ]
    return any(p.is_dir() and any(p.iterdir()) for p in cache_candidates if str(p) != "." and p.is_dir())


def browser_available() -> bool:
    """Cheap, no-network check: worker can be started on this machine."""
    if not _find_node():
        return False
    if not _WORKER.is_file():
        return False
    if not (_DIR / "node_modules" / "playwright-core").is_dir():
        return False
    return _chrome_available()


class BrowserPlaybackClient:
    def __init__(
        self,
        node_bin: Optional[str] = None,
        worker_script: Optional[Path] = None,
        popen_factory=None,
        job_timeout: float = 180.0,
        ready_timeout: float = 30.0,
    ):
        self.node_bin = node_bin or _find_node()
        self.worker_script = Path(worker_script) if worker_script else _WORKER
        self._popen_factory = popen_factory or subprocess.Popen
        self.job_timeout = job_timeout
        self.ready_timeout = ready_timeout
        self._proc: Optional[subprocess.Popen] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stdout_q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._job_lock = threading.Lock()
        self._restarts_left = 1
        self.jobs_completed = 0

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _forward_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw in proc.stderr:
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                _emit(line)

    def start(self) -> None:
        if self.alive:
            return
        if not self.node_bin:
            raise RuntimeError("node is not available")
        env = os.environ.copy()
        proc = self._popen_factory(
            [self.node_bin, str(self.worker_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.worker_script.parent),
            env=env,
        )
        self._proc = proc
        self._stdout_q = queue.Queue()
        self._stderr_thread = threading.Thread(target=self._forward_stderr, daemon=True)
        self._stdout_thread = threading.Thread(target=self._forward_stdout, daemon=True)
        self._stderr_thread.start()
        self._stdout_thread.start()
        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("browser worker exited before ready")
            line = self._readline(timeout=deadline - time.time())
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ready":
                return
            if msg.get("type") == "fatal":
                raise RuntimeError(msg.get("error") or "browser worker fatal")
        raise RuntimeError("timed out waiting for browser worker ready")

    def _forward_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            self._stdout_q.put(raw.decode("utf-8", "replace"))
        self._stdout_q.put(None)

    def _readline(self, timeout: float) -> Optional[str]:
        try:
            line = self._stdout_q.get(timeout=max(0.05, timeout))
        except queue.Empty:
            return None
        return line

    def _write(self, payload: dict) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("browser worker is not running")
        proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin:
                proc.stdin.write(b'{"cmd":"shutdown"}\n')
                proc.stdin.flush()
                proc.wait(timeout=5)
        except Exception:
            pass
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
        self._proc = None

    def _ensure(self) -> None:
        if self.alive:
            return
        self.start()

    def acquire(
        self,
        video_id: str,
        start: float,
        duration: float,
        dest: Path,
        ffmpeg: Optional[str] = None,
    ) -> dict:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        job = {
            "id": f"{video_id}-{time.time():.0f}",
            "video_id": video_id,
            "start": float(start),
            "duration": float(duration),
            "out": str(dest),
            "ffmpeg": ffmpeg or shutil.which("ffmpeg") or "ffmpeg",
        }
        with self._job_lock:
            return self._acquire_locked(job)

    def _acquire_locked(self, job: dict) -> dict:
        try:
            self._ensure()
        except Exception as exc:
            return {"ok": False, "kind": "browser_crashed", "error": str(exc)}
        try:
            self._write(job)
        except Exception as exc:
            return self._retry_or_crash(job, f"write failed: {exc}")
        timeout = max(self.job_timeout, 30.0 + float(job.get("duration") or 0) * 4)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                return self._retry_or_crash(job, "browser worker process exited")
            line = self._readline(timeout=min(1.0, deadline - time.time()))
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ready":
                continue
            if msg.get("id") == job["id"] or "ok" in msg:
                if msg.get("ok"):
                    self.jobs_completed += 1
                return msg
            if msg.get("type") == "fatal":
                return self._retry_or_crash(job, msg.get("error") or "fatal")
        return {"ok": False, "kind": "timeout", "error": "timed out waiting for browser acquisition"}

    def _retry_or_crash(self, job: dict, error: str) -> dict:
        self.stop()
        if self._restarts_left <= 0:
            return {"ok": False, "kind": "browser_crashed", "error": error}
        self._restarts_left -= 1
        _emit("[BROWSER] worker crashed; restarting once")
        try:
            self.start()
            self._write(job)
        except Exception as exc:
            return {"ok": False, "kind": "browser_crashed", "error": str(exc)}
        timeout = max(self.job_timeout, 30.0)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                return {"ok": False, "kind": "browser_crashed", "error": error}
            line = self._readline(timeout=min(1.0, deadline - time.time()))
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == job["id"] or "ok" in msg:
                if msg.get("ok"):
                    self.jobs_completed += 1
                return msg
        return {"ok": False, "kind": "timeout", "error": "timed out after worker restart"}


def get_client() -> BrowserPlaybackClient:
    global _client
    with _lock:
        if _client is None:
            _client = BrowserPlaybackClient()
        return _client


def shutdown_client() -> None:
    global _client
    with _lock:
        if _client is not None:
            _client.stop()
            _client = None


atexit.register(shutdown_client)
