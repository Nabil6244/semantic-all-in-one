#!/usr/bin/env python3
"""Run every test_*.py module in its own process, in parallel.

Same tests as ``python -m unittest discover -s . -p "test_*.py"`` — just one
subprocess per module across all CPU cores, which cuts CI test time several
times over. Exits non-zero if any module fails, and prints each failing
module's full output.

Usage: python scripts/run_tests_parallel.py [--workers N]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SUMMARY_RE = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)
_TIMEOUT_S = 1200


def _run(module: str) -> tuple[str, int, str, float, int]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module],
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_TIMEOUT_S,
        )
        code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code, out = 1, f"TIMEOUT after {_TIMEOUT_S}s\n{exc.stdout or ''}{exc.stderr or ''}"
    match = _SUMMARY_RE.search(out)
    return module, code, out, time.monotonic() - start, int(match.group(1)) if match else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 2)))
    args = parser.parse_args()

    modules = sorted(p.stem for p in ROOT.glob("test_*.py"))
    print(f"Running {len(modules)} test modules with {args.workers} workers", flush=True)
    start = time.monotonic()
    failed: list[tuple[str, str]] = []
    total = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_run, m) for m in modules]
        for fut in as_completed(futures):
            module, code, out, secs, ran = fut.result()
            total += ran
            status = "ok" if code == 0 else "FAILED"
            print(f"  {status:6} {module} ({ran} tests, {secs:.0f}s)", flush=True)
            if code != 0:
                failed.append((module, out))
    for module, out in failed:
        print(f"\n{'=' * 70}\n{module} output:\n{out[-20000:]}", flush=True)
    print(f"\nRan {total} tests in {len(modules)} modules in {time.monotonic() - start:.0f}s — "
          f"{'FAILED: ' + ', '.join(m for m, _ in failed) if failed else 'OK'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
