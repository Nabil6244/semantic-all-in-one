"""A worker thread's app.after(...) must never fail while the main thread is busy outside the event loop.

Windows CI: a pakMap run failed with RuntimeError('main thread is not in main loop') because its progress callback (a worker
thread) called app.after while the main thread was in a long step. VideoGeneratorApp.after queues calls from other threads; the
main thread schedules them.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class WorkerAfter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "scripts"))
        import ui_audit

        cls._settings = ROOT / "settings.json"
        cls._backup = Path(tempfile.mkdtemp()) / "settings.json"
        cls._had = cls._settings.is_file()
        if cls._had:
            shutil.copy2(cls._settings, cls._backup)
        try:
            _mod, cls.inst = ui_audit.build_app()
        except Exception as exc:
            raise unittest.SkipTest(f"app cannot be built here: {exc}")
        for _ in range(3):
            cls.inst.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.inst.destroy()
        finally:
            if cls._had:
                shutil.copy2(cls._backup, cls._settings)

    def _drain(self, until, timeout=5.0):
        end = time.monotonic() + timeout
        while not until() and time.monotonic() < end:
            self.inst.update()
            time.sleep(0.01)

    def test_a_worker_call_while_the_main_thread_is_busy_runs_on_the_main_thread(self):
        ran, errors = [], []

        def worker():
            try:
                self.inst.after(0, lambda: ran.append(threading.current_thread() is threading.main_thread()))
            except Exception as exc:   # before the fix: RuntimeError('main thread is not in main loop')
                errors.append(repr(exc))

        t = threading.Thread(target=worker)
        t.start()
        time.sleep(1.5)        # the main thread is busy, not in the event loop, for longer than Tk waits for it
        t.join(5)
        self._drain(lambda: ran)
        self.assertEqual(errors, [])
        self.assertEqual(ran, [True])

    def test_main_thread_calls_still_return_an_id_that_cancels(self):
        ran = []
        aid = self.inst.after(50, lambda: ran.append(1))
        self.assertTrue(aid)
        self.inst.after_cancel(aid)
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            self.inst.update()
            time.sleep(0.01)
        self.assertEqual(ran, [])

    def test_many_worker_calls_keep_their_order(self):
        got = []
        threads = [threading.Thread(target=lambda: [self.inst.after(0, got.append, i) for i in range(50)])]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        self._drain(lambda: len(got) == 50)
        self.assertEqual(got, list(range(50)))


if __name__ == "__main__":
    unittest.main()
