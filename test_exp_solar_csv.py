"""Focused tests for the Exp Solar CSV contract + adapter
(scene_graph/exp_solar_csv.py) and its UI wiring in app.py.

Mirrors test_overscaled_composition_improvements.py's/test_overscaled_ui_integration.py's
conventions: plain unittest, source-level checks for app.py (no live display
required), direct module calls for the parser/adapter itself.
"""

from __future__ import annotations

import inspect
import unittest

from scene_graph.exp_solar_csv import (
    DEFERRED_BEATS,
    KNOWN_BEATS,
    RELATIONSHIP_TYPES,
    compile_exp_solar_csv,
    validate_exp_solar_csv,
)


def _row(**kwargs) -> dict:
    base = {"scene_number": "1", "script_segment": "x"}
    base.update(kwargs)
    return base


class TestExpSolarCsvValidation(unittest.TestCase):
    def test_empty_csv_rejected(self):
        errors = validate_exp_solar_csv([])
        self.assertTrue(errors)

    def test_missing_required_column_rejected(self):
        errors = validate_exp_solar_csv([{"script_segment": "x"}])
        self.assertTrue(any("scene_number" in e for e in errors))

    def test_unknown_beat_rejected(self):
        errors = validate_exp_solar_csv([_row(beat="not_a_real_beat")])
        self.assertTrue(any("beat" in e for e in errors))

    def test_all_known_beats_accepted(self):
        for beat in KNOWN_BEATS:
            errors = validate_exp_solar_csv([_row(beat=beat)])
            self.assertEqual(errors, [], f"beat={beat!r} should validate cleanly")

    def test_unknown_relationship_type_rejected(self):
        errors = validate_exp_solar_csv([_row(relationship_type="friendship")])
        self.assertTrue(any("relationship_type" in e for e in errors))

    def test_all_known_relationship_types_accepted(self):
        for rel in RELATIONSHIP_TYPES:
            errors = validate_exp_solar_csv([_row(relationship_type=rel, relationship_to="n1")])
            self.assertEqual(errors, [])

    def test_blank_beat_and_relationship_type_are_valid(self):
        self.assertEqual(validate_exp_solar_csv([_row()]), [])


class TestExpSolarCsvAdapter(unittest.TestCase):
    def test_valid_csv_compiles_to_scene_graph(self):
        rows = [
            _row(
                scene_number="1", script_segment="The sun churns with plasma.",
                beat="hero", asset_type="flow_image", prompt="a churning sun",
                chapter="The Sun",
            ),
        ]
        result = compile_exp_solar_csv(rows, segment_id="seg1", title="t")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.style_preset, "exp_solar")
        self.assertEqual(len(result.scene_graph.nodes), 1)
        self.assertEqual(result.scene_graph.nodes[0].type, "image")
        self.assertEqual(result.scene_graph.nodes[0].semantic_role, "hero")
        self.assertEqual(result.scene_graph.title_cues[0].text, "The Sun")

    def test_two_panel_rows_without_relationship_to_are_auto_paired(self):
        # A genuine comparison (no cause/effect) must correctly leave
        # relationship_to blank per the arrow-restraint rule — but the two
        # rows still need to land on screen together. Regression for the
        # bug where two_panel rows with no relationship_to rendered as two
        # disconnected single cards instead of an actual 2-panel split.
        rows = [
            _row(scene_number="1", node_id="a", beat="two_panel",
                 asset_type="flow_image", prompt="mars atmosphere"),
            _row(scene_number="2", node_id="b", beat="two_panel",
                 asset_type="flow_image", prompt="earth atmosphere"),
        ]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        self.assertEqual(len(result.scene_graph.edges), 1)
        edge = result.scene_graph.edges[0]
        self.assertEqual(edge.kind, "group")  # never drawn as a visible arrow
        self.assertEqual({edge.from_node, edge.to_node}, {"a", "b"})

    def test_two_panel_explicit_relationship_to_is_not_overwritten(self):
        rows = [
            _row(scene_number="1", node_id="a", beat="two_panel", asset_type="flow_image", prompt="p"),
            _row(scene_number="2", node_id="b", beat="two_panel", asset_type="flow_image", prompt="p",
                 relationship_to="a", relationship_type="consequence"),
        ]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        edge = result.scene_graph.edges[0]
        self.assertEqual(edge.kind, "sequential")  # author's own edge, not the auto "group" pairing

    def test_two_consecutive_two_panel_pairs_form_two_separate_splits(self):
        rows = [
            _row(scene_number="1", node_id="a", beat="two_panel", asset_type="flow_image", prompt="p"),
            _row(scene_number="2", node_id="b", beat="two_panel", asset_type="flow_image", prompt="p"),
            _row(scene_number="3", node_id="c", beat="two_panel", asset_type="flow_image", prompt="p"),
            _row(scene_number="4", node_id="d", beat="two_panel", asset_type="flow_image", prompt="p"),
        ]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, [])
        edges = result.scene_graph.edges
        self.assertEqual(len(edges), 2)  # a-b and c-d, never one chain of 4
        pairs = {frozenset((e.from_node, e.to_node)) for e in edges}
        self.assertEqual(pairs, {frozenset({"a", "b"}), frozenset({"c", "d"})})

    def test_odd_two_panel_row_out_warns_and_stays_standalone(self):
        rows = [
            _row(scene_number="1", node_id="a", beat="two_panel", asset_type="flow_image", prompt="p"),
            _row(scene_number="2", node_id="b", beat="two_panel", asset_type="flow_image", prompt="p"),
            _row(scene_number="3", node_id="c", beat="two_panel", asset_type="flow_image", prompt="p"),
        ]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("no pairing partner", result.warnings[0])
        self.assertEqual(len(result.scene_graph.edges), 1)  # a-b only; c stands alone

    def test_missing_required_field_fails_compile(self):
        result = compile_exp_solar_csv([{"script_segment": "x"}], segment_id="seg1")
        self.assertFalse(result.ok)
        self.assertTrue(result.errors)
        self.assertIsNone(result.scene_graph)

    def test_video_asset_type_maps_to_video_loop_node(self):
        rows = [_row(node_id="n1", asset_type="stock_video", prompt="a clip")]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.nodes[0].type, "video_loop")

    def test_relationship_creates_a_never_callout_edge(self):
        rows = [
            _row(scene_number="1", node_id="n1", beat="hero", asset_type="flow_image", prompt="a"),
            _row(
                scene_number="2", node_id="n2", beat="two_panel", asset_type="flow_image",
                prompt="b", relationship_to="n1", relationship_type="consequence",
            ),
        ]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(len(result.scene_graph.edges), 1)
        edge = result.scene_graph.edges[0]
        self.assertEqual(edge.from_node, "n2")
        self.assertEqual(edge.to_node, "n1")
        # Arrow-restraint rule: the adapter must NEVER auto-promote to "callout".
        self.assertEqual(edge.kind, "sequential")

    def test_no_relationship_column_means_no_edge(self):
        rows = [_row(node_id="n1", asset_type="flow_image", prompt="a")]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.edges, [])

    def test_deferred_beats_degrade_with_a_warning_not_an_error(self):
        for beat in DEFERRED_BEATS:
            rows = [_row(node_id="n1", beat=beat, asset_type="flow_image", prompt="a")]
            result = compile_exp_solar_csv(rows, segment_id="seg1")
            self.assertTrue(result.ok, result.errors)
            self.assertTrue(result.warnings, f"beat={beat!r} should warn")
            self.assertIn(beat, result.warnings[0])
            # Still renders as one ordinary card — no fabricated grid/checklist.
            self.assertEqual(len(result.scene_graph.nodes), 1)

    def test_supported_beats_produce_no_warning(self):
        from scene_graph.exp_solar_csv import SUPPORTED_BEATS

        for beat in SUPPORTED_BEATS:
            if beat == "two_panel":
                # two_panel is inherently pairwise (see _chain_two_panel_beats)
                # — a single, unpaired row is the one legitimate case that
                # DOES warn; test it with a real pair instead.
                rows = [
                    _row(scene_number="1", node_id="n1", beat=beat, asset_type="flow_image", prompt="a"),
                    _row(scene_number="2", node_id="n2", beat=beat, asset_type="flow_image", prompt="b"),
                ]
            else:
                rows = [_row(node_id="n1", beat=beat, asset_type="flow_image", prompt="a")]
            result = compile_exp_solar_csv(rows, segment_id="seg1")
            self.assertTrue(result.ok, result.errors)
            self.assertEqual(result.warnings, [])

    def test_node_id_is_auto_generated_when_blank(self):
        rows = [_row(scene_number="7", asset_type="flow_image", prompt="a")]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.nodes[0].id, "n7")

    def test_conflicting_node_id_redefinition_is_rejected(self):
        rows = [
            _row(scene_number="1", node_id="dup", asset_type="flow_image", prompt="a"),
            _row(scene_number="2", node_id="dup", asset_type="flow_image", prompt="b"),
        ]
        result = compile_exp_solar_csv(rows, segment_id="seg1")
        self.assertFalse(result.ok)


class TestExpSolarUIWiring(unittest.TestCase):
    """Source-level checks (inspect.getsource) — no live display needed,
    same convention as TestOverscaledUIWiring in test_overscaled_ui_integration.py."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as _app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"customtkinter not available: {exc}")
        cls._app = _app

    def test_style_selector_exists(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._build_overscaled_section)
        self.assertIn("CTkSegmentedButton", src)
        self.assertIn("Exp Solar", src)
        self.assertIn("_on_overscaled_style_change", src)

    def test_exp_solar_has_its_own_browse_action(self):
        self.assertTrue(hasattr(self._app.VideoGeneratorApp, "_browse_exp_solar_csv"))
        src = inspect.getsource(self._app.VideoGeneratorApp._browse_exp_solar_csv)
        self.assertIn("Select Exp Solar CSV", src)
        self.assertIn("_load_overscaled_csv", src)

    def test_overscaled_browse_action_is_unchanged_and_still_present(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._browse_overscaled_csv)
        self.assertIn("Select Overscaled CSV", src)

    def test_load_dispatches_to_exp_solar_parser_by_style(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._load_overscaled_csv)
        self.assertIn('self._overscaled_style_preset_id == "exp_solar"', src)
        self.assertIn("compile_exp_solar_csv", src)
        self.assertIn("compile_overscaled_csv", src)

    def test_style_change_propagates_preset_id(self):
        src = inspect.getsource(self._app.VideoGeneratorApp._on_overscaled_style_change)
        self.assertIn('"exp_solar" if choice == "Exp Solar" else "overscaled"', src)
        self.assertIn("self._overscaled_style_preset_id", src)


if __name__ == "__main__":
    unittest.main()
