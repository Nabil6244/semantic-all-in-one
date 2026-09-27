"""A background worker must always hand control back to the UI.

Before: _run_pipeline (the normal Generate worker) redirected stdout/stderr
and then did path resolution + scratch-dir creation OUTSIDE its main try —
any failure there (disk full, unresolvable path) killed the thread without
ever sending "done" or "error", leaving the UI on "running" forever with
stdout still hijacked. (The Overscaled worker's equivalent is covered in
test_visual_plan_lifecycle_audit / test_overscaled_cancellation.)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

_LIVE = r'''
import os, sys, queue
from pathlib import Path
from unittest import mock
real_stdout = sys.stdout
sys.path.insert(0, os.getcwd())
def emit(n, ok, d=""): real_stdout.write(f"{'PASS' if ok else 'FAIL'}:{n}:{str(d)[:400]}\n"); real_stdout.flush()
from tkinter import messagebox
messagebox.showerror = messagebox.showinfo = lambda *a, **k: None
try:
    import app as _app
    inst = _app.VideoGeneratorApp(); inst.withdraw()
except Exception as exc:
    real_stdout.write(f"SKIP:{exc}\n"); os._exit(0)
while True:
    try: inst._ui_queue.get_nowait()
    except queue.Empty: break
config = {"csv_path": "a.csv", "audio_path": "a.wav", "images_dir": ".", "output_path": "o.mp4", "bg_path": None}
with mock.patch("tempfile.mkdtemp", side_effect=OSError(28, "No space left on device")):
    inst._run_pipeline(config)
events = []
while True:
    try: events.append(inst._ui_queue.get_nowait())
    except queue.Empty: break
errors = [e for e in events if e[0] == "error"]
emit("setup_failure_reports_error", errors and "No space left" in str(errors[-1][1]), events[-3:])
emit("stdout_is_restored", sys.stdout is real_stdout, type(sys.stdout).__name__)
os._exit(0)
'''


class TestNormalPipelineSetupFailure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys

        script = Path(tempfile.mkdtemp()) / "_setup_fail_live.py"
        script.write_text(_LIVE, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120,
                              cwd=Path(__file__).resolve().parent)
        cls._out, cls._err, cls._res = proc.stdout, proc.stderr, {}
        for line in proc.stdout.splitlines():
            if line.startswith("SKIP:"):
                raise unittest.SkipTest(line[5:])
            if line.startswith(("PASS:", "FAIL:")):
                status, rest = line.split(":", 1)
                name, _, detail = rest.partition(":")
                cls._res[name] = (status == "PASS", detail)

    def _check(self, name):
        if name not in self._res:
            self.fail(f"never reported {name}\n{self._out}\n{self._err[-2000:]}")
        ok, detail = self._res[name]
        self.assertTrue(ok, f"{name}: {detail}")

    def test_setup_failure_reports_an_error_to_the_ui(self):
        self._check("setup_failure_reports_error")

    def test_stdout_is_restored_after_setup_failure(self):
        self._check("stdout_is_restored")


if __name__ == "__main__":
    unittest.main()
