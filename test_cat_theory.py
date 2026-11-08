"""Cat Theory: the Rep Theory engine with the white cat theme (reptheory/theme.py "cat"). Rep Theory itself must stay exactly as it was."""
import unittest

from reptheory import app_section as A, beat_art as BA, theme as T
from ui import style_registry as R


class CatTheoryTheme(unittest.TestCase):
    def tearDown(self):
        T.set_theme("")

    def test_switch_and_back(self):
        base = (T.BG_TOP, T.WHITE, T.PLATE, T.P(20, 20, 22, 9))
        self.assertEqual(T.set_theme("cat"), "cat")
        self.assertGreater(sum(T.BG_TOP), 700)          # light canvas
        self.assertLess(sum(T.WHITE), 200)              # dark (warm brown) type on it
        self.assertGreater(sum(T.P(20, 20, 22)), 700)   # card panels turn light, so the dark type reads on them
        self.assertEqual(len(T.P(20, 20, 22, 9)), 4)
        T.set_theme("")
        self.assertEqual((T.BG_TOP, T.WHITE, T.PLATE, T.P(20, 20, 22, 9)), base)
        self.assertEqual(T.P(20, 20, 22, 9), (20, 20, 22, 9))   # Rep Theory panels unchanged

    def test_cat_prompts_have_no_trainee(self):
        T.set_theme("cat")
        for p in (BA.prompt_for("Your cat is not ignoring you."), BA.own_prompt("a tabby cat on a windowsill")):
            self.assertNotIn("trainee", p.lower()); self.assertNotIn("manga-style young man", p); self.assertIn("white background", p)
        T.set_theme("")
        self.assertIn("young man", BA.prompt_for("Hold the bar for ten seconds."))   # Rep Theory still draws its trainee

    def test_picker_and_prompt_file(self):
        self.assertEqual(R.BUILT_ON[R.CAT_THEORY], "Rep Theory")
        out = R.with_extras(("Rep Theory", "Health Cinema"))
        self.assertEqual(out[out.index("Rep Theory") + 1], "Cat Theory")
        txt = A.prompt_text("My script.", cat=True)
        self.assertIn("Cat Theory", txt); self.assertTrue(txt.rstrip().endswith("My script.")); self.assertNotIn("the trainee", txt)


if __name__ == "__main__":
    unittest.main()
