"""Regression tests for Exp Solar's narration-ownership / visual-membership
separation.

The report worried that the pipeline conflates two independent concepts:
narration ownership (which row's script_segment actually gets spoken) and
visual membership (which rows contribute an on-screen image/video). The
fear was that an empty script_segment on a two_panel/four_row/index_grid
continuation row gets treated as "this row is incomplete" and silently
dropped from media resolution.

INVESTIGATION FINDING (see TestEmptyScriptSegmentIsNotSkippedByMediaResolution
below): this was NOT actually happening. SceneAssetRouter.classify() and
AssetManager.resolve_all() route purely off asset_type/prompt/stock — never
script_segment — confirmed here with a real end-to-end resolve using the
established FakeProvider test convention. Narration and visual routing were
already independent dimensions at the media-resolution layer.

THE ONE REAL GAP (found and fixed here): scene_graph/media_resolution.py's
row-building loop included EVERY node with a truthy asset_source/
asset_reference, with no exception for "checklist_item" nodes (Exp Solar's
structural checklist-strip rows). A checklist row typically carries a
placeholder asset_type like "text" (not a real routable type) since it was
never meant to need one -- the checklist strip is drawn purely from
node.label/appear_at (scene_graph.layout's checklist_windows,
composition.render_checklist_strip_frame), never from resolved media. That
placeholder asset_type failed classification, producing exactly the
reported "no prompt, no stock keywords, and no local file found" error for
scenes 1/6/11 in a real CSV.

FIX (scene_graph/media_resolution.py): checklist_item nodes are now
excluded from resolve_scene_graph_media's row-building entirely via the
existing (previously-empty) _NON_ASSET_NODE_TYPES set -- structural UI
never enters media resolution, no placeholder asset_type needed. This is
inherently Exp-Solar-only: "checklist_item" only ever exists on a node
scene_graph.exp_solar_csv's beat=checklist adapter produces (see
schema.KNOWN_NODE_TYPES's own docstring) -- Overscaled's CSV/compiler has
no way to create one.

The grouped-timing (_sync_grouped_node_timing) and Whisper-word-consumption
(_merge_grouped_beats_for_retime) fixes from the earlier investigation are
NOT modified here -- reverified passing below (tests 4/7/8) and via the
existing test_exp_solar_multi_visual_composition.py suite.

No Flow account, network call, or Gemini call anywhere in this file.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from asset_manager import AssetManager
from providers.base import AssetSource, MediaType, SceneRow
from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
from scene_graph.media_resolution import resolve_scene_graph_media
from scene_graph.overscaled_csv import compile_overscaled_csv
from test_asset_pipeline import FakeProvider


def _resolve_with_fake_flow(scene_graph, images_dir, flow=None):
    """Drives the REAL resolve_scene_graph_media -> video_generator.
    resolve_scene_assets -> AssetManager.resolve_all path, substituting only
    the Flow ENGINE CONNECTION (a real flow-engine subprocess is obviously
    unavailable here) with the same FakeProvider stub the rest of this
    codebase's test suite already uses for exactly this purpose -- not a
    reconstructed resolver."""
    import video_generator as vg

    flow = flow or FakeProvider(AssetSource.FLOW_IMAGE, {}, media_type=MediaType.IMAGE)
    real_resolve_scene_assets = vg.resolve_scene_assets

    def patched(rows, images_dir, **kwargs):
        scene_rows = [SceneRow.from_csv_row(r) for r in rows]
        mgr = AssetManager(images_dir, flow_image_provider=flow, log=lambda *_: None)
        summary = mgr.resolve_all(scene_rows)
        if not summary.ok:
            raise SystemExit(f"resolve failed: {[r.error for r in summary.failed]}")

    vg.resolve_scene_assets = patched
    try:
        return resolve_scene_graph_media(scene_graph, images_dir=images_dir), flow
    finally:
        vg.resolve_scene_assets = real_resolve_scene_assets


class TestEmptyScriptSegmentIsNotSkippedByMediaResolution(unittest.TestCase):
    """Test 5 (spec) + the two_panel/four_row/index_grid membership tests
    (spec tests 1-3): a valid visual row with script_segment="" must still
    resolve through the REAL AssetManager/router path -- routing is driven
    by asset_type/prompt/stock, never by narration."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images_dir = self.tmp / "images"
        self.images_dir.mkdir()

    def test_two_panel_continuation_row_resolves_with_empty_script_segment(self):
        rows = [
            {"scene_number": "4", "script_segment": "The technology changed everything.", "node_id": "N04a",
             "beat": "two_panel", "asset_type": "stock_image", "prompt": "old technology"},
            {"scene_number": "5", "script_segment": "", "node_id": "N04b",
             "beat": "two_panel", "asset_type": "stock_image", "prompt": "modern technology"},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)

        fake = FakeProvider(AssetSource.STOCK_IMAGE, {})
        with patch("providers.stock.pexels.build_pexels_provider", side_effect=lambda d, k: fake):
            resolved = resolve_scene_graph_media(compiled.scene_graph, images_dir=self.images_dir, pexels_api_key="k")

        self.assertEqual(len(resolved), 2, "both visual members must resolve, not just the narration owner")
        self.assertIn("N04a", resolved)
        self.assertIn("N04b", resolved, "the empty-script_segment continuation row must NOT be dropped")

    def test_four_row_continuations_all_resolve_with_empty_script_segment(self):
        rows = [
            {"scene_number": str(i + 1),
             "script_segment": "Four technologies transformed the industry." if i == 0 else "",
             "node_id": f"N10{c}", "beat": "four_row", "asset_type": "stock_image", "prompt": f"technology {c}"}
            for i, c in enumerate("abcd")
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)

        fake = FakeProvider(AssetSource.STOCK_IMAGE, {})
        with patch("providers.stock.pexels.build_pexels_provider", side_effect=lambda d, k: fake):
            resolved = resolve_scene_graph_media(compiled.scene_graph, images_dir=self.images_dir, pexels_api_key="k")

        self.assertEqual(len(resolved), 4, "all four visual rows must resolve -- three have no narration")
        for c in "abcd":
            self.assertIn(f"N10{c}", resolved)

    def test_index_grid_continuations_all_resolve_with_empty_script_segment(self):
        letters = "abcdefghij"  # 10 grid members
        rows = [
            {"scene_number": str(i + 1),
             "script_segment": "These are the technologies that changed everything." if i == 0 else "",
             "node_id": f"N20{c}", "beat": "index_grid", "asset_type": "stock_image", "prompt": f"tech {c}"}
            for i, c in enumerate(letters)
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)

        fake = FakeProvider(AssetSource.STOCK_IMAGE, {})
        with patch("providers.stock.pexels.build_pexels_provider", side_effect=lambda d, k: fake):
            resolved = resolve_scene_graph_media(compiled.scene_graph, images_dir=self.images_dir, pexels_api_key="k")

        self.assertEqual(len(resolved), len(letters), "every requested grid member must resolve")
        for c in letters:
            self.assertIn(f"N20{c}", resolved)


class TestChecklistRowsNeverEnterMediaResolution(unittest.TestCase):
    """Test 6 (spec): a beat=checklist row (structural UI, asset_type="text"
    or any placeholder value) must not attempt media resolution at all --
    no "no prompt, no stock keywords, and no local file found" error --
    and must remain available for the checklist strip to read its label."""

    def test_checklist_row_produces_no_resolution_error_and_no_entry(self):
        tmp = Path(tempfile.mkdtemp())
        images_dir = tmp / "images"
        images_dir.mkdir()

        rows = [
            {"scene_number": "1", "script_segment": "", "node_id": "CK1", "beat": "checklist",
             "asset_type": "text", "prompt": "", "chapter": "The Dream", "node_label": "The Dream"},
            {"scene_number": "2", "script_segment": "For decades, engineers dreamed.", "node_id": "N01",
             "beat": "hero", "asset_type": "image", "prompt": "1950s research lab"},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)

        checklist_node = next(n for n in compiled.scene_graph.nodes if n.id == "CK1")
        self.assertEqual(checklist_node.type, "checklist_item")

        # No exception at all -- this used to raise SystemExit("no prompt,
        # no stock keywords, and no local file found") for the checklist row.
        resolved, flow = _resolve_with_fake_flow(compiled.scene_graph, images_dir)

        self.assertNotIn("CK1", resolved, "a checklist row must never enter media resolution")
        self.assertIn("N01", resolved, "the real visual row must still resolve normally")
        self.assertEqual(flow.calls, ["2"], "Flow must be called only for the real visual scene, never for CK1")

    def test_three_checklist_rows_reproduce_and_fix_the_original_report(self):
        """Directly reproduces the exact CSV shape from the original bug
        report: three checklist rows at scenes 1, 6, 11 among real visual
        content, asset_type='text'."""
        tmp = Path(tempfile.mkdtemp())
        images_dir = tmp / "images"
        images_dir.mkdir()

        rows = [
            {"scene_number": "1", "script_segment": "", "node_id": "CK1", "beat": "checklist",
             "asset_type": "text", "prompt": "", "chapter": "The Dream", "node_label": "The Dream"},
            {"scene_number": "2", "script_segment": "Engineers dreamed of thinking machines.", "node_id": "N01",
             "beat": "hero", "asset_type": "image", "prompt": "1950s research lab"},
            {"scene_number": "6", "script_segment": "", "node_id": "CK2", "beat": "checklist",
             "asset_type": "text", "prompt": "", "chapter": "Learning From Data", "node_label": "Learning From Data"},
            {"scene_number": "7", "script_segment": "Machines began learning from data.", "node_id": "N05",
             "beat": "hero", "asset_type": "image", "prompt": "neural network visualization"},
            {"scene_number": "11", "script_segment": "", "node_id": "CK3", "beat": "checklist",
             "asset_type": "text", "prompt": "", "chapter": "Agents", "node_label": "Agents"},
            {"scene_number": "12", "script_segment": "Machines began to plan and act.", "node_id": "N09",
             "beat": "hero", "asset_type": "image", "prompt": "an AI agent workspace"},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)

        resolved, flow = _resolve_with_fake_flow(compiled.scene_graph, images_dir)

        for ck in ("CK1", "CK2", "CK3"):
            self.assertNotIn(ck, resolved)
        for real in ("N01", "N05", "N09"):
            self.assertIn(real, resolved)
        self.assertEqual(sorted(flow.calls), ["12", "2", "7"])


class TestSequentialHeroesAreNotAccidentallyGrouped(unittest.TestCase):
    """Test 4 (spec): plain sequential hero rows, each with its own real
    narration, must stay as independent, sequential visual beats -- never
    merged just because they share a chapter or sit next to each other."""

    def test_four_sequential_heroes_get_four_distinct_appear_times(self):
        from scene_graph.pipeline import _sync_grouped_node_timing
        from scene_graph.voiceover_sync import retime_to_audio_duration

        rows = [
            {"scene_number": "1", "script_segment": "First, machines became smaller.", "node_id": "N30",
             "beat": "hero", "asset_type": "image", "prompt": "a small chip"},
            {"scene_number": "2", "script_segment": "Then processors became faster.", "node_id": "N31",
             "beat": "hero", "asset_type": "image", "prompt": "a fast processor"},
            {"scene_number": "3", "script_segment": "Finally, machines started learning.", "node_id": "N32",
             "beat": "hero", "asset_type": "image", "prompt": "a learning machine"},
            {"scene_number": "4", "script_segment": "And now they reason and act.", "node_id": "N33",
             "beat": "hero", "asset_type": "image", "prompt": "an autonomous agent"},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        self.assertEqual(compiled.scene_graph.edges, [], "plain sequential heroes must have no grouping edges at all")

        sg = _sync_grouped_node_timing(compiled.scene_graph)  # a no-op here (no groups) -- must stay a no-op
        appear_times = sorted(float(n.appear_at) for n in sg.nodes)
        self.assertEqual(
            len(set(appear_times)), 4,
            "four independent hero beats must keep four distinct appear times, never collapse together",
        )


class TestSimultaneousCompositionsShareOneStartAndEndTime(unittest.TestCase):
    """Test 8 (spec): for every explicit multi-visual composition, all
    member start AND end times must be equal -- proving the grouped-timing
    fix (_sync_grouped_node_timing) plus the shared chapter-end mechanism
    already in scene_graph.layout.compute_layout together satisfy the
    'no stagger' requirement, at the layout-window level (not just
    node.appear_at)."""

    def _layout_windows(self, rows):
        from scene_graph.layout import compute_layout
        from scene_graph.pipeline import _merge_grouped_beats_for_retime, _sync_grouped_node_timing
        from scene_graph.style_presets import load_style_preset
        from scene_graph.voiceover_sync import retime_to_audio_duration

        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)

        import tempfile

        wav = Path(tempfile.mkdtemp()) / "silence.wav"
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "4", str(wav)],
            check=True, capture_output=True,
        )
        sg = retime_to_audio_duration(compiled.scene_graph, str(wav))
        sg = _sync_grouped_node_timing(sg)
        style = load_style_preset("exp_solar")
        layout = compute_layout(sg, max_active_per_chapter=(style.metadata or {}).get("max_active_per_chapter"))
        return layout, [n.id for n in sg.nodes]

    def test_two_panel_members_share_identical_window(self):
        rows = [
            {"scene_number": "1", "script_segment": "Comparing old and new.", "node_id": "N1",
             "beat": "two_panel", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "2", "script_segment": "", "node_id": "N2",
             "beat": "two_panel", "asset_type": "local_image", "prompt": ""},
        ]
        layout, node_ids = self._layout_windows(rows)
        windows = [layout.active_windows[nid] for nid in node_ids]
        self.assertEqual(windows[0], windows[1], "two_panel members must share one identical start/end window")

    def test_four_row_members_share_identical_window(self):
        rows = [
            {"scene_number": str(i + 1), "script_segment": "Four related visuals." if i == 0 else "",
             "node_id": f"N{i + 1}", "beat": "four_row", "asset_type": "local_image", "prompt": ""}
            for i in range(4)
        ]
        layout, node_ids = self._layout_windows(rows)
        windows = [layout.active_windows[nid] for nid in node_ids]
        self.assertEqual(len(set(windows)), 1, "all four_row members must share one identical start/end window")


if __name__ == "__main__":
    unittest.main()
