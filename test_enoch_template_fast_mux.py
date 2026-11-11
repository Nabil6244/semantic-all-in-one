"""Enoch Template fast final join: only clips around a soft transition are re-encoded, hard cuts keep full length."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import video_generator as vg
from ancient_texts import fast_mux


class Groups(unittest.TestCase):
    def test_groups_follow_transitions(self):
        t = [None, ("fade", 0.5, ""), ("fade", 0.5, ""), None, None]
        self.assertEqual(fast_mux.transition_groups(t), [[0], [1, 2, 3], [4], [5]])

    def test_no_transitions_is_one_clip_per_group(self):
        self.assertEqual(fast_mux.transition_groups([None, None]), [[0], [1], [2]])

    def test_applied_restores_the_mux(self):
        orig = vg.run_final_mux
        with fast_mux.applied(vg, log=lambda s: None):
            self.assertIsNot(vg.run_final_mux, orig)
        self.assertIs(vg.run_final_mux, orig)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg needed")
class RealJoin(unittest.TestCase):
    def test_join_length_and_fallback_free(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            clips = []
            for i in range(5):
                p = d / f"c{i}.mp4"
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=2",
                                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p)], check=True)
                clips.append(p)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=12", str(d / "a.wav")], check=True)
            lst = d / "concat.txt"
            vg.write_ffmpeg_concat_list(clips, lst)
            logs = []
            calls = []
            orig = vg.run_final_mux

            def spy(**kw):
                calls.append(kw)
                return orig(**kw)

            out = d / "out.mp4"
            fast_mux.fast_final_mux(vg, spy, concat_list_path=lst, audio_path=d / "a.wav", output_path=out,
                                    clip_files=clips, scene_numbers=None,
                                    transitions=[None, ("fade", 0.5, ""), None, None], clip_durations=[2.0] * 5,
                                    log=logs.append)
            self.assertIsNone(calls[-1]["transitions"])          # final pass is the stream-copy mux
            self.assertEqual(len(calls[-1]["clip_files"]), 4)    # clips 1+2 joined into one segment
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        str(out)], capture_output=True, text=True).stdout)
            self.assertAlmostEqual(dur, 9.5, delta=0.1)           # 10 s minus the one 0.5 s overlap, cuts lose nothing
            self.assertIn("Fast join", logs[0])


if __name__ == "__main__":
    unittest.main()
