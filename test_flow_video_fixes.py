"""Focused regressions for three Flow/export bugs:

1. unchecked Flow accounts must never be sent to the engine (stale cached
   provider on Retry/Alt/Fix All, and "all unchecked" silently meaning "all");
2. a full disk during the final mux must be reported as such, with the
   truncated output removed, instead of "ffmpeg final mux failed — see log".
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import video_generator as vg
from providers.base import SceneRow, SceneStatus


def _app_cls():
    import app as _app

    return _app.VideoGeneratorApp


class TestVideoAccountSelection(unittest.TestCase):
    def _ids(self, profile):
        fake = SimpleNamespace(_default_video_profile=lambda: profile)
        return _app_cls()._video_account_ids(fake)

    def test_checked_accounts_are_returned_unchanged(self):
        self.assertEqual(self._ids({"account_ids": ["a", "b"]}), ["a", "b"])

    def test_untouched_profile_still_means_all_accounts(self):
        self.assertIsNone(self._ids({"account_ids": []}))

    def test_explicitly_unchecking_every_account_means_none_not_all(self):
        self.assertEqual(self._ids({"account_ids": [], "account_ids_explicit": True}), [])

    def test_empty_selection_never_reaches_the_engine(self):
        from providers.flow.provider import FlowProvider

        engine = MagicMock()
        fp = FlowProvider(engine, media_kind="video", account_ids=[])
        scenes = [SceneRow(scene_number="3", script_segment="x", asset_type="video", prompt="p")]
        with tempfile.TemporaryDirectory() as tmp:
            results = fp.resolve_batch(scenes, Path(tmp), log=lambda *_: None)
        engine.ensure_running.assert_not_called()
        self.assertEqual(results["3"].status, SceneStatus.FAILED)
        self.assertIn("No Flow accounts are checked", results["3"].error)

    def test_cached_manager_picks_up_accounts_unchecked_after_it_was_built(self):
        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            video_provider = SimpleNamespace(account_ids=["a", "b", "c"])
            mgr = SimpleNamespace(
                images_dir=images,
                youtube_provider=object(),
                flow_video_provider=video_provider,
                archive_provider=object(),
                nasa_provider=object(),
                local_provider=SimpleNamespace(library_dir=None),
                recovery=SimpleNamespace(skipped=set()),
            )
            fake = SimpleNamespace(
                _asset_manager=mgr,
                _asset_manager_local_only=False,
                _production_mode_is_local=lambda: False,
                _local_assets_dir=lambda: None,
                _video_account_ids=lambda: ["a"],  # "b" and "c" unchecked since
                _hydrated_skipped=set(),
                _apply_footage_quality=lambda m: None,
            )
            out = _app_cls()._ensure_asset_manager(fake, images)
        self.assertIs(out, mgr)
        self.assertEqual(video_provider.account_ids, ["a"])


class TestMuxDiskFull(unittest.TestCase):
    ENOSPC = (
        "[out#0/mp4 @ 0x6000031f8300] Error writing trailer: No space left on device\n"
        "Conversion failed!\n"
    )

    def test_disk_full_is_reported_and_partial_output_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "final.mp4"
            out.write_bytes(b"partial")
            with self.assertRaises(SystemExit) as ctx:
                vg._exit_if_disk_full(self.ENOSPC, out)
            self.assertIn("ran out of disk space", str(ctx.exception.code))
            self.assertFalse(out.exists())

    def test_other_mux_errors_are_left_to_the_existing_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "final.mp4"
            out.write_bytes(b"x")
            vg._exit_if_disk_full("Invalid data found when processing input", out)
            self.assertTrue(out.exists())


class TestOverscaledVideoAccountSelection(unittest.TestCase):
    """Overscaled / Exp Solar resolve media through their own AssetManager
    (resolve_scene_graph_media -> resolve_scene_assets), so the checked
    accounts must be threaded all the way to that video FlowProvider."""

    def _capture_video_provider(self, **kwargs):
        from unittest.mock import patch

        import asset_manager

        captured = {}
        real_init = asset_manager.AssetManager.__init__

        def spy_init(self_, *a, **kw):
            captured["video"] = kw.get("flow_video_provider")
            real_init(self_, *a, **kw)

        rows = [{"scene_number": "1", "script_segment": "x", "asset_type": "video", "prompt": "p"}]
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            asset_manager.AssetManager, "__init__", spy_init
        ), patch.object(asset_manager.AssetManager, "resolve_all", return_value={}, create=True):
            try:
                vg.resolve_scene_assets(rows, Path(tmp), flow_engine_manager=MagicMock(), log=lambda *_: None, **kwargs)
            except Exception:
                pass  # only the provider construction matters here
        return captured["video"]

    def test_checked_accounts_reach_the_overscaled_video_provider(self):
        self.assertEqual(self._capture_video_provider(flow_video_account_ids=["a"]).account_ids, ["a"])

    def test_omitting_accounts_keeps_the_old_all_accounts_default(self):
        self.assertIsNone(self._capture_video_provider().account_ids)

    def test_every_layer_forwards_the_parameter(self):
        import inspect

        from scene_graph import app_integration, media_resolution

        self.assertIn("flow_video_account_ids", inspect.signature(app_integration.generate_overscaled_video).parameters)
        self.assertIn("flow_video_account_ids", inspect.signature(media_resolution.resolve_scene_graph_media).parameters)
        self.assertIn("flow_video_account_ids=flow_video_account_ids", inspect.getsource(app_integration))
        self.assertIn("flow_video_account_ids=flow_video_account_ids", inspect.getsource(media_resolution))
        self.assertIn("flow_video_account_ids=self._video_account_ids()", inspect.getsource(_app_cls()))


if __name__ == "__main__":
    unittest.main()
