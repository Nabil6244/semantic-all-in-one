"""Hybrid Map: places the atlas used to lose (England, Scotland, Wales, Northern Ireland), a camera too tight for its markers
(widened by code, no AI asked), and the Director's rule that a small or unnamed place is written as lat,lon."""

from __future__ import annotations

import unittest

from hybrid.director import plan_from_payload
from hybrid.local_fix import fix
from hybrid.validate import validate
from pakmap.geo import resolve
from test_hybrid_director import DURATION, SENTENCES, WORDS, payload


class TestUkNations(unittest.TestCase):
    def test_the_four_nations_are_areas_with_their_own_shape(self):
        sizes = {}
        for name in ("England", "Scotland", "Wales", "Northern Ireland"):
            for prefer in ("area", "point"):
                loc = resolve(name, prefer)
                self.assertTrue(loc.is_area, f"{name} ({prefer}) must be an area, got {loc.kind}")
            w, s, e, n = loc.bbox
            sizes[name] = (e - w) * (n - s)
        self.assertGreater(sizes["England"], sizes["Wales"])
        self.assertGreater(sizes["Scotland"], sizes["Northern Ireland"])

    def test_england_holds_liverpool_and_not_edinburgh(self):
        eng = resolve("England")
        w, s, e, n = eng.bbox
        lv = resolve("Liverpool", "point")
        self.assertTrue(w < lv.lon < e and s < lv.lat < n)
        self.assertLess(eng.bbox[3], 56.0)   # Scotland's north is not in it

    def test_cornwall_the_county_beats_a_small_town_of_that_name(self):
        loc = resolve("Cornwall", "point")
        self.assertTrue(loc.is_area and 49.9 < loc.lat < 51.0, f"{loc.name} {loc.lat},{loc.lon}")

    def test_the_united_kingdom_still_resolves_as_the_country(self):
        self.assertEqual(resolve("United Kingdom").kind, "country")


class TestOutOfFrameRepair(unittest.TestCase):
    def build(self, p):
        return plan_from_payload(p, SENTENCES, WORDS, DURATION)[0]

    def tight(self):
        p = payload()
        p["beats"][3]["map"]["camera"] = {"place": "Quetta", "frame": "local", "move": "fly_to"}
        p["beats"][3]["map"]["layers"].append({"type": "marker", "anchor": "small fraction", "place": "Lahore", "label": "LAHORE"})
        return p

    def test_a_tight_camera_is_widened_by_code_until_every_marker_is_inside(self):
        plan = self.build(self.tight())
        found = [f for f in validate(plan) if f.code == "out_of_frame"]
        self.assertEqual(len(found), 1)
        n, done = fix(plan, found)
        self.assertEqual(n, 1, done)
        self.assertEqual([f for f in validate(plan) if f.code == "out_of_frame"], [])

    def test_a_marker_that_no_frame_can_hold_is_left_for_the_repair_pass(self):
        p = self.tight()
        p["beats"][3]["map"]["layers"].append({"type": "marker", "anchor": "small fraction", "place": "-33.9,18.4", "label": "CAPE TOWN"})
        plan = self.build(p)
        found = [f for f in validate(plan) if f.code == "out_of_frame"]
        before = [(c.place, c.frame) for c in plan.beats[3].camera]
        n, _ = fix(plan, found)
        self.assertEqual(n, 0)
        self.assertEqual([(c.place, c.frame) for c in plan.beats[3].camera], before)

    def test_a_small_area_camera_with_far_markers_goes_to_its_country(self):
        # the Liverpool case: a region-sized frame on a small county, markers 100 km away
        p = payload()
        p["beats"][3]["map"]["camera"] = {"place": "Quetta", "frame": "region", "move": "fly_to"}
        p["beats"][3]["map"]["layers"].append({"type": "marker", "anchor": "small fraction", "place": "Karachi", "label": "KARACHI"})
        plan = self.build(p)
        found = [f for f in validate(plan) if f.code == "out_of_frame"]
        self.assertTrue(found)
        fix(plan, found)
        self.assertEqual([f for f in validate(plan) if f.code == "out_of_frame"], [])


    def test_the_plan_check_widens_the_camera_and_says_so(self):
        from hybrid.app_integration import check_plan

        plan = self.build(self.tight())
        text, _ = check_plan(plan, engine=False)
        self.assertNotIn("outside the camera", text)
        self.assertIn("widened the camera", text)


class TestOutlierNoise(unittest.TestCase):
    def test_a_beat_that_goes_elsewhere_on_purpose_is_not_questioned_but_a_stray_marker_is(self):
        p = payload()
        p["beats"][3]["map"]["camera"] = {"place": "Sydney", "frame": "region", "move": "fly_to"}
        p["beats"][3]["map"]["layers"] = [{"type": "marker", "anchor": "almost half", "place": "-33.9,151.2", "label": "SYDNEY"}]
        plan = plan_from_payload(p, SENTENCES, WORDS, DURATION)[0]
        self.assertEqual([f for f in validate(plan) if f.code == "place_outlier" and f.beat == "b4"], [])
        p["beats"][0]["map"]["layers"].append({"type": "marker", "anchor": "long country", "place": "-33.9,18.4", "label": "NOT HERE"})
        plan = plan_from_payload(p, SENTENCES, WORDS, DURATION)[0]
        found = [f for f in validate(plan) if f.code == "place_outlier" and f.beat == "b1"]
        self.assertEqual(len(found), 1)


class TestPlacePrompt(unittest.TestCase):
    def test_every_hybrid_prompt_says_how_to_write_a_place_the_atlas_may_lack(self):
        from pathlib import Path

        for name in ("hybrid_director_prompt.txt", "hybrid_beats_prompt.txt", "hybrid_beats_prompt_graphics.txt", "hybrid_csv_prompt.txt"):
            low = (Path(__file__).parent / "composition_styles" / name).read_text(encoding="utf-8").lower()
            self.assertIn("lat,lon", low, name)
            self.assertTrue("bay" in low and "sea" in low, f"{name}: the rule must name bays and seas")
        for name in ("hybrid_beats_prompt.txt", "hybrid_beats_prompt_graphics.txt", "hybrid_csv_prompt.txt"):
            low = (Path(__file__).parent / "composition_styles" / name).read_text(encoding="utf-8").lower()
            self.assertIn("inside the camera's view", low, name)


if __name__ == "__main__":
    unittest.main()
