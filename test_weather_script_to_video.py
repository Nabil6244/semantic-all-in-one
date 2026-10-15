"""Weather: script + voiceover -> video with no CSV (docs/weather/script_to_video_plan.md).

The format and the editing style are read from the script (weather.autopick); the beats are made from the narration with footage
where it describes impacts (weather.intel.beats); the card needs no CSV and no Fetch data step (weather.app_section); the plan is
checked before the render (weather.selfcheck). No AI provider or network is reached on this path."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

from hybrid.plan import validate_plan
from weather.autopick import detect_format, resolve_format, resolve_style, style_for
from weather.intel.beats import FOOTAGE_SHARE, footage_request, plan_from_narration

SCRIPT = ("A tornado tore through Newberry County, South Carolina, early on October 11, 2026. "
          "The National Weather Service issued a tornado warning at 6:05 AM. "
          "The storm was moving northeast at 40 miles per hour. "
          "Roofs were ripped off homes and trees were snapped along the path. "
          "Debris was scattered across the roads for miles. "
          "Take cover. "
          "Crews worked through the day to restore power to thousands of residents without power. "
          "Survey teams rated the tornado an EF2 with winds of 115 miles per hour. "
          "Families in Newberry are now starting the cleanup. "
          "Stay safe out there.")


def words_of(text: str, wps: float = 2.6):
    out, t = [], 0.0
    for w in text.split():
        out.append((w, round(t, 3), round(t + 0.3, 3)))
        t += 1.0 / wps + (0.35 if w.endswith(".") else 0.0)
    return out, t + 0.5


class TheFormatAndStyleAreReadFromTheScript(unittest.TestCase):
    def test_formats(self):
        today = date(2026, 10, 15)
        self.assertEqual(detect_format("Severe storms are unfolding right now across Texas. A tornado warning is in effect until 3:15 PM.", today), "news")
        self.assertEqual(detect_format("Tomorrow, highs will reach 95 in Dallas. Expect a chance of storms this weekend, with lows near 70 tonight.", today), "forecast")
        self.assertEqual(detect_format("In August 2017 Hurricane Harvey stalled over Houston. Looking back, the cleanup took years and the totals "
                                       "were historic.", today), "post")
        self.assertEqual(detect_format("", today), "news")

    def test_style_follows_the_format_and_an_explicit_pick_wins(self):
        self.assertEqual(style_for("news"), "teamplate")
        self.assertEqual(style_for("post"), "teamplate")
        self.assertEqual(style_for("forecast"), "classic")
        self.assertEqual(resolve_style("classic", "news"), "classic")
        self.assertEqual(resolve_style("auto", "news"), "teamplate")
        self.assertEqual(resolve_format("forecast", "A tornado is on the ground right now."), "forecast")
        self.assertEqual(resolve_format("auto", "A tornado is on the ground right now."), "news")


class BeatsFromTheNarration(unittest.TestCase):
    def setUp(self):
        self.words, self.dur = words_of(SCRIPT)
        self.notes = []
        self.plan = plan_from_narration(self.words, self.dur, self.notes, script=SCRIPT)

    def test_the_plan_is_valid_and_covers_the_narration(self):
        self.assertEqual(validate_plan(self.plan), [])
        self.assertEqual(self.plan.beats[0].start, 0.0)
        self.assertAlmostEqual(self.plan.beats[-1].end, self.dur, places=3)

    def test_impacts_become_footage_and_data_stays_on_the_map(self):
        foot = [b for b in self.plan.beats if b.mode == "footage"]
        self.assertTrue(foot, self.notes)
        said = " ".join(b.narration for b in foot)
        self.assertIn("Roofs were ripped off", said)
        self.assertIn("Debris was scattered", said)
        maps = " ".join(b.narration for b in self.plan.beats if b.mode == "map")
        self.assertIn("6:05 AM", maps)                 # a time / warning is read on the map
        self.assertIn("115 miles per hour", maps)      # a number is read on the map
        asks = [c.asset for b in foot for c in b.clips]
        self.assertTrue(all(a.startswith("stock_video:") for a in asks))
        self.assertIn("stock_video:storm damaged roof", asks)
        self.assertTrue(any("without power" in b.narration for b in foot) or "stock_video:utility crew repairing power lines" not in asks)

    def test_the_opening_and_the_closing_are_map_beats_on_the_story_region(self):
        first, last = self.plan.beats[0], self.plan.beats[-1]
        self.assertEqual((first.mode, last.mode), ("map", "map"))
        self.assertEqual(first.cam_place, "South Carolina")
        self.assertEqual([c.action for c in first.camera][:1], ["start"])

    def test_a_short_line_with_nothing_to_show_joins_the_footage_next_to_it(self):
        self.assertTrue(any(b.mode == "footage" and "Take cover." in b.narration for b in self.plan.beats))

    def test_footage_is_capped_and_the_plan_is_the_same_every_time(self):
        foot = sum(b.end - b.start for b in self.plan.beats if b.mode == "footage")
        self.assertLessEqual(foot, FOOTAGE_SHARE * self.dur + 1e-6)
        again = plan_from_narration(self.words, self.dur, [], script=SCRIPT)
        key = lambda p: [(b.id, b.mode, b.start, b.end, b.cam_place, [c.asset for c in b.clips]) for b in p.beats]  # noqa: E731
        self.assertEqual(key(again), key(self.plan))

    def test_a_beat_that_names_no_place_keeps_the_camera_where_the_story_is(self):
        text = ("Storms hit Pecos County, Texas this afternoon. A warning was issued at 2:30 PM for Pecos County. "
                "The storm was moving northeast at 25 miles per hour, near the small town. It also carries quarter size hail and 60 mile per hour winds. "
                "Radar showed rotation at 2:40 PM. Then the storm weakened by 3 PM. Stay safe.")
        words, dur = words_of(text, wps=1.6)
        plan = plan_from_narration(words, dur, [], script=text)
        middle = [b for b in plan.beats[1:-1] if b.mode == "map"]
        self.assertTrue(middle)
        self.assertTrue(all(b.cam_place != "United States" for b in middle))
        self.assertTrue(all("," in b.cam_place for b in middle), [b.cam_place for b in middle])   # Pecos County's point, close up

    def test_requests_only_name_what_a_camera_can_film(self):
        self.assertEqual(footage_request("Roofs were ripped off homes."), "storm damaged roof")
        self.assertEqual(footage_request("The forecast calls for 3 inches."), None)


class AComparisonDateIsNotTheEventDate(unittest.TestCase):
    """Project #007 (2026-10-15): "a previous crest of 17.6 feet back on May 9th, 2019" made the whole story May 2019 (radar, warnings
    and crests from 2019) although the script is about storms "unfolding right now"."""

    def test_a_previous_crest_year_does_not_date_a_story_happening_now(self):
        from datetime import datetime, timezone

        from weather.intel.understand import Segment, understand

        u = understand([Segment("b1", "map", "Severe storms are unfolding right now across Oklahoma."),
                        Segment("b2", "map", "The river is at 18 feet, compared to a previous crest of 17.6 feet back on May 9th, 2019."),
                        Segment("b3", "map", "It will crest Thursday evening.")],
                       recorded_at=datetime(2026, 10, 14, 20, tzinfo=timezone.utc))
        self.assertEqual(u.years, [])
        self.assertTrue(any("2019" in r for r in u.reference))
        may = [d for d in u.dates if d.day == "2019-05-09"]
        self.assertTrue(may and all(d.reference for d in may))   # kept, but only as a comparison
        thursday = next(d for d in u.dates if d.text == "thursday")
        self.assertTrue(thursday.day.startswith("2026-10"))

    def test_a_story_told_in_the_past_keeps_its_year(self):
        from weather.intel.understand import Segment, understand

        u = understand([Segment("b1", "map", "Back in August 2017, Hurricane Harvey stalled over Houston."),
                        Segment("b2", "map", "The rain fell for days.")])
        self.assertEqual([y for y, _s in u.years], [2017])


class TheCardNeedsNoCsv(unittest.TestCase):
    def app(self, root: Path, script: str = ""):
        return NS(_workspace=NS(root=str(root)), _main_script_text=lambda: script)

    def test_no_csv_is_a_plan_when_intelligence_is_on(self):
        import json

        from weather import app_section

        tmp = Path(tempfile.mkdtemp())
        (tmp / "weather").mkdir()
        self.assertTrue(app_section.has_plan(self.app(tmp)))
        self.assertTrue(app_section.is_auto(app_section.project(self.app(tmp))))
        (tmp / "weather" / "weather.json").write_text(json.dumps({"intelligence": False}), encoding="utf-8")
        self.assertFalse(app_section.has_plan(self.app(tmp)))

    def test_the_script_page_reaches_the_plan_but_never_replaces_your_own_script(self):
        from weather import app_section

        tmp = Path(tempfile.mkdtemp())
        (tmp / "weather").mkdir()
        p = app_section.project(self.app(tmp))
        self.assertIsNone(app_section.sync_script(self.app(tmp, "First version."), p))
        self.assertEqual((p.root / "script.txt").read_text(encoding="utf-8").strip(), "First version.")
        self.assertIsNone(app_section.sync_script(self.app(tmp, "Second version."), p))   # the app's own copy follows the Script page
        self.assertEqual((p.root / "script.txt").read_text(encoding="utf-8").strip(), "Second version.")
        (p.root / "script.txt").write_text("My own script.\n", encoding="utf-8")
        note = app_section.sync_script(self.app(tmp, "Third version."), p)
        self.assertIn("your own file", note)
        self.assertEqual((p.root / "script.txt").read_text(encoding="utf-8").strip(), "My own script.")

    def test_a_csv_project_never_gets_a_script_written(self):
        from weather import app_section

        tmp = Path(tempfile.mkdtemp())
        (tmp / "weather").mkdir()
        (tmp / "weather" / "beats.csv").write_text("beat,row\n", encoding="utf-8")
        p = app_section.project(self.app(tmp))
        self.assertIsNone(app_section.sync_script(self.app(tmp, "A script."), p))
        self.assertFalse((p.root / "script.txt").exists())


class TheChecksBeforeTheRender(unittest.TestCase):
    def test_a_still_stretch_is_measured(self):
        from hybrid.plan import Beat, CameraStep, HybridPlan

        from weather.selfcheck import checks, longest_still

        plan = HybridPlan(duration=30.0, beats=[Beat("b1", "map", 0.0, 30.0, camera=[CameraStep("start", "Texas", "region", 0.0),
                                                                                        CameraStep("push_in", t=2.0, dur=4.0)])])
        payload = NS(events=[], fills=[], rasters=[], satellite=[], report=NS(lines=[]))
        still, at = longest_still(plan, payload)
        self.assertAlmostEqual(still, 24.0)
        self.assertAlmostEqual(at, 6.0)
        self.assertFalse(checks(plan, payload)[0][0])


class NoAiOnThisPath(unittest.TestCase):
    def test_script_to_plan_reaches_no_ai_provider_and_no_network(self):
        from enoch_template_testutil import NoPaidCalls
        from test_weather_intel import NOW, Replay
        from weather.generate import WeatherProject, plan_layers
        from weather.intel import engine

        words, dur = words_of(SCRIPT)
        tmp = Path(tempfile.mkdtemp())
        p = WeatherProject(tmp / "weather")
        p.root.mkdir()
        (p.root / "script.txt").write_text(SCRIPT, encoding="utf-8")
        with NoPaidCalls():
            plan, text = engine.project_plan(p, words, dur, [])
            self.assertEqual(text, "")
            engine.run(p, plan, words, now=NOW, get_text=Replay().text, get_bytes=Replay().bytes)
            plan2, _rows, _snap, _payload = plan_layers(p, words, dur, now=NOW, edit_style="teamplate")
        self.assertEqual(validate_plan(plan2), [])
        self.assertFalse(p.beats_csv.exists() or p.layers_csv.exists())


if __name__ == "__main__":
    unittest.main()
