"""Every style ends on the Export page with a verified video (export_state + the app's generation tracking).

Before: only Normal video moved to Export and showed its progress there; Overscaled / Exp Solar, pakMap, Hybrid, StarMap,
What If and Weather left the user where they were, the Export page said "Idle" during their renders, and a style could say
"video ready" without the app checking the file.
"""
import inspect
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import export_state as ES


def _video(path: Path, size: int = 4096, age_s: float = 0.0) -> Path:
    path.write_bytes(b"\0" * size)
    if age_s:
        t = time.time() - age_s
        os.utime(path, (t, t))
    return path


class VerifyOutput(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_good_file(self):
        self.assertIsNone(ES.verify_output(_video(self.d / "a.mp4"), time.time() - 1))

    def test_missing_empty_stale(self):
        self.assertIn("missing", ES.verify_output(self.d / "nope.mp4", None))
        self.assertIn("no output", ES.verify_output(None, None))
        self.assertIn("empty", ES.verify_output(_video(self.d / "e.mp4", size=10), None))
        old = _video(self.d / "old.mp4", age_s=3600)
        self.assertIn("earlier render", ES.verify_output(old, time.time()))
        self.assertIsNone(ES.verify_output(old, None))   # no start time: existence and size only

    def test_failed_copy_keeps_the_result_type(self):
        from pakmap.app_integration import PakmapResult
        from scene_graph.app_integration import OverscaledGenerationResult

        r = ES.failed_copy(PakmapResult(True, [], output_path=self.d / "x.mp4", credits=["c"]), "the output file is missing (x.mp4)")
        self.assertIsInstance(r, PakmapResult)
        self.assertFalse(r.ok)
        self.assertIn("missing", r.errors[0])
        self.assertEqual(r.credits, ["c"])
        o = ES.failed_copy(OverscaledGenerationResult(ok=True, errors=[], output_path=None), "the render reported no output file")
        self.assertFalse(o.ok)
        self.assertIn("no output", o.errors[0])

    def test_job_progress_and_status(self):
        j = ES.ExportJob("starmap")
        j.progress(0.4, "Rendering")
        j.progress(0.2, "late callback")   # never goes backwards while running
        self.assertEqual(j.fraction, 0.4)
        self.assertIn("StarMap", j.status_text())
        self.assertIn("40%", j.status_text())
        j.running, j.outcome, j.problem = False, "failed", "the output file is missing"
        self.assertIn("failed", j.status_text())
        self.assertIn("missing", j.status_text())


def _app_cls():
    import app
    return next(v for v in vars(app).values() if isinstance(v, type) and hasattr(v, "_track_generation_end"))


class AppHooks(unittest.TestCase):
    def setUp(self):
        self.cls = _app_cls()
        self.d = Path(tempfile.mkdtemp())

    def _fake(self, style):
        fake = SimpleNamespace(_last_output=None, logs=[], after_calls=[])
        fake._append_log = fake.logs.append
        fake.after = lambda ms, fn: fake.after_calls.append(fn)
        fake._goto_workflow_view = mock.Mock()
        fake._export_job = ES.ExportJob(style)
        for name in ("_export_job_end", "_export_verified", "_export_progress"):
            setattr(fake, name, getattr(self.cls, name).__get__(fake))
        return fake

    def test_style_success_registers_output_and_opens_export(self):
        f = self._fake("hybrid")
        out = _video(self.d / "final.mp4")
        f._export_progress(0.5, "Rendering")
        f._export_job_end("completed", out)
        self.assertEqual(f._last_output, str(out))
        self.assertEqual(f._export_job.output_path, str(out))
        for fn in f.after_calls:
            fn()
        f._goto_workflow_view.assert_called_once_with("render")

    def test_missing_output_is_not_exported(self):
        f = self._fake("whatif")
        f._export_job_end("completed", self.d / "never_written.mp4")
        self.assertIsNone(f._last_output)
        self.assertEqual(f._export_job.outcome, "failed")
        self.assertIn("missing", f._export_job.problem)
        self.assertEqual(f.after_calls, [])

    def test_failure_and_cancel_do_not_navigate(self):
        for outcome in ("failed", "cancelled"):
            f = self._fake("pakmap")
            f._export_job_end(outcome, None, "row 3: vo_anchor 'x' is not in the narration\nmore")
            self.assertEqual(f.after_calls, [])
            self.assertFalse(f._export_job.running)
        self.assertEqual(f._export_job.outcome, "cancelled")

    def test_normal_video_keeps_its_own_end_handling(self):
        f = self._fake("normal")
        f._export_job_end("completed", _video(self.d / "n.mp4"))
        self.assertIsNone(f._last_output)      # Normal video sets it and moves to Export itself
        self.assertEqual(f.after_calls, [])

    def test_ended_job_is_not_ended_twice(self):
        f = self._fake("starmap")
        out = _video(self.d / "s.mp4")
        f._export_job_end("completed", out)
        f._export_job_end("failed", None, "late")
        self.assertEqual(f._export_job.outcome, "completed")

    def test_export_verified_turns_a_false_success_into_a_failure(self):
        from pakmap.app_integration import PakmapResult

        f = self._fake("hybrid")
        bad = f._export_verified(PakmapResult(True, [], output_path=self.d / "gone.mp4"))
        self.assertFalse(bad.ok)
        self.assertTrue(any("Not exported" in l for l in f.logs))
        good_path = _video(self.d / "ok.mp4")
        good = PakmapResult(True, [], output_path=good_path)
        self.assertIs(f._export_verified(good), good)
        failed = PakmapResult(False, ["boom"])
        self.assertIs(f._export_verified(failed), failed)


class EveryStyleIsWired(unittest.TestCase):
    """Each style's finish() verifies its output first and its progress reaches the Export page."""

    def test_app_styles(self):
        src = inspect.getsource(_app_cls())
        for flag in ("_overscaled_running", "_hybrid_running", "_starmap_running", "_pakmap_running"):
            self.assertIn(f"result = self._export_verified(result)   # never \"video ready\" for a missing, empty or old file\n"
                          f"            self.{flag} = False", src, flag)
        for var in ("_overscaled_status_var", "_hybrid_status_var", "_starmap_status_var", "_pakmap_status_var"):
            i = src.index(f'self.{var}.set(f"{{message}} ({{int(fraction * 100)}}%)")')
            self.assertIn("self._export_progress(fraction, message)", src[i:i + 300], var)

    def test_section_styles(self):
        for mod, key in (("whatif.app_section", "whatif"), ("weather.app_section", "weather")):
            src = inspect.getsource(__import__(mod, fromlist=["x"]))
            self.assertIn(f"result = app._export_verified(result)", src, mod)
            i = src.index(f'app._{key}_status_var.set(f"{{message}} ({{int(fraction * 100)}}%)")')
            self.assertIn("app._export_progress(fraction, message)", src[i:i + 300], mod)

    def test_tracking_starts_and_ends_the_job(self):
        cls = _app_cls()
        self.assertIn("_ExportJob(render_engine)", inspect.getsource(cls._track_generation_start))
        self.assertIn("self._export_job_end(outcome, output_path, message)", inspect.getsource(cls._track_generation_end))
        self.assertIn("self._export_job = None", inspect.getsource(cls._clear_render_preview))


if __name__ == "__main__":
    unittest.main()
