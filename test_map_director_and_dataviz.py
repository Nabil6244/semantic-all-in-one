#!/usr/bin/env python3
"""Map Director (production.map_director), automatic data visualization (graphics.dataviz) and the render-cache key
fixes that make surgical re-rendering actually reuse clips. No network, no rendering of video."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from graphics.dataviz import DataViz, detect_dataviz, render_dataviz
from production.map_director import MapDirector, geographic_intents


class TestMapDirector(unittest.TestCase):
    def test_first_arrival_establishes_with_a_push_in(self):
        d = MapDirector().decide("Our story begins in the Florida Panhandle.")
        self.assertTrue(d.use_map)
        self.assertEqual((d.intent, d.camera, d.prompt), ("establish", "zoom_in", "Florida > Florida Panhandle"))

    def test_a_place_named_again_without_new_geography_gets_no_second_map(self):
        md = MapDirector()
        self.assertTrue(md.decide("Oil was found in Texas in 1901.").use_map)
        again = md.decide("Back in Texas, the governor signed the bill.")
        self.assertFalse(again.use_map)
        self.assertIn("already shown", again.reason)

    def test_a_repeat_with_geographic_information_earns_a_map_and_picks_the_camera(self):
        md = MapDirector()
        md.decide("Oil was found in Texas in 1901.")
        wide = md.decide("The oil fields stretch across Texas for 300 miles.")
        self.assertTrue(wide.use_map)
        self.assertEqual(wide.camera, "zoom_out")
        self.assertTrue(wide.prompt.endswith("| camera: zoom_out"))

    def test_scale_on_first_arrival_pulls_out(self):
        d = MapDirector().decide("The desert stretches across Nevada, covering most of the state.")
        self.assertEqual((d.use_map, d.camera), (True, "zoom_out"))

    def test_no_detected_place_means_no_map(self):
        d = MapDirector().decide("Chad said the plan would never work.")
        self.assertFalse(d.use_map)

    def test_author_maps_count_as_shown(self):
        md = MapDirector()
        md.note_shown("United States of America > Texas | camera: drift")
        self.assertFalse(md.decide("Workers stayed in Texas all winter.").use_map)

    def test_intents(self):
        self.assertIn("route", geographic_intents("The army marched from Egypt to Syria."))
        self.assertIn("distance", geographic_intents("It lies 400 miles away from the coast."))
        self.assertIn("boundary", geographic_intents("The river forms the border."))
        self.assertEqual(geographic_intents("He was a quiet man."), [])

    def test_map_pass_uses_the_director_for_repeats(self):
        from visual_director.map_pass import add_map_scenes
        from visual_director.schema import VisualPlan, VisualScene

        def scene(i, text, d=40.0):
            return VisualScene(scene_id=i, narration=text, visual_goal="g", visual_description="d", asset_type="stock_video",
                               provider_preference="stock_video", search_queries=["q"], timestamp_needed=False,
                               timestamp_hint="", duration=d, importance="medium", fallbacks=["youtube"],
                               visual_treatment="", transition="cut")

        plan = VisualPlan(topic="t", scenes=[scene(1, "Oil was found in Texas in 1901."),
                                             scene(2, "Money poured in."),
                                             scene(3, "Back in Texas, the governor signed the bill."),
                                             scene(4, "The fields stretch across Texas for 300 miles.")])
        self.assertEqual(add_map_scenes(plan), 2)
        types = [s.asset_type for s in plan.scenes]
        self.assertEqual(types, ["map", "stock_video", "stock_video", "map"])
        self.assertTrue(plan.scenes[3].visual_description.endswith("| camera: zoom_out"))


class TestDataVizDetection(unittest.TestCase):
    def test_ranking(self):
        v = detect_dataviz("Texas pumps 5.6 million barrels a day, New Mexico 1.8 million, and North Dakota 1.2 million.")
        self.assertEqual(v.kind, "ranking")
        self.assertEqual([(p.label, p.value) for p in v.points],
                         [("Texas", 5.6e6), ("New Mexico", 1.8e6), ("North Dakota", 1.2e6)])

    def test_comparison(self):
        v = detect_dataviz("China built 120 nuclear reactors while India built 22 nuclear reactors.")
        self.assertEqual((v.kind, [p.label for p in v.points]), ("comparison", ["China", "India"]))

    def test_change_with_years_and_derived_percent(self):
        v = detect_dataviz("The city's population grew from 2 million in 1990 to 9 million in 2020.")
        self.assertEqual(v.kind, "change")
        self.assertEqual([(p.label, p.value) for p in v.points], [("1990", 2e6), ("2020", 9e6)])
        self.assertEqual(v.note, "+350%")

    def test_change_with_unit_words_between_value_and_year(self):
        v = detect_dataviz("The town grew from 12 thousand people in 1975 to 49 thousand people in 1986, with schools.")
        self.assertEqual([(p.label, p.display) for p in v.points], [("1975", "12K"), ("1986", "49K")])
        self.assertEqual(v.note, "+308%")

    def test_share(self):
        v = detect_dataviz("Nearly 70 percent of the world's cobalt comes from Congo.")
        self.assertEqual((v.kind, v.points[0].value, v.points[0].label), ("share", 70.0, "Congo"))

    def test_timeline(self):
        v = detect_dataviz("The canal opened in 1914, was handed to Panama in 1999, and was expanded in 2016.")
        self.assertEqual((v.kind, [p.display for p in v.points]), ("timeline", ["1914", "1999", "2016"]))

    def test_no_chart_without_real_data(self):
        for text in ("It took 3 years to build and cost a fortune.",
                     "In 1986 the reactor exploded, killing 31 people.",
                     "The plant had four reactors and 1,000 workers on site.",
                     "From 1990 to 2020 the region changed completely.",
                     "He was 45 years old when he arrived in Texas.",
                     "Short line 5 10."):
            self.assertIsNone(detect_dataviz(text), text)

    def test_mixed_kinds_are_not_charted_together(self):
        self.assertIsNone(detect_dataviz("Texas has 30 percent of the wells while Ohio has 2 million barrels in storage."))

    def test_round_trip(self):
        v = detect_dataviz("China built 120 nuclear reactors while India built 22 nuclear reactors.")
        self.assertEqual(DataViz.from_dict(v.to_dict()).to_dict(), v.to_dict())


class TestDataVizThroughTheGraphicsPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_director_prefers_the_chart_over_a_single_statistic(self):
        from graphics.director import decide_graphic

        ds = decide_graphic(narration="The city's population grew from 2 million in 1990 to 9 million in 2020.",
                            scene_number="4", purpose="evidence")
        self.assertEqual(ds[0].decision, "COMPARISON")
        self.assertEqual(ds[0].payload["template"], "dataviz_change")
        self.assertFalse(any(d.decision == "STATISTIC" for d in ds))

    def test_engine_gives_charts_reading_time_and_renderer_draws_them(self):
        from graphics.director import decide_graphic
        from graphics.engine import _materialize_directive
        from graphics.design_system import get_design_system
        from graphics.render import render_graphic_overlay

        d = decide_graphic(narration="Texas pumps 5.6 million barrels a day, New Mexico 1.8 million, and North Dakota 1.2 million.",
                           scene_number="2", purpose="evidence")[0]
        spec = _materialize_directive(d, scene_number="2", scene_start=10.0, scene_end=18.0, scene_duration=8.0,
                                      importance="medium", design=get_design_system(), narration="")
        self.assertGreaterEqual(spec.end - spec.start, 3.5)
        self.assertLessEqual(spec.end, 18.0)
        png = render_graphic_overlay(spec, self.tmp / "c.png", 1920, 1080)
        from PIL import Image

        im = Image.open(png)
        self.assertEqual(im.size, (1920, 1080))
        box = im.getbbox()
        self.assertGreater(box[0], 1920 * 0.5)  # drawn on the right, inside the frame
        self.assertLess(box[2], 1920)

    def test_short_scene_gets_no_chart(self):
        from graphics.director import decide_graphic
        from graphics.engine import _materialize_directive
        from graphics.design_system import get_design_system

        d = decide_graphic(narration="China built 120 nuclear reactors while India built 22 nuclear reactors.",
                           scene_number="2", purpose="evidence")[0]
        self.assertIsNone(_materialize_directive(d, scene_number="2", scene_start=0.0, scene_end=2.0, scene_duration=2.0,
                                                 importance="medium", design=get_design_system(), narration=""))

    def test_4k_chart_has_the_same_layout(self):
        import numpy as np
        from PIL import Image

        v = detect_dataviz("The city's population grew from 2 million in 1990 to 9 million in 2020.")
        a = Image.open(render_dataviz(v, self.tmp / "hd.png", 1920, 1080))
        b = Image.open(render_dataviz(v, self.tmp / "uhd.png", 3840, 2160)).resize((1920, 1080))
        diff = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)).mean()
        self.assertLess(diff, 2.0)


class TestRenderCacheKeyStability(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _key(self, overlay_dir: Path, reason: str = "source covers beat"):
        from render_cache import build_scene_cache_key

        src = self.tmp / "001.mp4"
        if not src.exists():
            src.write_bytes(b"video")
        png = overlay_dir / "gfx_1_00_statistic.png"
        overlay_dir.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"PNG-bytes-of-the-same-picture")
        return build_scene_cache_key(
            scene_number="1", img_path=src, duration=4.0, width=1920, height=1080, fps=30, zoom=True, zoom_in=True,
            zoom_amount=0.1, timed_overlays=[(png, 0.5, 3.0, "fade", None)],
            edit_decision={"strategy": "SINGLE_SHOT", "reason": reason,
                           "shots": [{"source_path": str(src), "output_duration": 4.0, "reason": reason, "confidence": 0.7}]},
        )

    def test_same_overlay_drawn_in_another_run_folder_is_the_same_key(self):
        a = self._key(self.tmp / "run1" / "graphics_overlays")
        b = self._key(self.tmp / "run2" / "graphics_overlays")
        self.assertEqual(a, b)

    def test_descriptive_decision_fields_do_not_change_the_key(self):
        a = self._key(self.tmp / "r" / "o", reason="source covers beat")
        b = self._key(self.tmp / "r" / "o", reason="")
        self.assertEqual(a, b)

    def test_float_noise_from_a_reloaded_plan_does_not_change_the_key(self):
        from render_cache import build_scene_cache_key

        src = self.tmp / "001.mp4"
        src.write_bytes(b"v")
        common = dict(scene_number="1", img_path=src, duration=3.88, width=1920, height=1080, fps=30, zoom=False,
                      zoom_in=False, zoom_amount=0.1)
        a = build_scene_cache_key(**common, edit_decision={"shots": [{"output_duration": 3.88}]})
        b = build_scene_cache_key(**common, edit_decision={"shots": [{"output_duration": 3.879999999999999}]})
        c = build_scene_cache_key(**common, edit_decision={"shots": [{"output_duration": 3.9}]})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_superseded_and_orphaned_clips_are_removed(self):
        from render_cache import RenderCache

        state = self.tmp / "state"
        cache = RenderCache(state)
        clip = self.tmp / "clip.mp4"
        clip.write_bytes(b"c1")
        cache.put("1", "a" * 64, clip)
        clip.write_bytes(b"c2")
        cache.put("1", "b" * 64, clip)
        clips = list((state / "render_cache").iterdir())
        self.assertEqual(len(clips), 1)
        (state / "render_cache" / "scene_9_old.mp4").write_bytes(b"orphan")
        RenderCache(state)
        self.assertEqual(len(list((state / "render_cache").iterdir())), 1)
        self.assertIsNotNone(RenderCache(state).get("1", "b" * 64))


if __name__ == "__main__":
    unittest.main()
