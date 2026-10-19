#!/usr/bin/env python3
"""Start the built app in its startup-check mode and fail when anything it needs is missing (see startup_check.py).

Usage: python scripts/check_packaged_startup.py [path to the built executable]
Default: the PyInstaller output for this platform (dist/Semantic YT Studio/Semantic YT Studio.exe on Windows,
dist/Semantic YT Studio.app/Contents/MacOS/Semantic YT Studio on macOS).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_S = 300


def default_exe() -> Path:
    if sys.platform == "win32":
        return ROOT / "dist" / "Semantic YT Studio" / "Semantic YT Studio.exe"
    if sys.platform == "darwin":
        return ROOT / "dist" / "Semantic YT Studio.app" / "Contents" / "MacOS" / "Semantic YT Studio"
    return ROOT / "dist" / "Semantic YT Studio" / "Semantic YT Studio"


def main(argv: list) -> int:
    exe = Path(argv[1]) if len(argv) > 1 else default_exe()
    if not exe.is_file():
        print(f"::error::built app not found: {exe}")
        return 1
    with tempfile.TemporaryDirectory() as d:
        report = Path(d) / "startup_report.json"
        env = dict(os.environ, SYT_STARTUP_CHECK=str(report))
        # run from a neutral folder so nothing resolves against the source checkout by accident
        try:
            proc = subprocess.run([str(exe)], env=env, cwd=d, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            print(f"::error::the built app did not finish its startup check in {TIMEOUT_S} s")
            return 1
        if not report.is_file():
            print(f"::error::the built app wrote no startup report (exit code {proc.returncode})")
            print(proc.stdout[-4000:])
            print(proc.stderr[-4000:])
            return 1
        data = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(data, indent=2))
    if not data.get("ok") or proc.returncode != 0:
        for f in data.get("failures") or []:
            print(f"::error::{f}")
        return 1
    if not data.get("checks", {}).get("frozen"):
        print("::error::the startup check did not run inside the built app")
        return 1
    print("Packaged app startup check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
