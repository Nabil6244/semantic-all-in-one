"""Aviation style step 4: small graphics (counters, weather list, place title, briefing sheet, altitude side view, end card)
and storm cells on the flight map."""

import tempfile
import unittest

import numpy as np
from PIL import ImageChops

from aviation import flightmap as F
from aviation import gfx as G
from aviation import router as R
from test_aviation_map import fake_tile


def _diff(a, b):
    return sum(ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").histogram()[12:])


def _alpha_box(im):
    return im.getchannel("A").getbbox()


class CounterTests(unittest.TestCase):
    def test_counters_from_narration(self):
        v = R.extract_values("Boarding begins and 139 passengers walk on; inside the cabin are 5 cabin crew and 2 pilots.")
        self.assertEqual(G.counters_from(v), [(139, "PASSENGERS"), (5, "CABIN CREW"), (2, "PILOTS")])

    def test_counters_ignore_other_counts(self):
        self.assertEqual(G.counters_from(R.extract_values("It ordered 30 jets and cut 2,900 jobs.")), [])

    def test_digits_type_in(self):
        self.assertEqual(G.typed_digits(139, 0.0, 0.0), "")
        self.assertEqual(G.typed_digits(139, 10.0, 0.0), "139")
        self.assertEqual(len(G.typed_digits(139, 0.25, 0.0)), 2)

    def test_overlay_lower_left(self):
        im = G.lay_counters(3.0, 4.0, {"items": [(139, "PASSENGERS"), (5, "CABIN CREW")]})
        bb = _alpha_box(im)
        self.assertLess(bb[0], 100)
        self.assertGreater(bb[1], 720 * 0.5)
        self.assertIsNone(G.lay_counters(1.0, 4.0, {"items": []}))


class WeatherListTests(unittest.TestCase):
    def test_items_from_narration(self):
        items = G.weather_items("Light winds, a little dust haze and just a few clouds.")
        self.assertEqual([i[0] for i in items], ["wind", "haze", "cloud"])
        self.assertEqual(items[0][1], "LIGHT WINDS")

    def test_storm_items_with_values(self):
        items = G.weather_items("Storm clouds are building, with hail and gusts of 29 knots.")
        kinds = [i[0] for i in items]
        self.assertIn("storm", kinds)
        self.assertIn("hail", kinds)
        gust = [i for i in items if i[0] == "wind"][0]
        self.assertEqual(gust[2], "GUSTS 29 KT")

    def test_overlay_right_column(self):
        im = G.lay_weather(2.0, 4.0, {"items": G.weather_items("Light winds and a few clouds.")})
        bb = _alpha_box(im)
        self.assertGreater(bb[0], 1280 * 0.55)
        self.assertIsNone(G.lay_weather(2.0, 4.0, {"items": []}))


class TitleAndSheetTests(unittest.TestCase):
    def test_place_title(self):
        im = G.lay_place_title(1.5, 4.0, {"name": "Jammu", "pill": "RIGHT NOW"})
        bb = _alpha_box(im)
        self.assertLess(abs((bb[0] + bb[2]) / 2 - 640), 60)        # centred
        self.assertIsNone(G.lay_place_title(1.0, 4.0, {"name": ""}))

    def test_briefing_sheet_stamp_appears_later(self):
        p = {"title": "TRANSIT BRIEFING SHEET", "rows": [["DEST", "JAMMU"], ["WIND", "VRB 02 KT"], ["VIS", "4500 M"]],
             "highlight": [1, 2], "stamp": "OVER 2 HOURS OLD", "stamp_at": 2.0}
        before, after = G.lay_sheet(1.5, 5.0, p), G.lay_sheet(3.5, 5.0, p)
        self.assertGreater(_diff(before, after), 800)
        self.assertLess(_alpha_box(after)[2], 1280 * 0.5)            # the paper sits on the left
        self.assertIsNone(G.lay_sheet(1.0, 4.0, {"rows": []}))

    def test_altitude_side_view(self):
        a = G.lay_altitude(0.5, 5.0, {"from_ft": 11000, "to_ft": 20000, "lines": [11000, 20000]})
        b = G.lay_altitude(4.5, 5.0, {"from_ft": 11000, "to_ft": 20000, "lines": [11000, 20000]})
        self.assertEqual(a.size, (1280, 720))
        self.assertGreater(_diff(a, b), 500)                          # the aircraft climbs
        self.assertIsNone(G.lay_altitude(1.0, 4.0, {}))

    def test_altitude_y_is_monotonic(self):
        self.assertLess(G.altitude_y(20000, 0, 25000), G.altitude_y(11000, 0, 25000))

    def test_end_card(self):
        im = G.lay_end_card(2.0, 4.0, {"kicker": "THE STORY OF", "title": "VISTARA FLIGHT 944"})
        rgb = np.asarray(im.convert("RGB"), dtype=np.int32)
        self.assertLess(rgb.mean(), 30)                               # black card
        red = ((rgb[..., 0] > 150) & (rgb[..., 1] < 80)).sum()
        self.assertGreater(red, 50)                                   # the number in red
        self.assertIsNone(G.lay_end_card(1.0, 4.0, {"title": ""}))


class StormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def m(self, t, **p):
        q = {"airports": ["SXR", "IXJ", "ATQ"], "fetch_tile": fake_tile, "cache": self.tmp.name}
        q.update(p)
        return F.lay_flight_map(t, 6.0, q)

    def test_storm_cells_brighten_and_drift(self):
        storms = [{"at": "IXJ", "km": 40, "label": "GUSTS 29 KT"}]
        plain, s1, s2 = self.m(2.0), self.m(2.0, storms=storms), self.m(5.0, storms=storms)
        self.assertGreater(np.asarray(s1.convert("L")).mean(), np.asarray(plain.convert("L")).mean())
        self.assertGreater(_diff(s1, s2), 1000)

    def test_storm_cells_are_seeded(self):
        storms = [{"at": "IXJ", "km": 40}]
        self.assertEqual(_diff(self.m(2.0, storms=storms), self.m(2.0, storms=storms)), 0)


if __name__ == "__main__":
    unittest.main()


class StormLookTests(unittest.TestCase):
    def test_storm_is_several_puffs_not_one_blob(self):
        import tempfile as _t
        with _t.TemporaryDirectory() as d:
            q = {"airports": ["SXR", "IXJ", "ATQ"], "fetch_tile": fake_tile, "cache": d}
            plain = np.asarray(F.lay_flight_map(2.0, 6.0, q).convert("L"), dtype=np.int32)
            st = np.asarray(F.lay_flight_map(2.0, 6.0, dict(q, storms=[{"at": "IXJ", "km": 45}])).convert("L"), dtype=np.int32)
            lift = (st - plain) > 25
            small = lift.reshape(36, 20, 64, 20).mean(axis=(1, 3)) > 0.3      # 64 x 36 grid
            seen, n = set(), 0
            for y in range(36):
                for x in range(64):
                    if small[y, x] and (y, x) not in seen:
                        n += 1
                        stack = [(y, x)]
                        while stack:
                            cy, cx = stack.pop()
                            if (cy, cx) in seen or not (0 <= cy < 36 and 0 <= cx < 64) or not small[cy, cx]:
                                continue
                            seen.add((cy, cx))
                            stack += [(cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)]
            self.assertGreaterEqual(n, 3)                         # separate cloud cells
            self.assertLess(lift.mean(), 0.08)                    # and not a wall over the map
