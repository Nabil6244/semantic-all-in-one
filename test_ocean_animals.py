"""Ocean style step 2: code-drawn animals (docs/ocean/PATTERNS.md section 7, step 2)."""

import unittest

from PIL import ImageChops, ImageStat

from ocean import animals as A
from ocean import stage as OS


def _diff(a, b):
    if a.size != b.size:
        return 999.0
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean)


def _cover(img):
    return ImageStat.Stat(img.getchannel("A")).mean[0] / 255.0


class AnimalsTest(unittest.TestCase):
    def test_every_animal_draws_at_its_width_with_a_real_shape(self):
        for name in A.NAMES:
            img = A.draw(name, 300)
            self.assertEqual(img.mode, "RGBA", name)
            self.assertTrue(abs(img.width - 300) <= 20, f"{name} width {img.width}")
            self.assertTrue(0.08 < _cover(img) < 0.95, f"{name} coverage {_cover(img):.2f}")

    def test_swimmers_move_between_phases_and_props_do_not(self):
        for name in A.SWIMMERS:
            self.assertGreater(_diff(A.draw(name, 260, 0), A.draw(name, 260, 2)), 0.05, name)
        for name in ("boat", "cage", "tooth"):
            self.assertEqual(_diff(A.draw(name, 260, 0), A.draw(name, 260, 2)), 0, name)

    def test_face_left_is_a_mirror(self):
        r, l = A.draw("orca", 240), A.draw("orca", 240, face="left")
        self.assertEqual(_diff(r.transpose(0), l), 0)

    def test_silhouette_is_dark_and_unknown_names_draw_one(self):
        s = A.draw("great_white", 240, silhouette=True)
        self.assertLess(ImageStat.Stat(s.convert("RGB"), mask=s.getchannel("A")).mean[0], 30)
        self.assertGreater(_cover(A.draw("leviathan", 240)), 0.08)

    def test_jaw_and_options_change_the_drawing(self):
        self.assertGreater(_diff(A.draw("great_white", 260), A.draw("great_white", 260, jaw=True)), 0.05)
        self.assertGreater(_diff(A.draw("squid", 260), A.draw("squid", 260, color=[230, 150, 120])), 0.05)
        self.assertGreater(_diff(A.draw("megalodon", 260), A.draw("megalodon", 260, eye="red")), 0.001)

    def test_phase_cycles_and_differs_per_element(self):
        self.assertTrue(all(0 <= A.phase_at("orca", t / 10) < A.PHASES for t in range(100)))
        self.assertNotEqual({A.phase_at("seal", t / 10, "a") for t in range(30)}, {0})


class StageAnimalTest(unittest.TestCase):
    def test_animals_swim_on_the_ocean_stage(self):
        st = OS.OceanStage()
        st.set(0.0, "open_water")
        st.add("animal", 0.0, {"name": "great_white", "width": 520}, pos=(640, 380), enter="none")
        p = st.params()
        e = p["elements"][0]
        self.assertFalse(e["edge"])
        a, b = OS.lay_ocean(1.0, 10, p), OS.lay_ocean(1.5, 10, p)
        bare = OS.lay_ocean(1.0, 10, dict(p, elements=[]))
        self.assertGreater(_diff(a.convert("RGB"), bare.convert("RGB")), 1.0)
        self.assertGreater(_diff(a.convert("RGB"), b.convert("RGB")), 0.05)


if __name__ == "__main__":
    unittest.main()
