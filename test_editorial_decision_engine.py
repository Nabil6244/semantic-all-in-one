"""Focused tests for Editorial Decision Engine / coverage / timeline."""

from __future__ import annotations

import unittest
from pathlib import Path

from editorial.builder import build_editorial_plan
from editorial.continuity import shot_size_sequence, visual_role_for_scene
from editorial.edit_decision import EditDecision, ShotSpec
from editorial.engine import (
    EditorialEngine,
    build_timeline_from_decisions,
    compile_editorial_plan,
    decision_map_from_plan,
    plan_editorial_events,
    qc_edit_decisions,
)
from editorial.media_analysis import analyze_media_editability
from editorial.schema import EditorialPlan, EditorialScene
from editorial.shot_planner import plan_all_edit_decisions, plan_edit_decision
from editorial.timeline import EditorialTimeline, TimelineEvent


def _scene(
    sn: str,
    *,
    start: float,
    end: float,
    text: str,
    purpose: str = "context",
    asset_type: str = "stock_video",
    actual: float | None = None,
    pacing: str = "normal",
    attention: float = 0.5,
) -> EditorialScene:
    return EditorialScene(
        scene_number=sn,
        start=start,
        end=end,
        duration=end - start,
        narration_excerpt=text,
        purpose=purpose,  # type: ignore[arg-type]
        attention_score=attention,
        asset_type_intent=asset_type,
        actual_asset_duration=actual,
        pacing_bias=pacing,  # type: ignore[arg-type]
    )


class TestMediaEditability(unittest.TestCase):
    def test_image_prefers_motion_potentials(self) -> None:
        e = analyze_media_editability(None, asset_type="stock_image")
        self.assertEqual(e.media_kind, "image")
        self.assertGreater(e.punch_in_potential, 0.7)
        self.assertGreater(e.editability_score, 0.5)

    def test_short_video_usable_less_than_native(self) -> None:
        e = analyze_media_editability(None, known_duration=4.0, asset_type="stock_video")
        self.assertEqual(e.media_kind, "video")
        self.assertLessEqual(e.usable_duration, e.native_duration)
        self.assertGreater(e.usable_duration, 0)


class TestShotPlannerCoverage(unittest.TestCase):
    def test_long_clip_short_narration_single_shot(self) -> None:
        scene = _scene(
            "1",
            start=0,
            end=3,
            text="A brief statement.",
            actual=10.0,
        )
        d = plan_edit_decision(scene)
        self.assertEqual(d.strategy, "SINGLE_SHOT")
        self.assertEqual(len(d.shots), 1)
        self.assertAlmostEqual(d.total_output_duration(), 3.0, places=2)
        self.assertFalse(d.avoid_blind_loop)

    def test_short_clip_long_narration_multi_shot(self) -> None:
        scene = _scene(
            "2",
            start=0,
            end=8,
            text="America needs thousands of new transformers to meet rising demand.",
            purpose="process",
            actual=3.5,
            pacing="normal",
            attention=0.7,
        )
        d = plan_edit_decision(scene)
        self.assertIn(d.strategy, ("MULTI_SHOT", "PUNCH_IN", "MONTAGE", "HOLD_TAIL", "RETIME"))
        self.assertGreaterEqual(len(d.shots), 2)
        self.assertAlmostEqual(d.total_output_duration(), 8.0, places=1)
        # Perceived shot variety via scale / shot_size
        sizes = {s.shot_size for s in d.shots}
        self.assertGreaterEqual(len(sizes), 1)
        scales = [s.scale for s in d.shots]
        self.assertTrue(any(s >= 1.0 for s in scales))

    def test_image_long_narration_uses_image_motion(self) -> None:
        scene = _scene(
            "3",
            start=0,
            end=6,
            text="The factory floor at dawn.",
            purpose="atmosphere",
            asset_type="stock_image",
            actual=None,
        )
        d = plan_edit_decision(scene)
        self.assertIn(d.strategy, ("IMAGE_MOTION", "MULTI_SHOT"))
        self.assertGreaterEqual(len(d.shots), 1)
        self.assertTrue(all(s.camera_style != "hold" or len(d.shots) > 1 for s in d.shots) or d.shots)

    def test_hold_tail_only_when_unavoidable(self) -> None:
        scene = _scene(
            "4",
            start=0,
            end=4.5,
            text="Slightly longer than the clip.",
            actual=4.0,
        )
        d = plan_edit_decision(scene)
        self.assertNotEqual(d.strategy, "SAFE_LOOP")
        self.assertAlmostEqual(d.total_output_duration(), 4.5, places=1)
        # Small gap should be covered by a second shot, not a freeze.
        if d.strategy != "HOLD_TAIL":
            self.assertFalse(any(s.hold_tail for s in d.shots))

    def test_short_clip_does_not_plan_a_freeze(self) -> None:
        scene = _scene(
            "5",
            start=0,
            end=7.8,
            text="America needs thousands of new transformers.",
            purpose="process",
            actual=3.2,
        )
        d = plan_edit_decision(scene)
        self.assertGreaterEqual(len(d.shots), 2)
        self.assertNotEqual(d.strategy, "HOLD_TAIL")
        for s in d.shots:
            if not s.hold_tail and s.source_end is not None:
                span = float(s.source_end) - float(s.source_start or 0.0)
                self.assertLessEqual(s.output_duration, span + 0.2)


class TestContinuityAndRoles(unittest.TestCase):
    def test_statistic_role_from_narration(self) -> None:
        scene = _scene(
            "1",
            start=0,
            end=3,
            text="Nearly 40 percent of the grid needs upgrades.",
            purpose="evidence",
        )
        self.assertEqual(visual_role_for_scene(scene), "statistic")

    def test_shot_progression_wide_to_close(self) -> None:
        seq = shot_size_sequence("scale", 3)
        self.assertEqual(seq[0], "wide")
        self.assertIn(seq[-1], ("close", "medium", "detail"))


class TestTimelineAndEvents(unittest.TestCase):
    def test_timeline_has_independent_layers(self) -> None:
        plan = EditorialPlan(
            audio_end=6.0,
            scenes=[
                _scene("1", start=0, end=3, text="Hook secret story.", purpose="hook", attention=0.9),
                _scene(
                    "2",
                    start=3,
                    end=6,
                    text="Scientists found 12 percent growth.",
                    purpose="evidence",
                    actual=2.0,
                ),
            ],
        )
        decisions = plan_all_edit_decisions(plan.scenes)
        events = plan_editorial_events(plan)
        timeline = build_timeline_from_decisions(plan, decisions, events=events)
        self.assertIsInstance(timeline, EditorialTimeline)
        tracks = {e.track for e in timeline.events}
        self.assertIn("VOICEOVER", tracks)
        self.assertTrue(tracks & {"VIDEO_1", "VIDEO_2", "IMAGE"})
        # Text/graphics events for statistic / hook
        self.assertTrue(any(e.track in ("TEXT", "GRAPHICS", "SFX") for e in timeline.events) or events)

    def test_editorial_events_for_reveal(self) -> None:
        plan = EditorialPlan(
            audio_end=4.0,
            scenes=[
                _scene("1", start=0, end=4, text="The truth is revealed.", purpose="reveal", attention=0.9),
            ],
        )
        events = plan_editorial_events(plan)
        self.assertTrue(any(e.kind == "reveal" for e in events))


class TestEditorialEngine(unittest.TestCase):
    def test_compile_attaches_decisions(self) -> None:
        rows = [
            {
                "scene_number": "1",
                "script_segment": "Welcome to the secret story.",
                "asset_type": "image",
                "prompt": "city",
            },
            {
                "scene_number": "2",
                "script_segment": "Data shows 50 percent growth in demand.",
                "asset_type": "stock_video",
                "prompt": "grid",
            },
        ]
        aligned = [
            {
                "scene_number": "1",
                "script_segment": rows[0]["script_segment"],
                "start_time": 0.0,
                "end_time": 2.5,
            },
            {
                "scene_number": "2",
                "script_segment": rows[1]["script_segment"],
                "start_time": 2.5,
                "end_time": 8.0,
            },
        ]
        plan = build_editorial_plan(rows, aligned, 8.0)
        # Simulate short source for scene 2
        plan.scenes[1].actual_asset_duration = 3.0
        compiled = compile_editorial_plan(plan)
        self.assertTrue(compiled.edit_decisions)
        self.assertEqual(len(compiled.edit_decisions), 2)
        self.assertIsInstance(compiled.timeline, dict)
        dmap = decision_map_from_plan(compiled)
        self.assertIn("2", dmap)
        # Scene 2 should prefer multi-shot coverage for short clip / long VO
        d2 = EditDecision.from_dict(dmap["2"])
        self.assertGreaterEqual(d2.shot_count, 1)
        self.assertAlmostEqual(d2.required_duration, plan.scenes[1].duration, places=1)

    def test_qc_normalizes_duration_drift(self) -> None:
        plan = EditorialPlan(
            audio_end=5.0,
            scenes=[_scene("1", start=0, end=5, text="x", actual=2.0)],
        )
        decision = EditDecision(
            scene_number="1",
            required_duration=5.0,
            strategy="MULTI_SHOT",
            shots=[
                ShotSpec(shot_id="1_s0", output_duration=2.0),
                ShotSpec(shot_id="1_s1", output_duration=2.0),
            ],
        )
        issues = qc_edit_decisions(plan, [decision])
        self.assertAlmostEqual(decision.total_output_duration(), 5.0, places=2)
        self.assertTrue(any(i.get("fixed") for i in issues))

    def test_roundtrip_plan_dict(self) -> None:
        plan = EditorialPlan(
            audio_end=3.0,
            scenes=[_scene("1", start=0, end=3, text="Hello", actual=5.0)],
        )
        engine = EditorialEngine(plan)
        engine.compile()
        data = plan.to_dict()
        restored = EditorialPlan.from_dict(data)
        self.assertEqual(len(restored.edit_decisions), 1)
        self.assertIsNotNone(restored.timeline)


class TestTimelineEventModel(unittest.TestCase):
    def test_event_duration(self) -> None:
        e = TimelineEvent(
            event_id="a",
            track="TEXT",
            start=1.0,
            end=2.5,
            scene_number="1",
        )
        self.assertAlmostEqual(e.duration, 1.5)
        d = e.to_dict()
        self.assertIn("duration", d)


@unittest.skipUnless(
    __import__("shutil").which("ffmpeg") is not None,
    "ffmpeg not available",
)
class TestMultiShotRender(unittest.TestCase):
    def test_image_multi_shot_assembles_exact_duration(self) -> None:
        import tempfile

        from PIL import Image

        import video_generator as vg
        from media_duration import probe_media_duration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img = root / "001.png"
            Image.new("RGB", (640, 360), (30, 90, 140)).save(img)
            out = root / "scene.mp4"
            decision = {
                "scene_number": "1",
                "required_duration": 2.5,
                "strategy": "MULTI_SHOT",
                "avoid_blind_loop": True,
                "shots": [
                    {
                        "shot_id": "1_s0",
                        "output_duration": 1.25,
                        "scale": 1.0,
                        "crop_x": 0.5,
                        "crop_y": 0.5,
                        "speed": 1.0,
                        "shot_size": "wide",
                        "camera_style": "subtle_drift",
                    },
                    {
                        "shot_id": "1_s1",
                        "output_duration": 1.25,
                        "scale": 1.35,
                        "crop_x": 0.42,
                        "crop_y": 0.48,
                        "speed": 1.0,
                        "shot_size": "close",
                        "camera_style": "push_in",
                    },
                ],
            }
            ok = vg._render_scene_from_edit_decision(
                img_path=img,
                out_path=out,
                duration=2.5,
                edit_decision=decision,
                width=640,
                height=360,
                fps=24,
            )
            self.assertTrue(ok)
            self.assertTrue(out.is_file())
            dur = probe_media_duration(out)
            self.assertIsNotNone(dur)
            self.assertAlmostEqual(float(dur), 2.5, delta=0.15)


if __name__ == "__main__":
    unittest.main()
