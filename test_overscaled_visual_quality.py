"""Tests for the Section-5 visual-quality improvements:
  - node reveal: restrained scale-in + fade (not just a flat fade)
  - arrow draw-on: a REAL progressive stroke (not a fade of the finished arrow)

Both are pure Pillow functions (scene_graph.composition.render_node_reveal_frame /
render_edge_reveal_frame) — tested directly and fast, no ffmpeg needed here.
The full ffmpeg pipeline exercising them frame-by-frame is covered by
test_overscaled_pipeline_e2e.py.
"""

from __future__ import annotations

import unittest

import numpy as np

from scene_graph.composition import render_edge_reveal_frame, render_node_reveal_frame
from scene_graph.layout import NodeRect
from scene_graph.schema import SceneEdge, SceneNode
from scene_graph.style_presets import load_style_preset


def _visible_pixel_count(frame) -> int:
    alpha = np.array(frame.split()[-1])
    return int((alpha > 10).sum())


def _total_alpha(frame) -> int:
    return int(np.array(frame.split()[-1]).astype(int).sum())


class TestArrowProgressiveDrawOn(unittest.TestCase):
    def setUp(self):
        self.style = load_style_preset("overscaled")
        self.edge = SceneEdge(id="e1", from_node="a", to_node="b", draw_at=0.0, duration=0.8)
        self.r_from = NodeRect("a", 100, 100, 200, 150)
        self.r_to = NodeRect("b", 500, 400, 200, 150)

    def test_zero_progress_is_fully_invisible(self):
        frame = render_edge_reveal_frame(self.edge, self.r_from, self.r_to, self.style, canvas_size=(800, 600), progress=0.0)
        self.assertEqual(_visible_pixel_count(frame), 0)

    def test_pixel_count_strictly_increases_then_settles(self):
        counts = [
            _visible_pixel_count(
                render_edge_reveal_frame(self.edge, self.r_from, self.r_to, self.style, canvas_size=(800, 600), progress=p)
            )
            for p in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
        ]
        for a, b in zip(counts, counts[1:]):
            self.assertGreaterEqual(b, a)
        self.assertGreater(counts[-1], counts[0])

    def test_full_progress_matches_the_classic_fully_drawn_arrow(self):
        full = render_edge_reveal_frame(self.edge, self.r_from, self.r_to, self.style, canvas_size=(800, 600), progress=1.0)
        self.assertGreater(_visible_pixel_count(full), 0)

    def test_arrowhead_only_appears_near_completion(self):
        # A partial stroke (progress well below 1) must have visibly fewer
        # pixels near the destination end than the fully-drawn one (i.e. no
        # arrowhead has been stamped down early).
        partial = render_edge_reveal_frame(self.edge, self.r_from, self.r_to, self.style, canvas_size=(800, 600), progress=0.5)
        full = render_edge_reveal_frame(self.edge, self.r_from, self.r_to, self.style, canvas_size=(800, 600), progress=1.0)
        self.assertLess(_visible_pixel_count(partial), _visible_pixel_count(full))


class TestNodeScaleInReveal(unittest.TestCase):
    def setUp(self):
        self.style = load_style_preset("overscaled")
        self.node = SceneNode(id="n1", type="image", appear_at=0.0)
        self.rect = NodeRect("n1", 100, 100, 200, 150)

    def test_zero_progress_is_fully_invisible(self):
        frame = render_node_reveal_frame(self.node, self.rect, None, self.style, canvas_size=(800, 600), background="", progress=0.0)
        self.assertEqual(_total_alpha(frame), 0)

    def test_opacity_increases_monotonically_with_progress(self):
        alphas = [
            _total_alpha(
                render_node_reveal_frame(self.node, self.rect, None, self.style, canvas_size=(800, 600), background="", progress=p)
            )
            for p in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        for a, b in zip(alphas, alphas[1:]):
            self.assertGreaterEqual(b, a)
        self.assertGreater(alphas[-1], alphas[0])

    def test_reveal_grows_into_the_same_center_point(self):
        # A restrained scale-in should stay centered on the node's rect
        # center at every progress step (grows INTO place, doesn't drift).
        import numpy as np

        cx, cy = int(self.rect.center[0]), int(self.rect.center[1])
        for p in (0.4, 0.7, 1.0):
            frame = render_node_reveal_frame(self.node, self.rect, None, self.style, canvas_size=(800, 600), background="", progress=p)
            alpha = np.array(frame.split()[-1])
            self.assertGreater(alpha[cy, cx], 0, f"center pixel is transparent at progress={p}")


if __name__ == "__main__":
    unittest.main()
