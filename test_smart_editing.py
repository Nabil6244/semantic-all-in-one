"""Targeted tests for Smart Text Effects + SFX."""

from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from smart_editing import (
    SMART_EDITING_VERSION,
    SfxCatalog,
    SfxRequest,
    SmartEditingSettings,
    build_plan,
    cache_file,
    cache_settings_key,
    drawtext_filters,
    get_cached_whisper_words,
    get_sfx_catalog,
    mix_sfx_with_narration,
    plan_sfx_events,
    plan_text_effects,
    reset_sfx_catalog_cache,
    save_cache,
    scene_text_effects,
    write_test_sfx_library,
)


def _whisper_sample():
    words = []
    t = 0.0
    for token in (
        "welcome", "to", "today", "video", "we", "HATE", "MONDAYS", "because",
        "money", "matters",
    ):
        words.append((token.lower(), t, t + 0.35))
        t += 0.35
    return words


class TestSmartEditingPlan(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"scene_number": "1", "script_segment": "Welcome to today's video."},
            {
                "scene_number": "2",
                "script_segment": "We HATE MONDAYS because money matters.",
            },
        ]
        self.whisper = _whisper_sample()
        self.aligned = [
            {
                "scene_number": "1",
                "script_segment": self.rows[0]["script_segment"],
                "start_time": 0.0,
                "end_time": 1.4,
                "confidence": 1.0,
            },
            {
                "scene_number": "2",
                "script_segment": self.rows[1]["script_segment"],
                "start_time": 1.4,
                "end_time": 3.5,
                "confidence": 1.0,
            },
        ]

    def test_text_effects_off_returns_empty(self) -> None:
        settings = SmartEditingSettings(text_effects=False, sound_effects=False)
        self.assertEqual(plan_text_effects(self.rows, self.aligned, self.whisper, settings), [])

    def test_text_effects_on_finds_caps_phrase(self) -> None:
        settings = SmartEditingSettings(text_effects=True, sound_effects=False, intensity="high")
        effects = plan_text_effects(self.rows, self.aligned, self.whisper, settings)
        texts = {fx["text"] for fx in effects}
        self.assertTrue("HATE" in texts or "MONDAYS" in texts)
        for fx in effects:
            self.assertIn("start", fx)
            self.assertIn("effect", fx)

    def test_sfx_off_skips_events(self) -> None:
        settings = SmartEditingSettings(text_effects=True, sound_effects=False)
        fx = plan_text_effects(self.rows, self.aligned, self.whisper, settings)
        self.assertEqual(plan_sfx_events(self.aligned, fx, settings, catalog=SfxCatalog(Path("/tmp"), [])), [])

    def test_sfx_off_does_not_load_catalog(self) -> None:
        settings = SmartEditingSettings(
            text_effects=True, sound_effects=False, scene_ambience=False,
        )
        with patch("smart_editing.get_sfx_catalog") as mocked:
            build_plan(self.rows, self.aligned, self.whisper, settings)
        mocked.assert_not_called()

    def test_cache_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            audio = state / "narration.wav"
            with wave.open(str(audio), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(b"\x00\x00" * 48000)
            settings = SmartEditingSettings(sound_effects=False)
            first = build_plan(
                self.rows,
                self.aligned,
                self.whisper,
                settings,
                state_dir=state,
                audio_path=audio,
            )
            self.assertTrue(cache_file(state).is_file())
            cached = json.loads(cache_file(state).read_text(encoding="utf-8"))
            self.assertEqual(cached.get("smart_editing_version"), SMART_EDITING_VERSION)
            cached_words = get_cached_whisper_words(state, audio)
            self.assertIsNotNone(cached_words)
            with patch("smart_editing.plan_text_effects") as mocked:
                mocked.return_value = []
                second = build_plan(
                    self.rows,
                    self.aligned,
                    self.whisper,
                    settings,
                    state_dir=state,
                    audio_path=audio,
                )
            mocked.assert_not_called()
            self.assertEqual(second.whisper_words, first.whisper_words)

    def test_cache_invalidates_on_version_change(self) -> None:
        from smart_editing import _audio_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            audio = state / "narration.wav"
            with wave.open(str(audio), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(b"\x00\x00" * 48000)
            settings = SmartEditingSettings(sound_effects=False)
            cache_file(state).write_text(
                json.dumps(
                    {
                        "audio_key": _audio_fingerprint(audio),
                        "settings_key": cache_settings_key(settings),
                        "smart_editing_version": SMART_EDITING_VERSION - 1,
                        "plan": {
                            "text_effects": [{"scene_number": "1", "text": "OLD"}],
                            "sfx_events": [],
                            "whisper_words": [["old", 0, 1]],
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            with patch("smart_editing.plan_text_effects", return_value=[]) as mocked:
                build_plan(
                    self.rows,
                    self.aligned,
                    self.whisper,
                    settings,
                    state_dir=state,
                    audio_path=audio,
                )
            mocked.assert_called_once()

    def test_scene_local_timing(self) -> None:
        settings = SmartEditingSettings(text_effects=True, sound_effects=False, intensity="medium")
        plan = build_plan(self.rows, self.aligned, self.whisper, settings)
        local = scene_text_effects(plan, "2", scene_display_start=1.4)
        if local:
            self.assertGreaterEqual(local[0]["local_start"], 0.0)

    def test_drawtext_filter_escapes_text(self) -> None:
        from unittest.mock import patch

        fx = [{"text": "HATE:100%", "local_start": 0.1, "local_end": 0.5, "intensity": 0.6, "effect": "punch"}]
        with patch("smart_editing.ffmpeg_supports_drawtext", return_value=True):
            filt = drawtext_filters(fx, 1920, 1080)
        self.assertIn("drawtext=", filt)
        self.assertIn("HATE", filt)
        self.assertIn("fontfile=", filt)

    def test_drawtext_escapes_commas_in_fade_alpha(self) -> None:
        from unittest.mock import patch

        fx = [
            {
                "text": "attention",
                "local_start": 3.2,
                "local_end": 3.5,
                "intensity": 0.65,
                "effect": "word_reveal",
            },
            {
                "text": "breakthrough",
                "local_start": 3.5,
                "local_end": 3.82,
                "intensity": 0.65,
                "effect": "punch",
            },
        ]
        with patch("smart_editing.ffmpeg_supports_drawtext", return_value=True):
            filt = drawtext_filters(fx, 1920, 1080)
        # Alpha / enable expressions must escape commas so the filter graph stays valid.
        self.assertRegex(filt, r"if\(lt\(t\\,[0-9]")
        self.assertNotRegex(filt, r"fontcolor=white@\(if\(lt\(t,[0-9]")
        self.assertIn("borderw=", filt.split("drawtext=")[1])
        self.assertIn("letter_spacing=", filt)

    def test_drawtext_skipped_without_ffmpeg_support(self) -> None:
        from unittest.mock import patch

        fx = [{"text": "HELLO", "local_start": 0.1, "local_end": 0.4, "intensity": 0.5, "effect": "fade"}]
        with patch("smart_editing.ffmpeg_supports_drawtext", return_value=False):
            self.assertEqual(drawtext_filters(fx, 1280, 720), "")


class TestSfxCatalog(unittest.TestCase):
    def setUp(self) -> None:
        reset_sfx_catalog_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sfx_lib"
        write_test_sfx_library(self.root)
        self.aligned = [
            {"scene_number": "1", "start_time": 0.0, "end_time": 1.4},
            {"scene_number": "2", "start_time": 1.4, "end_time": 3.5},
        ]

    def tearDown(self) -> None:
        reset_sfx_catalog_cache()
        self.tmp.cleanup()

    def test_catalog_loads(self) -> None:
        catalog = get_sfx_catalog(root=self.root, force_reload=True)
        self.assertGreaterEqual(len(catalog), 5)

    def test_catalog_is_cached_in_memory(self) -> None:
        first = get_sfx_catalog(root=self.root, force_reload=True)
        with patch.object(SfxCatalog, "load", wraps=SfxCatalog.load) as mocked:
            second = get_sfx_catalog(root=self.root)
        mocked.assert_not_called()
        self.assertIs(first, second)

    def test_category_and_intensity_matching(self) -> None:
        catalog = get_sfx_catalog(root=self.root, force_reload=True)
        request = SfxRequest("text_reveal", "text", ("text_reveal", "reveal"), "medium", 0.75)
        entry = catalog.match(request)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.category, "text")
        self.assertIn("text_reveal", entry.tags)

    def test_duration_filter_skips_long_sound(self) -> None:
        catalog = get_sfx_catalog(root=self.root, force_reload=True)
        request = SfxRequest("scene_transition", "transition", ("movement",), "medium", 0.2)
        entry = catalog.match(request)
        self.assertIsNone(entry)

    def test_missing_file_is_skipped(self) -> None:
        catalog = SfxCatalog.load(
            self.root,
            catalog_path=self.root / "catalog.json",
        )
        broken = SfxRequest("text_emphasis", "impact", ("punch",), "high", 0.5)
        # Remove file for impact_test
        (self.root / "impact" / "impact_test.wav").unlink()
        reset_sfx_catalog_cache()
        catalog = SfxCatalog.load(self.root, self.root / "catalog.json")
        self.assertIsNone(catalog.match(broken))

    def test_semantic_sfx_planning_uses_ids_not_hardcoded_filenames(self) -> None:
        settings = SmartEditingSettings(text_effects=True, sound_effects=True, intensity="high")
        text_fx = [
            {
                "scene_number": "2",
                "text": "HATE",
                "start": 2.0,
                "end": 2.4,
                "effect": "punch",
                "intensity": 0.85,
            }
        ]
        catalog = get_sfx_catalog(root=self.root, force_reload=True)
        events = plan_sfx_events(self.aligned, text_fx, settings, catalog=catalog)
        self.assertTrue(events)
        self.assertIn("sfx_id", events[0])
        self.assertIn("source", events[0])
        self.assertIn("license", events[0])
        self.assertNotIn("whoosh_17.wav", events[0]["file"])

    def test_missing_sfx_never_fails_planning(self) -> None:
        empty = SfxCatalog(self.root, [])
        settings = SmartEditingSettings(sound_effects=True)
        events = plan_sfx_events(
            self.aligned,
            [{"scene_number": "1", "start": 0.5, "effect": "punch", "intensity": 0.7}],
            settings,
            catalog=empty,
        )
        self.assertEqual(events, [])

    def test_sfx_without_text_still_plans_transitions(self) -> None:
        settings = SmartEditingSettings(text_effects=False, sound_effects=True, intensity="medium")
        catalog = get_sfx_catalog(root=self.root, force_reload=True)
        aligned = [
            {"scene_number": "1", "start_time": 0.0, "end_time": 3.0, "script_segment": "city traffic at night"},
            {"scene_number": "2", "start_time": 3.0, "end_time": 6.2, "script_segment": "city traffic at night again"},
            {"scene_number": "3", "start_time": 6.2, "end_time": 9.5, "script_segment": "Meanwhile a rocket ignites far beyond"},
        ]
        rows = [
            {"scene_number": "1", "script_segment": aligned[0]["script_segment"]},
            {"scene_number": "2", "script_segment": aligned[1]["script_segment"]},
            {"scene_number": "3", "script_segment": aligned[2]["script_segment"]},
        ]
        from smart_editing import plan_scene_transitions

        transitions = plan_scene_transitions(rows, aligned, settings, gemini_settings={})
        events = plan_sfx_events(
            aligned, [], settings, catalog=catalog, scene_transitions=transitions,
        )
        # Sparse transitions — not on every scene boundary.
        self.assertLessEqual(len(transitions), 3)
        transition_events = [e for e in events if e.get("type") == "scene_transition"]
        self.assertEqual(len(transition_events), len([t for t in transitions if t.get("sfx", True)]))
        beat_events = [e for e in events if e.get("type") == "scene_beat"]
        self.assertGreaterEqual(len(beat_events), 0)

    def test_transition_sfx_variants_rotate(self) -> None:
        from smart_editing import _sfx_request_for_transition

        settings = SmartEditingSettings(sound_effects=True)
        cats = [
            _sfx_request_for_transition(settings, i).category
            for i in range(8)
        ]
        self.assertGreater(len(set(cats)), 1)

    def test_heuristic_transitions_are_sparse(self) -> None:
        from smart_editing import _heuristic_scene_transitions

        settings = SmartEditingSettings(intensity="medium")
        rows = []
        aligned = []
        t = 0.0
        texts = [
            "cars rush through wet streets",
            "cars keep rushing through streets",
            "Meanwhile a rocket prepares for launch",
            "engines ignite with fire and smoke",
            "the rocket rises into the night",
            "later scientists study the haze",
            "scientists keep studying the haze",
            "But then Pluto reveals a hidden ocean",
        ]
        for i, text in enumerate(texts, start=1):
            rows.append({"scene_number": str(i), "script_segment": text})
            aligned.append(
                {
                    "scene_number": str(i),
                    "script_segment": text,
                    "start_time": t,
                    "end_time": t + 3.0,
                }
            )
            t += 3.0
        picks = _heuristic_scene_transitions(rows, aligned, settings)
        self.assertGreaterEqual(len(picks), 1)
        self.assertLess(len(picks), len(aligned) - 1)

    def test_beat_sfx_when_text_off(self) -> None:
        settings = SmartEditingSettings(text_effects=False, sound_effects=True, intensity="high")
        aligned = []
        t = 0.0
        for i in range(1, 11):
            aligned.append(
                {
                    "scene_number": str(i),
                    "script_segment": f"Scene {i} about rockets and engines in the city.",
                    "start_time": t,
                    "end_time": t + 3.0,
                }
            )
            t += 3.0
        catalog = get_sfx_catalog(root=self.root, force_reload=True)
        events = plan_sfx_events(aligned, [], settings, catalog=catalog, scene_transitions=[])
        beats = [e for e in events if e.get("type") == "scene_beat"]
        self.assertGreaterEqual(len(beats), 1)
        self.assertLess(len(beats), len(aligned))


class TestSfxMixGraceful(unittest.TestCase):
    def test_missing_sfx_files_copy_narration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "vo.wav"
            out = root / "mixed.wav"
            with wave.open(str(src), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(b"\x00\x00" * 2400)
            events = [{"type": "whoosh", "start": 0.0, "duration": 0.2, "volume": 0.2, "file": "missing.wav"}]
            mix_sfx_with_narration(src, events, out, sfx_root=root)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)


class TestDefaults(unittest.TestCase):
    def test_settings_disabled_skips_plan(self) -> None:
        settings = SmartEditingSettings(
            text_effects=False,
            sound_effects=False,
            visual_transitions=False,
            scene_ambience=False,
        )
        plan = build_plan([], [], [], settings)
        self.assertEqual(plan.text_effects, [])
        self.assertEqual(plan.sfx_events, [])
        self.assertEqual(plan.scene_ambience, [])

    def test_per_feature_intensity_independent(self) -> None:
        settings = SmartEditingSettings(
            intensity="medium",
            visual_transitions_intensity="high",
            scene_ambience_intensity="low",
            sound_effects_intensity="medium",
            text_effects_intensity="high",
        )
        self.assertEqual(settings.transitions_intensity(), "high")
        self.assertEqual(settings.ambience_intensity(), "low")
        self.assertEqual(settings.sfx_intensity(), "medium")
        self.assertEqual(settings.text_intensity(), "high")

    def test_legacy_intensity_fills_missing_feature_levels(self) -> None:
        settings = SmartEditingSettings.from_dict({"intensity": "high"})
        self.assertEqual(settings.ambience_intensity(), "high")
        self.assertEqual(settings.transitions_intensity(), "high")
        self.assertEqual(settings.sfx_intensity(), "high")
        payload = settings.to_settings_dict()
        self.assertEqual(payload["scene_ambience_intensity"], "high")
        self.assertEqual(payload["visual_transitions_intensity"], "high")

    def test_ambience_volume_uses_ambience_intensity_only(self) -> None:
        from smart_editing import _ambience_volume

        low = SmartEditingSettings(
            intensity="high",
            scene_ambience_intensity="low",
            visual_transitions_intensity="high",
        )
        high = SmartEditingSettings(
            intensity="low",
            scene_ambience_intensity="high",
        )
        self.assertLess(_ambience_volume(low), _ambience_volume(high))


class TestSceneAmbience(unittest.TestCase):
    def test_merge_ambience_beds_does_not_span_visual_scenes(self) -> None:
        from smart_editing import _merge_ambience_beds

        beds = [
            {"scene_number": "1", "profile": "nature", "file": "a.wav", "start": 0.0, "end": 3.0, "duration": 3.0},
            {"scene_number": "2", "profile": "nature", "file": "a.wav", "start": 3.0, "end": 6.0, "duration": 3.0},
            {"scene_number": "3", "profile": "city", "file": "c.wav", "start": 6.0, "end": 9.0, "duration": 3.0},
        ]
        merged = _merge_ambience_beds(beds)
        self.assertEqual(len(merged), 3)
        self.assertEqual([b["scene_number"] for b in merged], ["1", "2", "3"])
        self.assertAlmostEqual(merged[0]["end"], 3.0)
        self.assertAlmostEqual(merged[1]["start"], 3.0)
        self.assertEqual(merged[0]["profile"], merged[1]["profile"])
        self.assertEqual(merged[0]["file"], merged[1]["file"])

    def test_merge_keeps_different_profiles_separate(self) -> None:
        from smart_editing import _merge_ambience_beds

        beds = [
            {"scene_number": "4", "profile": "room", "file": "r.wav", "start": 27.58, "end": 32.88, "duration": 5.3},
            {"scene_number": "5", "profile": "city", "file": "c.wav", "start": 32.88, "end": 41.92, "duration": 9.04},
        ]
        merged = _merge_ambience_beds(beds)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["profile"], "room")
        self.assertEqual(merged[1]["profile"], "city")

    def test_scene_4_to_5_beds_abut_at_visual_boundary(self) -> None:
        from smart_editing import _merge_ambience_beds, _annotate_ambience_boundary_fades

        visual_t = 32.880
        beds = [
            {
                "scene_number": "4",
                "profile": "room",
                "file": "ambience/ambience_15.wav",
                "start": 27.58,
                "end": visual_t,
                "duration": round(visual_t - 27.58, 3),
                "volume": 0.38,
            },
            {
                "scene_number": "5",
                "profile": "room",
                "file": "ambience/ambience_15.wav",
                "start": visual_t,
                "end": 41.92,
                "duration": round(41.92 - visual_t, 3),
                "volume": 0.38,
            },
        ]
        out = _merge_ambience_beds(beds)
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["end"], visual_t)
        self.assertAlmostEqual(out[1]["start"], visual_t)
        self.assertEqual(out[0]["scene_number"], "4")
        self.assertEqual(out[1]["scene_number"], "5")
        _annotate_ambience_boundary_fades(out)
        self.assertEqual(out[0]["fade_out"], 0.0)
        self.assertEqual(out[1]["fade_in"], 0.0)

    def test_beds_contained_in_exactly_one_visual_scene(self) -> None:
        from smart_editing import _merge_ambience_beds, _annotate_ambience_boundary_fades

        windows = {
            "4": (27.58, 32.88),
            "5": (32.88, 41.92),
            "6": (41.92, 52.12),
        }
        beds = [
            {
                "scene_number": sn,
                "profile": "room",
                "file": "ambience/ambience_15.wav",
                "start": start,
                "end": end,
                "duration": round(end - start, 3),
            }
            for sn, (start, end) in windows.items()
        ]
        out = _merge_ambience_beds(beds)
        _annotate_ambience_boundary_fades(out)
        self.assertEqual(len(out), 3)
        for bed in out:
            sn = str(bed["scene_number"])
            self.assertNotIn("-", sn)
            vs, ve = windows[sn]
            self.assertAlmostEqual(bed["start"], vs)
            self.assertAlmostEqual(bed["end"], ve)
            self.assertGreaterEqual(bed["start"], vs - 1e-9)
            self.assertLessEqual(bed["end"], ve + 1e-9)

    def test_heuristic_ambience_profiles(self) -> None:
        from smart_editing import _heuristic_ambience_profile

        self.assertEqual(_heuristic_ambience_profile("cars rush through city traffic"), "traffic")
        self.assertEqual(_heuristic_ambience_profile("rocket engines ignite"), "technology")
        self.assertEqual(_heuristic_ambience_profile("wind in the forest"), "nature")
        self.assertEqual(_heuristic_ambience_profile("heavy rain and thunder"), "rain")

    def test_plan_scene_ambience_resolves_beds(self) -> None:
        from smart_editing import plan_scene_ambience, write_test_sfx_library

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_test_sfx_library(root)
            aligned = [
                {
                    "scene_number": "1",
                    "script_segment": "Cars rush through wet city streets.",
                    "start_time": 0.0,
                    "end_time": 3.0,
                },
                {
                    "scene_number": "2",
                    "script_segment": "Rocket engines ignite at the launch pad.",
                    "start_time": 3.0,
                    "end_time": 6.0,
                },
            ]
            rows = [
                {"scene_number": "1", "script_segment": aligned[0]["script_segment"]},
                {"scene_number": "2", "script_segment": aligned[1]["script_segment"]},
            ]
            settings = SmartEditingSettings(scene_ambience=True, sound_effects=False)
            cat = get_sfx_catalog(root=root)
            beds = plan_scene_ambience(rows, aligned, settings, catalog=cat)
            self.assertEqual(len(beds), 2)
            profiles = {b["profile"] for b in beds}
            self.assertIn("city", profiles)
            self.assertIn("technology", profiles)
            for bed in beds:
                self.assertGreater(bed["duration"], 0)
                self.assertTrue(str(bed["file"]).startswith("ambience/"))

    def test_mix_ambience_beds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_test_sfx_library(root)
            src = root / "vo.wav"
            out = root / "mixed.wav"
            with wave.open(str(src), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(b"\x00\x00" * 72000)
            beds = [
                {
                    "type": "scene_ambience",
                    "start": 0.0,
                    "duration": 2.0,
                    "volume": 0.22,
                    "file": "ambience/ambience_room_test.wav",
                }
            ]
            stats: dict = {}
            mix_sfx_with_narration(src, [], out, sfx_root=root, ambience_beds=beds, stats=stats)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)
            self.assertEqual(stats.get("ambience_mixed"), 1)
            self.assertFalse(stats.get("used_fallback"))

    def test_mix_multiple_ambience_beds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_test_sfx_library(root)
            src = root / "vo.wav"
            out = root / "mixed.wav"
            with wave.open(str(src), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(b"\x00\x00" * 24000 * 8)
            beds = [
                {
                    "type": "scene_ambience",
                    "start": 0.0,
                    "end": 3.0,
                    "duration": 3.0,
                    "volume": 0.30,
                    "file": "ambience/ambience_room_test.wav",
                },
                {
                    "type": "scene_ambience",
                    "start": 3.0,
                    "end": 6.0,
                    "duration": 3.0,
                    "volume": 0.30,
                    "file": "ambience/ambience_city_test.wav",
                },
            ]
            stats: dict = {}
            mix_sfx_with_narration(src, [], out, sfx_root=root, ambience_beds=beds, stats=stats)
            self.assertTrue(out.is_file())
            self.assertEqual(stats.get("ambience_mixed"), 2)
            self.assertFalse(stats.get("used_fallback"))

    def test_ambience_beds_use_display_timeline(self) -> None:
        from smart_editing import _resolve_ambience_beds

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_test_sfx_library(root)
            cat = get_sfx_catalog(root=root)
            aligned = [
                {"scene_number": "1", "start_time": 0.5, "end_time": 2.5},
                {"scene_number": "2", "start_time": 2.5, "end_time": 5.0},
            ]
            profiles = [
                {"scene_number": "1", "profile": "room"},
                {"scene_number": "2", "profile": "room"},
            ]
            settings = SmartEditingSettings(scene_ambience=True, intensity="medium")
            windows = {"1": (0.0, 2.5), "2": (2.5, 5.0)}
            beds = _resolve_ambience_beds(
                profiles, aligned, settings, cat, display_windows=windows,
            )
            self.assertEqual(len(beds), 2)
            self.assertAlmostEqual(beds[0]["start"], 0.0)
            self.assertAlmostEqual(beds[0]["end"], 2.5)
            self.assertAlmostEqual(beds[1]["start"], 2.5)

    def test_smooth_ambience_profiles(self) -> None:
        from smart_editing import _smooth_ambience_profiles

        profiles = [
            {"scene_number": "1", "profile": "nature"},
            {"scene_number": "2", "profile": "city"},
            {"scene_number": "3", "profile": "nature"},
            {"scene_number": "4", "profile": "nature"},
            {"scene_number": "5", "profile": "nature"},
        ]
        smoothed = _smooth_ambience_profiles(profiles, min_run=3)
        self.assertEqual(smoothed[1]["profile"], "nature")

    def test_delayed_ambience_audible_beyond_scene_one(self) -> None:
        """Regression: fade on local clip timeline, then adelay to global start."""
        import struct
        from smart_editing import _ffmpeg_mix_ambience_chunk, sfx_library_root

        root = sfx_library_root()
        src = root / "ambience/ambience_06.wav"
        if not src.is_file():
            self.skipTest("production ambience library not installed")

        def _rms_at(path: Path, t: float) -> float:
            with wave.open(str(path), "rb") as wf:
                sr = wf.getframerate()
                wf.setpos(min(int(t * sr), max(0, wf.getnframes() - 1)))
                frames = wf.readframes(int(0.5 * sr))
            samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
            return (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0.0

        cases = [
            ("0s", {"start": 0.0, "duration": 28.0, "volume": 0.30}, 0.3, 15.0, True),
            ("28s", {"start": 28.0, "duration": 4.5, "volume": 0.30}, 28.3, 0.3, False),
            ("95s", {"start": 95.0, "duration": 5.0, "volume": 0.30}, 95.3, 0.3, False),
            ("190s", {"start": 190.0, "duration": 6.0, "volume": 0.30}, 190.3, 0.3, False),
            ("580s", {"start": 580.0, "duration": 20.0, "volume": 0.30}, 580.3, 0.3, False),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for label, bed, probe_t, silent_before, audible_at_probe in cases:
                out = Path(tmp) / f"bed_{label}.wav"
                ok = _ffmpeg_mix_ambience_chunk(
                    [(src, bed)], out, trim_duration=620.0,
                )
                self.assertTrue(ok, f"mix failed for bed {label}")
                rms_probe = _rms_at(out, probe_t)
                rms_early = _rms_at(out, silent_before)
                if audible_at_probe:
                    self.assertGreater(rms_probe, 20.0, f"{label}: expected audible at {probe_t}s")
                else:
                    self.assertGreater(rms_probe, 20.0, f"{label}: expected audible at {probe_t}s")
                    self.assertLess(rms_early, 20.0, f"{label}: expected silence before start at {silent_before}s")
            # delayed bed must not bleed to t=0
            late = Path(tmp) / "bed_95s.wav"
            self.assertLess(_rms_at(late, 0.3), 20.0, "95s bed must not be audible at timeline start")

    def test_annotate_ambience_boundary_fades(self) -> None:
        from smart_editing import _annotate_ambience_boundary_fades

        beds = [
            {
                "scene_number": "7",
                "profile": "atmospheric",
                "start": 0.0,
                "end": 10.0,
                "duration": 10.0,
            },
            {
                "scene_number": "8",
                "profile": "room",
                "start": 10.0,
                "end": 20.0,
                "duration": 10.0,
            },
        ]
        _annotate_ambience_boundary_fades(beds)
        self.assertAlmostEqual(beds[0]["fade_out"], 0.10)
        self.assertEqual(beds[1]["fade_in"], 0.0)

    def test_annotate_same_profile_boundary_hard_abut(self) -> None:
        from smart_editing import _annotate_ambience_boundary_fades

        beds = [
            {"scene_number": "4", "profile": "room", "start": 27.58, "end": 32.88, "duration": 5.3},
            {"scene_number": "5", "profile": "room", "start": 32.88, "end": 41.92, "duration": 9.04},
        ]
        _annotate_ambience_boundary_fades(beds)
        self.assertEqual(beds[0]["fade_out"], 0.0)
        self.assertEqual(beds[1]["fade_in"], 0.0)

    def test_same_profile_boundary_no_silence_gap(self) -> None:
        """Same-profile split beds must abut without an audible silence hole."""
        import math
        import struct

        from smart_editing import _annotate_ambience_boundary_fades, _ffmpeg_mix_ambience_chunk

        def _make_tone(path: Path, freq: float, *, dur: float = 30.0, sr: int = 24000) -> None:
            n = int(sr * dur)
            payload = struct.pack(
                "<" + "h" * n,
                *[int(8000 * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)],
            )
            with wave.open(str(path), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(payload)

        def _rms_at(path: Path, t: float, *, win: float = 0.04, sr: int = 24000) -> float:
            with wave.open(str(path), "rb") as wf:
                pos = min(int(t * sr), max(0, wf.getnframes() - 1))
                wf.setpos(pos)
                frames = wf.readframes(int(win * sr))
            samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
            return (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0.0

        boundary = 32.88
        beds = [
            {
                "profile": "room",
                "scene_number": "4",
                "start": 27.58,
                "end": boundary,
                "duration": round(boundary - 27.58, 3),
                "volume": 0.38,
            },
            {
                "profile": "room",
                "scene_number": "5",
                "start": boundary,
                "end": 41.92,
                "duration": round(41.92 - boundary, 3),
                "volume": 0.38,
            },
        ]
        _annotate_ambience_boundary_fades(beds)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tone = root / "room.wav"
            _make_tone(tone, 220.0)
            mixed = root / "mixed.wav"
            self.assertTrue(
                _ffmpeg_mix_ambience_chunk(
                    [(tone, beds[0]), (tone, beds[1])], mixed, trim_duration=45.0,
                )
            )
            # Probe straddling the visual cut — must stay audible (no fade hole).
            for t in (boundary - 0.05, boundary, boundary + 0.05):
                self.assertGreater(
                    _rms_at(mixed, t),
                    400.0,
                    f"expected continuous same-profile ambience at t={t}",
                )

    def test_profile_boundary_previous_ambience_stops_at_cut(self) -> None:
        """Visual/ambience profile change: outgoing bed must not bleed past the boundary."""
        import math
        import struct

        from smart_editing import _annotate_ambience_boundary_fades, _ffmpeg_mix_ambience_chunk

        def _make_tone(path: Path, freq: float, *, dur: float = 30.0, sr: int = 24000) -> None:
            n = int(sr * dur)
            payload = struct.pack(
                "<" + "h" * n,
                *[int(8000 * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)],
            )
            with wave.open(str(path), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(payload)

        def _rms_at(path: Path, t: float, *, win: float = 0.05, sr: int = 24000) -> float:
            with wave.open(str(path), "rb") as wf:
                pos = min(int(t * sr), max(0, wf.getnframes() - 1))
                wf.setpos(pos)
                frames = wf.readframes(int(win * sr))
            samples = struct.unpack("<" + "h" * (len(frames) // 2), frames)
            return (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0.0

        boundary = 10.0
        beds = [
            {
                "profile": "atmospheric",
                "scene_number": "7",
                "start": 0.0,
                "end": boundary,
                "duration": boundary,
                "volume": 0.30,
            },
            {
                "profile": "room",
                "scene_number": "8",
                "start": boundary,
                "end": 20.0,
                "duration": 10.0,
                "volume": 0.30,
            },
        ]
        _annotate_ambience_boundary_fades(beds)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tone_a = root / "a.wav"
            tone_b = root / "b.wav"
            _make_tone(tone_a, 440.0)
            _make_tone(tone_b, 880.0)

            solo_a = root / "solo_a.wav"
            solo_b = root / "solo_b.wav"
            mixed = root / "mixed.wav"
            self.assertTrue(
                _ffmpeg_mix_ambience_chunk([(tone_a, beds[0])], solo_a, trim_duration=20.0)
            )
            self.assertTrue(
                _ffmpeg_mix_ambience_chunk([(tone_b, beds[1])], solo_b, trim_duration=20.0)
            )
            self.assertTrue(
                _ffmpeg_mix_ambience_chunk(
                    [(tone_a, beds[0]), (tone_b, beds[1])], mixed, trim_duration=20.0,
                )
            )

            probe = boundary + 0.05
            rms_a = _rms_at(solo_a, probe)
            rms_b = _rms_at(solo_b, probe)
            rms_mix = _rms_at(mixed, probe)
            rms_a_before = _rms_at(solo_a, boundary - 0.03)

            self.assertGreater(rms_b, 500.0, "incoming bed should be audible after boundary")
            self.assertLess(rms_a, 80.0, "outgoing bed must be silent shortly after boundary")
            self.assertLess(
                rms_mix,
                rms_b * 1.15,
                "mix after boundary should track incoming bed, not carry outgoing",
            )
            self.assertGreater(
                rms_a_before,
                rms_a * 3.0,
                "outgoing bed should finish fading before/at boundary",
            )


class TestScriptAndCsvPaths(unittest.TestCase):
    def test_same_rows_shape_for_ai_script_and_csv(self) -> None:
        rows_csv = [{"scene_number": "1", "script_segment": "Hello WORLD today."}]
        rows_ai = [{"scene_number": "1", "script_segment": "Hello WORLD today."}]
        whisper = [("hello", 0.0, 0.3), ("world", 0.3, 0.6), ("today", 0.6, 0.9)]
        aligned = [
            {
                "scene_number": "1",
                "script_segment": "Hello WORLD today.",
                "start_time": 0.0,
                "end_time": 1.0,
                "confidence": 1.0,
            }
        ]
        settings = SmartEditingSettings(text_effects=True, sound_effects=False)
        self.assertEqual(
            plan_text_effects(rows_csv, aligned, whisper, settings),
            plan_text_effects(rows_ai, aligned, whisper, settings),
        )


class TestWindowsMixHardening(unittest.TestCase):
    def test_mix_chunk_size_windows_default(self) -> None:
        from smart_editing import _mix_chunk_size
        import os

        with patch("smart_editing.sys.platform", "win32"):
            os.environ.pop("SMART_MIX_CHUNK_SIZE", None)
            self.assertEqual(_mix_chunk_size(), 8)
        with patch("smart_editing.sys.platform", "darwin"):
            os.environ.pop("SMART_MIX_CHUNK_SIZE", None)
            self.assertEqual(_mix_chunk_size(), 24)

    def test_win32_rewrites_to_filter_complex_script(self) -> None:
        from smart_editing import _run_ffmpeg_cmd

        captured: list = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))

            class R:
                returncode = 0
                stderr = ""

            return R()

        with patch("smart_editing.sys.platform", "win32"):
            with patch("smart_editing.hidden_subprocess.run", side_effect=fake_run):
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / "out.wav"
                    cmd = [
                        "ffmpeg", "-y", "-i", "a.wav",
                        "-filter_complex", "anull[aout]",
                        "-map", "[aout]", str(out),
                    ]
                    self.assertTrue(_run_ffmpeg_cmd(cmd, work_dir=Path(tmp)))
        self.assertEqual(len(captured), 1)
        self.assertIn("-filter_complex_script", captured[0])
        self.assertNotIn("-filter_complex", captured[0])

    def test_is_win_cmdline_error(self) -> None:
        from smart_editing import _is_win_cmdline_error

        with patch("smart_editing.sys.platform", "win32"):
            err = OSError(206, "The filename or extension is too long")
            err.winerror = 206  # type: ignore[attr-defined]
            self.assertTrue(_is_win_cmdline_error(err))
        with patch("smart_editing.sys.platform", "darwin"):
            err = OSError(206, "The filename or extension is too long")
            err.winerror = 206  # type: ignore[attr-defined]
            self.assertFalse(_is_win_cmdline_error(err))


if __name__ == "__main__":
    unittest.main()


class TestAmbienceVolumeControl(unittest.TestCase):
    """Operator-facing ambience level: explicit override, Auto, and mute."""

    def _s(self, **kw):
        from smart_editing import SmartEditingSettings
        return SmartEditingSettings.from_dict(kw)

    def test_auto_still_follows_intensity_step(self) -> None:
        from smart_editing import _ambience_volume
        for level, expected in (("low", 0.22), ("medium", 0.30), ("high", 0.38)):
            s = self._s(scene_ambience_intensity=level)
            self.assertIsNone(s.scene_ambience_volume)
            self.assertTrue(s.ambience_volume_is_auto())
            self.assertAlmostEqual(_ambience_volume(s), expected)

    def test_explicit_volume_overrides_intensity(self) -> None:
        from smart_editing import _ambience_volume
        s = self._s(scene_ambience_intensity="low", scene_ambience_volume=0.65)
        self.assertFalse(s.ambience_volume_is_auto())
        self.assertAlmostEqual(_ambience_volume(s), 0.65)

    def test_volume_is_clamped_and_bad_input_falls_back_to_auto(self) -> None:
        self.assertAlmostEqual(self._s(scene_ambience_volume=4.0).ambience_volume(), 1.0)
        self.assertAlmostEqual(self._s(scene_ambience_volume=-2.0).ambience_volume(), 0.0)
        self.assertTrue(self._s(scene_ambience_volume="loud").ambience_volume_is_auto())
        self.assertTrue(self._s(scene_ambience_volume=None).ambience_volume_is_auto())

    def test_bounds_unchanged_at_the_default_level(self) -> None:
        """The historical clamp window must survive untouched at 0.30."""
        from smart_editing import ambience_volume_bounds
        self.assertEqual(ambience_volume_bounds(0.30), (0.05, 0.42))

    def test_louder_setting_raises_the_ceiling_instead_of_being_clipped(self) -> None:
        from smart_editing import ambience_volume_bounds
        lo, hi = ambience_volume_bounds(0.60)
        self.assertGreater(hi, 0.42)
        self.assertGreater(lo, 0.05)

    def test_volume_survives_a_settings_roundtrip(self) -> None:
        from smart_editing import SmartEditingSettings
        s = self._s(scene_ambience_volume=0.65)
        again = SmartEditingSettings.from_dict(s.to_settings_dict())
        self.assertAlmostEqual(again.ambience_volume(), 0.65)
        self.assertFalse(again.ambience_volume_is_auto())

    def test_changing_volume_invalidates_the_plan_cache(self) -> None:
        """Otherwise a volume change would reuse the previously planned beds."""
        self.assertNotEqual(
            self._s(scene_ambience_volume=0.65).fingerprint(),
            self._s().fingerprint(),
        )

    def test_zero_volume_plans_no_beds_at_all(self) -> None:
        from smart_editing import _resolve_ambience_beds
        profiles = [{"scene_number": "1", "profile": "room"}]
        rows = [{"scene_number": "1", "start_time": 0.0, "end_time": 5.0}]
        beds = _resolve_ambience_beds(
            profiles, rows, self._s(scene_ambience_volume=0.0), object(),
        )
        self.assertEqual(beds, [])


class TestAmbienceBedClampScalesWithOperatorLevel(unittest.TestCase):
    """The Audio Director must not clip a deliberately loud operator setting."""

    def _bed(self, volume, base=None):
        bed = {"scene_number": "1", "volume": volume}
        if base is not None:
            bed["base_volume"] = base
        return bed

    def _plan(self, intensity):
        from editorial.schema import EditorialPlan, EditorialScene
        scene = EditorialScene(scene_number="1", start=0.0, end=2.0, duration=2.0)
        scene.ambience_intensity = intensity
        scene.allow_silence = False
        return EditorialPlan(scenes=[scene])

    def test_legacy_beds_keep_the_fixed_window(self) -> None:
        from editorial.audio_director import apply_ambience_intensity_to_beds
        out = apply_ambience_intensity_to_beds(
            [self._bed(0.30)], self._plan(3.0),
        )
        self.assertAlmostEqual(out[0]["volume"], 0.42)

    def test_operator_base_scales_the_ceiling(self) -> None:
        from editorial.audio_director import apply_ambience_intensity_to_beds
        out = apply_ambience_intensity_to_beds(
            [self._bed(0.60, base=0.60)], self._plan(3.0),
        )
        self.assertGreater(out[0]["volume"], 0.42)

    def test_muted_base_stays_silent(self) -> None:
        from editorial.audio_director import apply_ambience_intensity_to_beds
        out = apply_ambience_intensity_to_beds(
            [self._bed(0.0, base=0.0)], self._plan(3.0),
        )
        self.assertEqual(out[0]["volume"], 0.0)


class TestIntensityLevelsAreMonotonic(unittest.TestCase):
    """Low/Medium/High must actually move each feature, and only its own."""

    SCENES = [
        "The research vessel left harbour before sunrise carrying nineteen scientists.",
        "Sonar mapping revealed a trench far deeper than any published chart suggested.",
        "But then the instruments began returning readings nobody could explain at all.",
        "Carbon dating placed the sediment layer at roughly forty thousand years old.",
        "Meanwhile in Oslo a separate team was reaching the exact opposite conclusion.",
        "Funding collapsed that winter and the entire project very nearly ended there.",
        "Suddenly a private donor stepped forward with an unusual condition attached.",
        "Robotic submersibles descended through crushing pressure into total darkness.",
    ]

    def _script(self):
        rows, aligned, words = [], [], []
        t = 0.0
        for i, txt in enumerate(self.SCENES, 1):
            rows.append({"scene_number": str(i), "script_segment": txt, "prompt": "p"})
            aligned.append({"scene_number": str(i), "script_segment": txt,
                            "start_time": t, "end_time": t + 7.0})
            for w in txt.split():
                words.append([w, t, t + 0.35]); t += 0.38
            t = aligned[-1]["end_time"]
        return rows, aligned, words

    @staticmethod
    def _catalog_available() -> bool:
        """CI has no bundled SFX library, so nothing can be planned there.

        These assertions are about the intensity CURVE, which only shows up
        once real catalog entries exist. Without a catalog every volume is
        0.0 and the comparison is vacuous — skip rather than assert nothing.
        """
        try:
            from smart_editing import get_sfx_catalog
            return bool(get_sfx_catalog().entries)
        except Exception:
            return False

    def _plan(self, **kw):
        from smart_editing import SmartEditingSettings, build_plan
        rows, aligned, words = self._script()
        return build_plan(rows, aligned, words, SmartEditingSettings.from_dict(kw))

    def _levels(self, key, measure):
        return [measure(self._plan(**{key: lvl})) for lvl in ("low", "medium", "high")]

    def test_text_effect_count_rises_with_its_own_intensity(self) -> None:
        lo, md, hi = self._levels("text_effects_intensity", lambda p: len(p.text_effects))
        self.assertLess(lo, md)
        self.assertLess(md, hi)

    def test_transition_count_rises_with_its_own_intensity(self) -> None:
        lo, md, hi = self._levels(
            "visual_transitions_intensity", lambda p: len(p.scene_transitions),
        )
        self.assertLess(lo, md)
        self.assertLess(md, hi)

    def test_sfx_volume_rises_with_its_own_intensity(self) -> None:
        if not self._catalog_available():
            self.skipTest("no bundled SFX catalog in this environment")
        from statistics import mean
        def vol(p):
            return mean([e["volume"] for e in p.sfx_events]) if p.sfx_events else 0.0
        lo, md, hi = self._levels("sound_effects_intensity", vol)
        self.assertLess(lo, md)
        self.assertLess(md, hi)

    def test_ambience_volume_rises_with_its_own_intensity(self) -> None:
        if not self._catalog_available():
            self.skipTest("no bundled SFX catalog in this environment")
        from statistics import mean
        def vol(p):
            return mean([b["volume"] for b in p.scene_ambience]) if p.scene_ambience else 0.0
        lo, md, hi = self._levels("scene_ambience_intensity", vol)
        self.assertLess(lo, md)
        self.assertLess(md, hi)

    def test_the_volume_curves_are_monotonic_without_a_catalog(self) -> None:
        """Catalog-free proof of the same contract, so CI still covers it.

        The plan-level volume tests above need real SFX entries and skip where
        none are bundled; these assert the underlying level tables directly.
        """
        from smart_editing import SmartEditingSettings, _ambience_volume, _sfx_base_volume
        amb = [_ambience_volume(SmartEditingSettings.from_dict(
            {"scene_ambience_intensity": lvl})) for lvl in ("low", "medium", "high")]
        self.assertLess(amb[0], amb[1])
        self.assertLess(amb[1], amb[2])
        sfx = [_sfx_base_volume(SmartEditingSettings.from_dict(
            {"sound_effects_intensity": lvl})) for lvl in ("low", "medium", "high")]
        self.assertLess(sfx[0], sfx[1])
        self.assertLess(sfx[1], sfx[2])

    def test_each_intensity_moves_only_its_own_feature(self) -> None:
        """Turning one dial must not quietly change the others."""
        base = self._plan()
        amb = self._plan(scene_ambience_intensity="high")
        self.assertEqual(len(base.text_effects), len(amb.text_effects))
        self.assertEqual(len(base.scene_transitions), len(amb.scene_transitions))
        trans = self._plan(visual_transitions_intensity="high")
        self.assertEqual(len(base.text_effects), len(trans.text_effects))
        self.assertEqual(len(base.scene_ambience), len(trans.scene_ambience))

    def test_transition_budget_is_actually_reachable(self) -> None:
        """The heuristic must be able to spend its budget on real copy."""
        from smart_editing import (SmartEditingSettings, plan_scene_transitions,
                                   _transition_budget)
        rows, aligned, _ = self._script()
        n_boundaries = len(aligned) - 1
        for lvl in ("low", "medium", "high"):
            s = SmartEditingSettings.from_dict({"visual_transitions_intensity": lvl})
            planned = len(plan_scene_transitions(rows, aligned, s))
            self.assertEqual(planned, _transition_budget(n_boundaries, lvl), lvl)

    def test_legacy_global_intensity_drives_every_feature(self) -> None:
        from smart_editing import SmartEditingSettings
        for lvl in ("low", "medium", "high"):
            s = SmartEditingSettings.from_dict({"intensity": lvl})
            self.assertEqual(s.text_intensity(), lvl)
            self.assertEqual(s.sfx_intensity(), lvl)
            self.assertEqual(s.transitions_intensity(), lvl)
            self.assertEqual(s.ambience_intensity(), lvl)

    def test_a_per_feature_level_overrides_the_global_one(self) -> None:
        from smart_editing import SmartEditingSettings
        s = SmartEditingSettings.from_dict(
            {"intensity": "low", "sound_effects_intensity": "high"},
        )
        self.assertEqual(s.sfx_intensity(), "high")
        self.assertEqual(s.text_intensity(), "low")

    def test_unusable_levels_fall_back_to_medium(self) -> None:
        from smart_editing import SmartEditingSettings
        for bad in ("", None, "LOUD", "9", 3):
            s = SmartEditingSettings.from_dict({"sound_effects_intensity": bad})
            self.assertEqual(s.sfx_intensity(), "medium", repr(bad))
        # ...but a valid level survives whitespace and casing from the UI.
        s = SmartEditingSettings.from_dict({"sound_effects_intensity": "  HIGH  "})
        self.assertEqual(s.sfx_intensity(), "high")
