"""Ocean style step 1: the sets and the ocean stage (docs/ocean/PATTERNS.md section 7, step 1)."""

import unittest

from PIL import Image, ImageChops, ImageStat

from ocean import backdrop as B
from ocean import stage as OS

SMALL = (320, 180)


def _spread(img):
    st = ImageStat.Stat(img.convert("L"))
    return st.stddev[0]


def _diff(a, b):
    return sum(ImageStat.Stat(ImageChops.difference(a.convert("RGB"), b.convert("RGB"))).mean)


class SetsTest(unittest.TestCase):
    def test_every_set_draws_full_frame_and_is_not_flat(self):
        for name in B.SETS:
            img = B.draw(name, 1.0, None, *SMALL)
            self.assertEqual(img.size, SMALL, name)
            self.assertEqual(img.mode, "RGBA", name)
            self.assertGreater(_spread(img), 3.0, f"{name} is a flat colour")

    def test_sets_look_different_from_each_other(self):
        imgs = {n: B.draw(n, 0.0, None, *SMALL) for n in B.SETS}
        for a in B.SETS:
            for b in B.SETS:
                if a < b:
                    self.assertGreater(_diff(imgs[a], imgs[b]), 1.0, f"{a} looks like {b}")

    def test_lit_sets_move_over_time(self):
        for name in ("open_water", "kelp", "abyss", "seafloor"):
            self.assertGreater(_diff(B.draw(name, 0.0, None, *SMALL), B.draw(name, 3.0, None, *SMALL)), 0.05, name)

    def test_unknown_set_falls_back_to_open_water(self):
        self.assertEqual(_diff(B.draw("nope", 2.0, None, *SMALL), B.draw("open_water", 2.0, None, *SMALL)), 0)

    def test_home_water_is_lighter_at_the_top(self):
        img = B.draw("open_water", 0.0, None, *SMALL).convert("L")
        top = ImageStat.Stat(img.crop((0, 0, SMALL[0], 30))).mean[0]
        bottom = ImageStat.Stat(img.crop((0, SMALL[1] - 30, SMALL[0], SMALL[1]))).mean[0]
        self.assertGreater(top, bottom + 10)

    def test_seafloor_has_sand_at_the_bottom(self):
        img = B.draw("seafloor", 0.0, None, *SMALL).convert("RGB")
        r, g, b = img.getpixel((SMALL[0] // 2, SMALL[1] - 25))
        self.assertGreater(r, b)

    def test_depth_marks_and_split_labels_change_the_picture(self):
        a = B.draw("depth_column", 0.0, {"marks": [[0, "surface"], [500, "500 m"]]}, *SMALL)
        b = B.draw("depth_column", 0.0, {"marks": [[0, "surface"], [6000, "6,000 m"]]}, *SMALL)
        self.assertGreater(_diff(a, b), 0.01)
        s = B.draw("split_columns", 0.0, {"left": {"label": "around antarctica"},
                                          "right": {"label": "everywhere else", "color": [236, 120, 40, 255]}}, *SMALL)
        self.assertGreater(_spread(s), 3.0)


class OceanStageTest(unittest.TestCase):
    def test_params_carry_sets_and_flat_elements(self):
        st = OS.OceanStage()
        st.set(0.0, "open_water")
        st.set(0.0, "open_water")                    # repeat ignored
        el = st.add("text", 0.5, {"text": "the food"})
        st.set(4.0, "seafloor")
        st.set(5.0, "bad_name")                      # unknown -> open_water
        p = st.params()
        self.assertEqual([s[1] for s in p["sets"]], ["open_water", "seafloor", "open_water"])
        e = [x for x in p["elements"] if x["id"] == el][0]
        self.assertFalse(e["edge"])
        self.assertTrue(e["args"]["_flat"])

    def test_no_sets_means_open_water(self):
        self.assertEqual(OS.OceanStage().params()["sets"][0][1], "open_water")

    def test_set_change_cross_fades(self):
        sets = [[0.0, "open_water", {}], [2.0, "abyss", {}]]
        cur, prev, k = OS.set_at(sets, 2.3)
        self.assertEqual((cur[1], prev[1]), ("abyss", "open_water"))
        self.assertTrue(0 < k < 1)
        self.assertEqual(OS.set_at(sets, 5.0)[2], 1.0)

    def test_lay_ocean_draws_world_and_elements(self):
        st = OS.OceanStage()
        st.set(0.0, "open_water")
        st.add("text", 0.0, {"text": "SHARK", "size": 120}, pos=(640, 360), enter="none")
        p = st.params()
        with_el = OS.lay_ocean(1.0, 10.0, p)
        bare = OS.lay_ocean(1.0, 10.0, dict(p, elements=[]))
        self.assertEqual(with_el.size, (OS.W, OS.H))
        self.assertGreater(_diff(with_el, bare), 0.1)

    def test_card_table_entry(self):
        self.assertIs(OS.CARDS["ocean.lay_ocean"], OS.lay_ocean)


if __name__ == "__main__":
    unittest.main()
