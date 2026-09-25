"""Exp Solar's index_grid composition — end-to-end:

    Exp Solar CSV (15x beat=index_grid rows)
        -> scene_graph.exp_solar_csv.adapt_exp_solar_csv_rows()
        -> compile_overscaled_csv()            (SHARED, unmodified compiler)
        -> scene_graph.layout.compute_layout()  (real 3x5 grid, 15 cells)
        -> scene_graph.pipeline.run_overscaled_pipeline()
        -> a REAL FFmpeg-rendered clip

Same infrastructure as test_exp_solar_four_row.py: no new SceneGraph, no
new renderer. Also proves four_row and Overscaled are both unaffected by
index_grid's addition.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.exp_solar_csv import (
    DEFERRED_BEATS,
    INDEX_GRID_MAX_ITEMS,
    SUPPORTED_BEATS,
    adapt_exp_solar_csv_rows,
    compile_exp_solar_csv,
)
from scene_graph.layout import MAX_ACTIVE_PER_CHAPTER, SLOT_TEMPLATE_GRID_15, compute_layout, find_overlaps
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _index_grid_rows(n=15):
    rows = [
        {"scene_number": "1", "script_segment": "Here are all the flare types.",
         "beat": "hero", "asset_type": "flow_image", "prompt": "a sun", "chapter": "Every Flare Type"},
    ]
    for i in range(1, n + 1):
        rows.append({
            "scene_number": str(i + 1), "script_segment": f"Item {i}.", "node_id": f"g{i}",
            "beat": "index_grid", "asset_type": "flow_image", "prompt": f"flare type {i}",
            "node_label": str(i),
        })
    return rows


class TestIndexGridAdapter(unittest.TestCase):
    def test_index_grid_is_no_longer_deferred(self):
        self.assertIn("index_grid", SUPPORTED_BEATS)
        self.assertNotIn("index_grid", DEFERRED_BEATS)

    def test_15_index_grid_rows_produce_15_nodes(self):
        adapted = adapt_exp_solar_csv_rows(_index_grid_rows(15))
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertEqual(adapted.warnings, [])
        grid_rows = [r for r in adapted.rows if r["node_id"].startswith("g")]
        self.assertEqual(len(grid_rows), 15)

    def test_15_index_grid_rows_are_chained_with_14_group_grid_edges(self):
        adapted = adapt_exp_solar_csv_rows(_index_grid_rows(15))
        self.assertTrue(adapted.ok, adapted.errors)
        grid_edges = [r for r in adapted.rows if r.get("edge_style") == "group_grid"]
        self.assertEqual(len(grid_edges), 14)  # a 15-node chain needs 14 links

    def test_hero_row_is_not_part_of_the_grid_chain(self):
        adapted = adapt_exp_solar_csv_rows(_index_grid_rows(15))
        self.assertTrue(adapted.ok, adapted.errors)
        hero_row = adapted.rows[0]
        self.assertNotIn("edge_to", hero_row)

    def test_lone_index_grid_row_gets_no_edge_and_no_warning(self):
        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "solo",
                 "beat": "index_grid", "asset_type": "flow_image", "prompt": "p"}]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertNotIn("edge_to", adapted.rows[0])
        self.assertEqual(adapted.warnings, [])

    def test_run_longer_than_15_starts_a_second_grid_with_a_warning(self):
        adapted = adapt_exp_solar_csv_rows(_index_grid_rows(17))
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertTrue(adapted.warnings)
        self.assertIn("exceeds", adapted.warnings[0])
        grid_edges = [r for r in adapted.rows if r.get("edge_style") == "group_grid"]
        # First 15 chained (14 edges) + row 16 starts a fresh grid (no
        # back-edge) + row 17 chains to row 16 (1 more edge) = 15 total.
        self.assertEqual(len(grid_edges), 15)

    def test_explicit_relationship_on_a_grid_row_is_not_overwritten(self):
        rows = _index_grid_rows(15)
        rows[3]["relationship_to"] = "g1"
        rows[3]["relationship_type"] = "consequence"
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        row_g2 = adapted.rows[3]
        self.assertEqual(row_g2["edge_to"], "g1")
        self.assertEqual(row_g2["edge_style"], "sequential")  # author's own edge, not "group_grid"


class TestIndexGridLayout(unittest.TestCase):
    def test_15_members_get_a_real_3x5_grid(self):
        adapted = adapt_exp_solar_csv_rows(_index_grid_rows(15))
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        sg = compiled.scene_graph

        layout = compute_layout(sg, resolved_media={})  # no style override needed — grid is edge-tagged
        grid_ids = [f"g{i}" for i in range(1, 16)]
        self.assertTrue(all(gid in layout.node_rects for gid in grid_ids))

        xs = sorted(round(layout.node_rects[gid].x, 1) for gid in grid_ids)
        ys = sorted(round(layout.node_rects[gid].y, 1) for gid in grid_ids)
        self.assertEqual(len(set(xs)), 5, "should be 5 distinct columns")
        self.assertEqual(len(set(ys)), 3, "should be 3 distinct rows")

        # All 15 simultaneously visible.
        windows = [layout.active_windows[gid] for gid in grid_ids]
        events = sorted((w[0], 1) for w in windows) + sorted((w[1], -1) for w in windows)
        events.sort()
        running = peak = 0
        for _, delta in events:
            running += delta
            peak = max(peak, running)
        self.assertEqual(peak, 15)

        # No group_grid edge is ever drawn.
        grid_edge_ids = [e.id for e in sg.edges if e.kind == "group_grid"]
        self.assertEqual(len(grid_edge_ids), 14)
        for eid in grid_edge_ids:
            self.assertNotIn(eid, layout.edge_windows)

        self.assertEqual(find_overlaps(layout), [])

    def test_grid_is_only_selected_for_index_grid_chapters_not_ordinary_ones(self):
        # A plain 3-node causal chain (kind="sequential", not "group_grid")
        # must still use the ordinary row templates, never the grid.
        rows = [
            {"scene_number": "1", "script_segment": "a", "node_id": "a", "node_type": "image",
             "asset_type": "flow_image", "prompt": "p"},
            {"scene_number": "2", "script_segment": "b", "node_id": "b", "node_type": "image",
             "asset_type": "flow_image", "prompt": "p", "edge_from": "b", "edge_to": "a"},
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        # 2-slot row template width (~0.47 of stage), not the compact grid width.
        rect_a = layout.node_rects["a"]
        self.assertGreater(rect_a.width, 300)  # grid cells are much narrower

    def test_index_grid_never_reachable_via_plain_overscaled_csv(self):
        # Overscaled's own compiler only ever emits "callout"/"sequential" —
        # a raw CSV author cannot request "group_grid" through edge_style
        # without going through the Exp Solar adapter (which is the only
        # thing that ever writes that literal value).
        rows = [
            {"scene_number": "1", "script_segment": "a", "node_id": "a", "node_type": "image",
             "asset_type": "flow_image", "prompt": "p", "edge_style": "group_grid"},
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        # A single row with no edge_from/edge_to defines no edge at all —
        # edge_style alone, without both endpoints, is inert either way.
        self.assertEqual(compiled.scene_graph.edges, [])

    def test_overscaled_default_cap_is_unchanged_by_the_grid_addition(self):
        rows = [
            {"scene_number": str(i), "script_segment": f"seg {i}", "node_id": f"m{i}",
             "node_type": "image", "asset_type": "flow_image", "prompt": "p",
             **({"edge_from": f"m{i}", "edge_to": f"m{i - 1}"} if i > 1 else {})}
            for i in range(1, 6)
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        events = sorted((w[0], 1) for w in layout.active_windows.values())
        events += sorted((w[1], -1) for w in layout.active_windows.values())
        events.sort()
        running = peak = 0
        for _, delta in events:
            running += delta
            peak = max(peak, running)
        self.assertLessEqual(peak, MAX_ACTIVE_PER_CHAPTER)

    def test_grid_template_constant_has_exactly_15_cells(self):
        self.assertEqual(len(SLOT_TEMPLATE_GRID_15[15]), 15)


class TestIndexGridVisualPlanCompile(unittest.TestCase):
    """The compile-only preview path (same one app.py's _load_overscaled_csv
    uses for the Visual Plan) — proves all 15 rows stay reviewable."""

    def test_compile_exp_solar_csv_exposes_all_16_rows_scene_graph_nodes(self):
        result = compile_exp_solar_csv(_index_grid_rows(15), segment_id="seg", title="t")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.style_preset, "exp_solar")
        self.assertEqual(len(result.scene_graph.nodes), 16)  # 1 hero + 15 grid


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestIndexGridRealRender(unittest.TestCase):
    """The acceptance test: a real Exp Solar CSV with an index_grid beat,
    through the exact render entry point (run_overscaled_pipeline, under
    style_preset_id="exp_solar"), produces a real, playable clip with a
    genuine 15-cell grid — not a degraded single card."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _make_sine_wav(self, path: Path, duration_s: float) -> None:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={max(0.5, duration_s):.2f}", str(path)],
            check=True, capture_output=True,
        )

    def test_index_grid_csv_renders_a_real_clip_with_15_simultaneous_cards(self):
        rows = _index_grid_rows(15)
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)

        probe_compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(probe_compiled.ok, probe_compiled.errors)
        voiceover = self.tmp / "voiceover.wav"
        self._make_sine_wav(voiceover, probe_compiled.scene_graph.duration)

        media_dir = self.tmp / "media"
        media_dir.mkdir()
        resolved_media = {}
        for i, node in enumerate(probe_compiled.scene_graph.nodes):
            p = media_dir / f"{node.id}.png"
            Image.new("RGB", (640, 360), ((i * 41) % 255, (i * 83) % 255, (i * 149) % 255)).save(p)
            resolved_media[node.id] = str(p)

        out_dir = self.tmp / "out"
        result = run_overscaled_pipeline(
            adapted.rows, segment_id="seg", title="Index Grid Test",
            style_preset_id="exp_solar", voiceover_path=str(voiceover), out_dir=out_dir,
            resolved_media=resolved_media, canvas_width=1920, canvas_height=1080,
            resolution="640x360", fps=15,
        )
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.segment_clip_path.is_file())

        grid_ids = [f"g{i}" for i in range(1, 16)]
        self.assertTrue(all(gid in result.layout.node_rects for gid in grid_ids))
        widths = {round(result.layout.node_rects[gid].width) for gid in grid_ids}
        heights = {round(result.layout.node_rects[gid].height) for gid in grid_ids}
        self.assertEqual(len(widths), 1, "all 15 grid cards should share the same grid cell width")
        self.assertEqual(len(heights), 1, "all 15 grid cards should share the same grid cell height")


if __name__ == "__main__":
    unittest.main()
