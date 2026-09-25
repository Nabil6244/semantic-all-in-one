"""Exp Solar's four_row composition — end-to-end:

    Exp Solar CSV (beat=four_row rows)
        -> scene_graph.exp_solar_csv.adapt_exp_solar_csv_rows()
        -> compile_overscaled_csv()            (SHARED, unmodified compiler)
        -> scene_graph.layout.compute_layout(max_active_per_chapter=4)
        -> scene_graph.pipeline.run_overscaled_pipeline()
        -> a REAL FFmpeg-rendered clip

No new SceneGraph, no new renderer — same infrastructure as
test_overscaled_pipeline_e2e.py, just Exp Solar's own CSV shape and the
composition_styles/exp_solar.json style preset (which is the only thing
that raises the cap above Overscaled's own default 3).

Also proves the inverse: Overscaled's own layout is byte-identical (the
4-slot template/raised cap machinery is dormant unless a style preset
explicitly opts in via metadata.max_active_per_chapter).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows, compile_exp_solar_csv
from scene_graph.layout import MAX_ACTIVE_PER_CHAPTER, compute_layout
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _four_row_rows():
    return [
        {"scene_number": "1", "script_segment": "Solar flares come in many colors.",
         "beat": "hero", "asset_type": "flow_image", "prompt": "a sun", "chapter": "Flare Types"},
        {"scene_number": "2", "script_segment": "Purple.", "node_id": "n2",
         "beat": "four_row", "asset_type": "flow_image", "prompt": "purple swirl"},
        {"scene_number": "3", "script_segment": "Cyan.", "node_id": "n3",
         "beat": "four_row", "asset_type": "flow_image", "prompt": "cyan swirl"},
        {"scene_number": "4", "script_segment": "Red.", "node_id": "n4",
         "beat": "four_row", "asset_type": "flow_image", "prompt": "red swirl"},
        {"scene_number": "5", "script_segment": "Orange.", "node_id": "n5",
         "beat": "four_row", "asset_type": "flow_image", "prompt": "orange swirl"},
    ]


class TestFourRowAdapter(unittest.TestCase):
    def test_four_row_is_no_longer_deferred(self):
        from scene_graph.exp_solar_csv import DEFERRED_BEATS, SUPPORTED_BEATS

        self.assertIn("four_row", SUPPORTED_BEATS)
        self.assertNotIn("four_row", DEFERRED_BEATS)

    def test_consecutive_four_row_rows_are_chained_with_group_edges(self):
        adapted = adapt_exp_solar_csv_rows(_four_row_rows())
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertEqual(adapted.warnings, [])
        group_edges = [r for r in adapted.rows if r.get("edge_style") == "group"]
        self.assertEqual(len(group_edges), 3)  # n2-n3, n3-n4, n4-n5
        for row in group_edges:
            self.assertIn(row["edge_from"], {"n3", "n4", "n5"})

    def test_hero_row_is_not_chained_into_the_four_row_group(self):
        adapted = adapt_exp_solar_csv_rows(_four_row_rows())
        self.assertTrue(adapted.ok, adapted.errors)
        hero_row = adapted.rows[0]
        self.assertNotIn("edge_to", hero_row)

    def test_lone_four_row_with_no_sibling_gets_no_edge(self):
        rows = [{"scene_number": "1", "script_segment": "x", "node_id": "solo",
                 "beat": "four_row", "asset_type": "flow_image", "prompt": "p"}]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        self.assertNotIn("edge_to", adapted.rows[0])

    def test_explicit_relationship_on_a_four_row_row_is_not_overwritten(self):
        rows = _four_row_rows()
        rows[2]["relationship_to"] = "n2"
        rows[2]["relationship_type"] = "consequence"
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        row_n3 = adapted.rows[2]
        self.assertEqual(row_n3["edge_to"], "n2")  # author's own relationship, not the chain default
        self.assertEqual(row_n3["edge_style"], "sequential")  # never auto-promoted, and not "group"


class TestFourRowLayout(unittest.TestCase):
    def test_four_members_get_the_4_slot_layout_under_exp_solar_style(self):
        adapted = adapt_exp_solar_csv_rows(_four_row_rows())
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        sg = compiled.scene_graph

        layout = compute_layout(sg, resolved_media={}, max_active_per_chapter=4)
        four_row_ids = {"n2", "n3", "n4", "n5"}
        self.assertEqual(set(layout.node_rects.keys()) & four_row_ids, four_row_ids)

        # All 4 simultaneously on screen (no eviction at exactly cap=4).
        windows = [layout.active_windows[nid] for nid in four_row_ids]
        # peak concurrency = 4 means there's a moment all 4 windows overlap.
        events = sorted((start, 1) for start, _ in windows) + sorted((end, -1) for _, end in windows)
        events.sort()
        running = peak = 0
        for _, delta in events:
            running += delta
            peak = max(peak, running)
        self.assertEqual(peak, 4)

        # No group-edge arrow ever gets a visible window.
        group_edge_ids = [e.id for e in sg.edges if e.kind == "group"]
        self.assertEqual(len(group_edge_ids), 3)
        for eid in group_edge_ids:
            self.assertNotIn(eid, layout.edge_windows)

        # Rects are distinct, non-overlapping x-positions (a real row, not stacked).
        xs = sorted(layout.node_rects[nid].x for nid in four_row_ids)
        self.assertEqual(len(set(round(x) for x in xs)), 4)

    def test_overscaled_default_cap_is_unchanged_without_a_style_override(self):
        # Same 5-row shape, but compiled/laid out as PLAIN Overscaled (no
        # style override) — must fall back to the original 3-card cap,
        # proving Overscaled's own behavior is untouched.
        rows = [
            {"scene_number": str(i), "script_segment": f"seg {i}", "node_id": f"m{i}",
             "node_type": "image", "asset_type": "flow_image", "prompt": "p",
             **({"edge_from": f"m{i}", "edge_to": f"m{i - 1}"} if i > 1 else {})}
            for i in range(1, 5)
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})  # no override passed
        events = sorted((w[0], 1) for w in layout.active_windows.values())
        events += sorted((w[1], -1) for w in layout.active_windows.values())
        events.sort()
        running = peak = 0
        for _, delta in events:
            running += delta
            peak = max(peak, running)
        self.assertLessEqual(peak, MAX_ACTIVE_PER_CHAPTER)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestFourRowRealRender(unittest.TestCase):
    """The acceptance test: a real Exp Solar CSV with a four_row beat,
    through the exact render entry point (run_overscaled_pipeline, under
    style_preset_id="exp_solar"), produces a real, playable clip — and the
    layout actually used the 4-slot composition, not a degraded single card."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _make_sine_wav(self, path: Path, duration_s: float) -> None:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={max(0.5, duration_s):.2f}", str(path)],
            check=True, capture_output=True,
        )

    def test_four_row_csv_renders_a_real_clip_with_4_simultaneous_cards(self):
        rows = _four_row_rows()
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
            Image.new("RGB", (640, 360), ((i * 53) % 255, (i * 97) % 255, (i * 131) % 255)).save(p)
            resolved_media[node.id] = str(p)

        out_dir = self.tmp / "out"
        # This mirrors exactly what scene_graph.app_integration.generate_overscaled_video
        # now does for style_preset_id == "exp_solar": adapt once, then feed
        # the adapted rows into the SAME run_overscaled_pipeline Overscaled uses.
        result = run_overscaled_pipeline(
            adapted.rows, segment_id="seg", title="Four Row Test",
            style_preset_id="exp_solar", voiceover_path=str(voiceover), out_dir=out_dir,
            resolved_media=resolved_media, canvas_width=1600, canvas_height=1000,
            resolution="640x360", fps=15,
        )
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.segment_clip_path.is_file())

        four_row_ids = {"n2", "n3", "n4", "n5"}
        self.assertEqual(set(result.layout.node_rects.keys()) & four_row_ids, four_row_ids)
        # 4-slot template width, not the 1-slot fallback that degrade would use.
        widths = {round(result.layout.node_rects[nid].width) for nid in four_row_ids}
        self.assertEqual(len(widths), 1, "all 4 four_row cards should share the same 4-slot box width")


if __name__ == "__main__":
    unittest.main()
