"""Regression test for the asset ACQUISITION ordering (not the source-
selection intelligence itself — see test_scene_graph_local_planner.py's
TestSourceIntelligence* for that): stock_video -> flow_image -> stock_image
-> flow_video, applied at the actual resolve_scene_assets() orchestration
layer, before any provider is called. Provider implementations and
AssetManager itself are untouched — only the LIST ORDER scene rows are
handed to resolve_all() in is changed.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import video_generator as vg


class _FakeSummary:
    ok = True
    failed: list = []


class _FakeAssetManager:
    """Records the scene_number order resolve_all() was actually called
    with; never touches a real provider/network/filesystem asset."""

    last_order: list = []

    def __init__(self, *args, **kwargs):
        pass

    def resolve_all(self, scene_rows, **kwargs):
        _FakeAssetManager.last_order = [s.scene_number for s in scene_rows]
        return _FakeSummary()


class TestAcquisitionOrdering(unittest.TestCase):
    def test_resolve_scene_assets_orders_stock_video_flow_image_stock_image_flow_video(self):
        rows = [
            {"scene_number": "1", "script_segment": "a", "asset_type": "video", "prompt": "p1"},
            {"scene_number": "2", "script_segment": "b", "asset_type": "stock_video", "prompt": "p2"},
            {"scene_number": "3", "script_segment": "c", "asset_type": "image", "prompt": "p3"},
            {"scene_number": "4", "script_segment": "d", "asset_type": "stock_image", "prompt": "p4"},
        ]
        with patch("asset_manager.AssetManager", _FakeAssetManager), \
             patch("providers.flow.provider.FlowProvider"), \
             patch("providers.stock.pexels.build_pexels_provider", return_value=object()):
            vg.resolve_scene_assets(
                rows, Path("/tmp/does-not-matter"),
                pexels_api_key="fake-key", flow_engine_manager=object(),
            )
        self.assertEqual(_FakeAssetManager.last_order, ["2", "3", "4", "1"])

    def test_ordering_is_stable_within_the_same_tier(self):
        rows = [
            {"scene_number": "1", "script_segment": "a", "asset_type": "stock_video", "prompt": "p1"},
            {"scene_number": "2", "script_segment": "b", "asset_type": "stock_video", "prompt": "p2"},
            {"scene_number": "3", "script_segment": "c", "asset_type": "stock_video", "prompt": "p3"},
        ]
        with patch("asset_manager.AssetManager", _FakeAssetManager), \
             patch("providers.stock.pexels.build_pexels_provider", return_value=object()):
            vg.resolve_scene_assets(rows, Path("/tmp/does-not-matter"), pexels_api_key="fake-key")
        self.assertEqual(_FakeAssetManager.last_order, ["1", "2", "3"])

    def test_other_asset_types_are_unaffected_and_kept_in_relative_order(self):
        rows = [
            {"scene_number": "1", "script_segment": "a", "asset_type": "youtube_video", "prompt": "q1"},
            {"scene_number": "2", "script_segment": "b", "asset_type": "stock_video", "prompt": "p2"},
            {"scene_number": "3", "script_segment": "c", "asset_type": "youtube_video", "prompt": "q3"},
        ]
        with patch("asset_manager.AssetManager", _FakeAssetManager), \
             patch("providers.stock.pexels.build_pexels_provider", return_value=object()), \
             patch("providers.youtube.base.YouTubeProvider"), \
             patch("providers.youtube.ytdlp_backend.YtDlpBackend"):
            vg.resolve_scene_assets(rows, Path("/tmp/does-not-matter"), pexels_api_key="fake-key")
        self.assertEqual(_FakeAssetManager.last_order, ["2", "1", "3"])


if __name__ == "__main__":
    unittest.main()
