"""Queued Explainer board clips: drawn in the background while the scenes are fetched; a render waits for a drawing still running."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from explainer.board import jobs as J


class BackgroundDraw(unittest.TestCase):
    def test_background_returns_at_once_and_render_waits(self):
        d = tempfile.mkdtemp()
        J.queue(d, [("a", 0.0, 0.3)], [{"out_path": str(Path(d) / "board_x.mp4")}])
        started, release = threading.Event(), threading.Event()

        def slow_run(words, jobs, log, n):
            started.set()
            release.wait(5)
            Path(jobs[0]["out_path"]).write_bytes(b"x")
            return 0

        with mock.patch.object(J, "run", side_effect=slow_run):
            t0 = time.time()
            self.assertEqual(J.ensure_built(d, background=True), 0)
            self.assertLess(time.time() - t0, 1.0)
            self.assertTrue(started.wait(5))
            done = []
            th = threading.Thread(target=lambda: done.append(J.ensure_built(d)))
            th.start()
            time.sleep(0.3)
            self.assertEqual(done, [])               # the render's call is waiting for the background drawing
            release.set()
            th.join(5)
        self.assertEqual(done, [0])
        self.assertTrue((Path(d) / "board_x.mp4").is_file())
        self.assertTrue((Path(d) / J.PENDING).is_file())       # kept: the next render checks the clips again and redraws a broken one

    def test_a_clip_cut_off_half_way_is_not_finished(self):
        d = tempfile.mkdtemp()
        cut = Path(d) / "cut.mp4"
        cut.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 5000)       # an MP4 with no index: ffmpeg was stopped
        self.assertFalse(J.clip_ok(cut))
        whole = Path(d) / "whole.mov"
        whole.write_bytes(b"\x00" * 5000 + b"\x00\x00\x01\x00moov" + b"\x00" * 200)
        self.assertTrue(J.clip_ok(whole))
        self.assertFalse(J.clip_ok(Path(d) / "missing.mp4"))

    def test_no_queue_is_nothing(self):
        self.assertEqual(J.ensure_built(tempfile.mkdtemp()), 0)


if __name__ == "__main__":
    unittest.main()
