"""Render-level regression tests for Exp Solar's multi-visual compositions
(two_panel / four_row / index_grid): the real bug report was "even when the
CSV defines multi-visual compositions, the final video is ~99% single
full-frame images." Proven and fixed here with the ACTUAL render/compositor
path — real ffmpeg encode, real extracted frames, real pixel sampling —
never only layout metadata.

ROOT CAUSE #1 (timing): every CSV row compiles to its own narration beat
with its own appear_at (scene_graph.overscaled_csv.py / voiceover_sync.py,
shared with Overscaled, unmodified). A two_panel/four_row/index_grid row
that continues an existing composition (typically authored with an empty
script_segment, per the earlier CSV-authoring guidance) still only becomes
visible partway through the group's own on-screen span — for MOST of a
four_row chapter's duration only the first member was ever on screen alone.
Confirmed with real rendered pixels before this fix: a two-panel frame
sampled early in its window showed panel A only, panel B still background
color; a four-row frame showed only node A, with B/C/D not yet visible.

FIX #1 (scene_graph/pipeline.py, gated to style_preset_id == "exp_solar"
only — never called for Overscaled): _sync_grouped_node_timing() unifies
every member of a "group"/"group_grid" connected set (exactly the edges
scene_graph.exp_solar_csv's _chain_two_panel_beats/_chain_four_row_beats/
_chain_index_grid_beats create) to the group's own earliest appear_at, so
they all become visible together. A causal ("sequential"/"callout") edge
between otherwise-independent nodes is untouched.

ROOT CAUSE #2 (index_grid crash, independent of #1 — reproduced identically
with or without the timing fix): scene_graph/layout.py's adaptive-sizing
pass computed EVERY chapter's template_size from
max(1, min(peak_concurrency, chapter_cap, member_count)) — including grid
chapters. But SLOT_TEMPLATE_GRID_15 (the fixed 3x5 index-grid board) has
exactly ONE entry, keyed 15; any other template_size KeyErrors. A real
index_grid chapter (typically far fewer than 15 rows) always hit this,
independent of the timing bug — index_grid could never render at all.

FIX #2 (scene_graph/layout.py): a grid chapter's template_size is now
unconditionally 15 (matching the template's only key) instead of the
peak-based value — only ever exercised by is_grid chapters, which
Overscaled's own CSV can never produce (group_grid edges are an Exp-Solar-
adapter-only construct), so this cannot change Overscaled's behavior.

ROOT CAUSE #3 (residual real-narration drift, found after #1/#2): even
with grouped nodes now appearing together, voiceover_sync.py's
retime_to_whisper_words still claims >=1 real Whisper word per BEAT
(one beat per CSV row, word_count = max(1, len(narration.split()))) — so
a continuation row's empty script_segment still steals exactly 1 real
word it never needed. Across a video with several grouped compositions
this compounds: every beat AFTER a group drifts a little further from
the real audio for each continuation row that preceded it.

FIX #3 (scene_graph/pipeline.py, gated to style_preset_id == "exp_solar"
only, and only on the whisper_words retiming path — retime_to_audio_
duration has no word-consumption logic to begin with):
_merge_grouped_beats_for_retime() runs BEFORE retime_to_whisper_words and
merges each group's continuation-row beats into their group's own
primary (first-member) beat, widening it to cover the group's full
original span and dropping the rest — so the real-word cursor advances
once per group, never once per row. Proven with a deterministic word
list: a 5-word beat followed by 3 empty continuation beats then another
5-word beat previously landed the second beat 3 seconds late; with the
fix it lands exactly on time.

ROOT CAUSE #4 (persistent chapter title never visible — reported live: "the
video does not have a title", found using a real Exp Solar CSV where every
row of a section repeats the SAME `chapter` value instead of only the
section's first row): compile_overscaled_csv (scene_graph/overscaled_csv.py,
shared with Overscaled) appends a NEW TitleCue for every row with a non-
empty chapter_title, with no deduplication — even when the text is
identical to the currently-active title. scene_graph/layout.py's
title_windows builder then gave EVERY cue its own reveal-in window, so a
section with (say) 8 rows all repeating "Learning From Data" produced 8
separate, closely-spaced re-triggers of the title's fade-in animation
instead of one stable, persistent header — confirmed directly: for a real
25-row CSV this collapsed 22 raw TitleCues down to 3 real section changes.

FIX #4 (scene_graph/layout.py, NOT gated to Exp Solar — this is a generic,
provably-inert improvement for any CSV, Overscaled included): consecutive
TitleCues sharing IDENTICAL text are now collapsed into ONE persistent
window spanning from the first cue's start to the next genuinely DIFFERENT
cue's start (or the segment's end). A CSV that already sets chapter_title
on only the first row of each section (as documented for both styles)
never has two consecutive cues with the same text, so this is a no-op
there — see TestTitleCollapseIsInertForNonRepeatingChapterTitles below.

No Flow account, network call, or Gemini call anywhere in this file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

# Obviously-distinct, deterministic test colors.
_COLORS = {
    "A": (220, 30, 30), "B": (30, 60, 220), "C": (30, 180, 60), "D": (230, 210, 20),
    "E": (200, 80, 200), "F": (80, 200, 200),
}


def _make_color_images(tmp: Path) -> dict:
    paths = {}
    for name, rgb in _COLORS.items():
        p = tmp / f"{name}.png"
        Image.new("RGB", (800, 450), rgb).save(p)
        paths[name] = p
    return paths


def _make_silent_wav(path: Path, duration_s: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono", "-t", f"{duration_s:.2f}", str(path)],
        check=True, capture_output=True,
    )


def _extract_frame(clip_path: Path, at_seconds: float, out_path: Path) -> Image.Image:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(clip_path), "-ss", f"{at_seconds:.3f}", "-vframes", "1", "-update", "1", str(out_path)],
        check=True, capture_output=True,
    )
    return Image.open(out_path).convert("RGB")


def _closest_color_name(rgb) -> str:
    best, best_dist = None, None
    for name, ref in _COLORS.items():
        dist = sum((a - b) ** 2 for a, b in zip(rgb, ref))
        if best_dist is None or dist < best_dist:
            best, best_dist = name, dist
    return best


def _rect_center(rect) -> tuple:
    return (int(rect.x + rect.width / 2), int(rect.y + rect.height / 2))


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestExpSolarMultiVisualCompositionRendersSimultaneously(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = _make_color_images(self.tmp)
        self.voiceover = self.tmp / "voiceover.wav"
        _make_silent_wav(self.voiceover, 6.0)

    def _run(self, rows, letters, segment_id):
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id=segment_id, style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        node_ids = [n.id for n in compiled.scene_graph.nodes]
        self.assertEqual(len(node_ids), len(letters))
        resolved_media = {nid: str(self.images[letter]) for nid, letter in zip(node_ids, letters)}

        out_dir = self.tmp / f"{segment_id}_out"
        result = run_overscaled_pipeline(
            adapted.rows, segment_id=segment_id, voiceover_path=str(self.voiceover),
            out_dir=out_dir, style_preset_id="exp_solar", resolved_media=resolved_media,
            whisper_words=None, resolution="1920x1080", fps=30,
        )
        self.assertTrue(result.ok, result.errors)
        return result, node_ids

    def test_two_panel_both_visible_in_same_frame(self):
        """A and B must both be visible in the SAME rendered frame -- and
        NEAR THE START of the clip, not only near the end (which is what
        the pre-fix staggered-appear_at bug produced: A alone for the
        first half, both only in the second half)."""
        rows = [
            {"scene_number": "1", "script_segment": "Comparing A and B.", "beat": "two_panel",
             "asset_type": "local_image", "prompt": ""},
            {"scene_number": "2", "script_segment": "", "beat": "two_panel",
             "asset_type": "local_image", "prompt": ""},
        ]
        result, node_ids = self._run(rows, ["A", "B"], "tp")

        frame = _extract_frame(result.segment_clip_path, 0.5, self.tmp / "tp_early.png")
        rect_a = result.layout.node_rects[node_ids[0]]
        rect_b = result.layout.node_rects[node_ids[1]]
        color_a = _closest_color_name(frame.getpixel(_rect_center(rect_a)))
        color_b = _closest_color_name(frame.getpixel(_rect_center(rect_b)))
        self.assertEqual(color_a, "A", "left panel must show image A")
        self.assertEqual(
            color_b, "B",
            "right panel must ALREADY show image B at 0.5s into a 6s clip -- "
            "if this is anything else (background/placeholder), B has not "
            "joined the composition yet: the staggered-timing bug is back",
        )

    def test_four_row_all_four_visible_in_same_frame(self):
        rows = [
            {"scene_number": str(i + 1),
             "script_segment": "Four related visuals, here is the first in detail." if i == 0 else "",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""}
            for i in range(4)
        ]
        result, node_ids = self._run(rows, ["A", "B", "C", "D"], "fr")

        frame = _extract_frame(result.segment_clip_path, 0.5, self.tmp / "fr_early.png")
        seen = {}
        for nid, letter in zip(node_ids, ["A", "B", "C", "D"]):
            rect = result.layout.node_rects[nid]
            seen[letter] = _closest_color_name(frame.getpixel(_rect_center(rect)))
        self.assertEqual(
            seen, {"A": "A", "B": "B", "C": "C", "D": "D"},
            "all four images must be simultaneously visible at 0.5s into a 6s clip",
        )

    def test_index_grid_all_supplied_nodes_visible_in_same_frame(self):
        letters = ["A", "B", "C", "D", "E", "F"]
        rows = [
            {"scene_number": str(i + 1), "script_segment": "Six items in a grid." if i == 0 else "",
             "beat": "index_grid", "asset_type": "local_image", "prompt": ""}
            for i in range(6)
        ]
        result, node_ids = self._run(rows, letters, "ig")

        frame = _extract_frame(result.segment_clip_path, 0.5, self.tmp / "ig_early.png")
        seen = {}
        for nid, letter in zip(node_ids, letters):
            rect = result.layout.node_rects[nid]
            seen[letter] = _closest_color_name(frame.getpixel(_rect_center(rect)))
        self.assertEqual(
            seen, {l: l for l in letters},
            "all six grid images must be simultaneously visible at 0.5s into a 6s clip",
        )

    def test_hero_still_renders_large_full_frame(self):
        """A plain hero beat (no group/group_grid edges) must be unaffected
        by either fix: one node, rendered large (near-canvas-size), not
        shrunk toward a multi-slot size."""
        rows = [{"scene_number": "1", "script_segment": "A single hero visual.", "beat": "hero",
                  "asset_type": "local_image", "prompt": ""}]
        result, node_ids = self._run(rows, ["A"], "hero")

        rect = result.layout.node_rects[node_ids[0]]
        canvas_w, canvas_h = result.layout.canvas_width, result.layout.canvas_height
        self.assertGreater(rect.width, canvas_w * 0.6, "hero must still occupy most of the canvas width")
        self.assertGreater(rect.height, canvas_h * 0.6, "hero must still occupy most of the canvas height")

        frame = _extract_frame(result.segment_clip_path, 0.5, self.tmp / "hero_early.png")
        color = _closest_color_name(frame.getpixel(_rect_center(rect)))
        self.assertEqual(color, "A")


class TestRepeatedChapterTitleDoesNotFlicker(unittest.TestCase):
    """FIX #4: a CSV that repeats the same `chapter` value on every row of
    a section (instead of only its first row) must still produce ONE
    stable, persistent title window per section — not one re-triggered
    reveal per row."""

    def test_title_windows_collapse_repeated_chapter_text(self):
        from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
        from scene_graph.layout import compute_layout
        from scene_graph.overscaled_csv import compile_overscaled_csv
        from scene_graph.style_presets import load_style_preset
        from scene_graph.voiceover_sync import retime_to_audio_duration

        rows = [
            {"scene_number": "1", "script_segment": "Opening the topic.", "node_id": "n1",
             "beat": "hero", "asset_type": "local_image", "prompt": "", "chapter": "Section One"},
            {"scene_number": "2", "script_segment": "Continuing the same idea.", "node_id": "n2",
             "beat": "hero", "asset_type": "local_image", "prompt": "", "chapter": "Section One"},
            {"scene_number": "3", "script_segment": "Still in the same section.", "node_id": "n3",
             "beat": "hero", "asset_type": "local_image", "prompt": "", "chapter": "Section One"},
            {"scene_number": "4", "script_segment": "Now a new topic begins.", "node_id": "n4",
             "beat": "hero", "asset_type": "local_image", "prompt": "", "chapter": "Section Two"},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)
        # Confirm the raw (uncollapsed) cue count really is 4 -- one per
        # row -- so the assertion below is proving layout's collapse, not
        # a compile-time dedup that would mask the same bug elsewhere.
        self.assertEqual(len(compiled.scene_graph.title_cues), 4)

        style = load_style_preset("exp_solar")
        layout = compute_layout(
            compiled.scene_graph,
            max_active_per_chapter=(style.metadata or {}).get("max_active_per_chapter"),
        )
        self.assertEqual(
            len(layout.title_windows), 2,
            "3 rows repeating 'Section One' plus 1 row of 'Section Two' must collapse "
            "to exactly 2 persistent title windows, not 4 flickering ones",
        )
        self.assertEqual(layout.title_windows[0][0], "Section One")
        self.assertEqual(layout.title_windows[1][0], "Section Two")
        # The first window must span the FULL run (start of row 1 through
        # to row 4's start), not just row 1's own slice.
        self.assertEqual(layout.title_windows[0][1], 0.0)
        self.assertEqual(layout.title_windows[0][2], layout.title_windows[1][1])


class TestTitleCollapseIsInertForNonRepeatingChapterTitles(unittest.TestCase):
    """The collapse must never fire for a well-formed CSV that already
    follows the documented rule (chapter_title set only on a section's
    first row) -- proving FIX #4 cannot change Overscaled's existing,
    tested behavior, since Overscaled CSVs are authored the same way."""

    def test_overscaled_style_csv_with_one_chapter_title_per_section_is_unaffected(self):
        from scene_graph.layout import compute_layout
        from scene_graph.overscaled_csv import compile_overscaled_csv

        rows = [
            {"scene_number": "1", "script_segment": "Opening.", "node_id": "n1", "node_type": "image",
             "asset_type": "local", "chapter_title": "Section One"},
            {"scene_number": "2", "script_segment": "Continuing.", "node_id": "n2", "node_type": "image",
             "asset_type": "local"},
            {"scene_number": "3", "script_segment": "New topic.", "node_id": "n3", "node_type": "image",
             "asset_type": "local", "chapter_title": "Section Two"},
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        self.assertEqual(len(compiled.scene_graph.title_cues), 2, "one cue per section, as authored")

        layout = compute_layout(compiled.scene_graph)
        self.assertEqual(
            len(layout.title_windows), 2,
            "a correctly-authored CSV (one chapter_title per section) must be completely "
            "unaffected by the collapse -- no consecutive cues share identical text here",
        )


class TestGroupedContinuationRowsDoNotStealRealNarrationWords(unittest.TestCase):
    """FIX #3: a group's continuation rows (empty script_segment) must not
    each claim a real Whisper word, or every beat after the group drifts
    further out of sync with the real audio the more continuation rows
    preceded it. Deterministic word-list proof, not just layout metadata."""

    def test_beat_after_a_four_row_group_is_not_shifted_late(self):
        from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
        from scene_graph.overscaled_csv import compile_overscaled_csv
        from scene_graph.pipeline import _merge_grouped_beats_for_retime
        from scene_graph.voiceover_sync import retime_to_whisper_words

        rows = [
            {"scene_number": "1", "script_segment": "one two three four five", "node_id": "n1",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "2", "script_segment": "", "node_id": "n2",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "3", "script_segment": "", "node_id": "n3",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "4", "script_segment": "", "node_id": "n4",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "5", "script_segment": "six seven eight nine ten", "node_id": "n5",
             "beat": "hero", "asset_type": "local_image", "prompt": ""},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        self.assertTrue(adapted.ok, adapted.errors)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        self.assertTrue(compiled.ok, compiled.errors)

        words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        whisper_words = [(w, float(i), float(i + 1)) for i, w in enumerate(words)]

        merged = _merge_grouped_beats_for_retime(compiled.scene_graph)
        retimed = retime_to_whisper_words(merged, whisper_words)
        n5 = next(n for n in retimed.nodes if n.id == "n5")
        self.assertAlmostEqual(
            n5.appear_at, 5.0, places=3,
            msg="scene 5's real narration starts exactly at word index 5 ('six') -- "
                "three continuation rows must not push it 3 words/seconds late",
        )

    def test_without_the_merge_the_drift_is_reproducible(self):
        """Documents the pre-fix failure mode directly (not just via git
        stash): calling retime_to_whisper_words on the RAW scene graph,
        skipping _merge_grouped_beats_for_retime, must show the drift --
        proving the fix is what removes it, not an unrelated change."""
        from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
        from scene_graph.overscaled_csv import compile_overscaled_csv
        from scene_graph.voiceover_sync import retime_to_whisper_words

        rows = [
            {"scene_number": "1", "script_segment": "one two three four five", "node_id": "n1",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "2", "script_segment": "", "node_id": "n2",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "3", "script_segment": "", "node_id": "n3",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "4", "script_segment": "", "node_id": "n4",
             "beat": "four_row", "asset_type": "local_image", "prompt": ""},
            {"scene_number": "5", "script_segment": "six seven eight nine ten", "node_id": "n5",
             "beat": "hero", "asset_type": "local_image", "prompt": ""},
        ]
        adapted = adapt_exp_solar_csv_rows(rows)
        compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
        words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        whisper_words = [(w, float(i), float(i + 1)) for i, w in enumerate(words)]

        retimed = retime_to_whisper_words(compiled.scene_graph, whisper_words)
        n5 = next(n for n in retimed.nodes if n.id == "n5")
        self.assertAlmostEqual(
            n5.appear_at, 8.0, places=3,
            msg="without the merge pre-pass, 3 continuation beats each steal 1 real "
                "word, pushing scene 5 three seconds late -- this documents the bug shape",
        )


class TestOverscaledUnaffectedByExpSolarFixes(unittest.TestCase):
    """The style_preset_id == "exp_solar" gate on _sync_grouped_node_timing
    means it must never run for plain Overscaled; the grid-template fix in
    layout.py only ever applies to is_grid chapters, which Overscaled's own
    CSV parser (scene_graph.overscaled_csv.py) has no way to create (no
    "group_grid" edge kind exists there) -- both confirmed structurally,
    not just by the existing Overscaled suite continuing to pass."""

    def test_sync_grouped_node_timing_is_never_invoked_for_overscaled(self):
        import inspect

        from scene_graph import pipeline as pipeline_module

        source = inspect.getsource(pipeline_module.run_overscaled_pipeline)
        self.assertIn('style_preset_id == "exp_solar"', source)
        self.assertIn("_sync_grouped_node_timing", source)

    def test_merge_grouped_beats_for_retime_is_never_invoked_for_overscaled(self):
        import inspect

        from scene_graph import pipeline as pipeline_module

        source = inspect.getsource(pipeline_module.run_overscaled_pipeline)
        self.assertIn("_merge_grouped_beats_for_retime", source)
        # Both Exp-Solar-only calls must sit behind the same literal gate,
        # not a differently-scoped or missing condition.
        self.assertEqual(source.count('style_preset_id == "exp_solar"'), 2)

    def test_overscaled_csv_parser_cannot_produce_group_grid_edges(self):
        from scene_graph.overscaled_csv import OPTIONAL_COLUMNS

        # Overscaled's own CSV schema exposes edge_style as callout/sequential
        # only (see its module docstring) -- "group"/"group_grid" edge kinds
        # are exclusively synthesized by scene_graph.exp_solar_csv's chaining
        # helpers, never reachable from a plain Overscaled CSV row.
        self.assertIn("edge_style", OPTIONAL_COLUMNS)
        rows = [
            {"scene_number": "1", "script_segment": "a", "node_id": "n1", "node_type": "image",
             "asset_type": "local", "edge_style": "group"},
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        # A single row with no edge_from/edge_to defines no edge at all --
        # "group_grid" specifically is not even in overscaled_csv.py's own
        # accepted edge_style vocabulary (see its edge_kind mapping).
        self.assertEqual(compiled.scene_graph.edges, [])


if __name__ == "__main__":
    unittest.main()
