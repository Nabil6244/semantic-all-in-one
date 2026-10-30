"""A single long headline word in the narrow 3D-panel column shrinks instead of running off the frame (found in the release render: "STRAIGHTEN" lost its last letter)."""
import unittest

from PIL import Image

from reptheory import draw as D


class HeadlineFit(unittest.TestCase):
    def _right_edge(self, text):
        ctx = D.Ctx(1280, 720); lay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
        D.callout_column(lay, ctx, text, 1.0, "", 1.0, [], x=(0.60 * 1280 + 70) / ctx.S + 40)
        box = lay.getchannel("A").getbbox(); return box[2] if box else 0

    def test_long_word_stays_inside_the_frame(self):
        self.assertLess(self._right_edge("TRICEPS STRAIGHTEN"), 1280 - 20)

    def test_short_headline_unchanged_in_size(self):
        short = self._right_edge("UPPER ARM"); self.assertGreater(short, 0); self.assertLess(short, 1280 - 20)


if __name__ == "__main__":
    unittest.main()
