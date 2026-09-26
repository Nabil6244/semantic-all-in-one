"""Exp Solar's sound design layer — deterministic SFX/ambience event
planning + the final mix, built entirely on the EXISTING smart_editing
SFX/ambience catalog and FFmpeg mixing pipeline (see
scene_graph/exp_solar_audio.py's module docstring for the full flow).

Mirrors test_smart_editing.py's own SFX-catalog test conventions
(reset_sfx_catalog_cache / write_test_sfx_library) since this module reuses
that exact infrastructure rather than building a second one.
"""

from __future__ import annotations

import inspect
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import smart_editing as se
from scene_graph.exp_solar_audio import (
    MAX_SFX_FRACTION,
    MIN_SFX_GAP_S,
    build_exp_solar_ambience_beds,
    build_exp_solar_audio_mix,
    build_exp_solar_sfx_events,
    plan_exp_solar_audio_events,
)
from scene_graph.exp_solar_csv import adapt_exp_solar_csv_rows
from scene_graph.layout import compute_layout
from scene_graph.overscaled_csv import compile_overscaled_csv
from scene_graph.pipeline import run_overscaled_pipeline

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _rich_exp_solar_rows():
    """A CSV exercising chapter entries, checklist items, a reaction beat,
    and a four_row chapter — every event kind plan_exp_solar_audio_events
    knows about, in one segment."""
    rows = [
        {"scene_number": "1", "script_segment": "Cold open narration line here.",
         "node_id": "hero0", "beat": "hero", "asset_type": "flow_image", "prompt": "p", "chapter": "Intro"},
    ]
    for i in range(1, 3):
        rows.append({
            "scene_number": str(len(rows) + 1), "script_segment": f"Checklist item {i}.",
            "node_id": f"chk{i}", "beat": "checklist", "chapter": f"Item {i}", "node_label": str(i),
        })
        rows.append({
            "scene_number": str(len(rows) + 1), "script_segment": f"Item {i} narration content for timing here.",
            "node_id": f"hero{i}", "beat": "hero", "asset_type": "flow_image", "prompt": f"hero {i}",
        })
        rows.append({
            "scene_number": str(len(rows) + 1), "script_segment": f"Reaction to item {i}.",
            "node_id": f"react{i}", "beat": "reaction", "asset_type": "stock_video", "prompt": "r",
        })
    for i in range(1, 5):
        rows.append({
            "scene_number": str(len(rows) + 1), "script_segment": f"Four row variant {i}.",
            "node_id": f"f{i}", "beat": "four_row", "asset_type": "flow_image", "prompt": "p",
        })
    return rows


def _compile(rows):
    adapted = adapt_exp_solar_csv_rows(rows)
    assert adapted.ok, adapted.errors
    compiled = compile_overscaled_csv(adapted.rows, segment_id="seg", style_preset="exp_solar")
    assert compiled.ok, compiled.errors
    return adapted, compiled.scene_graph


class TestAudioEventDetection(unittest.TestCase):
    def test_detects_chapter_checklist_reaction_and_four_row_events(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        events = plan_exp_solar_audio_events(sg, layout)
        kinds = {e.kind for e in events}
        self.assertEqual(kinds, {"chapter_entry", "checklist", "reaction", "four_row"})

    def test_four_row_produces_one_event_not_one_per_card(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        events = plan_exp_solar_audio_events(sg, layout)
        four_row_events = [e for e in events if e.kind == "four_row"]
        self.assertEqual(len(four_row_events), 1)  # one chapter entry, not 4

    def test_no_events_for_a_segment_with_no_exp_solar_beats(self):
        rows = [
            {"scene_number": "1", "script_segment": "a", "node_id": "a", "node_type": "image",
             "asset_type": "flow_image", "prompt": "p"},
        ]
        compiled = compile_overscaled_csv(rows, segment_id="seg")
        self.assertTrue(compiled.ok, compiled.errors)
        layout = compute_layout(compiled.scene_graph, resolved_media={})
        events = plan_exp_solar_audio_events(compiled.scene_graph, layout)
        self.assertEqual(events, [])


class TestDeterministicGeneration(unittest.TestCase):
    def test_same_input_produces_identical_event_list(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        events_a = plan_exp_solar_audio_events(sg, layout)
        events_b = plan_exp_solar_audio_events(sg, layout)
        self.assertEqual(events_a, events_b)

    def test_same_input_produces_identical_sfx_selection(self):
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "sfxlib"
        se.write_test_sfx_library(root)
        se.reset_sfx_catalog_cache()
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        a = build_exp_solar_sfx_events(sg, layout, sfx_root=root)
        b = build_exp_solar_sfx_events(sg, layout, sfx_root=root)
        self.assertEqual(a, b)


class TestSfxPlacementAndRestraint(unittest.TestCase):
    def setUp(self):
        se.reset_sfx_catalog_cache()
        self.tmp = Path(tempfile.mkdtemp())
        self.sfx_root = self.tmp / "sfxlib"
        se.write_test_sfx_library(self.sfx_root)

    def tearDown(self):
        se.reset_sfx_catalog_cache()

    def test_sfx_events_are_placed_near_their_source_visual_event(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        events = plan_exp_solar_audio_events(sg, layout)
        sfx_events = build_exp_solar_sfx_events(sg, layout, sfx_root=self.sfx_root)
        event_times = [e.at for e in events]
        for sfx in sfx_events:
            self.assertTrue(any(abs(sfx["start"] - t) < 0.01 for t in event_times))

    def test_not_every_detected_event_gets_sfx(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        events = plan_exp_solar_audio_events(sg, layout)
        sfx_events = build_exp_solar_sfx_events(sg, layout, sfx_root=self.sfx_root)
        self.assertGreater(len(events), len(sfx_events))
        self.assertLessEqual(len(sfx_events), max(1, round(len(events) * MAX_SFX_FRACTION)))

    def test_selected_sfx_never_closer_together_than_min_gap(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        sfx_events = build_exp_solar_sfx_events(sg, layout, sfx_root=self.sfx_root)
        starts = sorted(e["start"] for e in sfx_events)
        for a, b in zip(starts, starts[1:]):
            self.assertGreaterEqual(b - a, MIN_SFX_GAP_S - 1e-6)

    def test_major_chapter_moments_prefer_stronger_impact_category(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        sfx_events = build_exp_solar_sfx_events(sg, layout, sfx_root=self.sfx_root)
        chapter_events = [e for e in sfx_events if e["type"] == "chapter_entry"]
        self.assertTrue(chapter_events)
        for e in chapter_events:
            self.assertEqual(e["category"], "impact")

    def test_sfx_volume_stays_clearly_below_narration_level(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        sfx_events = build_exp_solar_sfx_events(sg, layout, sfx_root=self.sfx_root)
        self.assertTrue(sfx_events)
        for e in sfx_events:
            self.assertLessEqual(e["volume"], 0.22)


class TestAmbienceBehavior(unittest.TestCase):
    def setUp(self):
        se.reset_sfx_catalog_cache()

    def tearDown(self):
        se.reset_sfx_catalog_cache()

    def test_ambience_bed_spans_the_full_segment_when_catalog_has_one(self):
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "sfxlib"
        se.write_test_sfx_library(root)
        beds = build_exp_solar_ambience_beds(42.5, sfx_root=root)
        self.assertEqual(len(beds), 1)
        self.assertAlmostEqual(beds[0]["duration"], 42.5, places=2)
        self.assertLessEqual(beds[0]["volume"], 0.12)

    def test_no_ambience_when_catalog_has_no_ambience_category(self):
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "sfxlib"
        se.write_test_sfx_library(root, entries=[
            {"id": "whoosh_only", "file": "whoosh/w.wav", "category": "whoosh", "tags": [],
             "intensity": "medium", "duration": 0.3, "source": "test", "license": "test",
             "commercial_use": True, "attribution_required": False},
        ])
        beds = build_exp_solar_ambience_beds(20.0, sfx_root=root)
        self.assertEqual(beds, [])

    def test_no_music_required_no_render_failure_with_empty_catalog(self):
        tmp = Path(tempfile.mkdtemp())
        empty_root = tmp / "no_such_sfx_lib"
        beds = build_exp_solar_ambience_beds(20.0, sfx_root=empty_root)
        self.assertEqual(beds, [])

    def test_one_bed_per_chapter_when_layout_has_multiple_title_windows(self):
        """The reported bug: one continuous ambience bed for the whole
        video, start to end, regardless of chapter changes. Fix: one bed
        PER title window (chapter), each spanning exactly that chapter's
        own on-screen range."""
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "sfxlib"
        se.write_test_sfx_library(root, entries=[
            {"id": "amb_a", "file": "ambience/a.wav", "category": "ambience", "tags": [],
             "intensity": "low", "duration": 10.0, "source": "test", "license": "test",
             "commercial_use": True, "attribution_required": False},
            {"id": "amb_b", "file": "ambience/b.wav", "category": "ambience", "tags": [],
             "intensity": "low", "duration": 10.0, "source": "test", "license": "test",
             "commercial_use": True, "attribution_required": False},
            {"id": "amb_c", "file": "ambience/c.wav", "category": "ambience", "tags": [],
             "intensity": "low", "duration": 10.0, "source": "test", "license": "test",
             "commercial_use": True, "attribution_required": False},
        ])

        class _FakeLayout:
            title_windows = [("Intro", 0.0, 10.0), ("Middle", 10.0, 22.0), ("Outro", 22.0, 30.0)]

        beds = build_exp_solar_ambience_beds(30.0, layout=_FakeLayout(), sfx_root=root)

        self.assertEqual(len(beds), 3, "one bed per chapter, not one for the whole video")
        self.assertEqual([b["start"] for b in beds], [0.0, 10.0, 22.0])
        self.assertEqual([b["end"] for b in beds], [10.0, 22.0, 30.0])
        self.assertEqual([b["duration"] for b in beds], [10.0, 12.0, 8.0], "each bed's own duration is its OWN chapter span")
        self.assertEqual(
            len({b["sfx_id"] for b in beds}), 3,
            "with 3 distinct ambience tracks available, each chapter should get a different one",
        )

    def test_falls_back_to_one_whole_segment_bed_when_layout_has_no_chapters(self):
        """A layout with no chapter_title at all (title_windows empty) must
        keep the OLD single-bed-for-the-whole-segment behavior, not
        silently drop ambience entirely."""
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "sfxlib"
        se.write_test_sfx_library(root)

        class _FakeLayoutNoChapters:
            title_windows = []

        beds = build_exp_solar_ambience_beds(42.5, layout=_FakeLayoutNoChapters(), sfx_root=root)
        self.assertEqual(len(beds), 1)
        self.assertAlmostEqual(beds[0]["duration"], 42.5, places=2)

    def test_real_csv_with_repeated_chapter_text_still_gets_per_chapter_beds(self):
        """End-to-end through the real compiler/layout: 3 sections, each
        repeating its own chapter text across several rows (the exact
        pattern from the live bug report) -- must still produce exactly
        3 ambience beds, one per real section, not one per row and not
        one for the whole video."""
        tmp = Path(tempfile.mkdtemp())
        root = tmp / "sfxlib"
        se.write_test_sfx_library(root, entries=[
            {"id": "amb_a", "file": "ambience/a.wav", "category": "ambience", "tags": [],
             "intensity": "low", "duration": 10.0, "source": "test", "license": "test",
             "commercial_use": True, "attribution_required": False},
            {"id": "amb_b", "file": "ambience/b.wav", "category": "ambience", "tags": [],
             "intensity": "low", "duration": 10.0, "source": "test", "license": "test",
             "commercial_use": True, "attribution_required": False},
        ])

        rows = []
        for section in ("Section One", "Section Two", "Section Three"):
            for i in range(3):
                rows.append({
                    "scene_number": str(len(rows) + 1),
                    "script_segment": f"{section} narration line {i}." if i == 0 else "",
                    "node_id": f"n{len(rows) + 1}", "beat": "hero", "asset_type": "flow_image",
                    "prompt": "p", "chapter": section,
                })
        _, sg = _compile(rows)
        layout = compute_layout(sg, resolved_media={})
        self.assertEqual(len(layout.title_windows), 3, "sanity: 3 real sections after title-collapse")

        beds = build_exp_solar_ambience_beds(float(sg.duration), layout=layout, sfx_root=root)
        self.assertEqual(len(beds), 3, "one ambience bed per real section, not one continuous bed")


class TestGracefulDegradation(unittest.TestCase):
    def setUp(self):
        se.reset_sfx_catalog_cache()

    def tearDown(self):
        se.reset_sfx_catalog_cache()

    def test_missing_sfx_library_produces_no_events_not_an_error(self):
        tmp = Path(tempfile.mkdtemp())
        missing_root = tmp / "does_not_exist"
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        sfx_events = build_exp_solar_sfx_events(sg, layout, sfx_root=missing_root)
        self.assertEqual(sfx_events, [])

    @unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
    def test_mix_falls_back_to_plain_narration_copy_when_nothing_resolves(self):
        tmp = Path(tempfile.mkdtemp())
        missing_root = tmp / "does_not_exist"
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})

        voiceover = tmp / "vo.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={sg.duration:.2f}", str(voiceover)],
            check=True, capture_output=True,
        )
        out = tmp / "mixed.wav"
        result = build_exp_solar_audio_mix(sg, layout, voiceover_path=voiceover, output_path=out, sfx_root=missing_root)
        self.assertTrue(result.is_file())
        self.assertEqual(result.read_bytes(), voiceover.read_bytes())  # exact fallback copy


class TestNarrationTimingUnchanged(unittest.TestCase):
    def setUp(self):
        se.reset_sfx_catalog_cache()
        self.tmp = Path(tempfile.mkdtemp())
        self.sfx_root = self.tmp / "sfxlib"
        se.write_test_sfx_library(self.sfx_root)

    def tearDown(self):
        se.reset_sfx_catalog_cache()

    @unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
    def test_mixed_audio_duration_matches_narration_duration(self):
        _, sg = _compile(_rich_exp_solar_rows())
        layout = compute_layout(sg, resolved_media={})
        voiceover = self.tmp / "vo.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={sg.duration:.2f}", str(voiceover)],
            check=True, capture_output=True,
        )
        out = self.tmp / "mixed.wav"
        result = build_exp_solar_audio_mix(sg, layout, voiceover_path=voiceover, output_path=out, sfx_root=self.sfx_root)

        import wave
        with wave.open(str(voiceover)) as w:
            vo_dur = w.getnframes() / w.getframerate()
        with wave.open(str(result)) as w:
            mixed_dur = w.getnframes() / w.getframerate()
        self.assertAlmostEqual(vo_dur, mixed_dur, delta=0.3)


class TestAppIntegrationWiring(unittest.TestCase):
    """Source-level checks: the real render entry point
    (scene_graph.app_integration.generate_overscaled_video) actually calls
    build_exp_solar_audio_mix and feeds its result into the same FFmpeg
    export Overscaled uses — and ONLY for style_preset_id == "exp_solar"."""

    def test_generate_overscaled_video_wires_the_audio_mix_for_exp_solar_only(self):
        import scene_graph.app_integration as ai

        src = inspect.getsource(ai.generate_overscaled_video)
        self.assertIn('style_preset_id == "exp_solar"', src)
        self.assertIn("build_exp_solar_audio_mix", src)
        self.assertIn("final_audio_path", src)
        self.assertIn("_export_via_existing_renderer(", src)

    def test_overscaled_default_path_never_mentions_exp_solar_audio_unconditionally(self):
        # The guard above IS the isolation — this just double-checks the
        # fallback variable defaults to the raw voiceover_path (Overscaled's
        # existing, unchanged behavior) before any exp_solar-only branch.
        import scene_graph.app_integration as ai

        src = inspect.getsource(ai.generate_overscaled_video)
        self.assertIn("final_audio_path = voiceover_path", src)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestRealEndToEndAudioRender(unittest.TestCase):
    """The acceptance test: real video render + real Exp Solar audio mix,
    combined via the SAME _export_via_existing_renderer Overscaled uses,
    producing a final MP4 that actually contains an audio stream built
    from the mix (not just the raw voiceover)."""

    def setUp(self):
        se.reset_sfx_catalog_cache()
        self.tmp = Path(tempfile.mkdtemp())
        self.sfx_root = self.tmp / "sfxlib"
        se.write_test_sfx_library(self.sfx_root)

    def tearDown(self):
        se.reset_sfx_catalog_cache()

    def test_final_mp4_contains_the_exp_solar_audio_mix(self):
        import os

        from scene_graph.app_integration import _export_via_existing_renderer

        adapted, sg = _compile(_rich_exp_solar_rows())

        voiceover = self.tmp / "vo.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={sg.duration:.2f}", str(voiceover)],
            check=True, capture_output=True,
        )

        media_dir = self.tmp / "media"
        media_dir.mkdir()
        resolved_media = {}
        for i, node in enumerate(sg.nodes):
            if node.type == "checklist_item":
                continue
            p = media_dir / f"{node.id}.png"
            Image.new("RGB", (640, 360), (20, 20, 20)).save(p)
            resolved_media[node.id] = str(p)

        out_dir = self.tmp / "out"
        pipeline_result = run_overscaled_pipeline(
            adapted.rows, segment_id="seg", title="Audio E2E", style_preset_id="exp_solar",
            voiceover_path=str(voiceover), out_dir=out_dir, resolved_media=resolved_media,
            canvas_width=1280, canvas_height=720, resolution="640x360", fps=10,
        )
        self.assertTrue(pipeline_result.ok, pipeline_result.errors)

        mixed_path = build_exp_solar_audio_mix(
            pipeline_result.scene_graph, pipeline_result.layout,
            voiceover_path=voiceover, output_path=self.tmp / "exp_solar_audio_mix.wav", sfx_root=self.sfx_root,
        )
        self.assertTrue(mixed_path.is_file())
        # Not just a silent fallback copy — a real mix happened.
        self.assertNotEqual(mixed_path.read_bytes(), voiceover.read_bytes())

        final_path = self.tmp / "final.mp4"
        old_cwd = os.getcwd()
        try:
            _export_via_existing_renderer(
                pipeline_result.scene_graph, pipeline_result.segment_clip_path,
                voiceover_path=str(mixed_path), output_path=final_path,
                resolution="640x360", fps=10, work_dir=self.tmp / "export_work",
            )
        finally:
            os.chdir(old_cwd)

        self.assertTrue(final_path.is_file())
        import json as _json

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
             "-of", "json", str(final_path)],
            capture_output=True, text=True,
        )
        info = _json.loads(probe.stdout or "{}")
        stream_types = {s["codec_type"] for s in info.get("streams", [])}
        self.assertEqual(stream_types, {"video", "audio"})
        self.assertAlmostEqual(float(info["format"]["duration"]), sg.duration, delta=0.6)


if __name__ == "__main__":
    unittest.main()
