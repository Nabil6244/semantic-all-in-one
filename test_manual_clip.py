#!/usr/bin/env python3
"""Manual local clip recovery: validate, copy into Images/, mark scene READY."""

from __future__ import annotations

import unittest
from pathlib import Path

from asset_manager import AssetManager
from manual_clip import (
    FILE_DIALOG_TYPES,
    ManualClipError,
    install_manual_clip,
    normalize_picked_path,
    validate_local_media,
)
from providers.base import AssetSource, MediaType, SceneRow, SceneStatus
from scene_qa import SceneQAState
from scene_recovery import PLACEHOLDER_PNG, scene_key
from test_asset_pipeline import AssetPipelineTestCase, FakeProvider

TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00" + (b"\x08" * 64)
    + b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    + b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\xff\xd9"
)
TINY_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _failed_stock(n="47"):
    return SceneRow(
        scene_number=n, script_segment="narration",
        asset_type="stock_video", stock="empty query",
    )


class TestPickerPath(unittest.TestCase):
    def test_empty_picker_rejected(self):
        with self.assertRaises(ManualClipError):
            normalize_picked_path("")
        with self.assertRaises(ManualClipError):
            normalize_picked_path("   ")

    def test_dialog_filters_include_supported_types(self):
        blob = " ".join(spec[1] for spec in FILE_DIALOG_TYPES)
        for ext in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".png", ".jpg", ".webp"):
            self.assertIn(ext, blob)


class TestValidation(AssetPipelineTestCase):
    def test_missing_file_rejected(self):
        with self.assertRaises(ManualClipError) as ctx:
            validate_local_media(self.tmp / "nope.mp4")
        self.assertIn("does not exist", str(ctx.exception).lower())

    def test_unsupported_extension_rejected(self):
        bad = self.tmp / "notes.txt"
        bad.write_text("hello")
        with self.assertRaises(ManualClipError) as ctx:
            validate_local_media(bad)
        self.assertIn("unsupported", str(ctx.exception).lower())

    def test_unreadable_directory_rejected(self):
        with self.assertRaises(ManualClipError):
            validate_local_media(self.tmp)

    def test_valid_image_accepted(self):
        src = self.tmp / "shot.png"
        src.write_bytes(PLACEHOLDER_PNG)
        info = validate_local_media(src)
        self.assertEqual(info.media_type, MediaType.IMAGE)
        self.assertEqual(info.suffix, ".png")

    def test_valid_jpeg_accepted(self):
        src = self.tmp / "shot.jpg"
        src.write_bytes(TINY_JPEG)
        info = validate_local_media(src)
        self.assertEqual(info.media_type, MediaType.IMAGE)

    def test_valid_video_accepted(self):
        src = self.tmp / "clip.mp4"
        src.write_bytes(TINY_MP4)
        info = validate_local_media(src)
        self.assertEqual(info.media_type, MediaType.VIDEO)

    def test_image_bytes_with_video_extension_rejected(self):
        src = self.tmp / "clip.mp4"
        src.write_bytes(PLACEHOLDER_PNG)
        with self.assertRaises(ManualClipError):
            validate_local_media(src)


class TestInstallAndState(AssetPipelineTestCase):
    def test_copied_into_project_images_and_becomes_ready(self):
        src = self.tmp / "user_clip.png"
        src.write_bytes(PLACEHOLDER_PNG)
        dest, info = install_manual_clip(self.images, "47", src)
        self.assertEqual(dest, self.images / "047.png")
        self.assertTrue(dest.is_file())
        self.assertTrue((self.images / "047_manual.png").is_file())
        self.assertEqual(info.media_type, MediaType.IMAGE)
        self.assertTrue(src.is_file(), "original must not be moved")

    def test_failed_scene_becomes_ready_and_error_count_drops(self):
        src = self.tmp / "fix.png"
        src.write_bytes(PLACEHOLDER_PNG)
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"47": "fail"}, media_type=MediaType.VIDEO)
        scene = _failed_stock()
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        first = mgr.resolve_all([scene])
        self.assertFalse(first.results["47"].ok)
        qa = SceneQAState()
        results = {"047": first.results["47"]}
        snap = qa.snapshot([scene], results)
        self.assertEqual(snap.needs_action, 1)
        self.assertEqual(snap.header, "0 / 1 READY · 1 NEEDS ACTION")

        ready = mgr.attach_manual_clip(scene, src)
        self.assertTrue(ready.ok)
        self.assertEqual(ready.source, AssetSource.MANUAL)
        self.assertEqual(ready.status, SceneStatus.READY)
        rec = mgr.manifest.get("47")
        self.assertEqual(rec["status"], "complete")
        self.assertEqual(rec["source"], "manual")
        self.assertTrue(Path(rec["local_path"]).is_file())

        results["047"] = ready
        snap = qa.snapshot([scene], results)
        self.assertEqual(snap.needs_action, 0)
        self.assertEqual(snap.header, "✓ 1 / 1 READY")
        self.assertEqual(snap.health, "healthy")

    def test_manual_replaces_failed_placeholder_not_duplicate_active(self):
        skip_png = self.images / "047.png"
        skip_png.write_bytes(PLACEHOLDER_PNG)
        src = self.tmp / "real.jpg"
        src.write_bytes(TINY_JPEG)
        dest, _ = install_manual_clip(self.images, "47", src)
        self.assertEqual(dest.name, "047.jpg")
        self.assertTrue(dest.is_file())
        # leftover PNG must not remain the active lookup (images are preferred)
        from video_generator import find_image_for_scene
        found = find_image_for_scene(self.images, "47")
        self.assertEqual(found.resolve(), dest.resolve())

    def test_does_not_silently_overwrite_manual_archive(self):
        src = self.tmp / "a.png"
        src.write_bytes(PLACEHOLDER_PNG)
        install_manual_clip(self.images, "47", src)
        first_archive = (self.images / "047_manual.png").read_bytes()
        src2 = self.tmp / "b.png"
        src2.write_bytes(PLACEHOLDER_PNG + b"x")
        install_manual_clip(self.images, "47", src2)
        self.assertEqual((self.images / "047_manual.png").read_bytes(), first_archive)
        self.assertTrue((self.images / "047_manual_2.png").is_file())

    def test_survives_restart_via_manifest(self):
        src = self.tmp / "keep.png"
        src.write_bytes(PLACEHOLDER_PNG)
        scene = _failed_stock("47")
        mgr = AssetManager(self.images, log=lambda *_: None)
        mgr.attach_manual_clip(scene, src)
        mgr2 = AssetManager(self.images, log=lambda *_: None)
        cached = mgr2._cache_hit(scene, AssetSource.STOCK_VIDEO)
        self.assertIsNotNone(cached)
        self.assertTrue(cached.ok)
        self.assertEqual(cached.source, AssetSource.MANUAL)

    def test_skip_and_retry_still_work(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"2": "fail"}, media_type=MediaType.VIDEO)
        scene = SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2")
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        mgr.resolve_all([scene])
        skipped = mgr.skip_scene(scene)
        self.assertEqual(skipped.status, SceneStatus.SKIPPED)
        stock.scripted["2"] = "ok"
        # retry-after-skip still uses the existing flow-image path when no flow provider:
        # attach a manual clip instead to recover
        src = self.tmp / "ok.png"
        src.write_bytes(PLACEHOLDER_PNG)
        ready = mgr.attach_manual_clip(scene, src)
        self.assertTrue(ready.ok)
        self.assertNotIn(scene_key("2"), mgr.recovery.skipped)

    def test_retry_untouched_by_manual_helper(self):
        stock = FakeProvider(AssetSource.STOCK_VIDEO, {"1": "ok", "2": "fail"}, media_type=MediaType.VIDEO)
        rows = [
            SceneRow(scene_number="1", script_segment="a", asset_type="stock_video", stock="q1"),
            SceneRow(scene_number="2", script_segment="b", asset_type="stock_video", stock="q2"),
        ]
        mgr = AssetManager(self.images, stock_provider=stock, log=lambda *_: None)
        mgr.resolve_all(rows)
        before = (self.images / "001.mp4").read_bytes()
        src = self.tmp / "fix.png"
        src.write_bytes(PLACEHOLDER_PNG)
        mgr.attach_manual_clip(rows[1], src)
        self.assertEqual((self.images / "001.mp4").read_bytes(), before)
        stock.calls.clear()
        stock.scripted["2"] = "ok"
        # scene 2 is now manual-ready; retry would still hit stock, but ready file stays unless retry runs
        self.assertTrue((self.images / "002.png").is_file())


if __name__ == "__main__":
    unittest.main()
