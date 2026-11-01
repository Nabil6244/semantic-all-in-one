"""Line-figure scenes (sketch.py) and the equation lockup, offered from sentence shape so any script gets them (docs/rep_theory/AUDIT_2026-11-01_final3.md, "Already in the code")."""
from __future__ import annotations
import unittest

from reptheory import variety as V

def _sc(text, no=1, start=0.0, **kw):
    ws = [{"w": w, "t0": start + 0.3 * i, "t1": start + 0.3 * i + 0.25} for i, w in enumerate(text.split())]
    return dict({"no": no, "kind": "callout", "start": start, "end": start + 0.3 * len(ws) + 0.6, "words": ws, "text": text, "pages": [], "decisions": [], "art": "", "section": "X", "topic": ""}, **kw)

class Sketch(unittest.TestCase):
    def test_exercises_and_settings_get_a_line_figure(self):
        for text, move in (("Do three sets of squats.", "squat"), ("Hold a plank for thirty seconds.", "plank"), ("Try ten press-ups a day.", "pushup"), ("Chin-ups build your back.", "pullup"),
                           ("Lunges train one leg at a time.", "squat"), ("Get to the gym three times a week.", "gym")):
            ev = V.evidence(_sc(text)); self.assertIn("sketch", ev, text); self.assertEqual(ev["sketch"][1]["move"], move)

    def test_a_pose_wins_unless_only_the_figure_has_the_variant(self):
        pose = {"art": "rep_squat_v1", "at": 0.3, "glows": []}
        self.assertNotIn("sketch", V.evidence(_sc("Do three sets of squats.", pose_pick=pose)))
        self.assertIn("sketch", V.evidence(_sc("Start with wall push-ups.", pose_pick={"art": "rep_pushup_top_v1", "at": 0.3, "glows": []})))      # only the line figure has a wall push-up

    def test_chosen_sketch_becomes_the_scene(self):
        scs = [_sc("Sleep well tonight and every night.", 1, 0.0), _sc("Start with wall push-ups until you can do ten.", 2, 3.0), _sc("Your body adapts to what you ask of it.", 3, 7.0)]      # not the last scene (the last line may be a key line)
        V.direct(scs, flow=False, three_d=False)
        self.assertEqual(scs[1]["kind"], "sketch"); self.assertEqual(scs[1]["sketch"]["variant"], "wall")

class Equation(unittest.TestCase):
    def test_conversions_said_with_numbers_on_both_sides(self):
        for text, lhs, rhs in (("One kilo is about two pounds.", "1 KG", "2 LB"), ("Three eggs give you about eighteen grams.", "3 EGGS", "18 G"), ("An hour is 60 minutes.", "1 H", "60 MIN")):
            eq = V.evidence(_sc(text))["equation"][1][0]; self.assertEqual((eq["lhs"], eq["rhs"]), (lhs, rhs)); self.assertGreater(eq["at_r"], eq["at_l"])

    def test_no_equation_without_two_numbers_or_when_too_long(self):
        for text in ("A big guy is a strong guy.", "A stretchy tendon is like slack in a rope.", "A can of tuna gives you twenty five. Plant protein works too.", "Sleep is when you grow."):
            self.assertNotIn("equation", V.evidence(_sc(text)), text)

    def test_chosen_equation_becomes_the_scene(self):
        scs = [_sc("Sleep well tonight and every night.", 1, 0.0), _sc("One kilo is about two pounds.", 2, 3.0), _sc("Your body adapts to what you ask of it.", 3, 7.0)]
        V.direct(scs, flow=False, three_d=False)
        self.assertEqual(scs[1]["kind"], "equation"); self.assertEqual(scs[1]["equations"][0]["lhs"], "1 KG")

class Neither(unittest.TestCase):
    def test_plain_sentence_gets_neither(self):
        ev = V.evidence(_sc("Your body adapts to what you ask of it."))
        self.assertNotIn("sketch", ev); self.assertNotIn("equation", ev)

if __name__ == "__main__":
    unittest.main()
