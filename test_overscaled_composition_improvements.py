"""Tests for the Overscaled composition improvements: adaptive visual
sizing, global obstacle-aware arrow routing (+ labels), and subtle Ken Burns
motion on static images/diagrams — all solved ONCE at layout time and cached,
never recomputed per frame. See scene_graph/layout.py, scene_graph/routing.py
and scene_graph/render.py's module docstrings for the full design rationale.
"""

from __future__ import annotations

import csv
import math
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.layout import compute_layout
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.routing import (
    ObstacleRect,
    polyline_hits_rect,
    rect_obstacle,
    solve_caption_position,
    solve_edge_route,
    solve_label_position,
)


FIXTURE = Path(__file__).resolve().parent / "overscaled_sample.csv"


def _graph(rows, **kwargs):
    result = compile_overscaled_csv(rows, segment_id="seg", **kwargs)
    assert result.ok, result.errors
    return result.scene_graph


def _row(n, node_id, script="x", **extra):
    row = {"scene_number": str(n), "script_segment": script, "node_id": node_id,
           "node_type": "image", "asset_type": "flow_image"}
    row.update(extra)
    return row


class TestAdaptiveSizing(unittest.TestCase):
    """One active node should get a much larger rect than a node sharing the
    screen with two others — 1 active -> large, 3 active -> smaller but
    still collision-free, matching the spec's priority order (no collisions
    first, then large useful visuals)."""

    _CHAIN_SCRIPTS = (
        "Germany was falling behind in the industrial race of the war.",
        "Factories in the middle of the country kept struggling to keep pace.",
        "In the end the entire industrial base collapsed under the pressure.",
    )

    def _three_way_chain(self, role_on_b=""):
        rows = [
            _row(1, "a", script=self._CHAIN_SCRIPTS[0]),
            _row(2, "b", script=self._CHAIN_SCRIPTS[1], edge_from="a", edge_to="b", role=role_on_b),
            _row(3, "c", script=self._CHAIN_SCRIPTS[2], edge_from="b", edge_to="c"),
        ]
        return _graph(rows)

    def test_single_active_node_is_larger_than_three_concurrent(self):
        solo_rows = [_row(1, "solo", script=self._CHAIN_SCRIPTS[0])]
        solo_sg = _graph(solo_rows)
        solo_layout = compute_layout(solo_sg)
        solo_area = solo_layout.node_rects["solo"].width * solo_layout.node_rects["solo"].height

        trio_sg = self._three_way_chain()
        trio_layout = compute_layout(trio_sg)
        # All three genuinely overlap in time (the "editorial board" lingering
        # behavior — see scene_graph.layout.compute_layout) so this exercises
        # the real 3-active-visuals-at-once case, not just 3 members on paper.
        windows = [trio_layout.active_windows[n] for n in ("a", "b", "c")]
        self.assertTrue(all(windows[0][0] < w[1] and w[0] < windows[0][1] for w in windows[1:]))
        trio_area = trio_layout.node_rects["a"].width * trio_layout.node_rects["a"].height

        self.assertGreater(solo_area, trio_area)

    def test_three_concurrent_nodes_have_no_collisions(self):
        from scene_graph.layout import find_overlaps

        sg = self._three_way_chain()
        layout = compute_layout(sg)
        self.assertEqual(find_overlaps(layout, tolerance=0.5), [])

    def test_hero_role_gets_no_smaller_a_slot_than_symmetric(self):
        # A "hero" node should never be squeezed smaller just because it
        # happens to share a chapter with plainer context nodes.
        sg = self._three_way_chain(role_on_b="hero")
        layout = compute_layout(sg)
        hero_area = layout.node_rects["b"].width * layout.node_rects["b"].height
        other_area = layout.node_rects["a"].width * layout.node_rects["a"].height
        self.assertGreaterEqual(hero_area, other_area)


class TestObstacleAwareRouting(unittest.TestCase):
    """The core bug fix: an arrow between two endpoints must route AROUND an
    unrelated card sitting between them, never straight through it."""

    def test_direct_line_would_hit_the_obstacle(self):
        # Sanity check on the test setup itself: A and C are on opposite
        # sides of B, so the naive straight line genuinely passes through it.
        obstacle = rect_obstacle(280, 80, 420, 220)
        self.assertTrue(polyline_hits_rect([(100, 150), (600, 150)], obstacle))

    def test_solved_route_avoids_the_middle_obstacle(self):
        obstacle = rect_obstacle(280, 80, 420, 220, margin=16.0)
        route = solve_edge_route(100, 150, 600, 150, [obstacle])
        self.assertFalse(polyline_hits_rect(list(route.points), obstacle))

    def test_solved_route_avoids_multiple_obstacles(self):
        obstacles = [
            rect_obstacle(250, 60, 370, 180, margin=12.0),
            rect_obstacle(420, 200, 540, 320, margin=12.0),
        ]
        route = solve_edge_route(100, 120, 650, 260, obstacles)
        for obstacle in obstacles:
            self.assertFalse(polyline_hits_rect(list(route.points), obstacle))

    def test_route_endpoints_are_anchored_exactly(self):
        obstacle = rect_obstacle(280, 80, 420, 220, margin=16.0)
        route = solve_edge_route(100, 150, 600, 150, [obstacle])
        self.assertEqual(route.points[0], (100, 150))
        self.assertEqual(route.points[-1], (600, 150))

    def test_routing_is_deterministic(self):
        obstacle = rect_obstacle(280, 80, 420, 220, margin=16.0)
        r1 = solve_edge_route(100, 150, 600, 150, [obstacle])
        r2 = solve_edge_route(100, 150, 600, 150, [obstacle])
        self.assertEqual(r1.points, r2.points)

    def test_a_to_c_with_b_between_real_scene_graph(self):
        # The exact reported bug shape: three causally chained nodes in one
        # chapter, A -> B -> C, PLUS an A -> C edge (e.g. a "therefore"
        # callout) that must not cross through B's card.
        rows = [
            _row(1, "a", script="Germany was falling behind in the industrial race of the war."),
            _row(2, "b", script="Factories in the middle of the country kept struggling to keep pace.",
                 edge_from="a", edge_to="b"),
            _row(3, "c", script="In the end the entire industrial base collapsed under the pressure.",
                 edge_from="b", edge_to="c"),
            _row(4, "", script="Therefore the industry itself fell short of what was truly needed.",
                 node_type="", asset_type="", edge_from="a", edge_to="c", edge_label="industry falls short"),
        ]
        # Row 4 is edge-only (no node_type/asset_type -> defines no new node).
        rows[3].pop("node_id")
        sg = _graph(rows)
        layout = compute_layout(sg)
        route = layout.edge_routes.get("e_a_c")
        self.assertIsNotNone(route, "A->C edge route was not solved/cached")
        b_rect = layout.node_rects["b"]
        b_obstacle = rect_obstacle(b_rect.x, b_rect.y, b_rect.x2, b_rect.y2 + 170.0, margin=16.0)
        self.assertFalse(polyline_hits_rect(route, b_obstacle))


class TestLabelPlacement(unittest.TestCase):
    def test_label_avoids_keep_out_obstacle(self):
        curve = [(0.0, 100.0), (100.0, 100.0), (200.0, 100.0)]
        keep_out = [ObstacleRect(80.0, 60.0, 220.0, 140.0)]
        pos = solve_label_position(curve, 40.0, 16.0, keep_out)
        box = ObstacleRect(pos[0] - 40.0, pos[1] - 16.0, pos[0] + 40.0, pos[1] + 16.0)
        overlap = not (box.x1 <= keep_out[0].x0 or keep_out[0].x1 <= box.x0
                        or box.y1 <= keep_out[0].y0 or keep_out[0].y1 <= box.y0)
        self.assertFalse(overlap)

    def test_label_offset_clears_render_time_wobble(self):
        # Regression test: composition._jitter_polyline perturbs the cached
        # route by up to ~10px perpendicular AFTER the label position is
        # solved from the unjittered curve. The base label offset must stay
        # comfortably beyond jitter + a typical label's half-height, or the
        # wobbled line can be drawn straight through the label text (found
        # via a real render — an "idea becomes aircraft" label bisected by
        # its own arrow's stroke).
        from scene_graph.routing import _LABEL_OFFSETS

        max_jitter = 10.0
        typical_label_half_h = 16.0
        self.assertGreater(_LABEL_OFFSETS[0], max_jitter + typical_label_half_h)


class TestKenBurnsParams(unittest.TestCase):
    def _image_with_hold(self, node_id, script):
        return _row(1, node_id, script=script)

    def test_static_image_gets_deterministic_motion(self):
        rows = [self._image_with_hold("photo", "A reasonably long narration line so a hold exists.")]
        sg = _graph(rows)
        layout = compute_layout(sg)
        self.assertIn("photo", layout.node_ken_burns)
        params = layout.node_ken_burns["photo"]
        self.assertGreater(params["zoom_end"], 1.0)
        self.assertLessEqual(params["zoom_end"], 1.08)
        self.assertLessEqual(abs(params["pan_x"]), 0.05)
        self.assertLessEqual(abs(params["pan_y"]), 0.05)

    def test_same_node_id_same_motion_across_renders(self):
        rows = [self._image_with_hold("photo", "A reasonably long narration line so a hold exists.")]
        sg = _graph(rows)
        layout1 = compute_layout(sg)
        layout2 = compute_layout(sg)
        self.assertEqual(layout1.node_ken_burns["photo"], layout2.node_ken_burns["photo"])

    def test_different_nodes_can_have_different_motion(self):
        rows = [
            self._image_with_hold("photo_a", "First narration line long enough for a hold."),
            self._image_with_hold("photo_b", "Second narration line also long enough for a hold."),
        ]
        sg = _graph(rows)
        layout = compute_layout(sg)
        self.assertNotEqual(layout.node_ken_burns["photo_a"], layout.node_ken_burns["photo_b"])

    def test_anchor_nodes_never_get_ken_burns(self):
        rows = [
            {"scene_number": "1", "script_segment": "An anchor identifier.",
             "node_id": "anchor1", "node_type": "anchor", "asset_type": "flow_image"},
        ]
        sg = _graph(rows)
        layout = compute_layout(sg)
        self.assertNotIn("anchor1", layout.node_ken_burns)


class TestKenBurnsRenderWiring(unittest.TestCase):
    """render.py wires cached Ken Burns params into a real ffmpeg zoompan
    filter chain for image/diagram nodes only, never for video_loop cards —
    see scene_graph.render._kenburns_pre_filter / _node_reveal_layers."""

    def test_pre_filter_uses_cached_params_and_trims_to_exact_frame_count(self):
        from scene_graph.render import _kenburns_pre_filter

        pre = _kenburns_pre_filter(
            width=400, height=300, hold_start=2.0, hold_duration=3.0, fps=30,
            zoom_end=1.06, pan_x=0.02, pan_y=-0.01,
        )
        self.assertIn("zoompan=", pre)
        self.assertIn("d=90", pre)  # 3.0s * 30fps
        self.assertIn("trim=end_frame=90", pre)
        self.assertIn("setpts=PTS-STARTPTS+2.000000/TB", pre)
        self.assertIn("1.06", pre)

    def test_video_loop_node_never_gets_kenburns_layers(self):
        from scene_graph.layout import SceneGraphLayout
        from scene_graph.render import _node_reveal_layers
        from scene_graph.schema import SceneNode
        from scene_graph.style_presets import load_style_preset

        node = SceneNode(id="vid1", type="video_loop", label="", caption=None)
        layout = SceneGraphLayout(
            canvas_width=1920, canvas_height=1080,
            node_rects={"vid1": _fake_rect("vid1", 100, 100, 400, 300)},
            active_windows={"vid1": (0.0, 5.0)},
            node_ken_burns={"vid1": {"zoom_end": 1.05, "pan_x": 0.0, "pan_y": 0.0}},
        )
        style = load_style_preset("overscaled")
        with tempfile.TemporaryDirectory() as tmp:
            img = Image.new("RGBA", (400, 300), (255, 255, 255, 255))
            layers = _node_reveal_layers(
                node, layout=layout, style=style, media_image=img, hollow=True,
                fps=30, work_dir=Path(tmp),
            )
        # hollow=True (video_loop's decoration-only layer) must fall back to
        # the plain single settled-hold layer, never the two-layer zoompan
        # treatment reserved for image/diagram nodes.
        hold_layers = [l for l in layers if "-loop" in l.input_args]
        self.assertEqual(len(hold_layers), 1)

    def test_image_node_with_hold_gets_two_layers(self):
        from scene_graph.layout import SceneGraphLayout
        from scene_graph.render import _node_reveal_layers
        from scene_graph.schema import SceneNode
        from scene_graph.style_presets import load_style_preset

        node = SceneNode(id="img1", type="image", label="", caption=None)
        layout = SceneGraphLayout(
            canvas_width=1920, canvas_height=1080,
            node_rects={"img1": _fake_rect("img1", 100, 100, 400, 300)},
            active_windows={"img1": (0.0, 5.0)},
            node_ken_burns={"img1": {"zoom_end": 1.05, "pan_x": 0.01, "pan_y": -0.01}},
        )
        style = load_style_preset("overscaled")
        with tempfile.TemporaryDirectory() as tmp:
            img = Image.new("RGBA", (400, 300), (255, 255, 255, 255))
            layers = _node_reveal_layers(
                node, layout=layout, style=style, media_image=img, hollow=False,
                fps=30, work_dir=Path(tmp),
            )
        hold_layers = [l for l in layers if "-loop" in l.input_args]
        self.assertEqual(len(hold_layers), 2)
        self.assertTrue(any("zoompan=" in l.pre_filter for l in hold_layers))


class TestChapterVerticalVariation(unittest.TestCase):
    """Every slot template used to hardcode cy_frac=0.50 — every card in
    every chapter sat on the exact same horizontal line for the whole
    video. A small deterministic per-chapter offset fixes that without
    touching slot sizing or introducing any per-frame movement."""

    def _fixture(self):
        with open(FIXTURE, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return compile_overscaled_csv(rows, segment_id="aurora_bridge").scene_graph

    def test_different_chapters_get_different_vertical_centers(self):
        sg = self._fixture()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        centers = {
            members[0]: layout.node_rects[members[0]].y + layout.node_rects[members[0]].height / 2.0
            for members in layout.chapters
        }
        self.assertGreater(len(set(round(v, 3) for v in centers.values())), 1)

    def test_offset_is_deterministic(self):
        sg = self._fixture()
        layout1 = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        layout2 = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        self.assertEqual(layout1.to_dict()["node_rects"], layout2.to_dict()["node_rects"])

    def test_members_of_one_chapter_share_the_same_offset(self):
        # The RELATIVE geometry within a chapter (the deliberate
        # diagonal/asymmetric slot layout) must be unaffected — only the
        # whole chapter's group shifts together.
        rows = [
            _row(1, "a", script="Germany was falling behind in the industrial race of the war."),
            _row(2, "b", script="Factories in the middle of the country kept struggling to keep pace.",
                 edge_from="a", edge_to="b"),
        ]
        sg = _graph(rows)
        layout = compute_layout(sg)
        ra, rb = layout.node_rects["a"], layout.node_rects["b"]
        self.assertAlmostEqual(ra.y, rb.y, delta=0.01)

    def test_still_collision_free_with_offset_applied(self):
        from scene_graph.layout import find_overlaps

        sg = self._fixture()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        self.assertEqual(find_overlaps(layout, tolerance=0.5), [])

    def test_offset_never_pushes_a_rect_outside_the_canvas(self):
        sg = self._fixture()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        for node_id, rect in layout.node_rects.items():
            self.assertGreaterEqual(rect.y, 0, node_id)
            self.assertLessEqual(rect.y2, layout.canvas_height, node_id)


class TestCaptionPlacementSolver(unittest.TestCase):
    """routing.solve_caption_position — the pure-geometry layer under
    scene_graph.layout's narration-caption pass."""

    def test_no_conflict_returns_exactly_the_primary_position(self):
        bounds = ObstacleRect(0.0, 0.0, 1920.0, 1080.0)
        pos = solve_caption_position(100.0, 200.0, 300.0, 160.0, [], bounds=bounds)
        self.assertEqual(pos, (100.0, 200.0))

    def test_blocked_primary_escapes_to_a_clear_alternate(self):
        bounds = ObstacleRect(0.0, 0.0, 1920.0, 1080.0)
        blocker = ObstacleRect(100.0, 200.0, 400.0, 220.0)  # covers only the primary slice
        pos = solve_caption_position(100.0, 200.0, 300.0, 160.0, [blocker], bounds=bounds)
        self.assertNotEqual(pos, (100.0, 200.0))
        box = ObstacleRect(pos[0], pos[1], pos[0] + 300.0, pos[1] + 160.0)
        overlap = not (box.x1 <= blocker.x0 or blocker.x1 <= box.x0 or box.y1 <= blocker.y0 or blocker.y1 <= box.y0)
        self.assertFalse(overlap)

    def test_fully_blocked_falls_back_inside_bounds_deterministically(self):
        bounds = ObstacleRect(0.0, 0.0, 1920.0, 1080.0)
        huge_blocker = ObstacleRect(0.0, 0.0, 1920.0, 1080.0)
        pos1 = solve_caption_position(100.0, 200.0, 300.0, 160.0, [huge_blocker], bounds=bounds)
        pos2 = solve_caption_position(100.0, 200.0, 300.0, 160.0, [huge_blocker], bounds=bounds)
        self.assertEqual(pos1, pos2)
        self.assertGreaterEqual(pos1[0], bounds.x0)
        self.assertGreaterEqual(pos1[1], bounds.y0)
        self.assertLessEqual(pos1[0] + 300.0, bounds.x1)
        self.assertLessEqual(pos1[1] + 160.0, bounds.y1)

    def test_never_escapes_canvas_bounds_even_with_no_obstacles(self):
        bounds = ObstacleRect(0.0, 0.0, 1920.0, 1080.0)
        pos = solve_caption_position(1900.0, 200.0, 300.0, 160.0, [], bounds=bounds)
        self.assertLessEqual(pos[0] + 300.0, bounds.x1 + 1e-6)


class TestCaptionPlacementLayoutIntegration(unittest.TestCase):
    """scene_graph.layout.compute_layout's narration-caption pass — wired
    end to end, not just the underlying solver."""

    def test_caption_positions_present_for_every_captioned_node(self):
        rows = [
            _row(1, "a", script="Germany was falling behind in the industrial race of the war.",
                 caption="Germany was falling behind"),
            _row(2, "b", script="Factories in the middle of the country kept struggling to keep pace.",
                 edge_from="a", edge_to="b", caption="Factories struggled"),
        ]
        sg = _graph(rows)
        layout = compute_layout(sg)
        self.assertIn("a", layout.caption_positions)
        self.assertIn("b", layout.caption_positions)

    def test_no_conflict_gives_zero_offset(self):
        # A single solo node has nothing to conflict with.
        rows = [_row(1, "solo", script="A reasonably long narration line here.", caption="A short caption")]
        sg = _graph(rows)
        layout = compute_layout(sg)
        self.assertEqual(layout.caption_positions.get("solo"), (0.0, 0.0))

    def test_deterministic_across_two_computations(self):
        rows = [
            _row(1, "a", script="Germany was falling behind in the industrial race of the war.",
                 caption="Germany was falling behind"),
            _row(2, "b", script="Factories in the middle of the country kept struggling to keep pace.",
                 edge_from="a", edge_to="b", caption="Factories struggled"),
            _row(3, "c", script="In the end the entire industrial base collapsed under the pressure.",
                 edge_from="b", edge_to="c", caption="Industry collapsed"),
        ]
        sg = _graph(rows)
        layout1 = compute_layout(sg)
        layout2 = compute_layout(sg)
        self.assertEqual(layout1.caption_positions, layout2.caption_positions)

    def test_node_without_caption_gets_no_entry(self):
        rows = [_row(1, "nocap", script="A reasonably long narration line here without a caption.")]
        sg = _graph(rows)
        layout = compute_layout(sg)
        self.assertNotIn("nocap", layout.caption_positions)


class TestCaptionDrawOffset(unittest.TestCase):
    """composition._draw_caption — the render-time consumer: draws at the
    already-solved offset, never searches, and reproduces the exact
    pre-existing pixel position when the offset is (0, 0)."""

    def _render(self, offset):
        from scene_graph.composition import _draw_caption
        from scene_graph.layout import NodeRect
        from scene_graph.schema import CaptionSpec
        from scene_graph.style_presets import load_style_preset

        canvas = Image.new("RGBA", (800, 600), (255, 255, 255, 255))
        rect = NodeRect(node_id="n1", x=100.0, y=100.0, width=400.0, height=300.0)
        caption = CaptionSpec(text="A short caption line")
        style = load_style_preset("overscaled")
        _draw_caption(canvas, caption, rect, style=style, offset=offset)
        return canvas

    def test_default_offset_matches_legacy_zero_offset_call(self):
        import numpy as np

        from scene_graph.composition import _draw_caption
        from scene_graph.layout import NodeRect
        from scene_graph.schema import CaptionSpec
        from scene_graph.style_presets import load_style_preset

        rect = NodeRect(node_id="n1", x=100.0, y=100.0, width=400.0, height=300.0)
        caption = CaptionSpec(text="A short caption line")
        style = load_style_preset("overscaled")

        canvas_legacy = Image.new("RGBA", (800, 600), (255, 255, 255, 255))
        _draw_caption(canvas_legacy, caption, rect, style=style)  # no offset kwarg at all

        canvas_explicit = Image.new("RGBA", (800, 600), (255, 255, 255, 255))
        _draw_caption(canvas_explicit, caption, rect, style=style, offset=(0.0, 0.0))

        self.assertEqual(
            np.asarray(canvas_legacy).tobytes(), np.asarray(canvas_explicit).tobytes(),
        )

    def test_nonzero_offset_actually_shifts_the_drawn_pixels(self):
        import numpy as np

        canvas_zero = self._render((0.0, 0.0))
        canvas_shifted = self._render((0.0, 40.0))
        self.assertFalse(
            np.array_equal(np.asarray(canvas_zero), np.asarray(canvas_shifted))
        )


def _fake_rect(node_id, x, y, w, h):
    from scene_graph.layout import NodeRect

    return NodeRect(node_id=node_id, x=x, y=y, width=w, height=h)


if __name__ == "__main__":
    unittest.main()
