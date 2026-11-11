"""Carl Jung Theory: the Rep Theory engine with the old-master theme (reptheory/theme.py "jung"), Jung's paintings drawn with his reference images, sourced quote cards."""
import unittest

from reptheory import app_section as A, art as AR, beat_art as BA, cards as K, direction as DR, theme as T
from ui import style_registry as R


class JungTheory(unittest.TestCase):
    def tearDown(self):
        T.set_theme("")

    def test_theme_dark_and_back(self):
        self.assertEqual(T.set_theme("jung"), "jung")
        self.assertLess(sum(T.BG_BOT), 60); self.assertGreater(sum(T.WHITE), 600)
        self.assertIn("jung", T.NO_GYM)
        T.set_theme(""); self.assertEqual(T.WHITE, (247, 247, 245))

    def test_jung_paintings_use_references_only_when_he_is_in_them(self):
        T.set_theme("jung")
        him = BA.own_prompt("Carl Jung writing in a red leather book by candlelight")
        idea = BA.own_prompt("a man before a mirror, his reflection a shadow")
        self.assertTrue(BA.wants_refs(him)); self.assertFalse(BA.wants_refs(idea))
        self.assertIn("Oil painting", him); self.assertIn("no Carl Jung", idea)
        self.assertTrue(BA.wants_refs(BA.prompt_for("Jung spent years facing his own shadow.")))
        self.assertLessEqual(len(AR.jung_refs()), 3)
        T.set_theme(""); self.assertFalse(BA.wants_refs(him))      # never outside Carl Jung Theory

    def test_quote_payload(self):
        ws = [{"w": w, "t0": i * 0.3} for i, w in enumerate("He wrote: one does not become enlightened".split())]
        q = K.quote_payload("He wrote: one does not become enlightened", ws, "The Philosophical Tree, 1945")
        self.assertEqual([w["w"] for w in q["words"]], ["One", "does", "not", "become", "enlightened"])
        self.assertAlmostEqual(q["words"][0]["t0"], 0.6); self.assertEqual(q["source"], "The Philosophical Tree, 1945")
        self.assertEqual(K.quote_payload("No source given here.", [], "")["source"], "")      # never invented
        self.assertEqual(DR.norm_look("quote"), "quote")

    def test_picker_and_prompt(self):
        out = R.with_extras(("Rep Theory", "Health Cinema"))
        self.assertEqual(out[out.index("Rep Theory") + 1: out.index("Rep Theory") + 3], ("Cat Theory", "Carl Jung Theory"))
        txt = A.prompt_text("My script.", cat="jung")
        self.assertIn("Carl Jung Theory", txt); self.assertTrue(txt.rstrip().endswith("My script."))


class FilmFinishSpeed(unittest.TestCase):
    def test_fast_grain_matches_the_float_version(self):
        """A 23-min Jung video is ~34,000 frames: the finish must stay cheap and look the same as the original float maths (within one level)."""
        import math
        import numpy as np
        from PIL import Image, ImageChops
        from reptheory import film as FM
        img = Image.fromarray(np.random.default_rng(1).integers(0, 256, (90, 160, 3), dtype=np.uint8))
        for f in (0, 5, 11):
            t = f / 24; flick = 1.0 + 0.010 * math.sin(t * 7.1) + 0.006 * math.sin(t * 17.3 + 1.3)
            old = np.clip(np.asarray(img, dtype=np.float32) * flick + FM._grains(160, 90)[(f // 2) % FM.GRAIN_FRAMES], 0, 255).astype("uint8").astype(int)
            up, down = FM._grain_images(160, 90)[(f // 2) % FM.GRAIN_FRAMES]
            new = np.asarray(ImageChops.subtract(ImageChops.add(img.point([min(255, int(v * flick)) for v in range(256)] * 3), up), down)).astype(int)
            self.assertLessEqual(int(np.abs(old - new).max()), 1)
        self.assertEqual(FM.finish(img, 3).size, img.size)


if __name__ == "__main__":
    unittest.main()
