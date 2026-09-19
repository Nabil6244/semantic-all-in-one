"""Real B-roll (VIDEO_2) picture-in-picture overlay tests. VIDEO_2
previously had NO actual simultaneous-overlay rendering anywhere — this is
video_generator.composite_broll_overlay (real ffmpeg overlay filter) plus
the end-to-end path through render_video().
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import video_generator as vg

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestCompositeBrollOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls._tmpdir.name)
        cls.base = root / "base.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=4:r=25", "-pix_fmt", "yuv420p", str(cls.base)],
            check=True, capture_output=True,
        )
        cls.broll = root / "broll.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=4:r=25", "-pix_fmt", "yuv420p", str(cls.broll)],
            check=True, capture_output=True,
        )
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def _sample(self, path: Path, frame_n: int, xy) -> tuple:
        frame = self.root / f"sample_{frame_n}_{xy[0]}_{xy[1]}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path), "-vf", f"select=eq(n\\,{frame_n})", "-vframes", "1", str(frame)],
            check=True, capture_output=True,
        )
        return Image.open(frame).convert("RGB").getpixel(xy)

    def test_overlay_appears_only_within_its_time_window(self):
        out = self.root / "composited.mp4"
        ok = vg.composite_broll_overlay(
            self.base, self.broll, out,
            overlay_start=1.0, overlay_duration=2.0, width=320, height=180, fps=25,
        )
        self.assertTrue(ok)
        self.assertTrue(out.is_file())

        # PIP box: width=128 (320*0.4), height~72, margin=8 -> (184,100)-(312,172).
        pip_point = (250, 140)
        outside_point = (10, 10)

        before = self._sample(out, 5, pip_point)  # t~0.2s, before window
        during = self._sample(out, 50, pip_point)  # t~2.0s, inside window
        after = self._sample(out, 95, pip_point)  # t~3.8s, after window
        bg = self._sample(out, 50, outside_point)  # unaffected background

        self.assertEqual(before, (254, 0, 0), "before the overlay window, the PIP area must show the base (red)")
        self.assertEqual(during, (0, 0, 255), "during the overlay window, the PIP area must show the B-roll (blue)")
        self.assertEqual(after, (254, 0, 0), "after the overlay window, the PIP area must revert to the base (red)")
        self.assertEqual(bg, (254, 0, 0), "outside the PIP rectangle, the base must be unaffected")

    def test_zero_duration_returns_false_without_crashing(self):
        out = self.root / "zero.mp4"
        ok = vg.composite_broll_overlay(
            self.base, self.broll, out, overlay_start=1.0, overlay_duration=0.0,
            width=320, height=180, fps=25,
        )
        self.assertFalse(ok)

    def test_bad_broll_source_fails_gracefully(self):
        out = self.root / "bad.mp4"
        ok = vg.composite_broll_overlay(
            self.base, self.root / "does_not_exist.mp4", out,
            overlay_start=0.5, overlay_duration=1.0, width=320, height=180, fps=25,
        )
        self.assertFalse(ok)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg not on PATH")
class TestBrollThroughRenderVideo(unittest.TestCase):
    """End-to-end: render_video() with an EditDecision carrying a real
    broll entry actually produces a composited frame in the final output —
    not just that the primitive works in isolation."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        root = Path(self._tmpdir.name)
        self.images_dir = root / "images"
        self.images_dir.mkdir()
        Image.new("RGB", (160, 90), (200, 40, 40)).save(self.images_dir / "1.png")

        self.broll_path = root / "broll.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=4:r=10", "-pix_fmt", "yuv420p", str(self.broll_path)],
            check=True, capture_output=True,
        )
        self.audio_path = root / "vo.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(self.audio_path)],
            check=True, capture_output=True,
        )
        self.work_dir = root / "work"
        self.work_dir.mkdir()
        self.old_cwd = os.getcwd()
        os.chdir(self.work_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self._tmpdir.cleanup()

    def test_real_broll_overlay_reaches_the_final_export(self):
        aligned_rows = [{"scene_number": "1", "start_time": 0.0, "script_segment": "one"}]
        decision_map = {
            "1": {
                "scene_number": "1", "required_duration": 4.0, "strategy": "SINGLE_SHOT",
                "shots": [{"shot_id": "s1", "output_duration": 4.0, "source_path": str(self.images_dir / "1.png")}],
                "source_asset": str(self.images_dir / "1.png"),
                "broll": [
                    {
                        "shot_id": "b1", "source_path": str(self.broll_path), "source_start": 0.0,
                        "speed": 1.0, "overlay_start": 1.0, "overlay_duration": 2.0,
                        "scale": 0.4, "position": "bottom_right",
                    },
                ],
            },
        }
        out_path = self.work_dir / "final.mp4"
        vg.render_video(
            aligned_rows, 4.0, self.images_dir, str(self.audio_path), str(out_path),
            "160x90", 10, zoom=False, visual_transitions=False,
            edit_decisions_by_scene=decision_map,
        )
        self.assertTrue(out_path.is_file())

        frame = self.work_dir / "check.png"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(out_path), "-vf", "select=eq(n\\,20)", "-vframes", "1", str(frame)],
            check=True, capture_output=True,
        )
        img = Image.open(frame).convert("RGB")
        # PIP box for 160x90 at scale 0.4: width=64, height~36, margin~3 -> around (93,51)-(157,87).
        r, g, b = img.getpixel((125, 70))
        self.assertGreater(b, r, "B-roll (blue) should be visible in the PIP region during its overlay window")


if __name__ == "__main__":
    unittest.main()
