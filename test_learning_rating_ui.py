"""Real Tk checks of the rating dialog: save, visible+retryable failure, skip, closing mid-save. Bounded; always destroys the root."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from learning import events as ev, ledger as lg, rating_flow as rf


class RatingDialogTk(unittest.TestCase):
    def setUp(self):
        try:
            import customtkinter as ctk
            self.root = ctk.CTk()
            self.root.geometry("200x80+40+40")
        except Exception as exc:
            raise unittest.SkipTest(f"no display / customtkinter: {exc}")
        self.addCleanup(self.root.destroy)
        # The save runs on a background thread that may still be closing its sqlite connection when the test ends;
        # Windows will not delete an open file (CI 2026-10-21: WinError 32 in cleanup after every check had passed).
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.led = lg.Ledger(Path(self.tmp.name) / "l.sqlite")
        lg.set_default_ledger(self.led)
        self.addCleanup(lg.set_default_ledger, None)
        app = SimpleNamespace(generation_mode="normal", _workspace=SimpleNamespace(project_id="p", read_meta=lambda: {}))
        ev.begin_render_op(app, "normal", None)
        ev.note_render_outcome(app, SimpleNamespace(generation_id="g1", project_id="p", render_engine="normal"), "completed")
        self.h = rf.pending_prompt_target("p")
        import learning.rating_ui as ui
        self.ui = ui

    def pump(self, cond, seconds=5):
        end = time.time() + seconds
        while time.time() < end and not cond():
            self.root.update()
            time.sleep(0.02)
        return cond()

    def test_save_once_then_failure_is_visible_and_retry_works(self):
        done = []
        d = self.ui.RatingDialog(self.root, self.h, on_done=lambda: done.append(1))
        d._set(4)
        bad = ev.RatingResult(False, "error", error="ledger_unavailable")
        with mock.patch.object(rf, "submit", return_value=bad):
            d._save()
            self.assertTrue(self.pump(lambda: "could not be saved" in d.status.cget("text")))
        self.assertEqual(str(d.save_btn.cget("state")), "normal")                      # retryable
        self.assertEqual(done, [])
        d._save()                                                                      # retry for real
        self.assertTrue(self.pump(lambda: done))
        self.assertEqual([(e["payload"]["rating"], e["payload"]["revision"]) for e in self.led.events(event_type="video_rating")], [(4, 1)])

    def test_skip_records_nothing_and_stars_required(self):
        d = self.ui.RatingDialog(self.root, self.h)
        d._save()
        self.assertIn("Choose", d.status.cget("text"))
        d._skip()
        self.assertEqual(self.led.events(event_type="video_rating"), [])
        self.assertIsNone(rf.pending_prompt_target("p"))

    def test_closing_the_window_mid_save_does_not_hang_or_lose_the_rating(self):
        d = self.ui.RatingDialog(self.root, self.h)
        d._set(5)
        d._save()
        d.win.destroy()
        t0 = time.time()
        self.pump(lambda: bool(self.led.events(event_type="video_rating")), 3)
        self.assertLess(time.time() - t0, 4)
        self.assertEqual(len(self.led.events(event_type="video_rating")), 1)


if __name__ == "__main__":
    unittest.main()
