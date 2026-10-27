"""Camera + film texture tests (Phase B of docs/explainer/explainer_major_upgrade_plan.md): determinism, default-off, safe area at every frame, motion during a hold,
missing-asset fallback, asset --check.

usage: python3 -B explainer/spike/test_motion_camera.py   (from the repository root; small encodes only)"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

import numpy as np                                                            # noqa: E402
from PIL import Image, ImageDraw                                              # noqa: E402

from explainer.board import render as R                                       # noqa: E402
from explainer.board import Cue, build_board_clip                             # noqa: E402
from explainer.motion import camera as CAM                                    # noqa: E402
from explainer.motion import texture as TX                                    # noqa: E402
from explainer.motion import build_texture as BT                              # noqa: E402

FPS = 30
N = 180                                  # a 6 s clip
SIZES = ((1920, 1080), (1280, 720))
WORDS = [(w, 0.3 + i * 0.3, 0.3 + i * 0.3 + 0.25) for i, w in enumerate("The old fortress stood above the river for centuries and nobody dared".split())]
CUES = [Cue(id="t1", kind="title", anchor={"word": "fortress", "occurrence": 1}, text="FORTRESS"), Cue(id="p1", kind="pop", anchor={"word": "river", "occurrence": 1}, text="river", role="blue")]


def safe_frame(size):
    """A board whose ink sits exactly on the layout SAFE rectangle (the worst case for the camera)."""
    W, H = size
    m = round(CAM.MARGIN * W / 1920)
    im = Image.new("RGB", size, (192, 192, 192))
    ImageDraw.Draw(im).rectangle([m, m, W - m - 1, H - m - 1], outline=(20, 20, 20), width=4)
    return im


def ink_bbox(im):
    a = np.asarray(im.convert("L")) < 90
    ys, xs = np.where(a)
    return xs.min(), ys.min(), xs.max(), ys.max()


class Camera(unittest.TestCase):
    def test_off_and_short_clips_do_nothing(self):
        self.assertIsNone(CAM.camera_box("off", N, 50, FPS))
        self.assertIsNone(CAM.camera_box("push", 3 * FPS, 10, FPS))          # shorter than 4 s
        self.assertIsNotNone(CAM.camera_box("push", 4 * FPS, 10, FPS))

    def test_pure(self):
        for m in ("push", "drift", "reframe"):
            self.assertEqual([CAM.camera_box(m, N, i, FPS, focus=(0.7, 0.4)) for i in range(N)], [CAM.camera_box(m, N, i, FPS, focus=(0.7, 0.4)) for i in range(N)])

    def test_zoom_in_range(self):
        z = CAM.camera_box("push", N, N - 1, FPS)
        self.assertAlmostEqual(1920 / (z[2] - z[0]), CAM.PUSH_ZOOM, places=3)
        self.assertTrue(1.03 <= CAM.PUSH_ZOOM <= 1.06 and CAM.ZOOM_CAP <= 1.06)

    def test_safe_area_geometry_every_frame(self):
        for size in SIZES:
            W, H = size
            inset = CAM.MIN_INSET * W / 1920
            for m in ("push", "drift", "reframe"):
                for focus in ((0.5, 0.5), (0.0, 0.0), (1.0, 1.0), (0.9, 0.2)):
                    for n in (4 * FPS, N, 900):
                        for i in range(n):
                            b = CAM.camera_box(m, n, i, FPS, size, focus)
                            self.assertTrue(-1e-6 <= b[0] and b[2] <= W + 1e-6 and -1e-6 <= b[1] and b[3] <= H + 1e-6, (m, i, b))
                            s = CAM.mapped_safe(b, size)
                            self.assertTrue(s[0] >= inset - 1e-6 and s[1] >= inset - 1e-6 and s[2] <= W - inset + 1e-6 and s[3] <= H - inset + 1e-6, (m, size, focus, n, i, s))

    def test_text_inside_frame_every_frame_pixels(self):
        for size in SIZES:
            W, H = size
            src = safe_frame(size)
            inset = CAM.MIN_INSET * W / 1920
            for m in ("push", "drift", "reframe"):
                for i in list(range(0, N, 2)) + [N - 1]:                     # includes the last frame
                    out = CAM.apply(src, CAM.camera_box(m, N, i, FPS, size, (0.8, 0.3)))
                    x0, y0, x1, y1 = ink_bbox(out)
                    self.assertTrue(x0 >= inset - 2 and y0 >= inset - 2 and x1 <= W - 1 - inset + 2 and y1 <= H - 1 - inset + 2, (size, m, i, (x0, y0, x1, y1)))

    def test_moves_during_a_hold(self):
        src = safe_frame((1920, 1080))
        for m in ("push", "drift", "reframe"):
            a = CAM.apply(src, CAM.camera_box(m, N, 90, FPS))
            b = CAM.apply(src, CAM.camera_box(m, N, 91, FPS))
            self.assertGreater(float(np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).sum()), 0)


class Texture(unittest.TestCase):
    def setUp(self):
        self.size = (640, 360)
        self.layer, note = TX.get_layer(self.size)
        self.assertIsNotNone(self.layer, note)
        self.base = Image.new("RGB", self.size, (192, 192, 192))

    def test_deterministic_per_frame_index_and_varies(self):
        a1 = TX.apply(self.base.copy(), self.layer, 17, FPS, "dust")
        a2 = TX.apply(self.base.copy(), self.layer, 17, FPS, "dust")
        b = TX.apply(self.base.copy(), self.layer, 18, FPS, "dust")
        self.assertEqual(a1.tobytes(), a2.tobytes())
        self.assertNotEqual(a1.tobytes(), b.tobytes())

    def test_mean_luma_stays_in_range(self):
        for mode in ("clean", "dust", "snow"):
            m = np.asarray(TX.apply(self.base.copy(), self.layer, 5, FPS, mode)).mean()
            self.assertTrue(192 - 14 <= m <= 192 + 3, (mode, m))
        c = np.asarray(TX.apply(self.base.copy(), self.layer, 5, FPS, "clean")).astype(int)
        self.assertLess(abs(int(c[180, 320, 0]) - 192), 14)                  # centre: grain only
        self.assertLess(int(c[0, 0, 0]), int(c[180, 320, 0]) - 8)             # corner darker than centre

    def test_missing_asset_gives_plain_frame_and_note(self):
        real = TX.DIR
        with tempfile.TemporaryDirectory() as d:
            TX.DIR = Path(d)
            TX._load.cache_clear()
            try:
                layer, note = TX.get_layer(self.size)
                self.assertIsNone(layer)
                self.assertIn("without grain", note)
                f = self.base.copy()
                self.assertEqual(TX.apply(f, layer, 3, FPS, "dust").tobytes(), self.base.tobytes())
                notes = []
                out = Path(d) / "x.mp4"
                rc = R.encode([], 3, FPS, (320, 180), out, None, False, None, "grey", "off", True, None, notes)
                self.assertEqual(rc, 0)
                self.assertEqual(len(notes), 1)
            finally:
                TX.DIR = real
                TX._load.cache_clear()

    def test_assets_check_passes(self):
        self.assertEqual(BT.main(["--check"]), 0)


class Hooks(unittest.TestCase):
    def test_defaults_do_not_change_a_frame(self):
        items = []
        a = R.draw_frame(items, 1.0, (640, 360), None, 30, False)
        b = R.draw_frame(items, 1.0, (640, 360), None, 30, False, None, "grey", "off", False, 0, 30, None)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_on_changes_frame_and_instrument_is_exact(self):
        a = R.draw_frame([], 1.0, (640, 360), None, 30, False)
        b = R.draw_frame([], 1.0, (640, 360), None, 30, False, None, "grey", "push", True, N, 30, None)
        self.assertNotEqual(a.tobytes(), b.tobytes())
        c = R.draw_frame([], 1.0, (640, 360), None, 30, True, None, "grey", "push", True, N, 30, None)
        self.assertEqual(c.tobytes(), R.draw_frame([], 1.0, (640, 360), None, 30, True).tobytes())

    def test_two_encodes_equal_and_default_equals_off(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            h = {}
            for name, kw in (("a", dict(camera="push", texture=True)), ("b", dict(camera="push", texture=True)), ("plain", {}), ("off", dict(camera="off", texture=False))):
                build_board_clip(CUES, WORDS, 0.0, 4.2, d / f"{name}.mp4", strict=False, size=(480, 270), fps=15, **kw)
                h[name] = hashlib.sha256((d / f"{name}.mp4").read_bytes()).hexdigest()
            self.assertEqual(h["a"], h["b"])
            self.assertEqual(h["plain"], h["off"])
            self.assertNotEqual(h["a"], h["plain"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
