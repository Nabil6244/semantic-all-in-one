"""Regression: strong visuals must breathe; repetition ≠ automatic shorten.

Covers the decision hierarchy after the VO-aware / dual-asset upgrade:
coverage opportunity and repetition must not force 1–2s micro-cuts on
assets that already cover narration.
"""

from __future__ import annotations

import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from editorial.complements import (
    AssetCandidate,
    needs_complementary_coverage,
    score_complement_candidate,
    select_complements,
)
from editorial.continuity import ContinuityTracker, source_identity_key
from editorial.intent import EditorialIntent
from editorial.schema import EditorialScene
from editorial.shot_planner import plan_edit_decision


def _png(path: Path, rgb=(40, 80, 120)) -> Path:
    r, g, b = rgb
    raw = bytes([0, r, g, b])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return path


def _scene(
    sn: str,
    *,
    start: float,
    end: float,
    text: str,
    purpose: str = "process",
    actual: float | None = 7.0,
    asset: str = "stock_video",
) -> EditorialScene:
    return EditorialScene(
        scene_number=sn,
        start=start,
        end=end,
        duration=end - start,
        narration_excerpt=text,
        purpose=purpose,  # type: ignore[arg-type]
        attention_score=0.7,
        asset_type_intent=asset,
        actual_asset_duration=actual,
        visual_description="transformer factory manufacturing",
        visual_goal="show production",
    )


class TestVideoBreathing(unittest.TestCase):
    def test_5s_vo_7s_video_no_unnecessary_cut(self) -> None:
        """CASE A — covering video must not be chopped to ~2s."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "001.mp4"
            primary.write_bytes(b"fake-mp4")
            comp = _png(root / "001_b.png", (80, 80, 80))
            scene = _scene(
                "1",
                start=0,
                end=5,
                text="Factory production continues at full pace.",
                actual=7.0,
            )
            candidates = [
                AssetCandidate(
                    asset_id="001",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="transformer factory",
                    asset_class="stock_video",
                ),
                AssetCandidate(
                    asset_id="001_b",
                    path=comp,
                    visual_role="detail",
                    query_hint="transformer factory manufacturing detail",
                    asset_class="stock_image",
                ),
            ]
            # Stale dual hint from pre-download allocation must not force a cut.
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
            )
            self.assertEqual(d.strategy, "SINGLE_SHOT")
            self.assertEqual(len(d.shots), 1)
            self.assertAlmostEqual(d.shots[0].output_duration, 5.0, places=1)
            self.assertGreaterEqual(d.shots[0].output_duration, 4.5)

    def test_6s_vo_8s_video_breathes(self) -> None:
        """CASE H — strong video covers longer VO as one shot."""
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp) / "008.mp4"
            primary.write_bytes(b"fake")
            scene = _scene(
                "8",
                start=0,
                end=6,
                text="The production line runs through the night.",
                actual=8.0,
                purpose="context",
            )
            d = plan_edit_decision(scene, media_path=primary, coverage_strategy="single")
            self.assertEqual(d.strategy, "SINGLE_SHOT")
            self.assertEqual(len(d.shots), 1)
            self.assertAlmostEqual(d.shots[0].output_duration, 6.0, places=1)

    def test_repetition_does_not_shorten_strong_clip(self) -> None:
        """CASE B — repetition is a selection problem, not a duration problem."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "002.mp4"
            primary.write_bytes(b"fake")
            alt = _png(root / "002_b.png", (10, 10, 10))
            scene = _scene(
                "2",
                start=0,
                end=5,
                text="Workers assemble the next transformer core.",
                actual=7.0,
            )
            candidates = [
                AssetCandidate(
                    asset_id="002",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="transformer workers",
                    asset_class="stock_video",
                ),
                AssetCandidate(
                    asset_id="002_b",
                    path=alt,
                    visual_role="detail",
                    query_hint="transformer workers assemble core detail",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
                used_asset_ids=["002"],
                recent_asset_ids=["002", "002"],
            )
            self.assertEqual(len(d.shots), 1)
            self.assertAlmostEqual(d.shots[0].output_duration, 5.0, places=1)

    def test_short_2s_vo_no_multishot(self) -> None:
        """CASE G — short VO gets one visual."""
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp) / "004.mp4"
            primary.write_bytes(b"fake")
            comp = _png(Path(tmp) / "004_b.png")
            scene = _scene(
                "4",
                start=0,
                end=2,
                text="Brief beat.",
                purpose="context",
                actual=7.0,
            )
            candidates = [
                AssetCandidate(
                    asset_id="004",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="factory",
                    asset_class="stock_video",
                ),
                AssetCandidate(
                    asset_id="004_b",
                    path=comp,
                    visual_role="detail",
                    query_hint="factory detail",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
            )
            self.assertEqual(len(d.shots), 1)
            self.assertAlmostEqual(d.total_output_duration(), 2.0, places=1)


@unittest.skipUnless(
    __import__("shutil").which("ffmpeg") is not None
    and __import__("shutil").which("ffprobe") is not None,
    "ffmpeg/ffprobe required",
)
class TestNoSameShotLoopWhenFileCovers(unittest.TestCase):
    """Post-upgrade regression: 8s Flow/stock must not become 2s×3 loops."""

    def _make_video(self, path: Path, seconds: float) -> Path:
        import subprocess

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
                f"color=c=blue:s=320x180:d={seconds}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-t",
                str(seconds),
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        return path

    def test_stale_short_metadata_does_not_multishot_long_file(self) -> None:
        """Stale actual=2s must not override probed 8s file for a 5s VO."""
        with tempfile.TemporaryDirectory() as tmp:
            primary = self._make_video(Path(tmp) / "flow8.mp4", 8.0)
            scene = _scene(
                "20",
                start=0,
                end=5,
                text="Factory production continues with a strong eight second clip.",
                actual=2.0,  # stale / wrong
                purpose="process",
            )
            d = plan_edit_decision(scene, media_path=primary, coverage_strategy="dual")
            self.assertEqual(d.strategy, "SINGLE_SHOT")
            self.assertEqual(len(d.shots), 1)
            self.assertAlmostEqual(d.shots[0].output_duration, 5.0, places=1)
            # Source window must cover the VO, not a ~2s stub.
            span = float(d.shots[0].source_end or 0) - float(d.shots[0].source_start or 0)
            self.assertGreaterEqual(span, 4.5)

    def test_collapse_same_source_multishot_when_file_covers(self) -> None:
        from editorial.edit_decision import EditDecision, MediaEditability, ShotSpec
        from editorial.shot_planner import _reconcile_playable_coverage

        with tempfile.TemporaryDirectory() as tmp:
            primary_path = self._make_video(Path(tmp) / "stock8.mp4", 8.0)
            primary = AssetCandidate(
                asset_id="021",
                path=primary_path,
                is_primary=True,
                asset_class="stock_video",
            )
            decision = EditDecision(
                scene_number="21",
                required_duration=5.0,
                strategy="MULTI_SHOT",
                shots=[
                    ShotSpec(
                        shot_id="21_s0",
                        output_duration=2.0,
                        source_start=0.0,
                        source_end=2.0,
                        scale=1.0,
                        source_path=str(primary_path),
                        asset_id="021",
                    ),
                    ShotSpec(
                        shot_id="21_s1",
                        output_duration=2.0,
                        source_start=0.0,
                        source_end=2.0,
                        scale=1.28,
                        source_path=str(primary_path),
                        asset_id="021",
                    ),
                    ShotSpec(
                        shot_id="21_s2",
                        output_duration=1.0,
                        source_start=0.0,
                        source_end=1.0,
                        scale=1.4,
                        source_path=str(primary_path),
                        asset_id="021",
                    ),
                ],
            )
            out = _reconcile_playable_coverage(
                decision,
                primary=primary,
                usable=2.0,  # stale short
                required=5.0,
                media_kind="video",
            )
            self.assertEqual(out.strategy, "SINGLE_SHOT")
            self.assertEqual(len(out.shots), 1)
            self.assertAlmostEqual(out.shots[0].output_duration, 5.0, places=1)

    def test_render_does_not_loop_when_file_covers_vo(self) -> None:
        import video_generator as vg

        with tempfile.TemporaryDirectory() as tmp:
            src = self._make_video(Path(tmp) / "src8.mp4", 8.0)
            out = Path(tmp) / "shot.mp4"
            # Stale short source_end like an old edit plan — file is still 8s.
            shot = {
                "shot_id": "1_s0",
                "output_duration": 5.0,
                "source_start": 0.0,
                "source_end": 2.0,
                "scale": 1.0,
                "camera_style": "static",
                "hold_tail": False,
            }
            vg._render_editorial_shot(src, out, shot, 320, 180, 12, zoom_amount=0.05)
            self.assertTrue(out.is_file())
            from media_duration import probe_media_duration

            dur = probe_media_duration(out) or 0.0
            self.assertGreaterEqual(dur, 4.7)
            self.assertLessEqual(dur, 5.3)



class TestImageBreathing(unittest.TestCase):
    def test_5s_vo_strong_image_holds(self) -> None:
        """CASE C — strong still covers full VO."""
        with tempfile.TemporaryDirectory() as tmp:
            img = _png(Path(tmp) / "003.png")
            scene = _scene(
                "3",
                start=0,
                end=5,
                text="Historical photograph of the plant.",
                purpose="evidence",
                actual=None,
                asset="stock_image",
            )
            d = plan_edit_decision(scene, media_path=img, coverage_strategy="single")
            self.assertEqual(len(d.shots), 1)
            self.assertAlmostEqual(d.shots[0].output_duration, 5.0, places=1)
            self.assertIn(d.shots[0].camera_style, ("static", "hold", "subtle_drift"))

    def test_image_plus_complement_not_auto_dual_at_5s(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            img = _png(Path(tmp) / "005.png")
            comp = _png(Path(tmp) / "005_b.png", (1, 1, 1))
            scene = _scene(
                "5",
                start=0,
                end=5,
                text="Archive photograph of the original plant.",
                purpose="evidence",
                actual=None,
                asset="stock_image",
            )
            candidates = [
                AssetCandidate(
                    asset_id="005",
                    path=img,
                    is_primary=True,
                    visual_role="context",
                    query_hint="archive plant photograph",
                    asset_class="stock_image",
                ),
                AssetCandidate(
                    asset_id="005_b",
                    path=comp,
                    visual_role="detail",
                    query_hint="archive plant photograph detail document",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=img,
                candidates=candidates,
                coverage_strategy="single",
            )
            self.assertNotEqual(d.strategy, "DUAL_ASSET")
            self.assertEqual(len(d.shots), 1)

    def test_four_images_vary_motion_not_all_zoom(self) -> None:
        """CASE D — consecutive stills must not all push_in."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracker = ContinuityTracker()
            cams: list[str] = []
            for i in range(4):
                img = _png(root / f"img{i}.png", (i * 40, i * 40, i * 40))
                scene = _scene(
                    str(10 + i),
                    start=float(i * 5),
                    end=float(i * 5 + 5),
                    text=f"Atmosphere around transformers and the plant {i}.",
                    purpose="atmosphere",
                    actual=None,
                    asset="stock_image",
                )
                d = plan_edit_decision(scene, media_path=img, tracker=tracker)
                self.assertEqual(len(d.shots), 1)
                cams.append(d.shots[0].camera_style)
            self.assertLess(cams.count("push_in"), 4)
            # At least two distinct treatments across four holds.
            self.assertGreaterEqual(len(set(cams)), 2)


class TestRepetitionSelection(unittest.TestCase):
    def test_same_asset_prefers_alternative(self) -> None:
        """CASE E — exact asset reuse prefers an alternative when available."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = _png(root / "006.png")
            alt = _png(root / "006_b.png", (9, 9, 9))
            scene = _scene(
                "6",
                start=0,
                end=8,
                text="America needs transformers for electricity demand on the grid.",
                actual=2.5,
                purpose="process",
            )
            scene.asset_type_intent = "stock_video"
            candidates = [
                AssetCandidate(
                    asset_id="006",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="transformer factory",
                    asset_class="stock_video",
                ),
                AssetCandidate(
                    asset_id="006",
                    path=primary,
                    visual_role="context",
                    query_hint="transformer factory exterior",
                    asset_class="stock_image",
                ),
                AssetCandidate(
                    asset_id="006_b",
                    path=alt,
                    visual_role="consequence",
                    query_hint="electrical power grid transformers demand",
                    asset_class="stock_image",
                ),
            ]
            # Force need for complements via short usable + dual strategy.
            # Use a real short video duration path: media is image file but
            # known duration is set — planner still needs short primary.
            # Build via select_complements directly for identity preference.
            primary_c = candidates[0]
            picked = select_complements(
                candidates,
                scene=scene,
                primary=primary_c,
                beat_role="process",
                used_asset_ids=["006"],
                recent_asset_ids=["006"],
            )
            self.assertTrue(picked)
            self.assertEqual(picked[0].asset_id, "006_b")

    def test_crop_reframe_same_source_identity(self) -> None:
        """CASE — crop/zoom of same image shares source identity."""
        self.assertEqual(source_identity_key(asset_id="001"), "001")
        self.assertEqual(
            source_identity_key(source_path="/media/001_crop.png"),
            "001",
        )
        self.assertEqual(
            source_identity_key(source_path="/media/001_zoom.jpg"),
            "001",
        )
        tracker = ContinuityTracker()
        tracker.note_asset("001")
        self.assertGreaterEqual(
            tracker.source_reuse_count(source_path="/x/001_reframe.png"), 1
        )

    def test_same_subject_different_role_not_forced_cut(self) -> None:
        """CASE F — semantic similarity with different roles is progression."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = Path(tmp) / "007.mp4"
            primary.write_bytes(b"fake")
            line = _png(root / "007_b.png", (2, 2, 2))
            scene = _scene(
                "7",
                start=0,
                end=5,
                text="Inside the factory the production line builds transformers.",
                actual=7.0,
            )
            primary_c = AssetCandidate(
                asset_id="007",
                path=primary,
                is_primary=True,
                visual_role="context",
                query_hint="factory exterior transformers",
                asset_class="stock_video",
            )
            prog = AssetCandidate(
                asset_id="007_b",
                path=line,
                visual_role="detail",
                query_hint="factory production line transformers",
                asset_class="stock_image",
            )
            score = score_complement_candidate(
                prog,
                scene=scene,
                primary=primary_c,
                beat_role="process",
                used_asset_ids=[],
                recent_asset_ids=[],
            )
            self.assertGreaterEqual(score, 0.28)
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=[primary_c, prog],
                coverage_strategy="dual",
            )
            # Covering primary still breathes — progression does not force a cut.
            self.assertEqual(d.strategy, "SINGLE_SHOT")
            self.assertAlmostEqual(d.shots[0].output_duration, 5.0, places=1)


class TestDualOnlyWhenJustified(unittest.TestCase):
    def test_dual_when_primary_short(self) -> None:
        """Dual remains available when primary cannot cover."""
        self.assertTrue(
            needs_complementary_coverage(
                required=8.0, primary_usable=3.0, coverage_strategy="dual"
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Use .mp4 so media_kind is video; duration from actual_asset_duration.
            primary = root / "009.mp4"
            primary.write_bytes(b"fake")
            comp = _png(root / "009_b.png", (8, 8, 8))
            scene = _scene(
                "9",
                start=0,
                end=8,
                text="America needs thousands of new transformers to meet rising electricity demand.",
                actual=3.0,
            )
            candidates = [
                AssetCandidate(
                    asset_id="009",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="transformer factory",
                    asset_class="stock_video",
                ),
                AssetCandidate(
                    asset_id="009_b",
                    path=comp,
                    visual_role="detail",
                    query_hint="transformer manufacturing detail electricity demand",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
            )
            self.assertEqual(d.strategy, "DUAL_ASSET")
            self.assertGreaterEqual(len(d.shots), 2)
            # Primary should keep nearly all of its usable window, not ~45%.
            self.assertGreaterEqual(d.shots[0].output_duration, 2.5)

    def test_stale_dual_hint_ignored_when_primary_covers(self) -> None:
        self.assertFalse(
            needs_complementary_coverage(
                required=5.0,
                primary_usable=7.0,
                coverage_strategy="dual",
                media_kind="video",
            )
        )

    def test_prefer_dual_intent_does_not_chop_covering_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            primary = Path(tmp) / "010.mp4"
            primary.write_bytes(b"fake")
            comp = _png(Path(tmp) / "010_b.png")
            scene = _scene(
                "10",
                start=0,
                end=5,
                text="The plant runs at capacity.",
                actual=7.0,
            )
            intent = EditorialIntent(
                scene_number="10",
                shot_strategy="dual",
                visual_strategy="process_sequence",
                confidence=0.9,
                source="ai",
            )
            candidates = [
                AssetCandidate(
                    asset_id="010",
                    path=primary,
                    is_primary=True,
                    visual_role="context",
                    query_hint="plant capacity",
                    asset_class="stock_video",
                ),
                AssetCandidate(
                    asset_id="010_b",
                    path=comp,
                    visual_role="detail",
                    query_hint="plant capacity detail",
                    asset_class="stock_image",
                ),
            ]
            d = plan_edit_decision(
                scene,
                media_path=primary,
                candidates=candidates,
                coverage_strategy="dual",
                intent=intent,
            )
            self.assertEqual(d.strategy, "SINGLE_SHOT")
            self.assertAlmostEqual(d.shots[0].output_duration, 5.0, places=1)


if __name__ == "__main__":
    unittest.main()
