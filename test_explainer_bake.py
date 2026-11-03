"""Boards baked onto their pictures before the render (explainer/bake.py): the clip is the picture with the engine's own push-in and the board on it, frame for frame."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from explainer import bake as B

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


def _gradient(path: Path, w: int = 1376, h: int = 768) -> None:
    x = np.linspace(0, 255, w)[None, :, None]
    y = np.linspace(0, 255, h)[:, None, None]
    Image.fromarray(np.concatenate([np.broadcast_to(x, (h, w, 1)), np.broadcast_to(y, (h, w, 1)), np.full((h, w, 1), 90.0)], axis=2).astype("uint8")).save(path)


def _board(path: Path, seconds: float = 1.0) -> None:
    """A see-through board: a white box in the top-left corner, transparent elsewhere."""
    png = path.with_suffix(".png")
    im = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    im.paste((255, 255, 255, 255), (100, 100, 400, 300))
    im.save(png)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-r", "30", "-i", str(png), "-t", str(seconds), "-c:v", "qtrle", "-pix_fmt", "argb", str(path)], check=True)


def _frame(path: Path, i: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{i})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(1080, 1920, 3).astype(int)


class FramesTest(unittest.TestCase):
    def test_push_in_is_the_engines_and_even(self):
        with tempfile.TemporaryDirectory() as d:
            pic = Path(d) / "p.png"
            _gradient(pic)
            fr = [np.asarray(Image.frombytes("RGB", (1920, 1080), b), int) for b in B._frames(str(pic), 30, 30)]
            self.assertEqual(len(fr), 30)
            first = np.asarray(Image.open(pic).convert("RGB").resize((1920, 1080), Image.BILINEAR, box=B._cover(1376, 768)), int)
            self.assertLess(np.abs(fr[0] - first).mean(), 0.5)                  # frame 0: the cover crop, no zoom yet
            steps = [np.abs(fr[i] - fr[i - 1]).mean() for i in range(1, 30)]
            self.assertLess(np.std(steps) / np.mean(steps), 0.1)               # an even push-in: no stair steps


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is not installed")
class BakeTest(unittest.TestCase):
    def test_a_baked_clip_has_the_board_on_the_picture(self):
        with tempfile.TemporaryDirectory() as d:
            pic, mov, out = Path(d) / "p.png", Path(d) / "b.mov", Path(d) / "baked.mp4"
            _gradient(pic)
            _board(mov)
            self.assertTrue(B.bake_one(str(pic), str(mov), 30, out))
            self.assertFalse(out.with_name("baked.part.mp4").exists())
            f0 = _frame(out, 0)
            self.assertGreater(f0[200, 250].mean(), 235)                       # the board's white box
            self.assertLess(abs(f0[900, 1500].mean() - np.asarray(Image.open(pic).convert("RGB").resize((1920, 1080), Image.BILINEAR, box=B._cover(1376, 768)), int)[900, 1500].mean()), 12)

    def test_the_spec_shows_the_baked_clip_and_the_after_pass_skips_its_board(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "_work"
            (Path(d) / "explainer").mkdir(parents=True)
            work.mkdir()
            pic, mov = work / "005.png", Path(d) / "explainer" / "board_a.mov"
            _gradient(pic)
            _board(mov)
            rr = {"report": {"beat_details": {"e6": {"board_overlay": {"mov": str(mov), "start": 2.0, "end": 3.0}}}}}
            (Path(d) / "explainer" / "render_report.json").write_text(json.dumps(rr), encoding="utf-8")
            spec = {"events": [{"id": "e6_c1", "type": "media_full", "media": str(pic), "kenburns": True, "t_in": 2.0, "t_out": 3.0},
                               {"id": "e9_c1", "type": "media_full", "media": str(pic), "kenburns": True, "t_in": 8.0, "t_out": 9.0}]}
            self.assertEqual(B.bake_spec(spec, work), 1)
            self.assertTrue(spec["events"][0]["media"].endswith(".mp4"))
            self.assertFalse(spec["events"][0]["kenburns"])
            self.assertEqual(spec["events"][1]["media"], str(pic))              # a picture with no board stays a still
            self.assertIn(str(mov), B.baked_movs(Path(d) / "explainer"))

    def test_nothing_to_bake_leaves_the_spec_and_clears_an_old_list(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "explainer").mkdir()
            (Path(d) / "explainer" / "render_report.json").write_text(json.dumps({"report": {"beat_details": {}}}), encoding="utf-8")
            (Path(d) / "explainer" / B.BAKED_LIST).write_text(json.dumps({"old.mov": "x"}), encoding="utf-8")
            spec = {"events": []}
            self.assertEqual(B.bake_spec(spec, Path(d) / "_work"), 0)
            self.assertEqual(B.baked_movs(Path(d) / "explainer"), {})


if __name__ == "__main__":
    unittest.main()
