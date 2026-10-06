#!/usr/bin/env python3
"""Retry keeps the source chosen with Change Source, and Visual QA reads the saved coverage plans again.

Before: Retry (retry_scene -> regenerate_scene) routed by the CSV row's original asset_type, so a stock row changed to Flow
image went back to stock after a failed Flow attempt; bulk Retry did the same in the app's Flow check, and the Flow retry
batch turned a Flow video choice into a Flow image. Visual QA built CoverageSegment with a field renamed in August
(asset_type -> asset_class), so every scene with a coverage plan skipped QA with a TypeError.

No network, no Flow engine: fake providers record what they were asked to do.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from asset_manager import AssetManager
from providers.base import AssetProvider, AssetResult, AssetSource, MediaType, SceneRow, SceneStatus


class _Recorder(AssetProvider):
    """Fails or succeeds as told, and remembers every call."""

    def __init__(self, source: AssetSource, ok: bool = True):
        self.source, self.ok, self.calls = source, ok, []

    def _result(self, scene, images_dir, how):
        self.calls.append((how, scene.scene_number, scene.asset_type))
        if not self.ok:
            return AssetResult(scene.scene_number, None, None, self.source, SceneStatus.FAILED, error="No mediaId in generation response")
        p = Path(images_dir) / f"{int(scene.scene_number):03d}.png"
        p.write_bytes(b"x")
        return AssetResult(scene.scene_number, p, MediaType.IMAGE, self.source, SceneStatus.READY,
                           metadata={"provider_asset_id": f"{self.source.value}-{len(self.calls)}"})

    def resolve(self, scene, images_dir, log=print):
        return self._result(scene, images_dir, "resolve")

    def regenerate(self, scene, images_dir, exclude=None, log=print):
        return self._result(scene, images_dir, "regenerate")


class TestRetryKeepsChangeSource(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "assets"
        self.images.mkdir()
        self.stock = _Recorder(AssetSource.STOCK_VIDEO)
        self.youtube = _Recorder(AssetSource.YOUTUBE_VIDEO)
        self.flow_image = _Recorder(AssetSource.FLOW_IMAGE, ok=False)
        self.flow_video = _Recorder(AssetSource.FLOW_VIDEO, ok=False)
        self.mgr = AssetManager(self.images, stock_provider=self.stock, flow_image_provider=self.flow_image,
                                flow_video_provider=self.flow_video, youtube_provider=self.youtube, log=lambda *_: None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _row(self, asset_type="stock_video"):
        prompt = "man looking up at sky in surprise shock"
        if asset_type.startswith("stock"):
            return SceneRow(scene_number="2", script_segment="He looked up.", asset_type=asset_type, stock=prompt)
        return SceneRow(scene_number="2", script_segment="He looked up.", asset_type=asset_type, prompt=prompt)

    def test_stock_changed_to_flow_image_retries_as_flow_image(self):
        row = self._row("stock_video")
        self.assertFalse(self.mgr.change_source(row, "flow_image").ok)
        before = len(self.stock.calls)
        self.mgr.retry_scene(row)  # the CSV row, as the app passes it
        self.assertEqual(self.flow_image.calls[-1][0], "regenerate")
        self.assertEqual(len(self.stock.calls), before, "Retry must not fall back to the CSV's stock source")

    def test_stock_changed_to_flow_video_retries_as_flow_video(self):
        row = self._row("stock_video")
        self.mgr.change_source(row, "flow_video")
        self.mgr.retry_scene(row)
        self.assertEqual(self.flow_video.calls[-1][0], "regenerate")
        self.assertEqual(self.flow_image.calls, [])

    def test_youtube_changed_to_flow_image_retries_as_flow_image(self):
        row = self._row("youtube_video")
        self.mgr.change_source(row, "flow_image")
        self.mgr.retry_scene(row)
        self.assertEqual(self.flow_image.calls[-1][0], "regenerate")
        self.assertEqual([c for c in self.youtube.calls if c[0] == "regenerate"], [])

    def test_no_override_retries_the_original_source(self):
        row = self._row("stock_video")
        self.mgr.retry_scene(row)
        self.assertEqual(self.stock.calls[-1][0], "regenerate")
        self.assertEqual(self.flow_image.calls, [])

    def test_flow_retry_batch_keeps_a_flow_video_choice(self):
        row = self._row("stock_video")
        self.mgr.change_source(row, "flow_video")
        seen = []
        self.mgr._resolve_flow_batch = lambda source, provider, group, results, **kw: seen.append((source, [s.asset_type for s in group]))
        self.mgr.retry_flow_batch([row])
        self.assertEqual([s for s, _ in seen], [AssetSource.FLOW_VIDEO])

    def test_app_bulk_retry_sends_an_overridden_scene_to_the_flow_batch(self):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            self.skipTest(f"customtkinter not available: {exc}")
        row = self._row("stock_video")
        self.mgr.change_source(row, "flow_image")

        class FakeApp:
            _asset_manager = self.mgr

        self.assertTrue(_app.VideoGeneratorApp._scene_is_flow(FakeApp(), row))
        FakeApp._asset_manager = None
        self.assertFalse(_app.VideoGeneratorApp._scene_is_flow(FakeApp(), row))  # no manager yet: the CSV row decides


class TestVisualQaReadsSavedCoveragePlans(unittest.TestCase):
    PLAN = {"scene_id": 1, "narration_duration": 4.0, "strategy": "single",
            "segments": [{"start": 0.0, "end": 4.0, "asset_class": "stock_image", "visual_role": "primary",
                          "avoid_loop": False, "semantic_query_hint": "harbor"}]}

    def test_saved_plan_is_read(self):
        from visual_qa.coverage import _plan_from_dict

        plan = _plan_from_dict(self.PLAN)
        self.assertEqual(plan.segments[0].asset_class, "stock_image")

    def test_older_key_still_reads(self):
        from visual_qa.coverage import _plan_from_dict

        old = {**self.PLAN, "segments": [{"start": 0.0, "end": 4.0, "asset_type": "image"}]}
        self.assertEqual(_plan_from_dict(old).segments[0].asset_class, "image")

    def test_refined_plan_is_written_with_the_current_field(self):
        from visual_qa.coverage import _plan_from_dict, score_duration_coverage

        _, _, refined = score_duration_coverage(4.0, 6.0, self.PLAN)
        seg = refined["segments"][0]
        self.assertEqual(seg.get("asset_class"), "stock_image")
        self.assertNotIn("asset_type", seg)
        self.assertEqual(_plan_from_dict(refined).segments[0].asset_class, "stock_image")  # and reads back

    def test_full_visual_qa_runs_on_a_video_scene_with_a_coverage_plan(self):
        """Stills return before the plan is read; a video scene is where QA used to stop with the TypeError."""
        import subprocess

        from visual_qa import evaluate_scene_asset

        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not available")
        tmp = Path(tempfile.mkdtemp())
        try:
            clip = tmp / "002.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=24:duration=3",
                            "-pix_fmt", "yuv420p", str(clip)], check=True)
            plan = {**self.PLAN, "segments": [{**self.PLAN["segments"][0], "asset_class": "stock_video"}]}
            scene = SceneRow(scene_number="2", script_segment="The harbor at dawn.", asset_type="stock_video", stock="harbor")
            res = AssetResult("2", clip, MediaType.VIDEO, AssetSource.STOCK_VIDEO, SceneStatus.READY,
                              metadata={"provider": "pexels", "provider_asset_id": "pexels:2", "title": "harbor at dawn"})
            q = evaluate_scene_asset(scene, res, images_dir=tmp, coverage_plan=plan, enable_vision=False)
            self.assertNotEqual(str(q.status), "SKIPPED")
            self.assertIsNotNone(q.duration_coverage)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
