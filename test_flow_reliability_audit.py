"""
Final reliability audit for the Flow pipeline — additive tests only, covering
gaps not already exercised by test_flow_cancellation_retry.py,
test_video_duration_cleanup.py, and test_visual_qa.py.

No real Flow account or network call anywhere in this file. Flow interaction
is exercised through unittest.mock.MagicMock engine clients and the in-repo
FakeProvider stub, mirroring the existing pattern in test_asset_pipeline.py.
Real Flow calls made while writing/running this file: 0. Flow credits
spent: 0.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from asset_manager import AssetManager
from providers.base import AssetSource, SceneRow
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
# Rule 4: a Flow failure on one scene must not cancel/touch a successful
# sibling scene in the same batch.
# ---------------------------------------------------------------------------


class TestFailureDoesNotCancelSuccessfulSiblings(unittest.TestCase):
    def test_one_failed_scene_does_not_stop_the_engine_or_touch_the_other(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = _make_client(root)
            done_png = root / "002.png"
            _png(done_png)

            def fake_subscribe(fn):
                def generate(*_a, **_k):
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "running",
                        "label": "acct1", "message": "generating"})
                    fn({"type": "BATCH_PROGRESS", "index": 1, "status": "running",
                        "label": "acct2", "message": "generating"})
                    # Scene 0 fails outright (a real Flow error, not a cancel).
                    fn({"type": "BATCH_PROGRESS", "index": 0, "status": "failed",
                        "message": "PUBLIC_ERROR_UNSAFE_GENERATION"})
                    # Scene 1 succeeds normally.
                    fn({"type": "BATCH_PROGRESS", "index": 1, "status": "done",
                        "path": str(done_png)})
                    fn({"type": "GENERATE_DONE"})
                client.generate.side_effect = generate
                return lambda: None
            client.subscribe.side_effect = fake_subscribe

            fp = FlowProvider(_FakeEngineManager(client))
            scenes = [
                SceneRow(scene_number="1", script_segment="a", prompt="bad prompt"),
                SceneRow(scene_number="2", script_segment="b", prompt="good prompt"),
            ]
            results = fp.resolve_batch(scenes, root, log=lambda *_: None,
                                        should_stop=lambda: False)

            self.assertFalse(results["1"].ok, "scene 1 genuinely failed")
            self.assertTrue(results["2"].ok, "a sibling failure must never cancel a success")
            client.stop.assert_not_called()

    def test_asset_manager_level_failure_leaves_other_scene_results_untouched(self):
        """Same guarantee one layer up, through AssetManager.resolve_all()."""
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {"1": "fail"})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)
            scenes = [
                SceneRow(scene_number="1", script_segment="a", prompt="p"),
                SceneRow(scene_number="2", script_segment="b", prompt="q"),
                SceneRow(scene_number="3", script_segment="c", prompt="r"),
            ]
            summary = mgr.resolve_all(scenes)
            self.assertFalse(summary.results["1"].ok)
            self.assertTrue(summary.results["2"].ok)
            self.assertTrue(summary.results["3"].ok)


# ---------------------------------------------------------------------------
# Rule 11: cancellation / retry / batch state cannot leak from one batch
# into the next.
# ---------------------------------------------------------------------------


class TestNoStateLeakAcrossBatches(unittest.TestCase):
    def test_two_sequential_retry_batches_are_fully_independent(self):
        """Batch 1 fails and leaves is_cancelled True (simulating an earlier
        STOP). Batch 2, for a completely different scene, must not inherit
        any of batch 1's cancellation or failure state."""
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)

            scene_a = SceneRow(scene_number="1", script_segment="a", prompt="p")
            mgr.retry_flow_batch([scene_a])
            mgr.request_cancel()  # simulate a STOP after batch 1
            self.assertTrue(mgr.is_cancelled)

            scene_b = SceneRow(scene_number="2", script_segment="b", prompt="q")
            results = mgr.retry_flow_batch([scene_b])

            self.assertIn("2", flow.calls, "batch 2 must actually run, not inherit batch 1's stop")
            self.assertTrue(results["2"].ok)
            self.assertFalse(mgr.is_cancelled)

    def test_a_cancelled_scene_from_batch_one_does_not_poison_batch_two(self):
        with TemporaryDirectory() as tmp:
            images = Path(tmp)
            flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
            mgr = AssetManager(images, flow_image_provider=flow, log=lambda *_: None)

            mgr.request_cancel_scene("1")
            self.assertTrue(mgr.is_scene_cancelled("1"))

            scene_2 = SceneRow(scene_number="2", script_segment="b", prompt="q")
            results = mgr.retry_flow_batch([scene_2])
            self.assertTrue(results["2"].ok)
            self.assertIn("2", flow.calls)

    def test_flow_retry_batch_busy_flag_resets_even_if_the_worker_raises(self):
        """app.py's _flow_retry_batch_busy guard must not get stuck True and
        permanently block every future Retry click if a batch call throws."""
        import inspect
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            self.skipTest(f"customtkinter not available in this interpreter: {exc}")
            return
        src = inspect.getsource(_app.VideoGeneratorApp._start_flow_batch)
        # The done-flag must be set unconditionally in a finally block, not
        # only on the success path.
        self.assertIn("finally:", src)
        finally_body = src.split("finally:", 1)[1]
        self.assertIn('"flow_retry_batch_done"', finally_body)


# ---------------------------------------------------------------------------
# Rule 13: the employee must be able to tell success / failure / waiting /
# needs-action apart at a glance — verify the status vocabulary stays
# distinct, and specifically that a QUEUED Flow scene is never mislabeled
# as actively processing (the exact confusion the watchdog fix depended on).
# ---------------------------------------------------------------------------


class TestSceneStatusesAreDistinguishable(unittest.TestCase):
    def test_queued_ready_processing_needs_action_all_render_differently(self):
        try:
            from app import _status_display
        except ModuleNotFoundError as exc:
            self.skipTest(f"customtkinter not available in this interpreter: {exc}")
            return

        labels = {}
        colors = {}
        for status in ("waiting", "ready", "generating", "needs_action", "cancelled", "skipped"):
            label, color = _status_display(status)
            labels[status] = label
            colors[status] = color

        self.assertEqual(len(set(labels.values())), len(labels), f"labels collide: {labels}")
        # QUEUED must not be visually indistinguishable from PROCESSING —
        # that ambiguity is exactly what let a queued scene look like it was
        # already running (and thus "should" be timing out).
        self.assertNotEqual(labels["waiting"], labels["generating"])
        self.assertNotEqual(colors["waiting"], colors["generating"])

    def test_on_scene_start_callback_uses_waiting_for_flow_sources(self):
        """Regression guard for the watchdog fix itself: the moment a Flow
        batch is submitted, scenes must show QUEUED, not PROCESSING — only
        the true in-flight signal (_on_scene_generating) may claim
        'generating'."""
        import inspect
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            self.skipTest(f"customtkinter not available in this interpreter: {exc}")
            return
        src = inspect.getsource(_app)
        self.assertIn('"scene_busy", (scene.scene_number, "waiting")', src)
        self.assertIn("_on_scene_generating", src)


if __name__ == "__main__":
    unittest.main()
