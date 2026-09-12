"""Focused tests: small-shortage RETIME and distributed retime coverage."""

from __future__ import annotations

import unittest
from pathlib import Path

from editorial.complements import AssetCandidate, needs_complementary_coverage
from editorial.edit_decision import MediaEditability
from editorial.schema import EditorialScene
from editorial.shot_planner import plan_edit_decision, safe_retime_speed


def _scene(
    sn: str,
    *,
    start: float,
    end: float,
    text: str,
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
        attention_score=0.5,
        asset_type_intent=asset_type,
        actual_asset_duration=actual,
        pacing_bias="normal",  # type: ignore[arg-type]
    )


def _video_edit(usable: float, *, motion: float = 0.4) -> MediaEditability:
    return MediaEditability(
        native_duration=usable,
        usable_duration=usable,
        media_kind="video",
        motion_level=motion,
        loopability=0.2,
        crop_potential=0.7,
        reframe_potential=0.7,
        punch_in_potential=0.75,
        slow_motion_potential=0.35,
        speed_change_tolerance=0.15,
        visual_complexity=0.45,
        editability_score=0.7,
    )


class TestSafeRetimeSpeed(unittest.TestCase):
    def test_exact_and_over_cover(self) -> None:
        self.assertEqual(safe_retime_speed(8.0, 8.0), 1.0)
        self.assertEqual(safe_retime_speed(10.0, 8.0), 1.0)

    def test_small_shortage(self) -> None:
        s = safe_retime_speed(7.0, 8.0)
        self.assertIsNotNone(s)
        assert s is not None
        self.assertAlmostEqual(s, 0.875, places=3)

    def test_large_shortage_refuses(self) -> None:
        self.assertIsNone(safe_retime_speed(5.0, 8.0))


class TestSmallShortageRetime(unittest.TestCase):
    def test_seven_into_eight_retimes(self) -> None:
        scene = _scene(
            "1",
            start=0,
            end=8,
            text="A slightly longer narration over a nearly matching clip.",
            actual=7.0,
        )
        d = plan_edit_decision(scene, editability=_video_edit(7.0))
        self.assertEqual(d.strategy, "RETIME")
        self.assertEqual(len(d.shots), 1)
        shot = d.shots[0]
        self.assertFalse(shot.hold_tail)
        self.assertAlmostEqual(shot.speed, 0.875, places=3)
        self.assertAlmostEqual(shot.output_duration, 8.0, places=2)
        self.assertAlmostEqual(float(shot.source_end or 0), 7.0, places=2)
        self.assertGreaterEqual(float(shot.source_end or 0), 6.9)

    def test_exact_coverage_no_retime(self) -> None:
        scene = _scene(
            "2",
            start=0,
            end=8,
            text="Narration matches the clip length exactly.",
            actual=8.0,
        )
        d = plan_edit_decision(scene, editability=_video_edit(8.0))
        self.assertEqual(d.strategy, "SINGLE_SHOT")
        self.assertEqual(len(d.shots), 1)
        self.assertAlmostEqual(d.shots[0].speed, 1.0, places=3)
        self.assertFalse(d.shots[0].hold_tail)

    def test_clip_longer_than_vo_keeps_1x_assigned_coverage(self) -> None:
        """Longer clip: use assigned VO window at 1× — do not invent a longer beat."""
        scene = _scene(
            "3",
            start=0,
            end=6,
            text="Shorter narration than the available clip.",
            actual=8.0,
        )
        d = plan_edit_decision(scene, editability=_video_edit(8.0))
        self.assertEqual(d.strategy, "SINGLE_SHOT")
        self.assertEqual(len(d.shots), 1)
        self.assertAlmostEqual(d.shots[0].speed, 1.0, places=3)
        self.assertAlmostEqual(d.shots[0].output_duration, 6.0, places=2)
        # Assigned coverage may trim usage; full asset remains available (source_end ≤ usable).
        self.assertLessEqual(float(d.shots[0].source_end or 0), 8.05)
        self.assertGreaterEqual(float(d.shots[0].source_end or 0), 5.5)

    def test_large_shortage_does_not_force_retime(self) -> None:
        scene = _scene(
            "4",
            start=0,
            end=8,
            text="America needs thousands of new transformers to meet rising demand.",
            purpose="process",
            actual=5.0,
        )
        d = plan_edit_decision(scene, editability=_video_edit(5.0))
        self.assertNotEqual(d.strategy, "RETIME")
        if d.shots:
            for s in d.shots:
                self.assertGreaterEqual(float(s.speed or 1.0), 0.8 - 1e-6)
                if abs(float(s.speed or 1.0) - 1.0) > 0.02:
                    # Must not be a forced 5→8 (0.625×) stretch.
                    self.assertGreaterEqual(float(s.speed), 0.8 - 1e-6)
                    self.assertGreaterEqual(5.0 / float(s.output_duration), 0.8 - 1e-6)
        self.assertFalse(
            len(d.shots) == 1
            and abs(float(d.shots[0].speed) - (5.0 / 8.0)) < 0.05
        )

    def test_no_premature_trim_before_full_coverage(self) -> None:
        """7s clip under 8s VO must keep ~full usable, not a short first sub-window."""
        scene = _scene(
            "5",
            start=0,
            end=8,
            text="Keep the full clip available for coverage planning.",
            actual=7.0,
        )
        d = plan_edit_decision(scene, editability=_video_edit(7.0))
        self.assertEqual(len(d.shots), 1)
        span = float(d.shots[0].source_end or 0) - float(d.shots[0].source_start or 0)
        self.assertGreaterEqual(span, 6.9)
        self.assertEqual(d.strategy, "RETIME")


class TestDistributedRetime(unittest.TestCase):
    @staticmethod
    def _make_video(path: Path, seconds: float) -> Path:
        import subprocess

        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size=320x180:rate=24:duration={seconds}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(path),
            ],
            check=True,
        )
        return path

    def test_two_clips_nearly_cover_vo(self) -> None:
        import tempfile

        scene = _scene(
            "6",
            start=0,
            end=12,
            text="America needs thousands of new transformers to meet rising electricity demand on the grid.",
            purpose="process",
            actual=7.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = self._make_video(root / "006.mp4", 7.0)
            comp = self._make_video(root / "006_b.mp4", 4.0)
            candidates = [
                AssetCandidate(
                    asset_id="006",
                    path=primary,
                    is_primary=True,
                    asset_class="stock_video",
                    visual_role="context",
                    query_hint="transformer factory electricity",
                    metadata={"actual_duration": 7.0},
                ),
                AssetCandidate(
                    asset_id="006_b",
                    path=comp,
                    asset_class="stock_video",
                    visual_role="detail",
                    editorial_purpose="detail",
                    query_hint="transformer close-up manufacturing electricity grid detail",
                    metadata={"actual_duration": 4.0},
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                editability=_video_edit(7.0),
                candidates=candidates,
                coverage_strategy="dual",
            )
            self.assertEqual(d.strategy, "DUAL_ASSET")
            self.assertGreaterEqual(len(d.shots), 2)
            self.assertAlmostEqual(d.total_output_duration(), 12.0, places=1)
            self.assertFalse(any(s.hold_tail for s in d.shots))
            speeds = [float(s.speed or 1.0) for s in d.shots]
            self.assertTrue(any(abs(sp - 1.0) > 0.02 for sp in speeds))
            for s in d.shots:
                self.assertGreaterEqual(float(s.speed or 1.0), 0.8 - 1e-6)
                self.assertLessEqual(float(s.speed or 1.0), 1.25 + 1e-6)
            src_total = 0.0
            for s in d.shots:
                if s.source_end is not None:
                    src_total += max(
                        0.0, float(s.source_end) - float(s.source_start or 0.0)
                    )
            self.assertGreaterEqual(src_total, 10.5)
            self.assertLessEqual(src_total, 11.6)


class TestComplementGateRespectsRetimeBand(unittest.TestCase):
    def test_mild_shortfall_does_not_need_complement(self) -> None:
        self.assertFalse(
            needs_complementary_coverage(
                required=8.0,
                primary_usable=7.0,
                coverage_strategy="dual",
                media_kind="video",
            )
        )


if __name__ == "__main__":
    unittest.main()
