"""Stress: the Activity log under sustained high-volume output (QA, 2026-10-17).

Builds the real app (scripts/ui_audit.build_app), opens a real temporary project workspace, shows the Activity log and
floods it from several worker threads (routed through _ui_queue / _poll_queue) and from the main thread while the Tk
mainloop runs. Checks UI responsiveness (gap between 10 ms after() ticks), per-producer order, the on-screen line cap,
that the project log on disk has every line in order, and that RSS stays bounded.

settings.json is never written: app._settings_path / ui.theme._settings_path point at a temp copy (projects_root is a
temp dir, no active project), and the real file is backed up and restored anyway, then compared byte-for-byte.
"""

from __future__ import annotations

import filecmp
import json
import os
try:
    import resource  # Unix only
except ImportError:  # Windows
    resource = None
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREFIX = "STRESS|"
MARKER = "… earlier lines are in the project log file …"
VERBOSE = os.environ.get("STRESS_VERBOSE", "1") == "1"


def _block_flow_engine():
    """Belt and braces: no code path in these tests may start the Flow engine."""
    try:
        from providers.flow import engine_manager as _em

        def _refuse(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        _em.FlowEngineManager.start = _refuse
        _em.FlowEngineManager.ensure_running = _refuse
    except Exception:
        pass


def _rss_mb(pid: int) -> float:
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
        return int(out.strip()) / 1024.0
    except Exception:
        return float("nan")


def _pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, max(0, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


class _Harness:
    """Real app on a temp settings copy and a temp projects root."""

    @classmethod
    def build(cls, owner):
        owner.real_settings = ROOT / "settings.json"
        owner.tmp = Path(tempfile.mkdtemp(prefix="stress_log_"))
        owner.backup = owner.tmp / "settings.backup.json"
        owner.had = owner.real_settings.is_file()
        data = {}
        if owner.had:
            shutil.copy2(owner.real_settings, owner.backup)
            try:
                data = json.loads(owner.real_settings.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data.pop("active_project_id", None)
        data["projects_root"] = str(owner.tmp / "projects")
        sp = owner.tmp / "settings.json"
        sp.write_text(json.dumps(data), encoding="utf-8")
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "scripts"))
        _block_flow_engine()
        import app as app_mod
        import ui.theme as T

        app_mod._settings_path = lambda: sp
        T._settings_path = lambda: sp
        import ui_audit

        owner.app_mod, owner.inst = ui_audit.build_app()
        owner.errors = []

        def no_engine(*_a, **_k):
            raise RuntimeError("stress tests never start the Flow engine")

        owner.inst._get_flow_engine_manager = no_engine
        owner.inst.report_callback_exception = lambda *a: owner.errors.append(a)

    @classmethod
    def teardown(cls, owner):
        try:
            if getattr(owner, "inst", None) is not None:
                owner.inst.destroy()
        finally:
            if owner.had:
                shutil.copy2(owner.backup, owner.real_settings)
                assert filecmp.cmp(owner.backup, owner.real_settings, shallow=False), "settings.json not restored"
            shutil.rmtree(owner.tmp, ignore_errors=True)


class ActivityLogFlood(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            _Harness.build(cls)
        except Exception as exc:  # no display
            cls.inst = None
            cls.skip_reason = str(exc)
            return
        import project_workspace

        cls.ws = project_workspace.create_project("stress log", projects_root=cls.tmp / "projects")
        cls.inst._activate_workspace(cls.ws, persist=False)
        if not cls.inst._log_visible:
            cls.inst._toggle_activity_log()
        cls.inst.update()
        cls.results = {}

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "results", None):
            print("\n[stress activity log] " + json.dumps(cls.results, indent=1), file=sys.stderr)
        _Harness.teardown(cls)

    def setUp(self):
        if self.inst is None:
            self.skipTest("needs Tk: " + getattr(self, "skip_reason", ""))
        inst = self.inst
        # Start from an empty screen log and an empty project log.
        inst._flush_log_ui()
        inst._flush_log_disk()
        inst.log_box.configure(state="normal")
        inst.log_box.delete("1.0", "end")
        inst.log_box.configure(state="disabled")
        self.ws.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.ws.log_path.write_text("", encoding="utf-8")
        self.errors.clear()

    def tearDown(self):
        # Restore class caps in case a test overrode them on the instance.
        for name in ("_LOG_VIEW_MAX_LINES", "_LOG_VIEW_KEEP_LINES"):
            self.inst.__dict__.pop(name, None)

    # ------------------------------------------------------------------ driver
    def _flood(self, *, workers: int, per_worker: int, main_lines: int, main_burst: int = 100,
               worker_burst: int = 0, deadline_s: float = 110.0) -> dict:
        """Run the mainloop while producers write; return timing / memory stats."""
        inst = self.inst
        gaps: list[float] = []
        state = {"main_seq": 0, "workers_done": 0, "stop": False, "last_tick": None,
                 "flood_end": None, "drained_at": None, "max_qsize": 0}
        rss = []
        pid = os.getpid()

        def rss_sampler():
            while not state["stop"]:
                rss.append(_rss_mb(pid))
                time.sleep(0.5)

        def ticker():
            now = time.perf_counter()
            if state["last_tick"] is not None:
                gaps.append((now - state["last_tick"]) * 1000.0)
            state["last_tick"] = now
            try:
                state["max_qsize"] = max(state["max_qsize"], inst._ui_queue.qsize())
            except Exception:
                pass
            if not state["stop"]:
                inst.after(10, ticker)

        def worker(i: int):
            for n in range(per_worker):
                inst._append_log(f"{PREFIX}w{i}|{n:07d}\n")
                if worker_burst and n % worker_burst == worker_burst - 1:
                    time.sleep(0.001)
            state["workers_done"] += 1  # GIL-atomic enough for a counter read on the main thread

        def main_producer():
            end = min(main_lines, state["main_seq"] + main_burst)
            for n in range(state["main_seq"], end):
                inst._append_log(f"{PREFIX}main|{n:07d}\n")
            state["main_seq"] = end
            if end < main_lines:
                inst.after(5, main_producer)

        def watch():
            produced = state["workers_done"] == workers and state["main_seq"] >= main_lines
            if produced and state["flood_end"] is None:
                state["flood_end"] = time.perf_counter()
            if produced and inst._ui_queue.qsize() == 0 and not inst._log_ui_buf:
                if state["drained_at"] is None:
                    state["drained_at"] = time.perf_counter()
                    # one more disk flush window (after(400)) and the 50 ms UI flush, then stop
                    inst.after(700, finish)
                    return
            if time.perf_counter() - t0 > deadline_s:
                finish()
                return
            inst.after(50, watch)

        def finish():
            state["stop"] = True
            inst.quit()

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(workers)]
        rss_thread = threading.Thread(target=rss_sampler, daemon=True)
        rss_before = _rss_mb(pid)
        t0 = time.perf_counter()
        rss_thread.start()
        inst.after(0, ticker)
        inst.after(0, main_producer)
        inst.after(0, lambda: [t.start() for t in threads])
        inst.after(50, watch)
        inst.mainloop()
        for t in threads:
            t.join(timeout=30)
        state["stop"] = True
        rss_thread.join(timeout=5)
        # anything still pending lands now (not _poll_queue(): calling it would start a second poll loop)
        inst._flush_log_ui()
        inst._flush_log_disk()
        t_end = time.perf_counter()
        total = workers * per_worker + main_lines
        drain_s = (state["drained_at"] or t_end) - t0
        return {
            "lines": total,
            "workers": workers,
            "per_worker": per_worker,
            "main_lines": main_lines,
            "wall_s": round(t_end - t0, 2),
            "drained_s": round(drain_s, 2),
            "produce_s": round(((state["flood_end"] or t_end) - t0), 2),
            "throughput_lines_per_s": round(total / drain_s, 1) if drain_s else None,
            "max_ui_queue": state["max_qsize"],
            "ticks": len(gaps),
            "gap_p50_ms": round(_pct(gaps, 50), 1),
            "gap_p99_ms": round(_pct(gaps, 99), 1),
            "gap_max_ms": round(max(gaps) if gaps else 0.0, 1),
            "rss_before_mb": round(rss_before, 1),
            "rss_peak_sampled_mb": round(max([r for r in rss if r == r] or [0]), 1),
            "rss_after_mb": round(_rss_mb(pid), 1),
            "ru_maxrss_mb": (round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024), 1)
                             if resource is not None else float("nan")),
            "timed_out": state["drained_at"] is None,
        }

    # ---------------------------------------------------------------- checks
    def _screen_lines(self) -> list[str]:
        return self.inst.log_box.get("1.0", "end-1c").split("\n")

    def _check_order(self, lines: list[str], expected: dict[str, int] | None, where: str):
        by: dict[str, list[int]] = defaultdict(list)
        for ln in lines:
            if ln.startswith(PREFIX):
                parts = ln.split("|")
                self.assertEqual(len(parts), 3, f"{where}: mangled line {ln!r}")
                by[parts[1]].append(int(parts[2]))
        for producer, seqs in by.items():
            bad = next((i for i in range(1, len(seqs)) if seqs[i] <= seqs[i - 1]), None)
            self.assertIsNone(bad, f"{where}: {producer} out of order at index {bad}: "
                                   f"{seqs[bad - 1] if bad else None} -> {seqs[bad] if bad else None}")
        if expected is not None:
            for producer, n in expected.items():
                self.assertEqual(by.get(producer, []), list(range(n)), f"{where}: {producer} lines missing or extra")
        return by

    def _run_and_check(self, *, label, workers, per_worker, main_lines, max_lines, keep_lines,
                       gap_limit_ms, rss_growth_limit_mb, **kw):
        inst = self.inst
        if max_lines is not None:
            inst._LOG_VIEW_MAX_LINES = max_lines
            inst._LOG_VIEW_KEEP_LINES = keep_lines
        cap = inst._LOG_VIEW_MAX_LINES
        stats = self._flood(workers=workers, per_worker=per_worker, main_lines=main_lines, **kw)
        self.results[label] = stats
        if VERBOSE:
            print(f"\n[{label}] {json.dumps(stats)}", file=sys.stderr)
        self.assertFalse(stats["timed_out"], f"{label}: log did not drain in time: {stats}")
        self.assertEqual(self.errors, [], f"{label}: Tk callback exceptions")
        expected = {f"w{i}": per_worker for i in range(workers)}
        expected["main"] = main_lines

        # (d) disk has every line, in order
        disk = self.ws.log_path.read_text(encoding="utf-8").split("\n")
        self._check_order(disk, expected, f"{label} disk")
        n_disk = sum(1 for ln in disk if ln.startswith(PREFIX))
        self.assertEqual(n_disk, stats["lines"])
        self.assertNotIn(MARKER, disk, "the screen-cap marker must never reach the project log")

        # (b)+(c) screen: bounded, ordered, marker once at top, tail intact
        screen = self._screen_lines()
        stats["screen_lines"] = len(screen)
        self.assertLessEqual(len(screen), cap + 2, f"{label}: on-screen log not bounded ({len(screen)} lines)")
        if stats["lines"] > cap:
            self.assertEqual(screen.count(MARKER), 1, f"{label}: marker count {screen.count(MARKER)}")
            self.assertEqual(screen[0], MARKER)
        by = self._check_order(screen, None, f"{label} screen")
        for producer, n in expected.items():
            if by.get(producer):
                self.assertEqual(by[producer][-1], n - 1, f"{label}: last {producer} line missing on screen")
                # what is on screen is a contiguous tail of each producer's output
                tail = by[producer]
                self.assertEqual(tail, list(range(tail[0], n)), f"{label}: gap inside on-screen {producer} lines")

        # (a) responsiveness
        self.assertLess(stats["gap_max_ms"], gap_limit_ms, f"{label}: UI froze: {stats}")
        # (e) memory
        growth = stats["rss_peak_sampled_mb"] - stats["rss_before_mb"]
        stats["rss_growth_mb"] = round(growth, 1)
        if growth == growth:  # NaN when the OS gave no RSS reading (CI sandbox, Windows): nothing to assert
            self.assertLess(growth, rss_growth_limit_mb, f"{label}: RSS grew {growth:.0f} MB: {stats}")
        return stats

    # ----------------------------------------------------------------- tests
    def test_1_flood_100k_small_caps(self):
        """100k lines: 4 worker threads x 12.5k (off-thread, throttled ~realistic bursts) + 50k main-thread."""
        self._run_and_check(
            label="flood_100k_caps_2000_1500", workers=4, per_worker=12_500, main_lines=50_000,
            max_lines=2000, keep_lines=1500, gap_limit_ms=500, rss_growth_limit_mb=300,
        )

    def test_2_flood_real_caps(self):
        """Real caps (20000 / 15000): 45k lines so the screen trims at least twice."""
        self._run_and_check(
            label="flood_45k_real_caps", workers=3, per_worker=5_000, main_lines=30_000,
            max_lines=None, keep_lines=None, gap_limit_ms=1000, rss_growth_limit_mb=400,
        )

    def test_3_worker_only_drain_rate(self):
        """Worker-only output: measures how fast _poll_queue drains (48 items per 40 ms tick)."""
        stats = self._run_and_check(
            label="workers_only_12k", workers=4, per_worker=3_000, main_lines=0,
            max_lines=2000, keep_lines=1500, gap_limit_ms=500, rss_growth_limit_mb=300,
        )
        # Report only: the UI queue drain is the throughput ceiling for worker logs.
        self.assertGreater(stats["throughput_lines_per_s"], 0)


if __name__ == "__main__":
    unittest.main()
