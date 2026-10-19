"""A shot CSV for another script stops Generate; flash shots join their neighbour; stock searches come from context."""
import re
import unittest

from whatif.app_integration import plan_from, script_match
from whatif.planner import Shot, absorb_short, stock_query
from whatif.shot_csv import PlanError

SPOKEN = ("right now you are moving through the milky way at about 230 kilometres per second faster than any spacecraft humans have built "
          "and yet if you looked at the night sky tonight and again a lifetime from now the stars would look almost exactly the same ").split() * 3


def _words():
    return [[w, i * 0.4, i * 0.4 + 0.3] for i, w in enumerate(SPOKEN)]


def _csv(text):
    return "beat,row,vo_anchor,text\nb1,beat,,\"%s\"\n" % text


class ScriptGuardTest(unittest.TestCase):   # unittest, not pytest: the test runner (scripts/run_tests_parallel.py) has no pytest
    def test_other_script_stops_generate(self):
        other = " ".join(f"Voyager {i} crossed region {i * 7} beyond the planets and sent signal number {i * 3} back toward Earth" for i in range(12))
        self.assertLess(script_match(_words(), _csv(other))[0], 0.25)
        with self.assertRaises(PlanError):
            plan_from(_words(), "", 100.0, "t", _csv(other))

    def test_own_script_matches(self):
        self.assertGreater(script_match(_words(), _csv(" ".join(SPOKEN)))[0], 0.9)

    def test_flash_shots_join_neighbour(self):
        sh = [Shot(id="", start=0, end=5, text="a", kind="image"), Shot(id="", start=5, end=5.5, text="b", kind="image"),
              Shot(id="", start=5.5, end=9, text="c", kind="image")]
        out = absorb_short(sh, [])
        spans = [(s.start, s.end) for s in out]
        self.assertIn(spans, ([(0, 5.5), (5.5, 9)], [(0, 5), (5, 9)]))
        self.assertGreaterEqual(min(s.length for s in out), 2.0)

    def test_stock_query_is_context_and_niche(self):
        q = stock_query(Shot(id="", start=0, end=.5, text="move"), "planets near the sun move fast and planets far from it move slowly")
        self.assertTrue(len(q.split()) >= 5 and re.search(r"planet|sun", q))
        self.assertIn("space", stock_query(Shot(id="", start=0, end=.5, text="because")))


if __name__ == "__main__":
    unittest.main()
