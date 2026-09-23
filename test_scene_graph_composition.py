"""Tests for scene_graph/composition.py — real Pillow rendering, no mocking."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.composition import render_composition
from scene_graph.layout import compute_layout
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.style_presets import load_style_preset

FIXTURE = Path(__file__).resolve().parent / "overscaled_sample.csv"


def _fixture_scene_graph():
    with open(FIXTURE, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = compile_overscaled_csv(rows, segment_id="aurora_bridge")
    assert result.ok, result.errors
    return result.scene_graph


class CompositionTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.media_dir = self.tmp / "media"
        self.media_dir.mkdir()
        self.style = load_style_preset("overscaled")

    def _resolved_media(self, sg):
        resolved = {}
        for i, node in enumerate(sg.nodes):
            if node.type == "video_loop":
                continue  # exercised separately with a real video below
            path = self.media_dir / f"{node.id}.png"
            color = ((i * 47) % 255, (i * 91) % 255, (i * 137) % 255)
            Image.new("RGB", (640, 360), color).save(path)
            resolved[node.id] = str(path)
        return resolved


class TestImageDiagramAnchorNodesRender(CompositionTestBase):
    def test_all_node_types_produce_overlay_files(self):
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1200, canvas_height=800)
        resolved = self._resolved_media(sg)
        assets = render_composition(sg, layout, self.style, resolved_media=resolved, out_dir=self.tmp / "out")

        self.assertTrue(assets.canvas_path.is_file())
        types_present = {n.type for n in sg.nodes}
        self.assertEqual(types_present, {"image", "diagram", "video_loop", "anchor"})
        for node in sg.nodes:
            self.assertIn(node.id, assets.node_overlay_paths)
            self.assertTrue(assets.node_overlay_paths[node.id].is_file())

    def test_video_loop_node_renders_via_real_ffmpeg_thumbnail(self):
        import subprocess

        video_path = self.media_dir / "clip.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=1", str(video_path)],
            capture_output=True, check=True,
        )
        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "video_loop", "asset_type": "flow_video"}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        sg = result.scene_graph
        layout = compute_layout(sg, canvas_width=800, canvas_height=600)
        assets = render_composition(sg, layout, self.style, resolved_media={"n1": str(video_path)}, out_dir=self.tmp / "vloop")
        overlay = Image.open(assets.node_overlay_paths["n1"])
        # The node's rect region should now contain non-transparent (revealed) pixels.
        rect = layout.node_rects["n1"]
        pixel = overlay.convert("RGBA").getpixel((int(rect.center[0]), int(rect.center[1])))
        self.assertGreater(pixel[3], 0, "video thumbnail did not get composited into the node overlay")

    def test_missing_media_renders_a_placeholder_not_a_crash(self):
        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image", "asset_type": "flow_image"}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        sg = result.scene_graph
        layout = compute_layout(sg, canvas_width=800, canvas_height=600)
        assets = render_composition(sg, layout, self.style, resolved_media={}, out_dir=self.tmp / "missing")
        self.assertTrue(assets.canvas_path.is_file())


class TestCaptionsAndHighlightsRender(CompositionTestBase):
    def test_caption_and_highlight_change_pixels_vs_no_caption(self):
        rows_with = [{
            "scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image",
            "asset_type": "flow_image", "caption": "The bridge fell down", "highlight": "fell down",
        }]
        rows_without = [{
            "scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image", "asset_type": "flow_image",
        }]
        style = self.style
        for rows, name in ((rows_with, "with"), (rows_without, "without")):
            result = compile_overscaled_csv(rows, segment_id="seg")
            sg = result.scene_graph
            layout = compute_layout(sg, canvas_width=800, canvas_height=600)
            assets = render_composition(sg, layout, style, resolved_media={}, out_dir=self.tmp / name)
            setattr(self, f"canvas_{name}", Image.open(assets.canvas_path).convert("RGB"))

        import numpy as np

        arr_with = np.array(self.canvas_with)
        arr_without = np.array(self.canvas_without)
        self.assertFalse((arr_with == arr_without).all(), "adding a caption did not change any pixels")


class TestCaptionFitsWithinItsReservedClearance(CompositionTestBase):
    """Regression test for a real bug: a realistically long, 2-line-wrapping
    caption was being visually clipped because the reserved caption band
    didn't leave enough ABSOLUTE pixels once the font size — itself
    proportional to the (now bigger) card — grew along with the card. This
    renders a caption at PRODUCTION card sizes and checks the wrapped text
    block actually fits in the reserved band, not just that it renders
    without crashing. (The reserve is now a fixed pixel amount,
    CAPTION_RESERVE_PX, not a fraction of box height — a fraction shrank
    disproportionately for the wide-but-short boxes the row-based
    _SLOT_TEMPLATES uses, a separate bug fixed alongside this one.)"""

    def test_long_real_world_caption_fits_in_the_reserved_band(self):
        from scene_graph.composition import _CAPTION_FONT_CANDIDATES, _load_font, _wrap_caption_lines
        from scene_graph.layout import CAPTION_RESERVE_PX, compute_layout
        from scene_graph.schema import CaptionSpec, SceneGraph, SceneNode
        from PIL import ImageDraw

        long_caption = "A hidden dependency was built into the design that would later prove catastrophic"
        sg = SceneGraph(
            segment_id="seg", duration=5.0,
            nodes=[SceneNode(id="n1", type="image", appear_at=0.0, caption=CaptionSpec(text=long_caption))],
        )
        canvas_w, canvas_h = 1920, 1080
        layout = compute_layout(sg, canvas_width=canvas_w, canvas_height=canvas_h)
        rect = layout.node_rects["n1"]
        reserved_px = CAPTION_RESERVE_PX

        font = _load_font(_CAPTION_FONT_CANDIDATES, min(34, max(14, int(rect.height * 0.09))))
        draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        lines = _wrap_caption_lines(draw, long_caption, font, rect.width, max_lines=3)
        line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + 6
        top_gap = 10
        needed_px = top_gap + len(lines) * line_height

        self.assertLessEqual(
            needed_px, reserved_px,
            f"caption needs {needed_px:.0f}px but only {reserved_px:.0f}px was reserved — it will be clipped",
        )

    def test_both_wrapped_lines_actually_render_through_the_real_reveal_frame(self):
        # Regression: the outer-canvas reserve math above passed even while
        # a SEPARATE bug clipped the caption — render_node_reveal_frame
        # draws the caption inside a small internal sub-canvas whose bottom
        # margin was a flat 24px (meant only for the scale-in animation's
        # growth headroom), so a 2-line caption got clipped by THAT
        # boundary regardless of how much room the layout engine reserved.
        # This only reproduces by going through the real function, not by
        # re-deriving the numbers separately.
        from scene_graph.composition import render_node_reveal_frame
        from scene_graph.layout import compute_layout
        from scene_graph.schema import CaptionSpec, SceneEdge, SceneGraph, SceneNode

        long_caption = "A tiny software flaw quietly became a catastrophic system-level failure across every dependent module"
        sg = SceneGraph(
            segment_id="seg", duration=5.0,
            nodes=[
                SceneNode(id="n1", type="image", appear_at=0.0, caption=CaptionSpec(text=long_caption)),
                SceneNode(id="n2", type="image", appear_at=3.0),
            ],
            edges=[SceneEdge(id="e1", from_node="n1", to_node="n2", draw_at=3.0)],
        )
        layout = compute_layout(sg, canvas_width=1920, canvas_height=1080)
        rect = layout.node_rects["n1"]  # 2-slot template (narrower) — this is where the real bug reproduced

        frame = render_node_reveal_frame(
            sg.nodes[0], rect, None, self.style, canvas_size=(1920, 1080), background="", progress=1.0,
        )
        white_bg = Image.new("RGBA", frame.size, (255, 255, 255, 255))
        white_bg.alpha_composite(frame)

        from scene_graph.composition import _CAPTION_FONT_CANDIDATES, _load_font, _wrap_caption_lines
        from PIL import ImageDraw

        font = _load_font(_CAPTION_FONT_CANDIDATES, min(34, max(14, int(rect.height * 0.09))))
        draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        lines = _wrap_caption_lines(draw, long_caption, font, rect.width, max_lines=2)
        self.assertEqual(len(lines), 2, "test assumes this caption wraps to exactly 2 lines")
        line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + 6

        import numpy as np

        arr = np.array(white_bg.convert("RGB"))
        second_line_y = int(rect.y2) + 10 + line_height
        band = arr[second_line_y: second_line_y + line_height, int(rect.x): int(rect.x2)]
        self.assertTrue((band < 200).any(), "the caption's second line did not render at all — it was clipped")

    def test_video_loop_card_caption_also_gets_enough_room(self):
        # The bottom-pad fix must not be conditioned on media type — a
        # video_loop card's hollow decoration still carries a caption below it.
        from scene_graph.composition import render_node_reveal_frame
        from scene_graph.layout import compute_layout
        from scene_graph.schema import CaptionSpec, SceneGraph, SceneNode

        sg = SceneGraph(
            segment_id="seg", duration=5.0,
            nodes=[SceneNode(id="n1", type="video_loop", appear_at=0.0,
                              caption=CaptionSpec(text="A faulty signal triggered repeated nose-down commands"))],
        )
        layout = compute_layout(sg, canvas_width=1920, canvas_height=1080)
        rect = layout.node_rects["n1"]
        # Should not raise, and should produce a non-trivial frame.
        frame = render_node_reveal_frame(
            sg.nodes[0], rect, None, self.style, canvas_size=(1920, 1080), background="", progress=1.0, hollow=True,
        )
        self.assertGreater(frame.split()[-1].getextrema()[1], 0)


class TestSmallSourceImageUpscalesToFillTheCard(CompositionTestBase):
    """PIL's Image.thumbnail() only ever shrinks — a source image smaller
    than its card rect was left stranded at native size instead of filling
    the (now generously-sized) card. render_node_reveal_frame at progress=1.0
    exercises the exact same _resize_to_fit() path as the real pipeline."""

    def test_tiny_source_image_fills_a_much_bigger_rect(self):
        from scene_graph.composition import render_node_reveal_frame
        from scene_graph.layout import NodeRect
        from scene_graph.schema import SceneNode

        tiny_path = self.tmp / "tiny.png"
        Image.new("RGB", (64, 36), (220, 20, 20)).save(tiny_path)  # far smaller than the rect below
        from scene_graph.composition import load_media_image

        media_image = load_media_image(str(tiny_path), self.tmp)
        node = SceneNode(id="n1", type="image")
        rect = NodeRect(node_id="n1", x=100, y=100, width=400, height=225)  # 16:9, much bigger than 64x36

        frame = render_node_reveal_frame(
            node, rect, media_image, self.style, canvas_size=(800, 600), background="", progress=1.0,
        )
        import numpy as np

        alpha = np.array(frame.split()[-1])
        box = alpha[int(rect.y) + 5:int(rect.y2) - 5, int(rect.x) + 5:int(rect.x2) - 5]
        coverage = (box > 200).mean()
        self.assertGreater(coverage, 0.95, "a small source image must be scaled UP to fill its (bigger) card rect")


class TestArrowsRender(CompositionTestBase):
    def test_edge_produces_a_visible_arrow_overlay(self):
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1200, canvas_height=800)
        assets = render_composition(sg, layout, self.style, resolved_media={}, out_dir=self.tmp / "arrows")
        self.assertEqual(set(assets.edge_overlay_paths.keys()), {"e_n3_n4", "e_n4_n5"})
        for edge_id, path in assets.edge_overlay_paths.items():
            overlay = Image.open(path).convert("RGBA")
            alpha = overlay.split()[-1]
            self.assertGreater(alpha.getextrema()[1], 0, f"{edge_id} overlay is fully transparent")

    def test_arrow_does_not_cross_either_cards_caption_band(self):
        # Regression: a center-to-center arrow on a diagonal 2-slot layout
        # routinely cut straight through the OTHER card's caption text.
        # The arrow must start/end at each card's own boundary (plus its
        # caption band), never inside that keep-out zone.
        import numpy as np

        from scene_graph.composition import render_edge_reveal_frame
        from scene_graph.layout import compute_layout
        from scene_graph.overscaled_csv import compile_overscaled_csv

        rows = [
            {"scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image",
             "asset_type": "flow_image", "caption": "A hidden dependency was built into the design"},
            {"scene_number": "2", "script_segment": "x", "node_id": "n2", "node_type": "image",
             "asset_type": "flow_image", "caption": "Larger engines forced a new wing position",
             "edge_from": "n1", "edge_to": "n2", "edge_label": "required larger engines"},
        ]
        result = compile_overscaled_csv(rows, segment_id="seg")
        sg = result.scene_graph
        layout = compute_layout(sg, canvas_width=1920, canvas_height=1080)
        from_rect, to_rect = layout.node_rects["n1"], layout.node_rects["n2"]
        edge = sg.edges[0]

        frame = render_edge_reveal_frame(
            edge, from_rect, to_rect, self.style, canvas_size=(1920, 1080), progress=1.0,
        )
        alpha = np.array(frame.split()[-1])

        for rect in (from_rect, to_rect):
            caption_band = alpha[
                int(rect.y2) + 2: int(rect.y2) + int(rect.height * 0.35),
                int(rect.x): int(rect.x2),
            ]
            self.assertEqual(
                int((caption_band > 40).sum()), 0,
                f"arrow/label ink found inside {rect.node_id}'s own caption band",
            )


class TestThreeCardChapterNeverOverlapsVisually(CompositionTestBase):
    """Regression for a real reported bug: a node's red `label` (drawn ABOVE
    its media rect) and black caption (drawn below) were only accounted for
    in composition's own local per-frame padding, never in the layout
    engine's slot geometry — so with a chapter title also on screen, a
    3-card chapter's hero caption visibly overlapped the neighboring card's
    label. This renders the FULL final composite (render_composition draws
    every node unconditionally, no time-gating) with a chapter_title + 3
    nodes each carrying both a label and a realistic multi-line caption —
    the exact combination from the bug report — and checks each node's own
    rendered ink (label + media + caption together) never overlaps another
    simultaneously-visible node's ink, using each node's real per-node
    overlay PNG's own non-transparent bounding box — no internal layout
    constants assumed, purely black-box pixel geometry."""

    def _three_card_scene_graph(self, *, with_chapter_title: bool):
        from scene_graph.schema import CaptionSpec, SceneEdge, SceneGraph, SceneNode, TitleCue

        nodes = [
            SceneNode(
                id="n1", type="image", appear_at=0.0, label="Vasa",
                caption=CaptionSpec(text="Sank on its maiden voyage in the harbor of Stockholm."),
            ),
            SceneNode(
                id="n2", type="image", appear_at=1.0, label="Harbor of Stockholm",
                caption=CaptionSpec(text="Taking 472 of its 497 crew members with it that day.", highlight="472,497"),
            ),
            SceneNode(
                id="n3", type="image", appear_at=2.0, label="Bay of Biscay",
                caption=CaptionSpec(text="Capsized and sank in the Bay of Biscay on September 7.", highlight="September 7"),
            ),
        ]
        edges = [
            SceneEdge(id="e1", from_node="n1", to_node="n2", draw_at=1.2),
            SceneEdge(id="e2", from_node="n1", to_node="n3", draw_at=2.2, kind="callout"),
        ]
        title_cues = [TitleCue(text="HMS Captain", at=0.0)] if with_chapter_title else []
        return SceneGraph(
            segment_id="seg", duration=6.0, nodes=nodes, edges=edges, title_cues=title_cues,
        )

    def _assert_no_node_ink_overlap(self, with_chapter_title: bool):
        sg = self._three_card_scene_graph(with_chapter_title=with_chapter_title)
        layout = compute_layout(sg, resolved_media=self._resolved_media(sg), canvas_width=1920, canvas_height=1080)
        assets = render_composition(
            sg, layout, self.style, resolved_media=self._resolved_media(sg), out_dir=self.tmp / f"t{with_chapter_title}",
        )

        boxes = {}
        for node_id, path in assets.node_overlay_paths.items():
            with Image.open(path) as im:
                bbox = im.split()[-1].getbbox()
            self.assertIsNotNone(bbox, f"node {node_id} rendered no visible ink at all")
            boxes[node_id] = bbox

        ids = list(boxes)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a_id, b_id = ids[i], ids[j]
                ax0, ay0, ax1, ay1 = boxes[a_id]
                bx0, by0, bx1, by1 = boxes[b_id]
                intersects = not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)
                self.assertFalse(
                    intersects,
                    f"{a_id} {boxes[a_id]} overlaps {b_id} {boxes[b_id]} "
                    f"(with_chapter_title={with_chapter_title}) — label/caption ink collision",
                )

    def test_no_overlap_with_a_chapter_title_present(self):
        # The tightest case: a TitleCue shrinks the available stage height
        # the most, which is exactly what triggered the reported bug.
        self._assert_no_node_ink_overlap(with_chapter_title=True)

    def test_no_overlap_without_a_chapter_title(self):
        self._assert_no_node_ink_overlap(with_chapter_title=False)


class TestRevealOverlaysAreIndependentPerAction(CompositionTestBase):
    def test_multi_action_beat_has_node_and_edge_overlays_available(self):
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1200, canvas_height=800)
        assets = render_composition(sg, layout, self.style, resolved_media={}, out_dir=self.tmp / "multi")
        beat5 = next(b for b in sg.beats if b.beat_id == "beat_5")
        action_types = {a.type for a in beat5.actions}
        self.assertEqual(action_types, {"reveal_node", "draw_edge", "move_camera"})
        reveal_action = next(a for a in beat5.actions if a.type == "reveal_node")
        draw_action = next(a for a in beat5.actions if a.type == "draw_edge")
        self.assertIn(reveal_action.node_id, assets.node_overlay_paths)
        self.assertIn(draw_action.edge_id, assets.edge_overlay_paths)


if __name__ == "__main__":
    unittest.main()
