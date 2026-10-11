"""Test helpers for the Enoch Template work (not a test module).

`NoPaidCalls` is the zero-cost guard the Enoch Template tests run under: inside it, any attempt to reach a paid or
external service raises and is counted, so a test (and the final two-minute render) can prove it made none:

  * a network connection to anything but this machine (every provider, `requests`, Gemini/Groq, Flow's browser traffic);
  * a Flow submission (FlowProvider.resolve / resolve_batch, FlowClient.generate);
  * an AI router completion (GeminiProvider / GroqProvider .complete);
  * launching Node, a Chrome/Chromium or Playwright process (how Flow's engine reaches Google).

Connections to this machine (127.0.0.1, ::1, localhost) and ffmpeg/ffprobe stay allowed: the app talks to itself and
renders locally. Nothing here changes behaviour outside the `with` block.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import socket
import subprocess
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
BLOCKED_PROGRAMS = ("node", "nodejs", "chrome", "chromium", "google-chrome", "chrome.exe", "chromium.exe", "node.exe", "playwright")


class PaidCallAttempt(AssertionError):
    """Something tried to reach a paid or external service inside `NoPaidCalls`."""


def normalized_sha256(path) -> str:
    """sha256 of a file with CRLF turned into LF, so a Windows checkout hashes like a macOS one."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _is_local(address) -> bool:
    host = address[0] if isinstance(address, (tuple, list)) and address else address
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    return str(host) in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "::", "") or str(host).startswith("127.")


class NoPaidCalls(contextlib.ContextDecorator):
    """Context manager / decorator. `.attempts` lists what was refused; `.assert_clean()` fails if anything was."""

    def __init__(self) -> None:
        self.attempts: list = []
        self._stack = contextlib.ExitStack()

    def _refuse(self, what: str):
        self.attempts.append(what)
        raise PaidCallAttempt(f"blocked inside NoPaidCalls: {what}")

    def __enter__(self) -> "NoPaidCalls":
        real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
        real_getaddrinfo = socket.getaddrinfo
        real_popen = subprocess.Popen.__init__
        guard = self

        def connect(sock, address, *a, **k):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address):
                guard._refuse(f"network connection to {address!r}")
            return real_connect(sock, address, *a, **k)

        def connect_ex(sock, address, *a, **k):
            if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address):
                guard._refuse(f"network connection to {address!r}")
            return real_connect_ex(sock, address, *a, **k)

        def getaddrinfo(host, *a, **k):
            if not _is_local((host,)):
                guard._refuse(f"DNS lookup of {host!r}")
            return real_getaddrinfo(host, *a, **k)

        def popen(proc, args, *a, **k):
            argv = args if isinstance(args, (list, tuple)) else [str(args)]
            program = os.path.basename(str(argv[0])).lower() if argv else ""
            if program in BLOCKED_PROGRAMS:
                guard._refuse(f"process {program}")
            return real_popen(proc, args, *a, **k)

        self._stack.enter_context(mock.patch.object(socket.socket, "connect", connect))
        self._stack.enter_context(mock.patch.object(socket.socket, "connect_ex", connect_ex))
        self._stack.enter_context(mock.patch.object(socket, "getaddrinfo", getaddrinfo))
        self._stack.enter_context(mock.patch.object(subprocess.Popen, "__init__", popen))
        for dotted in (
            "providers.flow.provider.FlowProvider.resolve",
            "providers.flow.provider.FlowProvider.resolve_batch",
            "providers.flow.client.FlowClient.generate",
            "ai_router.providers.GeminiProvider.complete",
            "ai_router.providers.GroqProvider.complete",
        ):
            module, _, attr = dotted.rpartition(".")
            owner, _, cls = module.rpartition(".")
            try:
                target = getattr(__import__(owner, fromlist=[cls]), cls)
            except Exception:  # a module that cannot even be imported here cannot make a call either
                continue
            self._stack.enter_context(
                mock.patch.object(target, attr, lambda *a, _d=dotted, **k: guard._refuse(_d)))
        return self

    def __exit__(self, *exc) -> bool:
        self._stack.close()
        return False

    def assert_clean(self) -> None:
        if self.attempts:
            raise PaidCallAttempt("refused attempts: " + "; ".join(self.attempts))
