"""The channel name is laid over the finished Hybrid video (hybrid.generate.add_watermark), not drawn by the page on every frame, so
the renderer can copy footage-only frames straight from their clips (pakmap-engine/lib/footage_pass.mjs). Approved by the owner
2026-10-15."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image


def video(path: Path, seconds: float = 3.0):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:size=640x360:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
                   check=True)


class LateWatermark(unittest.TestCase):
    def test_the_name_sits_bottom_right_like_the_page_draws_it(self):
        from hybrid.generate import watermark_png

        tmp = Path(tempfile.mkdtemp())
        img = Image.open(watermark_png({"text": "My Channel"}, (1920, 1080), tmp / "wm.png"))
        box = img.split()[3].getbbox()
        self.assertIsNotNone(box)
        self.assertGreater(box[0], 1300)                      # right side
        self.assertLessEqual(1080 - box[3], 50)              # 36 px from the bottom (plus descent)
        self.assertLess(max(img.split()[3].getdata()), 200)   # 60 % opacity

    def test_it_is_laid_over_the_finished_video_and_the_sound_is_kept(self):
        from hybrid.generate import add_watermark

        tmp = Path(tempfile.mkdtemp())
        video(tmp / "v.mp4")
        self.assertEqual(add_watermark(tmp / "v.mp4", {"text": "My Channel"}, tmp), "")
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json",
                                          str(tmp / "v.mp4")], capture_output=True, text=True).stdout)
        self.assertEqual(sorted(s["codec_type"] for s in info["streams"]), ["audio", "video"])
        self.assertAlmostEqual(float(info["format"]["duration"]), 3.0, delta=0.15)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(tmp / "v.mp4"), "-frames:v", "1", str(tmp / "f.png")], check=True)
        frame = Image.open(tmp / "f.png").convert("L")
        self.assertGreater(max(frame.crop((400, 300, 640, 360)).getdata()), 60)   # the name is there, bottom right

    def test_the_renderer_never_gets_the_watermark(self):
        import hybrid.generate as G
        from hybrid.plan import Beat, CameraStep, HybridPlan
        from pakmap.app_integration import PakmapResult

        tmp = Path(tempfile.mkdtemp())
        video(tmp / "vo.mp4")
        plan = HybridPlan(duration=3.0, beats=[Beat("b1", "map", 0.0, 3.0, camera=[CameraStep("start", "Texas", "region", 0.0)])])
        seen = {}

        def fake(csv_path, vo, out, **kw):
            seen["wm"] = kw.get("watermark")
            video(Path(out))
            return PakmapResult(True, output_path=Path(out))

        with mock.patch.object(G, "generate_pakmap_video", side_effect=fake):
            res = G.generate_hybrid_video(plan, tmp / "vo.mp4", tmp / "out.mp4", work_dir=tmp / "w", whisper_words=[("x", 0.0, 0.2)],
                                          watermark={"text": "My Channel"}, log=lambda m: None)
        self.assertTrue(res.ok)
        self.assertIsNone(seen["wm"])   # footage frames can skip the page


if __name__ == "__main__":
    unittest.main()
