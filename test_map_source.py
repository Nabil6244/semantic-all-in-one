"""Map as an asset source (step 2): CSV rows, routing, AssetManager resolve /
cache / Change Source persistence, failure + cancel, Local clip priority,
hold-last-frame at render, app labels, and packaging."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from asset_manager import AssetManager
from map_scene.clip import MAP_CLIP_MARKER, is_map_clip
from providers.base import AssetSource, SceneRow, SceneStatus
from providers.map.provider import MapProvider
from providers.router import SceneAssetRouter

ROOT = Path(__file__).resolve().parent
HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _make_clip(path: Path, seconds: float = 1.0, *, map_tag: bool = True, size: str = "320x180", fps: int = 10) -> Path:
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={seconds}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if map_tag:
        cmd += ["-metadata", f"comment={MAP_CLIP_MARKER}"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


class TestCsvRowAndRouting(unittest.TestCase):
    def test_map_row_keeps_its_place_text_intact(self):
        row = SceneRow.from_csv_row({"scene_number": "3", "script_segment": "x", "asset_type": "map",
                                     "prompt": "Florida > Florida Panhandle | camera: zoom_out"})
        self.assertEqual((row.asset_type, row.prompt, row.stock), ("map", "Florida > Florida Panhandle | camera: zoom_out", ""))
        self.assertTrue(row.wants_map)
        self.assertEqual(SceneAssetRouter.classify(row), AssetSource.MAP)

    def test_map_without_a_place_is_not_routable(self):
        row = SceneRow.from_csv_row({"scene_number": "3", "script_segment": "x", "asset_type": "map", "prompt": ""})
        self.assertFalse(row.wants_map)
        self.assertIsNone(SceneAssetRouter.classify(row))

    def test_other_types_are_unchanged(self):
        nasa = SceneRow.from_csv_row({"scene_number": "1", "script_segment": "x", "asset_type": "nasa_video",
                                      "prompt": "apollo || saturn v"})
        self.assertEqual((nasa.prompt, nasa.search_queries), ("apollo", ["apollo", "saturn v"]))
        self.assertEqual(SceneAssetRouter.classify(nasa), AssetSource.NASA_VIDEO)

    def test_change_source_to_map_keeps_a_map_prompt_and_guesses_from_text_otherwise(self):
        m = SceneRow(scene_number="1", script_segment="x", asset_type="map", prompt="Egypt | label: Nile")
        self.assertEqual(m.as_fallback("map").prompt, "Egypt | label: Nile")
        stock = SceneRow(scene_number="1", script_segment="x", asset_type="stock_video", stock="Florida")
        moved = stock.as_fallback("map")
        self.assertEqual((moved.asset_type, moved.prompt, moved.stock), ("map", "Florida", ""))


def _fake_render(clip: Path, calls: list):
    def render(prompt, target, *, duration, ai, progress, cancel_check):
        calls.append(prompt)
        progress(1, 2)
        progress(2, 2)
        shutil.copy2(clip, target)
        return SimpleNamespace(output=Path(target), places={"focus": ["Florida", "admin1", "boundary"]})

    return render


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class TestAssetManagerMapSource(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.clip = _make_clip(self.tmp / "clip.mp4")
        self.calls: list = []
        self.logs: list = []
        self.mgr = AssetManager(self.tmp / "Images", log=self.logs.append,
                                map_provider=MapProvider(render=_fake_render(self.clip, self.calls)))

    def _row(self, prompt="Florida > Florida Panhandle", asset_type="map", **extra):
        return SceneRow.from_csv_row({"scene_number": "4", "script_segment": "x", "asset_type": asset_type,
                                      "prompt": prompt, **extra})

    def test_generate_renders_the_map_into_images_and_records_it(self):
        summary = self.mgr.resolve_all([self._row()])
        result = summary.results["4"]
        self.assertTrue(result.ok, result.error)
        self.assertEqual((result.source, result.path.name), (AssetSource.MAP, "004.mp4"))
        record = self.mgr.manifest.get("4")
        self.assertEqual((record["source"], record["prompt"], record["status"]), ("map", "Florida > Florida Panhandle", "complete"))
        self.assertTrue(any("rendering map" in line for line in self.logs))  # Activity panel

    def test_unchanged_map_is_reused_and_a_new_place_renders_again(self):
        self.mgr.resolve_all([self._row()])
        self.mgr.resolve_all([self._row()])
        self.assertEqual(len(self.calls), 1)
        self.mgr.resolve_all([self._row("Egypt")])
        self.assertEqual(self.calls, ["Florida > Florida Panhandle", "Egypt"])

    def test_unknown_place_is_a_clear_needs_action_failure(self):
        mgr = AssetManager(self.tmp / "Images2", log=lambda *_: None, map_provider=MapProvider())
        result = mgr.resolve_all([self._row("Atlantis Plateau")]).results["4"]
        self.assertEqual(result.status, SceneStatus.NEEDS_ACTION)
        self.assertIn('Couldn\'t find "Atlantis Plateau"', result.error)

    def test_stop_cancels_a_map_scene(self):
        self.mgr.request_cancel()
        result = self.mgr.map_provider.resolve(self._row(), self.tmp / "Images", log=lambda *_: None)
        self.assertEqual(result.status, SceneStatus.CANCELLED)
        self.assertEqual(self.calls, [])

    def test_change_source_to_map_survives_a_regenerate_from_the_csv(self):
        stock_row = self._row("beach drone", asset_type="stock_video")
        chosen = SceneRow(scene_number="4", script_segment="x", asset_type="map", prompt="Florida > Florida Panhandle")
        self.assertTrue(self.mgr.change_source(chosen, "map").ok)
        # A later Generate rebuilds the row from the CSV (still stock): the map choice + place must stick.
        rebuilt = self.mgr._apply_requested_provider(stock_row)
        self.assertEqual((rebuilt.asset_type, rebuilt.prompt), ("map", "Florida > Florida Panhandle"))
        self.assertTrue(self.mgr.resolve_all([stock_row]).results["4"].ok)
        self.assertEqual(len(self.calls), 1)  # reused, not re-rendered
        # Changing to another source later drops the stored place.
        self.mgr._mark_requested_provider("4", "stock_video")
        self.assertNotIn("requested_prompt", self.mgr.manifest.get("4"))

    def test_local_clip_still_wins_over_a_map(self):
        manual = _make_clip(self.tmp / "mine.mp4", map_tag=False)
        self.assertTrue(self.mgr.attach_manual_clip(self._row(), manual).ok)
        result = self.mgr.resolve_all([self._row()]).results["4"]
        self.assertEqual(result.source, AssetSource.MANUAL)
        self.assertEqual(self.calls, [])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class TestHoldLastFrame(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_marker_is_detected(self):
        self.assertTrue(is_map_clip(_make_clip(self.tmp / "m.mp4")))
        self.assertFalse(is_map_clip(_make_clip(self.tmp / "p.mp4", map_tag=False)))
        self.assertFalse(is_map_clip(self.tmp / "missing.mp4"))

    def test_planner_gives_a_map_one_shot_that_holds(self):
        from editorial.schema import EditorialScene
        from editorial.shot_planner import plan_edit_decision

        clip = _make_clip(self.tmp / "m.mp4", seconds=2.0)
        scene = EditorialScene(scene_number="1", start=0.0, end=6.0, duration=6.0, narration_excerpt="x")
        decision = plan_edit_decision(scene, media_path=clip)
        self.assertEqual((decision.strategy, len(decision.shots)), ("HOLD_TAIL", 1))
        shot = decision.shots[0]
        self.assertEqual((shot.source_start, shot.scale, shot.hold_tail), (0.0, 1.0, True))
        short = EditorialScene(scene_number="2", start=0.0, end=1.5, duration=1.5, narration_excerpt="x")
        self.assertEqual(plan_edit_decision(short, media_path=clip).strategy, "SINGLE_SHOT")

    def _tail_frames(self, clip: Path, out: Path):
        import numpy as np
        import video_generator as vg

        vg._render_scene_clip(clip, out, 2.5, 320, 180, 10, False, False, 0.1)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, check=True).stdout
        frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 180, 320).astype(int)
        return frames[12:]  # after the 1 s source ends

    def test_render_freezes_a_map_clip_but_still_loops_other_clips(self):
        held = self._tail_frames(_make_clip(self.tmp / "m.mp4"), self.tmp / "m_out.mp4")
        self.assertLess(max(abs(f - held[0]).mean() for f in held), 1.0)  # frozen last frame
        looped = self._tail_frames(_make_clip(self.tmp / "p.mp4", map_tag=False), self.tmp / "p_out.mp4")
        self.assertGreater(max(abs(f - looped[0]).mean() for f in looped), 5.0)  # unchanged: loops


class TestAppAndPackaging(unittest.TestCase):
    def test_source_lists_know_map(self):
        from downloaded_assets import PIPELINE_SOURCES
        from scene_recovery import CHANGE_SOURCE_ORDER

        self.assertIn("map", CHANGE_SOURCE_ORDER)
        self.assertIn("map", PIPELINE_SOURCES)

    def test_app_labels_and_buckets(self):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(str(exc))
        self.assertEqual(_app.SOURCE_BADGE[AssetSource.MAP][0], "Map")
        self.assertEqual(_app.source_option_label("map"), "Map…")
        self.assertEqual(_app.VideoGeneratorApp._source_mix_bucket(AssetSource.MAP), "Map")
        row = SceneRow(scene_number="1", script_segment="x", asset_type="map", prompt="Egypt")
        self.assertEqual(_app.scene_visual_text_summary(row), "Map: Egypt")

    def test_installer_bundles_the_renderer_and_place_data(self):
        spec = (ROOT / "VideoGenerator.spec").read_text(encoding="utf-8")
        for needle in ('"render.mjs", "page.html", "page.js"', '"dist/maplibre-gl.mjs"',
                       '"map_scene/data"', '"providers.map.provider"'):
            self.assertIn(needle, spec)
        workflow = (ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("cd map-engine"), 2)  # macOS + Windows jobs


if __name__ == "__main__":
    unittest.main()
