"""Phase 2: the narrator and the board cards stand in front of a Flow picture of the story's place and period instead of paper. The board is drawn see-through (once on black, once on
white; the difference is the transparency), the plan shows the picture, and the finishing step lays every board over its picture in a few passes."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from explainer.beats import overlay as OV
from explainer.board import render as R
from explainer.director import plan as PL
from explainer.director import select as SL
from test_explainer_transcript_places import STORY, timed, beat


def drawn(bg):
    im = Image.new("RGB", (200, 120), bg)
    d = ImageDraw.Draw(im)
    d.ellipse([20, 20, 90, 90], fill=(200, 40, 40))
    d.text((100, 50), "Venice", fill=(20, 20, 20))
    return im


class Matte(unittest.TestCase):
    def test_black_and_white_give_back_the_drawing_over_any_picture(self):
        rgba = R.matte_rgba(drawn((0, 0, 0)), drawn((255, 255, 255)), glow=False)
        grey = Image.new("RGBA", (200, 120), (90, 140, 200, 255))
        grey.alpha_composite(rgba)
        want = drawn((90, 140, 200))
        diff = max(abs(a - b) for pa, pb in zip(grey.convert("RGB").getdata(), want.getdata()) for a, b in zip(pa, pb))
        self.assertLessEqual(diff, 3)

    def test_empty_frame_is_fully_transparent_and_glow_sits_under_drawn_parts(self):
        blank = R.matte_rgba(Image.new("RGB", (64, 64), (0, 0, 0)), Image.new("RGB", (64, 64), (255, 255, 255)))
        self.assertEqual(blank.getextrema()[3], (0, 0))
        rgba = R.matte_rgba(drawn((0, 0, 0)), drawn((255, 255, 255)), glow=True)
        self.assertGreater(rgba.getpixel((95, 55))[3], 100)       # just beside the circle: the paper glow
        self.assertLess(rgba.getpixel((199, 0))[3], 10)            # far corner: the picture shows (a trace of the feathered edge at most)


class Plates(unittest.TestCase):
    def setUp(self):
        self.words = timed("venice grew rich . venice built ships . venice traded silk . venice ruled the sea . in 1204 venice sailed .")
        ends = [i + 1 for i, w in enumerate(self.words) if w[0] == "."]
        self.beats = [beat(f"e{k + 1}", self.words, a, b, ["Venice"]) for k, (a, b) in enumerate(zip([0] + ends[:-1], ends))]

    def test_a_plate_is_kept_for_a_short_run_then_the_framing_changes(self):
        st = {}
        ps = [PL.backdrop_prompt(self.beats, k, self.words, "Venice", st) for k in range(4)]
        self.assertEqual(ps[0], ps[1])
        self.assertNotEqual(ps[1], ps[2])
        self.assertTrue(all("Venice" in p and "no people" in p for p in ps))

    def test_a_new_period_gets_a_new_plate(self):
        st = {}
        ps = [PL.backdrop_prompt(self.beats, k, self.words, "Venice", st) for k in range(5)]
        self.assertIn("1204", ps[4])
        self.assertNotIn(ps[4], ps[:4])

    def test_a_topic_with_no_setting_keeps_paper(self):
        words = timed("prices rose because demand was strong .")
        b = beat("e1", words, 0, len(words))
        self.assertEqual(PL.backdrop_prompt([b], 0, words, "", {}), "")


class Director(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from explainer.director.options import DirectorOptions
        words = timed(STORY, step=0.42)
        cls.on = PL.direct(words, None, DirectorOptions(scene_intel=True, pictures=True, flow_only=True, scene_flow_share=1.0, footage_source="flow_image", flow_backdrops=True), materialize=False)
        cls.off = PL.direct(words, None, DirectorOptions(scene_intel=True, pictures=True), materialize=False)

    def test_board_beats_show_a_flow_picture_and_record_their_overlay(self):
        ovs = {k: v["board_overlay"] for k, v in self.on.report["beat_details"].items() if v.get("board_overlay")}
        self.assertTrue(ovs)
        beats = {b["id"]: b for b in self.on.plan["beats"]}
        for bid, ov in ovs.items():
            self.assertTrue(ov["mov"].endswith(".mov"))
            self.assertTrue(beats[bid]["footage"]["clips"][0]["asset"].startswith("flow_image:"))

    def test_off_means_paper_boards_as_before(self):
        self.assertFalse([k for k, v in self.off.report["beat_details"].items() if v.get("board_overlay")])
        self.assertNotIn("flow_backdrops", self.off.report["options"])

    def test_the_app_turns_it_on_by_default(self):
        from explainer import integration as IT
        self.assertTrue(IT._flag(IT.full_look({}), "explainer_flow_backdrops"))


class Finishing(unittest.TestCase):
    def test_several_boards_are_laid_on_in_one_pass_at_their_times(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=3:r=30", "-pix_fmt", "yuv420p", str(d / "v.mp4")], check=True)
            movs = []
            for k, colour in enumerate(("red", "yellow")):
                m = d / f"o{k}.mov"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}@1.0:s=320x180:d=0.8:r=30,format=argb", "-c:v", "qtrle", str(m)], check=True)
                movs.append((m, 0.5 + 1.2 * k))
            self.assertEqual(OV.probe_size(d / "v.mp4"), (320, 180))
            self.assertEqual(OV.composite_many(d / "v.mp4", movs, d / "out.mp4", per_pass=1), 0)

            def px(t):
                raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(d / "out.mp4"), "-frames:v", "1", "-vf", "crop=2:2:160:90", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     capture_output=True, check=True).stdout
                return tuple(raw[:3])
            self.assertGreater(px(0.2)[2], 150)          # blue before the first board
            self.assertGreater(px(0.9)[0], 150)          # red board
            self.assertGreater(px(2.0)[1], 150)          # yellow board
            self.assertGreater(px(2.8)[2], 150)          # blue again after it


if __name__ == "__main__":
    unittest.main()
