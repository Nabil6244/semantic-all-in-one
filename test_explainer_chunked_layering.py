"""Boards, map overlays and the presenter are laid on in one pass of parallel time chunks (overlay.composite_chunked): every clip lands on the same frames as in one long
pass, across chunk edges too, the frame count and the audio are kept, and the presenter shows only inside its windows."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from explainer.beats import overlay as OV

W, H, FPS = 320, 180, 30


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def pixel(video, n, x, y):
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"select='eq(n,{n})',crop=2:2:{x}:{y}", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return tuple(out[:3])


def frames(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True, check=True)
    return int(r.stdout.strip())


class Chunked(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Path(tempfile.mkdtemp())
        ff("-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d=12", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-c:v", "libx264", "-crf", "10", "-preset", "superfast",
           "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.d / "base.mp4"))
        for name, color in (("a", "yellow"), ("b", "red")):          # 1 s full-frame alpha clips, a box at the centre
            ff("-filter_complex", f"color=c={color}:s=100x100:r={FPS}:d=1,format=rgba[b];color=c=black@0.0:s={W}x{H}:r={FPS}:d=1,format=rgba[bg];[bg][b]overlay=110:40:format=auto,format=rgba",
               "-c:v", "qtrle", "-pix_fmt", "argb", str(cls.d / f"{name}.mov"))
        ff("-filter_complex", f"color=c=blue:s=40x40:r={FPS}:d=1,format=rgba", "-c:v", "qtrle", "-pix_fmt", "argb", str(cls.d / "p.mov"))
        cls.out = cls.d / "out.mp4"
        # clip a from frame 60 (2.0 s); clip b straddles the chunk edge at 6.0 s (frames 165-194); presenter at 9-10 s
        cls.rc = OV.composite_chunked(cls.d / "base.mp4", [(cls.d / "a.mov", 2.0), (cls.d / "b.mov", 5.5)], cls.out, workers=2,
                                      presenter={"mov": str(cls.d / "p.mov"), "x": 10, "y": 10, "windows": [(9.0, 10.0)]})

    def test_written_with_every_frame_and_the_audio(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual(frames(self.out), 12 * FPS)
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(self.out)], capture_output=True, text=True)
        self.assertIn("audio", r.stdout)

    def test_a_clip_lands_on_its_own_frames(self):
        self.assertLess(sum(pixel(self.out, 59, 160, 90)), 60)
        self.assertGreater(pixel(self.out, 60, 160, 90)[0], 200)
        self.assertGreater(pixel(self.out, 89, 160, 90)[0], 200)
        self.assertLess(sum(pixel(self.out, 90, 160, 90)), 60)

    def test_a_clip_across_the_chunk_edge_is_whole(self):
        for n in (165, 179, 180, 194):
            self.assertGreater(pixel(self.out, n, 160, 90)[0], 200, n)
        self.assertLess(sum(pixel(self.out, 195, 160, 90)), 60)

    def test_the_presenter_only_inside_its_window(self):
        self.assertGreater(pixel(self.out, 275, 30, 30)[2], 200)
        self.assertLess(sum(pixel(self.out, 260, 30, 30)), 60)
        self.assertLess(sum(pixel(self.out, 305, 30, 30)), 60)


if __name__ == "__main__":
    unittest.main()
