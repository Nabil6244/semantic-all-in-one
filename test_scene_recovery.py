#!/usr/bin/env python3
"""Per-scene recovery: one failure must not block other scenes or wipe their assets."""

from __future__ import annotations

import unittest
from pathlib import Path

from asset_manager import AssetManager
from providers.base import AssetSource, MediaType, SceneRow, SceneStatus
from scene_recovery import SceneRecoveryTracker, allow_final_render, scene_key, summarize_assets
from test_asset_pipeline import AssetPipelineTestCase, FakeProvider, FakeYouTubeBackend


class TestContinueOnFailure(AssetPipelineTestCase):
    def test_one_scene_fails_others_continue(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"1": "ok", "2": "fail", "3": "ok"}, media_type=MediaType.VIDEO)
        rows = [
            SceneRow(scene_number="1", script_segment="a", asset_type="stock_video", stock="q1"),
            SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2"),
            SceneRow(scene_number="3", script_segment="c", asset_type="stock_video", stock="q3"),
        ]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        summary = mgr.resolve_all(rows)
        self.assertTrue(summary.results["1"].ok)
        self.assertTrue(summary.results["3"].ok)
        self.assertFalse(summary.results["2"].ok)
        self.assertEqual(summary.results["2"].status, SceneStatus.NEEDS_ACTION)
        self.assertTrue((self.images / "001.mp4").is_file())
        self.assertTrue((self.images / "003.mp4").is_file())
        self.assertFalse((self.images / "002.mp4").is_file())

    def test_successful_assets_untouched_after_failed_retry(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"1": "ok", "2": "fail"}, media_type=MediaType.VIDEO)
        rows = [
            SceneRow(scene_number="1", script_segment="a", asset_type="stock_video", stock="q1"),
            SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2"),
        ]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        mgr.resolve_all(rows)
        before = (self.images / "001.mp4").read_bytes()
        mgr.retry_scene(rows[1])
        self.assertEqual((self.images / "001.mp4").read_bytes(), before)
        self.assertTrue((self.images / "001.mp4").is_file())

    def test_retry_only_calls_that_scene(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"1": "ok", "2": "fail"}, media_type=MediaType.VIDEO)
        rows = [
            SceneRow(scene_number="1", script_segment="a", asset_type="stock_video", stock="q1"),
            SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2"),
        ]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        mgr.resolve_all(rows)
        stock.calls.clear()
        mgr.retry_scene(rows[1])
        self.assertEqual(stock.calls, ["2"])

    def test_failed_scene_can_be_regenerated_successfully(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"2": "fail"}, media_type=MediaType.VIDEO)
        scene = SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2")
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        first = mgr.resolve_all([scene])
        self.assertFalse(first.results["2"].ok)
        stock.scripted["2"] = "ok"
        second = mgr.retry_scene(scene)
        self.assertTrue(second.ok)
        self.assertTrue((self.images / "002.mp4").is_file())


class TestAlternativeDoesNotRepeatQuery(AssetPipelineTestCase):
    def test_alternative_skips_failed_youtube_query(self):
        from providers.youtube.base import YouTubeProvider, VideoCandidate

        cand = VideoCandidate(
            video_id="ok", url="https://youtube.com/watch?v=ok", title="Falcon 9",
            channel="c", duration=60, has_captions=False,
        )
        backend = FakeYouTubeBackend([], results_by_query={
            "Falcon 9 rocket launch night": [],
            "SpaceX Falcon 9 launch": [cand],
        })
        youtube = YouTubeProvider(backend, clip_duration=3.5)
        scene = SceneRow(
            scene_number="4",
            script_segment="Falcon 9",
            asset_type="youtube_video",
            prompt="Falcon 9 rocket launch night",
            search_queries=["Falcon 9 rocket launch night", "SpaceX Falcon 9 launch"],
            fallbacks=["flow_video"],
        )
        mgr = AssetManager(self.images, youtube_provider=youtube, log=lambda *_: None)
        mgr.recovery.mark_query("4", "Falcon 9 rocket launch night")
        result = mgr.alternative_scene(scene)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(backend.search_calls, ["SpaceX Falcon 9 launch"])
        self.assertNotIn("Falcon 9 rocket launch night", backend.search_calls)

    def test_all_queries_failed_uses_declared_fallback(self):
        from providers.youtube.base import YouTubeProvider

        backend = FakeYouTubeBackend([])
        youtube = YouTubeProvider(backend)
        flow = FakeProvider(AssetSource.FLOW_VIDEO, {"4": "ok"}, media_type=MediaType.VIDEO)
        scene = SceneRow(
            scene_number="4", script_segment="x", asset_type="youtube_video",
            prompt="q1", search_queries=["q1", "q2"], fallbacks=["flow_video"],
            visual_description="cinematic falcon 9",
        )
        mgr = AssetManager(
            self.images, youtube_provider=youtube, flow_video_provider=flow, log=lambda *_: None,
        )
        mgr.recovery.mark_query("4", "q1")
        mgr.recovery.mark_query("4", "q2")
        mgr.recovery.mark_provider("4", "youtube")
        result = mgr.alternative_scene(scene)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.FLOW_VIDEO)
        self.assertEqual(flow.calls, ["4"])
        self.assertEqual(backend.search_calls, [])

    def test_cancel_one_scene_does_not_cancel_others(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"1": "ok", "2": "ok"}, media_type=MediaType.VIDEO)
        rows = [
            SceneRow(scene_number="1", script_segment="a", asset_type="stock_video", stock="q1"),
            SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2"),
        ]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        mgr.request_cancel_scene("2")
        summary = mgr.resolve_all(rows)
        # resolve_all reset_cancel() clears per-scene cancels at start — cancel during a run:
        mgr.reset_cancel()
        mgr.resolve_all(rows)
        mgr.request_cancel_scene("2")
        self.assertTrue(mgr.is_scene_cancelled("2"))
        self.assertFalse(mgr.is_scene_cancelled("1"))
        cancelled = mgr._cancelled_result(rows[1], AssetSource.STOCK_VIDEO)
        self.assertEqual(cancelled.status, SceneStatus.CANCELLED)
        self.assertTrue((self.images / "001.mp4").is_file())

    def test_skip_does_not_remove_other_assets(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"1": "ok", "2": "fail"}, media_type=MediaType.VIDEO)
        rows = [
            SceneRow(scene_number="1", script_segment="a", asset_type="stock_video", stock="q1"),
            SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2"),
        ]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        mgr.resolve_all(rows)
        skipped = mgr.skip_scene(rows[1])
        self.assertEqual(skipped.status, SceneStatus.SKIPPED)
        self.assertTrue((self.images / "001.mp4").is_file())
        self.assertTrue((self.images / "002.png").is_file())

    def test_retry_after_skip_generates_flow_image(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"2": "fail"}, media_type=MediaType.VIDEO)
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"2": "ok"}, media_type=MediaType.IMAGE)
        scene = SceneRow(
            scene_number="2", script_segment="haze secrets",
            asset_type="stock_video", stock="vast empty dark starfield",
        )
        mgr = AssetManager(
            self.images, stock_provider=stock, flow_image_provider=flow, log=lambda *_: None,
        )
        mgr.skip_scene(scene)
        result = mgr.retry_scene(scene)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, AssetSource.FLOW_IMAGE)
        self.assertEqual(flow.calls, ["2"])
        self.assertTrue((self.images / "002.jpg").is_file())
        self.assertFalse((self.images / "002.png").is_file())
        self.assertNotIn(scene_key("2"), mgr.recovery.skipped)

    def test_stock_fallback_to_flow_image_uses_stock_query(self):
        scene = SceneRow(
            scene_number="42", script_segment="hidden",
            asset_type="stock_video", stock="vast empty dark starfield",
        )
        alt = scene.as_fallback("flow_image")
        self.assertEqual(alt.asset_type, "image")
        self.assertEqual(alt.prompt, "vast empty dark starfield")

    def test_youtube_fallback_to_flow_image_uses_search_prompt(self):
        scene = SceneRow(
            scene_number="6", script_segment="telescope",
            asset_type="youtube_video", prompt="James Webb Space Telescope real footage",
        )
        alt = scene.as_fallback("flow_image")
        self.assertEqual(alt.asset_type, "image")
        self.assertEqual(alt.prompt, "James Webb Space Telescope real footage")

    def test_generate_reuses_flow_image_after_source_change(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"2": "fail"}, media_type=MediaType.VIDEO)
        flow = FakeProvider(AssetSource.FLOW_IMAGE, {"2": "ok"}, media_type=MediaType.IMAGE)
        scene = SceneRow(
            scene_number="2", script_segment="n",
            asset_type="stock_video", stock="starfield",
        )
        mgr = AssetManager(
            self.images, stock_provider=stock, flow_image_provider=flow, log=lambda *_: None,
        )
        first = mgr.change_source(scene, "flow_image")
        self.assertTrue(first.ok)
        stock.calls.clear()
        flow.calls.clear()
        summary = mgr.resolve_all([scene])
        self.assertTrue(summary.results["2"].ok)
        self.assertEqual(summary.results["2"].source, AssetSource.FLOW_IMAGE)
        self.assertEqual(stock.calls, [])
        self.assertEqual(flow.calls, [])

    def test_final_render_blocked_until_resolved_or_skipped(self):
        r1 = type("R", (), {"ok": True, "status": SceneStatus.READY})()
        r2 = type("R", (), {"ok": False, "status": SceneStatus.NEEDS_ACTION})()
        results = {"001": r1, "002": r2}
        self.assertFalse(allow_final_render(["1", "2"], results, set()))
        self.assertTrue(allow_final_render(["1", "2"], results, {"002"}))
        stats = summarize_assets(["1", "2"], results, set())
        self.assertEqual(stats["needs_attention"], 1)
        self.assertFalse(stats["allow_render"])

    def test_tracker_does_not_repeat_query(self):
        tracker = SceneRecoveryTracker()
        scene = SceneRow(
            scene_number="4", script_segment="x", asset_type="youtube_video",
            prompt="q1", search_queries=["q1", "q2", "q1"],
        )
        tracker.mark_query("4", "q1")
        remaining = tracker.remaining_youtube_queries(scene)
        self.assertEqual(remaining, ["q2"])
        nxt = tracker.next_alternative(scene)
        self.assertEqual(nxt["kind"], "youtube_query")
        self.assertEqual(nxt["query"], "q2")


class TestManualCsvUnchanged(unittest.TestCase):
    def test_csv_youtube_prompt_still_single_column(self):
        row = SceneRow.from_csv_row({
            "scene_number": "1", "script_segment": "hi",
            "asset_type": "youtube_video", "prompt": "simple query",
        })
        self.assertEqual(row.prompt, "simple query")
        self.assertEqual(row.asset_type, "youtube_video")


if __name__ == "__main__":
    unittest.main()
