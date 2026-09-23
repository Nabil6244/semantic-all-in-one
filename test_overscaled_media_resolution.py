"""Tests for scene_graph/media_resolution.py — proves Overscaled nodes route
through the EXISTING resolve_scene_assets()/find_image_for_scene() machinery
(video_generator.py), not a second provider implementation.

Uses only the LOCAL provider path (no network) — Flow/Pexels/YouTube routing
is exercised by the EXISTING test suite for resolve_scene_assets/SceneRow;
this file only proves the Overscaled adapter feeds that same function
correctly and reads its output back correctly.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.media_resolution import resolve_scene_graph_media
from scene_graph.overscaled_csv import compile_overscaled_csv


class TestMediaResolutionReusesExistingSystem(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images_dir = self.tmp / "images"
        self.images_dir.mkdir()

    def test_local_asset_resolves_via_existing_find_image_for_scene(self):
        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image", "asset_type": "local"}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(result.ok, result.errors)
        Image.new("RGB", (64, 64), (10, 20, 30)).save(self.images_dir / "001.png")

        resolved = resolve_scene_graph_media(result.scene_graph, images_dir=self.images_dir)
        self.assertEqual(resolved, {"n1": str(self.images_dir / "001.png")})

    def test_node_without_asset_info_is_skipped_not_crashed(self):
        rows = [{"scene_number": "1", "script_segment": "just narration"}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        resolved = resolve_scene_graph_media(result.scene_graph, images_dir=self.images_dir)
        self.assertEqual(resolved, {})

    def test_unresolvable_local_asset_fails_loudly_like_the_existing_pipeline(self):
        # This is EXISTING, unmodified resolve_scene_assets() behavior (a
        # hard sys.exit with a specific reason) — the Overscaled adapter
        # must not swallow or soften it; scene_graph.app_integration is
        # responsible for catching this at the UI-worker boundary.
        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image", "asset_type": "local"}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        with self.assertRaises(SystemExit):
            resolve_scene_graph_media(result.scene_graph, images_dir=self.images_dir)

    def test_asset_source_is_preserved_verbatim_into_the_row_sent_downstream(self):
        # Confirms we never rewrite asset_type -> semantic_role or vice versa
        # when building the row resolve_scene_assets consumes.
        rows = [{
            "scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "diagram",
            "role": "design_flaw", "asset_type": "local", "prompt": "",
        }]
        result = compile_overscaled_csv(rows, segment_id="seg")
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.asset_source, "local")
        self.assertEqual(node.semantic_role, "design_flaw")
        Image.new("RGB", (32, 32), (1, 2, 3)).save(self.images_dir / "001.png")
        resolved = resolve_scene_graph_media(result.scene_graph, images_dir=self.images_dir)
        self.assertIn("n1", resolved)

    def test_scene_number_metadata_is_stashed_for_resolution_routing(self):
        rows = [{"scene_number": "42", "script_segment": "x", "node_id": "n1", "node_type": "image", "asset_type": "local"}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertEqual(result.scene_graph.nodes[0].metadata.get("scene_number"), "42")


if __name__ == "__main__":
    unittest.main()
