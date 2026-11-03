"""Hybrid openings: two videos do not open the same way (every video used to open on the globe for 1.4 s, then fly in)."""

import os
import tempfile
import unittest
from pathlib import Path

from hybrid import openings
from hybrid.director import derive_cameras
from hybrid.plan import Beat, Clip, HybridPlan, Layer

SCRIPTS = [  # (first sentence, camera place, frame, early layer types)
    ("Across the world, more than forty countries now ration water.", "India", "country", []),
    ("In 2014, 1.2 million people fled the region in a single summer.", "Syria", "country", ["stat"]),
    ("The old trade route ran from Kashgar across the mountains to the sea.", "Xinjiang", "region", ["line"]),
    ("Since 2010, the city of Lagos has doubled in size.", "Lagos", "local", []),
    ("The port of Gwadar sits at the edge of a quiet bay.", "Balochistan", "region", []),
    ("For decades, the Nile delta has been sinking.", "Egypt", "country", []),
    ("Smugglers cross the border at night, carrying fuel.", "Iran", "country", ["line"]),
    ("Kenya is a country of farmers.", "Kenya", "country", []),
    ("The capital Kabul was surrounded within days.", "Kabul", "local", []),
    ("Greenland holds enough ice to raise the seas by seven metres.", "Greenland", "country", ["stat"]),
]


def plan_for(text, place, frame, early, first_footage=False, settings=None):
    beats = []
    if first_footage:
        beats.append(Beat(id="b0", mode="footage", start=0.0, end=6.0, narration=text, clips=[Clip(asset="stock_video:a street")]))
    start = 6.0 if first_footage else 0.0
    b = Beat(id="b1", mode="map", start=start, end=start + 12.0, narration="" if first_footage else text, cam_place=place, cam_frame=frame)
    b.layers = [Layer(id=f"l{k}", type=t, t=1.0, place=place) for k, t in enumerate(early)]
    beats.append(b)
    beats.append(Beat(id="b2", mode="footage", start=start + 12.0, end=start + 20.0, clips=[Clip(asset="stock_video:fields")]))
    return HybridPlan(duration=start + 20.0, beats=beats, settings=dict(settings or {}))


class OpeningsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HYBRID_OPENING_HISTORY"] = str(Path(self.tmp.name) / "openings.json")

    def tearDown(self):
        os.environ.pop("HYBRID_OPENING_HISTORY", None)
        self.tmp.cleanup()

    def test_ten_topics_get_varied_openings(self):
        kinds = []
        for text, place, frame, early in SCRIPTS:
            p = plan_for(text, place, frame, early)
            derive_cameras(p)
            kinds.append(p.settings["opening_picked"])
        self.assertGreaterEqual(len(set(kinds)), 5, kinds)
        for a, b in zip(kinds, kinds[1:]):
            self.assertNotEqual(a, b, kinds)  # never the last video's opening
        self.assertLess(kinds.count("globe_fly_in"), 4, kinds)

    def test_same_video_planned_again_keeps_its_opening(self):
        text, place, frame, early = SCRIPTS[0]
        p1 = plan_for(text, place, frame, early)
        derive_cameras(p1)
        p2 = plan_for(text, place, frame, early)
        derive_cameras(p2)
        self.assertEqual(p1.settings["opening_picked"], p2.settings["opening_picked"])
        derive_cameras(p1)  # a repair derives again: the pick is kept
        self.assertEqual(p1.settings["opening_picked"], p2.settings["opening_picked"])

    def test_two_similar_videos_differ(self):
        a = plan_for("Kenya is a country of farmers.", "Kenya", "country", [])
        b = plan_for("Uganda is a country of farmers.", "Uganda", "country", [])
        derive_cameras(a)
        derive_cameras(b)
        self.assertNotEqual(a.settings["opening_picked"], b.settings["opening_picked"])

    def test_every_type_makes_a_valid_opening(self):
        for kind in openings.TYPES:
            early = ["stat"] if kind == "stat_open" else ["line"] if kind == "route_open" else []
            frame = "region" if kind == "settle_in" else "country"  # settle_in glides in from one step wider: a region or a city
            p = plan_for("Kenya is a country of farmers.", "Kenya", frame, early, settings={"opening": kind})
            derive_cameras(p)
            self.assertEqual(p.settings["opening_picked"], kind)
            cam = p.beats[0].camera
            self.assertEqual(cam[0].action, "start")
            self.assertEqual(cam[0].t, 0.0)
            hi = p.beats[0].end - p.setting("dissolve_s") / 2
            for c in cam[1:]:
                self.assertLessEqual(c.t + (c.dur or 0.0), hi + 1e-6, (kind, c))
            moved = [c for c in cam if c.action == "fly_to"]
            if moved:
                self.assertEqual((moved[-1].place, moved[-1].frame), ("Kenya", frame), kind)

    def test_globe_opening_off_is_a_plain_start(self):
        p = plan_for("Across the world, water is short.", "India", "country", [], settings={"globe_opening": False})
        derive_cameras(p)
        self.assertEqual([(c.action, c.frame) for c in p.beats[0].camera], [("start", "country")])
        self.assertNotIn("opening_picked", p.settings)

    def test_footage_first_is_recorded_as_a_cold_open(self):
        p = plan_for("Smoke rose over the street at dawn.", "Gaza", "region", [], first_footage=True)
        derive_cameras(p)
        self.assertEqual(p.settings["opening_picked"], "cold_footage")
        self.assertEqual([c.action for c in p.beats[1].camera], ["start"])
        self.assertEqual(openings.load_history()[0]["type"], "cold_footage")

    def test_no_history_under_tests_without_a_path(self):
        os.environ.pop("HYBRID_OPENING_HISTORY", None)
        self.assertIsNone(openings.history_path())


if __name__ == "__main__":
    unittest.main()
