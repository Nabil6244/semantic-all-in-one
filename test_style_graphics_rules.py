"""A style's opt-in graphics rules (Book of Enoch: plain_numbers, short_names, numbers_first): plain counts and dated
years become big number cards, name labels are only the name, a number leads its beat. A style without the block
(every other style) plans exactly the graphics it always did."""

import unittest
from types import SimpleNamespace as NS

from graphics.director import decide_for_scenes, decide_graphic
from graphics.engine import style_graphics_rules
from graphics.extract import extract_plain_numbers, short_name
from style_engine.loader import list_builtin_styles

ENOCH = style_graphics_rules(NS(style={"style_id": "book_of_enoch"}))
LINES = ["For more than a thousand years, one of the oldest books ever written about angels was lost.",
         "In 1773, the Scottish explorer James Bruce returned from Ethiopia with three copies written in Ge'ez.",
         "In the days of Jared, two hundred angels called the Watchers descended on the summit of Mount Hermon.",
         "The Watcher Azazel taught men to forge swords and shields, and to work metals.",
         "Then, in 1952, in Cave Four at Qumran,",
         "The book also describes a year of exactly 364 days, the same calendar followed at Qumran.",
         "Then the archangels cried out to heaven."]


def roles(rules):
    scenes = [NS(scene_number=str(i + 1), narration_excerpt=t, purpose="context", start=i * 30.0) for i, t in enumerate(LINES)]
    return {k: [(d.role, d.text_hint, d.secondary_hint) for d in v] for k, v in decide_for_scenes(scenes, rules=rules).items()}


class StyleGraphicsRules(unittest.TestCase):
    def test_plain_numbers_become_number_cards(self):
        got = roles(ENOCH)
        self.assertEqual(got["1"], [("STATISTIC", "1,000", "YEARS")])
        self.assertEqual(got["2"], [("STATISTIC", "1773", "")])
        self.assertEqual(got["3"], [("STATISTIC", "200", "ANGELS")])
        self.assertEqual(got["5"], [("STATISTIC", "1952", "")])
        self.assertEqual(got["6"], [("STATISTIC", "364", "DAYS")])
        self.assertEqual(got["7"], [], "no number, no name: no graphic")

    def test_a_name_label_is_only_the_name(self):
        self.assertEqual(roles(ENOCH)["4"], [("LOWER_THIRD", "Azazel", "")])
        self.assertEqual(short_name("James Bruce returned from Ethiopia"), "James Bruce")
        self.assertEqual(short_name("Watcher Azazel", ["Watcher", "Azazel"]), "Azazel")

    def test_not_every_number_is_a_card(self):
        self.assertEqual(extract_plain_numbers("Cave Four at Qumran"), [])
        self.assertEqual(extract_plain_numbers("one of the oldest books"), [])

    def test_other_styles_plan_exactly_as_before(self):
        before = roles(None)
        for st in list_builtin_styles():
            if st.id == "book_of_enoch":
                continue
            rules = style_graphics_rules(NS(style={"style_id": st.id}))
            self.assertEqual(rules, {}, st.id)
            self.assertEqual(roles(rules), before, st.id)
        self.assertEqual(decide_graphic(narration=LINES[5]), [], "the default still skips plain counts")


if __name__ == "__main__":
    unittest.main()
