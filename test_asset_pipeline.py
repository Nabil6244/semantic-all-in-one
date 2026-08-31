#!/usr/bin/env python3
"""
Unit tests for the AI/Stock/Manual asset pipeline (SceneAssetRouter, AssetManager,
LocalProvider, and the StockProvider pipeline logic) — no network, no Node/Playwright,
no real Pexels/Flow calls. FlowProvider/PexelsBackend network paths are exercised via
fake in-repo providers that implement the same AssetProvider interface, so these tests
run anywhere Python + the stdlib run.

Run: python -m unittest test_asset_pipeline.py -v
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import video_generator as vg
from asset_manager import AssetManager
from providers.base import (
    AssetError,
    AssetProvider,
    AssetResult,
    AssetSource,
    MediaType,
    SceneRow,
    SceneStatus,
)
from providers.router import SceneAssetRouter


class FakeProvider(AssetProvider):
    """A scripted provider: resolve() returns pre-programmed AssetResults per scene
    number, and counts calls so tests can assert caching actually skipped a re-fetch."""

    def __init__(self, source: AssetSource, scripted: dict, media_type=MediaType.IMAGE):
        self.source = source
        self.scripted = scripted  # scene_number -> "ok" | "fail" | Exception
        self.media_type = media_type
        self.calls: list[str] = []

    def resolve(self, scene: SceneRow, images_dir: Path, log=print) -> AssetResult:
        self.calls.append(scene.scene_number)
        outcome = self.scripted.get(scene.scene_number, "ok")
        if outcome == "fail":
            return AssetResult(
                scene.scene_number, None, None, self.source, SceneStatus.FAILED,
                error=f"scripted failure for scene {scene.scene_number}",
            )
        if isinstance(outcome, Exception):
            raise outcome
        n = int(scene.scene_number)
        ext = ".mp4" if self.media_type == MediaType.VIDEO else ".jpg"
        target = Path(images_dir) / f"{n:03d}{ext}"
        target.write_bytes(b"fake-bytes")
        return AssetResult(
            scene.scene_number, target, self.media_type, self.source, SceneStatus.READY,
            metadata={"provider_asset_id": f"asset-{scene.scene_number}", "prompt": scene.prompt,
                      "stock_query": scene.stock},
        )

    def regenerate(self, scene, images_dir, exclude=None, log=print):
        return self.resolve(scene, images_dir, log=log)


def _write_csv(path: Path, rows: list[dict], columns=("scene_number", "script_segment", "prompt", "stock")):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(columns))
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


class AssetPipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "Images"
        self.images.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _manager(self, stock=None, flow=None):
        return AssetManager(self.images, stock_provider=stock, flow_image_provider=flow, log=lambda *_: None)


class TestBackwardCompat(AssetPipelineTestCase):
    def test_old_two_column_csv_all_local(self):
        (self.images / "001.png").write_bytes(b"x")
        (self.images / "002.png").write_bytes(b"x")
        rows = [SceneRow(scene_number="1", script_segment="a"), SceneRow(scene_number="2", script_segment="b")]
        mgr = self._manager()
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.ok)
        self.assertEqual(summary.results["1"].source, AssetSource.LOCAL)
        self.assertEqual(summary.results["2"].source, AssetSource.LOCAL)


class TestRouting(AssetPipelineTestCase):
    def test_prompt_routes_to_flow(self):
        scene = SceneRow(scene_number="1", script_segment="a", prompt="a cinematic scene")
        self.assertEqual(SceneAssetRouter.classify(scene), AssetSource.FLOW_IMAGE)

    def test_stock_routes_to_stock(self):
        scene = SceneRow(scene_number="1", script_segment="a", stock="sundial")
        self.assertEqual(SceneAssetRouter.classify(scene), AssetSource.STOCK)

    def test_manual_scene_with_local_file(self):
        (self.images / "001.png").write_bytes(b"x")
        scene = SceneRow(scene_number="1", script_segment="a")
        mgr = self._manager()
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.LOCAL)

    def test_prompt_and_stock_both_set_flow_wins_with_warning(self):
        scene = SceneRow(scene_number="1", script_segment="a", prompt="a prompt", stock="a query")
        self.assertEqual(SceneAssetRouter.classify(scene), AssetSource.FLOW_IMAGE)
        self.assertIsNotNone(scene.ignored_stock_warning)
        self.assertIn("ignoring stock", scene.ignored_stock_warning)

    def test_both_empty_and_no_local_file_is_validation_error(self):
        rows = [SceneRow(scene_number="1", script_segment="a")]
        errors = SceneAssetRouter.validate(rows, self.images)
        self.assertEqual(len(errors), 1)
        self.assertIn("Scene 1", errors[0])

        mgr = self._manager()
        with self.assertRaises(AssetError):
            mgr.resolve_all(rows)

    def test_documentary_asset_types_route_correctly(self):
        self.assertEqual(
            SceneAssetRouter.classify(
                SceneRow(scene_number="1", script_segment="a", asset_type="archive_video", prompt="apollo launch")
            ),
            AssetSource.ARCHIVE_VIDEO,
        )
        self.assertEqual(
            SceneAssetRouter.classify(
                SceneRow(scene_number="2", script_segment="b", asset_type="nasa_video", prompt="pluto flyby")
            ),
            AssetSource.NASA_VIDEO,
        )
        self.assertEqual(
            SceneAssetRouter.classify(
                SceneRow(scene_number="3", script_segment="c", asset_type="commons_video", prompt="moon landing")
            ),
            AssetSource.STOCK_VIDEO,
        )
        self.assertEqual(
            SceneAssetRouter.classify(
                SceneRow(scene_number="4", script_segment="d", asset_type="commons_image", prompt="solar system")
            ),
            AssetSource.STOCK_IMAGE,
        )


class TestStockAndFlowResolution(AssetPipelineTestCase):
    def test_stock_scene_resolves_and_downloads(self):
        stock = FakeProvider(AssetSource.STOCK, {})
        scene = SceneRow(scene_number="4", script_segment="a", stock="factory workers")
        mgr = self._manager(stock=stock)
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.STOCK)
        self.assertTrue((self.images / "004.jpg").is_file())

    def test_flow_scene_resolves_and_downloads(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        scene = SceneRow(scene_number="1", script_segment="a", prompt="a clockmaker")
        mgr = self._manager(flow=flow)
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.FLOW_IMAGE)
        self.assertTrue((self.images / "001.jpg").is_file())

    def test_image_and_video_media_types(self):
        flow_img = FakeProvider(AssetSource.FLOW_IMAGE, {}, media_type=MediaType.IMAGE)
        stock_vid = FakeProvider(AssetSource.STOCK, {}, media_type=MediaType.VIDEO)
        mgr = self._manager(stock=stock_vid, flow=flow_img)
        img_scene = SceneRow(scene_number="1", script_segment="a", prompt="x")
        vid_scene = SceneRow(scene_number="2", script_segment="b", stock="y")
        r1 = mgr.resolve_scene(img_scene)
        r2 = mgr.resolve_scene(vid_scene)
        self.assertEqual(r1.media_type, MediaType.IMAGE)
        self.assertEqual(r2.media_type, MediaType.VIDEO)
        self.assertTrue(r1.path.suffix == ".jpg")
        self.assertTrue(r2.path.suffix == ".mp4")

    def test_stock_provider_not_configured_fails_clearly(self):
        scene = SceneRow(scene_number="1", script_segment="a", stock="x")
        mgr = self._manager()  # no stock provider
        result = mgr.resolve_scene(scene)
        self.assertFalse(result.ok)
        self.assertIn("not configured", result.error)


class TestFailureHandling(AssetPipelineTestCase):
    def test_flow_failure_is_reported_per_scene_not_substituted(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"2": "fail"})
        rows = [
            SceneRow(scene_number="1", script_segment="a", prompt="ok prompt"),
            SceneRow(scene_number="2", script_segment="b", prompt="bad prompt"),
        ]
        mgr = self._manager(flow=flow)
        summary = mgr.resolve_all(rows)
        self.assertFalse(summary.ok)
        self.assertTrue(summary.results["1"].ok)
        self.assertFalse(summary.results["2"].ok)
        self.assertIn("scripted failure", summary.results["2"].error)
        # scene 2 must not have silently gotten scene 1's (or any) asset
        self.assertIsNone(summary.results["2"].path)

    def test_pexels_failure_is_reported_per_scene(self):
        stock = FakeProvider(AssetSource.STOCK, {"1": "fail"})
        rows = [SceneRow(scene_number="1", script_segment="a", stock="no results query")]
        mgr = self._manager(stock=stock)
        summary = mgr.resolve_all(rows)
        self.assertFalse(summary.ok)
        self.assertFalse(summary.results["1"].ok)


class TestParallelResolveAll(AssetPipelineTestCase):
    def test_parallel_stock_scenes_run_concurrently(self):
        class SlowStock(FakeProvider):
            def __init__(self):
                super().__init__(AssetSource.STOCK, {})
                self.delay = 0.15
                self.in_flight = 0
                self.max_in_flight = 0
                self._lock = threading.Lock()

            def resolve(self, scene, images_dir, log=print):
                with self._lock:
                    self.in_flight += 1
                    self.max_in_flight = max(self.max_in_flight, self.in_flight)
                try:
                    time.sleep(self.delay)
                    return super().resolve(scene, images_dir, log=log)
                finally:
                    with self._lock:
                        self.in_flight -= 1

        stock = SlowStock()
        rows = [
            SceneRow(scene_number=str(i), script_segment=f"s{i}", stock=f"query {i}")
            for i in range(1, 5)
        ]
        mgr = self._manager(stock=stock)
        started = time.time()
        summary = mgr.resolve_all(rows, max_parallel=4)
        elapsed = time.time() - started
        self.assertTrue(summary.ok)
        self.assertEqual(len(summary.results), 4)
        self.assertGreaterEqual(stock.max_in_flight, 2)
        self.assertLess(elapsed, stock.delay * 4)

    def test_one_failed_stock_scene_does_not_block_others(self):
        stock = FakeProvider(AssetSource.STOCK, {"2": "fail"})
        rows = [
            SceneRow(scene_number="1", script_segment="a", stock="one"),
            SceneRow(scene_number="2", script_segment="b", stock="two"),
            SceneRow(scene_number="3", script_segment="c", stock="three"),
        ]
        summary = self._manager(stock=stock).resolve_all(rows, max_parallel=3)
        self.assertTrue(summary.results["1"].ok)
        self.assertFalse(summary.results["2"].ok)
        self.assertTrue(summary.results["3"].ok)

    def test_resolve_all_progress_callbacks(self):
        stock = FakeProvider(AssetSource.STOCK, {})
        rows = [
            SceneRow(scene_number="1", script_segment="a", stock="one"),
            SceneRow(scene_number="2", script_segment="b", stock="two"),
        ]
        started: list[str] = []
        completed: list[str] = []

        def on_start(scene, source):
            started.append(scene.scene_number)

        def on_complete(scene, result):
            completed.append(scene.scene_number)

        summary = self._manager(stock=stock).resolve_all(
            rows, on_scene_start=on_start, on_scene_complete=on_complete, max_parallel=2
        )
        self.assertTrue(summary.ok)
        self.assertEqual(set(started), {"1", "2"})
        self.assertEqual(set(completed), {"1", "2"})


class TestCachingAndResume(AssetPipelineTestCase):
    def test_cached_asset_is_not_refetched(self):
        stock = FakeProvider(AssetSource.STOCK, {})
        scene = SceneRow(scene_number="1", script_segment="a", stock="sundial")
        mgr = self._manager(stock=stock)
        mgr.resolve_all([scene])
        self.assertEqual(stock.calls, ["1"])
        mgr.resolve_all([scene])  # second run, same manager/manifest
        self.assertEqual(stock.calls, ["1"], "cache hit should not call the provider again")

    def test_cache_invalidated_when_query_changes(self):
        stock = FakeProvider(AssetSource.STOCK, {})
        mgr = self._manager(stock=stock)
        mgr.resolve_all([SceneRow(scene_number="1", script_segment="a", stock="sundial")])
        mgr.resolve_all([SceneRow(scene_number="1", script_segment="a", stock="different query")])
        self.assertEqual(stock.calls, ["1", "1"], "a changed query must trigger a fresh fetch")

    def test_missing_cached_file_triggers_refetch(self):
        stock = FakeProvider(AssetSource.STOCK, {})
        scene = SceneRow(scene_number="1", script_segment="a", stock="sundial")
        mgr = self._manager(stock=stock)
        mgr.resolve_all([scene])
        (self.images / "001.jpg").unlink()
        mgr.resolve_all([scene])
        self.assertEqual(stock.calls, ["1", "1"])

    def test_stale_extension_replaced_on_new_download(self):
        # scene 1 starts as a stock .jpg, then routes to Flow (.mp4-producing fake) —
        # the old .jpg must be removed so the renderer doesn't see two files for scene 1.
        stock = FakeProvider(AssetSource.STOCK, {})
        mgr = self._manager(stock=stock)
        mgr.resolve_all([SceneRow(scene_number="1", script_segment="a", stock="sundial")])
        self.assertTrue((self.images / "001.jpg").is_file())

        flow = FakeProvider(AssetSource.FLOW_IMAGE, {}, media_type=MediaType.VIDEO)
        mgr2 = AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None)
        mgr2.resolve_all([SceneRow(scene_number="1", script_segment="a", prompt="now a prompt")])
        self.assertFalse((self.images / "001.jpg").is_file(), "stale .jpg must be removed")
        self.assertTrue((self.images / "001.mp4").is_file())

    def test_resume_after_partial_failure_only_retries_failed_scene(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"2": "fail"})
        rows = [
            SceneRow(scene_number=str(i), script_segment=f"scene {i}", prompt=f"prompt {i}")
            for i in range(1, 4)
        ]
        mgr = self._manager(flow=flow)
        summary = mgr.resolve_all(rows)
        self.assertFalse(summary.ok)
        # scene 2 gets one automatic same-source retry before landing at NEEDS_ACTION
        self.assertEqual(sorted(flow.calls), ["1", "2", "2", "3"])

        # "fix" the scripted failure (simulates the underlying issue being resolved)
        # and re-run with a FRESH manager pointed at the same manifest/images dir.
        flow.scripted = {}
        flow.calls = []
        mgr2 = self._manager(flow=flow)
        summary2 = mgr2.resolve_all(rows)
        self.assertTrue(summary2.ok)
        self.assertEqual(flow.calls, ["2"], "scenes 1 and 3 were already complete and must not be redone")

    def test_resume_reuses_when_prompt_none_vs_empty(self):
        """None vs '' prompt must not invalidate a complete cache hit."""
        (self.images / "001.jpg").write_bytes(b"fake")
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        mgr = self._manager(flow=flow)
        mgr.manifest.set(
            "1",
            {
                "status": "complete",
                "source": AssetSource.FLOW_IMAGE.value,
                "prompt": None,
                "stock_query": None,
                "local_path": str(self.images / "001.jpg"),
            },
        )
        scene = SceneRow(scene_number="1", script_segment="a", prompt="")
        summary = mgr.resolve_all([scene])
        self.assertTrue(summary.ok)
        self.assertEqual(flow.calls, [], "ready asset must not regenerate on prompt None/'' drift")

    def test_resume_finds_file_when_manifest_path_stale(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        scene = SceneRow(scene_number="1", script_segment="a", prompt="p")
        mgr = self._manager(flow=flow)
        self.assertTrue(mgr.resolve_all([scene]).ok)
        rec = mgr.manifest.get("1")
        self.assertIsNotNone(rec)
        rec["local_path"] = str(self.images / "missing_gone.jpg")
        mgr.manifest.set("1", rec)
        self.assertTrue((self.images / "001.jpg").is_file())

        flow.calls = []
        mgr2 = self._manager(flow=flow)
        mgr2.manifest.set("1", rec)
        summary = mgr2.resolve_all([scene])
        self.assertTrue(summary.ok)
        self.assertEqual(flow.calls, [], "stale local_path must fall back to Images/ file")


class TestMixedProject(AssetPipelineTestCase):
    def test_ten_plus_scene_mixed_project(self):
        (self.images / "010.png").write_bytes(b"x")  # one manual scene among the mix
        rows = []
        for i in range(1, 11):
            if i == 10:
                rows.append(SceneRow(scene_number=str(i), script_segment=f"s{i}"))  # manual
            elif i % 2 == 0:
                rows.append(SceneRow(scene_number=str(i), script_segment=f"s{i}", stock=f"query {i}"))
            else:
                rows.append(SceneRow(scene_number=str(i), script_segment=f"s{i}", prompt=f"prompt {i}"))

        stock = FakeProvider(AssetSource.STOCK, {})
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        mgr = self._manager(stock=stock, flow=flow)
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.ok, [r.error for r in summary.failed])
        self.assertEqual(summary.results["10"].source, AssetSource.LOCAL)
        self.assertEqual(len(stock.calls), 4)  # scenes 2,4,6,8
        self.assertEqual(len(flow.calls), 5)  # scenes 1,3,5,7,9


class TestFlowClientProtocol(unittest.TestCase):
    """Protocol-shape checks that don't need a live engine — full end-to-end coverage
    of FlowClient/FlowProvider against a fake WebSocket server lives in this session's
    manual verification; see the final report. This just locks the message shapes."""

    def test_generate_message_shape(self):
        from unittest.mock import MagicMock

        from providers.flow.client import FlowClient

        client = FlowClient.__new__(FlowClient)  # bypass connect() — just test message building
        client.send = MagicMock()
        client.generate(["prompt one", "prompt two"], settings={"imageCount": 1}, account_ids=["a", "b"])
        client.send.assert_called_once_with(
            {"type": "GENERATE", "prompts": "prompt one\nprompt two",
             "settings": {"imageCount": 1}, "accountIds": ["a", "b"]}
        )

    def test_stop_message_shape(self):
        from unittest.mock import MagicMock

        from providers.flow.client import FlowClient

        client = FlowClient.__new__(FlowClient)
        client.send = MagicMock()
        client.stop()
        client.send.assert_called_once_with({"type": "STOP"})


class _CancelAfterNProvider(FakeProvider):
    """Like FakeProvider, but triggers manager.request_cancel() after resolving the
    Nth scene — simulates a user clicking Cancel mid-run."""

    def __init__(self, source, manager, cancel_after: int):
        super().__init__(source, {})
        self.manager = manager
        self.cancel_after = cancel_after

    def resolve(self, scene, images_dir, log=print):
        result = super().resolve(scene, images_dir, log=log)
        if len(self.calls) >= self.cancel_after:
            self.manager.request_cancel()
        return result


class TestCancellation(AssetPipelineTestCase):
    def test_cancel_mid_run_skips_remaining_scenes_not_yet_started(self):
        rows = [
            SceneRow(scene_number=str(i), script_segment=f"s{i}", stock=f"query {i}")
            for i in range(1, 5)
        ]
        mgr = self._manager()
        stock = _CancelAfterNProvider(AssetSource.STOCK, mgr, cancel_after=2)
        mgr.stock_provider = stock

        summary = mgr.resolve_all(rows, max_parallel=1)
        self.assertTrue(summary.results["1"].ok)
        self.assertTrue(summary.results["2"].ok)
        self.assertEqual(summary.results["3"].status, SceneStatus.CANCELLED)
        self.assertEqual(summary.results["4"].status, SceneStatus.CANCELLED)
        self.assertEqual(stock.calls, ["1", "2"], "cancelled scenes must never call the provider")
        self.assertFalse(summary.ok)
        self.assertEqual(len(summary.cancelled), 2)
        self.assertEqual(len(summary.failed), 0, "cancelled scenes must not be reported as failed")

    def test_cancel_before_run_skips_everything(self):
        rows = [SceneRow(scene_number="1", script_segment="a", stock="x")]
        stock = FakeProvider(AssetSource.STOCK, {})
        mgr = self._manager(stock=stock)
        mgr.request_cancel()
        summary = mgr.resolve_all(rows)
        # resolve_all() resets cancel state at the start of a fresh run — cancelling
        # before calling it should NOT silently skip a run the caller just started.
        self.assertTrue(summary.ok)
        self.assertEqual(stock.calls, ["1"])

    def test_reset_cancel_allows_a_clean_rerun(self):
        rows = [SceneRow(scene_number="1", script_segment="a", stock="x")]
        stock = FakeProvider(AssetSource.STOCK, {})
        mgr = self._manager(stock=stock)
        mgr.request_cancel()
        self.assertTrue(mgr.is_cancelled)
        mgr.reset_cancel()
        self.assertFalse(mgr.is_cancelled)
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.ok)

    def test_flow_batch_stop_signal_sent_on_cancel(self):
        """FlowProvider.resolve_batch must call client.stop() when should_stop() flips
        true, not just silently stop polling — verified against a mock client's
        recorded calls (protocol-level; live behavior verified separately, see report)."""
        from unittest.mock import MagicMock

        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client
            def ensure_running(self):
                return self.client

        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": "/tmp/doesnotmatter"}

        # Capture the real on_message callback resolve_batch registers, so
        # client.stop() can synchronously deliver GENERATE_DONE through it —
        # avoids the real implementation's 15s grace-period wait in this test.
        captured_callback = {}

        def fake_subscribe(fn):
            captured_callback["fn"] = fn
            return lambda: None

        def fake_stop():
            captured_callback["fn"]({"type": "GENERATE_DONE"})

        client.subscribe.side_effect = fake_subscribe
        client.stop.side_effect = fake_stop

        fp = FlowProvider(FakeEngineManager(client))
        scenes = [SceneRow(scene_number="1", script_segment="a", prompt="x")]
        results = fp.resolve_batch(
            scenes, self.images, log=lambda *_: None, should_stop=lambda: True
        )

        client.stop.assert_called_once()
        self.assertEqual(results["1"].status, SceneStatus.CANCELLED)

    def test_flow_timeout_keeps_finished_scenes_and_resets_engine(self):
        """On GENERATE timeout, keep scenes that already finished and stop/reset
        the engine so Retry is not blocked by a stuck running flag."""
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client

            def ensure_running(self):
                return self.client

        client = MagicMock()
        client.get_state.return_value = {"running": False}
        run_root = self.images.parent / "flow_run"
        run_root.mkdir(parents=True, exist_ok=True)
        client.get_info.return_value = {"downloadsRoot": str(run_root)}

        done_png = run_root / "batch" / "001.png"
        done_png.parent.mkdir(parents=True, exist_ok=True)
        done_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 96)

        def fake_subscribe(fn):
            def generate(*_a, **_k):
                fn({
                    "type": "BATCH_PROGRESS",
                    "index": 0,
                    "status": "done",
                    "path": str(done_png),
                })
                fn({
                    "type": "PROMPT_RESULT",
                    "index": 0,
                    "path": str(done_png),
                    "status": "done",
                })
                # Never send GENERATE_DONE — force the timeout path.
            client.generate.side_effect = generate
            return lambda: None

        client.subscribe.side_effect = fake_subscribe

        orig_timeout = flow_mod.GENERATE_TIMEOUT_SECONDS
        flow_mod.GENERATE_TIMEOUT_SECONDS = 0.05
        try:
            fp = FlowProvider(FakeEngineManager(client))
            scenes = [
                SceneRow(scene_number="1", script_segment="a", prompt="done"),
                SceneRow(scene_number="2", script_segment="b", prompt="pending"),
            ]
            results = fp.resolve_batch(scenes, self.images, log=lambda *_: None)
        finally:
            flow_mod.GENERATE_TIMEOUT_SECONDS = orig_timeout

        client.stop.assert_called()
        client.reset_generate.assert_called()
        self.assertEqual(results["1"].status, SceneStatus.READY)
        self.assertEqual(results["2"].status, SceneStatus.FAILED)
        self.assertIn("Timed out", results["2"].error or "")

    def test_stale_running_engine_is_stopped_not_failed(self):
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client
            def ensure_running(self):
                return self.client

        client = MagicMock()
        calls = {"n": 0}

        def get_state():
            calls["n"] += 1
            return {"running": calls["n"] == 1}

        client.get_state.side_effect = get_state
        client.get_info.return_value = {"downloadsRoot": "/tmp/doesnotmatter"}

        def fake_subscribe(fn):
            def generate(*_a, **_k):
                fn({"type": "GENERATE_DONE"})
            client.generate.side_effect = generate
            return lambda: None

        client.subscribe.side_effect = fake_subscribe

        orig_stale = flow_mod._SOFT_STOP_AFTER_SECONDS
        orig_force = flow_mod._FORCE_RESET_AFTER_SECONDS
        orig_poll = flow_mod._IDLE_POLL_SECONDS
        flow_mod._SOFT_STOP_AFTER_SECONDS = 0.0
        flow_mod._FORCE_RESET_AFTER_SECONDS = 0.05
        flow_mod._IDLE_POLL_SECONDS = 0.01
        try:
            fp = FlowProvider(FakeEngineManager(client))
            scenes = [SceneRow(scene_number="1", script_segment="a", prompt="x")]
            results = fp.resolve_batch(scenes, self.images, log=lambda *_: None)
        finally:
            flow_mod._SOFT_STOP_AFTER_SECONDS = orig_stale
            flow_mod._FORCE_RESET_AFTER_SECONDS = orig_force
            flow_mod._IDLE_POLL_SECONDS = orig_poll

        client.stop.assert_called()
        client.generate.assert_called()
        self.assertNotIn("already running", (results["1"].error or "").lower())
        self.assertNotIn("try again shortly", (results["1"].error or "").lower())

    def test_flow_places_into_assets_as_each_scene_finishes(self):
        """assets/ must fill during the batch, not only after GENERATE_DONE."""
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client

            def ensure_running(self):
                return self.client

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 96
        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": str(self.images)}
        mid_batch_asset = {"path": None}
        ready_calls = []

        def fake_subscribe(fn):
            def generate(*_a, **kwargs):
                out = Path(kwargs["settings"]["outputDir"])
                path = out / "001.png"
                path.write_bytes(png)
                fn({
                    "type": "BATCH_PROGRESS",
                    "index": 0,
                    "status": "done",
                    "path": str(path),
                })
                # Still generating the rest of the batch — asset must already exist.
                mid_batch_asset["path"] = self.images / "001.png"
                self.assertTrue(
                    mid_batch_asset["path"].is_file(),
                    "file must land in assets/ before GENERATE_DONE",
                )
                self.assertEqual(len(ready_calls), 1)
                fn({"type": "GENERATE_DONE", "outputDir": str(out)})
            client.generate.side_effect = generate
            return lambda: None

        client.subscribe.side_effect = fake_subscribe

        orig_settle = flow_mod._BATCH_SETTLE_SECONDS
        flow_mod._BATCH_SETTLE_SECONDS = 0.0
        try:
            fp = FlowProvider(FakeEngineManager(client))
            scenes = [SceneRow(scene_number="1", script_segment="a", prompt="x")]
            results = fp.resolve_batch(
                scenes,
                self.images,
                log=lambda *_: None,
                on_scene_ready=lambda s, r: ready_calls.append((s.scene_number, r.status)),
            )
        finally:
            flow_mod._BATCH_SETTLE_SECONDS = orig_settle

        self.assertEqual(results["1"].status, SceneStatus.READY)
        self.assertTrue((self.images / "001.png").is_file())
        self.assertEqual(ready_calls, [("1", SceneStatus.READY)])

    def test_flow_timeout_picks_up_files_without_progress(self):
        """Timeout must still copy files already on disk, even with no DONE event."""
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client

            def ensure_running(self):
                return self.client

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 96
        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": str(self.images)}

        def fake_subscribe(fn):
            def generate(*_a, **kwargs):
                out = Path(kwargs["settings"]["outputDir"])
                (out / "001.png").write_bytes(png)
                (out / "002.png").write_bytes(png)
                fn({
                    "type": "BATCH_PROGRESS",
                    "index": 0,
                    "status": "done",
                    "path": str(out / "001.png"),
                })
            client.generate.side_effect = generate
            return lambda: None

        client.subscribe.side_effect = fake_subscribe

        orig_timeout = flow_mod.GENERATE_TIMEOUT_SECONDS
        orig_settle = flow_mod._BATCH_SETTLE_SECONDS
        flow_mod.GENERATE_TIMEOUT_SECONDS = 0.05
        flow_mod._BATCH_SETTLE_SECONDS = 0.0
        try:
            fp = FlowProvider(FakeEngineManager(client))
            scenes = [
                SceneRow(scene_number="1", script_segment="a", prompt="done"),
                SceneRow(scene_number="2", script_segment="b", prompt="silent"),
            ]
            results = fp.resolve_batch(scenes, self.images, log=lambda *_: None)
        finally:
            flow_mod.GENERATE_TIMEOUT_SECONDS = orig_timeout
            flow_mod._BATCH_SETTLE_SECONDS = orig_settle

        self.assertEqual(results["1"].status, SceneStatus.READY)
        self.assertEqual(results["2"].status, SceneStatus.READY)

    def test_flow_empty_abort_retries_once_for_large_batch(self):
        """Leftover stopAll / stale GENERATE_DONE: retry GENERATE once when a
        large batch finishes instantly with zero files."""
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client

            def ensure_running(self):
                return self.client

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 96
        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": str(self.images)}
        calls = {"n": 0}

        def fake_subscribe(fn):
            def generate(*_a, **kwargs):
                calls["n"] += 1
                out = Path(kwargs["settings"]["outputDir"])
                if calls["n"] == 1:
                    fn({"type": "GENERATE_DONE"})
                    return
                for i in range(4):
                    path = out / f"{i + 1:03d}.png"
                    path.write_bytes(png)
                    fn({
                        "type": "BATCH_PROGRESS",
                        "index": i,
                        "status": "done",
                        "path": str(path),
                    })
                fn({"type": "GENERATE_DONE", "outputDir": str(out)})
            client.generate.side_effect = generate
            return lambda: None

        client.subscribe.side_effect = fake_subscribe

        orig_settle = flow_mod._BATCH_SETTLE_SECONDS
        flow_mod._BATCH_SETTLE_SECONDS = 0.0
        try:
            fp = FlowProvider(FakeEngineManager(client))
            scenes = [
                SceneRow(scene_number=str(i), script_segment="a", prompt="x")
                for i in range(1, 5)
            ]
            results = fp.resolve_batch(scenes, self.images, log=lambda *_: None)
        finally:
            flow_mod._BATCH_SETTLE_SECONDS = orig_settle

        self.assertEqual(calls["n"], 2)
        for i in range(1, 5):
            self.assertEqual(results[str(i)].status, SceneStatus.READY)

    def test_flow_empty_abort_retries_single_scene(self):
        """1-scene Flow video used to skip ghost retry (min=4) and fail as
        'not downloaded' — now empty GENERATE_DONE retries once."""
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client

            def ensure_running(self):
                return self.client

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 96
        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": str(self.images)}
        calls = {"n": 0}

        def fake_subscribe(fn):
            def generate(*_a, **kwargs):
                calls["n"] += 1
                out = Path(kwargs["settings"]["outputDir"])
                if calls["n"] == 1:
                    fn({"type": "GENERATE_DONE"})
                    return
                path = out / "001.png"
                path.write_bytes(png)
                fn({
                    "type": "BATCH_PROGRESS",
                    "index": 0,
                    "status": "done",
                    "path": str(path),
                })
                fn({"type": "GENERATE_DONE", "outputDir": str(out)})
            client.generate.side_effect = generate
            return lambda: None

        client.subscribe.side_effect = fake_subscribe

        orig_settle = flow_mod._BATCH_SETTLE_SECONDS
        flow_mod._BATCH_SETTLE_SECONDS = 0.0
        try:
            fp = FlowProvider(FakeEngineManager(client))
            scenes = [SceneRow(scene_number="1", script_segment="a", prompt="x")]
            results = fp.resolve_batch(scenes, self.images, log=lambda *_: None)
        finally:
            flow_mod._BATCH_SETTLE_SECONDS = orig_settle

        self.assertEqual(calls["n"], 2)
        self.assertEqual(results["1"].status, SceneStatus.READY)

    def test_flow_empty_abort_still_fails_clearly_after_retry(self):
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client

            def ensure_running(self):
                return self.client

        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": str(self.images)}
        calls = {"n": 0}

        def fake_subscribe(fn):
            def generate(*_a, **_k):
                calls["n"] += 1
                fn({"type": "GENERATE_DONE"})
            client.generate.side_effect = generate
            return lambda: None

        client.subscribe.side_effect = fake_subscribe

        orig_settle = flow_mod._BATCH_SETTLE_SECONDS
        flow_mod._BATCH_SETTLE_SECONDS = 0.0
        try:
            fp = FlowProvider(FakeEngineManager(client))
            scenes = [SceneRow(scene_number="1", script_segment="a", prompt="x")]
            results = fp.resolve_batch(scenes, self.images, log=lambda *_: None)
        finally:
            flow_mod._BATCH_SETTLE_SECONDS = orig_settle

        self.assertEqual(calls["n"], 2)
        self.assertEqual(results["1"].status, SceneStatus.FAILED)
        err = (results["1"].error or "").lower()
        self.assertTrue(
            "aborted" in err or "without running" in err or "missing" in err,
            results["1"].error,
        )
    def test_flow_generate_timeout_scales_with_batch_size(self):
        from unittest.mock import MagicMock

        from providers.flow import provider as flow_mod
        from providers.flow.provider import FlowProvider

        fp = FlowProvider(MagicMock())
        self.assertGreaterEqual(fp._generate_timeout_seconds(164), 164 * 25)
        self.assertGreaterEqual(
            max(flow_mod._IDLE_WAIT_TIMEOUT + 30.0, fp._generate_timeout_seconds(164) + 30.0),
            fp._generate_timeout_seconds(164) + 30.0,
        )
        orig = flow_mod.GENERATE_TIMEOUT_SECONDS
        flow_mod.GENERATE_TIMEOUT_SECONDS = 0.05
        try:
            self.assertAlmostEqual(fp._generate_timeout_seconds(10), 0.05)
        finally:
            flow_mod.GENERATE_TIMEOUT_SECONDS = orig


class TestAssetTypeCsvFormat(AssetPipelineTestCase):
    """New CSV format: scene_number,script_segment,asset_type,prompt."""

    def test_asset_type_routes_image_video_stock_local(self):
        image_row = {"scene_number": "1", "script_segment": "a", "asset_type": "image", "prompt": "a city"}
        video_row = {"scene_number": "2", "script_segment": "b", "asset_type": "video", "prompt": "a launch"}
        stock_row = {"scene_number": "3", "script_segment": "c", "asset_type": "stock", "prompt": "a market"}
        local_row = {"scene_number": "4", "script_segment": "d", "asset_type": "local", "prompt": ""}

        image_scene = SceneRow.from_csv_row(image_row)
        video_scene = SceneRow.from_csv_row(video_row)
        stock_scene = SceneRow.from_csv_row(stock_row)
        local_scene = SceneRow.from_csv_row(local_row)

        self.assertEqual(SceneAssetRouter.classify(image_scene), AssetSource.FLOW_IMAGE)
        self.assertEqual(SceneAssetRouter.classify(video_scene), AssetSource.FLOW_VIDEO)
        self.assertEqual(SceneAssetRouter.classify(stock_scene), AssetSource.STOCK)
        self.assertIsNone(SceneAssetRouter.classify(local_scene))  # falls back to a local file

        # asset_type=stock: the single `prompt` column doubles as the stock query.
        self.assertEqual(stock_scene.stock, "a market")
        self.assertEqual(stock_scene.prompt, "")

    def test_flow_video_and_flow_image_csv_aliases(self):
        video = SceneRow.from_csv_row(
            {
                "scene_number": "1",
                "script_segment": "a",
                "asset_type": "flow_video",
                "prompt": "icy planet flythrough",
            }
        )
        image = SceneRow.from_csv_row(
            {
                "scene_number": "2",
                "script_segment": "b",
                "asset_type": "flow_image",
                "prompt": "pluto frost close-up",
            }
        )
        self.assertEqual(video.asset_type, "video")
        self.assertEqual(image.asset_type, "image")
        self.assertEqual(SceneAssetRouter.classify(video), AssetSource.FLOW_VIDEO)
        self.assertEqual(SceneAssetRouter.classify(image), AssetSource.FLOW_IMAGE)

    def test_image_and_video_scenes_batch_separately(self):
        image_p = FakeProvider(AssetSource.FLOW_IMAGE, {})
        video_p = FakeProvider(AssetSource.FLOW_VIDEO, {}, media_type=MediaType.VIDEO)
        mgr = AssetManager(
            self.images, flow_image_provider=image_p, flow_video_provider=video_p, log=lambda *_: None
        )
        rows = [
            SceneRow.from_csv_row({"scene_number": "1", "script_segment": "a", "asset_type": "image", "prompt": "x"}),
            SceneRow.from_csv_row({"scene_number": "2", "script_segment": "b", "asset_type": "video", "prompt": "y"}),
        ]
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.ok, [r.error for r in summary.failed])
        self.assertEqual(image_p.calls, ["1"])
        self.assertEqual(video_p.calls, ["2"])
        self.assertEqual(summary.results["1"].source, AssetSource.FLOW_IMAGE)
        self.assertEqual(summary.results["2"].source, AssetSource.FLOW_VIDEO)
        self.assertTrue((self.images / "002.mp4").is_file())


class TestDocumentaryProviders(AssetPipelineTestCase):
    def test_expanded_media_queries_shortens_director_prompts(self):
        from providers.media_clip.queries import expanded_media_queries

        scene = SceneRow(
            scene_number="4",
            script_segment="Pluto",
            asset_type="nasa_video",
            prompt="new horizons pluto encounter animation",
        )
        expanded = expanded_media_queries(scene)
        self.assertIn("new horizons pluto encounter animation", expanded)
        self.assertIn("new horizons pluto", expanded)

    def test_nasa_backend_reads_nasa_id_from_search_data(self):
        from providers.nasa.api_backend import NasaMediaBackend

        class FakeResp:
            status_code = 200

            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        backend = NasaMediaBackend()
        backend._session = type("S", (), {})()
        search_payload = {
            "collection": {
                "items": [
                    {
                        "data": [{"nasa_id": "NH001", "title": "Pluto Flyby"}],
                        "links": [{"href": "https://images.nasa.gov/details/NH001"}],
                    }
                ]
            }
        }
        asset_payload = {
            "collection": {
                "items": [
                    {"href": "http://images-assets.nasa.gov/video/NH001/NH001~orig.mp4"},
                ]
            }
        }

        def fake_get(url, params=None, timeout=None):
            if "search" in url:
                return FakeResp(search_payload)
            return FakeResp(asset_payload)

        backend._session.get = fake_get
        hits = backend.search("pluto")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].nasa_id, "NH001")
        self.assertIn(".mp4", hits[0].download_url)

    def test_nasa_provider_tries_broader_query_after_zero_hits(self):
        from unittest.mock import patch

        from providers.nasa.api_backend import NasaCandidate
        from providers.nasa.provider import NasaProvider

        tried = []

        class FakeNasaBackend:
            def search(self, query, max_results=None):
                tried.append(query)
                if query == "new horizons pluto":
                    return [
                        NasaCandidate(
                            nasa_id="NH001",
                            title="New Horizons Pluto Flyby",
                            download_url="https://example.invalid/pluto.mp4",
                            duration=60.0,
                        )
                    ]
                return []

            def resolve_nasa_id(self, nasa_id):
                return None

        provider = NasaProvider(backend=FakeNasaBackend(), clip_duration=3.0)
        scene = SceneRow(
            scene_number="4",
            script_segment="Pluto",
            asset_type="nasa_video",
            prompt="new horizons pluto encounter animation",
        )
        target = self.images / "004.mp4"
        with patch("providers.nasa.provider.download_clip", return_value=target):
            target.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            result = provider.resolve(scene, self.images, log=lambda *_: None)
        self.assertTrue(result.ok)
        self.assertIn("new horizons pluto", tried)

    def test_archive_provider_with_fake_backend(self):
        from providers.archive.provider import ArchiveProvider

        class FakeArchiveBackend:
            def search(self, query, max_results=None):
                from providers.archive.ia_backend import ArchiveCandidate
                return [
                    ArchiveCandidate(
                        identifier="apollo11",
                        title="Apollo 11 Launch",
                        description="Saturn V liftoff",
                        download_url="https://example.invalid/apollo.mp4",
                        duration=120.0,
                        source_url="https://archive.org/details/apollo11",
                    )
                ]

            def resolve_identifier(self, identifier):
                return self.search(identifier)[0]

        provider = ArchiveProvider(backend=FakeArchiveBackend(), clip_duration=3.0)
        provider.resolve = lambda scene, images_dir, log=print: AssetResult(
            scene.scene_number,
            images_dir / "001.mp4",
            MediaType.VIDEO,
            AssetSource.ARCHIVE_VIDEO,
            SceneStatus.READY,
            metadata={"provider_asset_id": "apollo11"},
        )
        scene = SceneRow(
            scene_number="1",
            script_segment="Apollo launches",
            asset_type="archive_video",
            prompt="apollo 11 launch",
        )
        mgr = AssetManager(self.images, archive_provider=provider, log=lambda *_: None)
        (self.images / "001.mp4").write_bytes(b"fake")
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.ARCHIVE_VIDEO)


class TestFlowMediaKindRouting(AssetPipelineTestCase):
    """Traces the exact concern from the bug report: does a video-typed scene
    actually reach generateOneVideo (via a "video" GENERATE message), and does
    the provider refuse to accept an image mislabeled as a video?"""

    def test_video_provider_sends_mediaKind_video_never_image(self):
        from unittest.mock import MagicMock

        from providers.flow.provider import FlowProvider

        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": "/tmp/doesnotmatter"}
        captured = {}

        def fake_subscribe(fn):
            captured["fn"] = fn
            return lambda: None

        def fake_stop():
            fn = captured.get("fn")
            if fn:
                fn({"type": "GENERATE_DONE"})

        client.subscribe.side_effect = fake_subscribe
        client.stop.side_effect = fake_stop

        class FakeEngineManager:
            def ensure_running(self_):
                return client

        fp = FlowProvider(
            FakeEngineManager(), media_kind="video", account_ids=["acct-A", "acct-B"],
            flow_settings={"videoModel": "veo_3_1_t2v_quality", "videoDuration": 6},
        )
        scenes = [SceneRow(scene_number="3", script_segment="x", asset_type="video", prompt="a rocket launch")]
        try:
            fp.resolve_batch(scenes, self.images, log=lambda *_: None, should_stop=lambda: True)
        except Exception:
            pass

        sent_kwargs = client.generate.call_args.kwargs
        self.assertEqual(sent_kwargs["settings"]["mediaKind"], "video")
        self.assertNotEqual(sent_kwargs["settings"]["mediaKind"], "image")
        self.assertEqual(sent_kwargs["account_ids"], ["acct-A", "acct-B"])
        self.assertIn("outputDir", sent_kwargs["settings"])
        self.assertTrue(sent_kwargs["settings"]["outputDir"])

    def test_image_mislabeled_as_video_is_rejected_not_accepted(self):
        from providers.base import sniff_media_kind
        from providers.flow.provider import FlowProvider

        # A real PNG magic-byte header, saved with a .mp4 name — simulates the
        # exact failure mode from the bug report if it were ever to occur.
        fake_dir = self.images / "acct1"
        fake_dir.mkdir()
        bad_file = fake_dir / "001.mp4"
        bad_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 96)

        self.assertEqual(sniff_media_kind(bad_file), "image")

        class DummyEngineManager:
            def ensure_running(self_):
                raise AssertionError("not reached in this test")

        fp = FlowProvider(DummyEngineManager(), media_kind="video")
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="video", prompt="p")
        result = fp._resolve_one_result(0, scene, self.images, str(self.images), None, log=lambda *_: None)
        self.assertFalse(result.ok)
        self.assertIn("image", result.error.lower())
        self.assertFalse((self.images / "001.mp4").is_file(), "a mismatched file must never be accepted as this scene's asset")


def _png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 96


class TestFlowRunIsolation(AssetPipelineTestCase):
    """A leftover Flow_Images/001.png from another project must never become this scene."""

    def _image_provider(self):
        from providers.flow.provider import FlowProvider

        class DummyEngineManager:
            def ensure_running(self_):
                raise AssertionError("not reached in this test")

        return FlowProvider(DummyEngineManager(), media_kind="image")

    def test_leftover_global_001_is_not_used(self):
        import os
        import time

        fp = self._image_provider()
        old_root = self.tmp / "Flow_Images"
        (old_root / "acct").mkdir(parents=True)
        leftover = old_root / "acct" / "001.png"
        leftover.write_bytes(_png_bytes())
        age = time.time() - 86400
        os.utime(leftover, (age, age))

        project = self.tmp / "new_project"
        run_dir = project / "flow" / "runs" / "run-new"
        assets = project / "assets"
        run_dir.mkdir(parents=True)
        assets.mkdir(parents=True)
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="image", prompt="new prompt")
        result = fp._resolve_one_result(
            0,
            scene,
            assets,
            str(run_dir),
            None,
            log=lambda *_: None,
            engine_root=str(old_root),
            batch_started_at=time.time(),
        )
        self.assertFalse(result.ok)
        err = result.error.lower()
        self.assertTrue(
            any(p in err for p in ("leftover", "engine aborted", "did not download")),
            result.error,
        )
        self.assertFalse((assets / "001.png").is_file())

    def test_this_run_file_is_used_not_leftover(self):
        import os
        import time

        fp = self._image_provider()
        old_root = self.tmp / "Flow_Images"
        (old_root / "acct").mkdir(parents=True)
        leftover = old_root / "acct" / "001.png"
        leftover.write_bytes(_png_bytes() + b"OLD")
        age = time.time() - 86400
        os.utime(leftover, (age, age))

        project = self.tmp / "new_project"
        run_dir = project / "flow" / "runs" / "run-new"
        assets = project / "assets"
        (run_dir / "acct").mkdir(parents=True)
        assets.mkdir(parents=True)
        fresh = run_dir / "acct" / "001.png"
        fresh.write_bytes(_png_bytes() + b"NEW")
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="image", prompt="new prompt")
        result = fp._resolve_one_result(
            0,
            scene,
            assets,
            str(run_dir),
            None,
            log=lambda *_: None,
            engine_root=str(old_root),
            batch_started_at=time.time() - 1,
        )
        self.assertTrue(result.ok, result.error)
        self.assertTrue((assets / "001.png").is_file())
        self.assertTrue((assets / "001.png").read_bytes().endswith(b"NEW"))

    def test_progress_path_wins_over_leftover(self):
        import os
        import time

        fp = self._image_provider()
        old_root = self.tmp / "Flow_Images"
        (old_root / "acct").mkdir(parents=True)
        leftover = old_root / "acct" / "001.png"
        leftover.write_bytes(_png_bytes() + b"OLD")
        age = time.time() - 86400
        os.utime(leftover, (age, age))

        project = self.tmp / "new_project"
        run_dir = project / "flow" / "runs" / "run-new"
        assets = project / "assets"
        run_dir.mkdir(parents=True)
        assets.mkdir(parents=True)
        saved = run_dir / "acct-b" / "001.png"
        saved.parent.mkdir(parents=True)
        saved.write_bytes(_png_bytes() + b"PATH")
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="image", prompt="p")
        result = fp._resolve_one_result(
            0,
            scene,
            assets,
            str(run_dir),
            {"status": "done", "path": str(saved)},
            log=lambda *_: None,
            engine_root=str(old_root),
            batch_started_at=time.time() - 1,
        )
        self.assertTrue(result.ok, result.error)
        self.assertTrue((assets / "001.png").read_bytes().endswith(b"PATH"))


def _mp4_bytes() -> bytes:
    # Minimal "ftyp" box header — enough for sniff_media_kind() to say "video".
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


class FakeYouTubeBackend:
    """Scripted YouTubeSearchBackend — no network, no yt-dlp import. `candidates`
    is returned by search() (already in the desired rank order); `transcripts`
    maps video_id -> list[TranscriptSegment] or None (no captions)."""

    def __init__(self, candidates, transcripts=None, write_bad_bytes=False, fail_video_ids=None, results_by_query=None):
        self.candidates = candidates
        self.transcripts = transcripts or {}
        self.write_bad_bytes = write_bad_bytes
        self.fail_video_ids = fail_video_ids or set()  # simulate a per-candidate download/403 failure
        self.download_calls = []
        self.search_calls = []
        self.results_by_query = results_by_query

    def search(self, query, max_results=5):
        self.search_calls.append(query)
        if self.results_by_query is not None:
            return list(self.results_by_query.get(query, []))[:max_results]
        return list(self.candidates)[:max_results]

    def get_transcript(self, candidate):
        return self.transcripts.get(candidate.video_id)

    def download_segment(self, candidate, start, duration, dest, log=print):
        self.download_calls.append((candidate.video_id, start, duration))
        if candidate.video_id in self.fail_video_ids:
            raise RuntimeError("YouTube rejected the download (HTTP 403).")
        dest = Path(dest)
        dest.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16 if self.write_bad_bytes else _mp4_bytes())
        return dest


class TestYouTubeQueryExpand(unittest.TestCase):
    def test_cinematic_prompt_gets_short_variants(self):
        from providers.youtube.query import expand_youtube_query

        q = (
            "Real archival footage from the mid-1940s post-war American grocery store, "
            "period-accurate black and white or sepia toned footage."
        )
        variants = expand_youtube_query(q)
        self.assertGreaterEqual(len(variants), 3)
        blob = " | ".join(variants).lower()
        self.assertIn("grocery", blob)
        self.assertTrue(any("grocery store" in v.lower() and len(v.split()) <= 6 for v in variants))


class TestYouTubeAssetType(AssetPipelineTestCase):
    def test_csv_youtube_video_routes_correctly(self):
        scene = SceneRow(
            scene_number="7", script_segment="Steve Jobs introduced the first iPhone to the world",
            asset_type="youtube_video", prompt="Steve Jobs original iPhone launch presentation",
        )
        self.assertTrue(scene.wants_youtube)
        self.assertEqual(SceneAssetRouter.classify(scene), AssetSource.YOUTUBE_VIDEO)

    def test_from_csv_row_keeps_prompt_for_youtube(self):
        row = {
            "scene_number": "7", "script_segment": "seg", "asset_type": "youtube_video",
            "prompt": "steve jobs iphone launch",
        }
        scene = SceneRow.from_csv_row(row)
        self.assertEqual(scene.prompt, "steve jobs iphone launch")
        self.assertEqual(scene.stock, "")


class TestYouTubeRanking(unittest.TestCase):
    def test_rank_prefers_captions_and_landscape(self):
        from providers.youtube.base import VideoCandidate
        from providers.youtube.ranking import rank_candidates

        no_captions = VideoCandidate(video_id="a", url="u", title="A", channel="c", duration=60, has_captions=False)
        with_captions = VideoCandidate(video_id="b", url="u", title="B", channel="c", duration=60, has_captions=True)
        ranked = rank_candidates([no_captions, with_captions])
        self.assertEqual(ranked[0].video_id, "b")

    def test_rank_discards_absurdly_short_clips_when_alternatives_exist(self):
        from providers.youtube.base import VideoCandidate
        from providers.youtube.ranking import rank_candidates

        too_short = VideoCandidate(video_id="a", url="u", title="A", channel="c", duration=1)
        fine = VideoCandidate(video_id="b", url="u", title="B", channel="c", duration=120)
        ranked = rank_candidates([too_short, fine])
        self.assertNotIn(too_short, ranked)


class TestYouTubeTranscriptMatching(unittest.TestCase):
    def test_finds_the_relevant_timestamp_not_zero(self):
        from providers.youtube.base import TranscriptSegment
        from providers.youtube.matching import best_transcript_match

        segments = [
            TranscriptSegment(0.0, 5.0, "Good morning, welcome to the keynote."),
            TranscriptSegment(2530.0, 5.0, "Today we're going to introduce three revolutionary products."),
            TranscriptSegment(2545.0, 5.0, "An iPod, a phone, and an internet communicator."),
            TranscriptSegment(2557.0, 5.0, "These are not three separate devices."),
        ]
        match = best_transcript_match(segments, "Steve Jobs introduced the first iPhone to the world")
        self.assertIsNotNone(match)
        segment, score = match
        self.assertNotEqual(segment.start, 0.0)
        self.assertIn(segment.start, (2530.0, 2545.0))

    def test_no_match_returns_none_not_a_fabricated_result(self):
        from providers.youtube.base import TranscriptSegment
        from providers.youtube.matching import best_transcript_match

        segments = [TranscriptSegment(0.0, 5.0, "completely unrelated cooking tutorial content")]
        match = best_transcript_match(segments, "Steve Jobs introduced the first iPhone to the world")
        self.assertIsNone(match)


class TestYouTubeClipWindow(unittest.TestCase):
    def test_default_duration_is_3_5_seconds_with_1s_lead_in(self):
        from providers.youtube.base import compute_clip_window

        start, duration = compute_clip_window(target_ts=2545.0, video_duration=3000.0)
        self.assertAlmostEqual(start, 2544.0)
        self.assertAlmostEqual(duration, 3.5)

    def test_clamped_to_video_start(self):
        from providers.youtube.base import compute_clip_window

        start, duration = compute_clip_window(target_ts=0.2, video_duration=3000.0)
        self.assertEqual(start, 0.0)

    def test_clamped_to_video_end(self):
        from providers.youtube.base import compute_clip_window

        start, duration = compute_clip_window(target_ts=99.5, video_duration=100.0)
        self.assertLessEqual(start + duration, 100.0)


class TestYouTubeProviderIntegration(AssetPipelineTestCase):
    def _candidate(self, vid="abc123", duration=3000.0, has_captions=True):
        from providers.youtube.base import VideoCandidate
        return VideoCandidate(
            video_id=vid, url=f"https://youtube.com/watch?v={vid}", title="Apple Keynote 2007",
            channel="Apple", duration=duration, has_captions=has_captions,
        )

    def test_transcript_match_produces_canonical_filename_and_manifest(self):
        from providers.youtube.base import TranscriptSegment, YouTubeProvider

        candidate = self._candidate()
        transcript = [
            TranscriptSegment(2530.0, 5.0, "Steve Jobs unveiled the original iPhone here today at Macworld."),
        ]
        backend = FakeYouTubeBackend([candidate], transcripts={candidate.video_id: transcript})
        provider = YouTubeProvider(backend, clip_duration=3.5)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(
            scene_number="7", script_segment="Steve Jobs unveiled the very first iPhone at Macworld",
            asset_type="youtube_video", prompt="Steve Jobs unveils the original iPhone Macworld keynote",
        )
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.path, self.images / "007.mp4")
        self.assertTrue(result.path.is_file())

        record = mgr.manifest.get("7")
        self.assertEqual(record["selection_method"], "transcript_match")
        self.assertEqual(record["local_path"], str(self.images / "007.mp4"))
        self.assertAlmostEqual(record["clip_duration"], 3.5)
        self.assertIn("video_title", record)
        self.assertIn("channel", record)

    def test_no_transcript_falls_back_and_records_fallback_method(self):
        from providers.youtube.base import YouTubeProvider

        candidate = self._candidate(has_captions=False)
        backend = FakeYouTubeBackend([candidate], transcripts={})
        provider = YouTubeProvider(backend, clip_duration=3.5)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(
            scene_number="3", script_segment="anything", asset_type="youtube_video", prompt="some query",
        )
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok, result.error)
        record = mgr.manifest.get("3")
        self.assertEqual(record["selection_method"], "fallback")

    def test_no_search_results_fails_clearly_without_substituting_another_provider(self):
        from providers.youtube.base import YouTubeProvider

        backend = FakeYouTubeBackend([])
        provider = YouTubeProvider(backend)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(scene_number="1", script_segment="x", asset_type="youtube_video", prompt="nonexistent query xyz")
        result = mgr.resolve_scene(scene)
        self.assertFalse(result.ok)
        self.assertEqual(result.source, AssetSource.YOUTUBE_VIDEO)
        self.assertFalse((self.images / "001.mp4").is_file())

    def test_non_video_segment_is_rejected_by_media_validation(self):
        from providers.youtube.base import TranscriptSegment, YouTubeProvider

        candidate = self._candidate()
        transcript = [TranscriptSegment(10.0, 5.0, "some matching narration text here")]
        backend = FakeYouTubeBackend([candidate], transcripts={candidate.video_id: transcript}, write_bad_bytes=True)
        provider = YouTubeProvider(backend)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(
            scene_number="9", script_segment="some matching narration text here",
            asset_type="youtube_video", prompt="some matching narration text here",
        )
        result = mgr.resolve_scene(scene)
        self.assertFalse(result.ok)
        self.assertIn("not a video", result.error.lower())
        self.assertFalse((self.images / "009.mp4").is_file(), "a mismatched file must never be accepted")

    def test_regenerate_excludes_previous_video_id(self):
        from providers.youtube.base import YouTubeProvider

        first = self._candidate(vid="video-1", has_captions=False)
        second = self._candidate(vid="video-2", has_captions=False)
        backend = FakeYouTubeBackend([first, second])
        provider = YouTubeProvider(backend)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(scene_number="1", script_segment="x", asset_type="youtube_video", prompt="query")
        first_result = mgr.resolve_scene(scene)
        self.assertTrue(first_result.ok)
        self.assertEqual(first_result.metadata["video_id"], "video-1")

        second_result = mgr.regenerate_scene(scene)
        self.assertTrue(second_result.ok)
        self.assertEqual(second_result.metadata["video_id"], "video-2")

    def test_stale_image_asset_removed_when_scene_becomes_youtube_video(self):
        from providers.youtube.base import YouTubeProvider

        (self.images / "005.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)
        candidate = self._candidate(has_captions=False)
        backend = FakeYouTubeBackend([candidate])
        provider = YouTubeProvider(backend)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(scene_number="5", script_segment="x", asset_type="youtube_video", prompt="query")
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok)
        self.assertFalse((self.images / "005.jpg").is_file(), "stale image must be removed")
        self.assertTrue((self.images / "005.mp4").is_file())

    def test_candidate_fallback_moves_to_next_candidate_on_extraction_failure(self):
        from providers.youtube.base import YouTubeProvider

        cand1 = self._candidate(vid="fails-1", has_captions=False)
        cand2 = self._candidate(vid="fails-2", has_captions=False)
        cand3 = self._candidate(vid="succeeds-3", has_captions=False)
        backend = FakeYouTubeBackend(
            [cand1, cand2, cand3], fail_video_ids={"fails-1", "fails-2"},
        )
        provider = YouTubeProvider(backend, clip_duration=3.5)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(
            scene_number="3", script_segment="airplane flying through clouds sunset",
            asset_type="youtube_video", prompt="airplane flying through clouds sunset",
        )
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.metadata["video_id"], "succeeds-3")
        self.assertEqual(result.path, self.images / "003.mp4")
        # Candidates 1 and 2 were each tried exactly once (no repeated
        # same-video retries at this layer) before moving on.
        attempted_ids = [c[0] for c in backend.download_calls]
        self.assertEqual(attempted_ids, ["fails-1", "fails-2", "succeeds-3"])
        # Exactly one asset file exists for the scene.
        self.assertEqual(list(self.images.glob("003.*")), [self.images / "003.mp4"])
        self.assertEqual(len(backend.search_calls), 1)

    def test_youtube_query_fallback_skips_zero_results_and_stops_on_hit(self):
        from providers.youtube.base import YouTubeProvider

        hit = self._candidate(vid="ok-2", has_captions=False)
        backend = FakeYouTubeBackend([], results_by_query={
            "falcon 9 rocket standing on launchpad night floodlights static view": [],
            "Falcon 9 rocket launch night": [hit],
            "SpaceX Falcon 9 launch": [self._candidate(vid="should-not-search", has_captions=False)],
            "rocket launch night": [self._candidate(vid="also-not-search", has_captions=False)],
        })
        provider = YouTubeProvider(backend, clip_duration=3.5)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)
        scene = SceneRow(
            scene_number="4",
            script_segment="Falcon 9 rocket standing on the launchpad at night",
            asset_type="youtube_video",
            prompt="falcon 9 rocket standing on launchpad night floodlights static view",
            search_queries=[
                "falcon 9 rocket standing on launchpad night floodlights static view",
                "Falcon 9 rocket launch night",
                "SpaceX Falcon 9 launch",
                "rocket launch night",
            ],
        )
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            backend.search_calls[0],
            "falcon 9 rocket standing on launchpad night floodlights static view",
        )
        self.assertIn("Falcon 9 rocket launch night", backend.search_calls)
        # Declared broader queries must not run once an earlier query/variant hits.
        self.assertNotIn("SpaceX Falcon 9 launch", backend.search_calls)
        self.assertEqual(result.metadata["video_id"], "ok-2")
        self.assertNotEqual((result.metadata or {}).get("youtube_phase"), "search")

    def test_youtube_duplicate_queries_are_not_retried(self):
        from providers.youtube.base import unique_youtube_queries, YouTubeProvider

        scene = SceneRow(
            scene_number="4", script_segment="x", asset_type="youtube_video",
            prompt="Falcon 9 rocket launch night",
            search_queries=[
                "Falcon 9 rocket launch night",
                "falcon 9 rocket launch night",
                "Falcon 9 rocket launch night",
                "SpaceX Falcon 9 launch",
            ],
        )
        self.assertEqual(unique_youtube_queries(scene), [
            "Falcon 9 rocket launch night",
            "SpaceX Falcon 9 launch",
        ])
        backend = FakeYouTubeBackend([], results_by_query={})
        provider = YouTubeProvider(backend)
        logs = []
        result = provider.resolve(scene, self.images, log=logs.append)
        self.assertFalse(result.ok)
        self.assertEqual((result.metadata or {}).get("youtube_phase"), "search")
        # Exact declared queries appear; zero-hit broadening may add shorter variants.
        self.assertEqual(backend.search_calls[0], "Falcon 9 rocket launch night")
        self.assertIn("SpaceX Falcon 9 launch", backend.search_calls)
        # Case-only duplicates of the first query must not be re-tried as a new root.
        self.assertEqual(
            sum(1 for q in backend.search_calls if q.lower() == "falcon 9 rocket launch night"),
            1,
        )

    def test_all_youtube_queries_fail_uses_declared_fallback(self):
        from providers.youtube.base import YouTubeProvider

        backend = FakeYouTubeBackend([])
        youtube = YouTubeProvider(backend)
        flow = FakeProvider(AssetSource.FLOW_VIDEO, {"4": "ok"}, media_type=MediaType.VIDEO)
        mgr = AssetManager(
            self.images, youtube_provider=youtube, flow_video_provider=flow, log=lambda *_: None,
        )
        scene = SceneRow(
            scene_number="4",
            script_segment="Falcon 9 on the pad at night",
            asset_type="youtube_video",
            prompt="Falcon 9 rocket launch night",
            search_queries=["Falcon 9 rocket launch night", "SpaceX Falcon 9 launch", "rocket launch night"],
            fallbacks=["flow_video", "stock_video"],
            visual_description="Falcon 9 vertical on a floodlit pad at night, steam at the base.",
        )
        result = mgr.resolve_scene(scene)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, AssetSource.FLOW_VIDEO)
        self.assertEqual(backend.search_calls[0], "Falcon 9 rocket launch night")
        self.assertIn("SpaceX Falcon 9 launch", backend.search_calls)
        self.assertIn("rocket launch night", backend.search_calls)
        self.assertEqual(flow.calls, ["4"])
        self.assertTrue((self.images / "004.mp4").is_file())

    def test_search_failure_does_not_attempt_browser_acquisition(self):
        from providers.youtube.base import YouTubeProvider

        backend = FakeYouTubeBackend([])
        provider = YouTubeProvider(backend)
        scene = SceneRow(
            scene_number="4", script_segment="x", asset_type="youtube_video",
            prompt="q1", search_queries=["q1", "q2"],
        )
        result = provider.resolve(scene, self.images, log=lambda *_: None)
        self.assertFalse(result.ok)
        self.assertEqual(result.metadata.get("youtube_phase"), "search")
        self.assertEqual(backend.download_calls, [])
        self.assertEqual(backend.search_calls, ["q1", "q2"])

    def test_csv_youtube_prompt_roundtrips_multiple_queries(self):
        from visual_director.schema import parse_visual_plan

        plan = parse_visual_plan({
            "topic": "t",
            "scenes": [
                {
                    "scene_id": 1,
                    "narration": "a",
                    "visual_goal": "g",
                    "visual_description": "d",
                    "provider_preference": "stock_video",
                    "search_queries": ["crowded commuter train early morning"],
                    "duration": 3.0,
                    "fallbacks": ["flow_image"],
                    "visual_treatment": "static",
                    "transition": "cut",
                },
                {
                    "scene_id": 2,
                    "narration": "Falcon 9 on the pad.",
                    "visual_goal": "authentic launch",
                    "visual_description": "Falcon 9 night pad",
                    "provider_preference": "youtube",
                    "search_queries": [
                        "Falcon 9 rocket launch night",
                        "SpaceX Falcon 9 launch",
                        "rocket launch night",
                    ],
                    "duration": 3.0,
                    "fallbacks": ["flow_video", "stock_video"],
                    "visual_treatment": "static",
                    "transition": "cut",
                },
            ],
        })
        row = plan.scenes[1].to_scene_row()
        self.assertEqual(len(row.search_queries), 3)
        dicts = plan.to_csv_dicts()
        self.assertIn(" || ", dicts[1]["prompt"])
        restored = SceneRow.from_csv_row(dicts[1])
        self.assertEqual(restored.search_queries[0], "Falcon 9 rocket launch night")
        self.assertEqual(len(restored.search_queries), 3)

    def test_all_candidates_exhausted_reports_structured_failure(self):
        from providers.youtube.base import YouTubeProvider

        cand1 = self._candidate(vid="fails-1", has_captions=False)
        cand2 = self._candidate(vid="fails-2", has_captions=False)
        backend = FakeYouTubeBackend([cand1, cand2], fail_video_ids={"fails-1", "fails-2"})
        provider = YouTubeProvider(backend)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(scene_number="4", script_segment="x", asset_type="youtube_video", prompt="query")
        result = mgr.resolve_scene(scene)
        self.assertFalse(result.ok)
        self.assertIn("candidates exhausted", result.error.lower())
        self.assertIn("attempted: 2", result.error.lower())
        self.assertFalse((self.images / "004.mp4").is_file())

    def test_ranking_prefers_title_matching_the_prompt(self):
        from providers.youtube.base import VideoCandidate
        from providers.youtube.ranking import rank_candidates

        off_topic = VideoCandidate(video_id="a", url="u", title="Cooking pasta at home", channel="c", duration=60)
        on_topic = VideoCandidate(
            video_id="b", url="u", title="Airplane flying through clouds at sunset", channel="c", duration=60,
        )
        ranked = rank_candidates([off_topic, on_topic], query="airplane flying through clouds sunset")
        self.assertEqual(ranked[0].video_id, "b")

    def test_youtube_provider_not_configured_fails_clearly(self):
        mgr = AssetManager(self.images, youtube_provider=None, log=lambda *_: None)
        scene = SceneRow(scene_number="1", script_segment="x", asset_type="youtube_video", prompt="query")
        result = mgr.resolve_scene(scene)
        self.assertFalse(result.ok)
        self.assertIn("not configured", result.error.lower())

    def test_creative_commons_policy_fails_when_no_licensed_result(self):
        from providers.youtube.base import YouTubeProvider

        candidate = self._candidate()  # license=None by default
        backend = FakeYouTubeBackend([candidate])
        provider = YouTubeProvider(backend, require_creative_commons=True)
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)

        scene = SceneRow(scene_number="1", script_segment="x", asset_type="youtube_video", prompt="query")
        result = mgr.resolve_scene(scene)
        self.assertFalse(result.ok)
        self.assertIn("search exhausted", result.error.lower())
        self.assertIn("creative commons", result.error.lower())


class _FakeStrategy:
    """A no-network AcquisitionStrategy stand-in for testing run_strategy_chain()'s
    orchestration in isolation from yt-dlp/ffmpeg. `outcome` is either a
    (FailureKind) to raise as a StrategyFailed, or "success" / "success_invalid"
    to write real/bad bytes to dest."""

    def __init__(self, name, outcome, write_bytes=None):
        self.name = name
        self.outcome = outcome
        self.write_bytes = write_bytes
        self.calls = 0

    def can_handle(self, candidate):
        return True

    def download_segment(self, candidate, start, duration, dest):
        from providers.youtube.strategies import StrategyFailed

        self.calls += 1
        if self.outcome == "success":
            Path(dest).write_bytes(self.write_bytes or _mp4_bytes())
            return
        if self.outcome == "success_invalid":
            Path(dest).write_bytes(b"not a real video, just html or whatever")
            return
        raise StrategyFailed(self.outcome, f"{self.name} failed", f"{self.name} failed")


class TestYouTubeStrategyClassification(unittest.TestCase):
    def test_classifies_403(self):
        from providers.youtube.strategies import FailureKind, classify_failure

        self.assertEqual(
            classify_failure("ffmpeg exited with code 8", "HTTP error 403 Forbidden\nError opening input"),
            FailureKind.HTTP_403,
        )

    def test_classifies_drm(self):
        from providers.youtube.strategies import FailureKind, classify_failure

        self.assertEqual(classify_failure("This video is DRM protected", ""), FailureKind.DRM)
        self.assertTrue(FailureKind.DRM.is_candidate_fatal)

    def test_classifies_unavailable(self):
        from providers.youtube.strategies import FailureKind, classify_failure

        self.assertEqual(classify_failure("This video is not available", ""), FailureKind.UNAVAILABLE)
        self.assertTrue(FailureKind.UNAVAILABLE.is_candidate_fatal)

    def test_403_and_drm_are_not_candidate_fatal_vs_fatal(self):
        from providers.youtube.strategies import FailureKind

        self.assertFalse(FailureKind.HTTP_403.is_candidate_fatal)
        self.assertFalse(FailureKind.OTHER.is_candidate_fatal)


class TestYouTubeStrategyChain(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dest = self.tmp / "007.mp4"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, strategies):
        from providers.youtube.strategies import run_strategy_chain

        candidate = SimpleNamespace(video_id="v1", title="t", url="u")

        # A trivial stand-in validator (accepts any non-empty file, rejects
        # the deliberately-bad "success_invalid" marker bytes) — keeps these
        # orchestration tests independent of ffmpeg/real media validation,
        # which has its own dedicated tests in TestYouTubeClipValidation.
        def fake_validate(path, expected_duration, log=print):
            data = Path(path).read_bytes()
            if not data or data == b"not a real video, just html or whatever":
                return "fake validator: not real content"
            return None

        return run_strategy_chain(
            strategies, candidate, 10.0, 3.5, self.dest, log=lambda *_: None, validate=fake_validate
        )

    def test_403_moves_to_next_strategy(self):
        from providers.youtube.strategies import FailureKind

        s1 = _FakeStrategy("s1", FailureKind.HTTP_403)
        s2 = _FakeStrategy("s2", "success")
        outcome = self._run([s1, s2])
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.strategy, "s2")
        self.assertEqual(s1.calls, 1)
        self.assertEqual(s2.calls, 1)

    def test_drm_stops_trying_further_strategies_for_this_candidate(self):
        from providers.youtube.strategies import FailureKind

        s1 = _FakeStrategy("s1", FailureKind.DRM)
        s2 = _FakeStrategy("s2", "success")
        outcome = self._run([s1, s2])
        self.assertFalse(outcome.ok)
        self.assertEqual(s1.calls, 1)
        self.assertEqual(s2.calls, 0, "must never try another strategy after DRM")

    def test_unavailable_also_stops_immediately(self):
        from providers.youtube.strategies import FailureKind

        s1 = _FakeStrategy("s1", FailureKind.UNAVAILABLE)
        s2 = _FakeStrategy("s2", "success")
        outcome = self._run([s1, s2])
        self.assertFalse(outcome.ok)
        self.assertEqual(s2.calls, 0)

    def test_successful_strategy_stops_immediately_without_trying_later_ones(self):
        s1 = _FakeStrategy("s1", "success")
        s2 = _FakeStrategy("s2", "success")
        outcome = self._run([s1, s2])
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.strategy, "s1")
        self.assertEqual(s2.calls, 0)

    def test_invalid_output_is_rejected_and_moves_to_next_strategy(self):
        s1 = _FakeStrategy("s1", "success_invalid")
        s2 = _FakeStrategy("s2", "success")
        outcome = self._run([s1, s2])
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.strategy, "s2")
        # Exactly one file remains at dest, and it's s2's real bytes — s1's
        # rejected invalid output was removed, not left behind alongside it.
        self.assertEqual(list(self.tmp.glob("*")), [self.dest])
        self.assertEqual(self.dest.read_bytes(), _mp4_bytes())

    def test_all_strategies_fail_reports_every_attempt(self):
        from providers.youtube.strategies import FailureKind

        s1 = _FakeStrategy("s1", FailureKind.HTTP_403)
        s2 = _FakeStrategy("s2", FailureKind.OTHER)
        outcome = self._run([s1, s2])
        self.assertFalse(outcome.ok)
        self.assertEqual([a.strategy for a in outcome.attempts], ["s1", "s2"])

    def test_can_handle_false_skips_strategy_without_calling_it(self):
        s1 = _FakeStrategy("s1", "success")
        s1.can_handle = lambda candidate: False
        s2 = _FakeStrategy("s2", "success")
        outcome = self._run([s1, s2])
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.strategy, "s2")
        self.assertEqual(s1.calls, 0)


class TestYouTubeClipValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_real_clip_is_accepted(self):
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg not on PATH")
        from providers.youtube.strategies import validate_clip

        path = self.tmp / "clip.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3.5:size=320x240:rate=10",
             "-f", "lavfi", "-i", "sine=frequency=1000:duration=3.5",
             "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
            capture_output=True, timeout=30,
        )
        self.assertIsNone(validate_clip(path, expected_duration=3.5))

    def test_tiny_garbage_file_is_rejected(self):
        from providers.youtube.strategies import validate_clip

        path = self.tmp / "clip.mp4"
        path.write_bytes(b"not a video")
        reason = validate_clip(path, expected_duration=3.5)
        self.assertIsNotNone(reason)

    def test_html_error_body_is_rejected(self):
        from providers.youtube.strategies import validate_clip

        path = self.tmp / "clip.mp4"
        path.write_bytes(b"<html><body>403 Forbidden</body></html>" * 100)
        reason = validate_clip(path, expected_duration=3.5)
        self.assertIsNotNone(reason)

    def test_missing_file_is_rejected(self):
        from providers.youtube.strategies import validate_clip

        reason = validate_clip(self.tmp / "does_not_exist.mp4", expected_duration=3.5)
        self.assertIsNotNone(reason)

    def test_partial_file_is_rejected(self):
        from providers.youtube.strategies import validate_clip

        path = self.tmp / "clip.mp4.part"
        path.write_bytes(_mp4_bytes())
        reason = validate_clip(path, expected_duration=3.5)
        self.assertIsNotNone(reason)


class TestYouTubeResolveAllBatching(AssetPipelineTestCase):
    def test_youtube_scenes_resolved_alongside_other_sources(self):
        from providers.youtube.base import YouTubeProvider

        candidate_a = self._make_candidate("a")
        candidate_b = self._make_candidate("b")
        backend_a = FakeYouTubeBackend([candidate_a])
        # AssetManager only takes one youtube_provider, so route both scenes
        # through one backend serving different candidates per call order.
        backend = FakeYouTubeBackend([candidate_a, candidate_b])
        provider = YouTubeProvider(backend)

        (self.images / "001.png").write_bytes(b"x")  # a LOCAL scene
        rows = [
            SceneRow(scene_number="1", script_segment="local one"),
            SceneRow(scene_number="2", script_segment="yt one", asset_type="youtube_video", prompt="query one"),
        ]
        mgr = AssetManager(self.images, youtube_provider=provider, log=lambda *_: None)
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.ok, summary.failed)
        self.assertEqual(summary.results["1"].source, AssetSource.LOCAL)
        self.assertEqual(summary.results["2"].source, AssetSource.YOUTUBE_VIDEO)
        self.assertEqual(summary.results["2"].path, self.images / "002.mp4")

    def _make_candidate(self, vid):
        from providers.youtube.base import VideoCandidate
        return VideoCandidate(
            video_id=vid, url=f"https://youtube.com/watch?v={vid}", title="T", channel="C",
            duration=60.0, has_captions=False,
        )


_FAKE_BROWSER_WORKER = r"""
import { createInterface } from 'node:readline';
import { existsSync, writeFileSync } from 'node:fs';
console.log(JSON.stringify({ type: 'ready' }));
const rl = createInterface({ input: process.stdin });
for await (const line of rl) {
  if (!line.trim()) continue;
  const job = JSON.parse(line);
  if (job.cmd === 'shutdown') process.exit(0);
  if (job.video_id === 'hang') { await new Promise(() => {}); }
  if (job.video_id === 'slow') { await new Promise((r) => setTimeout(r, 2500)); }
  if (job.video_id === 'crash-once') {
    const marker = process.env.CRASH_MARKER;
    if (marker && !existsSync(marker)) {
      writeFileSync(marker, 'x');
      process.exit(2);
    }
  }
  if (job.video_id === 'fail') {
    console.log(JSON.stringify({ id: job.id, ok: false, kind: 'unavailable', error: 'video unavailable' }));
    continue;
  }
  writeFileSync(job.out, 'clip-bytes');
  console.log(JSON.stringify({ id: job.id, ok: true, duration: 3.4, bytes: 10, out: job.out }));
}
"""


class TestBrowserPlaybackClient(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.worker = self.tmp / "fake_worker.mjs"
        self.worker.write_text(_FAKE_BROWSER_WORKER, encoding="utf-8")
        self.dest = self.tmp / "out.mp4"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self, **kwargs):
        from providers.youtube.acquisition.browser_client import BrowserPlaybackClient

        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH")
        return BrowserPlaybackClient(
            node_bin=node, worker_script=self.worker, ready_timeout=5, **kwargs
        )

    def test_persistent_worker_handles_two_jobs(self):
        client = self._client(job_timeout=8)
        try:
            a = self.tmp / "a.mp4"
            b = self.tmp / "b.mp4"
            r1 = client.acquire("vid-a", 0, 3.5, a)
            pid = client._proc.pid
            r2 = client.acquire("vid-b", 0, 3.5, b)
            self.assertTrue(r1.get("ok") and r2.get("ok"), (r1, r2))
            self.assertEqual(client._proc.pid, pid)
            self.assertEqual(client.jobs_completed, 2)
        finally:
            client.stop()

    def test_successful_response_parsing(self):
        client = self._client(job_timeout=8)
        try:
            result = client.acquire("okvid", 10.0, 3.5, self.dest)
        finally:
            client.stop()
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("duration"), 3.4)
        self.assertTrue(self.dest.is_file())
        self.assertEqual(client.jobs_completed, 1)

    def test_error_mapping_unavailable(self):
        from providers.youtube.strategies import FailureKind, map_browser_kind

        client = self._client(job_timeout=8)
        try:
            result = client.acquire("fail", 1.0, 3.5, self.dest)
        finally:
            client.stop()
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("kind"), "unavailable")
        self.assertEqual(map_browser_kind("unavailable"), FailureKind.UNAVAILABLE)
        self.assertEqual(map_browser_kind("bot_blocked"), FailureKind.BOT_BLOCKED)
        self.assertEqual(map_browser_kind("capture_failed"), FailureKind.CAPTURE_FAILED)
        self.assertEqual(map_browser_kind("timeout"), FailureKind.TIMEOUT)

    def test_timeout(self):
        client = self._client(job_timeout=1.2)
        try:
            result = client.acquire("hang", 1.0, 3.5, self.dest)
        finally:
            client.stop()
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("kind"), "timeout")

    def test_delayed_success_is_not_lost_by_poll_timeouts(self):
        client = self._client(job_timeout=8)
        try:
            result = client.acquire("slow", 1.0, 3.5, self.dest)
        finally:
            client.stop()
        self.assertTrue(result.get("ok"), result)

    def test_worker_restart_after_crash(self):
        marker = self.tmp / "crash-marker"
        os.environ["CRASH_MARKER"] = str(marker)
        client = self._client(job_timeout=8)
        try:
            result = client.acquire("crash-once", 1.0, 3.5, self.dest)
            self.assertTrue(result.get("ok"), result)
            self.assertEqual(client.jobs_completed, 1)
        finally:
            client.stop()
            os.environ.pop("CRASH_MARKER", None)

    def test_browser_unavailable(self):
        from providers.youtube.acquisition import browser_client as bc

        original = bc._find_node
        bc._find_node = lambda: None
        try:
            self.assertFalse(bc.browser_available())
        finally:
            bc._find_node = original

    def test_build_chain_is_browser_only_when_available(self):
        from providers.youtube import strategies as st

        original = st.BrowserPlaybackStrategy.can_handle
        st.BrowserPlaybackStrategy.can_handle = lambda self, candidate: True
        try:
            chain = st.build_strategy_chain("best")
            self.assertEqual([s.name for s in chain], ["browser_playback"])
        finally:
            st.BrowserPlaybackStrategy.can_handle = original

    def test_build_chain_legacy_when_browser_unavailable(self):
        from providers.youtube import strategies as st

        original = st.BrowserPlaybackStrategy.can_handle
        st.BrowserPlaybackStrategy.can_handle = lambda self, candidate: False
        try:
            chain = st.build_strategy_chain("best")
            self.assertGreaterEqual(len(chain), 2)
            self.assertNotEqual(chain[0].name, "browser_playback")
        finally:
            st.BrowserPlaybackStrategy.can_handle = original


class TestBrowserStrategyNoYtDlpFallthrough(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.dest = self.tmp / "007.mp4"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_capture_failure_does_not_run_legacy_strategy(self):
        from providers.youtube.strategies import FailureKind, run_strategy_chain

        s1 = _FakeStrategy("browser_playback", FailureKind.CAPTURE_FAILED)
        s2 = _FakeStrategy("dash_default", "success")
        candidate = SimpleNamespace(video_id="v1", title="t", url="u")

        def fake_validate(path, expected_duration, log=print):
            return None

        outcome = run_strategy_chain(
            [s1, s2], candidate, 10.0, 3.5, self.dest, log=lambda *_: None, validate=fake_validate
        )
        self.assertFalse(outcome.ok)
        self.assertEqual(s1.calls, 1)
        self.assertEqual(s2.calls, 0)


class TestYtDlpSearchDoesNotProbe(unittest.TestCase):
    def test_search_uses_flat_listing_only(self):
        from providers.youtube.ytdlp_backend import YtDlpBackend

        backend = object.__new__(YtDlpBackend)
        backend.format_selector = "best"
        backend._last_strategy = None
        calls = {"extract": 0, "probe": 0}
        extracted_urls = []

        class YDL:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, url, download=False):
                calls["extract"] += 1
                extracted_urls.append(url)
                return {
                    "entries": [
                        {"id": "aaa", "title": "Night wet roads", "duration": 120, "channel": "C"},
                        {"id": "bbb", "title": "Hour loop rain", "duration": 3600, "channel": "C"},
                    ]
                }

        backend._ydl = lambda extra=None: YDL()

        def boom(*_a, **_k):
            calls["probe"] += 1
            raise AssertionError("watch-page probe must not run during search")

        backend._probe = boom
        found = backend.search("city traffic at night wet roads", max_results=5)
        self.assertEqual(calls["extract"], 1)
        self.assertEqual(calls["probe"], 0)
        self.assertTrue(extracted_urls[0].startswith("ytsearch5:"))
        self.assertEqual([c.video_id for c in found], ["aaa", "bbb"])
        self.assertEqual(found[0].duration, 120.0)
        self.assertEqual(found[1].duration, 3600.0)
        self.assertFalse(found[0].has_captions)


class FlakyProvider(FakeProvider):
    """Fails a scene's first N calls, then succeeds — for testing retry-once."""

    def __init__(self, source, fail_first, media_type=MediaType.IMAGE):
        super().__init__(source, {}, media_type=media_type)
        self.fail_first = dict(fail_first)  # scene_number -> failures remaining

    def resolve(self, scene, images_dir, log=print):
        remaining = self.fail_first.get(scene.scene_number, 0)
        if remaining > 0:
            self.fail_first[scene.scene_number] = remaining - 1
            self.calls.append(scene.scene_number)
            return AssetResult(
                scene.scene_number, None, None, self.source, SceneStatus.FAILED,
                error=f"scripted transient failure for scene {scene.scene_number}",
            )
        return super().resolve(scene, images_dir, log=log)


class TestFlowImageStockFallback(AssetPipelineTestCase):
    """A genuine Flow image failure must stop at NEEDS_ACTION with its source
    left as flow_image — never silently switched to stock. The operator
    reviews it and manually changes source via the UI if they want to. Both
    the single-scene path (_resolve_one) and the batched path (resolve_all /
    _resolve_flow_batch) must behave identically."""

    def _rows(self, n=3):
        return [
            SceneRow(scene_number=str(i), script_segment=f"scene {i}",
                     asset_type="image", prompt=f"prompt {i}",
                     fallbacks=["stock_image"])
            for i in range(1, n + 1)
        ]

    def test_batch_flow_image_recovers_on_single_retry(self):
        flow = FlakyProvider(AssetSource.FLOW_IMAGE, {"2": 1})
        mgr = AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows())

        self.assertTrue(summary.results["2"].ok, "one retry must recover the scene")
        self.assertEqual(summary.results["2"].source, AssetSource.FLOW_IMAGE)
        self.assertEqual(flow.calls.count("2"), 2, "exactly one retry, no more")

    def test_batch_flow_image_still_failing_after_retry_is_needs_action(self):
        flow = FlakyProvider(AssetSource.FLOW_IMAGE, {"2": 99})
        mgr = AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows())

        self.assertFalse(summary.results["2"].ok)
        self.assertEqual(summary.results["2"].status, SceneStatus.NEEDS_ACTION)
        self.assertEqual(summary.results["2"].source, AssetSource.FLOW_IMAGE)
        self.assertEqual(flow.calls.count("2"), 2, "exactly one retry, then give up")

    def test_single_scene_flow_image_recovers_on_single_retry(self):
        flow = FlakyProvider(AssetSource.FLOW_IMAGE, {"1": 1})
        mgr = AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None)
        result = mgr._resolve_one(self._rows(1)[0], AssetSource.FLOW_IMAGE)
        self.assertTrue(result.ok)
        self.assertEqual(flow.calls.count("1"), 2)

    def test_batch_flow_image_failure_needs_action_not_stock(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"2": "fail"})
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        mgr = AssetManager(self.images, stock_provider=stock,
                           flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows())

        self.assertFalse(summary.results["2"].ok)
        self.assertEqual(summary.results["2"].source, AssetSource.FLOW_IMAGE)
        self.assertEqual(summary.results["2"].status, SceneStatus.NEEDS_ACTION)
        self.assertEqual(stock.calls, [], "a Flow image failure must not auto-query stock")

    def test_successful_flow_images_are_untouched(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"2": "fail"})
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        mgr = AssetManager(self.images, stock_provider=stock,
                           flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows())

        for key in ("1", "3"):
            self.assertEqual(summary.results[key].source, AssetSource.FLOW_IMAGE)
            self.assertTrue(summary.results[key].ok)
        self.assertEqual(stock.calls, [], "stock must never be queried automatically")

    def test_all_flow_images_succeed_means_no_stock_calls(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        mgr = AssetManager(self.images, stock_provider=stock,
                           flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows())
        self.assertEqual(stock.calls, [])
        for key in ("1", "2", "3"):
            self.assertEqual(summary.results[key].source, AssetSource.FLOW_IMAGE)

    def test_single_scene_flow_image_failure_needs_action_not_stock(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"1": "fail"})
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        mgr = AssetManager(self.images, stock_provider=stock,
                           flow_image_provider=flow, log=lambda *_: None)
        scene = self._rows(1)[0]
        result = mgr._resolve_one(scene, AssetSource.FLOW_IMAGE)
        self.assertFalse(result.ok)
        self.assertEqual(result.source, AssetSource.FLOW_IMAGE)
        self.assertEqual(result.status, SceneStatus.NEEDS_ACTION)
        self.assertEqual(stock.calls, [])

    def test_both_paths_agree(self):
        """Batch and single-scene must not differ in how they handle a Flow failure."""
        flow_a = FakeProvider(AssetSource.FLOW_IMAGE, {"1": "fail"})
        stock_a = FakeProvider(AssetSource.STOCK_IMAGE, {})
        single = AssetManager(self.images, stock_provider=stock_a,
                              flow_image_provider=flow_a, log=lambda *_: None
                              )._resolve_one(self._rows(1)[0], AssetSource.FLOW_IMAGE)

        images_b = self.tmp / "ImagesB"
        images_b.mkdir()
        flow_b = FakeProvider(AssetSource.FLOW_IMAGE, {"1": "fail"})
        stock_b = FakeProvider(AssetSource.STOCK_IMAGE, {})
        batch = AssetManager(images_b, stock_provider=stock_b,
                             flow_image_provider=flow_b, log=lambda *_: None
                             ).resolve_all(self._rows(1)).results["1"]

        self.assertEqual(single.source, batch.source)
        self.assertEqual(single.ok, batch.ok)
        self.assertEqual(single.status, batch.status)

    def test_flow_video_does_not_fall_back_to_stock_image(self):
        """Flow VIDEO keeps its existing behaviour — no stock_image fallback."""
        video = FakeProvider(AssetSource.FLOW_VIDEO, {"1": "fail"}, media_type=MediaType.VIDEO)
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {})
        rows = [SceneRow(scene_number="1", script_segment="s", asset_type="video",
                         prompt="p", fallbacks=["stock_image"])]
        mgr = AssetManager(self.images, stock_provider=stock,
                           flow_video_provider=video, log=lambda *_: None)
        summary = mgr.resolve_all(rows)
        self.assertFalse(summary.results["1"].ok)
        self.assertEqual(stock.calls, [], "Flow video must not fall back to stock_image")

    def test_no_stock_provider_leaves_flow_failure_untouched(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"1": "fail"})
        mgr = AssetManager(self.images, flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows(1))
        self.assertFalse(summary.results["1"].ok)

    def test_flow_failure_keeps_original_error_and_never_touches_stock(self):
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"1": "fail"})
        stock = FakeProvider(AssetSource.STOCK_IMAGE, {"1": "fail"})
        mgr = AssetManager(self.images, stock_provider=stock,
                           flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(self._rows(1))
        self.assertFalse(summary.results["1"].ok)
        self.assertIn("scripted failure", (summary.results["1"].error or ""))
        self.assertEqual(stock.calls, [])

    def test_stock_video_routing_unchanged(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {}, media_type=MediaType.VIDEO)
        rows = [SceneRow(scene_number="1", script_segment="s",
                         asset_type="stock_video", stock="a wide shot")]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.results["1"].ok)
        self.assertEqual(summary.results["1"].source, AssetSource.STOCK_VIDEO)

    def test_research_routing_unchanged(self):
        self.assertEqual(
            SceneAssetRouter.classify(
                SceneRow(scene_number="1", script_segment="s",
                         asset_type="research", prompt="q")
            ),
            AssetSource.RESEARCH,
        )


class TestOneSceneStopDoesNotCancelBatch(AssetPipelineTestCase):
    """Regression: one Flow scene being stopped/failing must not mass-cancel
    hundreds of unrelated scenes. Production log showed 254 of 369 scenes
    written off as CANCELLED after a single rejected prompt."""

    def test_should_stop_is_run_level_not_batch_wide(self):
        """AssetManager._run_cancelled must answer 'did the USER stop the run',
        not 'was any single scene stopped'. Feeding the batch-wide form into
        the provider made every in-flight scene look user-cancelled."""
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {})
        mgr = self._manager(flow=flow)
        mgr.request_cancel_scene("3")

        self.assertTrue(mgr.is_scene_cancelled("3"))
        self.assertFalse(
            mgr._run_cancelled(),
            "one cancelled scene must NOT read as a whole-run cancellation",
        )

        mgr.request_cancel()
        self.assertTrue(mgr._run_cancelled(), "a real user cancel must still stop the batch")

    def test_sibling_interruption_is_failed_not_cancelled(self):
        """The provider already distinguishes 'user cancelled' from 'caught in
        the STOP sent for a sibling scene'; it only reached the CANCELLED
        branch because should_stop() was batch-wide."""
        from unittest.mock import MagicMock

        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client
            def ensure_running(self):
                return self.client

        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": str(self.images)}

        captured = {}

        def fake_subscribe(fn):
            captured["fn"] = fn
            return lambda: None

        def fake_stop():
            captured["fn"]({"type": "GENERATE_DONE"})

        client.subscribe.side_effect = fake_subscribe
        client.stop.side_effect = fake_stop

        fp = FlowProvider(FakeEngineManager(client))
        scenes = [
            SceneRow(scene_number=str(i), script_segment=f"s{i}", prompt=f"p{i}")
            for i in range(1, 5)
        ]
        # Scene 2 alone is stopped; the run itself was never cancelled.
        fp.should_stop_scene = lambda n: str(n) == "2"
        results = fp.resolve_batch(
            scenes, self.images, log=lambda *_: None, should_stop=lambda: False
        )

        client.stop.assert_called_once()   # per-scene stop still reaches the engine
        for number in ("1", "3", "4"):
            self.assertNotEqual(
                results[number].status, SceneStatus.CANCELLED,
                f"scene {number} was never stopped — it must not be CANCELLED",
            )
            self.assertEqual(results[number].status, SceneStatus.FAILED)
            self.assertIn("Retry", results[number].error or "")

    def test_real_user_cancel_still_cancels_outstanding_scenes(self):
        from unittest.mock import MagicMock

        from providers.flow.provider import FlowProvider

        class FakeEngineManager:
            def __init__(self, client):
                self.client = client
            def ensure_running(self):
                return self.client

        client = MagicMock()
        client.get_state.return_value = {"running": False}
        client.get_info.return_value = {"downloadsRoot": str(self.images)}
        captured = {}
        client.subscribe.side_effect = lambda fn: (captured.__setitem__("fn", fn), lambda: None)[1]
        client.stop.side_effect = lambda: captured["fn"]({"type": "GENERATE_DONE"})

        fp = FlowProvider(FakeEngineManager(client))
        scenes = [SceneRow(scene_number=str(i), script_segment=f"s{i}", prompt=f"p{i}")
                  for i in range(1, 4)]
        results = fp.resolve_batch(
            scenes, self.images, log=lambda *_: None, should_stop=lambda: True
        )
        for number in ("1", "2", "3"):
            self.assertEqual(results[number].status, SceneStatus.CANCELLED)

    def test_retry_only_targets_unresolved_scenes(self):
        """READY scenes must be left untouched by a retry pass."""
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"2": "fail"})
        rows = [SceneRow(scene_number=str(i), script_segment=f"s{i}",
                         asset_type="image", prompt=f"p{i}") for i in range(1, 4)]
        mgr = self._manager(flow=flow)
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.results["1"].ok)
        self.assertFalse(summary.results["2"].ok)

        flow.scripted = {}
        flow.calls = []
        unresolved = [r for r in rows if not summary.results[r.scene_number].ok]
        mgr.retry_flow_batch(unresolved)
        self.assertEqual(flow.calls, ["2"], "only the unresolved scene may be regenerated")


if __name__ == "__main__":
    unittest.main()
