"""Tests for the dedicated Overscaled CSV contract (scene_graph/overscaled_csv.py).

Confirms the NEW schema is fully separate from, and never modifies, the
EXISTING normal CSV contract (providers.base.SceneRow / csv.DictReader
usage in video_generator.py) — see TestNormalCsvUnaffected below.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from providers.base import SceneRow
from scene_graph.overscaled_csv import compile_overscaled_csv

FIXTURE = Path(__file__).resolve().parent / "overscaled_sample.csv"


def _read_fixture():
    with open(FIXTURE, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class TestValidOverscaledCsvParses(unittest.TestCase):
    def test_sample_fixture_compiles(self):
        result = compile_overscaled_csv(_read_fixture(), segment_id="aurora_bridge", title="The Aurora Bridge")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.validate(), [])

    def test_minimal_valid_rows(self):
        rows = [{"scene_number": "1", "script_segment": "Just narration."}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.nodes, [])


class TestInvalidRequiredFieldsFail(unittest.TestCase):
    def test_empty_csv_fails(self):
        result = compile_overscaled_csv([], segment_id="seg")
        self.assertFalse(result.ok)
        self.assertTrue(any("no rows" in e for e in result.errors))

    def test_missing_required_column_fails(self):
        rows = [{"scene_number": "1"}]  # no script_segment column at all
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertFalse(result.ok)
        self.assertTrue(any("script_segment" in e for e in result.errors))

    def test_invalid_caption_highlight_fails_validation(self):
        rows = [{
            "scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image",
            "asset_type": "flow_image", "caption": "hello world", "highlight": "not present",
        }]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertFalse(result.ok)
        self.assertTrue(any("substring" in e for e in result.errors))


class TestDuplicateNodeIdsFailWhenConflicting(unittest.TestCase):
    def test_redefining_same_node_id_with_new_data_fails(self):
        rows = [
            {"scene_number": "1", "script_segment": "a", "node_id": "n1", "node_type": "image", "asset_type": "flow_image"},
            {"scene_number": "2", "script_segment": "b", "node_id": "n1", "node_type": "diagram", "asset_type": "flow_image"},
        ]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertFalse(result.ok)
        self.assertTrue(any("conflicting redefinition" in e for e in result.errors))

    def test_referencing_same_node_id_without_new_data_is_fine(self):
        rows = [
            {"scene_number": "1", "script_segment": "a", "node_id": "n1", "node_type": "image", "asset_type": "flow_image"},
            {"scene_number": "2", "script_segment": "b", "camera_action": "focus", "camera_target": "n1"},
        ]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.scene_graph.nodes), 1)
        self.assertEqual(len(result.scene_graph.camera_keyframes), 1)


class TestAssetTypesPreserved(unittest.TestCase):
    def test_asset_type_column_copied_verbatim_and_kept_separate_from_role(self):
        rows = [{
            "scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "video_loop",
            "role": "consequence", "asset_type": "flow_video", "prompt": "engine smoking",
        }]
        result = compile_overscaled_csv(rows, segment_id="seg")
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.asset_source, "flow_video")
        self.assertEqual(node.semantic_role, "consequence")
        self.assertEqual(node.asset_reference, "engine smoking")
        self.assertNotEqual(node.asset_source, node.semantic_role)

    def test_supported_asset_types_from_spec(self):
        for asset_type in ("flow_image", "flow_video", "stock_image", "stock_video", "youtube_video"):
            rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image", "asset_type": asset_type}]
            result = compile_overscaled_csv(rows, segment_id="seg")
            self.assertTrue(result.ok, result.errors)
            self.assertEqual(result.scene_graph.nodes[0].asset_source, asset_type)


class TestCausalEdgesAndCameraAndMultiActionBeats(unittest.TestCase):
    def test_explicit_edges_only_from_csv_columns(self):
        result = compile_overscaled_csv(_read_fixture(), segment_id="seg")
        sg = result.scene_graph
        self.assertEqual(len(sg.edges), 2)
        self.assertEqual({(e.from_node, e.to_node) for e in sg.edges}, {("n3", "n4"), ("n4", "n5")})
        self.assertEqual(sg.edges[0].metadata.get("label"), "caused the deck to resonate")

    def test_camera_action_and_target_produce_keyframe(self):
        rows = [{
            "scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image",
            "asset_type": "flow_image", "camera_action": "focus", "camera_target": "n1",
        }]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertEqual(len(result.scene_graph.camera_keyframes), 1)
        self.assertEqual(result.scene_graph.camera_keyframes[0].frame_nodes, ["n1"])

    def test_row_with_node_edge_and_camera_is_one_multi_action_beat(self):
        result = compile_overscaled_csv(_read_fixture(), segment_id="seg")
        beat5 = next(b for b in result.scene_graph.beats if b.beat_id == "beat_5")
        self.assertEqual(sorted(a.type for a in beat5.actions), ["draw_edge", "move_camera", "reveal_node"])


class TestChapterTitleColumn(unittest.TestCase):
    def test_chapter_title_column_produces_a_title_cue(self):
        rows = [
            {"scene_number": "1", "script_segment": "The Vasa was a warship.", "node_id": "n1",
             "node_type": "image", "asset_type": "flow_image", "chapter_title": "Vasa"},
            {"scene_number": "2", "script_segment": "It sank on its maiden voyage.", "node_id": "n2",
             "node_type": "image", "asset_type": "flow_image"},
        ]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.scene_graph.title_cues), 1)
        self.assertEqual(result.scene_graph.title_cues[0].text, "Vasa")
        self.assertEqual(result.scene_graph.title_cues[0].at, 0.0)

    def test_blank_chapter_title_produces_no_cue(self):
        rows = [
            {"scene_number": "1", "script_segment": "No title here.", "node_id": "n1",
             "node_type": "image", "asset_type": "flow_image", "chapter_title": ""},
        ]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertEqual(result.scene_graph.title_cues, [])

    def test_multiple_chapter_titles_produce_multiple_cues_in_order(self):
        rows = [
            {"scene_number": "1", "script_segment": "First ship intro here now.", "node_id": "n1",
             "node_type": "image", "asset_type": "flow_image", "chapter_title": "Vasa"},
            {"scene_number": "2", "script_segment": "Second ship intro right here.", "node_id": "n2",
             "node_type": "image", "asset_type": "flow_image", "chapter_title": "HMS Captain"},
        ]
        result = compile_overscaled_csv(rows, segment_id="seg")
        self.assertEqual([c.text for c in result.scene_graph.title_cues], ["Vasa", "HMS Captain"])
        self.assertLess(result.scene_graph.title_cues[0].at, result.scene_graph.title_cues[1].at)

    def test_sample_fixture_has_no_chapter_titles_and_still_compiles(self):
        # Backward compatibility: the existing sample fixture predates this
        # column and must keep compiling exactly as before.
        result = compile_overscaled_csv(_read_fixture(), segment_id="seg")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.title_cues, [])


class TestNormalCsvUnaffected(unittest.TestCase):
    """The existing normal CSV contract/parser must not notice this feature exists."""

    def test_existing_scene_row_parsing_is_untouched(self):
        row = {"scene_number": "1", "script_segment": "hello", "asset_type": "video", "prompt": "a shot"}
        scene_row = SceneRow.from_csv_row(row)
        self.assertEqual(scene_row.asset_type, "video")
        self.assertEqual(scene_row.prompt, "a shot")

    def test_normal_csv_has_no_overscaled_columns_and_still_works(self):
        # A plain normal-format CSV row has none of the Overscaled columns —
        # SceneRow.from_csv_row must not care, and never will, since this
        # module never touches providers/base.py.
        row = {"scene_number": "1", "script_segment": "hello", "asset_type": "image", "prompt": "a photo"}
        self.assertNotIn("node_id", row)
        scene_row = SceneRow.from_csv_row(row)
        self.assertEqual(scene_row.scene_number, "1")


if __name__ == "__main__":
    unittest.main()
