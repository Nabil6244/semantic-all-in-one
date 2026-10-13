"""Phase 2: the temp_trend layer (the week's highs and lows of one city as a line chart): sidecar rows, events, numbers report."""

import unittest

from weather.events import build
from weather.layers import FetchContext, get
from weather.resolve import Snapshot
from weather.sidecar import COLUMNS, SidecarError, parse_sidecar
from weather.timing import Window

from test_weather_auto_story import snapshot

HEAD = ",".join(COLUMNS) + "\n"


class TrendRows(unittest.TestCase):
    def test_a_row_for_any_covered_city_reads(self):
        rows = parse_sidecar(HEAD + 'b6,the week ahead,,trend,temp_trend,"Boston, MA","nws:forecast@Boston,MA#day1-7",,,"{""title"": ""BOSTON WEEK""}"\n')
        self.assertEqual(rows[0].type, "temp_trend")
        self.assertEqual(rows[0].data_source.days(), (1, 7))

    def test_problems_name_the_row(self):
        text = HEAD + "\n".join([
            'b1,,1,a,temp_trend,"Boston, MA","nws:forecast@Boston,MA#day1-2",,,',     # row 2: too few days
            'b1,,1,b,temp_trend,"Miami, FL","nws:forecast@Boston,MA#day1-5",,,',      # row 3: place is another city
            'b1,,1,c,temp_trend,,"nws:obs@Boston,MA",,,',                             # row 4: wrong product
            'b1,,1,d,temp_trend,,"nws:forecast@Gotham,NY#day1-5",,,',                 # row 5: unknown city
            'b1,,1,e,temp_trend,,"nws:forecast@Boston,MA#day1-5",,,"{""color"": 1}"',  # row 6: extra key it does not use
        ]) + "\n"
        with self.assertRaises(SidecarError) as cm:
            parse_sidecar(text)
        e = "\n".join(cm.exception.problems)
        for n, words in [(2, "3 to 7 days"), (3, "is not the city of the data_source"), (4, "temp_trend takes nws:forecast@"),
                         (5, "unknown city 'Gotham,NY'"), (6, "extra has color")]:
            self.assertRegex(e, rf"row {n}: .*{words}")


class TrendBuild(unittest.TestCase):
    def setUp(self):
        cov = snapshot()
        self.snap = Snapshot(prepared=cov.prepared, forecasts={"Phoenix, AZ": cov.forecasts["Phoenix, AZ"]})
        self.rows = parse_sidecar(HEAD + 'b6,,1,trend,temp_trend,"Phoenix, AZ","nws:forecast@Phoenix,AZ#day2-7",,,\n'
                                         "b6,,1,src,source_line,,,,,\n")

    def test_every_point_is_a_forecast_value_in_the_numbers_report(self):
        out = build(self.rows, self.snap, {"trend": Window(1.0, 9.0), "src": Window(1.0, 9.0)})
        (e,) = [x for x in out.events if x["type"] == "temp_trend"]
        days = self.snap.forecasts["Phoenix, AZ"]["days"][1:7]
        self.assertEqual([d["dow"] for d in e["days"]], [d["dow"] for d in days])
        self.assertEqual([d["hi_v"] for d in e["days"]], [d["high"]["value"] for d in days])
        self.assertEqual(e["days"][0]["hi"], f"{days[0]['high']['value']}°")
        self.assertEqual(e["title"], "PHOENIX, AZ · HIGHS AND LOWS")
        shown = [(ln["label"], ln["shown"]) for ln in out.report.lines if ln["layer"] == "trend"]
        n_lows = sum(1 for d in days if d["low"])
        self.assertEqual(len(shown), len(days) + n_lows)
        for ln in out.report.lines:
            self.assertEqual(ln["url"], "https://api.weather.gov/gridpoints/PSR/159,58/forecast")
            self.assertTrue(ln["issued"])
        src = next(x for x in out.events if x["type"] == "source_line")
        self.assertIn("Forecast as of", src["text"])

    def test_a_day_without_its_night_has_no_low_point(self):
        self.snap.forecasts["Phoenix, AZ"]["days"][6]["low"] = None
        out = build(self.rows, self.snap, {"trend": Window(1.0, 9.0), "src": Window(1.0, 9.0)})
        (e,) = [x for x in out.events if x["type"] == "temp_trend"]
        self.assertEqual((e["days"][-1]["lo"], e["days"][-1]["lo_v"]), ("", None))

    def test_the_forecast_already_in_the_snapshot_is_not_fetched_again(self):
        lt = get("temp_trend")
        ctx = FetchContext(snap=self.snap, now=None, nws=None)
        lt.fetch(self.rows[0], ctx)   # no client needed: the forecast is there
        ctx.snap.forecasts.clear()
        with self.assertRaises(ValueError) as cm:
            lt.fetch(self.rows[0], ctx)
        self.assertIn("row 2 (trend)", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
