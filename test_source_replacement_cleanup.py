#!/usr/bin/env python3
"""Changing a scene's source leaves exactly one file the renderer can take as that scene's source: the new one.

The renderer (video_generator.find_image_for_scene / build_scene_media_index) prefers images over videos, so an old
002.jpg left next to a new 002.mp4 used to win and the final video kept the old picture. No network, no Flow.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

import video_generator as vg
from asset_manager import AssetManager
from providers.base import AssetProvider, AssetResult, AssetSource, MediaType, SceneRow, SceneStatus
from test_asset_pipeline import AssetPipelineTestCase

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class ExtProvider(AssetProvider):
    """Writes <scene>.<ext> into the images folder, like every real provider does."""

    def __init__(self, source: AssetSource, ext: str, tag: str):
        self.source, self.ext, self.tag = source, ext, tag

    def resolve(self, scene: SceneRow, images_dir: Path, log=print) -> AssetResult:
        target = Path(images_dir) / f"{int(scene.scene_number):03d}{self.ext}"
        target.write_bytes(self.tag.encode())
        kind = MediaType.VIDEO if self.ext in vg.VIDEO_EXTS else MediaType.IMAGE
        return AssetResult(scene.scene_number, target, kind, self.source, SceneStatus.READY,
                           metadata={"provider_asset_id": f"{self.tag}-{scene.scene_number}"})

    def regenerate(self, scene, images_dir, exclude=None, log=print):
        return self.resolve(scene, images_dir, log=log)


def _scene(n="2", asset_type="stock_image"):
    return SceneRow(scene_number=n, script_segment="x", asset_type=asset_type, prompt="p", stock="q")


class TestSourceReplacementCleanup(AssetPipelineTestCase):
    def _mgr(self, stock_ext=".jpg", flow_image_ext=".png", flow_video_ext=".mp4"):
        return AssetManager(
            self.images,
            stock_provider=ExtProvider(AssetSource.STOCK_IMAGE, stock_ext, "stock"),
            flow_image_provider=ExtProvider(AssetSource.FLOW_IMAGE, flow_image_ext, "flowimg"),
            flow_video_provider=ExtProvider(AssetSource.FLOW_VIDEO, flow_video_ext, "flowvid"),
            log=lambda *_: None,
        )

    def _neighbours(self):
        """Other scenes' files, including look-alike numbers (012, 020, 0020) that must never be touched."""
        files = {"001.jpg": b"s1", "003.png": b"s3", "012.jpg": b"s12", "020.mp4": b"s20", "0020.png": b"s20b"}
        for name, data in files.items():
            (self.images / name).write_bytes(data)
        return files

    def _assert_neighbours_intact(self, files):
        for name, data in files.items():
            self.assertEqual((self.images / name).read_bytes(), data, f"{name} must not be touched")

    def _scene_sources(self, n="2"):
        """Every file the renderer could take as scene n's source."""
        stems = {f"{int(n)}", f"{int(n):02d}", f"{int(n):03d}", f"{int(n):04d}"}
        return sorted(p.name for p in self.images.iterdir() if p.stem in stems and p.suffix.lower() in vg.MEDIA_EXTS)

    def _assert_render_uses(self, name, n="2"):
        self.assertEqual(self._scene_sources(n), [name], "exactly one eligible source must remain")
        self.assertEqual(vg.find_image_for_scene(self.images, n).name, name)
        self.assertEqual(vg.find_image_for_scene(self.images, n, ext_cache=vg.build_scene_media_index(self.images)).name, name)

    # ---- the critical regression ---------------------------------------------------------------------------------------

    def test_jpg_to_mp4_render_uses_the_new_video(self):
        """scene 2: old 002.jpg, new 002.mp4 — the image-first lookup must not find the old picture."""
        mgr = self._mgr()
        neighbours = self._neighbours()
        mgr.resolve_all([_scene("2", "stock_image")])
        self.assertEqual(self._scene_sources(), ["002.jpg"])
        result = mgr.change_source(_scene("2", "stock_image"), "flow_video")
        self.assertTrue(result.ok)
        self._assert_render_uses("002.mp4")
        self.assertEqual((self.images / "002.mp4").read_bytes(), b"flowvid")
        self._assert_neighbours_intact(neighbours)

    def test_two_leftover_images_both_removed_when_the_new_source_is_a_video(self):
        """The state a project is left in by the old cleanup (002.jpg + 002.png): both go, 002.mp4 is used."""
        mgr = self._mgr()
        (self.images / "002.jpg").write_bytes(b"old-stock")
        (self.images / "002.png").write_bytes(b"old-flow")
        mgr.change_source(_scene("2"), "flow_video")
        self._assert_render_uses("002.mp4")

    # ---- the listed replacements ---------------------------------------------------------------------------------------

    def test_jpg_to_png(self):
        mgr = self._mgr()
        mgr.resolve_all([_scene("2", "stock_image")])
        mgr.change_source(_scene("2"), "flow_image")
        self._assert_render_uses("002.png")

    def test_png_to_mp4(self):
        mgr = self._mgr()
        mgr.change_source(_scene("2"), "flow_image")
        self.assertEqual(self._scene_sources(), ["002.png"])
        mgr.change_source(_scene("2", "flow_image"), "flow_video")
        self._assert_render_uses("002.mp4")

    def test_mp4_to_png(self):
        """The new file already wins the lookup here; the old video must still not remain as a second source."""
        mgr = self._mgr()
        mgr.change_source(_scene("2"), "flow_video")
        self.assertEqual(self._scene_sources(), ["002.mp4"])
        mgr.change_source(_scene("2", "flow_video"), "flow_image")
        self._assert_render_uses("002.png")

    def test_stock_to_flow_image(self):
        mgr = self._mgr(stock_ext=".mp4")   # a stock video this time
        neighbours = self._neighbours()
        mgr.resolve_all([_scene("2", "stock_video")])
        mgr.change_source(_scene("2", "stock_video"), "flow_image")
        self._assert_render_uses("002.png")
        self._assert_neighbours_intact(neighbours)

    def test_stock_image_to_flow_video(self):
        mgr = self._mgr()
        mgr.resolve_all([_scene("2", "stock_image")])
        mgr.change_source(_scene("2"), "flow_video")
        self._assert_render_uses("002.mp4")
        self.assertEqual(mgr.manifest.get("2")["source"], "flow_video")

    def test_same_name_replacement_keeps_the_new_content(self):
        """002.mp4 -> 002.mp4 (stock video -> Flow video): the file is replaced in place, not deleted."""
        mgr = self._mgr(stock_ext=".mp4")
        mgr.resolve_all([_scene("2", "stock_video")])
        mgr.change_source(_scene("2", "stock_video"), "flow_video")
        self._assert_render_uses("002.mp4")
        self.assertEqual((self.images / "002.mp4").read_bytes(), b"flowvid")

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe needed to make a real video")
    def test_flow_video_to_manual_video(self):
        mgr = self._mgr()
        neighbours = self._neighbours()
        mgr.change_source(_scene("2"), "flow_video")
        (self.images / "002.png").write_bytes(b"leftover")   # a leftover the old cleanup could leave behind
        picked = self.tmp / "my clip.mov"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(picked)], check=True)
        result = mgr.attach_manual_clip(_scene("2", "flow_video"), picked)
        self.assertTrue(result.ok, result.error)
        self._assert_render_uses("002.mov")
        self.assertEqual((self.images / "002.mov").read_bytes(), picked.read_bytes())
        self.assertTrue(any(p.name.startswith("002_manual") for p in self.images.iterdir()), "the manual archive copy is kept")
        self._assert_neighbours_intact(neighbours)

    def test_retained_alternate_and_archive_clips_survive(self):
        mgr = self._mgr()
        mgr.resolve_all([_scene("2", "stock_image")])
        keep = {"002_b.jpg": b"alt-b", "002_c.mp4": b"alt-c", "002_manual.mp4": b"archive", "002_replaced.png": b"backup"}
        for name, data in keep.items():
            (self.images / name).write_bytes(data)
        mgr.change_source(_scene("2"), "flow_video")
        self._assert_render_uses("002.mp4")
        for name, data in keep.items():
            self.assertEqual((self.images / name).read_bytes(), data, f"{name} must be kept")
        self.assertEqual([p.name for p in vg.find_complement_assets_for_scene(self.images, "2")], ["002_b.jpg", "002_c.mp4"])

    def test_unpadded_and_upper_case_leftovers_are_removed(self):
        mgr = self._mgr()
        (self.images / "2.jpg").write_bytes(b"old")
        (self.images / "02.PNG").write_bytes(b"old")
        mgr.change_source(_scene("2"), "flow_video")
        self._assert_render_uses("002.mp4")

    def test_a_failed_replacement_removes_nothing(self):
        mgr = self._mgr()
        mgr.resolve_all([_scene("2", "stock_image")])
        mgr.flow_video_provider = ExtProvider(AssetSource.FLOW_VIDEO, ".mp4", "x")
        mgr.flow_video_provider.resolve = lambda scene, images_dir, log=print: AssetResult(
            scene.scene_number, None, None, AssetSource.FLOW_VIDEO, SceneStatus.FAILED, error="no")
        self.assertFalse(mgr.change_source(_scene("2"), "flow_video").ok)
        self.assertEqual(self._scene_sources(), ["002.jpg"], "the old source stays until a new one exists")


if __name__ == "__main__":
    unittest.main()
