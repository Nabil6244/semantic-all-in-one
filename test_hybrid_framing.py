"""Hybrid framing: a small place is framed as itself (not as the country around it), and text stays off the place being discussed."""
import unittest

from hybrid.compile import _focus_box, clear_anchor
from hybrid.geo import resolve
from hybrid.local_fix import _tighten_camera
from hybrid.plan import Beat, CameraStep, Layer
from hybrid.validate import focus_extent_km, view_width_km


class Framing(unittest.TestCase):
    def test_uk_regions_resolve(self):
        for name in ("South West England", "West Country", "Cornwall and Devon", "Britain", "Yorkshire", "Cornwall;Devon"):
            self.assertTrue(resolve(name, "area").is_area, name)

    def test_union_is_one_tight_view(self):
        self.assertLess(view_width_km(resolve("Cornwall;Devon"), "region"), 600)
        self.assertGreater(view_width_km(resolve("England"), "region"), 2000)

    def test_england_camera_is_tightened_to_the_places_shown(self):
        b = Beat(id="b1", mode="map", start=0, end=10)
        b.layers = [Layer(id="l1", type="fill", t=0.0, place="Cornwall"), Layer(id="l2", type="fill", t=0.0, place="Devon")]
        b.camera = [CameraStep(action="start", place="England", frame="region", t=0.0)]
        msg = _tighten_camera(b)
        self.assertIn("tightened", msg)
        self.assertEqual(b.camera[0].place, "Cornwall;Devon")

    def test_text_moves_off_the_focus_place(self):
        b = Beat(id="b1", mode="map", start=0, end=10)
        b.layers = [Layer(id="l1", type="fill", t=0.0, place="Cornwall")]
        low = (0.3, 0.7, 0.8, 0.98)   # the place sits where a caption is drawn
        self.assertNotEqual(clear_anchor("bc", low, "caption"), "bc")
        self.assertEqual(clear_anchor("bc", _focus_box(None, b, ("Cornwall", "region")), "caption"), "bc")
        self.assertEqual(clear_anchor("br", _focus_box(None, b, ("England", "region")), "stat"), "br")


if __name__ == "__main__":
    unittest.main()
