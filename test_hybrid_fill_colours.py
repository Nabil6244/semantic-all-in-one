"""Hybrid Map: the area a beat talks about is filled in a strong colour, one colour per country, the same colour every time that country returns."""

from __future__ import annotations

import copy
import unittest

import place_focus
from hybrid.compile import compile_plan
from hybrid.plan import HybridPlan
from test_hybrid import HAS_NODE, PLAN


def fill(i, t, iso="", **kw):
    ev = {"id": i, "type": "fill", "t_in": t, "t_out": t + 5, "role": "primary", "iso": ["XXX"], "_iso": iso}
    ev.update(kw)
    return ev


class TestColourFills(unittest.TestCase):
    def test_each_country_gets_its_own_colour_and_keeps_it(self):
        evs = [fill("a", 1, "GBR"), fill("b", 3, "FRA"), fill("c", 9, "GBR")]
        place_focus.colour_fills(evs)
        a, b, c = evs
        self.assertNotEqual(a["color"], b["color"])
        self.assertEqual(a["color"], c["color"])
        self.assertEqual((a["outline_color"], a["opacity"]), (a["color"], place_focus.FILL_OPACITY))
        self.assertNotIn("role", a)
        self.assertTrue(all("_iso" not in e for e in evs))

    def test_colours_follow_the_order_on_screen_not_the_list_order(self):
        evs = [fill("late", 9, "FRA"), fill("early", 1, "GBR")]
        place_focus.colour_fills(evs)
        self.assertEqual(evs[1]["color"], place_focus.COUNTRY_PALETTE[0])

    def test_a_colour_chosen_on_purpose_is_kept(self):
        evs = [fill("a", 1, "GBR", color="#123456"), fill("b", 2, "GBR", role="compare"), fill("c", 3, "GBR")]
        place_focus.colour_fills(evs)
        self.assertEqual(evs[0]["color"], "#123456")
        self.assertEqual(evs[1]["role"], "compare")
        self.assertEqual(evs[2]["color"], place_focus.COUNTRY_PALETTE[0])

    def test_an_automatic_place_outline_takes_its_countrys_colour(self):
        auto = {"id": "f", "type": "fill", "t_in": 5, "t_out": 9, "color": place_focus.FOCUS_COLOR, "outline_color": place_focus.FOCUS_COLOR,
                "geo_focus": {"country": "FRA"}, "polys": []}
        evs = [fill("a", 1, "GBR"), auto]
        place_focus.colour_fills(evs)
        self.assertNotEqual(evs[0]["color"], auto["color"])

    def test_more_countries_than_colours_start_the_palette_again(self):
        assigned = {}
        cols = [place_focus.country_colour(f"C{i}", assigned) for i in range(len(place_focus.COUNTRY_PALETTE) + 1)]
        self.assertEqual(cols[0], cols[-1])
        self.assertEqual(len(set(cols[:-1])), len(place_focus.COUNTRY_PALETTE))

    @unittest.skipUnless(HAS_NODE, "node or the engine is not available")
    def test_a_hybrid_plan_compiles_fills_in_country_colours(self):
        d = copy.deepcopy(PLAN)
        d["beats"][2]["layers"].append({"id": "uganda", "type": "fill", "t": 16, "place": "Uganda", "role": "subject"})
        spec = compile_plan(HybridPlan.from_dict(d), width=1920, height=1080, fps=30).spec
        ev = {e["id"]: e for e in spec["events"]}
        self.assertNotEqual(ev["kenya"]["color"], ev["uganda"]["color"])
        self.assertEqual(ev["kenya"]["opacity"], place_focus.FILL_OPACITY)
        self.assertTrue(all("_iso" not in e for e in spec["events"]))


if __name__ == "__main__":
    unittest.main()
