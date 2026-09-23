"""Tests for scene_graph/layout.py — the fixed-canvas deterministic grid.

scene_graph/camera.py was removed along with the camera-pan/zoom rendering
architecture (see scene_graph/render.py's module docstring): the Overscaled
canvas is now fixed at the output resolution and never moves, so there is no
camera geometry left to resolve or test here.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from scene_graph.layout import compute_layout, find_overlaps
from scene_graph.overscaled_csv import compile_overscaled_csv

FIXTURE = Path(__file__).resolve().parent / "overscaled_sample.csv"


def _fixture_scene_graph():
    with open(FIXTURE, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = compile_overscaled_csv(rows, segment_id="aurora_bridge")
    assert result.ok, result.errors
    return result.scene_graph


class TestLayoutDeterminism(unittest.TestCase):
    def test_same_scene_graph_produces_identical_layout(self):
        sg = _fixture_scene_graph()
        layout1 = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        layout2 = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        self.assertEqual(layout1.to_dict(), layout2.to_dict())

    def test_layout_round_trips(self):
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        from scene_graph.layout import SceneGraphLayout

        restored = SceneGraphLayout.from_dict(layout.to_dict())
        self.assertEqual(restored.to_dict(), layout.to_dict())


class TestLayoutNoOverlap(unittest.TestCase):
    def test_no_overlapping_nodes_beyond_tolerance(self):
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        self.assertEqual(find_overlaps(layout, tolerance=0.5), [])

    def test_every_node_has_a_rect_within_canvas_bounds(self):
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        for node in sg.nodes:
            rect = layout.node_rects[node.id]
            self.assertGreaterEqual(rect.x, 0)
            self.assertGreaterEqual(rect.y, 0)
            self.assertLessEqual(rect.x2, layout.canvas_width)
            self.assertLessEqual(rect.y2, layout.canvas_height)


class TestAspectRatioPreserved(unittest.TestCase):
    def test_node_rect_matches_resolved_media_aspect_ratio(self):
        import tempfile

        from PIL import Image

        tmp = Path(tempfile.mkdtemp())
        wide_path = tmp / "wide.png"
        Image.new("RGB", (1600, 400), (10, 10, 10)).save(wide_path)  # 4:1 aspect

        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "n1", "node_type": "image", "asset_type": "flow_image"}]
        result = compile_overscaled_csv(rows, segment_id="seg")
        sg = result.scene_graph
        layout = compute_layout(sg, resolved_media={"n1": str(wide_path)}, canvas_width=1600, canvas_height=1000)
        rect = layout.node_rects["n1"]
        self.assertAlmostEqual(rect.width / rect.height, 4.0, delta=0.05)


class TestCausalChainSpatiallyReadable(unittest.TestCase):
    def test_causally_connected_nodes_share_one_chapter(self):
        # n3 -(edge)-> n4 -(edge)-> n5 in the fixture: one connected causal
        # chain that should be grouped into the SAME chapter (shown together,
        # on screen at once) — n1/n2/n6 have no edges, so each is its own
        # one-member chapter, never sharing a chapter with the chain.
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        chain_chapter = next(c for c in layout.chapters if "n3" in c)
        self.assertEqual(set(chain_chapter), {"n3", "n4", "n5"})
        for solo_id in ("n1", "n2", "n6"):
            solo_chapter = next(c for c in layout.chapters if solo_id in c)
            self.assertEqual(solo_chapter, [solo_id])

    def test_nodes_in_the_same_chapter_are_spatially_close(self):
        # Chapter-mates share the same small stage — their centers should be
        # much closer to each other than the stage's own full diagonal.
        import math

        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)

        def dist(a, b):
            return math.hypot(a.center[0] - b.center[0], a.center[1] - b.center[1])

        flaw_rect = layout.node_rects["n3"]
        failure_rect = layout.node_rects["n4"]
        stage_diagonal = math.hypot(layout.canvas_width, layout.canvas_height)
        self.assertLess(dist(flaw_rect, failure_rect), stage_diagonal * 0.6)

    def test_unrelated_nodes_do_not_appear_on_screen_at_the_same_time(self):
        # n1 (solo) and the n3/n4/n5 chain are unrelated — their active
        # windows must not overlap, i.e. the board never shows both at once.
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        n1_start, n1_end = layout.active_windows["n1"]
        n3_start, n3_end = layout.active_windows["n3"]
        self.assertTrue(n1_end <= n3_start or n3_end <= n1_start)

    def test_at_most_three_content_cards_are_ever_simultaneously_active(self):
        # The core "controlled density" acceptance rule: sample many
        # timestamps across the whole segment and confirm the active set
        # (excluding always-persistent anchors) never exceeds 3.
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        anchor_ids = {n.id for n in sg.nodes if n.type == "anchor"}
        samples = [sg.duration * f / 100.0 for f in range(0, 101, 2)]
        for t in samples:
            active = [
                nid for nid, (start, end) in layout.active_windows.items()
                if nid not in anchor_ids and start <= t < end
            ]
            self.assertLessEqual(len(active), 3, f"too many simultaneous cards at t={t}: {active}")


class TestInterleavedChaptersNeverOverlap(unittest.TestCase):
    """Regression for a real bug hit in production: chapters are formed by
    EDGE CONNECTIVITY, but the old per-chapter windowing assumed chapters
    also occupy non-overlapping, LIST-ORDER-CONTIGUOUS time blocks — false
    whenever (a) an isolated node with no edges is authored chronologically
    between two members of an unrelated, ongoing causal chain, or (b) a
    chapter deliberately sets something up early and pays it off much later
    (a supported pattern — see TestUnrelatedChaptersReplaceEachOther),
    letting an entirely different chapter's whole span fit in the gap. Both
    used to render simultaneously; see scene_graph/layout.py's
    compute_layout for the fix (a single global chronological sweep)."""

    def _isolated_node_interleaved_scene_graph(self):
        from scene_graph.schema import SceneEdge, SceneGraph, SceneNode

        nodes = [
            SceneNode(id="chain_a", type="image", appear_at=0.0),
            SceneNode(id="chain_b", type="image", appear_at=2.0),
            # Isolated: no edges at all, authored chronologically BETWEEN
            # chain_b and chain_c even though chain_a/b/c are one causal
            # chain (the exact real-world pattern: an LLM-authored CSV row
            # for a same-beat companion detail, missing its own edge).
            SceneNode(id="isolated", type="image", appear_at=3.0),
            SceneNode(id="chain_c", type="image", appear_at=5.0),
        ]
        edges = [
            SceneEdge(id="e_ab", from_node="chain_a", to_node="chain_b", draw_at=2.0),
            SceneEdge(id="e_bc", from_node="chain_b", to_node="chain_c", draw_at=5.0),
        ]
        return SceneGraph(segment_id="seg", duration=10.0, nodes=nodes, edges=edges)

    def test_isolated_node_interleaved_inside_a_causal_chain_does_not_overlap_it(self):
        sg = self._isolated_node_interleaved_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        self.assertEqual(len(layout.chapters), 2, "isolated + the 3-member chain must be 2 chapters")

        samples = [sg.duration * f / 1000.0 for f in range(0, 1001)]
        chapter_of = {nid: i for i, members in enumerate(layout.chapters) for nid in members}
        for t in samples:
            active_chapters = {
                chapter_of[nid] for nid, (s, e) in layout.active_windows.items() if s <= t < e
            }
            self.assertLessEqual(
                len(active_chapters), 1, f"more than one chapter simultaneously active at t={t}: {active_chapters}"
            )

    def test_isolated_node_is_not_swallowed_by_whichever_chapter_reappears_next(self):
        # The specific symptom from the bug report: the isolated node's
        # window must end when the causal chain's NEXT member (chain_c)
        # reaches its own appear_at, not run all the way to the segment end
        # or past chain_c's own start.
        sg = self._isolated_node_interleaved_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        iso_start, iso_end = layout.active_windows["isolated"]
        chain_c_start, _ = layout.active_windows["chain_c"]
        self.assertAlmostEqual(iso_start, 3.0, places=3)
        self.assertLessEqual(iso_end, chain_c_start + 1e-9)

    def test_a_chapter_that_pays_off_much_later_does_not_overlap_a_chapter_nested_in_the_gap(self):
        # The OTHER half of the same real bug: chain_a/b set up early, but
        # the SAME chapter's causal arrow only pays off much later
        # (chain_c at t=8, long after an entirely unrelated chapter (solo)
        # has come and gone in between) — a deliberate, supported pattern.
        # The unrelated chapter nested in that gap must not overlap either
        # half of the interrupted chain.
        from scene_graph.schema import SceneEdge, SceneGraph, SceneNode

        nodes = [
            SceneNode(id="chain_a", type="image", appear_at=0.0),
            SceneNode(id="chain_b", type="image", appear_at=2.0),
            SceneNode(id="solo", type="image", appear_at=4.0),
            SceneNode(id="chain_c", type="image", appear_at=8.0),
        ]
        edges = [
            SceneEdge(id="e_ab", from_node="chain_a", to_node="chain_b", draw_at=2.0),
            SceneEdge(id="e_bc", from_node="chain_b", to_node="chain_c", draw_at=8.0),
        ]
        sg = SceneGraph(segment_id="seg", duration=12.0, nodes=nodes, edges=edges)
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)

        solo_start, solo_end = layout.active_windows["solo"]
        chain_b_start, chain_b_end = layout.active_windows["chain_b"]
        chain_c_start, chain_c_end = layout.active_windows["chain_c"]
        self.assertLessEqual(chain_b_end, solo_start + 1e-9)
        self.assertLessEqual(solo_end, chain_c_start + 1e-9)
        self.assertGreaterEqual(chain_c_start, solo_end - 1e-9)


class TestArrowDensityCapped(unittest.TestCase):
    """Arrows are a momentary "look at this connection" cue, not a
    permanent web — an older arrow must hard-cut away once enough newer
    ones have been drawn, so the canvas is never criss-crossed with every
    causal link accumulated so far."""

    def test_long_chain_never_shows_more_than_max_active_edges_at_once(self):
        from scene_graph.layout import MAX_ACTIVE_EDGES
        from scene_graph.schema import SceneEdge, SceneGraph, SceneNode

        nodes = [SceneNode(id=f"n{i}", type="image", appear_at=float(i) * 1.5) for i in range(6)]
        edges = [
            SceneEdge(id=f"e{i}", from_node=f"n{i}", to_node=f"n{i + 1}", draw_at=float(i + 1) * 1.5)
            for i in range(5)
        ]
        sg = SceneGraph(segment_id="seg", duration=12.0, nodes=nodes, edges=edges)
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)

        samples = [sg.duration * f / 100.0 for f in range(0, 101, 2)]
        for t in samples:
            active_edges = [eid for eid, (s, e) in layout.edge_windows.items() if s <= t < e]
            self.assertLessEqual(
                len(active_edges), MAX_ACTIVE_EDGES, f"too many simultaneous arrows at t={t}: {active_edges}"
            )

    def test_earliest_edge_is_gone_once_later_edges_have_taken_over(self):
        from scene_graph.schema import SceneEdge, SceneGraph, SceneNode

        nodes = [SceneNode(id=f"n{i}", type="image", appear_at=float(i) * 1.5) for i in range(6)]
        edges = [
            SceneEdge(id=f"e{i}", from_node=f"n{i}", to_node=f"n{i + 1}", draw_at=float(i + 1) * 1.5)
            for i in range(5)
        ]
        sg = SceneGraph(segment_id="seg", duration=12.0, nodes=nodes, edges=edges)
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        e0_start, e0_end = layout.edge_windows["e0"]
        self.assertLess(e0_end, sg.duration, "the first arrow must not persist forever alongside every later one")


class TestPersistentChapterTitleAndAnchor(unittest.TestCase):
    """Per the real "Overscaled" reference style: a subject's bold title AND
    its small anchor icon persist for that subject's whole segment, then get
    replaced together — not one global anchor for the entire video."""

    def _two_ship_rows(self):
        return [
            {"scene_number": "1", "script_segment": "The Vasa was a warship built in Sweden.",
             "node_id": "n1", "node_type": "image", "asset_type": "flow_image", "chapter_title": "Vasa"},
            {"scene_number": "2", "script_segment": "It sank on its maiden voyage in the harbor.",
             "node_id": "anchor1", "node_type": "anchor", "asset_type": "flow_image"},
            {"scene_number": "3", "script_segment": "HMS Captain later suffered a similar fate at sea.",
             "node_id": "n2", "node_type": "image", "asset_type": "flow_image", "chapter_title": "HMS Captain"},
            {"scene_number": "4", "script_segment": "A second small icon marks this new ship clearly.",
             "node_id": "anchor2", "node_type": "anchor", "asset_type": "flow_image"},
        ]

    def test_title_window_spans_until_the_next_title(self):
        result = compile_overscaled_csv(self._two_ship_rows(), segment_id="seg")
        sg = result.scene_graph
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        self.assertEqual(len(layout.title_windows), 2)
        (text1, start1, end1), (text2, start2, end2) = layout.title_windows
        self.assertEqual((text1, text2), ("Vasa", "HMS Captain"))
        self.assertAlmostEqual(end1, start2, places=3)
        self.assertAlmostEqual(end2, sg.duration, places=3)

    def test_second_anchor_replaces_the_first_rather_than_stacking(self):
        result = compile_overscaled_csv(self._two_ship_rows(), segment_id="seg")
        sg = result.scene_graph
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        anchor1_start, anchor1_end = layout.active_windows["anchor1"]
        anchor2_start, anchor2_end = layout.active_windows["anchor2"]
        self.assertAlmostEqual(anchor1_end, anchor2_start, places=3)
        self.assertAlmostEqual(anchor2_end, sg.duration, places=3)
        # Same physical slot (they're time-disjoint, so reusing it is correct).
        r1, r2 = layout.node_rects["anchor1"], layout.node_rects["anchor2"]
        self.assertEqual((r1.x, r1.y, r1.width, r1.height), (r2.x, r2.y, r2.width, r2.height))

    def test_single_anchor_csv_still_persists_to_the_end_as_before(self):
        # Backward compatibility: a CSV with only ONE anchor (like the
        # existing sample fixture) must behave exactly as before this change.
        sg = _fixture_scene_graph()
        layout = compute_layout(sg, canvas_width=1600, canvas_height=1000)
        start, end = layout.active_windows["anchor1"]
        self.assertAlmostEqual(end, sg.duration, places=3)


if __name__ == "__main__":
    unittest.main()
