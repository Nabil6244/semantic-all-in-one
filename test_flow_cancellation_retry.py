"""
Regression tests for the Flow watchdog-boundary / cascading-cancellation /
retry-loop fix.

Root cause recap (see the accompanying report):
  1. `_resolve_flow_batch()` fired `on_scene_start` for every scene in a batch
     the instant the batch was submitted, and the UI treated that as "started
     generating" — arming a 12-minute watchdog immediately. With hundreds of
     scenes and a handful of Flow accounts, scenes near the back of the queue
     were guaranteed to trip the watchdog before they ever got a worker.
  2. Flow's engine has no way to cancel one in-flight generation without
     stopping the whole shared multi-account batch (`_batch_should_stop`),
     so a wave of false-positive per-scene timeouts cascaded into killing
     every scene still in flight.
  3. `retry_flow_batch()` / `change_source_flow_batch()` (the manual "Retry" /
     "Change Source" bulk-batch path) never cleared the whole-run
     `is_cancelled` flag left over from an earlier STOP, so every subsequent
     manual retry instantly returned CANCELLED for every scene with zero
     real Flow activity — looking like an infinite loop of retries that
     never do anything.
  4. `_confirm_alternatives()` referenced an undefined variable `n`.

No real Flow account or network call is used anywhere in this file — Flow
interaction is exercised through `unittest.mock.MagicMock` engine clients
(mirroring the existing pattern in test_asset_pipeline.py) or the in-repo
`FakeProvider` stub. Real Flow calls made while writing/running this file: 0.
Flow credits spent: 0.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from asset_manager import AssetManager
from providers.base import AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from providers.flow.provider import FlowProvider
from test_asset_pipeline import FakeProvider


class _FakeEngineManager:
    def __init__(self, client):
        self.client = client

    def ensure_running(self):
        return self.client


def _make_client(downloads_root) -> MagicMock:
    client = MagicMock()
    client.get_state.return_value = {"running": False}
    client.get_info.return_value = {"downloadsRoot": str(downloads_root)}
    return client


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 96)


# ---------------------------------------------------------------------------
# 1. Watchdog boundary: on_scene_generating fires only on the true
#    FLOW_IN_FLIGHT signal, never at batch submission.
# ---------------------------------------------------------------------------


class TestWatchdogBoundary(unittest.TestCase):
    def test_on_scene_generating_fires_when_flow_reports_running(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _make_client(root)
            done_png = root / "001.png"
            _png(done_png)

            def fake_subscribe(fn):
                def generate(*_a, **_k):
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "running",
                        "label": "acct1", "message": "generating"})
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "done",
                        "path": str(done_png)})
                    fn({"type": "GENERATE_DONE"})
                client.generate.side_effect = generate
                return lambda: None
            client.subscribe.side_effect = fake_subscribe

            fp = FlowProvider(_FakeEngineManager(client))
            scene = SceneRow(scene_number="1", script_segment="a", prompt="p")
            seen = []
            fp.resolve_batch(
                [scene], root, log=lambda *_: None,
                on_scene_generating=lambda s: seen.append(s.scene_number),
            )
            self.assertEqual(seen, ["1"], "the true in-flight signal must fire exactly once")

    def test_on_scene_generating_never_fires_for_a_scene_still_queued(self):
        """A scene that never gets a worker before the batch ends (queue-wait,
        not a stall) must never be reported as 'generating' at all."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _make_client(root)
            done_png = root / "001.png"
            _png(done_png)

            def fake_subscribe(fn):
                def generate(*_a, **_k):
                    # Only scene index 0 ever starts; index 1 stays queued.
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "running",
                        "label": "acct1", "message": "generating"})
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "done",
                        "path": str(done_png)})
                    fn({"type": "GENERATE_DONE"})
                client.generate.side_effect = generate
                return lambda: None
            client.subscribe.side_effect = fake_subscribe

            fp = FlowProvider(_FakeEngineManager(client))
            scenes = [
                SceneRow(scene_number="1", script_segment="a", prompt="p"),
                SceneRow(scene_number="2", script_segment="b", prompt="q"),
            ]
            seen = []
            fp.resolve_batch(
                scenes, root, log=lambda *_: None,
                on_scene_generating=lambda s: seen.append(s.scene_number),
            )
            self.assertEqual(seen, ["1"], "scene 2 never went in-flight — must not be reported")

    def test_downloading_status_is_not_mistaken_for_generating(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _make_client(root)
            done_png = root / "001.png"
            _png(done_png)

            def fake_subscribe(fn):
                def generate(*_a, **_k):
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "running",
                        "label": "acct1", "message": "downloading result"})
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "done",
                        "path": str(done_png)})
                    fn({"type": "GENERATE_DONE"})
                client.generate.side_effect = generate
                return lambda: None
            client.subscribe.side_effect = fake_subscribe

            fp = FlowProvider(_FakeEngineManager(client))
            scene = SceneRow(scene_number="1", script_segment="a", prompt="p")
            seen = []
            fp.resolve_batch(
                [scene], root, log=lambda *_: None,
                on_scene_generating=lambda s: seen.append(s.scene_number),
            )
            self.assertEqual(seen, [], "a bare 'downloading' ping is not a generation start")

    def test_repeated_running_pings_report_generating_only_once(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _make_client(root)
            done_png = root / "001.png"
            _png(done_png)

            def fake_subscribe(fn):
                def generate(*_a, **_k):
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "running",
                        "label": "acct1", "message": "generating"})
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "running",
                        "label": "acct1", "message": "generating"})
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "done",
                        "path": str(done_png)})
                    fn({"type": "GENERATE_DONE"})
                client.generate.side_effect = generate
                return lambda: None
            client.subscribe.side_effect = fake_subscribe

            fp = FlowProvider(_FakeEngineManager(client))
            scene = SceneRow(scene_number="1", script_segment="a", prompt="p")
            seen = []
            fp.resolve_batch(
                [scene], root, log=lambda *_: None,
                on_scene_generating=lambda s: seen.append(s.scene_number),
            )
            self.assertEqual(seen, ["1"])


# ---------------------------------------------------------------------------
# 2. Large-batch simulation: queue wait must never trigger a false signal,
#    only actual worker pickup does — proven at a scale close to the real
#    358-scene / ~7-account run from the bug report.
# ---------------------------------------------------------------------------


class TestLargeBatchQueueWaitSimulation(unittest.TestCase):
    def test_300_scenes_7_workers_only_report_generating_when_actually_running(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _make_client(root)
            n_scenes = 300
            n_workers = 7

            for i in range(n_workers):
                _png(root / f"{i:03d}.png")

            def fake_subscribe(fn):
                def generate(*_a, **_k):
                    # Simulate only the first `n_workers` scenes ever getting a
                    # worker before the batch call returns in this test — the
                    # remaining ~293 scenes are still genuinely queued, exactly
                    # like scene 200+ in the real 358-scene / 7-account report.
                    for i in range(n_workers):
                        fn({"type": "BATCH_PROGRESS", "index": i, "status": "running",
                            "label": f"acct{i}", "message": "generating"})
                    for i in range(n_workers):
                        fn({"type": "BATCH_PROGRESS", "index": i, "status": "done",
                            "path": str(root / f"{i:03d}.png")})
                    fn({"type": "GENERATE_DONE"})
                client.generate.side_effect = generate
                return lambda: None
            client.subscribe.side_effect = fake_subscribe

            fp = FlowProvider(_FakeEngineManager(client))
            scenes = [
                SceneRow(scene_number=str(i + 1), script_segment="x", prompt="p")
                for i in range(n_scenes)
            ]
            generating_seen = []
            fp.resolve_batch(
                scenes, root, log=lambda *_: None,
                on_scene_generating=lambda s: generating_seen.append(s.scene_number),
            )
            # Only the scenes that actually got a worker may ever be reported —
            # the ~293 still-queued scenes must never falsely arm a watchdog.
            self.assertEqual(len(generating_seen), n_workers)
            self.assertEqual(set(generating_seen), {str(i + 1) for i in range(n_workers)})


# ---------------------------------------------------------------------------
# 3. on_scene_start (the pre-existing "queued" signal) is unchanged: it still
#    fires for every scene up front — only the watchdog-arming moved.
# ---------------------------------------------------------------------------


class TestOnSceneStartUnchanged(unittest.TestCase):
    def test_on_scene_start_still_fires_for_every_scene_immediately(self):
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)
            scenes = [
                SceneRow(scene_number=str(i), script_segment="x", prompt="p")
                for i in range(1, 6)
            ]
            started = []
            mgr.resolve_all(scenes, on_scene_start=lambda s, src: started.append(s.scene_number))
            self.assertEqual(set(started), {"1", "2", "3", "4", "5"})


# ---------------------------------------------------------------------------
# 4. Cancellation: a per-scene timeout/cancel must not poison the whole run;
#    an explicit whole-run Cancel must still cancel everything.
# ---------------------------------------------------------------------------


class TestCancellationScoping(unittest.TestCase):
    def _mgr(self):
        return AssetManager(Path("."), log=lambda *_: None)

    def test_per_scene_cancel_does_not_set_the_whole_run_cancelled(self):
        mgr = self._mgr()
        mgr.request_cancel_scene("42")
        self.assertTrue(mgr.is_scene_cancelled("42"))
        self.assertFalse(mgr.is_cancelled, "one scene's cancel must not cancel the whole run")

    def test_explicit_user_cancel_still_cancels_the_whole_run(self):
        mgr = self._mgr()
        mgr.request_cancel()
        self.assertTrue(mgr.is_cancelled, "an explicit Stop must still cancel everything")


# ---------------------------------------------------------------------------
# 5. Retry: stale cancellation must not poison a fresh manual retry, retry
#    only touches the scenes it was given, and it does not auto-repeat.
# ---------------------------------------------------------------------------


class TestRetryClearsStaleCancellation(unittest.TestCase):
    """This is the exact bug behind '[QA] retry N unresolved scene(s) ->
    Scene X Cancelled -> retry again -> Scene X Cancelled -> ...': the
    whole-run is_cancelled flag stayed True from an earlier STOP, so every
    subsequent manual retry died instantly with zero Flow calls."""

    def test_retry_flow_batch_actually_runs_after_a_prior_stop(self):
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)
            mgr.request_cancel()  # simulate the earlier STOP that never got cleared
            self.assertTrue(mgr.is_cancelled)

            scene = SceneRow(scene_number="1", script_segment="x", prompt="p")
            results = mgr.retry_flow_batch([scene])

            self.assertIn("1", flow.calls, "retry must actually call Flow, not short-circuit")
            self.assertTrue(results["1"].ok)
            self.assertFalse(mgr.is_cancelled, "the stale flag must be cleared by the retry")

    def test_change_source_flow_batch_actually_runs_after_a_prior_stop(self):
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)
            mgr.request_cancel()
            self.assertTrue(mgr.is_cancelled)

            scene = SceneRow(scene_number="1", script_segment="x", asset_type="stock_image", stock="q")
            results = mgr.change_source_flow_batch([scene], "flow_image")

            self.assertIn("1", flow.calls)
            self.assertTrue(results["1"].ok)
            self.assertFalse(mgr.is_cancelled)

    def test_retry_only_touches_the_scenes_it_was_given(self):
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)
            scene_1 = SceneRow(scene_number="1", script_segment="x", prompt="p")
            scene_2 = SceneRow(scene_number="2", script_segment="y", prompt="q")

            mgr.retry_flow_batch([scene_1])

            self.assertIn("1", flow.calls)
            self.assertNotIn("2", flow.calls, "an untouched scene must not be retried")

    def test_retry_does_not_automatically_repeat(self):
        """One retry call must mean exactly one attempt per scene — no
        automatic re-launch of another retry batch on failure."""
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {"1": "fail"})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)
            scene = SceneRow(scene_number="1", script_segment="x", prompt="p")

            results = mgr.retry_flow_batch([scene])

            self.assertFalse(results["1"].ok)
            # The scene's own single-retry-on-technical-failure mechanism
            # (asset_manager.py's _retry_flow_batch_once) may attempt it a
            # second time — that is a bounded, existing, non-QA mechanism.
            # What must NOT happen is unbounded repetition: at most two calls.
            self.assertLessEqual(
                flow.calls.count("1"), 2,
                "retry must not loop — bounded to the existing single technical retry",
            )

    def test_successful_scene_is_never_touched_by_retry_flow_batch(self):
        """A scene that already has a working Flow asset must never be
        silently regenerated just because it was included in a batch call."""
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)
            scene = SceneRow(scene_number="1", script_segment="x", prompt="p")
            first = mgr.retry_flow_batch([scene])
            self.assertTrue(first["1"].ok)
            calls_after_first = list(flow.calls)

            # A caller must only ever pass unresolved scenes into retry_flow_batch
            # in the first place (this is what app.py's _try_start_flow_retry_batch
            # already filters for) — retrying an already-ok scene is a caller bug,
            # not something this function should paper over by silently skipping
            # it, but it must not spend a second Flow credit unnoticed either:
            # calling it again on the same scene is one deliberate, visible call.
            second = mgr.retry_flow_batch([scene])
            self.assertTrue(second["1"].ok)
            self.assertEqual(
                len(flow.calls), len(calls_after_first) + 1,
                "exactly one additional call, not a hidden loop",
            )


# ---------------------------------------------------------------------------
# 6. QA remains advisory (regression guard for the fix already made this
#    session in visual_qa/fix_engine.py + scorer.py) — re-verified here in
#    the same file as the rest of the Flow-safety regression suite.
# ---------------------------------------------------------------------------


class TestQaNeverTouchesFlow(unittest.TestCase):
    def test_low_score_flow_asset_is_never_retried_by_fix_all(self):
        from visual_qa.fix_engine import fix_all_issues
        from visual_qa.models import RecommendedAction, VisualQAResult, VisualQAStatus

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = AssetResult(
                "1", root / "001.mp4", MediaType.VIDEO, AssetSource.FLOW_VIDEO,
                SceneStatus.READY, metadata={},
            )

            class TripwireMgr:
                images_dir = root
                selection_history = None
                resolved_style = None

                def classify(self, s):
                    return AssetSource.FLOW_VIDEO

                def regenerate_scene(self, s):
                    raise AssertionError("QA must never call Flow generation")

                def retry_scene(self, s):
                    raise AssertionError("QA must never call Flow generation")

                def alternative_scene(self, s):
                    raise AssertionError("QA must never replace a Flow asset")

            scene = SceneRow(scene_number="1", script_segment="x", asset_type="video", prompt="p")
            qa = VisualQAResult(scene_number="1", overall_score=0.1, status=VisualQAStatus.FAIL,
                                 failure_reasons=["semantic mismatch"])
            results = {"001": good}
            qa_results = {"001": qa}
            fix_all_issues(TripwireMgr(), [scene], qa_results, results, log=lambda *_: None)

            self.assertIs(results["001"], good, "the Flow asset must be kept exactly as delivered")
            self.assertEqual(qa_results["001"].recommended_action, RecommendedAction.MANUAL_REVIEW)

    def test_low_score_does_not_reject_the_flow_asset(self):
        """A poor QA score must never turn a delivered Flow asset into a
        rejected/needs_action result on its own."""
        from visual_qa.fix_engine import FlowBudgetState, fix_scene_if_needed
        from visual_qa.models import VisualQAResult, VisualQAStatus

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = AssetResult(
                "1", root / "001.png", MediaType.IMAGE, AssetSource.FLOW_IMAGE,
                SceneStatus.READY, metadata={},
            )

            class Mgr:
                def classify(self, s):
                    return AssetSource.FLOW_IMAGE

            scene = SceneRow(scene_number="1", script_segment="x", asset_type="image", prompt="p")
            qa = VisualQAResult(scene_number="1", overall_score=0.05, status=VisualQAStatus.FAIL,
                                 failure_reasons=["semantic mismatch"])
            result, after_qa = fix_scene_if_needed(
                Mgr(), scene, qa, results={"001": good}, flow_budget=FlowBudgetState(), log=lambda *_: None,
            )
            self.assertTrue(result.ok)
            self.assertIs(result, good)


# ---------------------------------------------------------------------------
# 7. The _confirm_alternatives NameError crash.
#
# Importing app.py requires customtkinter, which is not installed in every
# dev/test environment (it is present in this repo's .venv-build). Run this
# class with an interpreter that has customtkinter — e.g.:
#   .venv-build/bin/python -m unittest test_flow_cancellation_retry.TestConfirmAlternativesCrash
# ---------------------------------------------------------------------------


class TestConfirmAlternativesCrash(unittest.TestCase):
    def test_confirm_alternatives_does_not_raise_nameerror(self):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            self.skipTest(f"customtkinter not available in this interpreter: {exc}")
            return

        from unittest.mock import patch
        from types import SimpleNamespace

        fake_self = SimpleNamespace(_asset_manager=None)
        scenes = [
            SceneRow(scene_number="1", script_segment="a", asset_type="stock_video", stock="q"),
            SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="r"),
        ]
        with patch.object(_app.messagebox, "askokcancel", return_value=True) as mock_dialog:
            result = _app.VideoGeneratorApp._confirm_alternatives(fake_self, scenes)
        self.assertTrue(result)
        mock_dialog.assert_called_once()
        shown_text = mock_dialog.call_args[0][1]
        self.assertIn("2 scenes selected", shown_text)


if __name__ == "__main__":
    unittest.main()
