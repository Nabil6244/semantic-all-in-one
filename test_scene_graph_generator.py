"""Regression tests for scene_graph/generator.py (Phase 2: CSV -> SceneGraph).

Pure data-transform logic — no network, no real Gemini calls. Uses
visual_director.llm.StaticLLM (the project's own existing test double) to
fake model responses.
"""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

from providers.base import SceneRow
from visual_director.llm import LLMError, StaticLLM

from scene_graph import SceneGraph
from scene_graph.generator import (
    generate_scene_graph,
    generate_scene_graph_heuristic,
    generate_scene_graph_with_llm,
    scene_rows_from_csv_rows,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "ai_visual_plan.csv"


def _rows(*tuples):
    """tuples of (scene_number, script_segment, asset_type, prompt)."""
    return [
        SceneRow.from_csv_row(
            {"scene_number": sn, "script_segment": seg, "asset_type": at, "prompt": pr}
        )
        for sn, seg, at, pr in tuples
    ]


class TestExistingCsvToSceneGraphMapping(unittest.TestCase):
    def test_csv_dict_rows_map_to_scene_graph(self):
        raw_rows = [
            {"scene_number": "1", "script_segment": "A quiet frozen world.", "asset_type": "image", "prompt": "pluto ice"},
            {"scene_number": "2", "script_segment": "It keeps itself warm somehow.", "asset_type": "video", "prompt": "pluto glow"},
        ]
        rows = scene_rows_from_csv_rows(raw_rows)
        result = generate_scene_graph_heuristic("seg1", rows)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.scene_graph.nodes), 2)

    def test_existing_csv_parser_unchanged_end_to_end(self):
        # Exactly how video_generator.py's main() already reads the CSV —
        # csv.DictReader is never touched by this feature.
        with open(FIXTURE_CSV, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            raw_rows = list(reader)
        self.assertGreater(len(raw_rows), 0)
        self.assertIn("scene_number", raw_rows[0])
        self.assertIn("script_segment", raw_rows[0])
        self.assertIn("asset_type", raw_rows[0])
        self.assertIn("prompt", raw_rows[0])
        rows = [SceneRow.from_csv_row(r) for r in raw_rows]
        result = generate_scene_graph_heuristic("pluto_fixture", rows, title="Pluto")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.scene_graph.beats), len(raw_rows))


class TestAssetTypeSourcePreservation(unittest.TestCase):
    def test_asset_source_matches_original_csv_value_exactly(self):
        rows = _rows(
            ("1", "Establishing shot.", "image", "a wide shot"),
            ("2", "A closer look.", "stock_video", "closeup search"),
            ("3", "Archive footage.", "youtube_video", "archive clip"),
        )
        result = generate_scene_graph_heuristic("seg", rows)
        self.assertTrue(result.ok, result.errors)
        sources = {n.asset_source for n in result.scene_graph.nodes}
        self.assertEqual(sources, {"image", "stock_video", "youtube_video"})

    def test_asset_type_to_node_type_mapping(self):
        rows = _rows(
            ("1", "Image one.", "image", "p"),
            ("2", "Video one.", "video", "p"),
            ("3", "Stock image.", "stock_image", "p"),
            ("4", "Stock video.", "stock_video", "p"),
            ("5", "Youtube clip.", "youtube_video", "p"),
        )
        result = generate_scene_graph_heuristic("seg", rows)
        by_source = {n.asset_source: n.type for n in result.scene_graph.nodes}
        self.assertEqual(by_source["image"], "image")
        self.assertEqual(by_source["video"], "video_loop")
        self.assertEqual(by_source["stock_image"], "image")
        self.assertEqual(by_source["stock_video"], "video_loop")
        self.assertEqual(by_source["youtube_video"], "video_loop")


class TestSemanticRoleSeparation(unittest.TestCase):
    def test_semantic_role_is_never_the_asset_source_value(self):
        rows = _rows(("1", "Just a normal sentence about ships.", "image", "a ship"))
        result = generate_scene_graph_heuristic("seg", rows)
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.asset_source, "image")
        self.assertNotEqual(node.semantic_role, "image")

    def test_first_row_gets_title_role(self):
        rows = _rows(
            ("1", "The Vasa was designed to carry massive firepower.", "image", "warship"),
            ("2", "It sailed for the first time in 1628.", "video", "sailing"),
        )
        result = generate_scene_graph_heuristic("vasa", rows)
        self.assertEqual(result.scene_graph.nodes[0].semantic_role, "title")


class TestCaptionGenerationAndValidation(unittest.TestCase):
    def test_generated_caption_is_valid(self):
        rows = _rows(("1", "The hull was too narrow for its height.", "diagram", "hull cross section"))
        result = generate_scene_graph_heuristic("vasa", rows)
        self.assertTrue(result.ok, result.errors)
        node = result.scene_graph.nodes[0]
        self.assertIsNotNone(node.caption)
        self.assertEqual(node.caption.validate(), [])

    def test_design_flaw_caption_highlights_the_flaw_keyword(self):
        rows = _rows(("1", "But the hull was too narrow to support the deck.", "diagram", "hull"))
        result = generate_scene_graph_heuristic("vasa", rows)
        node = result.scene_graph.nodes[0]
        self.assertEqual(node.semantic_role, "design_flaw")
        self.assertIsNotNone(node.caption.highlight)
        self.assertIn(node.caption.highlight.lower(), node.caption.text.lower())


class TestEdgeGeneration(unittest.TestCase):
    def test_design_flaw_to_consequence_edge_is_created(self):
        rows = _rows(
            ("1", "The Vasa was designed to carry massive firepower.", "image", "warship"),
            ("2", "But the hull was too narrow to support the upper structure.", "diagram", "hull flaw"),
            ("3", "The ship capsized minutes after launch.", "image", "sinking ship"),
        )
        result = generate_scene_graph_heuristic("vasa", rows)
        self.assertTrue(result.ok, result.errors)
        sg = result.scene_graph
        self.assertEqual(len(sg.edges), 1)
        flaw_node = next(n for n in sg.nodes if n.semantic_role == "design_flaw")
        consequence_node = next(n for n in sg.nodes if n.semantic_role == "consequence")
        edge = sg.edges[0]
        self.assertEqual(edge.from_node, flaw_node.id)
        self.assertEqual(edge.to_node, consequence_node.id)


class TestMultipleActionsInOneBeat(unittest.TestCase):
    def test_consequence_beat_reveals_node_and_draws_edge_and_moves_camera(self):
        rows = _rows(
            ("1", "The Vasa was built to impress the king.", "image", "warship"),
            ("2", "But the hull was too narrow for the upper decks.", "diagram", "hull flaw"),
            ("3", "It sank within the hour.", "image", "sinking"),
        )
        result = generate_scene_graph_heuristic("vasa", rows)
        consequence_beat = result.scene_graph.beats[2]
        action_types = [a.type for a in consequence_beat.actions]
        self.assertIn("reveal_node", action_types)
        self.assertIn("draw_edge", action_types)
        self.assertIn("move_camera", action_types)
        self.assertGreaterEqual(len(consequence_beat.actions), 3)

    def test_row_with_no_asset_info_has_no_visual_actions(self):
        rows = _rows(("1", "Just narration, no visual.", "", ""))
        result = generate_scene_graph_heuristic("seg", rows)
        self.assertEqual(result.scene_graph.beats[0].actions, [])
        self.assertEqual(result.scene_graph.nodes, [])


class TestCameraIntentWithoutPixelCoordinates(unittest.TestCase):
    def test_camera_keyframes_reference_nodes_symbolically(self):
        rows = _rows(("1", "A wide establishing shot.", "image", "wide shot"))
        result = generate_scene_graph_heuristic("seg", rows)
        kf = result.scene_graph.camera_keyframes[0]
        self.assertEqual(kf.frame_nodes, [result.scene_graph.nodes[0].id])
        self.assertIsNone(kf.position)
        d = kf.to_dict()
        self.assertNotIn("x", d)
        self.assertNotIn("y", d)


class TestValidModelJsonToSceneGraph(unittest.TestCase):
    def test_valid_llm_json_is_accepted(self):
        payload = {
            "segment_id": "vasa",
            "title": "Vasa",
            "style_preset": "overscaled",
            "duration": 10.0,
            "nodes": [
                {"id": "n1", "type": "image", "semantic_role": "establisher",
                 "asset_source": "image", "asset_reference": "ship", "appear_at": 0.0},
                {"id": "n2", "type": "diagram", "semantic_role": "design_flaw",
                 "asset_source": "image", "asset_reference": "hull",
                 "appear_at": 5.0,
                 "caption": {"text": "Too narrow for its height", "highlight": "Too narrow"}},
            ],
            "edges": [
                {"id": "e1", "from": "n1", "to": "n2", "style": "hand_drawn", "draw_at": 6.0, "duration": 1.0},
            ],
            "camera_keyframes": [
                {"keyframe_id": "c1", "at": 0.0, "frame_nodes": ["n1"], "zoom": 1.0},
            ],
            "beats": [
                {"beat_id": "b1", "narration": "Intro.", "start": 0.0, "end": 5.0,
                 "actions": [{"type": "reveal_node", "action_id": "a1", "node_id": "n1"}]},
            ],
        }
        llm = StaticLLM(json.dumps(payload))
        result = generate_scene_graph_with_llm("vasa", _rows(("1", "x", "image", "p")), llm=llm)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.source, "llm")
        self.assertIsInstance(result.scene_graph, SceneGraph)
        self.assertEqual(len(result.scene_graph.nodes), 2)


class TestInvalidModelJsonRejection(unittest.TestCase):
    def test_non_json_response_is_rejected(self):
        llm = StaticLLM("this is not json at all")
        result = generate_scene_graph_with_llm("seg", _rows(("1", "x", "image", "p")), llm=llm)
        self.assertFalse(result.ok)
        self.assertIsNone(result.scene_graph)
        self.assertTrue(any("valid JSON" in e for e in result.errors))

    def test_json_array_instead_of_object_is_rejected(self):
        llm = StaticLLM("[1, 2, 3]")
        result = generate_scene_graph_with_llm("seg", _rows(("1", "x", "image", "p")), llm=llm)
        self.assertFalse(result.ok)

    def test_semantically_invalid_scene_graph_is_rejected(self):
        # Valid JSON, but an edge references a node that does not exist —
        # must be rejected, not silently accepted.
        payload = {
            "segment_id": "seg",
            "nodes": [{"id": "n1", "type": "image"}],
            "edges": [{"id": "e1", "from": "n1", "to": "ghost", "draw_at": 0.0, "duration": 1.0}],
        }
        llm = StaticLLM(json.dumps(payload))
        result = generate_scene_graph_with_llm("seg", _rows(("1", "x", "image", "p")), llm=llm)
        self.assertFalse(result.ok)
        self.assertTrue(any("does not exist" in e for e in result.errors))


class TestMissingRequiredModelFields(unittest.TestCase):
    def test_missing_segment_id_is_rejected(self):
        payload = {"nodes": [{"id": "n1", "type": "image"}]}
        llm = StaticLLM(json.dumps(payload))
        result = generate_scene_graph_with_llm("seg", _rows(("1", "x", "image", "p")), llm=llm)
        self.assertFalse(result.ok)
        self.assertTrue(any("segment_id is required" in e for e in result.errors))

    def test_invalid_caption_highlight_is_rejected(self):
        payload = {
            "segment_id": "seg",
            "nodes": [
                {"id": "n1", "type": "image", "caption": {"text": "hello world", "highlight": "not present"}}
            ],
        }
        llm = StaticLLM(json.dumps(payload))
        result = generate_scene_graph_with_llm("seg", _rows(("1", "x", "image", "p")), llm=llm)
        self.assertFalse(result.ok)
        self.assertTrue(any("substring" in e for e in result.errors))


class TestDeterministicFakeProviderGeneration(unittest.TestCase):
    def test_same_input_produces_identical_output(self):
        rows = _rows(
            ("1", "The Vasa was built to impress the king.", "image", "warship"),
            ("2", "But the hull was too narrow.", "diagram", "hull"),
        )
        r1 = generate_scene_graph_heuristic("vasa", rows)
        r2 = generate_scene_graph_heuristic("vasa", rows)
        self.assertEqual(r1.scene_graph.to_dict(), r2.scene_graph.to_dict())

    def test_static_llm_records_the_prompt_it_was_given(self):
        payload = {"segment_id": "seg", "nodes": []}
        llm = StaticLLM(json.dumps(payload))
        generate_scene_graph_with_llm("seg", _rows(("1", "hello narration", "image", "p")), llm=llm)
        self.assertEqual(len(llm.calls), 1)
        system, user = llm.calls[0]
        self.assertIn("Overscaled", system)
        self.assertIn("hello narration", user)


class TestProviderFailureDoesNotAffectExistingPipeline(unittest.TestCase):
    class _RaisingLLM:
        def complete(self, system: str, user: str) -> str:
            raise LLMError("simulated network failure")

    def test_llm_error_falls_back_to_heuristic_without_raising(self):
        rows = _rows(
            ("1", "The Vasa was built to impress the king.", "image", "warship"),
            ("2", "But the hull was too narrow.", "diagram", "hull"),
        )
        result = generate_scene_graph(
            "vasa", rows, llm=self._RaisingLLM()
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "heuristic_fallback_after_llm_failure")
        self.assertTrue(any("simulated network failure" in e for e in result.errors))
        # Falls back to exactly what the pure heuristic path would produce.
        heuristic_only = generate_scene_graph_heuristic("vasa", rows)
        self.assertEqual(result.scene_graph.to_dict(), heuristic_only.scene_graph.to_dict())

    def test_no_llm_supplied_uses_heuristic_directly(self):
        rows = _rows(("1", "A calm narration line.", "image", "p"))
        result = generate_scene_graph("seg", rows)
        self.assertEqual(result.source, "heuristic")
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
