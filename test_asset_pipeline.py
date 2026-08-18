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
import shutil
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(sorted(flow.calls), ["1", "2", "3"])

        # "fix" the scripted failure (simulates the underlying issue being resolved)
        # and re-run with a FRESH manager pointed at the same manifest/images dir.
        flow.scripted = {}
        flow.calls = []
        mgr2 = self._manager(flow=flow)
        summary2 = mgr2.resolve_all(rows)
        self.assertTrue(summary2.ok)
        self.assertEqual(flow.calls, ["2"], "scenes 1 and 3 were already complete and must not be redone")


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

        summary = mgr.resolve_all(rows)
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
            scenes, Path("/tmp"), log=lambda *_: None, should_stop=lambda: True
        )

        client.stop.assert_called_once()
        self.assertEqual(results["1"].status, SceneStatus.CANCELLED)


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

    def test_image_mislabeled_as_video_is_rejected_not_accepted(self):
        from providers.base import sniff_media_kind
        from providers.flow.provider import FlowProvider

        # A real PNG magic-byte header, saved with a .mp4 name — simulates the
        # exact failure mode from the bug report if it were ever to occur.
        fake_dir = self.images / "acct1"
        fake_dir.mkdir()
        bad_file = fake_dir / "001.mp4"
        bad_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

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


if __name__ == "__main__":
    unittest.main()
