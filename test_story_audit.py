"""Tests for story_audit: tiny ffmpeg-made clips (480x270), a few seconds each. Run: python3 -m unittest test_story_audit -v"""
import subprocess
import tempfile
import unittest
from pathlib import Path

import story_audit as sa


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", *args], check=True, timeout=120)


class AuditVideos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast"]
        # a still picture with grain and dust (noise) and a slow 10% zoom, 8 s
        cls.still = d / "still.mp4"
        _ff("-f", "lavfi", "-i", "gradients=s=480x270:r=30:d=1:c0=0x203060:c1=0xe0b080:x0=0:y0=0:x1=480:y1=270,drawbox=x=100:y=60:w=200:h=120:color=black@0.5:t=fill,boxblur=10", "-frames:v", "1", str(d / "pic.png"))
        _ff("-loop", "1", "-i", str(d / "pic.png"), "-t", "8", "-r", "30", "-vf",
            "scale=w='480*(1+0.1*t/8)':h=-2:eval=frame,crop=480:270,noise=alls=8:allf=t", *enc, str(cls.still))
        # a picture that really moves, 8 s
        cls.moving = d / "moving.mp4"
        _ff("-f", "lavfi", "-i", "color=c=0x3050a0:s=480x270:r=30:d=8", "-f", "lavfi", "-i", "color=c=white:s=120x150:r=30:d=8",
            "-filter_complex", "[0][1]overlay=x='mod(t*120,360)':y=60", *enc, str(cls.moving))
        # moving, with one white flash frame pair at 3 s and a slow fade to black at the end
        cls.flash = d / "flash.mp4"
        _ff("-f", "lavfi", "-i", "color=c=0x3050a0:s=480x270:r=30:d=6", "-f", "lavfi", "-i", "color=c=gray:s=120x150:r=30:d=6",
            "-filter_complex", "[0][1]overlay=x='mod(t*120,360)':y=60,drawbox=x=0:y=0:w=480:h=270:color=white:t=fill:enable='between(t,3,3.07)',fade=t=out:st=5:d=1",
            *enc, str(cls.flash))
        # a still half, then a moving half
        cls.half = d / "half.mp4"
        _ff("-i", str(cls.still), "-i", str(cls.moving), "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", *enc, str(cls.half))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_still_found_with_timestamps(self):
        sp = sa.still_stretches(self.still, min_len=3.0)
        self.assertEqual(len(sp), 1)
        self.assertGreaterEqual(sp[0]["length"], 6.5)
        self.assertLess(sp[0]["start"], 1.0)

    def test_moving_has_no_still(self):
        self.assertEqual(sa.still_stretches(self.moving, min_len=3.0), [])

    def test_still_then_moving_stops_at_the_change(self):
        sp = sa.still_stretches(self.half, min_len=3.0)
        self.assertEqual(len(sp), 1)
        self.assertLess(sp[0]["end"], 8.8)

    def test_flash_detected_but_not_a_fade(self):
        fl = sa.flash_frames(self.flash)
        self.assertEqual(len(fl), 1, fl)
        self.assertAlmostEqual(fl[0]["t"], 3.0, delta=0.15)
        self.assertEqual(fl[0]["kind"], "white")
        self.assertEqual(sa.flash_frames(self.moving), [])

    def test_sheets(self):
        out = Path(self.tmp.name) / "cs.png"
        self.assertTrue(Path(sa.contact_sheet(self.moving, 2.0, out)).is_file())
        self.assertTrue(Path(sa.cut_sheets(self.half, [8.0], Path(self.tmp.name) / "cuts.png")).is_file())

    def test_audit_all_pass_and_fail(self):
        r = sa.audit_all(self.moving, print_fn=None)
        self.assertTrue(r["ok"], r["checks"])
        r = sa.audit_all(self.still, print_fn=None)
        self.assertFalse(r["ok"])
        self.assertEqual(r["checks"][0]["check"], "still stretches")


class AuditData(unittest.TestCase):
    def test_variety(self):
        shots = [{"shot_id": f"s{i}", "start": i * 4.0, "end": i * 4.0 + (4.0 if i != 3 else 7.5), "transition_in": "dissolve" if i in (1, 2, 3, 4) else "cut",
                  "motion_tier": 0 if i % 3 == 0 else 2, "character": "fox" if i < 3 else ("owl" if i == 3 else "")} for i in range(6)]
        v = sa.variety_report({"shots": shots, "protagonist": "fox"})
        self.assertEqual(v["shots"], 6)
        self.assertEqual(v["max_len_s"], 7.5)
        self.assertEqual(v["over_max"][0][0], "s3")
        self.assertEqual(v["max_transition_run"], 4)
        self.assertEqual(v["tier_mix"], {"0": 2, "2": 4})
        self.assertEqual(v["character_switches"], 1)
        self.assertEqual(v["with_character"], 4)

    def test_sync_hindi_spelling_tolerant(self):
        aligned = [{"scene_number": "1", "script_segment": "आज रात Amazon के ऑर्डर का ट्रैकिंग पेज", "start_time": 0.0, "end_time": 4.0},
                   {"scene_number": "2", "script_segment": "आपको एक बिंदु दिखाई देगा", "start_time": 4.0, "end_time": 8.0}]
        words = [["आज", 0.0, 0.4], ["रात", 0.5, 0.9], ["अमेज़न", 1.0, 1.4], ["के", 1.5, 1.6], ["ऑर्डर", 1.7, 2.2], ["का", 2.3, 2.4], ["ट्रकिन", 2.5, 3.0], ["पेज", 3.1, 3.5],
                 ["आपको", 4.1, 4.5], ["एक", 4.6, 4.8], ["बिंदु", 5.0, 5.4], ["दिखाई", 5.5, 6.0], ["देगा", 6.1, 6.5]]
        r = sa.sync_report(aligned, words)
        self.assertGreaterEqual(r["pct_inside"], 99.0)
        self.assertGreaterEqual(r["matched"], 10)
        # scene 2 pushed 5 s early: its words now sit in scene 1's window -> fails
        bad = [dict(aligned[0]), dict(aligned[1], start_time=0.0, end_time=2.0)]
        bad[0]["start_time"], bad[0]["end_time"] = 2.0, 8.0
        r2 = sa.sync_report(bad, words)
        self.assertLess(r2["pct_inside"], 90.0)

    def test_audit_all_plan_only(self):
        shots = [{"shot_id": i, "start": i * 3.0, "end": i * 3.0 + 3.0, "transition_in": "cut", "motion_tier": 2} for i in range(5)]
        r = sa.audit_all(plan={"shots": shots}, print_fn=None)
        self.assertTrue(r["ok"], r["checks"])


if __name__ == "__main__":
    unittest.main()
