"""Phase 2: beats.csv + weather_layers.csv built from the data load the way the render loads them, and keep the Weather rules."""

import csv
import io
import json
import unittest
from collections import defaultdict

from hybrid.beat_csv import plan_from_csv
from pakmap.words import estimate_words
from weather.automation import spoken as sp
from weather.automation.coverage import metro
from weather.automation.plan import FOOTAGE, NATIONAL, PlanBuildError, anchor_at, build_plan, choose_camera, in_view
from weather.automation.script import category_of, day_of
from weather.footage_library import condition_of
from weather.sidecar import parse_sidecar
from weather.timing import layer_windows

from test_weather_auto_script import TODAY, scripts

LIBRARY_SAME = {"cold": "snow", "cloud": "cloud"}   # frost reads as snow to the footage library; both are wintry pictures


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


class Plans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = [(snap, st, sc, build_plan(snap, st, sc)) for snap, st, sc in scripts()[::2]]

    def test_the_plan_loads_against_the_script_and_every_layer_finds_its_words(self):
        for snap, st, sc, plan in self.cases:
            words = estimate_words(sp.strip_hints(sc.text))
            hp = plan_from_csv(plan.beats_csv, words, words[-1][2] + 1)
            wx = parse_sidecar(plan.layers_csv)
            win = layer_windows(wx, hp, words)
            self.assertEqual(set(win), {r.id for r in wx})
            self.assertEqual(len(hp.beats), len(sc.sections))

    def test_the_beats_text_cells_are_the_script_word_for_word(self):
        for snap, st, sc, plan in self.cases:
            text = " ".join(r["text"] for r in rows(plan.beats_csv) if r["row"] == "beat")
            self.assertEqual(text.split(), sp.strip_hints(sc.text).split())

    def test_two_or_three_footage_beats_whose_clips_match_their_citys_forecast(self):
        for snap, st, sc, plan in self.cases:
            beats = rows(plan.beats_csv)
            foot = [r for r in beats if r["row"] == "beat" and r["mode"] == "footage"]
            self.assertIn(len(foot), (2, 3))
            secs = {f"b{i}": s for i, s in enumerate(sc.sections, start=1)}
            for b in foot:
                sec = secs[b["beat"]]
                d = day_of(snap, sec.footage_city, st.on)
                self.assertEqual(sec.footage, category_of(d))
                clips = [r for r in beats if r["row"] == "clip" and r["beat"] == b["beat"]]
                self.assertTrue(1 <= len(clips) <= 2)
                for c in clips:
                    self.assertTrue(c["asset"].startswith("stock_video:"), c)
                    desc = c["asset"].split(":", 1)[1]
                    self.assertIn(desc, FOOTAGE[sec.footage])
                    self.assertNotIn("footage of", desc)
            self.assertFalse([r for r in beats if "flow_" in r["asset"]])

    def test_every_stock_description_says_its_condition_to_the_footage_library(self):
        for cat, descs in FOOTAGE.items():
            for d in descs:
                self.assertEqual(condition_of(d), LIBRARY_SAME.get(cat, cat), d)

    def test_weather_layers_rules(self):
        for snap, st, sc, plan in self.cases:
            beats = {r["beat"]: r for r in rows(plan.beats_csv) if r["row"] == "beat"}
            by_beat = defaultdict(list)
            for r in parse_sidecar(plan.layers_csv):
                by_beat[r.beat].append(r)
            self.assertEqual(beats["b1"]["place"], NATIONAL[0])
            self.assertEqual(beats["b1"]["frame"], "continental")
            sat = [r for rs in by_beat.values() for r in rs if r.type == "satellite"]
            self.assertEqual([(r.beat, r.until) for r in sat], [("b1", "end")])
            kinds = {r.type for rs in by_beat.values() for r in rs}
            self.assertTrue({"temp_marker", "forecast_strip", "temp_trend", "now_card", "source_line"} <= kinds, kinds)
            for b, rs in by_beat.items():
                self.assertEqual(beats[b]["mode"], "map", f"weather layers on footage beat {b}")
                self.assertLessEqual(sum(r.type == "temp_marker" for r in rs), 4)
                shows = [r for r in rs if r.type not in ("satellite", "source_line")]
                self.assertEqual(bool(shows), any(r.type == "source_line" for r in rs), f"beat {b}: a source line exactly where numbers show")
                self.assertLessEqual(sum(r.type in ("forecast_strip", "temp_trend") for r in rs), 1)
            for b in beats.values():
                if b["mode"] == "map" and b["beat"] != "b1":
                    self.assertIn(b["type"], ("", "push_in", "hold"))
            if st.alerts:
                lead_beat = by_beat["b2"]
                self.assertTrue(any(r.type == "alert_area" and r.data_source.target in st.states for r in lead_beat))

    def test_markers_use_the_day_of_the_forecast_for_each_city(self):
        snap, st, sc, plan = self.cases[0]
        for r in parse_sidecar(plan.layers_csv):
            if r.type == "temp_marker" and r.data_source.product == "forecast":
                n = r.data_source.days()[0]
                d = snap.forecasts[metro(r.data_source.target.replace(",", ", ")).key]["days"][n - 1]
                self.assertEqual(d["start"][:10], st.on.isoformat(), r.id)

    def test_a_held_camera_stays_on_the_place_before_it(self):
        for snap, st, sc, plan in self.cases:
            prev = None
            for b in rows(plan.beats_csv):
                if b["row"] != "beat" or b["mode"] != "map":
                    continue
                if b["type"] == "hold":
                    self.assertEqual((b["place"], b["frame"]), prev, b["beat"])
                prev = (b["place"], b["frame"])


class Camera(unittest.TestCase):
    def test_the_camera_place_shows_its_cities(self):
        dal, hou = metro("Dallas, TX").city, metro("Houston, TX").city
        place, inside = choose_camera([(dal.lon, dal.lat), (hou.lon, hou.lat)])
        self.assertEqual((place, inside), ("Texas", [True, True]))
        self.assertTrue(in_view((-100.0, 31.3, 5.0), dal.lon, dal.lat))
        self.assertFalse(in_view((-100.0, 31.3, 5.0), -74.0, 40.7))

    def test_an_anchor_is_unique_from_where_its_search_starts_and_never_a_number(self):
        text = "Now to Texas. In Dallas, it stays sunny. In Dallas, there is rain. Ninety two degrees near Austin today."
        self.assertEqual(anchor_at(text, 3, 3), "In Dallas, it")
        self.assertEqual(anchor_at(text, 3, 0), "In Dallas, it")
        self.assertEqual(anchor_at(text, 8, 3), "In Dallas, there")
        with self.assertRaises(PlanBuildError):
            anchor_at(text, 13, 13)   # "Ninety two degrees": a number would not match the transcript reliably


if __name__ == "__main__":
    unittest.main()
