"""Kinetic / headline words are whole thoughts (Black Sea film, 2026-11-09): a colon payoff is the line; a lead never ends on 'a new'."""
import unittest

from cinematic_explainer.war import direction as D


class KineticText(unittest.TestCase):
    def test_colon_payoff_is_the_line(self):
        self.assertEqual(D._phrase_or_lead("Then Ukraine turned to a new weapon: sea drones."), "Sea drones")

    def test_lead_never_ends_inside_a_noun_phrase(self):
        h = D._phrase_or_lead("Then Ukraine turned to a new weapon and changed the war at sea")
        self.assertFalse(h.lower().endswith(("a new", "the new", "an old")), h)

    def test_long_colon_tail_falls_back(self):
        h = D._phrase_or_lead("He said one thing: that the fleet would never leave the port of Sevastopol again.")
        self.assertNotEqual(h, "")
        self.assertLessEqual(len(h.split()), 6)

    def test_weak_fragments_are_never_headlines(self):
        h = D._phrase_or_lead("These are small, fast boats packed with explosives, steered by remote control.")
        self.assertNotEqual(h.lower(), "these are small")
        h = D._phrase_or_lead("And the war at sea showed that cheap drones can now threaten even the largest warships.")
        self.assertFalse(h.lower().endswith("showed"), h)

    def test_glimpse_between_cards_uses_the_two_second_rule(self):
        self.assertGreaterEqual(max(D.FLASH_S, D.MIN_SHOT_S), 2.0)


if __name__ == "__main__":
    unittest.main()
