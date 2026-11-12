"""Aviation style step 3: dark relief basemap, flight map (airports, routes, holding loops, callouts), clock/fuel HUD, radio lines.
No network: elevation comes from a fake tile function."""

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import ImageChops

from aviation import basemap as B
from aviation import flightmap as F
from aviation import hud as U
from aviation import router as R


def fake_tile(z, x, y):
    """A smooth mountain ridge running diagonally, sea level in one corner."""
    n = 256
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    gx, gy = (x * n + xx) / (n * 2 ** z), (y * n + yy) / (n * 2 ** z)
    ridge = 4000 * np.exp(-((gx - gy * 0.9 - 0.08) * 900) ** 2)
    return (300 + ridge + 200 * np.sin(gx * 4000) * np.cos(gy * 3000)).astype(np.float32)


def _diff(a, b):
    return sum(ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").histogram()[12:])


class ProjectionTests(unittest.TestCase):
    def test_fit_is_16_by_9_and_holds_the_points(self):
        pts = [(33.99, 74.77), (32.69, 74.84), (28.56, 77.10)]       # Srinagar, Jammu, Delhi
        bb = B.fit_bbox(pts, pad=0.15)
        x0, y0 = B.merc(bb[0], bb[3])
        x1, y1 = B.merc(bb[2], bb[1])
        self.assertAlmostEqual((x1 - x0) / (y1 - y0), 16 / 9, places=2)
        for lat, lon in pts:
            px, py = B.to_px(bb, lat, lon, 1280, 720)
            self.assertTrue(40 < px < 1240 and 30 < py < 690, (lat, lon, px, py))

    def test_north_is_up(self):
        bb = B.fit_bbox([(33.99, 74.77), (28.56, 77.10)])
        self.assertLess(B.to_px(bb, 33.99, 74.77, 1280, 720)[1], B.to_px(bb, 28.56, 77.10, 1280, 720)[1])

    def test_zoom_choice_scales_with_area(self):
        self.assertGreater(B.zoom_for(B.fit_bbox([(33.9, 74.7), (32.6, 74.8)]), 1280), B.zoom_for(B.fit_bbox([(51, 0), (25, 55)]), 1280))


class BasemapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bb = B.fit_bbox([(33.99, 74.77), (32.69, 74.84), (31.71, 74.80)])

    def tearDown(self):
        self.tmp.cleanup()

    def test_dark_desaturated_relief(self):
        im = B.relief(self.bb, (640, 360), fetch_tile=fake_tile, cache=Path(self.tmp.name)).convert("RGB")
        px = np.asarray(im, dtype=np.float32)
        self.assertLess(px.mean(), 120)                               # dark overall
        sat = (px.max(axis=2) - px.min(axis=2)).mean()
        self.assertLess(sat, 30)                                      # nearly grey
        self.assertGreater(px.std(), 8)                               # but with visible relief

    def test_cached_on_disk(self):
        calls = []

        def counting(z, x, y):
            calls.append((z, x, y))
            return fake_tile(z, x, y)
        B.relief(self.bb, (320, 180), fetch_tile=counting, cache=Path(self.tmp.name))
        n = len(calls)
        self.assertGreater(n, 0)
        B.relief(self.bb, (320, 180), fetch_tile=counting, cache=Path(self.tmp.name))
        self.assertEqual(len(calls), n)

    def test_no_tiles_gives_a_plain_dark_map(self):
        def broken(z, x, y):
            raise OSError("offline")
        im = B.relief(self.bb, (320, 180), fetch_tile=broken, cache=Path(self.tmp.name))
        self.assertEqual(im.size, (320, 180))


class FlightMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = dict(airports=["SXR", "IXJ", "ATQ"], fetch_tile=fake_tile, cache=cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def m(self, t=3.0, dur=6.0, **p):
        q = dict(self.base)
        q.update(p)
        return F.lay_flight_map(t, dur, q)

    def test_needs_places(self):
        self.assertIsNone(F.lay_flight_map(1.0, 4.0, {"airports": [], "fetch_tile": fake_tile, "cache": self.tmp.name}))
        self.assertIsNone(F.lay_flight_map(1.0, 4.0, {"airports": ["XXX"], "fetch_tile": fake_tile, "cache": self.tmp.name}))

    def test_frame_and_gold_route(self):
        im = self.m(route={"from": "SXR", "to": "IXJ", "start": 0.5, "length": 2.0})
        self.assertEqual(im.size, (1280, 720))
        rgb = np.asarray(im.convert("RGB"), dtype=np.int32)
        gold = ((rgb[..., 0] > 180) & (rgb[..., 1] > 130) & (rgb[..., 2] < 110)).sum()
        self.assertGreater(gold, 150)

    def test_route_draws_over_time(self):
        a = self.m(t=0.6, route={"from": "SXR", "to": "IXJ", "start": 0.5, "length": 2.0})
        b = self.m(t=2.6, route={"from": "SXR", "to": "IXJ", "start": 0.5, "length": 2.0})
        self.assertGreater(_diff(a, b), 800)

    def test_never_sits_still(self):
        self.assertGreater(_diff(self.m(t=1.0), self.m(t=5.0)), 1000)     # slow camera drift

    def test_holding_loops_stack_up(self):
        one = self.m(t=1.4, holding={"at": "IXJ", "laps": 3, "start": 0.5, "length": 4.0})
        three = self.m(t=5.0, holding={"at": "IXJ", "laps": 3, "start": 0.5, "length": 4.0})
        def gold(im):
            a = np.asarray(im.convert("RGB"), dtype=np.int32)
            return ((a[..., 0] > 180) & (a[..., 1] > 120) & (a[..., 2] < 110)).sum()
        g1, g3 = gold(one), gold(three)
        self.assertGreater(g3, g1 * 1.5)

    def test_holding_geometry_is_a_closed_racetrack(self):
        pts = F.racetrack_km(10.0, 4.0, heading_deg=0.0, steps=64)
        self.assertAlmostEqual(pts[0][0], pts[-1][0], places=6)
        self.assertAlmostEqual(pts[0][1], pts[-1][1], places=6)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.assertAlmostEqual(max(ys) - min(ys), 10.0 + 2 * 4.0, delta=0.3)   # legs + two turn radii
        self.assertAlmostEqual(max(xs) - min(xs), 2 * 4.0, delta=0.3)

    def test_callout_and_crossed_out_change_the_frame(self):
        plain = self.m()
        c = self.m(callouts=[{"from": "IXJ", "to": "ATQ", "label": "~100 KM", "start": 0.5}])
        x = self.m(crossed=["IXJ"])
        r = self.m(range_ring={"at": "IXJ", "km": 120})
        for other in (c, x, r):
            self.assertGreater(_diff(plain, other), 400)

    def test_distance_label_from_coordinates(self):
        self.assertEqual(F.distance_label("IXJ", "ATQ"), "~110 KM")
        self.assertEqual(F.distance_label("SXR", "DEL", unit="nm"), "~350 NM")


class HudTests(unittest.TestCase):
    def test_overlay_is_transparent_in_the_middle(self):
        im = U.lay_hud(1.0, 4.0, {"time": ("13:38", "13:40"), "fuel": (4220, 4120)})
        self.assertEqual(im.getpixel((640, 360))[3], 0)
        self.assertIsNotNone(im.getchannel("A").crop((0, 0, 400, 220)).getbbox())

    def test_values_tick_between_beats(self):
        self.assertEqual(U.fuel_at(0.0, 4.0, (4220, 4120)), 4220)
        self.assertEqual(U.fuel_at(4.0, 4.0, (4220, 4120)), 4120)
        self.assertEqual(U.time_at(2.0, 4.0, ("13:38", "13:40")), "1:39 PM")
        self.assertEqual(U.time_at(0.0, 4.0, ("12:05", "12:05")), "12:05 PM")

    def test_fuel_turns_red_when_critical(self):
        self.assertTrue(U.is_critical(540, {"final_reserve": 1150}))
        self.assertFalse(U.is_critical(4000, {"final_reserve": 1150}))

    def test_fuel_bar_drains(self):
        segs = {"trip": 1400, "contingency": 150, "alternate": 600, "final_reserve": 1150}
        full = U.lay_hud(1.0, 4.0, {"fuel": (3300, 3300), "fuel_bar": segs})
        low = U.lay_hud(1.0, 4.0, {"fuel": (900, 900), "fuel_bar": segs})
        self.assertGreater(_diff(full, low), 300)

    def test_nothing_to_show(self):
        self.assertIsNone(U.lay_hud(1.0, 4.0, {}))

    def test_hud_plan_from_narration(self):
        lines = ["Vistara 611 takes off from Srinagar.", "At 1:38 PM they have about 4,220 kg of fuel.",
                 "They turn towards Jammu.", "By 2:03 PM fuel is down to 3,040 kg and they are cleared to 4,100 feet."]
        plan = U.hud_plan(R.route_script(lines))
        self.assertIsNone(plan[0])                                   # nothing known yet: no HUD
        self.assertEqual(plan[1]["fuel"], (4220, 4220))
        # the line between two known readings ticks from one to the next
        self.assertEqual(plan[2]["fuel"][0], 4220)
        self.assertEqual(plan[2]["fuel"][1], 3040)
        self.assertEqual(plan[2]["time"], ("13:38", "14:03"))
        self.assertEqual(plan[3]["altitude"], 4100)


class RadioTests(unittest.TestCase):
    def test_two_lines_lower_left(self):
        im = U.lay_radio(1.5, 4.0, {"lines": [{"speaker": "FIRST OFFICER", "text": "Jammu, Vistara 611, request climb to 10,000 feet."},
                                             {"speaker": "JAMMU ATC", "text": "Vistara 611, climb 7,000 feet."}]})
        bb = im.getchannel("A").getbbox()
        self.assertLess(bb[0], 120)
        self.assertGreater(bb[1], 720 * 0.6)

    def test_speaker_guess(self):
        self.assertEqual(U.speaker_of("Vistara 611, runway 34, cleared to land."), "ATC")
        self.assertEqual(U.speaker_of("Jammu, Vistara 611, request climb."), "CREW")

    def test_no_lines_no_layer(self):
        self.assertIsNone(U.lay_radio(1.0, 4.0, {"lines": []}))


if __name__ == "__main__":
    unittest.main()
