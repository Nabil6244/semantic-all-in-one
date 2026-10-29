"""Per-element motion (explainer/board/anim.py): pure functions of age; no motion spec = the old pixels."""
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from explainer.board import anim as A


def red_box(im, it, age, frame_no=0):
    ImageDraw.Draw(im).rectangle(it.rect, fill=(200, 30, 30))


def item(motion=None, rect=(400, 300, 600, 400)):
    return SimpleNamespace(rect=rect, bbox=rect, vparams={"motion": motion} if motion is not None else {})


def centroid(im):
    a = np.asarray(im).astype(int)
    m = (a[..., 0] > 150) & (a[..., 1] < 100)
    ys, xs = np.nonzero(m)
    return (xs.mean(), ys.mean(), m.sum()) if len(xs) else (None, None, 0)


class State(unittest.TestCase):
    def test_enter_slides_to_rest(self):
        spec = {"enter": {"from": "left", "dist": 200, "dur": 0.5}}
        self.assertAlmostEqual(A.state(spec, 0.0)[0], -200, places=3)
        self.assertAlmostEqual(A.state(spec, 0.5)[0], 0, places=3)
        self.assertAlmostEqual(A.state(spec, 5.0)[0], 0, places=3)

    def test_fade_scale_and_path(self):
        self.assertEqual(A.state({"fade": 0.4}, 0.0)[3], 0.0)
        self.assertEqual(A.state({"fade": 0.4}, 0.4)[3], 1.0)
        self.assertAlmostEqual(A.state({"scale": [0.5, 1.0, 0.4]}, 0.0)[2], 0.5)
        self.assertAlmostEqual(A.state({"scale": [0.5, 1.0, 0.4]}, 1.0)[2], 1.0)
        p = {"path": [{"t": 0, "x": 0}, {"t": 1, "x": 300, "ease": "linear"}]}
        self.assertAlmostEqual(A.state(p, 0.5)[0], 150, places=3)
        self.assertAlmostEqual(A.state(p, 9)[0], 300, places=3)

    def test_exit_and_emphasis(self):
        ex = {"exit": {"at": 2.0, "to": "right", "dist": 100, "dur": 0.5}}
        self.assertEqual(A.state(ex, 1.9)[3], 1.0)
        self.assertEqual(A.state(ex, 2.5)[3], 0.0)
        em = {"emphasis": {"at": 1.0, "kind": "pulse", "dur": 0.4, "amp": 0.1}}
        self.assertAlmostEqual(A.state(em, 1.2)[2], 1.1, places=3)
        self.assertEqual(A.state(em, 2.0)[2], 1.0)

    def test_deterministic_and_layers(self):
        spec = {"enter": {"from": "top"}, "emphasis": {"at": 0.3, "kind": "shake"}, "parallax": 0.5, "layer": "fg"}
        self.assertEqual(A.state(spec, 0.77), A.state(spec, 0.77))
        self.assertLess(A.layer_of({"motion": {"layer": "bg"}}), A.layer_of({"motion": {"layer": "fg"}}))
        self.assertEqual(A.layer_of({}), 1)
        self.assertFalse(A.has_motion(None))
        self.assertTrue(A.has_motion({"motion": {"fade": 1}}))


class Draw(unittest.TestCase):
    def _frame(self, it, age):
        im = Image.new("RGB", (1000, 700), (240, 235, 220))
        A.draw_moving(im, red_box, it, age)
        return im

    def test_at_rest_equals_the_plain_draw(self):
        it = item({"enter": {"from": "left", "dist": 200, "dur": 0.5}})
        plain = Image.new("RGB", (1000, 700), (240, 235, 220))
        red_box(plain, it, 1.0)
        self.assertEqual(self._frame(it, 1.0).tobytes(), plain.tobytes())          # identity state takes the old path

    def test_slide_in_moves_the_pixels(self):
        it = item({"enter": {"from": "left", "dist": 200, "dur": 0.5, "ease": "linear"}})
        x_rest = centroid(self._frame(it, 1.0))[0]
        x_mid = centroid(self._frame(it, 0.25))[0]
        self.assertAlmostEqual(x_rest - x_mid, 100, delta=3)

    def test_fade_blends_with_the_background(self):
        it = item({"fade": 1.0})
        half = np.asarray(self._frame(it, 0.2)).astype(int)[350, 500]
        full = np.asarray(self._frame(it, 5.0)).astype(int)[350, 500]
        bg = np.array((240, 235, 220))
        self.assertTrue(np.all(half <= bg) and half[1] < bg[1] and half[1] > full[1])
        self.assertEqual(tuple(full), (200, 30, 30))

    def test_scale_grows_about_the_centre(self):
        it = item({"scale": [0.5, 1.0, 1.0]})
        small = centroid(self._frame(it, 0.0))
        big = centroid(self._frame(it, 2.0))
        self.assertAlmostEqual(small[0], big[0], delta=2)
        self.assertAlmostEqual(small[1], big[1], delta=2)
        self.assertLess(small[2], big[2] * 0.4)

    def test_gone_after_exit(self):
        it = item({"exit": {"at": 1.0, "to": "none", "dur": 0.2}})
        self.assertEqual(centroid(self._frame(it, 2.0))[2], 0)

    def test_deterministic_pixels(self):
        it = item({"enter": {"from": "bottom"}, "scale": [0.7, 1.0, 0.5]})
        self.assertEqual(self._frame(it, 0.2).tobytes(), self._frame(it, 0.2).tobytes())


if __name__ == "__main__":
    unittest.main()
