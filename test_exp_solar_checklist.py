"""Exp Solar's checklist beat — a persistent 15-item progress/header strip:

    Exp Solar CSV (beat=checklist rows)
        -> scene_graph.exp_solar_csv.adapt_exp_solar_csv_rows()
        -> compile_overscaled_csv()            (SHARED, unmodified compiler)
        -> scene_graph.layout.compute_layout()  (checklist_item nodes excluded
                                                  from ordinary chaptering,
                                                  band reserved, checklist_windows
                                                  built)
        -> scene_graph.render.render_overscaled_segment()
           (_checklist_strip_layers -> composition.render_checklist_strip_frame)
        -> a REAL FFmpeg-rendered clip

No new SceneGraph, no new renderer: a checklist_item is an ordinary
SceneNode (new node TYPE only), excluded from chaptering the same way
"anchor" already is. Also proves four_row/index_grid/Overscaled remain
unaffected.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.composition import render_checklist_strip_frame
from scene_graph.exp_solar_csv import (
    CHECKLIST_MAX_ITEMS,
    SUPPORTED_BEATS,
    adapt_exp_solar_csv_rows,
    compile_exp_solar_csv,
)
from scene_graph.layout import CHECKLIST_BAND_PX, MAX_ACTIVE_PER_CHAPTER, compute_layout, find_overlaps
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline
from scene_graph.schema import SceneGraph, SceneNode

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _checklist_and_hero_rows(n=3):
    """n checklist items, each followed by one ordinary hero row for that
    item's actual content — the realistic, non-consecutive authoring
    pattern this beat is designed for."""
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "scene_number": str(len(rows) + 1), "script_segment": f"Now covering item {i}.",
            "node_id": f"chk{i}", "beat": "checklist", "chapter": f"Item {i}", "node_label": str(i),
        })
        rows.append({
            "scene_number": str(len(rows) + 1), "script_segment": f"Item {i}'s main narration content here.",
            "node_id": f"hero{i}", "beat": "hero", "asset_type": "flow_image", "prompt": f"hero {i}",
        })
    return rows


class TestChecklistAdapter(unittest.TestCase):
    def test_checklist_is_supported(self):
        self.assertIn("checklist", SUPPORTED_BEATS)

    def test_checklist_row_becomes_a_checklist_item_node_type(self):
        adapted = adapt_exp_solar_csv_rows(_checklist_and_hero_rows(3))
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertEqual(adapted.warnings, [])
        checklist_rows = [r for r in adapted.rows if r["node_id"].startswith("chk")]
        self.assertEqual(len(checklist_rows), 3)
        for row in checklist_rows:
            self.assertEqual(row["node_type"], "checklist_item")

    def test_node_label_precedence_label_then_chapter_then_generic(self):
        rows = [
            {"scene_number": "1", "script_segment": "x", "node_id": "a", "beat": "checklist",
             "node_label": "Explicit", "chapter": "Chapter Text"},
            {"scene_number": "2", "script_segment": "x", "node_id": "b", "beat": "checklist",
             "chapter": "Chapter Text Only"},
            {"scene_number": "3", "script_segment": "x", "node_id": "c", "beat": "checklist"},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertEqual(adapted.rows[0]["node_label"], "Explicit")
        self.assertEqual(adapted.rows[1]["node_label"], "Chapter Text Only")
        self.assertEqual(adapted.rows[2]["node_label"], "Item 3")

    def test_15_checklist_items_can_be_represented(self):
        rows = [
            {"scene_number": str(i), "script_segment": f"x{i}", "node_id": f"c{i}",
             "beat": "checklist", "node_label": str(i)}
            for i in range(1, 16)
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertEqual(adapted.warnings, [])
        self.assertEqual(sum(1 for r in adapted.rows if r["node_type"] == "checklist_item"), 15)

    def test_16th_checklist_row_downgrades_with_a_warning(self):
        rows = [
            {"scene_number": str(i), "script_segment": f"x{i}", "node_id": f"c{i}",
             "beat": "checklist", "node_label": str(i), "asset_type": "flow_image", "prompt": "p"}
            for i in range(1, 17)
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertTrue(adapted.warnings)
        self.assertIn("exceeds", adapted.warnings[0])
        checklist_count = sum(1 for r in adapted.rows if r["node_type"] == "checklist_item")
        self.assertEqual(checklist_count, CHECKLIST_MAX_ITEMS)
        self.assertEqual(adapted.rows[-1]["node_type"], "image")  # downgraded, not dropped

    def test_checklist_rows_need_no_grouping_edges(self):
        # Unlike four_row/index_grid, checklist items are excluded from
        # chaptering entirely — no "group"/"group_grid" edges should ever
        # be emitted for them.
        adapted = adapt_exp_solar_csv_rows(_checklist_and_hero_rows(3))
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertFalse(any(r.get("edge_style") in ("group", "group_grid") for r in adapted.rows))


class TestChecklistLayout(unittest.TestCase):
    def test_state_progression_is_deterministic(self):
        """Before an item: inactive. Current item: highlighted (index ==
        current). Previously completed: index < current. Remaining:
        inactive — purely a function of chapter/item appear_at order, not
        frame timing."""
        adapted = adapt_exp_solar_csv_rows(_checklist_and_hero_rows(3))
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        windows = layout.checklist_windows
        self.assertEqual(len(windows), 3)
        # Strictly increasing, back-to-back (no gaps, no overlaps) windows.
        for i in range(len(windows) - 1):
            self.assertAlmostEqual(windows[i][2], windows[i + 1][1], places=3)
        self.assertEqual([w[0] for w in windows], ["1", "2", "3"])

    def test_checklist_renders_for_exp_solar_style_only(self):
        # A plain Overscaled CSV never produces checklist_item nodes at
        # all (node_type is always an author-chosen value from a fixed,
        # pre-existing vocabulary in normal use) — checklist_windows stays
        # empty and the band stays 0 unless a node explicitly has
        # type="checklist_item", which only the Exp Solar adapter emits.
        rows = [
            {"scene_number": "1", "script_segment": "a", "node_id": "a", "node_type": "image",
             "asset_type": "flow_image", "prompt": "p"},
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        self.assertEqual(layout.checklist_windows, [])
        self.assertEqual(layout.checklist_band_px, 0.0)

    def test_main_visual_area_is_shifted_below_the_reserved_band(self):
        adapted = adapt_exp_solar_csv_rows(_checklist_and_hero_rows(1))
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        self.assertEqual(layout.checklist_band_px, CHECKLIST_BAND_PX)
        hero_rect = layout.node_rects["hero1"]
        self.assertGreaterEqual(hero_rect.y, CHECKLIST_BAND_PX)

    def test_no_overlap_between_checklist_items_and_main_content(self):
        adapted = adapt_exp_solar_csv_rows(_checklist_and_hero_rows(3))
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        # checklist_item nodes never get an ordinary NodeRect at all.
        checklist_ids = {n.id for n in compiled.scene_graph.nodes if n.type == "checklist_item"}
        self.assertTrue(checklist_ids)
        self.assertFalse(checklist_ids & set(layout.node_rects.keys()))
        self.assertEqual(find_overlaps(layout), [])

    def test_checklist_items_excluded_from_ordinary_chaptering(self):
        # Directly probe _connected_chapters-driven output: no chapter
        # should ever contain a checklist_item id.
        adapted = adapt_exp_solar_csv_rows(_checklist_and_hero_rows(3))
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        checklist_ids = {n.id for n in compiled.scene_graph.nodes if n.type == "checklist_item"}
        for chapter in layout.chapters:
            self.assertFalse(set(chapter) & checklist_ids)

    def test_overscaled_default_behavior_unchanged(self):
        rows = [
            {"scene_number": str(i), "script_segment": f"seg {i}", "node_id": f"m{i}",
             "node_type": "image", "asset_type": "flow_image", "prompt": "p",
             **({"edge_from": f"m{i}", "edge_to": f"m{i - 1}"} if i > 1 else {})}
            for i in range(1, 5)
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        self.assertEqual(layout.checklist_band_px, 0.0)
        events = sorted((w[0], 1) for w in layout.active_windows.values())
        events += sorted((w[1], -1) for w in layout.active_windows.values())
        events.sort()
        running = peak = 0
        for _, delta in events:
            running += delta
            peak = max(peak, running)
        self.assertLessEqual(peak, MAX_ACTIVE_PER_CHAPTER)


class TestChecklistStripFrame(unittest.TestCase):
    def test_current_item_is_highlighted_completed_are_darker_upcoming_are_grey(self):
        from scene_graph.composition import (
            _CHECKLIST_COMPLETED_FILL,
            _CHECKLIST_CURRENT_FILL,
            _CHECKLIST_INACTIVE_FILL,
        )

        labels = ["1", "2", "3", "4"]
        frame = render_checklist_strip_frame(
            labels, 2, canvas_size=(1920, 1080), band_height=110, margin_px=60,
        )
        stage_w = 1920 - 120
        cell_w = stage_w / 4
        y = 20  # inside the cell body, above the centered number glyph
        px = lambda i: frame.getpixel((int(60 + i * cell_w + cell_w / 2), y))
        self.assertEqual(px(0)[:3], _CHECKLIST_COMPLETED_FILL[:3])
        self.assertEqual(px(1)[:3], _CHECKLIST_COMPLETED_FILL[:3])
        self.assertEqual(px(2)[:3], _CHECKLIST_CURRENT_FILL[:3])
        self.assertEqual(px(3)[:3], _CHECKLIST_INACTIVE_FILL[:3])

    def test_empty_labels_returns_transparent_frame(self):
        frame = render_checklist_strip_frame([], 0, canvas_size=(1920, 1080), band_height=110, margin_px=60)
        self.assertEqual(frame.getpixel((100, 50))[3], 0)  # fully transparent alpha


class TestChecklistVisualPlanCompile(unittest.TestCase):
    def test_compile_exp_solar_csv_exposes_all_rows(self):
        result = compile_exp_solar_csv(_checklist_and_hero_rows(3), segment_id="seg", title="t")
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.scene_graph.style_preset, "exp_solar")
        self.assertEqual(len(result.scene_graph.nodes), 6)  # 3 checklist + 3 hero


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestChecklistRealRender(unittest.TestCase):
    """The acceptance test: a real Exp Solar CSV with checklist rows,
    through the exact render entry point (run_overscaled_pipeline, under
    style_preset_id="exp_solar"), produces a real, playable clip whose
    frames actually contain the strip's highlight color."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _make_sine_wav(self, path: Path, duration_s: float) -> None:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={max(0.5, duration_s):.2f}", str(path)],
            check=True, capture_output=True,
        )

    def test_checklist_csv_renders_a_real_clip_containing_the_strip(self):
        rows = _checklist_and_hero_rows(3)
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
            if node.type == "checklist_item":
                continue
            p = media_dir / f"{node.id}.png"
            Image.new("RGB", (640, 360), (30, 30, 30)).save(p)
            resolved_media[node.id] = str(p)

        out_dir = self.tmp / "out"
        result = run_overscaled_pipeline(
            adapted.rows, segment_id="seg", title="Checklist Test",
            style_preset_id="exp_solar", voiceover_path=str(voiceover), out_dir=out_dir,
            resolved_media=resolved_media, canvas_width=1920, canvas_height=1080,
            resolution="1920x1080", fps=10,
        )
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.segment_clip_path.is_file())
        self.assertGreater(result.layout.checklist_band_px, 0.0)
        self.assertEqual(len(result.layout.checklist_windows), 3)

        # Extract a real frame during item 1's window and confirm the
        # strip's current-item highlight color is actually present.
        frame_path = self.tmp / "frame.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "0.5", "-i", str(result.segment_clip_path), "-frames:v", "1", str(frame_path)],
            check=True, capture_output=True,
        )
        frame = Image.open(frame_path)
        from scene_graph.composition import _CHECKLIST_CURRENT_FILL

        # H.264 (even at -crf 20) is lossy — exact RGB match after encode/
        # decode is unreliable, so compare with a small per-channel tolerance.
        target = _CHECKLIST_CURRENT_FILL[:3]
        found = False
        for x in range(50, 400, 10):
            px = frame.getpixel((x, 20))[:3]
            if all(abs(px[c] - target[c]) <= 15 for c in range(3)):
                found = True
                break
        self.assertTrue(found, "expected the checklist strip's highlighted current-item color in the real render")


if __name__ == "__main__":
    unittest.main()
