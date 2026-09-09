"""Regression tests for unintended freeze frames and timeline coverage."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from editorial.edit_decision import EditDecision, ShotSpec
from editorial.engine import build_timeline_from_decisions, qc_edit_decisions
from editorial.schema import EditorialPlan, EditorialScene
from editorial.shot_planner import plan_edit_decision
from editorial.timeline import EditorialTimeline, TimelineEvent, validate_visual_timeline
from graphics.composition import compose_presentation, compute_size_vh
from graphics.render import render_graphic_overlay
from graphics.schema import GraphicSpec, TextOverlaySpec


FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _scene(
    sn: str,
    *,
    start: float,
    end: float,
    text: str = "Narration beat.",
    purpose: str = "context",
    asset_type: str = "stock_video",
    actual: float | None = None,
) -> EditorialScene:
    return EditorialScene(
        scene_number=sn,
        start=start,
        end=end,
        duration=end - start,
        narration_excerpt=text,
        purpose=purpose,  # type: ignore[arg-type]
        attention_score=0.6,
        asset_type_intent=asset_type,
        actual_asset_duration=actual,
    )


def _make_clip(path: Path, seconds: float, fps: int = 24, size: str = "320x180") -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"testsrc=size={size}:rate={fps}:duration={seconds}",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _make_png(path: Path, color=(20, 80, 140)) -> Path:
    Image.new("RGB", (320, 180), color).save(path)
    return path


class TestPlannerDoesNotOverrunSource(unittest.TestCase):
    def test_short_video_long_narration_replays_instead_of_one_freeze(self) -> None:
        scene = _scene("1", start=0, end=8, text="Long process explanation.", actual=3.2, purpose="process")
        d = plan_edit_decision(scene)
        self.assertAlmostEqual(d.total_output_duration(), 8.0, places=1)
        self.assertGreaterEqual(len(d.shots), 2)
        playable = 3.2
        for shot in d.shots:
            if shot.hold_tail:
                self.assertLessEqual(shot.output_duration - playable, 1.25)
                continue
            self.assertLessEqual(shot.output_duration, playable + 0.12)

    def test_video_longer_than_requested_stays_single(self) -> None:
        scene = _scene("1", start=0, end=3, text="Short beat.", actual=10.0)
        d = plan_edit_decision(scene)
        self.assertEqual(d.strategy, "SINGLE_SHOT")
        self.assertEqual(len(d.shots), 1)
        self.assertFalse(d.shots[0].hold_tail)

    def test_small_hold_tail_gap(self) -> None:
        scene = _scene("1", start=0, end=4.5, text="Slightly longer.", actual=4.0)
        d = plan_edit_decision(scene)
        self.assertNotEqual(d.strategy, "SAFE_LOOP")
        self.assertAlmostEqual(d.total_output_duration(), 4.5, places=1)
        if any(s.hold_tail for s in d.shots):
            hold = [s for s in d.shots if s.hold_tail][-1]
            self.assertLessEqual(hold.output_duration, 4.0 + 1.25)

    def test_image_then_does_not_freeze_plan(self) -> None:
        scene = _scene(
            "1", start=0, end=5, text="Still photograph.", asset_type="stock_image", actual=None
        )
        d = plan_edit_decision(scene)
        self.assertIn(d.strategy, ("IMAGE_MOTION", "MULTI_SHOT"))
        self.assertFalse(any(s.hold_tail for s in d.shots))

    def test_no_zero_duration_shots(self) -> None:
        scene = _scene("1", start=0, end=6, text="Coverage.", actual=2.5, purpose="process")
        d = plan_edit_decision(scene)
        self.assertTrue(all(s.output_duration > 0.05 for s in d.shots))


class TestTimelineContinuity(unittest.TestCase):
    def test_monotonic_continuous_visuals(self) -> None:
        plan = EditorialPlan(
            audio_end=6.0,
            scenes=[
                _scene("1", start=0, end=3, text="A", actual=5.0),
                _scene("2", start=3, end=6, text="B", actual=5.0),
            ],
        )
        from editorial.shot_planner import plan_all_edit_decisions

        decisions = plan_all_edit_decisions(plan.scenes)
        timeline = build_timeline_from_decisions(plan, decisions)
        issues = validate_visual_timeline(timeline, audio_end=6.0)
        visual = [e for e in timeline.events if e.track in ("VIDEO_1", "VIDEO_2", "IMAGE")]
        visual.sort(key=lambda e: e.start)
        for ev in visual:
            self.assertGreater(ev.duration, 0.0)
        for a, b in zip(visual, visual[1:]):
            self.assertGreaterEqual(b.start + 1e-6, a.start)
            self.assertLess(b.start, a.end + 0.15)
        self.assertFalse(any(i.get("category") == "timeline" and "zero-duration" in i.get("message", "") for i in issues))

    def test_detects_zero_duration_and_gap(self) -> None:
        tl = EditorialTimeline(
            audio_end=5.0,
            events=[
                TimelineEvent("a", "VIDEO_1", 0.0, 2.0, scene_number="1", source="a.mp4"),
                TimelineEvent("b", "VIDEO_1", 2.0, 2.0, scene_number="1", source="b.mp4"),
                TimelineEvent("c", "VIDEO_1", 3.5, 5.0, scene_number="2", source="c.mp4"),
            ],
        )
        issues = validate_visual_timeline(tl, audio_end=5.0)
        cats = " ".join(i["message"] for i in issues)
        self.assertIn("zero-duration", cats)
        self.assertIn("gap", cats)

    def test_qc_flags_freeze_risk_mismatch(self) -> None:
        plan = EditorialPlan(
            audio_end=5.0,
            scenes=[_scene("1", start=0, end=5, text="x", actual=2.0)],
        )
        decision = EditDecision(
            scene_number="1",
            required_duration=5.0,
            strategy="MULTI_SHOT",
            shots=[
                ShotSpec(
                    shot_id="1_s0",
                    output_duration=5.0,
                    source_start=0.0,
                    source_end=2.0,
                    hold_tail=False,
                ),
            ],
        )
        issues = qc_edit_decisions(plan, [decision])
        self.assertTrue(any(i.get("category") == "freeze_risk" for i in issues))


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestRenderPlayback(unittest.TestCase):
    def test_short_clip_without_hold_tail_does_not_tpad(self) -> None:
        import video_generator as vg

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            out = root / "shot.mp4"
            _make_clip(src, 1.2, fps=24)
            shot = {
                "shot_id": "1_s0",
                "output_duration": 1.2,
                "source_start": 0.0,
                "source_end": 1.2,
                "scale": 1.0,
                "speed": 1.0,
                "hold_tail": False,
                "camera_style": "static",
            }
            vg._render_editorial_shot(src, out, shot, 320, 180, 24)
            self.assertTrue(out.is_file())
            from media_duration import probe_media_duration

            dur = probe_media_duration(out)
            self.assertAlmostEqual(float(dur or 0), 1.2, delta=0.2)

    def test_hold_tail_extends_with_clone(self) -> None:
        import video_generator as vg
        from media_duration import probe_media_duration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src.mp4"
            out = root / "shot.mp4"
            _make_clip(src, 1.0, fps=24)
            shot = {
                "shot_id": "1_s0",
                "output_duration": 2.0,
                "source_start": 0.0,
                "source_end": 1.0,
                "scale": 1.0,
                "speed": 1.0,
                "hold_tail": True,
                "camera_style": "static",
            }
            vg._render_editorial_shot(src, out, shot, 320, 180, 24)
            dur = probe_media_duration(out)
            self.assertAlmostEqual(float(dur or 0), 2.0, delta=0.2)

    def test_video_then_image_and_image_then_video(self) -> None:
        import video_generator as vg
        from media_duration import probe_media_duration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vid = root / "a.mp4"
            img = root / "b.png"
            _make_clip(vid, 1.0, fps=24)
            _make_png(img)
            for decision, duration in (
                (
                    {
                        "strategy": "DUAL_ASSET",
                        "shots": [
                            {
                                "shot_id": "1_s0",
                                "output_duration": 1.0,
                                "source_path": str(vid),
                                "scale": 1.0,
                                "speed": 1.0,
                                "hold_tail": False,
                            },
                            {
                                "shot_id": "1_s1",
                                "output_duration": 1.0,
                                "source_path": str(img),
                                "scale": 1.2,
                                "speed": 1.0,
                                "camera_style": "push_in",
                                "hold_tail": False,
                            },
                        ],
                    },
                    2.0,
                ),
                (
                    {
                        "strategy": "DUAL_ASSET",
                        "shots": [
                            {
                                "shot_id": "1_s0",
                                "output_duration": 1.0,
                                "source_path": str(img),
                                "scale": 1.0,
                                "speed": 1.0,
                                "camera_style": "subtle_drift",
                                "hold_tail": False,
                            },
                            {
                                "shot_id": "1_s1",
                                "output_duration": 1.0,
                                "source_path": str(vid),
                                "scale": 1.0,
                                "speed": 1.0,
                                "hold_tail": False,
                            },
                        ],
                    },
                    2.0,
                ),
            ):
                out = root / f"scene_{decision['shots'][0]['shot_id']}.mp4"
                ok = vg._render_scene_from_edit_decision(
                    img_path=vid,
                    out_path=out,
                    duration=duration,
                    edit_decision=decision,
                    width=320,
                    height=180,
                    fps=24,
                )
                self.assertTrue(ok)
                self.assertAlmostEqual(float(probe_media_duration(out) or 0), duration, delta=0.25)

    def test_video_then_video_mixed_fps(self) -> None:
        import video_generator as vg
        from media_duration import probe_media_duration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.mp4"
            b = root / "b.mp4"
            _make_clip(a, 1.0, fps=24)
            _make_clip(b, 1.0, fps=30)
            out = root / "mix.mp4"
            decision = {
                "strategy": "DUAL_ASSET",
                "shots": [
                    {
                        "shot_id": "1_s0",
                        "output_duration": 1.0,
                        "source_path": str(a),
                        "scale": 1.0,
                        "speed": 1.0,
                        "hold_tail": False,
                    },
                    {
                        "shot_id": "1_s1",
                        "output_duration": 1.0,
                        "source_path": str(b),
                        "scale": 1.15,
                        "speed": 1.0,
                        "hold_tail": False,
                    },
                ],
            }
            ok = vg._render_scene_from_edit_decision(
                img_path=a,
                out_path=out,
                duration=2.0,
                edit_decision=decision,
                width=320,
                height=180,
                fps=24,
            )
            self.assertTrue(ok)
            self.assertAlmostEqual(float(probe_media_duration(out) or 0), 2.0, delta=0.25)

    def test_graphics_over_video_does_not_shorten_clip(self) -> None:
        import video_generator as vg
        from media_duration import probe_media_duration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "v.mp4"
            overlay = root / "ov.png"
            out = root / "scene.mp4"
            _make_clip(src, 1.5, fps=24)
            Image.new("RGBA", (320, 180), (0, 0, 0, 0)).save(overlay)
            vg._render_scene_clip(
                img_path=src,
                out_path=out,
                duration=1.5,
                width=320,
                height=180,
                fps=24,
                zoom=False,
                zoom_in=True,
                zoom_amount=0.05,
                timed_overlays=[(overlay, 0.2, 1.0, "fade", None)],
            )
            self.assertAlmostEqual(float(probe_media_duration(out) or 0), 1.5, delta=0.2)

    def test_short_source_multi_shot_covers_without_hold_on_every_shot(self) -> None:
        import video_generator as vg
        from media_duration import probe_media_duration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "short.mp4"
            out = root / "scene.mp4"
            _make_clip(src, 1.4, fps=24)
            decision = {
                "strategy": "PUNCH_IN",
                "shots": [
                    {
                        "shot_id": "1_s0",
                        "output_duration": 1.4,
                        "source_path": str(src),
                        "source_start": 0.0,
                        "source_end": 1.4,
                        "scale": 1.0,
                        "speed": 1.0,
                        "hold_tail": False,
                    },
                    {
                        "shot_id": "1_s1",
                        "output_duration": 1.4,
                        "source_path": str(src),
                        "source_start": 0.0,
                        "source_end": 1.4,
                        "scale": 1.25,
                        "speed": 1.0,
                        "hold_tail": False,
                    },
                ],
            }
            ok = vg._render_scene_from_edit_decision(
                img_path=src,
                out_path=out,
                duration=2.8,
                edit_decision=decision,
                width=320,
                height=180,
                fps=24,
            )
            self.assertTrue(ok)
            self.assertAlmostEqual(float(probe_media_duration(out) or 0), 2.8, delta=0.25)


class TestTextSizingRender(unittest.TestCase):
    def test_normal_overlay_does_not_fill_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = compose_presentation(
                role="LABEL",
                text="Demand is rising",
                scene_start=0,
                scene_end=4,
                scene_duration=4,
                importance="medium",
            )
            spec = GraphicSpec(
                graphic_id="g1",
                role="LABEL",
                start=d.start,
                end=d.end,
                text=TextOverlaySpec(
                    role="LABEL",
                    text="Demand is rising",
                    position_x=d.position_x,
                    position_y=d.position_y,
                    scale=1.0,
                    metadata={"size_vh": d.size_vh},
                ),
            )
            png = Path(tmp) / "t.png"
            out = render_graphic_overlay(spec, png, 1280, 720)
            self.assertIsNotNone(out)
            img = Image.open(out).convert("RGBA")
            alpha = img.split()[-1]
            bbox = alpha.getbbox()
            self.assertIsNotNone(bbox)
            x0, y0, x1, y1 = bbox
            self.assertLess((y1 - y0) / 720, 0.22)
            self.assertLess((x1 - x0) / 1280, 0.70)
            self.assertGreaterEqual(y0, int(720 * 0.08))
            self.assertLessEqual(y1, 720 - int(720 * 0.08))

    def test_720_vs_1080_same_visual_fraction(self) -> None:
        size = compute_size_vh(role="STATISTIC", text="40%", importance="high")
        self.assertLessEqual(size, 0.078)
        self.assertAlmostEqual((720 * size) / 720, (1920 * size) / 1920)


if __name__ == "__main__":
    unittest.main()
