#!/usr/bin/env python3
"""Reproducible performance micro-benchmarks for Semantic YT Studio.

Measures host profile, governor budgets, FFmpeg short-encode throughput,
and Flow worker-cap math — without requiring a full documentary render.

Usage:
  python scripts/bench_performance.py
  VIDEOGEN_BENCH_SCENES=50 python scripts/bench_performance.py
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _ffmpeg() -> str:
    bundled = ROOT / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if bundled.is_file():
        return str(bundled)
    return shutil.which("ffmpeg") or "ffmpeg"


def bench_startup() -> dict:
    t0 = time.perf_counter()
    from hardware.governor import reset_governor_for_tests, get_governor

    reset_governor_for_tests()
    g = get_governor()
    snap = g.to_dict()
    t1 = time.perf_counter()
    return {
        "name": "startup_governor",
        "seconds": round(t1 - t0, 4),
        "platform": snap.get("platform"),
        "architecture": snap.get("architecture"),
        "budget": snap.get("budget"),
    }


def bench_import_hot_paths() -> dict:
    mods = [
        "video_generator",
        "asset_manager",
        "providers.ffmpeg_runner",
        "hardware.governor",
    ]
    times = {}
    for name in mods:
        t0 = time.perf_counter()
        __import__(name)
        times[name] = round(time.perf_counter() - t0, 4)
    return {"name": "imports", "seconds": times}


def bench_ffmpeg_clip(n: int = 3) -> dict:
    ff = _ffmpeg()
    durations = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            out = Path(tmp) / f"c{i}.mp4"
            cmd = [
                ff, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=size=640x360:rate=24:duration=1",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-t", "1",
                str(out),
            ]
            t0 = time.perf_counter()
            from providers.ffmpeg_runner import run_ffmpeg

            result = run_ffmpeg(cmd, owner="bench", media_duration_s=1.0, stall_s=60, label=f"bench{i}")
            dt = time.perf_counter() - t0
            if result.returncode != 0:
                return {"name": "ffmpeg_1s_clip", "error": result.stderr[-500:], "seconds": dt}
            durations.append(dt)
    return {
        "name": "ffmpeg_1s_clip",
        "runs": n,
        "seconds_mean": round(statistics.mean(durations), 4),
        "seconds_max": round(max(durations), 4),
        "encoder": "libx264",
    }


def bench_flow_cap() -> dict:
    # Pure math — mirrors flow-engine computeFlowWorkerCount
    def compute(prompt_count, account_count, max_parallel=6):
        if prompt_count <= 0 or account_count <= 0:
            return 0
        return min(account_count, prompt_count, max_parallel)

    cases = {
        "1_acct_1_prompt": compute(1, 1),
        "5_acct_5_prompt": compute(5, 5),
        "20_acct_100_prompt_cap6": compute(100, 20, 6),
        "20_acct_100_prompt_old_uncapped": min(20, 100),  # old ≥15 fan-out
    }
    return {
        "name": "flow_worker_cap",
        "cases": cases,
        "improvement_workers_saved": cases["20_acct_100_prompt_old_uncapped"]
        - cases["20_acct_100_prompt_cap6"],
    }


def bench_governor_scene_scales() -> dict:
    from hardware.governor import get_governor

    g = get_governor()
    out = {}
    for label, n in (("small_5", 5), ("medium_50", 50), ("large_150", 150), ("long_form_200", 200)):
        long_form = n >= 80
        b = g.budget(long_form=long_form)
        out[label] = {
            "scenes": n,
            "download": b.download,
            "ffmpeg": b.ffmpeg,
            "flow": b.flow_accounts,
            "processing": b.processing,
        }
    return {"name": "scene_scale_budgets", "scales": out}


def main() -> int:
    report = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
        },
        "benches": [],
    }
    for fn in (
        bench_startup,
        bench_import_hot_paths,
        bench_governor_scene_scales,
        bench_flow_cap,
        bench_ffmpeg_clip,
    ):
        try:
            report["benches"].append(fn())
        except Exception as exc:
            report["benches"].append({"name": fn.__name__, "error": str(exc)})

    out_path = ROOT / "bench_performance_last.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
