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


if __name__ == "__main__":
    unittest.main()
