"""The 1-card ("solo") slot is per-style: Exp Solar's near-full-stage hero
(98% x 97%) must never leak into Overscaled, which keeps its original
62% x 90% solo card with white canvas around it."""
from __future__ import annotations

import unittest

from scene_graph.layout import OVERSCALED_SOLO_SLOT, compute_layout
from scene_graph.schema import SceneGraph, SceneNode
from scene_graph.style_presets import load_style_preset


def _solo_graph() -> SceneGraph:
    return SceneGraph(segment_id="seg", duration=6.0, nodes=[SceneNode(id="solo", type="image", appear_at=0.0)], edges=[])


class TestSoloSlotGate(unittest.TestCase):
    def _solo_box(self, solo_slot=None):
        layout = compute_layout(_solo_graph(), canvas_width=1920, canvas_height=1080, solo_slot=solo_slot)
        return layout.node_rects["solo"]

    def test_overscaled_default_is_the_original_solo_slot(self):
        self.assertEqual(OVERSCALED_SOLO_SLOT, (0.50, 0.50, 0.62, 0.90))
        self.assertIsNone((load_style_preset("overscaled").metadata or {}).get("solo_slot"))

    def test_exp_solar_keeps_its_near_full_stage_solo_card(self):
        slot = (load_style_preset("exp_solar").metadata or {}).get("solo_slot")
        self.assertEqual(list(slot), [0.50, 0.50, 0.98, 0.97])
        overscaled = self._solo_box()
        exp_solar = self._solo_box(slot)
        self.assertGreater(exp_solar.width * exp_solar.height, overscaled.width * overscaled.height * 1.1)

    def test_default_matches_passing_the_overscaled_slot_explicitly(self):
        a, b = self._solo_box(), self._solo_box(OVERSCALED_SOLO_SLOT)
        self.assertEqual((a.x, a.y, a.width, a.height), (b.x, b.y, b.width, b.height))


class TestStaggeredCollageGate(unittest.TestCase):
    """Overscaled's 2/3-card compositions are a staggered collage from its
    own preset metadata; Exp Solar keeps the built-in single row."""

    def _layout(self, n, style):
        from scene_graph.schema import SceneEdge

        nodes = [SceneNode(id=f"c{i}", type="image", appear_at=float(i)) for i in range(n)]
        edges = [
            SceneEdge(id=f"e{i}", from_node=f"c{i}", to_node=f"c{i + 1}", draw_at=float(i + 1))
            for i in range(n - 1)
        ]
        sg = SceneGraph(segment_id="seg", duration=float(n) + 6.0, nodes=nodes, edges=edges)
        meta = load_style_preset(style).metadata or {}
        return compute_layout(
            sg, canvas_width=1920, canvas_height=1080,
            solo_slot=meta.get("solo_slot"), slot_templates=meta.get("slot_templates"),
        )

    def _centers_y(self, layout, n):
        return [layout.node_rects[f"c{i}"].y + layout.node_rects[f"c{i}"].height / 2 for i in range(n)]

    def test_overscaled_two_cards_are_staggered_and_large(self):
        from scene_graph.layout import find_overlaps

        layout = self._layout(2, "overscaled")
        a, b = (layout.node_rects["c0"], layout.node_rects["c1"])
        ya, yb = self._centers_y(layout, 2)
        self.assertGreater(yb - ya, 150)  # not one horizontal centerline
        for r in (a, b):
            self.assertTrue(0.32 * 1920 <= r.width <= 0.42 * 1920 + 1, r.width)
        self.assertGreater(b.x - (a.x + a.width), 120)  # room for a visible arrow
        self.assertEqual(find_overlaps(layout), [])

    def test_overscaled_three_cards_form_a_triangle(self):
        from scene_graph.layout import find_overlaps

        layout = self._layout(3, "overscaled")
        ys = self._centers_y(layout, 3)
        self.assertGreater(max(ys) - min(ys), 200)
        for i in range(3):
            self.assertTrue(0.25 * 1920 <= layout.node_rects[f"c{i}"].width <= 0.33 * 1920 + 1)
        self.assertEqual(find_overlaps(layout), [])

    def test_overscaled_trio_arrow_has_room_to_travel(self):
        import math

        layout = self._layout(3, "overscaled")
        for edge_id in ("e0", "e1"):
            route = layout.edge_routes[edge_id]
            length = sum(math.dist(route[i], route[i + 1]) for i in range(len(route) - 1))
            self.assertGreater(length, 140, edge_id)

    def test_arrow_is_not_bent_around_an_earlier_compositions_arrow(self):
        """Compositions reuse the same slots, so a cleared pair's arrow sits
        exactly on the next pair's straight path. It must not count as an
        obstacle once it's off screen (it used to bend the arrow into a hook)."""
        import math

        from scene_graph.schema import SceneEdge

        nodes = [SceneNode(id=i, type="image", appear_at=t) for i, t in
                 (("p1a", 0.0), ("p1b", 3.0), ("p2a", 8.0), ("p2b", 11.0))]
        edges = [
            SceneEdge(id="e1", from_node="p1a", to_node="p1b", draw_at=3.0),
            SceneEdge(id="e2", from_node="p2a", to_node="p2b", draw_at=11.0),
        ]
        sg = SceneGraph(segment_id="seg", duration=16.0, nodes=nodes, edges=edges)
        meta = load_style_preset("overscaled").metadata or {}
        layout = compute_layout(sg, canvas_width=1920, canvas_height=1080,
                                slot_templates=meta.get("slot_templates"))
        self.assertLessEqual(layout.edge_windows["e1"][1], layout.edge_windows["e2"][0])

        def deviation(pts):
            (x0, y0), (x1, y1) = pts[0], pts[-1]
            d = math.dist((x0, y0), (x1, y1)) or 1.0
            return max(abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / d for x, y in pts)

        self.assertLess(deviation(layout.edge_routes["e1"]), 1.0)
        self.assertLess(deviation(layout.edge_routes["e2"]), 1.0)

    def test_exp_solar_keeps_its_single_row(self):
        self.assertIsNone((load_style_preset("exp_solar").metadata or {}).get("slot_templates"))
        for n in (2, 3):
            ys = self._centers_y(self._layout(n, "exp_solar"), n)
            self.assertLess(max(ys) - min(ys), 1.0)


class TestOverscaledArrowAndAnchorGate(unittest.TestCase):
    """Overscaled's thicker/calmer arrows and inline subject photo come only
    from its own preset; Exp Solar keeps the original defaults."""

    def _graph(self):
        nodes = [
            SceneNode(id="a1", type="anchor", appear_at=0.0),
            SceneNode(id="c0", type="image", appear_at=0.0),
        ]
        return SceneGraph(segment_id="seg", duration=6.0, nodes=nodes, edges=[])

    def test_inline_anchor_does_not_push_the_stage_down(self):
        banded = compute_layout(self._graph(), canvas_width=1920, canvas_height=1080)
        inline = compute_layout(self._graph(), canvas_width=1920, canvas_height=1080, anchor_inline_title=True)
        self.assertIsNone(banded.title_x_px)
        a = inline.node_rects["a1"]
        self.assertGreater(inline.title_x_px, a.x + a.width)
        self.assertGreaterEqual(inline.node_rects["c0"].y, a.y + a.height)
        # The card gets the room the old separate anchor band used to take.
        self.assertGreater(inline.node_rects["c0"].height, banded.node_rects["c0"].height)

    def test_style_overrides_are_overscaled_only(self):
        over, exp = load_style_preset("overscaled"), load_style_preset("exp_solar")
        self.assertGreater(over.arrows["line_width"], 6)
        self.assertLess(over.arrows["jitter_px"], 10)
        self.assertTrue(over.metadata["anchor_inline_title"])
        self.assertEqual(over.metadata["anchor_style"], "photo")
        for key in ("line_width", "jitter_px", "head_len"):
            self.assertNotIn(key, exp.arrows or {})
        for key in ("anchor_inline_title", "anchor_style"):
            self.assertNotIn(key, exp.metadata or {})

    def test_photo_anchor_has_no_circle_outline(self):
        from PIL import Image

        from scene_graph.composition import _draw_anchor
        from scene_graph.layout import NodeRect

        rect = NodeRect(node_id="a1", x=10, y=10, width=170, height=96)
        photo = Image.new("RGBA", (340, 192), (200, 30, 30, 255))
        canvas = Image.new("RGBA", (200, 130), (255, 255, 255, 0))
        _draw_anchor(canvas, SceneNode(id="a1", type="anchor", appear_at=0.0), rect, photo,
                     load_style_preset("overscaled"))
        self.assertEqual(canvas.getpixel((95, 58))[:3], (200, 30, 30))  # the photo, edge to edge
        circled = Image.new("RGBA", (200, 130), (255, 255, 255, 0))
        _draw_anchor(circled, SceneNode(id="a1", type="anchor", appear_at=0.0), rect, photo,
                     load_style_preset("exp_solar"))
        self.assertNotEqual(circled.getpixel((12, 58))[:3], (200, 30, 30))


if __name__ == "__main__":
    unittest.main()
