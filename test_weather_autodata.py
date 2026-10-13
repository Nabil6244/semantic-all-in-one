"""A News / Post-Event plan with no storm data gets it from the event its own script names (weather.autodata): radar and warnings of
the same window, the day's storm reports and a counter, source lines, and the satellite picture of the storm day. No network."""

import csv
import io
import tempfile
import unittest
from pathlib import Path

from weather.autodata import detect_event, ensure_storm_data
from weather.autofix import repair_layers
from weather.generate import WeatherProject

BEATS = ("beat,row,vo_anchor,mode,type,id,place,frame,label,sub,text,role,kind,value_from,value_to,format,anchor,until,hold,asset,dur,why\n"
         'b1,beat,A tornado carrying estimated,map,,,South Carolina,region,,,"A tornado carrying estimated winds of 115 mph struck Newberry County, South Carolina, on Sunday, October 11, 2026.",,,,,,,,,,,open\n'
         'b2,beat,The storm moved through,footage,,,,,,,"The storm moved through as people slept.",,,,,,,,,,,feel it\n'
         "b2,clip,,,,,,,,,,,,,,,,,,stock_video:dark storm clouds rolling,,why\n"
         'b3,beat,Warnings went out across,map,,,South Carolina,region,,,"Warnings went out across the Midlands as the line of storms crossed the state.",,,,,,,,,,,warnings\n'
         'b4,beat,Survey teams later confirmed,map,,,South Carolina,region,,,"Survey teams later confirmed several tornadoes in Allendale and Barnwell counties.",,,,,,,,,,,reports\n')
LAYERS = ("beat,vo_anchor,t,id,type,place,data_source,hold,until,extra\n"
          "b1,A tornado carrying estimated,,sat1,satellite,,gibs:geocolor@latest,,end,\n"
          'b1,A tornado carrying estimated,,head1,headline,,,7,,"{""kicker"": ""STORM SURVEY"", ""title"": ""Tornado confirmed"", ""sub"": ""OCTOBER 11"", ""tone"": ""forecast""}"\n')


def rows_of(text):
    return list(csv.DictReader(io.StringIO(text)))


class FindsTheEvent(unittest.TestCase):
    def test_date_and_state_from_the_script(self):
        ev = detect_event("A tornado struck Newberry County, South Carolina, on Sunday, October 11, 2026. Georgia too.")
        self.assertEqual(ev.day, "2026-10-11")
        self.assertEqual(ev.states, ["SC", "GA"])
        self.assertEqual(ev.window, "2026-10-11T10:00Z..2026-10-12T04:00Z")

    def test_no_date_no_event(self):
        self.assertIsNone(detect_event("A tornado struck somewhere on Sunday."))


class AddsTheStormData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = WeatherProject(Path(self.tmp.name) / "w")
        self.p.root.mkdir()
        self.p.beats_csv.write_text(BEATS, encoding="utf-8")
        self.p.layers_csv.write_text(LAYERS, encoding="utf-8")
        (self.p.root / "resolved.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_radar_warnings_reports_counter_and_the_storm_day_satellite(self):
        notes = []
        self.assertTrue(ensure_storm_data(self.p, "news", notes))
        got = {r["id"]: r for r in rows_of(self.p.layers_csv.read_text(encoding="utf-8"))}
        self.assertEqual(got["auto_radar"]["data_source"], "iem:radar@2026-10-11T10:00Z..2026-10-12T04:00Z#n0q")
        self.assertEqual(got["auto_warnings"]["data_source"], "iem:warnings@2026-10-11T10:00Z..2026-10-12T04:00Z#TO,SV")
        self.assertEqual(got["auto_radar"]["beat"], "b3")                      # the map beat about the storm, never footage (b2)
        self.assertEqual(got["auto_warnings"]["beat"], "b3")                   # same beat, same window
        self.assertEqual(got["auto_reports"]["data_source"], "spc:reports@2026-10-11#tornado")
        self.assertEqual(got["auto_count"]["data_source"], "spc:reports@2026-10-11#tornado")
        self.assertEqual(got["auto_reports"]["beat"], "b4")                    # the beat about what was confirmed
        self.assertEqual(got["sat1"]["data_source"], "gibs:geocolor@2026-10-11T19:00Z")
        self.assertIn('"news"', got["head1"]["extra"])                         # a news headline is red, not the forecast blue
        self.assertTrue(any(r["type"] == "source_line" and r["beat"] == "b3" for r in got.values()))
        self.assertFalse((self.p.root / "resolved.json").exists())             # fetched again with the new graphics
        self.assertTrue(notes)
        kept = repair_layers(self.p.layers_csv.read_text(encoding="utf-8"), [])
        self.assertEqual(len(kept), len(got))                                   # every added row is valid as written

    def test_twice_adds_nothing_more(self):
        ensure_storm_data(self.p, "news", [])
        once = self.p.layers_csv.read_text(encoding="utf-8")
        self.assertFalse(ensure_storm_data(self.p, "news", []))
        self.assertEqual(self.p.layers_csv.read_text(encoding="utf-8"), once)

    def test_a_forecast_or_a_plan_that_has_data_is_left_alone(self):
        self.assertFalse(ensure_storm_data(self.p, "forecast", []))
        self.p.layers_csv.write_text(LAYERS + "b3,Warnings went out,,r,radar,,iem:radar@2026-10-11T10:00Z..2026-10-11T22:00Z#n0q,,,\n",
                                     encoding="utf-8")
        self.assertFalse(ensure_storm_data(self.p, "news", []))

    def test_no_date_in_the_script_says_so_and_changes_nothing(self):
        self.p.beats_csv.write_text(BEATS.replace("on Sunday, October 11, 2026", "on Sunday"), encoding="utf-8")
        notes = []
        self.assertFalse(ensure_storm_data(self.p, "news", notes))
        self.assertEqual(self.p.layers_csv.read_text(encoding="utf-8"), LAYERS)
        self.assertTrue(any("date" in n for n in notes))


class Prompts(unittest.TestCase):
    def test_the_script_prompt_asks_for_what_the_app_needs(self):
        from weather.app_section import script_prompt_text

        text = script_prompt_text("news")
        self.assertIn("FORMAT: NEWS", text)
        for need in ("FULL DATE", "Spell the state out", "miles per hour", "150 spoken words per minute"):
            self.assertIn(need, text)
        self.assertIn("FORMAT: POST-EVENT", script_prompt_text("post"))

    def test_a_script_written_that_way_gives_the_event(self):
        ev = detect_event("On Sunday, October 11, 2026, a tornado tore through Newberry County, South Carolina.")
        self.assertEqual((ev.day, ev.states), ("2026-10-11", ["SC"]))

    def test_the_csv_prompts_read_the_event_from_the_script_and_require_data(self):
        root = Path(__file__).resolve().parent / "weather" / "prompts"
        for name in ("news_csv_prompt.txt", "post_event_csv_prompt.txt"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertIn("read the event from the script itself", text)
            self.assertIn("THE DATA IS THE POINT OF THIS VIDEO", text)


if __name__ == "__main__":
    unittest.main()
