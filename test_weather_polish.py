"""Phase 5 pieces owned by the integrator: the wind_flow layer (NWS forecast wind as moving streaks)."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from weather.cache import HttpCache
from weather.events import build
from weather.layers.wind import COMPASS, mph_range, wind_text
from weather.nws import NwsClient
from weather.resolve import prepare
from weather.sidecar import parse_sidecar
from weather.timing import Window

from test_weather_data import DALLAS_ROUTES, FakeNet

UTC = timezone.utc
HEAD = "beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"


class Wind(unittest.TestCase):
    def test_speed_and_direction_text(self):
        self.assertEqual(mph_range("10 to 15 mph"), (10, 15))
        self.assertEqual(mph_range("5 mph"), (5, 5))
        self.assertEqual(mph_range("Calm"), (0, 0))
        self.assertEqual(wind_text("S", "10 to 15 mph"), "S 10–15 MPH")
        self.assertEqual(wind_text("NW", "5 mph"), "NW 5 MPH")
        self.assertEqual(wind_text("N", "0 mph"), "CALM")
        self.assertEqual((COMPASS["N"], COMPASS["E"], COMPASS["SSW"]), (0.0, 90.0, 202.5))

    def test_a_wind_row_draws_the_forecast_wind_and_reports_it(self):
        with tempfile.TemporaryDirectory() as d:
            now = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)
            client = NwsClient("me@example.com", cache=HttpCache(Path(d), now=lambda: now), fetch=FakeNet(DALLAS_ROUTES))
            rows = parse_sidecar(HEAD + 'b1,,1,w,wind_flow,"Dallas, TX","nws:forecast@Dallas,TX#day2",,,\n')
            snap = prepare(rows, client, now=now)
            out = build(rows, snap, {"w": Window(1.0, 5.0)})
        e = out.events[0]
        self.assertEqual((e["type"], e["label"], e["from_deg"], e["mph"]), ("wind_flow", "S 10–15 MPH", 180.0, 15))
        self.assertEqual(out.report.lines[0]["shown"], "S 10–15 MPH")
        self.assertTrue(out.report.lines[0]["url"].endswith("/forecast"))

    def test_a_range_of_days_is_refused(self):
        from weather.sidecar import SidecarError

        with self.assertRaises(SidecarError) as cm:
            parse_sidecar(HEAD + 'b1,,1,w,wind_flow,"Dallas, TX","nws:forecast@Dallas,TX#day1-3",,,\n')
        self.assertIn("row 2", cm.exception.problems[0])


if __name__ == "__main__":
    unittest.main()


class FootageLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = Path(self.tmp.name)
        for rel in ("storms/lightning over field.mp4", "storms/supercell.mov", "rain/raindrops window.mp4", "sunny/beach palms.mp4",
                    "misc/b-roll 01.mp4", "rain/notes.txt", "snow/.hidden.mp4"):
            (self.lib / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.lib / rel).write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_clips_are_labelled_by_the_words_in_their_names(self):
        from weather.footage_library import index, library_summary

        clips = {c.path.name: c.condition for c in index(self.lib)}
        self.assertEqual(clips, {"lightning over field.mp4": "storm", "supercell.mov": "storm", "raindrops window.mp4": "rain",
                                 "beach palms.mp4": "sun", "b-roll 01.mp4": None})
        self.assertEqual(library_summary(self.lib), {"storm": 2, "rain": 1, "sun": 1, "unlabelled": 1})

    def test_stock_requests_become_your_clips_each_used_once(self):
        from weather.footage_library import prefer_library

        beats = ("beat,row,vo_anchor,mode,asset,why\n"
                 "b2,beat,x,footage,,\nb2,clip,,,stock_video:dark storm clouds over farmland,\nb2,clip,,,stock_video:lightning at night,\n"
                 "b2,clip,,,stock_video:thunderstorm rolling in,\nb3,clip,,,stock_video:a quiet street,\nb3,clip,,,media/mine.mp4,\n")
        out, notes = prefer_library(beats, self.lib)
        assets = [r.split(",")[4] for r in out.splitlines()[1:]]
        self.assertTrue(assets[1].endswith("supercell.mov") or assets[1].endswith("lightning over field.mp4"))
        self.assertTrue(assets[2].endswith("lightning over field.mp4") or assets[2].endswith("supercell.mov"))
        self.assertNotEqual(assets[1], assets[2])
        self.assertEqual(assets[3], "stock_video:thunderstorm rolling in")   # two storm clips only: the third stays stock
        self.assertEqual(assets[4], "stock_video:a quiet street")            # no weather in the request: stock
        self.assertEqual(assets[5], "media/mine.mp4")
        self.assertEqual(len(notes), 2)

    def test_no_library_changes_nothing(self):
        from weather.footage_library import prefer_library

        self.assertEqual(prefer_library("beat,row,asset\nb1,clip,stock_video:rain\n", self.lib / "missing"), ("beat,row,asset\nb1,clip,stock_video:rain\n", []))
