"""Tests for Editorial Plan schema, builder, cache, and render integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from editorial.builder import build_editorial_plan
from editorial.persistence import (
    cache_settings_key,
    load_cached_plan,
    plan_file,
    save_editorial_plan,
)
from editorial.schema import EditorialPlan, EditorialScene
from smart_editing import SmartEditingSettings, build_plan, plan_scene_transitions
from video_generator import _camera_motion, _scene_display_timeline
from visual_director.schema import VisualPlan, VisualScene


def _sample_rows():
    return [
        {"scene_number": "1", "script_segment": "Welcome to the secret story.", "asset_type": "image", "prompt": "city skyline"},
        {
            "scene_number": "2",
            "script_segment": "Scientists found shocking evidence in the data.",
            "asset_type": "stock_video",
            "prompt": "research lab",
        },
        {"scene_number": "3", "script_segment": "Thank you for watching.", "asset_type": "image", "prompt": "sunset"},
    ]


def _sample_aligned():
    return [
        {"scene_number": "1", "script_segment": "Welcome to the secret story.", "start_time": 0.0, "end_time": 2.0},
        {"scene_number": "2", "script_segment": "Scientists found shocking evidence.", "start_time": 2.0, "end_time": 5.0},
        {"scene_number": "3", "script_segment": "Thank you for watching.", "start_time": 5.0, "end_time": 7.0},
    ]


def _visual_plan() -> VisualPlan:
    return VisualPlan(
        topic="Test",
        scenes=[
            VisualScene(
                scene_id=1,
                narration="Welcome to the secret story.",
                visual_goal="Hook viewer",
                visual_description="City skyline at dawn",
                asset_type="image",
                provider_preference="flow_image",
                search_queries=[],
                timestamp_needed=False,
                timestamp_hint="",
                duration=2.5,
                importance="high",
                fallbacks=[],
                visual_treatment="slow_push",
                transition="dissolve",
            ),
            VisualScene(
                scene_id=2,
                narration="Scientists found shocking evidence.",
                visual_goal="Show proof",
                visual_description="Research laboratory",
                asset_type="stock_video",
                provider_preference="stock_video",
                search_queries=["research lab"],
                timestamp_needed=False,
                timestamp_hint="",
                duration=3.0,
                importance="medium",
                fallbacks=[],
                visual_treatment="static",
                transition="fade",
            ),
            VisualScene(
                scene_id=3,
                narration="Thank you for watching.",
                visual_goal="Outro",
                visual_description="Sunset horizon",
                asset_type="image",
                provider_preference="flow_image",
                search_queries=[],
                timestamp_needed=False,
                timestamp_hint="",
                duration=2.0,
                importance="low",
                fallbacks=[],
                visual_treatment="pull_out",
                transition="cut",
            ),
        ],
    )


class TestEditorialSchema(unittest.TestCase):
    def test_round_trip(self) -> None:
        scene = EditorialScene(
            scene_number="1",
            start=0.0,
            end=2.5,
            duration=2.5,
            purpose="hook",
            attention_score=0.9,
            camera_style="push_in",
            transition_in="dissolve",
            visual_goal="Hook viewer",
            visual_description="City skyline",
        )
        plan = EditorialPlan(audio_end=10.0, scenes=[scene])
        restored = EditorialPlan.from_dict(plan.to_dict())
        self.assertEqual(restored.audio_end, 10.0)
        self.assertEqual(len(restored.scenes), 1)
        self.assertEqual(restored.scenes[0].purpose, "hook")
        self.assertEqual(restored.scenes[0].camera_style, "push_in")
        self.assertEqual(restored.scenes[0].visual_goal, "Hook viewer")

    def test_transition_style_map_skips_cut(self) -> None:
        plan = EditorialPlan(
            scenes=[
                EditorialScene(scene_number="1", start=0, end=1, duration=1, transition_in="fade"),
                EditorialScene(scene_number="2", start=1, end=2, duration=1, transition_in="cut"),
            ]
        )
        self.assertEqual(plan.transition_style_map(), {"1": "fade"})


class TestEditorialBuilder(unittest.TestCase):
    def test_timeline_matches_display_timeline(self) -> None:
        rows = _sample_rows()
        aligned = _sample_aligned()
        audio_end = 7.0
        plan = build_editorial_plan(rows, aligned, audio_end)
        expected = _scene_display_timeline(aligned, audio_end)
        actual = plan.display_timeline()
        self.assertEqual(len(actual), len(expected))
        for (a_start, a_end), (e_start, e_end) in zip(actual, expected):
            self.assertAlmostEqual(a_start, e_start, places=4)
            self.assertAlmostEqual(a_end, e_end, places=4)

    def test_csv_only_heuristic_plan(self) -> None:
        plan = build_editorial_plan(_sample_rows(), _sample_aligned(), 7.0)
        self.assertEqual(len(plan.scenes), 3)
        self.assertEqual(plan.scenes[0].purpose, "hook")
        self.assertGreater(plan.scenes[0].attention_score, 0.7)
        self.assertIn(plan.scenes[-1].purpose, ("outro", "transition"))
        for scene in plan.scenes:
            self.assertIn(scene.camera_style, {"push_in", "pull_out", "static", "hold", "subtle_drift"})
            self.assertTrue(scene.visual_variety_key)

    def test_visual_plan_fields_preserved(self) -> None:
        vp = _visual_plan()
        plan = build_editorial_plan(_sample_rows(), _sample_aligned(), 7.0, visual_plan=vp)
        by_sn = plan.scene_by_number()
        self.assertEqual(by_sn["1"].visual_goal, "Hook viewer")
        self.assertEqual(by_sn["1"].visual_description, "City skyline at dawn")
        self.assertEqual(by_sn["1"].camera_style, "push_in")
        self.assertEqual(by_sn["1"].transition_in, "dissolve")
        self.assertEqual(by_sn["2"].camera_style, "static")
        self.assertEqual(by_sn["3"].camera_style, "pull_out")

    def test_neighbor_camera_variety(self) -> None:
        rows = [
            {"scene_number": str(i), "script_segment": f"Line {i}", "asset_type": "image", "prompt": "same prompt"}
            for i in range(1, 6)
        ]
        aligned = []
        t = 0.0
        for row in rows:
            aligned.append(
                {
                    "scene_number": row["scene_number"],
                    "script_segment": row["script_segment"],
                    "start_time": t,
                    "end_time": t + 1.0,
                }
            )
            t += 1.0
        plan = build_editorial_plan(rows, aligned, t)
        styles = [s.camera_style for s in plan.scenes]
        repeats = sum(1 for a, b in zip(styles, styles[1:]) if a == b)
        self.assertLess(repeats, len(styles) - 1)

    def test_hook_window_boosts_attention(self) -> None:
        rows = [{"scene_number": "1", "script_segment": "Why does this matter?", "asset_type": "image", "prompt": "x"}]
        aligned = [{"scene_number": "1", "script_segment": rows[0]["script_segment"], "start_time": 0.0, "end_time": 4.0}]
        plan = build_editorial_plan(rows, aligned, 4.0)
        self.assertGreaterEqual(plan.scenes[0].attention_score, 0.75)
        self.assertEqual(plan.scenes[0].purpose, "hook")


class TestEditorialPersistence(unittest.TestCase):
    def test_cache_invalidates_on_settings_change(self) -> None:
        rows = _sample_rows()
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            key_a = cache_settings_key(rows)
            plan = build_editorial_plan(rows, _sample_aligned(), 7.0, settings_key=key_a, audio_key="audio1")
            save_editorial_plan(state, plan)
            loaded = load_cached_plan(state, audio_key="audio1", settings_key=key_a)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded.scenes), 3)

            self.assertIsNone(load_cached_plan(state, audio_key="audio2", settings_key=key_a))
            key_b = cache_settings_key(rows, visual_plan_dict={"scenes": []})
            self.assertIsNone(load_cached_plan(state, audio_key="audio1", settings_key=key_b))

            raw = json.loads(plan_file(state).read_text(encoding="utf-8"))
            self.assertEqual(raw["version"], 2)


class TestSmartEditingHints(unittest.TestCase):
    def test_editorial_transitions_merged(self) -> None:
        rows = _sample_rows()
        aligned = _sample_aligned()
        editorial = build_editorial_plan(rows, aligned, 7.0, visual_plan=_visual_plan())
        settings = SmartEditingSettings(
            text_effects=False,
            sound_effects=False,
            visual_transitions=True,
            scene_ambience=False,
            intensity="medium",
        )
        picks = plan_scene_transitions(rows, aligned, settings, editorial_plan=editorial)
        styles = {p["scene_number"]: p["style"] for p in picks}
        self.assertEqual(styles.get("1"), "dissolve")
        self.assertEqual(styles.get("2"), "fade")


class TestCameraMotion(unittest.TestCase):
    def test_camera_styles_map_to_distinct_motion(self) -> None:
        self.assertEqual(_camera_motion("push_in", index=0, zoom=True), (True, True, "push_in"))
        self.assertEqual(_camera_motion("pull_out", index=0, zoom=True), (True, False, "pull_out"))
        self.assertEqual(_camera_motion("static", index=0, zoom=True), (False, False, "static"))
        self.assertEqual(_camera_motion("hold", index=0, zoom=True), (False, False, "hold"))
        use_zoom, zoom_in, style = _camera_motion("subtle_drift", index=0, zoom=True)
        self.assertTrue(use_zoom)
        self.assertEqual(style, "subtle_drift")

    def test_fallback_alternates_without_plan(self) -> None:
        self.assertEqual(_camera_motion(None, index=0, zoom=True)[1], True)
        self.assertEqual(_camera_motion(None, index=1, zoom=True)[1], False)


if __name__ == "__main__":
    unittest.main()
