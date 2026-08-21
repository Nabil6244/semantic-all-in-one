"""GUI-side client: finds the isolated Qwen Python and talks to the worker."""

from __future__ import annotations

import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from tts.base import CLONE_MODEL_ID, DEFAULT_LANGUAGE, TTSResult
from tts.errors import (
    TTSError,
    model_missing_message,
    package_missing_message,
)
from tts.model_cache import model_is_installed

LogFn = Callable[[str], None]
_ROOT = Path(__file__).resolve().parent.parent
_WORKER = Path(__file__).resolve().parent / "worker.py"


def _runtime_platform_id() -> Optional[str]:
    system = sys.platform
    machine = platform.machine().lower()
    if system == "win32" and machine in ("amd64", "x86_64", "x64"):
        return "win-amd64"
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return "darwin-arm64"
    return None


def _provisioned_qwen_python() -> Optional[Path]:
    pid = _runtime_platform_id()
    if not pid:
        return None
    root = Path.home() / ".videogen" / "runtime" / "qwen" / pid
    if pid == "win-amd64":
        candidates = [
            root / "python.exe",
            root / "Scripts" / "python.exe",
            root / "python" / "python.exe",
        ]
        names = ("python.exe",)
    else:
        candidates = [
            root / "bin" / "python",
            root / "bin" / "python3",
        ]
        names = ("python", "python3")
    for path in candidates:
        if path.is_file():
            return path
    if not root.is_dir():
        return None
    for name in names:
        for found in root.rglob(name):
            if found.is_file() and found.name in names:
                return found
    return None


def find_qwen_python() -> Optional[Path]:
    env = os.environ.get("QWEN_TTS_PYTHON", "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
    provisioned = _provisioned_qwen_python()
    if provisioned is not None:
        return provisioned
    local = _ROOT / ".venv-qwen" / "bin" / "python"
    if local.is_file():
        return local
    win = _ROOT / ".venv-qwen" / "Scripts" / "python.exe"
    if win.is_file():
        return win
    return None


def qwen_runtime_status() -> tuple[bool, str]:
    """Fast readiness check — do not fully import qwen_tts (Torch cold-start is slow)."""
    py = find_qwen_python()
    if py is None:
        return False, package_missing_message()
    # find_spec confirms the package is installed without loading Torch / qwen_tts.
    probe = (
        "import importlib.util, sys\n"
        "spec = importlib.util.find_spec('qwen_tts')\n"
        "sys.exit(0 if spec is not None else 1)\n"
    )
    try:
        proc = subprocess.run(
            [str(py), "-c", probe],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        if getattr(sys, "frozen", False):
            return False, (
                "Could not start the Qwen3-TTS runtime.\n\n"
                "Re-run the Video Generator installer."
            )
        return False, (
            "Could not start the Qwen3-TTS Python environment: "
            "timed out while checking the package.\n\n"
            "Try again, or recreate .venv-qwen."
        )
    except Exception as exc:
        return False, f"Could not start the Qwen3-TTS Python environment: {exc}"
    if proc.returncode != 0:
        return False, package_missing_message()
    if model_is_installed(CLONE_MODEL_ID):
        return True, "✓ Qwen 1.7B Voice Cloning Ready"
    return False, model_missing_message()


class QwenTTSClient:
    def __init__(
        self,
        python_bin: Optional[Path] = None,
        log: LogFn = print,
        ready_timeout: float = 30.0,
        job_timeout: float = 1200.0,
    ):
        self.python_bin = Path(python_bin) if python_bin else find_qwen_python()
        self._log = log
        self.ready_timeout = ready_timeout
        self.job_timeout = job_timeout
        self._proc: Optional[subprocess.Popen] = None
        self._stdout_q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._lock = threading.Lock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _emit(self, message: str) -> None:
        self._log(message)

    def start(self) -> None:
        if self.alive:
            return
        if self.python_bin is None or not Path(self.python_bin).is_file():
            raise TTSError(package_missing_message(), "package_missing")
        env = os.environ.copy()
        env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        env.setdefault("TOKENIZERS_PARALLELISM", "false")
        try:
            proc = subprocess.Popen(
                [str(self.python_bin), str(_WORKER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(_ROOT),
                env=env,
            )
        except OSError as exc:
            raise TTSError(
                f"Qwen3-TTS worker could not start: {exc}",
                "process_crash",
            ) from exc
        self._proc = proc
        self._stdout_q = queue.Queue()
        threading.Thread(target=self._forward_stderr, daemon=True).start()
        threading.Thread(target=self._forward_stdout, daemon=True).start()
        deadline = time.time() + self.ready_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                raise TTSError(
                    "Qwen3-TTS worker exited before it became ready. "
                    "The isolated Python environment may be incomplete.",
                    "process_crash",
                )
            line = self._readline(timeout=max(0.1, deadline - time.time()))
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ready":
                return
            if msg.get("type") == "error":
                raise TTSError(
                    msg.get("message") or package_missing_message(),
                    msg.get("code") or "process_crash",
                )
        raise TTSError(
            "Qwen3-TTS worker timed out while starting.",
            "timeout",
        )

    def _forward_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for raw in proc.stderr:
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self._emit(line)

    def _forward_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            self._stdout_q.put(raw.decode("utf-8", "replace"))

    def _readline(self, timeout: float) -> Optional[str]:
        try:
            return self._stdout_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def _send_and_wait(self, payload: dict, voice_fallback: str = "clone") -> TTSResult:
        self.start()
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise TTSError("Qwen3-TTS worker is not running.", "process_crash")
        try:
            proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            proc.stdin.flush()
        except BrokenPipeError as exc:
            raise TTSError(
                "Qwen3-TTS worker crashed while sending the generate request.",
                "process_crash",
            ) from exc
        deadline = time.time() + self.job_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                raise TTSError(
                    "Qwen3-TTS worker crashed during generation.",
                    "process_crash",
                )
            line = self._readline(timeout=min(1.0, max(0.1, deadline - time.time())))
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "result":
                return TTSResult(
                    path=Path(msg["path"]),
                    duration_seconds=float(msg["duration_seconds"]),
                    sample_rate=int(msg["sample_rate"]),
                    format=str(msg.get("format") or "wav"),
                    provider=str(msg.get("provider") or "qwen3-tts"),
                    voice=str(msg.get("voice") or voice_fallback),
                    generation_time_seconds=float(msg.get("generation_time_seconds") or 0),
                    load_time_seconds=float(msg.get("load_time_seconds") or 0),
                    device=str(msg.get("device") or ""),
                    model=str(msg.get("model") or CLONE_MODEL_ID),
                    local=bool(msg.get("local", True)),
                )
            if msg.get("type") == "ok":
                continue
            if msg.get("type") == "error":
                raise TTSError(
                    msg.get("message") or "Qwen3-TTS failed.",
                    msg.get("code") or "generation_failure",
                )
        raise TTSError(
            "Qwen3-TTS timed out while generating narration.",
            "TTS_TIMEOUT",
        )

    def _send_raw(self, payload: dict) -> dict:
        self.start()
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise TTSError("Qwen3-TTS worker is not running.", "process_crash")
        try:
            proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            proc.stdin.flush()
        except BrokenPipeError as exc:
            raise TTSError(
                "Qwen3-TTS worker crashed while sending the request.",
                "process_crash",
            ) from exc
        deadline = time.time() + self.job_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                raise TTSError(
                    "Qwen3-TTS worker crashed during the request.",
                    "process_crash",
                )
            line = self._readline(timeout=min(1.0, max(0.1, deadline - time.time())))
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "error":
                raise TTSError(
                    msg.get("message") or "Qwen3-TTS failed.",
                    msg.get("code") or "generation_failure",
                )
            if msg.get("type") in ("ok", "result"):
                return msg
        raise TTSError(
            "Qwen3-TTS timed out while waiting for the worker.",
            "TTS_TIMEOUT",
        )

    def build_voice_prompt(self, ref_audio: Path | str, ref_text: str, prompt_path: Path) -> None:
        with self._lock:
            self._send_raw(
                {
                    "op": "build_voice_prompt",
                    "ref_audio": str(ref_audio),
                    "ref_text": ref_text,
                    "prompt_path": str(prompt_path),
                }
            )

    def generate_clone(
        self,
        text: str,
        output_path: Path,
        *,
        voice_prompt_path: Optional[Path | str] = None,
        ref_audio: Optional[Path | str] = None,
        ref_text: Optional[str] = None,
        language: str = DEFAULT_LANGUAGE,
    ) -> TTSResult:
        payload = {
            "op": "generate_clone",
            "text": text,
            "output_path": str(Path(output_path)),
            "language": language,
        }
        if voice_prompt_path:
            payload["voice_prompt_path"] = str(voice_prompt_path)
        else:
            payload["ref_audio"] = str(ref_audio or "")
            payload["ref_text"] = ref_text or ""
        with self._lock:
            msg = self._send_raw(payload)
            if msg.get("type") != "result":
                raise TTSError("Unexpected worker response.", "generation_failure")
            return TTSResult(
                path=Path(msg["path"]),
                duration_seconds=float(msg["duration_seconds"]),
                sample_rate=int(msg["sample_rate"]),
                format=str(msg.get("format") or "wav"),
                provider=str(msg.get("provider") or "qwen3-tts"),
                voice=str(msg.get("voice") or "clone"),
                generation_time_seconds=float(msg.get("generation_time_seconds") or 0),
                load_time_seconds=float(msg.get("load_time_seconds") or 0),
                device=str(msg.get("device") or ""),
                model=str(msg.get("model") or CLONE_MODEL_ID),
                local=bool(msg.get("local", True)),
            )

    def generate(
        self,
        text: str,
        output_path: Path,
        *,
        voice_prompt_path: Optional[Path | str] = None,
        ref_audio: Optional[Path | str] = None,
        ref_text: Optional[str] = None,
        language: str = DEFAULT_LANGUAGE,
        **kwargs,
    ) -> TTSResult:
        return self.generate_clone(
            text,
            output_path,
            voice_prompt_path=voice_prompt_path,
            ref_audio=ref_audio,
            ref_text=ref_text,
            language=language,
        )

    def shutdown(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin:
                proc.stdin.write(b'{"op":"shutdown"}\n')
                proc.stdin.flush()
                proc.wait(timeout=8)
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self._proc = None


_client: Optional[QwenTTSClient] = None
_client_lock = threading.Lock()


def get_shared_client(log: LogFn = print) -> QwenTTSClient:
    global _client
    with _client_lock:
        if _client is None or not _client.alive:
            _client = QwenTTSClient(log=log)
        else:
            _client._log = log
        return _client


def shutdown_shared_client() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            _client.shutdown()
            _client = None
