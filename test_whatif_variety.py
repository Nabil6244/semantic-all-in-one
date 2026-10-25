"""What If variety pass: 3D for named craft/worlds, fewer plain text cards, rotating camera moves, a look per topic."""
import unittest

from whatif import planner, variety
from whatif.planner import Shot


def shot(i, a, b, text, kind="video", asset="stock_video:space"):
    return Shot(id=f"s{i}", start=a, end=b, kind=kind, text=text, asset=asset)


class Upgrade3D(unittest.TestCase):
    def test_named_craft_becomes_model_but_not_next_to_another(self):
        shots = [shot(1, 0, 5, "Then Cassini reached Saturn orbit."), shot(2, 5, 10, "Cassini again turned its dish."), shot(3, 10, 15, "Juno arrived at Jupiter.")]
        notes = []
        n = variety.upgrade_3d(shots, notes)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(shots[0].kind, "craft")
        self.assertNotEqual(shots[1].kind, "craft")        # neighbours alternate
        self.assertEqual(shots[0].asset, "")

    def test_photo_claim_and_flow_stay(self):
        shots = [shot(1, 0, 5, "The photo from Voyager 1 showed Earth."), shot(2, 5, 10, "Voyager 1 flew on.", asset="flow_video:a probe")]
        self.assertEqual(variety.upgrade_3d(shots, []), 0)
        self.assertEqual([s.kind for s in shots], ["video", "video"])

    def test_carry_over_the_probe(self):
        shots = [shot(1, 0, 5, "Voyager 1 left Earth."), shot(2, 5, 9, "Stock.", kind="plate"), shot(3, 9, 14, "The probe kept going.")]
        variety.upgrade_3d(shots, [])
        self.assertEqual(shots[2].kind, "craft")
        self.assertEqual(shots[2].name, shots[0].name)


class TrimText(unittest.TestCase):
    def layer(self, tid, t):
        return {"type": "tm_template", "template": {"id": tid}, "start": t, "end": t + 3}

    def test_text_share_is_held_and_nothing_is_left_bare(self):
        shots = [shot(i, i * 6, i * 6 + 6, "x", kind="craft" if i % 2 else "video") for i in range(10)]
        layers = [self.layer("lower_third", i * 6 + 1) for i in range(10)] + [self.layer("ring_value", 2), self.layer("route_line", 14)]
        n = variety.trim_text(shots, layers, [])
        text = [L for L in layers if L["template"]["id"] == "lower_third"]
        self.assertGreater(n, 0)
        self.assertLessEqual(len(text), 5)         # every card over a 3D shot went; real footage keeps its only card
        self.assertTrue(all(L["template"]["id"] in ("lower_third", "ring_value", "route_line") for L in layers))


class MotionAndLook(unittest.TestCase):
    def test_no_two_in_a_row_move_the_same(self):
        shots = [shot(i, i * 5, i * 5 + 5, "x") for i in range(12)]
        variety.vary_motion(shots, [])
        drifts = [tuple(sorted(s.extra["drift"].items())) for s in shots]
        self.assertTrue(all(a != b for a, b in zip(drifts, drifts[1:])))
        self.assertGreater(len(set(drifts)), 3)

    def test_look_follows_topic_and_title_seeds_difference(self):
        hot = "The surface is hot, the heat melts lead, lava and fire, temperatures burn everything. " * 6
        cold = "Cold ice, frozen ocean, Europa and Neptune, a silent void. " * 6
        self.assertEqual(variety.pick_look("a", hot)[0], "heat")
        self.assertEqual(variety.pick_look("a", cold)[0], "cold")
        self.assertNotEqual(variety.pick_look("one", hot)[1], variety.pick_look("two", hot)[1])
        self.assertEqual(variety.pick_look("one", hot)[1], variety.pick_look("one", hot)[1])
        name, look = variety.pick_look("t", "plain words here")
        self.assertEqual(name, "house")
        self.assertNotIn("accent", look)


if __name__ == "__main__":
    unittest.main()


class CinemaVariety(unittest.TestCase):
    """The same pass on a StarMap Cinema spec (starmap/cinema.py variety)."""

    def spec_plan(self):
        from types import SimpleNamespace as NS

        beats = [NS(id="b1", mode="map", start=0.0, end=10.0, text="The map.", place="Jupiter"),
                 NS(id="b2", mode="footage", start=10.0, end=16.0, text="Voyager 1 swung past Jupiter and onward.", place=""),
                 NS(id="b3", mode="map", start=16.0, end=22.0, text="Onward.", place=""),
                 NS(id="b4", mode="footage", start=22.0, end=28.0, text="The photo from the team showed Earth.", place=""),
                 NS(id="b5", mode="footage", start=28.0, end=34.0, text="Then it left the planets behind.", place="")]
        spec = {"duration": 34.0, "camera": {"moves": []}, "layers": [{"type": "tm_template", "template": {"id": "lower_third"}, "start": 11.0, "end": 14.0}],
                "footage": [{"id": "b2_1", "start": 10.0, "end": 16.0, "image": "a.jpg"}, {"id": "b4_1", "start": 22.0, "end": 28.0, "image": "b.jpg"},
                            {"id": "b5_1", "start": 28.0, "end": 34.0, "image": "c.jpg"}]}
        return spec, NS(beats=beats, title="Voyager", words=[])

    def test_footage_about_a_craft_becomes_its_model_and_the_look_is_set(self):
        from starmap import cinema

        spec, plan = self.spec_plan()
        notes = []
        cinema.variety(spec, plan, notes)
        crafts = [L for L in spec["layers"] if L["type"] == "cinema_craft"]
        self.assertEqual(len(crafts), 1)
        self.assertEqual((crafts[0]["start"], crafts[0]["end"], crafts[0]["over_footage"]), (10.0, 16.0, True))
        self.assertTrue(crafts[0]["model"].startswith("wi:"))
        self.assertTrue(all(f.get("ken_burns") for f in spec["footage"]))      # every still moves, differently
        kb = [str(f["ken_burns"]) for f in spec["footage"]]
        self.assertEqual(len(set(kb)), 3)
        self.assertIn("cinema_look", spec)
        self.assertIn("variety", cinema.FEATURES)
        self.assertTrue(any("Cinema variety" in n for n in notes))
