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
        settings = SmartEditingSettings(text_effects=True, sound_effects=False)
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
        settings = SmartEditingSettings(text_effects=False, sound_effects=False)
        plan = build_plan([], [], [], settings)
        self.assertEqual(plan.text_effects, [])
        self.assertEqual(plan.sfx_events, [])


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
