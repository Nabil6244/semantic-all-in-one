"""Regression tests for the Overscaled scene_graph/ foundation (Phase 1).

Pure data-model tests — no Tk, no ffmpeg, no network. Mirrors the style of
test_editorial_timeline_edit.py.
"""

from __future__ import annotations

import json
import unittest

from scene_graph import (
    CameraKeyframe,
    CaptionSpec,
    SceneEdge,
    SceneGraph,
    SceneGraphAction,
    SceneGraphBeat,
    SceneNode,
    StylePreset,
    clear_style_preset_cache,
    load_style_preset,
    style_presets_by_id,
)


def _sample_graph() -> SceneGraph:
    return SceneGraph(
        segment_id="vasa",
        title="Vasa",
        style_preset="overscaled",
        duration=30.0,
        nodes=[
            SceneNode(
                id="n1",
                type="anchor",
                semantic_role="anchor",
                asset_source="flow_image",
                asset_reference="ship_model_silhouette",
                appear_at=0.0,
            ),
            SceneNode(
                id="n2",
                type="image",
                semantic_role="establisher",
                asset_source="flow_image",
                asset_reference="vasa_full_ship.png",
                appear_at=2.5,
            ),
            SceneNode(
                id="n3",
                type="diagram",
                semantic_role="design_flaw",
                asset_source="flow_image",
                asset_reference="hull_cross_section.png",
                appear_at=14.0,
                caption=CaptionSpec(
                    text="Its fundamental problem was that it was too narrow for its height",
                    highlight="too narrow",
                ),
            ),
        ],
        edges=[
            SceneEdge(id="e1", from_node="n2", to_node="n3", style="hand_drawn", draw_at=20.5),
        ],
        camera_keyframes=[
            CameraKeyframe(keyframe_id="c1", at=0.0, frame_nodes=["n1"], zoom=1.0),
            CameraKeyframe(keyframe_id="c2", at=12.0, frame_nodes=["n2"], zoom=1.3),
        ],
        beats=[
            SceneGraphBeat(
                beat_id="b07",
                narration="The hull could not support the upper structure.",
                start=20.0,
                end=23.0,
                actions=[
                    SceneGraphAction(type="reveal_node", action_id="a1", node_id="n3"),
                    SceneGraphAction(type="draw_edge", action_id="a2", edge_id="e1"),
                ],
            ),
        ],
    )


class TestSceneGraphConstruction(unittest.TestCase):
    def test_construction_is_valid(self):
        sg = _sample_graph()
        self.assertEqual(sg.validate(), [])
        self.assertTrue(sg.is_valid())

    def test_missing_optional_fields_default_safely(self):
        sg = SceneGraph(segment_id="minimal")
        self.assertEqual(sg.nodes, [])
        self.assertEqual(sg.edges, [])
        self.assertEqual(sg.camera_keyframes, [])
        self.assertEqual(sg.beats, [])
        self.assertEqual(sg.validate(), [])


class TestSceneNodeSerialization(unittest.TestCase):
    def test_round_trip(self):
        node = SceneNode(
            id="n1",
            type="video_loop",
            semantic_role="consequence",
            asset_source="flow_video",
            asset_reference="ship_sinking.mp4",
            appear_at=5.0,
            duration=4.0,
            caption=CaptionSpec(text="The ship sank in 32 meters of water", highlight="32 meters"),
        )
        restored = SceneNode.from_dict(node.to_dict())
        self.assertEqual(restored.to_dict(), node.to_dict())
        self.assertEqual(restored.semantic_role, "consequence")
        self.assertEqual(restored.asset_source, "flow_video")

    def test_asset_source_and_semantic_role_are_independent(self):
        node = SceneNode(id="n1", asset_source="flow_image", semantic_role="design_flaw")
        d = node.to_dict()
        self.assertEqual(d["asset_source"], "flow_image")
        self.assertEqual(d["semantic_role"], "design_flaw")
        self.assertNotEqual(d["asset_source"], d["semantic_role"])


class TestSceneEdgeSerialization(unittest.TestCase):
    def test_round_trip_uses_from_to_keys(self):
        edge = SceneEdge(id="e1", from_node="n2", to_node="n3", color="#c0392b", draw_at=20.5)
        d = edge.to_dict()
        self.assertEqual(d["from"], "n2")
        self.assertEqual(d["to"], "n3")
        restored = SceneEdge.from_dict(d)
        self.assertEqual(restored.from_node, "n2")
        self.assertEqual(restored.to_node, "n3")
        self.assertEqual(restored.to_dict(), d)


class TestSceneGraphRoundTrip(unittest.TestCase):
    def test_full_round_trip_via_json(self):
        sg = _sample_graph()
        blob = json.dumps(sg.to_dict())
        restored = SceneGraph.from_dict(json.loads(blob))
        self.assertEqual(restored.to_dict(), sg.to_dict())
        self.assertEqual(restored.validate(), [])

    def test_deterministic_serialization(self):
        sg = _sample_graph()
        self.assertEqual(sg.to_dict(), sg.to_dict())
        d1 = json.dumps(sg.to_dict(), sort_keys=True)
        d2 = json.dumps(SceneGraph.from_dict(sg.to_dict()).to_dict(), sort_keys=True)
        self.assertEqual(d1, d2)


class TestCaptionHighlightValidation(unittest.TestCase):
    def test_valid_highlight(self):
        cap = CaptionSpec(text="The hull was too narrow", highlight="too narrow")
        self.assertEqual(cap.validate(), [])

    def test_no_highlight_is_allowed(self):
        cap = CaptionSpec(text="The hull was too narrow", highlight=None)
        self.assertEqual(cap.validate(), [])

    def test_highlight_not_a_substring_fails(self):
        cap = CaptionSpec(text="The hull was too narrow", highlight="too wide")
        errors = cap.validate()
        self.assertTrue(any("substring" in e for e in errors))

    def test_empty_text_fails(self):
        cap = CaptionSpec(text="", highlight=None)
        errors = cap.validate()
        self.assertTrue(any("text is required" in e for e in errors))


class TestInvalidEdgeReference(unittest.TestCase):
    def test_edge_to_nonexistent_node_fails(self):
        sg = _sample_graph()
        sg.edges.append(SceneEdge(id="e2", from_node="n1", to_node="does_not_exist", draw_at=1.0))
        errors = sg.validate()
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_edge_from_nonexistent_node_fails(self):
        sg = _sample_graph()
        sg.edges.append(SceneEdge(id="e3", from_node="ghost", to_node="n1", draw_at=1.0))
        errors = sg.validate()
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_duplicate_edge_ids_fail(self):
        sg = _sample_graph()
        sg.edges.append(SceneEdge(id="e1", from_node="n1", to_node="n2", draw_at=1.0))
        errors = sg.validate()
        self.assertTrue(any("duplicate SceneEdge id" in e for e in errors))


class TestCameraKeyframeValidation(unittest.TestCase):
    def test_negative_at_fails(self):
        kf = CameraKeyframe(keyframe_id="c1", at=-1.0, zoom=1.0)
        self.assertTrue(any("at must be" in e for e in kf.validate()))

    def test_zero_zoom_fails(self):
        kf = CameraKeyframe(keyframe_id="c1", at=0.0, zoom=0.0)
        self.assertTrue(any("zoom must be" in e for e in kf.validate()))

    def test_non_monotonic_camera_timing_fails(self):
        sg = _sample_graph()
        sg.camera_keyframes = [
            CameraKeyframe(keyframe_id="c1", at=10.0, frame_nodes=["n1"], zoom=1.0),
            CameraKeyframe(keyframe_id="c2", at=5.0, frame_nodes=["n2"], zoom=1.0),
        ]
        errors = sg.validate()
        self.assertTrue(any("strictly increasing" in e for e in errors))


class TestCameraNodeReferenceValidation(unittest.TestCase):
    def test_camera_keyframe_referencing_unknown_node_fails(self):
        sg = _sample_graph()
        sg.camera_keyframes.append(
            CameraKeyframe(keyframe_id="c3", at=25.0, frame_nodes=["ghost_node"], zoom=1.0)
        )
        errors = sg.validate()
        self.assertTrue(any("unknown node" in e for e in errors))


class TestBeatActionSerialization(unittest.TestCase):
    def test_beat_round_trip(self):
        beat = SceneGraphBeat(
            beat_id="b07",
            narration="The hull could not support the upper structure.",
            start=20.0,
            end=23.0,
            actions=[SceneGraphAction(type="reveal_node", action_id="a1", node_id="n4")],
        )
        restored = SceneGraphBeat.from_dict(beat.to_dict())
        self.assertEqual(restored.to_dict(), beat.to_dict())

    def test_multiple_actions_in_one_beat(self):
        beat = SceneGraphBeat(
            beat_id="b07",
            start=20.0,
            end=23.0,
            actions=[
                SceneGraphAction(type="reveal_node", action_id="a1", node_id="n4"),
                SceneGraphAction(type="draw_edge", action_id="a2", edge_id="e3"),
                SceneGraphAction(type="move_camera", action_id="a3", camera_keyframe_id="c2"),
            ],
        )
        self.assertEqual(len(beat.actions), 3)
        restored = SceneGraphBeat.from_dict(beat.to_dict())
        self.assertEqual(len(restored.actions), 3)
        self.assertEqual([a.type for a in restored.actions], ["reveal_node", "draw_edge", "move_camera"])


class TestActionReferenceValidation(unittest.TestCase):
    def test_reveal_node_missing_node_id_fails_self_validation(self):
        action = SceneGraphAction(type="reveal_node", action_id="a1")
        self.assertTrue(any("requires node_id" in e for e in action.validate()))

    def test_draw_edge_referencing_unknown_edge_fails_graph_validation(self):
        sg = _sample_graph()
        sg.beats[0].actions.append(
            SceneGraphAction(type="draw_edge", action_id="a9", edge_id="ghost_edge")
        )
        errors = sg.validate()
        self.assertTrue(any("edge_id 'ghost_edge' does not exist" in e for e in errors))

    def test_reveal_node_referencing_unknown_node_fails_graph_validation(self):
        sg = _sample_graph()
        sg.beats[0].actions.append(
            SceneGraphAction(type="reveal_node", action_id="a9", node_id="ghost_node")
        )
        errors = sg.validate()
        self.assertTrue(any("node_id 'ghost_node' does not exist" in e for e in errors))

    def test_move_camera_referencing_unknown_keyframe_fails(self):
        sg = _sample_graph()
        sg.beats[0].actions.append(
            SceneGraphAction(type="move_camera", action_id="a9", camera_keyframe_id="ghost_kf")
        )
        errors = sg.validate()
        self.assertTrue(any("camera_keyframe_id 'ghost_kf' does not exist" in e for e in errors))

    def test_set_caption_requires_caption(self):
        action = SceneGraphAction(type="set_caption", action_id="a1", node_id="n1")
        self.assertTrue(any("requires a caption" in e for e in action.validate()))


class TestBeatTimingValidation(unittest.TestCase):
    def test_end_before_start_fails(self):
        beat = SceneGraphBeat(beat_id="b1", start=5.0, end=3.0)
        self.assertTrue(any("end must be greater than start" in e for e in beat.validate()))

    def test_beat_exceeding_segment_duration_fails(self):
        sg = _sample_graph()
        sg.duration = 21.0  # b07 ends at 23.0 > 21.0
        errors = sg.validate()
        self.assertTrue(any("exceeds segment duration" in e for e in errors))


class TestMalformedRequiredFields(unittest.TestCase):
    def test_empty_segment_id_fails(self):
        sg = SceneGraph(segment_id="")
        self.assertTrue(any("segment_id is required" in e for e in sg.validate()))

    def test_empty_node_id_fails(self):
        node = SceneNode(id="")
        self.assertTrue(any("SceneNode.id is required" in e for e in node.validate()))

    def test_duplicate_node_ids_fail(self):
        sg = _sample_graph()
        sg.nodes.append(SceneNode(id="n1", type="image"))
        errors = sg.validate()
        self.assertTrue(any("duplicate SceneNode id" in e for e in errors))


class TestBackwardCompatibleFromDict(unittest.TestCase):
    def test_from_dict_tolerates_missing_keys(self):
        sg = SceneGraph.from_dict({"segment_id": "old_project"})
        self.assertEqual(sg.segment_id, "old_project")
        self.assertEqual(sg.nodes, [])
        self.assertEqual(sg.validate(), [])

    def test_from_dict_tolerates_none(self):
        sg = SceneGraph.from_dict(None)
        self.assertEqual(sg.segment_id, "")
        self.assertEqual(sg.nodes, [])

    def test_from_dict_ignores_unknown_extra_keys(self):
        sg = SceneGraph.from_dict({"segment_id": "x", "some_future_field": {"a": 1}})
        self.assertEqual(sg.segment_id, "x")

    def test_from_dict_tolerates_garbage_node_entries(self):
        sg = SceneGraph.from_dict({"segment_id": "x", "nodes": ["not_a_dict", None, 42]})
        self.assertEqual(sg.nodes, [])


class TestOverscaledPresetLoading(unittest.TestCase):
    def setUp(self):
        clear_style_preset_cache()

    def tearDown(self):
        clear_style_preset_cache()

    def test_overscaled_preset_loads(self):
        preset = load_style_preset("overscaled")
        self.assertIsNotNone(preset)
        self.assertIsInstance(preset, StylePreset)
        self.assertEqual(preset.id, "overscaled")
        self.assertEqual(preset.name, "Overscaled")

    def test_overscaled_preset_has_expected_buckets(self):
        preset = load_style_preset("overscaled")
        self.assertIn("supported_types", preset.nodes)
        for node_type in ("image", "diagram", "video_loop", "anchor"):
            self.assertIn(node_type, preset.nodes["supported_types"])
        self.assertEqual(preset.canvas.get("background"), "#ffffff")
        self.assertIn("cold_open", preset.segment_structure_guidance)

    def test_unknown_preset_returns_none(self):
        self.assertIsNone(load_style_preset("does_not_exist"))

    def test_registry_keyed_by_id(self):
        registry = style_presets_by_id()
        self.assertIn("overscaled", registry)

    def test_preset_round_trip(self):
        preset = load_style_preset("overscaled")
        restored = StylePreset.from_dict(preset.to_dict())
        self.assertEqual(restored.to_dict(), preset.to_dict())


if __name__ == "__main__":
    unittest.main()
