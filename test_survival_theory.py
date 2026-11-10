"""Survival: the Rep Theory engine with the field-guide theme (reptheory/theme.py "survival"), its own script and CSV prompts, and the rules from the 10 s test (2026-11-10)."""
import unittest

from reptheory import app_section as A, art as AR, beat_art as BA, direction as DR, gate as G, packaging as PK, picture as P, theme as T
from ui import style_registry as R


class SurvivalTheme(unittest.TestCase):
    def tearDown(self):
        T.set_theme("")

    def test_switch_and_back(self):
        base = (T.BG_TOP, T.WHITE, T.HEAD_FONT)
        self.assertEqual(T.set_theme("survival"), "survival")
        self.assertIn("survival", T.NO_GYM); self.assertIn("survival", T.LIGHT)
        self.assertGreater(sum(T.BG_TOP), 700); self.assertLess(sum(T.WHITE), 200)      # paper canvas, dark ink type
        T.set_theme("")
        self.assertEqual((T.BG_TOP, T.WHITE, T.HEAD_FONT), base)

    def test_picture_prompts_use_the_field_guide_style(self):
        T.set_theme("survival")
        self.assertIn(AR.SURVIVAL_STYLE, BA.prompt_for("A blaze is a cut through the bark."))
        self.assertIn(AR.SURVIVAL_STYLE, BA.own_prompt("a long hunter cutting a blaze"))
        self.assertIn("drawn large", AR.SURVIVAL_STYLE)      # the detail the sentence is about must be unmistakable (test 1: blazes too faint)
        T.set_theme("cat")
        self.assertNotIn(AR.SURVIVAL_STYLE, BA.prompt_for("A blaze is a cut through the bark."))

    def test_close_up_is_a_real_close_up_only_in_survival(self):
        self.assertGreater(P.SURVIVAL_PUSH["close"][0], P.SURVIVAL_PUSH["medium"][1] * 1.25)
        self.assertEqual(P.PUSH["close"], (1.12, 1.22))      # Rep Theory / Cat / Jung / Elder keep their framing

    def test_no_repeated_words_on_screen(self):
        self.assertTrue(G.repeats("THAT'S NUMBER TWENTY-TWO", {"NUMBER TWENTY-TWO"}))
        self.assertTrue(G.repeats("THAT'S NUMBER TWENTY-TWO", {"#22"}))
        self.assertFalse(G.repeats("PALE WOOD", {"EYE LEVEL", "#22"}))
        self.assertFalse(G.repeats("", {"#22"}))

    def test_spoken_number_may_show_as_digits(self):
        self.assertEqual(DR.on_screen_ok("#22", "That's number twenty-two."), "#22")
        self.assertEqual(DR.on_screen_ok("$20", "There's a way to hide for about twenty dollars."), "$20")
        self.assertEqual(DR.on_screen_ok("22 DAYS", "It took days."), "")

    def test_picker_and_prompts(self):
        self.assertEqual(R.BUILT_ON[R.SURVIVAL], "Rep Theory")
        out = R.with_extras(("Rep Theory", "Health Cinema"))
        self.assertEqual(out[out.index("Elder Health Theory") + 1], "Survival")
        txt = A.prompt_text("That's number 22.", cat="survival")
        self.assertIn("Survival video", txt); self.assertTrue(txt.rstrip().endswith("That's number 22.")); self.assertNotIn("<<<PASTE", txt)
        script = A.SURVIVAL_SCRIPT_PROMPT_FILE.read_text(encoding="utf-8")
        for must in ("ONE SECRET, MANY MYTHS", "THE ONE RULE", "THE BRIDGE", "FORCED-CHOICE", "Never invent", "TOPIC:"):
            self.assertIn(must, script)
        names = {p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for p, _ in PK.prompt_files(".")}
        self.assertTrue({"survival_scenes_csv_prompt.txt", "survival_script_prompt.txt"} <= names)

    def test_csv_example_is_valid(self):
        import csv, io
        txt = A.SURVIVAL_PROMPT_FILE.read_text(encoding="utf-8")
        block = txt.split("CSV:\n", 1)[1].split("\n\nSCRIPT", 1)[0]
        rows = list(csv.reader(io.StringIO(block)))
        self.assertEqual(rows[0], ["text", "chapter", "look", "prompt", "muscle", "camera", "on_screen", "section", "graphic"])
        T.set_theme("survival")
        for r in rows[1:]:
            self.assertEqual(len(r), 9, r)
            if r[2]: self.assertTrue(DR.norm_look(r[2]), r[2])
            if r[6]: self.assertTrue(DR.on_screen_ok(r[6], r[0]), (r[6], r[0]))


if __name__ == "__main__":
    unittest.main()
