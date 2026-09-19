"""Regression tests for progress_events.py and its app.py integration
(Semantic YT Studio 2.0 — Batch 1, PHASE 9/10).

Event shape (ProgressEvent/EtaEstimator/make_event) is pure logic and is
tested directly. The app.py side (queue wiring, coalescing, progress-bar
mapping) needs a CTk GUI class — following the existing convention in
test_flow_reliability_audit.py, those parts are verified via
inspect.getsource() rather than instantiating the GUI, and the whole class
is skipped if customtkinter isn't importable in this environment.
"""

from __future__ import annotations

import queue
import unittest

from progress_events import EtaEstimator, PHASE_LABELS, ProgressEvent, make_event


class TestProgressEventShape(unittest.TestCase):
    def test_percent_computation(self):
        evt = ProgressEvent(phase="rendering", current=5, total=10)
        self.assertEqual(evt.percent, 50.0)

    def test_percent_zero_total_is_zero_not_a_crash(self):
        evt = ProgressEvent(phase="rendering", current=0, total=0)
        self.assertEqual(evt.percent, 0.0)

    def test_percent_clamped_to_100(self):
        evt = ProgressEvent(phase="rendering", current=15, total=10)
        self.assertEqual(evt.percent, 100.0)

    def test_percent_clamped_to_0(self):
        evt = ProgressEvent(phase="rendering", current=-5, total=10)
        self.assertEqual(evt.percent, 0.0)

    def test_to_dict_includes_percent(self):
        evt = ProgressEvent(phase="mux", current=1, total=1, status="done")
        d = evt.to_dict()
        self.assertEqual(d["phase"], "mux")
        self.assertEqual(d["status"], "done")
        self.assertEqual(d["percent"], 100.0)


class TestMakeEvent(unittest.TestCase):
    def test_make_event_fills_default_message_from_phase_label(self):
        evt = make_event("rendering", 1, 10)
        self.assertEqual(evt.message, PHASE_LABELS["rendering"])

    def test_make_event_custom_message_overrides_label(self):
        evt = make_event("rendering", 1, 10, message="Scene 1 (cached)")
        self.assertEqual(evt.message, "Scene 1 (cached)")

    def test_make_event_unknown_phase_falls_back_to_phase_name(self):
        evt = make_event("some_new_phase", 1, 2)
        self.assertEqual(evt.message, "some_new_phase")

    def test_make_event_scene_id_stringified(self):
        evt = make_event("rendering", 1, 2, scene_id=7)
        self.assertEqual(evt.scene_id, "7")

    def test_make_event_no_scene_id_stays_none(self):
        evt = make_event("mux", 1, 1)
        self.assertIsNone(evt.scene_id)

    def test_make_event_with_eta_estimator(self):
        eta = EtaEstimator()
        evt = make_event("rendering", 5, 10, eta=eta)
        # Some data exists (5/10 completed) so an estimate should be produced.
        self.assertIsInstance(evt.eta_seconds, float)

    def test_make_event_without_eta_estimator_is_none(self):
        evt = make_event("rendering", 5, 10)
        self.assertIsNone(evt.eta_seconds)


class TestEtaEstimator(unittest.TestCase):
    def test_insufficient_data_returns_none(self):
        eta = EtaEstimator()
        self.assertIsNone(eta.estimate(0, 10))

    def test_completed_returns_none(self):
        eta = EtaEstimator()
        self.assertIsNone(eta.estimate(10, 10))

    def test_zero_total_returns_none(self):
        eta = EtaEstimator()
        self.assertIsNone(eta.estimate(1, 0))

    def test_partial_progress_returns_a_positive_estimate(self):
        import time

        eta = EtaEstimator()
        time.sleep(0.02)
        estimate = eta.estimate(1, 4)
        self.assertIsNotNone(estimate)
        self.assertGreater(estimate, 0.0)

    def test_reset_restarts_the_clock(self):
        import time

        eta = EtaEstimator()
        time.sleep(0.02)
        first = eta.estimate(1, 4)
        eta.reset()
        second = eta.estimate(1, 4)
        self.assertLess(second, first)


class TestQueueCoalescingPattern(unittest.TestCase):
    """The actual coalescing loop lives in app.py's _poll_queue (verified
    structurally below); this exercises the same drain-and-keep-latest
    pattern against a real queue.Queue to prove the semantics are correct
    independent of the GUI."""

    def test_only_latest_progress_survives_a_drain(self):
        q: queue.Queue = queue.Queue()
        for i in range(1, 6):
            q.put(("progress", make_event("rendering", i, 5)))

        latest = None
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "progress":
                    latest = payload
        except queue.Empty:
            pass

        self.assertIsNotNone(latest)
        self.assertEqual(latest.current, 5)
        self.assertEqual(q.qsize(), 0)


class TestAppIntegrationStructure(unittest.TestCase):
    """Structural checks that app.py actually wires progress_events through
    the existing _ui_queue, following test_flow_reliability_audit.py's
    convention of inspecting source rather than instantiating the GUI."""

    @classmethod
    def setUpClass(cls):
        import inspect
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls._app = _app
        cls._inspect = inspect

    def test_run_pipeline_builds_a_perf_recorder(self):
        src = self._inspect.getsource(self._app.VideoGeneratorApp._run_pipeline)
        self.assertIn("PerfRecorder", src)
        self.assertIn("render_cache_state_dir=state_dir", src)
        self.assertIn("progress_cb=_progress_cb", src)

    def test_progress_callback_pushes_onto_existing_ui_queue(self):
        src = self._inspect.getsource(self._app.VideoGeneratorApp._run_pipeline)
        self.assertIn('self._ui_queue.put(("progress", evt))', src)

    def test_poll_queue_coalesces_progress_events(self):
        src = self._inspect.getsource(self._app.VideoGeneratorApp._poll_queue)
        self.assertIn('kind == "progress"', src)
        self.assertIn("latest_progress = payload", src)
        self.assertIn("_apply_progress_event(latest_progress)", src)

    def test_apply_progress_event_never_raises_by_construction(self):
        src = self._inspect.getsource(self._app.VideoGeneratorApp._apply_progress_event)
        self.assertIn("try:", src)
        self.assertIn("except Exception:", src)


if __name__ == "__main__":
    unittest.main()
