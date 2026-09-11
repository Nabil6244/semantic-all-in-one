"""Focused tests for Local Assets numbered matching + pipeline integration.

Additive only: existing flow/stock/youtube CSV types must keep routing the same.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from asset_manager import AssetManager
from providers.base import AssetSource, MediaType, SceneRow, SceneStatus
from providers.local_assets import (
    check_local_assets,
    expected_stem,
    find_numbered_asset,
    media_kind_for_asset_type,
)
from providers.local_provider import LocalProvider
from providers.router import SceneAssetRouter
from scene_recovery import mark_needs_action


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class NumberMappingTests(unittest.TestCase):
    def test_expected_stems(self):
        self.assertEqual(expected_stem("1"), "001")
        self.assertEqual(expected_stem("2"), "002")
        self.assertEqual(expected_stem("10"), "010")
        self.assertEqual(expected_stem("57"), "057")
        self.assertEqual(expected_stem("100"), "100")
        self.assertEqual(expected_stem("200"), "200")

    def test_media_kinds(self):
        self.assertEqual(media_kind_for_asset_type("local_video"), "video")
        self.assertEqual(media_kind_for_asset_type("local_image"), "image")
        self.assertIsNone(media_kind_for_asset_type("flow_video"))
        self.assertIsNone(media_kind_for_asset_type("stock_image"))

    def test_scene_mapping_mixed_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "001.mp4")
            _touch(folder / "002.jpg")
            _touch(folder / "003.mp4")
            _touch(folder / "004.png")
            _touch(folder / "010.mp4")
            _touch(folder / "057.mp4")
            _touch(folder / "100.png")
            _touch(folder / "200.mp4")
            _touch(folder / "unused_reference.mp4")
            _touch(folder / "notes.txt")

            cases = [
                ("1", "video", "001.mp4"),
                ("2", "image", "002.jpg"),
                ("10", "video", "010.mp4"),
                ("57", "video", "057.mp4"),
                ("100", "image", "100.png"),
                ("200", "video", "200.mp4"),
            ]
            for scene, kind, name in cases:
                match, issue = find_numbered_asset(folder, scene, kind)
                self.assertIsNone(issue, msg=f"scene {scene}: {issue}")
                self.assertIsNotNone(match)
                self.assertEqual(match.path.name, name)


class PrefixedNameAutoSortTests(unittest.TestCase):
    """Exports like ``1_Realistic_cinematic_….mp4`` map by leading scene number."""

    def test_leading_number_prefixed_videos(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "1_Realistic_cinematic_3D_game_76038777_1080p.mp4")
            _touch(folder / "2_Realistic_cinematic_3D_game_75158932_1080p.mp4")
            _touch(folder / "8_Realistic_cinematic_3D_game_44106946_1080p.mp4")
            _touch(folder / "10_Realistic_cinematic_3D_game_99999999_1080p.mp4")
            _touch(folder / "Success_11-09-2026.txt")
            _touch(folder / "Video_Save_List_2026-09-11.txt")

            for scene, name in (
                ("1", "1_Realistic_cinematic_3D_game_76038777_1080p.mp4"),
                ("2", "2_Realistic_cinematic_3D_game_75158932_1080p.mp4"),
                ("8", "8_Realistic_cinematic_3D_game_44106946_1080p.mp4"),
                ("10", "10_Realistic_cinematic_3D_game_99999999_1080p.mp4"),
            ):
                match, issue = find_numbered_asset(folder, scene, "video")
                self.assertIsNone(issue, msg=f"scene {scene}: {issue}")
                self.assertEqual(match.path.name, name)

            # Scene 1 must not steal the 10_… file
            match1, _ = find_numbered_asset(folder, "1", "video")
            self.assertEqual(match1.path.name, "1_Realistic_cinematic_3D_game_76038777_1080p.mp4")

            missing, issue = find_numbered_asset(folder, "7", "video")
            self.assertIsNone(missing)
            self.assertEqual(issue.code, "missing")

    def test_exact_stem_wins_over_prefixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "001.mp4")
            _touch(folder / "1_Realistic_extra_1080p.mp4")
            match, issue = find_numbered_asset(folder, "1", "video")
            self.assertIsNone(issue)
            self.assertEqual(match.path.name, "001.mp4")

    def test_ambiguous_two_prefixed_same_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "3_Realistic_a_1080p.mp4")
            _touch(folder / "3_Realistic_b_1080p.mp4")
            match, issue = find_numbered_asset(folder, "3", "video")
            self.assertIsNone(match)
            self.assertEqual(issue.code, "ambiguous")

    def test_padded_prefix_008(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "008_clip.mp4")
            match, issue = find_numbered_asset(folder, "8", "video")
            self.assertIsNone(issue)
            self.assertEqual(match.path.name, "008_clip.mp4")


class MissingAndWrongTypeTests(unittest.TestCase):
    def test_missing_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "056.mp4")
            _touch(folder / "058.mp4")
            match, issue = find_numbered_asset(folder, "57", "video")
            self.assertIsNone(match)
            self.assertIsNotNone(issue)
            self.assertEqual(issue.code, "missing")
            self.assertIn("057", issue.reason)
            self.assertIn("local video", issue.reason.lower())

    def test_wrong_media_type_not_substituted(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "057.jpg")
            match, issue = find_numbered_asset(folder, "57", "video")
            self.assertIsNone(match)
            self.assertIsNotNone(issue)
            self.assertEqual(issue.code, "wrong_type")
            self.assertIn("057.jpg", issue.reason)

    def test_ambiguous_same_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "057.mp4")
            _touch(folder / "057.mov")
            match, issue = find_numbered_asset(folder, "57", "video")
            self.assertIsNone(match)
            self.assertIsNotNone(issue)
            self.assertEqual(issue.code, "ambiguous")

    def test_type_disambiguates_when_both_kinds_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "057.mp4")
            _touch(folder / "057.jpg")
            v_match, v_issue = find_numbered_asset(folder, "57", "video")
            i_match, i_issue = find_numbered_asset(folder, "57", "image")
            self.assertIsNone(v_issue)
            self.assertEqual(v_match.path.name, "057.mp4")
            self.assertIsNone(i_issue)
            self.assertEqual(i_match.path.name, "057.jpg")


class CsvRoutingRegressionTests(unittest.TestCase):
    """Existing workflows must keep the same router outcomes."""

    def test_existing_types_unchanged(self):
        cases = [
            ("flow_image", "a city", AssetSource.FLOW_IMAGE),
            ("flow_video", "a launch", AssetSource.FLOW_VIDEO),
            ("image", "a city", AssetSource.FLOW_IMAGE),
            ("video", "a launch", AssetSource.FLOW_VIDEO),
            ("stock_image", "market", AssetSource.STOCK_IMAGE),
            ("stock_video", "crowd", AssetSource.STOCK_VIDEO),
            ("youtube_video", "iphone keynote", AssetSource.YOUTUBE_VIDEO),
        ]
        for asset_type, prompt, expected in cases:
            row = SceneRow.from_csv_row(
                {
                    "scene_number": "1",
                    "script_segment": "seg",
                    "asset_type": asset_type,
                    "prompt": prompt,
                }
            )
            self.assertEqual(SceneAssetRouter.classify(row), expected, asset_type)

    def test_legacy_local_still_unclassified(self):
        row = SceneRow.from_csv_row(
            {"scene_number": "1", "script_segment": "seg", "asset_type": "local", "prompt": ""}
        )
        self.assertEqual(row.asset_type, "local")
        self.assertIsNone(SceneAssetRouter.classify(row))

    def test_local_numbered_types_route_to_local(self):
        video = SceneRow.from_csv_row(
            {"scene_number": "1", "script_segment": "a", "asset_type": "local_video", "prompt": "ignored"}
        )
        image = SceneRow.from_csv_row(
            {"scene_number": "2", "script_segment": "b", "asset_type": "local_image", "prompt": "ignored"}
        )
        self.assertEqual(video.asset_type, "local_video")
        self.assertEqual(image.asset_type, "local_image")
        self.assertEqual(video.prompt, "")
        self.assertEqual(image.prompt, "")
        self.assertTrue(video.wants_local_numbered)
        self.assertEqual(SceneAssetRouter.classify(video), AssetSource.LOCAL)
        self.assertEqual(SceneAssetRouter.classify(image), AssetSource.LOCAL)


class ProviderAndNeedsActionTests(unittest.TestCase):
    def test_provider_installs_into_images_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "library"
            images = root / "images"
            library.mkdir()
            images.mkdir()
            _touch(library / "001.mp4")
            _touch(library / "002.jpg")
            provider = LocalProvider(library_dir=library)
            # Avoid ffprobe dependency in install_manual_clip for tiny stubs.
            with mock.patch("manual_clip.sniff_media_kind", side_effect=lambda p: (
                "video" if Path(p).suffix.lower() in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"} else "image"
            )), mock.patch("manual_clip._probe_media", return_value={}):
                v = provider.resolve(
                    SceneRow(scene_number="1", script_segment="a", asset_type="local_video"),
                    images,
                )
                i = provider.resolve(
                    SceneRow(scene_number="2", script_segment="b", asset_type="local_image"),
                    images,
                )
            self.assertTrue(v.ok)
            self.assertEqual(v.media_type, MediaType.VIDEO)
            self.assertTrue(v.path.is_file())
            self.assertEqual(v.path.parent.resolve(), images.resolve())
            self.assertTrue(i.ok)
            self.assertEqual(i.media_type, MediaType.IMAGE)

    def test_missing_becomes_failed_then_needs_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "library"
            images = root / "images"
            library.mkdir()
            images.mkdir()
            _touch(library / "001.mp4")
            mgr = AssetManager(images, local_assets_dir=library, log=lambda *_: None)
            scene = SceneRow(scene_number="57", script_segment="gap", asset_type="local_video")
            result = mgr.resolve_scene(scene)
            self.assertFalse(result.ok)
            self.assertEqual(result.status, SceneStatus.NEEDS_ACTION)
            self.assertIn("057", result.error or "")
            # mark_needs_action is what Visual Plan / QA already consume
            marked = mark_needs_action(result)
            self.assertEqual(marked.status, SceneStatus.NEEDS_ACTION)

    def test_no_cloud_fallback_on_local_failure(self):
        """LOCAL is not fallback-eligible — failure must not call stock/flow."""
        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            stock = mock.Mock()
            flow = mock.Mock()
            mgr = AssetManager(
                images,
                stock_provider=stock,
                flow_image_provider=flow,
                local_assets_dir=images / "missing_library",
                log=lambda *_: None,
            )
            scene = SceneRow(
                scene_number="1",
                script_segment="a",
                asset_type="local_video",
                fallbacks=["stock_video", "flow_image"],
            )
            result = mgr.resolve_scene(scene)
            self.assertFalse(result.ok)
            stock.resolve.assert_not_called()
            flow.resolve.assert_not_called()
            flow.resolve_batch.assert_not_called()

    def test_asset_manager_does_not_invent_duration(self):
        """Local resolve must not set a synthetic duration — VO/editorial remains authoritative."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "library"
            images = root / "images"
            library.mkdir()
            images.mkdir()
            _touch(library / "001.jpg")
            provider = LocalProvider(library_dir=library)
            with mock.patch("manual_clip.sniff_media_kind", return_value="image"), mock.patch(
                "manual_clip._probe_media", return_value={}
            ):
                result = provider.resolve(
                    SceneRow(scene_number="1", script_segment="a", asset_type="local_image"),
                    images,
                )
            self.assertTrue(result.ok)
            self.assertNotIn("planned_duration", result.metadata or {})
            # duration may be absent when ffprobe finds nothing — never invent VO length
            self.assertTrue(
                "duration" not in (result.metadata or {})
                or result.metadata.get("duration") is None
                or float(result.metadata["duration"]) > 0
            )


class CheckAndEditorialHandoffTests(unittest.TestCase):
    def test_check_local_assets_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _touch(folder / "001.mp4")
            _touch(folder / "002.jpg")
            scenes = [
                SceneRow(scene_number="1", script_segment="a", asset_type="local_video"),
                SceneRow(scene_number="2", script_segment="b", asset_type="local_image"),
                SceneRow(scene_number="3", script_segment="c", asset_type="local_video"),
            ]
            rows, ready, needs = check_local_assets(folder, scenes)
            self.assertEqual(ready, 2)
            self.assertEqual(needs, 1)
            self.assertEqual(len(rows), 3)

    def test_resolved_local_asset_is_standard_asset_result(self):
        """Editorial/renderer consume AssetResult paths — same type as other providers."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "library"
            images = root / "images"
            library.mkdir()
            images.mkdir()
            _touch(library / "001.mp4")
            mgr = AssetManager(images, local_assets_dir=library, log=lambda *_: None)
            with mock.patch("manual_clip.sniff_media_kind", return_value="video"), mock.patch(
                "manual_clip._probe_media", return_value={"duration": 7.2}
            ):
                result = mgr.resolve_scene(
                    SceneRow(scene_number="1", script_segment="a", asset_type="local_video")
                )
            self.assertTrue(result.ok)
            self.assertEqual(result.source, AssetSource.LOCAL)
            self.assertIsInstance(result.path, Path)
            # Existing editorial compile reads asset_results by scene — path only.
            self.assertTrue(result.path.is_file())


if __name__ == "__main__":
    unittest.main()
