import unittest

from explainer import scene_intel as SI


class SceneIntel(unittest.TestCase):
    def test_csv_note_wins_over_words(self):
        base = SI.from_words("In 1960 the farmers left the fields.")
        s = SI.from_notes("place: canal city; type: coast; period: 1450; architecture: Gothic palazzi; people: merchant, doge; mood: dusk", base)
        self.assertEqual((s.year, s.place_type, s.architecture, s.source), (1450, "coast", "Gothic palazzi", "csv"))
        self.assertEqual(s.people, ["merchant", "doge"])
        self.assertEqual(SI.decide(s).route, "flow")

    def test_prose_note_is_ignored(self):
        self.assertIsNone(SI.from_notes("show the harbour at night", None))
        self.assertIsNone(SI.from_notes("", None))

    def test_bc_year(self):
        self.assertEqual(SI.from_notes("period: 500 BC; type: coast").year, -500)

    def test_specific_architecture_goes_to_flow(self):
        d = SI.decide(SI.SceneSpec(place_type="coast", year=1450, architecture="Gothic palazzi"))
        self.assertEqual(d.route, "flow")
        self.assertIn("Gothic palazzi", d.reasons[0])

    def test_old_period_goes_to_flow_but_modern_composes(self):
        self.assertEqual(SI.decide(SI.SceneSpec(place_type="village", year=1400)).route, "flow")
        d = SI.decide(SI.SceneSpec(place_type="village", year=1960))
        self.assertEqual((d.route, d.set_name), ("compose", "old_town"))

    def test_unknown_place_type_goes_to_flow(self):
        self.assertEqual(SI.decide(SI.SceneSpec(place_type="palace", year=1960)).route, "flow")
        self.assertEqual(SI.decide(SI.SceneSpec()).route, "flow")

    def test_words_only_reads_period_and_place(self):
        s = SI.from_words("In 1960 the farmers left the fields.")
        self.assertEqual((s.year, s.place_type), (1960, "farm"))
        self.assertEqual(SI.from_words("The medieval harbour grew.").year, 1100)

    def test_flow_prompt_has_one_style_line_and_the_facts(self):
        p = SI.flow_prompt(SI.SceneSpec(place="canal city", region="Venice", year=1450, architecture="Gothic palazzi", people=["merchant"], clothing="wool cloak"))
        self.assertIn("Venice", p)
        self.assertIn("1450", p)
        self.assertIn("Gothic palazzi architecture", p)
        self.assertTrue(p.endswith("16:9"))

    def test_no_repeat(self):
        a = SI.arrangement("barn", ["farmer", "wife"])
        self.assertFalse(SI.no_repeat([a], SI.arrangement("barn", ["wife", "farmer"])))
        self.assertTrue(SI.no_repeat([a], SI.arrangement("barn", ["wife", "farmer"]), continues=True))
        self.assertTrue(SI.no_repeat([a], SI.arrangement("station", ["farmer"])))
        self.assertTrue(SI.no_repeat([a, ("x", ()), ("y", ()), ("z", ())], a))


if __name__ == "__main__":
    unittest.main()
