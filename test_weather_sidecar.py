"""weather_layers.csv, the layer timing on the narration, and the events + numbers report built from a snapshot."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from weather.cache import HttpCache
from weather.events import POP_SHOWN_FROM, build, source_text
from weather.nws import NwsClient
from weather.resolve import prepare
from weather.sidecar import COLUMNS, SidecarError, parse_data_source, parse_sidecar, rows_to_csv
from weather.timing import Window, layer_windows

from test_weather_data import DALLAS_ROUTES, FakeNet, fixture

HEAD = ",".join(COLUMNS) + "\n"
UTC = timezone.utc


def errs(text):
    try:
        parse_sidecar(text)
    except SidecarError as exc:
        return "\n".join(exc.problems)
    raise AssertionError("expected problems")


class Sidecar(unittest.TestCase):
    def test_a_valid_file_reads_and_writes_back(self):
        text = HEAD + 'b1,Dallas stays hot,,dal,temp_marker,"Dallas, TX","nws:forecast@Dallas,TX#day2",4,,"{""kind"": ""low""}"\n' \
                      "b1,,2.5,src,source_line,,,,end,\n"
        rows = parse_sidecar(text)
        self.assertEqual([r.id for r in rows], ["dal", "src"])
        self.assertEqual(rows[0].data_source.days(), (2, 2))
        self.assertEqual(rows[0].hold, 4.0)
        self.assertEqual(rows[0].extra, {"kind": "low"})
        self.assertEqual(rows[1].until, "end")
        self.assertEqual(rows[1].line, 3)
        self.assertEqual([r.__dict__ for r in parse_sidecar(rows_to_csv(rows))], [r.__dict__ for r in rows])

    def test_every_problem_names_its_row(self):
        text = HEAD + "\n".join([
            "b1,,1,a,lightning,,,,,",                                                     # row 2: unknown type
            'b1,,1,b,temp_marker,,"nws:forecast@Gotham,NY#day1",,,',                    # row 3: unknown city
            "b1,,1,c,forecast_strip,,nws:forecast@Dallas,TX#day1-2,,,",                 # row 4: (unquoted comma splits the cell)
            'b1,,1,d,forecast_strip,,"nws:forecast@Dallas,TX#day1-2",,,',               # row 5: too few days
            'b1,,1,e,now_card,,"nws:forecast@Dallas,TX#day1",,,',                       # row 6: wrong product for the type
            "b1,,1,f,alert_area,,nws:alerts@ZZ,,,",                                    # row 7: not a state
            "b1,,,g,source_line,,,,,",                                                 # row 8: no time
            'b1,,1,h,temp_marker,,"nws:forecast@Dallas,TX#day1",,,"{""color"": 1}"',    # row 9: extra key it does not use
            'b1,,1,h2,temp_marker,"Miami, FL","nws:forecast@Dallas,TX#day1",,,',        # row 10: place != data city
            "b1,,1,i,satellite,,gibs:geocolor@yesterday,,,",                           # row 11: bad time
            "b1,,1,j,source_line,,nws:alerts@TX,,,",                                   # row 12: source_line takes none
            "b1,,1,j,source_line,,,,,",                                                # row 13: ok
            "b1,,1,j,source_line,,,,,",                                                # row 14: duplicate of 13
        ]) + "\n"
        e = errs(text)
        for n, words in [(2, "unknown type 'lightning'"), (3, "unknown city 'Gotham,NY'"), (5, "3 to 7 days"), (6, "now_card takes nws:obs@"),
                         (7, "takes a state"), (8, "needs vo_anchor"), (9, "extra has color"), (10, "is not the city of the data_source"),
                         (11, "latest or a UTC time"), (12, "source_line takes no data_source"), (14, "duplicate id 'j' (also row 13)")]:
            self.assertIn(f"row {n}", e)
            self.assertRegex(e, rf"row {n}[^\n]*{__import__('re').escape(words)}")

    def test_an_unknown_column_or_a_missing_header_column_stops_at_once(self):
        self.assertIn("unknown column 'colour'", errs("beat,id,type,colour\nb1,a,source_line,red\n"))
        self.assertIn("no type column", errs("beat,id\nb1,a\n"))
        self.assertIn("has no layers", errs(HEAD))

    def test_data_source_grammar(self):
        ds = parse_data_source("nws:forecast@Los Angeles,CA#day1-7")
        self.assertEqual((ds.provider, ds.product, ds.target, ds.selector), ("nws", "forecast", "Los Angeles,CA", "day1-7"))
        self.assertEqual(ds.days(), (1, 7))
        for bad in ("forecast@Dallas", "nws:forecast", "NWS:forecast@x"):
            with self.assertRaises(ValueError):
                parse_data_source(bad)
        with self.assertRaises(ValueError):
            parse_data_source("nws:forecast@Dallas,TX#day5-2").days()


def small_plan(words):
    from hybrid.beat_csv import plan_from_csv

    csv = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
           'b1,beat,good morning everyone,map,hold,,Texas,region,,,"good morning everyone dallas stays hot this week",,,,,,,,,,,one\n'
           'b2,beat,here is the outlook,map,hold,,Texas,region,,,"here is the outlook for dallas and that is all",,,,,,,,,,,two\n')
    return plan_from_csv(csv, words, 10.0)


WORDS = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("good morning everyone dallas stays hot this week here is the outlook for dallas and that is all".split())]


class Timing(unittest.TestCase):
    def test_layers_appear_on_their_words_inside_their_beat_and_stay_until_it_ends(self):
        plan = small_plan(WORDS)
        rows = parse_sidecar(HEAD + 'b1,dallas stays hot,,a,temp_marker,,"nws:forecast@Dallas,TX#day1",,,\n'
                                    'b2,for dallas,,b,forecast_strip,,"nws:forecast@Dallas,TX#day1-5",,,\n'
                                    "b1,,0.5,c,source_line,,,2,,\nb1,,0,d,satellite,,gibs:geocolor@latest,,end,\n")
        w = layer_windows(rows, plan, WORDS)
        b1, b2 = plan.beats
        self.assertEqual(w["a"], Window(1.5, b1.end))           # "dallas stays hot" is spoken at 1.5 s
        self.assertEqual(w["b"].t_in, 6.0)                       # the SECOND "dallas", the one inside b2
        self.assertEqual(w["b"].t_out, b2.end)
        self.assertEqual(w["c"], Window(0.5, 2.5))               # hold
        self.assertEqual(w["d"].t_out, plan.duration)            # until end

    def test_words_not_spoken_in_the_beat_or_a_time_outside_it_name_the_row(self):
        plan = small_plan(WORDS)
        with self.assertRaises(SidecarError) as cm:
            layer_windows(parse_sidecar(HEAD + 'b1,the outlook,,a,temp_marker,,"nws:forecast@Dallas,TX#day1",,,\n'
                                               "b2,,1,b,source_line,,,,,\nb9,,1,c,source_line,,,,,\n"), plan, WORDS)
        e = "\n".join(cm.exception.problems)
        self.assertRegex(e, r"row 2 \(a\): it starts at 5.00s, outside its beat b1 \(0.00-4.00s\)")   # spoken, but in b2
        self.assertRegex(e, r"row 3 \(b\): it starts at 1.00s, outside its beat b2")
        self.assertRegex(e, r"row 4 \(c\): beat 'b9' is not in beats.csv")
        with self.assertRaises(SidecarError) as cm:
            layer_windows(parse_sidecar(HEAD + 'b1,zebra crossing,,a,temp_marker,,"nws:forecast@Dallas,TX#day1",,,\n'), plan, WORDS)
        self.assertRegex(cm.exception.problems[0], r"row 2 \(a\): vo_anchor 'zebra crossing' is not spoken in beat b1")


class Events(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        now = datetime(2026, 10, 12, 21, 0, tzinfo=UTC)
        client = NwsClient("me@example.com", cache=HttpCache(Path(self.tmp.name), now=lambda: now), fetch=FakeNet(DALLAS_ROUTES))
        self.rows = parse_sidecar(HEAD + "\n".join([
            "b1,,0,sat,satellite,,gibs:geocolor@latest,,end,",
            'b1,,1,dal,temp_marker,"Dallas, TX","nws:forecast@Dallas,TX#day1",,,',
            'b1,,1,lo,temp_marker,"Dallas, TX","nws:forecast@Dallas,TX#day2",,,"{""kind"": ""low""}"',
            'b1,,1,strip,forecast_strip,"Dallas, TX","nws:forecast@Dallas,TX#day1-5",,,',
            'b1,,1,now,now_card,"Dallas, TX","nws:obs@Dallas,TX",,,',
            "b1,,1,al,alert_area,TX,nws:alerts@TX,,,",
            "b1,,1,src,source_line,,,,,",
            "b2,,6,src2,source_line,,,,,",
        ]) + "\n")
        self.snap = prepare(self.rows, client, now=now, gibs_get=lambda u: fixture("gibs_geocolor_domain.xml").decode())
        self.windows = {r.id: Window(0.0 if r.id == "sat" else (6.0 if r.id == "src2" else 1.0), 10.0 if r.id in ("sat", "src2") else 5.0) for r in self.rows}

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_number_on_screen_is_in_the_report_with_its_source(self):
        out = build(self.rows, self.snap, self.windows)
        ev = {e["id"]: e for e in out.events}
        f = self.snap.forecasts["Dallas, TX"]
        self.assertEqual(ev["wx_dal"]["temp"], f"{f['days'][0]['high']['value']}°")
        self.assertEqual(ev["wx_lo"]["tag"], f"{f['days'][1]['dow']} LOW")
        self.assertEqual(ev["wx_lo"]["temp"], f"{f['days'][1]['low']['value']}°")
        self.assertEqual(ev["wx_now"]["temp"], "88°")
        self.assertEqual(ev["wx_now"]["foot"], "Observed 3:55 PM CDT · KDFW")
        shown = {(ln["layer"], ln["shown"]) for ln in out.report.lines}
        for e in out.events:   # every temperature drawn is a line of the report
            for t in [e.get("temp")] + [d[k] for d in e.get("days", []) for k in ("hi", "lo", "pop") if d[k]]:
                if t:
                    self.assertIn((e["id"][3:], t), shown, (e["id"], t))
        for ln in out.report.lines:
            self.assertTrue(ln["url"].startswith("https://api.weather.gov/"), ln)
            self.assertTrue(ln["issued"], ln)

    def test_a_small_chance_of_rain_is_not_printed(self):
        out = build(self.rows, self.snap, self.windows)
        strip = next(e for e in out.events if e["type"] == "forecast_strip")
        days = self.snap.forecasts["Dallas, TX"]["days"][:5]
        for d, shown in zip(days, strip["days"]):
            best = max([p["value"] for p in (d.get("pop"), d.get("pop_night")) if p] or [0])
            self.assertEqual(shown["pop"], f"{best}%" if best >= POP_SHOWN_FROM else "")

    def test_alert_areas_become_pakmap_fill_events_and_a_legend(self):
        out = build(self.rows, self.snap, self.windows)
        self.assertEqual(len(out.fills), 3)
        self.assertTrue(all(f["type"] == "fill" and f["polys"] and f["t_in"] == 1.0 for f in out.fills))
        legend = next(e for e in out.events if e["type"] == "alert_legend")
        self.assertIn({"label": "FLOOD WARNING", "color": "#00FF00"}, legend["items"])

    def test_the_satellite_layer_is_its_own_provider_per_picture_time(self):
        out = build(self.rows, self.snap, self.windows)
        sat = out.satellite[0]
        self.assertEqual(sat["provider"]["id"], "wx_geocolor_20261012_210000")
        self.assertIn("/2026-10-12T21:00:00Z/", sat["provider"]["urlTemplate"])
        self.assertTrue(any("GIBS" in c for c in out.credits))
        self.assertTrue(out.credits[0].startswith("Weather data: National Weather Service"))

    def test_source_lines_name_what_is_on_screen_with_them(self):
        out = build(self.rows, self.snap, self.windows)
        ev = {e["id"]: e for e in out.events}
        self.assertEqual(ev["wx_src"]["text"], "Data: National Weather Service · Forecast as of Oct 12, 1:26 PM CDT · Observed 3:55 PM CDT"
                                                " · Alerts as of 4:00 PM CDT · Satellite: NASA GIBS / NOAA GOES-East, 4:00 PM CDT")
        self.assertEqual(ev["wx_src2"]["text"], "Satellite: NASA GIBS / NOAA GOES-East, 5:00 PM EDT")   # only the satellite is on with it
        self.assertEqual(source_text([]), "Data: National Weather Service")


if __name__ == "__main__":
    unittest.main()
