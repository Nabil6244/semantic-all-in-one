"""Focused regression: restrained typography, simple motion, no freeze."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from editorial.schema import EditorialScene
from editorial.shot_planner import plan_edit_decision
from editorial.shot_planner import plan_edit_decision
from editorial.timeline import EditorialTimeline, TimelineEvent, validate_visual_timeline
from graphics.composition import compose_presentation, compute_size_vh, select_animation
from graphics.memory import GraphicsMemory
from typography.render import typography_params_for_effect
from typography.variation import plan_typography_decision, reset_variation_history


def _scene(sn: str, *, start: float, end: float, text: str, actual: float | None = None, **kw) -> EditorialScene:
    return EditorialScene(
        scene_number=sn,
        start=start,
        end=end,
        duration=end - start,
        narration_excerpt=text,
        purpose=kw.get("purpose", "context"),
        asset_type_intent=kw.get("asset_type", "stock_video"),
        actual_asset_duration=actual,
        pacing_bias=kw.get("pacing", "normal"),
    )


class TestTypographyRestraint(unittest.TestCase):
    def test_normal_text_restrained(self) -> None:
        size = compute_size_vh(role="LABEL", text="Grid upgrade", importance="medium")
        self.assertLessEqual(size, 0.040)
        self.assertGreaterEqual(size, 0.026)

    def test_important_text_capped(self) -> None:
        size = compute_size_vh(role="EMPHASIS", text="NOW", importance="critical", emphasis="dramatic")
        self.assertLessEqual(size, 0.050)

    def test_long_text_scales_down(self) -> None:
        short = compute_size_vh(role="CALLOUT", text="Demand")
        long = compute_size_vh(
            role="CALLOUT",
            text="The grid needs thousands of new transformers this decade to keep the lights on",
        )
        self.assertLess(long, short)

    def test_multiline_controlled(self) -> None:
        size = compute_size_vh(
            role="QUOTE",
            text="We have to rebuild the entire transmission network before demand peaks",
            n_lines=3,
        )
        self.assertLessEqual(size, 0.050)

    def test_statistic_prominent_not_huge(self) -> None:
        size = compute_size_vh(role="STATISTIC", text="+25%", importance="high")
        self.assertGreaterEqual(size, 0.052)
        self.assertLessEqual(size, 0.082)

    def test_chapter_respects_maximum(self) -> None:
        size = compute_size_vh(role="CHAPTER", text="Part One", importance="critical")
        self.assertLessEqual(size, 0.068)

    def test_safe_area_occupancy(self) -> None:
        from graphics.composition import occupied_block_ratios

        size = compute_size_vh(role="STATISTIC", text="25%")
        w, h = occupied_block_ratios("25%", size)
        self.assertLessEqual(h, 0.20)
        self.assertLessEqual(w, 0.55)

    def test_deterministic_params(self) -> None:
        reset_variation_history()
        a = typography_params_for_effect(
            {"effect": "fade", "text": "A quiet line of narration here.", "local_start": 0, "local_end": 1.2},
            1920, 1080, record_history=False,
        )
        b = typography_params_for_effect(
            {"effect": "fade", "text": "A quiet line of narration here.", "local_start": 0, "local_end": 1.2},
            1920, 1080, record_history=False,
        )
        self.assertEqual(a["fontsize"], b["fontsize"])
        self.assertEqual(a["animation"], b["animation"])

    def test_720p_and_4k_scale_with_height(self) -> None:
        reset_variation_history()
        p720 = typography_params_for_effect(
            {"effect": "fade", "text": "Quiet caption line", "local_start": 0, "local_end": 1},
            1280, 720, record_history=False,
        )
        p4k = typography_params_for_effect(
            {"effect": "fade", "text": "Quiet caption line", "local_start": 0, "local_end": 1},
            3840, 2160, record_history=False,
        )
        self.assertLess(p720["fontsize"] / 720, 0.05)
        self.assertLess(p4k["fontsize"] / 2160, 0.05)


class TestAnimationRestraint(unittest.TestCase):
    def test_normal_uses_fade(self) -> None:
        self.assertEqual(select_animation(role="CAPTION"), "FADE")

    def test_lower_third_slide(self) -> None:
        self.assertEqual(select_animation(role="LOWER_THIRD"), "SLIDE")

    def test_statistic_reveal(self) -> None:
        self.assertEqual(select_animation(role="STATISTIC"), "MASK_REVEAL")

    def test_chapter_reveal(self) -> None:
        self.assertEqual(select_animation(role="CHAPTER"), "MASK_REVEAL")

    def test_unnecessary_animation_suppressed(self) -> None:
        self.assertEqual(select_animation(role="EMPHASIS", emphasis="normal"), "FADE")

    def test_smart_text_normal_is_fade(self) -> None:
        reset_variation_history()
        d = plan_typography_decision(
            "Technology is changing the way we live every day.",
            "highlight",
            duration=1.4,
        )
        self.assertEqual(d.animation, "fade")

    def test_smart_text_statistic_is_reveal(self) -> None:
        reset_variation_history()
        d = plan_typography_decision("42%", "impact", duration=1.2)
        self.assertIn(d.animation, ("reveal", "fade"))
        self.assertNotEqual(d.animation, "scale_fade")


class TestGraphicsDensity(unittest.TestCase):
    def test_consecutive_scenes_get_breathing_room(self) -> None:
        mem = GraphicsMemory()
        mem.record(graphic_id="a", role="LABEL", text="one", start=0.0, importance="low", scene_number="1")
        mem.record(graphic_id="b", role="LABEL", text="two", start=3.0, importance="low", scene_number="2")
        reason = mem.should_suppress(
            role="LABEL", text="three", start=6.0, importance="low", consecutive_scenes=2,
        )
        self.assertEqual(reason, "consecutive_scenes")

    def test_high_importance_still_shows(self) -> None:
        mem = GraphicsMemory()
        mem.record(graphic_id="a", role="LABEL", text="one", start=0.0, importance="low", scene_number="1")
        mem.record(graphic_id="b", role="LABEL", text="two", start=3.0, importance="low", scene_number="2")
        reason = mem.should_suppress(
            role="STATISTIC", text="+25%", start=6.0, importance="high", consecutive_scenes=2,
        )
        self.assertIsNone(reason)


class TestCoverageNoUnintendedFreeze(unittest.TestCase):
    def test_short_video_uses_multi_shot(self) -> None:
        d = plan_edit_decision(_scene("1", start=0, end=8, text="Long beat.", actual=3.2, purpose="process"))
        self.assertIn(d.strategy, ("MULTI_SHOT", "PUNCH_IN", "MONTAGE", "REFRAME", "DUAL_ASSET"))
        self.assertGreaterEqual(len(d.shots), 2)
        self.assertFalse(all(s.hold_tail for s in d.shots))

    def test_long_video_single_shot(self) -> None:
        d = plan_edit_decision(_scene("2", start=0, end=4, text="Short beat.", actual=12.0))
        self.assertEqual(d.strategy, "SINGLE_SHOT")
        self.assertFalse(d.shots[0].hold_tail)

    def test_punch_in_shots_fit_source(self) -> None:
        d = plan_edit_decision(_scene("3", start=0, end=9, text="Process explanation.", actual=3.0, purpose="process"))
        self.assertGreaterEqual(len(d.shots), 2)
        for s in d.shots:
            if s.hold_tail:
                continue
            if s.source_end is None:
                continue
            span = float(s.source_end) - float(s.source_start or 0)
            self.assertLessEqual(s.output_duration, span + 0.2)

    def test_image_motion_has_no_hold_tail(self) -> None:
        d = plan_edit_decision(
            _scene("4", start=0, end=6, text="A still photograph.", asset_type="stock_image")
        )
        self.assertTrue(all(not s.hold_tail for s in d.shots))

    def test_timeline_continuous_and_monotonic(self) -> None:
        tl = EditorialTimeline(audio_end=8.0)
        tl.add(TimelineEvent("a", "VIDEO_1", 0.0, 3.2, scene_number="1", source="a.mp4"))
        tl.add(TimelineEvent("b", "VIDEO_2", 3.2, 8.0, scene_number="1", source="a.mp4"))
        issues = validate_visual_timeline(tl, audio_end=8.0)
        self.assertEqual(issues, [])

    def test_zero_duration_flagged(self) -> None:
        tl = EditorialTimeline(audio_end=2.0)
        tl.add(TimelineEvent("z", "VIDEO_1", 1.0, 1.0, scene_number="1"))
        issues = validate_visual_timeline(tl)
        self.assertTrue(any("zero-duration" in i["message"] for i in issues))

    def test_gap_flagged(self) -> None:
        tl = EditorialTimeline(audio_end=6.0)
        tl.add(TimelineEvent("a", "VIDEO_1", 0.0, 2.0, scene_number="1"))
        tl.add(TimelineEvent("b", "VIDEO_1", 3.5, 6.0, scene_number="2"))
        issues = validate_visual_timeline(tl)
        self.assertTrue(any("gap" in i["message"] for i in issues))

    def test_graphics_do_not_replace_visual_track(self) -> None:
        d = compose_presentation(
            role="STATISTIC",
            text="+25%",
            scene_start=0,
            scene_end=5,
            scene_duration=5,
        )
        self.assertGreater(d.end, d.start)
        # Graphic is overlay timing, not a video replacement.
        self.assertLess(d.end - d.start, 5.0)


class TestFFmpegNoUnintendedFreeze(unittest.TestCase):
    def test_short_clip_loop_not_tpad_without_hold(self) -> None:
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not available")
        from video_generator import _render_editorial_shot, is_video_file

        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "short.mp4"
            out = Path(td) / "out.mp4"
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src),
            ]
            import subprocess

            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0 or not src.is_file():
                self.skipTest("could not mint test clip")
            self.assertTrue(is_video_file(src))
            shot = {
                "output_duration": 2.4,
                "source_start": 0.0,
                "source_end": 1.0,
                "scale": 1.0,
                "hold_tail": False,
                "speed": 1.0,
            }
            _render_editorial_shot(src, out, shot, 320, 180, 30)
            self.assertTrue(out.is_file())
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=nk=1:nw=1", str(out),
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(probe.returncode, 0)
            dur = float(probe.stdout.strip() or 0)
            self.assertGreater(dur, 2.2)
            freeze = subprocess.run(
                [
                    "ffmpeg", "-i", str(out),
                    "-vf", "freezedetect=n=0.001:d=0.8",
                    "-f", "null", "-",
                ],
                capture_output=True, text=True,
            )
            self.assertNotIn("freeze_start:", freeze.stderr or "")


if __name__ == "__main__":
    unittest.main()
