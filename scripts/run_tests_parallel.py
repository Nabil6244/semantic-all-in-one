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

# Modules that assert wall-clock speed: run alone after the parallel phase so
# CPU contention from other tests can't push them over their limits.
SERIAL_MODULES = {
    "test_preview_parity",
    "test_long_form_stress",
    "test_phase2_verification",
    # Start the full app / a browser helper with fixed time limits; on a busy
    # Windows runner these timed out while 8 other modules were running.
    "test_qa_ui_scoped_repaint",
    "test_asset_pipeline",
}

# Slowest modules (ffmpeg renders) start first so none is left running alone
# at the end.
SLOW_FIRST = [
    "test_exp_solar_multi_visual_composition",
    "test_exp_solar_index_grid",
    "test_render_segmented",
    "test_overscaled_app_integration",
    "test_overscaled_pipeline_e2e",
    "test_visual_plan_lifecycle_audit",
    "test_scene_graph_local_planner_pipeline",
    "test_asset_pipeline",
    "test_overscaled_cancellation",
    "test_normal_workflow_stale_media",
]


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
    slow_rank = {m: i for i, m in enumerate(SLOW_FIRST)}
    parallel = sorted((m for m in modules if m not in SERIAL_MODULES),
                      key=lambda m: (slow_rank.get(m, len(SLOW_FIRST)), m))
    serial = [m for m in modules if m in SERIAL_MODULES]
    print(f"Running {len(parallel)} test modules with {args.workers} workers, "
          f"then {len(serial)} timing-sensitive modules alone", flush=True)
    start = time.monotonic()
    failed: list[tuple[str, str]] = []
    total = 0

    def record(result) -> None:
        nonlocal total
        module, code, out, secs, ran = result
        total += ran
        status = "ok" if code == 0 else "FAILED"
        print(f"  {status:6} {module} ({ran} tests, {secs:.0f}s)", flush=True)
        if code != 0:
            failed.append((module, out))

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for fut in as_completed([pool.submit(_run, m) for m in parallel]):
            record(fut.result())
    for module in serial:
        record(_run(module))
    for module, out in failed:
        print(f"\n{'=' * 70}\n{module} output:\n{out[-20000:]}", flush=True)
    print(f"\nRan {total} tests in {len(modules)} modules in {time.monotonic() - start:.0f}s - "
          f"{'FAILED: ' + ', '.join(m for m, _ in failed) if failed else 'OK'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
