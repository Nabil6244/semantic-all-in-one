"""Regression tests for perf_instrumentation.py (Semantic YT Studio 2.0 — Batch 1).

Verifies recorder correctness (timer/record/note_cache/total_for/count_for)
and that a failure inside any recording call is swallowed, never raised —
instrumentation must never be able to break the pipeline it's measuring.
"""

from __future__ import annotations

import time
import unittest

from perf_instrumentation import PerfEvent, PerfRecorder


class TestTimerRecording(unittest.TestCase):
    def test_timer_records_one_event(self):
        perf = PerfRecorder()
        with perf.timer("whisper"):
            # 0.01s was flaky on a real Windows CI runner (coarse Sleep()
            # timer resolution occasionally returning near-instantly for a
            # very short sleep — confirmed live: elapsed came back exactly
            # 0.0). A larger margin makes an exact-zero elapsed reading
            # effectively impossible while still keeping the test fast.
            time.sleep(0.05)
        self.assertEqual(perf.count_for("whisper"), 1)
        self.assertGreater(perf.total_for("whisper"), 0.0)

    def test_timer_records_extra_fields(self):
        perf = PerfRecorder()
        with perf.timer("scene_render", scene_id="007", cache_hit=False):
            pass
        evt = perf.events[-1]
        self.assertEqual(evt.name, "scene_render")
        self.assertEqual(evt.extra.get("scene_id"), "007")
        self.assertEqual(evt.extra.get("cache_hit"), False)

    def test_timer_records_even_when_body_raises(self):
        perf = PerfRecorder()
        with self.assertRaises(ValueError):
            with perf.timer("editorial"):
                raise ValueError("boom")
        # The span itself must still be recorded — the try/finally in
        # PerfRecorder.timer must not swallow the caller's own exception,
        # but must still capture the elapsed duration.
        self.assertEqual(perf.count_for("editorial"), 1)

    def test_multiple_spans_of_same_name_accumulate(self):
        perf = PerfRecorder()
        with perf.timer("scene_render"):
            pass
        with perf.timer("scene_render"):
            pass
        with perf.timer("scene_render"):
            pass
        self.assertEqual(perf.count_for("scene_render"), 3)

    def test_record_manual_span(self):
        perf = PerfRecorder()
        perf.record("mux", 2.5)
        self.assertEqual(perf.total_for("mux"), 2.5)

    def test_record_never_raises_on_bad_duration(self):
        perf = PerfRecorder()
        perf.record("mux", "not-a-number")  # type: ignore[arg-type]
        self.assertEqual(perf.count_for("mux"), 0)


class TestCacheTally(unittest.TestCase):
    def test_note_cache_hits_and_misses(self):
        perf = PerfRecorder()
        perf.note_cache(True)
        perf.note_cache(True)
        perf.note_cache(False)
        self.assertEqual(perf.cache_hits, 2)
        self.assertEqual(perf.cache_misses, 1)


class TestAggregates(unittest.TestCase):
    def test_total_for_unknown_name_is_zero(self):
        perf = PerfRecorder()
        self.assertEqual(perf.total_for("nonexistent"), 0.0)

    def test_count_for_unknown_name_is_zero(self):
        perf = PerfRecorder()
        self.assertEqual(perf.count_for("nonexistent"), 0)

    def test_total_elapsed_sums_all_events(self):
        perf = PerfRecorder()
        perf.record("a", 1.0)
        perf.record("b", 2.0)
        self.assertEqual(perf.total_elapsed(), 3.0)


class TestSummary(unittest.TestCase):
    def test_summary_includes_known_phases_in_order(self):
        perf = PerfRecorder()
        perf.record("whisper", 1.0)
        perf.record("editorial", 2.0)
        perf.record("scene_render", 3.0, scene_id="1")
        perf.note_cache(True)
        text = perf.summary(phase_order=["whisper", "editorial", "scene_render", "mux"])
        self.assertIn("Whisper", text)
        self.assertIn("Editorial", text)
        self.assertIn("Rendering", text)
        self.assertIn("Total", text)
        self.assertIn("Cache: 1 hits / 0 misses", text)

    def test_summary_never_raises_with_no_events(self):
        perf = PerfRecorder()
        text = perf.summary()
        self.assertIn("Performance Summary", text)

    def test_summary_grand_total_includes_events_outside_phase_order(self):
        perf = PerfRecorder()
        perf.record("some_untracked_phase", 5.0)
        text = perf.summary(phase_order=["whisper"])
        self.assertIn("Total: 5.00s", text)

    def test_summary_never_raises_on_malformed_event(self):
        perf = PerfRecorder()
        # Directly inject a malformed event bypassing the safe record() path,
        # simulating a future bug elsewhere — summary() must degrade, not crash.
        perf.events.append(PerfEvent(name="x", duration_s=float("nan"), extra={}))
        text = perf.summary(phase_order=["x"])
        self.assertIsInstance(text, str)


if __name__ == "__main__":
    unittest.main()
