"""Rep Theory / Carl Jung frames on every CPU core (reptheory/parallel_draw.py): same video as one process, Stop still works."""
from __future__ import annotations
import os, re, subprocess, tempfile, unittest
from pathlib import Path
from unittest import mock

from reptheory import engine, parallel_draw as PD


def S(text, a, b): return {"text": text, "start": a, "end": b}
SENTS = [S("Carl Jung said the shadow is the part of us we refuse to see.", 0, 4), S("He wrote that what you resist, persists.", 4, 8), S("So the work is to meet it, not to fight it.", 8, 12)]


def _vo(d, secs):
    p = str(Path(d) / "v.wav"); subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}", "-ar", "24000", "-ac", "1", p], check=True); return p


class Split(unittest.TestCase):
    def test_chunks_cover_every_frame_once_in_order(self):
        for n_frames, w in ((903, 3), (43200, 7), (241, 12), (5, 4)):
            c = PD.chunks(n_frames, w)
            self.assertEqual(c[0][0], 0); self.assertEqual(c[-1][1], n_frames)
            self.assertTrue(all(a < b for a, b in c)); self.assertTrue(all(c[i][1] == c[i + 1][0] for i in range(len(c) - 1)))

    def test_short_video_or_env_one_stays_in_one_process(self):
        with mock.patch.dict(os.environ, {PD.ENV: ""}): self.assertEqual(PD.workers(100), 1)
        with mock.patch.dict(os.environ, {PD.ENV: "1"}): self.assertEqual(PD.workers(10 ** 6), 1)
        with mock.patch.dict(os.environ, {PD.ENV: "3"}): self.assertEqual(PD.workers(10), 3)

    def test_scene_at_matches_the_old_walk(self):
        starts = [0, 0, 10, 10, 25, 40]; n = 5
        cur = 0
        for f in range(40):
            while cur + 1 < n and f >= starts[cur + 1]: cur += 1
            self.assertEqual(engine.scene_at(starts, f, n), cur, f)


class Render(unittest.TestCase):
    def _frames(self, p):
        return int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())

    def test_parallel_video_matches_one_process(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(PD, "MIN_CHUNK", 60):
            vo = _vo(d, 12)
            with mock.patch.dict(os.environ, {PD.ENV: "1"}): one = engine.run_rep_theory(d, SENTS, vo, str(Path(d) / "one.mp4"), quality="preview", theme="jung", sound=False, write_report=False)
            logs = []
            with mock.patch.dict(os.environ, {PD.ENV: "2"}): two = engine.run_rep_theory(d, SENTS, vo, str(Path(d) / "two.mp4"), quality="preview", theme="jung", sound=False, write_report=False, log=logs.append)
            self.assertTrue(any("CPU cores" in m for m in logs), logs)
            self.assertEqual(one["frames"], two["frames"]); self.assertEqual(self._frames(one["out"]), self._frames(two["out"]))
            r = subprocess.run(["ffmpeg", "-i", one["out"], "-i", two["out"], "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-"], capture_output=True, text=True).stderr
            self.assertGreater(float(re.search(r"min:([\d.]+|inf)", r).group(1).replace("inf", "99")), 35.0, r[-300:])      # only encoder noise, never another picture
            self.assertFalse(list(Path(d).glob("*.frames")))      # the stretch files are gone

    def test_stop_while_workers_draw(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(PD, "MIN_CHUNK", 60), mock.patch.dict(os.environ, {PD.ENV: "2"}):
            seen = []
            def prog(k, m):
                if "cores" in m: seen.append(m)
            with self.assertRaises(engine.Cancelled):
                engine.run_rep_theory(d, SENTS, _vo(d, 12), str(Path(d) / "o.mp4"), quality="preview", theme="jung", sound=False, write_report=False, progress_cb=prog, cancel_check=lambda: bool(seen))
            self.assertFalse(Path(d, "o.mp4").exists()); self.assertFalse(list(Path(d).glob("*.frames")))


if __name__ == "__main__":
    unittest.main()
