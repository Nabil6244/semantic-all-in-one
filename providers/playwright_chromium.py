"""One-time Playwright Chromium download for Flow / YouTube browser automation.

Packaged builds ship Node + flow-engine `node_modules` (including `playwright`)
but not the ~150MB Chromium binary. On first Flow/AI (or YouTube browser)
use we run `node …/playwright/cli.js install chromium` into the user's
Playwright cache when system Google Chrome is not available. System Chrome is
preferred when present; this module covers the Chromium fallback path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from providers import hidden_subprocess

LogFn = Callable[[str], None]

_ENSURE_LOCK = threading.Lock()


def playwright_cache_dirs() -> list[Path]:
    return [
        Path.home() / "Library" / "Caches" / "ms-playwright",  # macOS
        Path.home() / ".cache" / "ms-playwright",  # Linux
        Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",  # Windows
    ]


def is_playwright_chromium_installed() -> bool:
    """True when Playwright's Chromium build is already in the user cache."""
    for cache in playwright_cache_dirs():
        if not cache.is_dir():
            continue
        try:
            for child in cache.iterdir():
                if child.is_dir() and child.name.startswith("chromium"):
                    return True
        except OSError:
            continue
    return False


def system_chrome_available() -> bool:
    """Best-effort: Google Chrome (or Chromium) usable via Playwright channel."""
    env = os.environ.get("YOUTUBE_CHROME_PATH") or os.environ.get("CHROME_PATH")
    if env and Path(env).is_file():
        return True
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.is_file():
        return True
    if sys.platform == "win32":
        for candidate in (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
        ):
            if candidate.is_file():
                return True
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return True
    return False


def playwright_cli(engine_dir: Path) -> Optional[Path]:
    """Path to flow-engine's playwright CLI (preferred) or None."""
    cli = Path(engine_dir) / "node_modules" / "playwright" / "cli.js"
    return cli if cli.is_file() else None


def can_install_playwright_chromium(engine_dir: Path, node_bin: Optional[str]) -> bool:
    return bool(node_bin) and playwright_cli(engine_dir) is not None


def ensure_playwright_chromium(
    *,
    engine_dir: Path,
    node_bin: str,
    log: LogFn = print,
    timeout: float = 600.0,
    skip_if_system_chrome: bool = True,
) -> None:
    """Download Chromium once if missing. Safe to call from multiple threads.

    When skip_if_system_chrome is True (default), no download happens if Google
    Chrome is already installed — Flow/YouTube prefer the Chrome channel first.
    """
    if skip_if_system_chrome and system_chrome_available():
        return
    if is_playwright_chromium_installed():
        return

    with _ENSURE_LOCK:
        if skip_if_system_chrome and system_chrome_available():
            return
        if is_playwright_chromium_installed():
            return

        cli = playwright_cli(engine_dir)
        if cli is None:
            raise RuntimeError(
                f"Playwright is not installed under {engine_dir} "
                "(expected node_modules/playwright). Cannot download Chromium."
            )

        log(
            "[BROWSER] Playwright Chromium not found — downloading once "
            "(one-time; may take a few minutes)…"
        )
        try:
            proc = hidden_subprocess.run(
                [node_bin, str(cli), "install", "chromium"],
                cwd=str(engine_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Timed out downloading Playwright Chromium. Check your network "
                "and try opening Settings → AI / Flow again."
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to start Playwright Chromium install: {exc}") from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise RuntimeError(
                "Playwright Chromium download failed. "
                f"Exit code {proc.returncode}. {detail}"
            )

        if not is_playwright_chromium_installed():
            raise RuntimeError(
                "Playwright reported success but Chromium is still missing from "
                "the browser cache. Try again or install Google Chrome."
            )

        log("[BROWSER] Playwright Chromium ready.")
