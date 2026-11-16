"""Wall Moments engine (wall/engine.py, wall/frames.py, wall/facts.py, wall/sfx.py): docs/wall/PLAN.md Phase 1."""

import math
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from wall import engine as E
from wall import facts as FA
from wall import frames as FR
from wall import sfx as SX


def _clip(folder: Path, colour: str = "red", seconds: float = 2.0) -> str:
    p = folder / f"{colour}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=640x360:r=25:d={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True, timeout=60)
    return str(p)


def _params(clip=None, work=None):
    vid = {"id": "e", "type": "video", "x": 0, "y": 0, "w": 900, "t_in": -1,
           "clip": {"path": clip, "seek": 0.0, "t0": 0.0, "a": 0.0, "b": 2.0, "res": [320, 180]}}
    return {"theme": "slate", "dur": 6.0, "work": work, "items": [
        vid,
        {"type": "counter", "x": 1400, "y": 0, "size": 120, "value": 44.9, "t_in": 2.0, "t_land": 3.0,
         "fmt": {"dec": 1, "suf": "%"}, "caption": "of tap"},
        {"type": "stamp", "text": "no majority", "x": 1500, "y": 200, "size": 64, "rot": 8, "t_in": 3.5},
        {"type": "string", "a": [450, 0], "b": [1150, 0], "t_in": 1.6},
        {"type": "pen", "cx": 1400, "cy": 40, "rx": 300, "ry": 100, "t_in": 3.2},
        {"type": "note", "text": "≈ €1.2 BN", "x": 1400, "y": 300, "size": 40, "t_in": 4.0}],
        "cam": [{"t": 0, "fs": "e", "edge": True}, {"t": 0.2, "fs": "e", "edge": True}, {"t": 1.4, "x": 300, "y": 20, "z": 0.8},
                {"t": 2.4, "x": 1400, "y": 40, "z": 0.95}, {"t": 4.0, "x": 1450, "y": 120, "z": 0.9},
                {"t": 5.2, "fs": "e"}, {"t": 6.0, "fs": "e", "edge": True}]}


class SplineTest(unittest.TestCase):
    def test_monotone_never_overshoots(self):
        rnd = random.Random(4)
        for _ in range(30):
            keys, t = [], 0.0
            for _k in range(6):
                t += rnd.uniform(0.2, 2.0)
                keys.append((t, rnd.choice([rnd.uniform(-500, 500), keys[-1][1] if keys else 0.0])))
            sp = E.Spline(keys)
            for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
                lo, hi = min(v0, v1), max(v0, v1)
                for i in range(1, 20):
                    v = sp(t0 + (t1 - t0) * i / 20)
                    self.assertGreaterEqual(v, lo - 1e-6)
                    self.assertLessEqual(v, hi + 1e-6)

    def test_equal_keys_hold(self):
        sp = E.Spline([(0, 5), (1, 5), (2, 9)])
        self.assertAlmostEqual(sp(0.5), 5.0)


class ClampTest(unittest.TestCase):
    def test_full_screen_never_shows_the_border(self):
        p = _params()
        p["items"].append({"type": "stamp", "text": "x", "x": 0, "y": 0, "size": 60, "t_in": 5.5})      # a shake while full screen
        w = E.Wall(p)
        v = w.by_id["e"]
        for i in range(0, 601):
            t = i / 100
            x, y, z, r = w.cam(t)
            if z >= w.fill_zoom(v, True) - 1e-9:                      # the clip fills the frame
                hw, hh = E.W / 2 / z, E.H / 2 / z
                self.assertGreaterEqual(x - hw, v.x - v.w / 2 - 1e-6, t)
                self.assertLessEqual(x + hw, v.x + v.w / 2 + 1e-6, t)
                self.assertGreaterEqual(y - hh, v.y - v.h / 2 - 1e-6, t)
                self.assertLessEqual(y + hh, v.y + v.h / 2 + 1e-6, t)
                self.assertEqual(r, 0.0)

    def test_hand_off_frame_is_all_footage(self):
        td = Path(tempfile.mkdtemp())
        try:
            w = E.Wall(_params(_clip(td), str(td / "frames")))
            for t in (0.0, 6.0):
                im = w.render(t).convert("RGB")
                for xy in ((0, 0), (E.W - 1, 0), (0, E.H - 1), (E.W - 1, E.H - 1), (E.W // 2, E.H // 2)):
                    r, g, b = im.getpixel(xy)
                    self.assertGreater(r, 180, (t, xy))
                    self.assertLess(g, 80, (t, xy))
        finally:
            FR.forget()
            shutil.rmtree(td, ignore_errors=True)


class SharedRendererTest(unittest.TestCase):
    def test_wall_layer_through_the_chunked_renderer(self):
        """The wall as a layer of cinematic_explainer.render: the first frame is the clip full screen, a mid frame is the wall."""
        from cinematic_explainer.render import Layer, Shot, render
        td = Path(tempfile.mkdtemp())
        try:
            black = _clip(td, "black", 3.0)
            p = _params(_clip(td, "red"), str(td / "frames"))
            p["dur"] = 2.0
            p["cam"] = [{"t": 0, "fs": "e", "edge": True}, {"t": 0.2, "fs": "e", "edge": True}, {"t": 1.2, "x": 300, "y": 20, "z": 0.6},
                        {"t": 2.0, "x": 300, "y": 20, "z": 0.6}]
            out = td / "o.mp4"
            render([Shot(black, 0.0, 2.0)], [Layer("wall.lay_wall", 0.0, 2.0, p)], str(out), card_table=E.CARDS)
            for t, red in ((0.0, True), (1.8, False)):
                raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1", "-vf", "crop=2:2:0:0",
                                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                self.assertEqual(raw[0] > 150 and raw[1] < 90, red, (t, raw[:3]))
        finally:
            FR.forget()
            shutil.rmtree(td, ignore_errors=True)


class ItemsTest(unittest.TestCase):
    def test_counter_lands_on_its_word(self):
        w = E.Wall(_params())
        ctr = next(i for i in w.items if isinstance(i, E.Counter))
        self.assertEqual(ctr.state(ctr.t_land)[0][1], 40)
        self.assertEqual(ctr.text_at(40), "44.9%")
        self.assertLess(ctr.state(ctr.t_land - 0.3)[0][1], 40)
        self.assertIn((3.0, "impact"), w.cues())

    def test_layer_size_and_registration(self):
        im = E.lay_wall(2.5, 6.0, _params())
        self.assertEqual((im.mode, im.size), ("RGBA", (1280, 720)))
        self.assertIsNone(E.lay_wall(7.0, 6.0, _params()))
        self.assertIs(E.CARDS["wall.lay_wall"], E.lay_wall)

    def test_same_params_same_frame(self):
        for t in (1.0, 2.7, 3.6, 4.4):
            self.assertEqual(E.Wall(_params()).render(t).tobytes(), E.Wall(_params()).render(t).tobytes(), t)

    def test_cues_cover_every_item(self):
        names = {n.split(":")[0] for _t, n in E.Wall(_params()).cues()}
        self.assertTrue({"ticks", "impact", "stamp", "slide", "marker", "pencil"} <= names, names)

    def test_pingpong_never_freezes(self):
        seq = [FR.pingpong(i, 5) for i in range(12)]
        self.assertEqual(seq, [0, 1, 2, 3, 4, 3, 2, 1, 0, 1, 2, 3])
        self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])))


class FactsTest(unittest.TestCase):
    TEXT = "The winner was Lufthansa, and the price was 1.025 billion euros for 44.9 percent of TAP, a sum that climbs to about 1.2 billion euros."

    def test_money_percent_approx(self):
        fs = FA.facts(self.TEXT)
        self.assertEqual([f.kind for f in fs], ["money", "percent", "approx"])
        self.assertEqual(E.fmt_value(fs[0].value, fs[0].fmt), "€1.025 BN")
        self.assertEqual(fs[0].caption, "THE PRICE")
        self.assertEqual((fs[1].caption, fs[1].text), ("OF TAP", "of"))
        self.assertEqual(fs[2].text, "≈ €1.2 BN")

    def test_verdicts_twists_dates_and_spelled_numbers(self):
        self.assertEqual(FA.facts("And the buyer will not even own a majority.")[0].text, "NO MAJORITY")
        self.assertEqual(FA.facts("Here is the strange part.")[0].kind, "twist")
        self.assertEqual(FA.facts("On the fourteenth of October 2026, the cabinet met.")[0].text, "14 OCTOBER 2026")
        self.assertEqual(FA.facts("TAP lost 99.2 million euros, 40 percent more than a year earlier.")[1].text, "+40% MORE")
        self.assertEqual(FA.facts("It flew four billion miles.")[0].fmt["suf"], " BN")
        self.assertEqual(FA.facts("Its first aircraft were Douglas DC-3s."), [])

    def test_a_date_without_a_year_is_one_date(self):
        """War render 2026-11-16: 'On November 7 power failed' pinned a count 7 labelled POWER FAILED IN CENTRAL."""
        fs = FA.facts("On November 7 power failed in central Kyiv, and nearly 250,000 customers lost it.")
        self.assertEqual((fs[0].kind, fs[0].text), ("date", "7 NOVEMBER"))
        self.assertNotIn(("count", 7.0), [(f.kind, getattr(f, "value", None)) for f in fs])
        self.assertEqual([f.text for f in FA.facts("Drones came on November 3, 310 on November 4.") if f.kind == "date"],
                         ["3 NOVEMBER", "4 NOVEMBER"])
        self.assertFalse([f for f in FA.facts("It may 4 times; 4 may be enough.") if f.kind == "date"])

    def test_timer_matches_whisper_numbers(self):
        words = [("the", 8.2, 8.3), ("price", 8.3, 8.6), ("was", 8.6, 8.8), ("1", 8.8, 9.1), ("25", 9.1, 10.3), ("billion", 10.3, 10.7),
                 ("for", 10.7, 11.7), ("44", 11.7, 12.2), ("9", 12.2, 13.2), ("of", 13.2, 13.4), ("tap", 13.4, 14.1)]
        text = "the price was 1.025 billion euros for 44.9 percent of TAP"
        tm = FA.Timer(text, 8.2, 14.1, words)
        fs = FA.facts(text)
        self.assertAlmostEqual(tm.at(fs[0].start), 8.8, places=2)
        self.assertAlmostEqual(tm.at(text.index("of TAP")), 13.2, places=2)


class SfxTest(unittest.TestCase):
    def test_every_cue_has_a_file(self):
        d = SX.ensure()
        for cue in ("drop", "pop", "slide", "marker", "pencil", "impact", "stamp", "boom", "type", "whoosh", "ticks:1.3", "ticks:9"):
            self.assertTrue(SX.file_for(cue).is_file(), cue)
            self.assertIn(SX.base(cue), SX.KIND)
        self.assertEqual(SX.file_for("ticks:1.3").name, "ticks_15.wav")
        self.assertTrue(str(d).endswith(str(Path("bundled-sfx") / "wall")))


if __name__ == "__main__":
    unittest.main()
