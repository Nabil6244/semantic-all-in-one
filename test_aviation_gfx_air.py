"""Aviation graphics for business lines (fleet grid, route network, seat map, then->now bars, big number, timeline), their narration
triggers, and the rule that a line without its own clip gets a graphic or a clean text card, never a borrowed off-topic picture."""

import tempfile
import unittest

import numpy as np
from PIL import ImageChops

from aviation import gfx_air as A
from aviation import planner as P
from test_aviation_map import fake_tile
from test_aviation_planner import layers, scenes


def _diff(a, b):
    return sum(ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").histogram()[12:])


class DrawTests(unittest.TestCase):
    def check(self, fn, p, t0=0.4, t1=3.5, dur=5.0):
        a, b = fn(t0, dur, p), fn(t1, dur, p)
        self.assertEqual(a.size, (1280, 720))
        self.assertGreater(_diff(a, b), 2000, fn.__name__)            # it animates
        self.assertIsNone(fn(1.0, dur, {}), fn.__name__)               # nothing to show -> nothing drawn
        return b

    def test_fleet_grid(self):
        self.check(A.lay_fleet, {"count": 277, "label": "AIRCRAFT"})
        self.assertEqual(A.fleet_icons(277), 100)                     # big fleets: one icon stands for several, capped
        self.assertEqual(A.fleet_icons(5), 5)

    def test_network(self):
        with tempfile.TemporaryDirectory() as d:
            self.check(A.lay_network, {"hub": "DXB", "count": 150, "label": "DESTINATIONS", "fetch_tile": fake_tile, "cache": d})

    def test_seat_map(self):
        im = self.check(A.lay_seats, {"now": 72.0, "before": 79.5, "label": "SEATS FILLED"})
        self.assertAlmostEqual(A.seats_filled(72.0, 200), 144)

    def test_then_now_bars(self):
        self.check(A.lay_change, {"before": 3.1e9, "after": 1.0e9, "currency": "USD", "label": "PROFIT"})
        self.assertEqual(A.money(3.1e9, "USD"), "$3.1B")
        self.assertEqual(A.change_tag(3.1e9, 1.0e9), "-68%")

    def test_big_number(self):
        self.check(A.lay_big_number, {"value": 52.0, "unit": "%", "sign": "+", "label": "CARGO REVENUE", "icon": "freighter"})

    def test_timeline(self):
        self.check(A.lay_timeline, {"from_year": 1985, "to_year": 2026, "label": "EMIRATES"})


EMIRATES = ["By March 2026, Emirates ran 277 aircraft to more than 150 destinations, carried 53.2 million passengers in a year.",
            "In the six months to September, its seats were only 72 percent full, against 79.5 a year earlier.",
            "The airline's profit fell from 3.1 billion dollars to one billion.",
            "Cargo volume barely moved, but cargo revenue jumped 52 percent.",
            "On October twenty-fifth, 1985, flight EK600 left Dubai for Karachi."]


class TriggerTests(unittest.TestCase):
    def kinds(self, lines, **kw):
        sc = scenes(lines, each=6.0)
        for s in sc:
            s.update(kw)
        p = P.plan(sc)
        return {s["layer"] for s in p.shots if str(s.get("layer", "")).startswith("gfx_air.")}, p

    def test_numbers_bring_their_graphic(self):
        k, _ = self.kinds(EMIRATES[:4], has_clip=False)
        for want in ("gfx_air.lay_fleet", "gfx_air.lay_network", "gfx_air.lay_seats", "gfx_air.lay_change", "gfx_air.lay_big_number"):
            self.assertIn(want, k)

    def test_history_line_gets_the_timeline(self):
        # a flight line (EK600 leaving Dubai) gets the route map; a history line in the business story gets the timeline
        k, _ = self.kinds([EMIRATES[0], "The airline started in 1985 with two borrowed planes and ten million dollars."], has_clip=False)
        self.assertIn("gfx_air.lay_timeline", k)

    def test_a_line_without_a_clip_never_borrows_a_picture(self):
        sc = scenes(["Then the story flips.", "Airspace closures across the Gulf cut its flying schedule."], each=4.0)
        for s in sc:
            s["has_clip"] = False
        p = P.plan(sc)
        self.assertFalse([s for s in p.shots if s.get("kind") == "footage"])
        for s in p.shots:
            self.assertNotEqual((s.get("params") or {}).get("image_from"), "footage")

    def test_lines_with_clips_keep_their_clips(self):
        sc = scenes([EMIRATES[2]], each=13.0)
        sc[0]["has_clip"] = True
        p = P.plan(sc)
        self.assertTrue([s for s in p.shots if s.get("kind") == "footage"])
        self.assertTrue(layers(p, "gfx_air.lay_change"))             # clips (the cold open), the graphic, then clips again
        g = layers(p, "gfx_air.lay_change")[0]
        self.assertLessEqual(g["end"] - g["start"], P.CARD_MAX_S + 1e-6)
        self.assertGreaterEqual(g["start"], P.OPEN_S - 1e-6)


class TextCardTests(unittest.TestCase):
    def test_fact_without_a_picture_is_a_clean_text_card(self):
        from aviation import cards as K
        im = K.lay_article(2.0, 5.0, {"fact": "Then the story flips."})
        self.assertIsNotNone(im)


if __name__ == "__main__":
    unittest.main()


class BorrowedGraphicsTests(unittest.TestCase):
    """Graphics borrowed from the Green Dot Aviation reference (Eastern 855): crew card, gauge, runway diagram, approach side view,
    descent graphic, title card."""

    def anim(self, fn, p, overlay=False):
        a, b = fn(0.3, 5.0, p), fn(3.5, 5.0, p)
        self.assertEqual(b.size, (1280, 720))
        self.assertGreater(_diff(a, b), 1000, fn.__name__)
        self.assertIsNone(fn(1.0, 5.0, {}), fn.__name__)
        if overlay:
            self.assertEqual(b.getpixel((1150, 690))[3], 0)           # an overlay: the picture shows beside its shaded corner
        return b

    def test_crew_card(self):
        self.anim(A.lay_crew, {"name": "", "role": "CAPTAIN", "age": 52, "hours": 11000, "on_type": None}, overlay=True)

    def test_gauge(self):
        self.anim(A.lay_gauge, {"value": 540, "max": 5000, "unit": "KG", "label": "FUEL"})
        self.assertAlmostEqual(A.needle_angle(0, 0, 100), A.needle_angle(100, 0, 100) - 270, delta=0.01)

    def test_runway(self):
        self.anim(A.lay_runway, {"runway": "34", "length_m": 3330, "airport": "ATQ"})
        self.assertEqual(A.runway_ends("34"), ("34", "16"))

    def test_approach(self):
        self.anim(A.lay_approach, {"from_ft": 2600, "to_ft": 200, "lines": [450, 200]})

    def test_descent(self):
        self.anim(A.lay_descent, {"speed_kt": 285, "fpm": -3284})

    def test_title(self):
        self.anim(A.lay_title, {"title": "VISTARA 611", "sub": "4 JULY 2019"})


class BorrowedTriggerTests(unittest.TestCase):
    def layers_for(self, lines, **kw):
        sc = scenes(lines, each=6.0)
        for s in sc:
            s.update(kw)
        p = P.plan(sc)
        return {s["layer"]: s for s in p.shots if s.get("layer")}

    def test_crew_line(self):
        ly = self.layers_for(["The captain is 52, with more than 11,000 hours in his logbook."], has_clip=False)
        self.assertEqual(ly["gfx_air.lay_crew"]["params"]["age"], 52)
        self.assertEqual(ly["gfx_air.lay_crew"]["params"]["hours"], 11000)
        self.assertEqual(ly["gfx_air.lay_crew"]["params"]["role"], "CAPTAIN")

    def test_runway_line(self):
        ly = self.layers_for(["Vistara 611 takes off from Srinagar.", "They are cleared to land on runway 34 at Amritsar, 3,330 metres long."])
        self.assertEqual(ly["gfx_air.lay_runway"]["params"]["runway"], "34")
        self.assertEqual(ly["gfx_air.lay_runway"]["params"]["length_m"], 3330)

    def test_descent_line(self):
        ly = self.layers_for(["Vistara 611 takes off from Srinagar.", "They come down at 285 knots, sinking 3,284 feet per minute."])
        self.assertEqual(ly["gfx_air.lay_descent"]["params"]["fpm"], -3284)

    def test_gauge_line(self):
        ly = self.layers_for(["Vistara 611 takes off from Srinagar.", "The fuel gauge now reads just 540 kg."])
        self.assertEqual(ly["gfx_air.lay_gauge"]["params"]["value"], 540)

    def test_approach_line(self):
        ly = self.layers_for(["Vistara 611 takes off from Srinagar.", "On the glide slope they descend from 2,600 feet to the decision height of 200 feet."])
        self.assertIn("gfx_air.lay_approach", ly)
