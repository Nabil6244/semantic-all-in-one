"""Packaged-build startup check: does the built app have what it needs to start and render?

Run by the built app itself when SYT_STARTUP_CHECK=<report.json> is set (app.main calls run() before any window opens), and by
CI on the Windows and macOS builds through scripts/check_packaged_startup.py. It imports the modules the app only imports inside
functions (the spec writes their names into the bundle as startup_check_modules.json), finds the bundled ffmpeg, ffprobe and Node
and runs each once, loads the graphics templates and the bundled SFX, and checks each render engine's entry file. A missing hidden
import or data file otherwise only shows up on a user's machine, the first time that style is used.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MODULES_FILE = "startup_check_modules.json"
FILES_FILE = "startup_check_files.json"      # runtime-read files the spec says must be in the bundle (relative to it)
# third-party packages every build needs (native extensions included); their optional submodules are not checked
CORE_PACKAGES = ("customtkinter", "PIL.Image", "av", "numpy", "faster_whisper", "ctranslate2", "requests", "websockets", "yt_dlp", "sounddevice")
ENGINE_FILES = ("pakmap-engine/render.mjs", "starmap-engine/render.mjs", "map-engine/render.mjs", "whatif-engine/render.mjs",
                "weather-engine/render.mjs", "gfx-overlay-engine/render.mjs", "flow-engine/server.js")


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _modules(root: Path) -> List[str]:
    f = root / MODULES_FILE
    if not f.is_file():
        return []
    return [str(m) for m in json.loads(f.read_text(encoding="utf-8"))]


def _runs(exe: Optional[str], arg: str) -> Optional[str]:
    """None when `exe arg` runs and exits 0, else why not."""
    if not exe:
        return "not found"
    try:
        from providers.hidden_subprocess import run as _run   # no console window flashes on Windows
    except Exception:
        _run = subprocess.run
    try:
        r = _run([str(exe), arg], capture_output=True, timeout=60)
    except Exception as exc:
        return f"{exe}: {exc}"
    return None if r.returncode == 0 else f"{exe} {arg} exited {r.returncode}"


def run(report_path: str, ffmpeg: Optional[Callable[[], Optional[Path]]] = None) -> int:
    """Write the report to `report_path`; 0 when every check passed, 1 otherwise."""
    t0 = time.monotonic()
    root = bundle_root()
    failures: List[str] = []
    checks: Dict[str, Any] = {"frozen": bool(getattr(sys, "frozen", False)), "platform": sys.platform, "python": sys.version.split()[0],
                              "bundle_root": str(root)}

    listed = _modules(root)
    if getattr(sys, "frozen", False) and not listed:
        failures.append(f"{MODULES_FILE} is missing from the bundle")
    imported = 0
    for name in list(CORE_PACKAGES) + listed:
        try:
            importlib.import_module(name)
            imported += 1
        except BaseException as exc:   # a native extension can raise SystemExit or worse on a bad build
            failures.append(f"import {name}: {type(exc).__name__}: {exc}")
    checks["modules_imported"] = imported

    try:
        found = ffmpeg() if ffmpeg is not None else None
        checks["ffmpeg"] = str(found) if found else None
        problem = _runs(str(found) if found else None, "-version")
        if problem:
            failures.append(f"ffmpeg: {problem}")
        if found:
            probe = Path(found).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
            problem = _runs(str(probe) if probe.is_file() else None, "-version")
            if problem:
                failures.append(f"ffprobe: {problem}")
    except Exception as exc:
        failures.append(f"ffmpeg: {exc}")

    try:
        from providers.flow.engine_manager import _find_node_binary

        node = _find_node_binary()
        checks["node"] = node
        problem = _runs(node, "--version")
        if problem:
            failures.append(f"node: {problem}")
    except Exception as exc:
        failures.append(f"node: {exc}")

    try:
        import gfx_templates

        n = len(gfx_templates.load_library())
        checks["gfx_templates"] = n
        if n == 0:
            failures.append(f"no graphics templates in {gfx_templates.library_dir()}")
    except Exception as exc:
        failures.append(f"graphics templates: {exc}")

    try:
        from sfx.seed import bundled_sfx_inventory

        inv = bundled_sfx_inventory()
        checks["sfx_wavs"] = inv.get("wav_count")
        if not inv.get("ok"):
            failures.append(f"bundled SFX: {inv}")
    except Exception as exc:
        failures.append(f"bundled SFX: {exc}")

    listed_files: List[str] = []
    if (root / FILES_FILE).is_file():
        listed_files = [str(x) for x in json.loads((root / FILES_FILE).read_text(encoding="utf-8"))]
    elif getattr(sys, "frozen", False):
        failures.append(f"{FILES_FILE} is missing from the bundle")
    lost = [x for x in listed_files if not (root / x).is_file()]
    checks["files_checked"] = len(listed_files)
    if lost:
        failures.append("files missing from the bundle: " + ", ".join(lost))
    missing = [p for p in ENGINE_FILES if not (root / p).is_file()]
    if missing:
        failures.append("engine files missing: " + ", ".join(missing))

    checks["seconds"] = round(time.monotonic() - t0, 1)
    report = {"ok": not failures, "failures": failures, "checks": checks}
    try:
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception:
        traceback.print_exc()
        return 1
    return 0 if not failures else 1
