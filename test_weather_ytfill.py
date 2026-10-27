"""YouTube news footage in Weather and Weather Teamplate (weather/ytfill.py). No network: the harvest is a stand-in."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

from hybrid.plan import Beat, CameraStep, Clip, HybridPlan
from weather import generate as wgen
from weather.footage import footage_problems
from weather.newsdoc.harvest import Harvest, Run
from weather.ytfill import enabled, fill_from_youtube, wanted


def plan():
    return HybridPlan(duration=40.0, beats=[
        Beat(id="b1", mode="map", start=0, end=10, camera=[CameraStep("start", "Texas", "region")]),
        Beat(id="b2", mode="footage", start=10, end=20, clips=[Clip("stock_video:flooded street"), Clip("stock_video:documents on a desk")]),
        Beat(id="b3", mode="footage", start=20, end=30, clips=[Clip("stock_video:storm damaged roof"), Clip("my_clips/own.mp4")]),
        Beat(id="b4", mode="footage", start=30, end=40, clips=[Clip("stock_video:waves crashing over a seawall")])])


def story(category="flood"):
    lines = [NS(span_start=0.0, span_end=20.0, part=0), NS(span_start=20.0, span_end=40.0, part=1)]
    return NS(category=category, lines=lines)


class Fill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = wgen.WeatherProject(self.root)
        for n in ("a", "b", "c"):
            (self.root / f"run_{n}.mp4").write_bytes(b"x")
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def runs(self):
        mk = lambda n, part: Run(path=f"run_{n}.mp4", video_id=f"id_{n}", title=f"Flood report {n}", channel="KFOR News", url=f"https://youtu.be/{n}",
                                 part=part, place="Norman", start=8.0, dur=8.0)
        return [mk("a", 0), mk("b", 1), mk("c", 1)]

    def fill(self, p=None, cat="flood", harvest_fn=None, notes=None):
        p = p or plan()
        fn = harvest_fn or (lambda *a, **k: Harvest(runs=self.runs()))
        with mock.patch("weather.newsdoc.story.read", return_value=story(cat)), mock.patch("weather.newsdoc.harvest.usable", return_value=True):
            n, credits = fill_from_youtube(p, self.project, [("x", 0.0, 0.1)], 40.0, self.log.append, notes if notes is not None else [], harvest_fn=fn)
        return p, n, credits

    def test_storm_scene_clips_become_news_footage_of_their_part(self):
        p, n, credits = self.fill()
        assets = {b.id: [c.asset for c in b.clips] for b in p.beats}
        self.assertEqual(n, 3)
        self.assertEqual(assets["b2"], ["run_a.mp4", "stock_video:documents on a desk"])   # a desk is not weather: stock stays
        self.assertEqual(assets["b3"], ["run_b.mp4", "my_clips/own.mp4"])                   # the second half of the story: its own run; your clip untouched
        self.assertEqual(assets["b4"], ["run_c.mp4"])                                       # every run once
        self.assertEqual(len(credits), 3)
        self.assertIn("KFOR News", credits[0])
        self.assertIn("YouTube news footage", p.beats[1].clips[0].reason)

    def test_the_wanted_clips_are_only_weather_impact_stock_requests(self):
        self.assertEqual([(b.id, c.asset) for b, c in wanted(plan())],
                         [("b2", "stock_video:flooded street"), ("b3", "stock_video:storm damaged roof"), ("b4", "stock_video:waves crashing over a seawall")])

    def test_a_forecast_or_a_story_that_is_not_a_storm_keeps_its_stock_footage(self):
        called = []
        for cat in ("forecast", "heat", "severe_other"):
            notes = []
            p, n, _c = self.fill(cat=cat, harvest_fn=lambda *a, **k: called.append(1) or Harvest(runs=self.runs()), notes=notes)
            self.assertEqual(n, 0, cat)
            self.assertEqual(p.beats[1].clips[0].asset, "stock_video:flooded street")
            self.assertTrue(any("stock footage is used" in x for x in notes), notes)
        self.assertEqual(called, [])   # no search for a story that YouTube news cannot help

    def test_a_story_with_few_storm_scenes_is_not_searched(self):
        # project #006 (a dam story that mentions floods): 7 storm-scene clips among 81 footage clips
        p = HybridPlan(duration=100.0, beats=[Beat(id="b0", mode="map", start=0, end=10, camera=[CameraStep("start", "Utah", "region")]),
                                              Beat(id="b1", mode="footage", start=10, end=100,
                                                   clips=[Clip("stock_video:flooded street"), Clip("stock_video:storm damaged roof")] +
                                                         [Clip(f"stock_video:concrete dam {k}") for k in range(10)])])
        called = []
        notes = []
        p, n, _c = self.fill(p=p, harvest_fn=lambda *a, **k: called.append(1) or Harvest(runs=self.runs()), notes=notes)
        self.assertEqual((n, called), (0, []))
        self.assertTrue(any("not a storm story" in x for x in notes), notes)

    def test_nothing_found_or_a_failure_keeps_stock_and_is_a_note(self):
        p, n, _c = self.fill(harvest_fn=lambda *a, **k: Harvest(notes=["news footage: nothing relevant"]))
        self.assertEqual(n, 0)
        self.assertEqual(p.beats[1].clips[0].asset, "stock_video:flooded street")

        def boom(*a, **k):
            raise RuntimeError("HTTP Error 429")
        notes = []
        p, n, _c = self.fill(harvest_fn=boom, notes=notes)
        self.assertEqual(n, 0)
        self.assertTrue(any("could not be searched" in x and "429" in x for x in notes), notes)

    def test_a_run_whose_file_is_missing_is_not_used(self):
        (self.root / "run_a.mp4").unlink()
        p, n, _c = self.fill()
        self.assertEqual(p.beats[1].clips[0].asset, "run_b.mp4")   # the next run of the pool, never a broken path

    def test_the_off_switch(self):
        (self.root / "weather.json").write_text(json.dumps({"youtube_news": False}), encoding="utf-8")
        self.assertFalse(enabled(self.project))
        called = []
        p, n, _c = self.fill(harvest_fn=lambda *a, **k: called.append(1) or Harvest(runs=self.runs()))
        self.assertEqual((n, called), (0, []))


class TheFootageRules(unittest.TestCase):
    def test_youtube_is_allowed_in_weather(self):
        p = HybridPlan(duration=10.0, beats=[Beat(id="b1", mode="map", start=0, end=5, camera=[CameraStep("start", "Texas", "region")]),
                                             Beat(id="b2", mode="footage", start=5, end=10, clips=[Clip("youtube_video:Fort Stockton tornado news")])])
        self.assertEqual(footage_problems(p), [])

    def test_generated_footage_is_still_refused(self):
        p = HybridPlan(duration=10.0, beats=[Beat(id="b1", mode="footage", start=0, end=10, clips=[Clip("flow_video:a tornado")])])
        self.assertTrue(footage_problems(p))


if __name__ == "__main__":
    unittest.main()
