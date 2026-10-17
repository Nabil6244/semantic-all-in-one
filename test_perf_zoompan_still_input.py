"""Perf regression: a Ken Burns still reads its image once (no ``-loop 1``) when the clip has no overlay inputs.

zoompan's ``d=frames`` makes every frame from the first picture, so the looped input only decoded and upscaled a
second 4x copy (~70 MB extra peak RSS per 1080p encode) for byte-identical output. Overlay clips keep the loop: with
an overlay input the graph can emit one extra frame once the base ends.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import video_generator as vg


def _capture_cmd(**kwargs) -> list[str]:
    cmds: list[list[str]] = []
    with mock.patch.object(vg, "_run_ffmpeg_encode", lambda cmd, name: cmds.append(list(cmd))):
        vg._render_scene_clip(**kwargs)
    assert len(cmds) == 1
    return cmds[0]


def _first_input_args(cmd: list[str]) -> list[str]:
    i = cmd.index("-i")
    return cmd[2:i + 2]  # after "ffmpeg", "-y"


class ZoompanStillInputArgsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.img = self.tmp / "001.png"
        self.img.write_bytes(b"")  # never decoded: the encode is captured
        self.base = dict(img_path=self.img, out_path=self.tmp / "o.mp4", duration=2.0, width=1920, height=1080,
                         fps=30, zoom=True, zoom_in=True, zoom_amount=0.10)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ken_burns_still_reads_the_image_once(self):
        cmd = _capture_cmd(**self.base)
        self.assertEqual(_first_input_args(cmd), ["-i", str(self.img)])
        self.assertIn("zoompan=", cmd[cmd.index("-vf") + 1])

    def test_fades_and_text_filters_also_read_once(self):
        cmd = _capture_cmd(**self.base, fade_in=0.3, fade_out=0.3, text_effect_filters="drawbox=t=fill")
        self.assertEqual(_first_input_args(cmd), ["-i", str(self.img)])

    def test_overlay_inputs_keep_the_looped_base(self):
        cap = self.tmp / "cap.png"
        cap.write_bytes(b"")
        cmd = _capture_cmd(**self.base, caption_overlay=cap)
        self.assertEqual(_first_input_args(cmd), ["-loop", "1", "-i", str(self.img)])
        cmd = _capture_cmd(**self.base, timed_overlays=[(cap, 0.1, 0.5)])
        self.assertEqual(_first_input_args(cmd), ["-loop", "1", "-i", str(self.img)])

    def test_static_still_keeps_the_loop(self):
        cmd = _capture_cmd(**{**self.base, "zoom": False})
        self.assertEqual(_first_input_args(cmd), ["-loop", "1", "-i", str(self.img)])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class ZoompanStillOutputUnchangedTest(unittest.TestCase):
    """The encoded clip is byte-identical to the old looped-input command, frame count included."""

    def setUp(self):
        from PIL import Image

        self.tmp = Path(tempfile.mkdtemp())
        self.img = self.tmp / "001.png"
        Image.effect_mandelbrot((640, 360), (-2, -1.2, 1, 1.2), 60).convert("RGB").save(self.img)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _encode(self, cmd: list[str], name: str) -> tuple[str, int]:
        out = self.tmp / name
        subprocess.run([cmd[0], "-v", "error", *cmd[1:-1], str(out)], check=True)
        frames = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
             "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return hashlib.sha1(out.read_bytes()).hexdigest(), int(frames)

    def test_same_bytes_as_looped_input(self):
        # 7.4667 s at 30 fps: "-t 7.466667" rounds UP past 224/30, the case where an extra frame could slip in.
        for duration, fps, style, fade in ((7.4667, 30, None, 0.0), (0.05, 30, "subtle_drift", 0.0), (2.2333, 24, None, 0.3)):
            with self.subTest(duration=duration, fps=fps, style=style):
                cmd = _capture_cmd(img_path=self.img, out_path=self.tmp / "o.mp4", duration=duration, width=320,
                                   height=180, fps=fps, zoom=True, zoom_in=False, zoom_amount=0.10,
                                   camera_style=style, fade_in=fade, fade_out=fade)
                i = cmd.index("-i")
                old = cmd[:i] + ["-loop", "1"] + cmd[i:]
                new_sha, new_frames = self._encode(cmd, "new.mp4")
                old_sha, old_frames = self._encode(old, "old.mp4")
                self.assertEqual(new_sha, old_sha)
                self.assertEqual(new_frames, max(int(round(duration * fps)), 1))
                self.assertEqual(old_frames, new_frames)


if __name__ == "__main__":
    unittest.main()
