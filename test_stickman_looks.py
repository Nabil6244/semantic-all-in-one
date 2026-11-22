"""Stickman Phase 3: 40 poses, the prop library, places and the five looks."""
import unittest

from stickman import director, draw, looks, make, places, poses, props, rig, timeline
from test_stickman_director import BODY, TITLE, fake_words

SMALL = [320, 180]


def _spec(look, acts, place="void", props_=None):
    return {"look": look, "fps": 30, "size": SMALL, "duration": 1.0, "place": place,
            "figures": {"a": {"x": 0.36, "facing": 1, "height": 0.4}, "b": {"x": 0.64, "facing": -1, "height": 0.4}},
            "beats": [{"t": 0, "dur": 1.0, "caption": "Hello *there*", "acts": acts, "props": props_ or []}]}


class PoseTests(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(poses.ALL), 40)
        self.assertEqual(len(poses.STATIC), 36)
        self.assertGreaterEqual(len(props.PROPS), 60)
        self.assertEqual(len(looks.LOOKS), 6)

    def test_every_still_pose_touches_ground(self):
        for name in poses.STATIC:
            spec = _spec("ink_paper", {"a": {"do": name}})
            fr = timeline.simulate(spec)[-1]
            a = fr["figs"][0]
            low = rig.lowest({k: ((x - a["joints"]["pelvis"][0]) / a["hpx"], (y - a["joints"]["pelvis"][1]) / a["hpx"])
                              for k, (x, y) in a["joints"].items()}) * a["hpx"] + a["joints"]["pelvis"][1]
            self.assertAlmostEqual(low, fr["ground"], delta=0.5, msg=name)

    def test_osc_and_pose_props_name_real_things(self):
        for name, loops in poses.OSC.items():
            self.assertIn(name, poses.STATIC)
            for key, _, period in loops:
                self.assertIn(key, rig.ANGLES)
                self.assertGreater(period, 0)
        for name, items in poses.POSE_PROPS.items():
            self.assertIn(name, poses.STATIC)
            for prop, where, size in items:
                self.assertIn(prop, props.PROPS)

    def test_sneak_moves_without_sliding(self):
        spec = _spec("ink_paper", {"a": {"do": "sneak", "to": 0.6}})
        spec["duration"] = spec["beats"][0]["dur"] = 3.0
        frames = timeline.simulate(spec)
        worst = 0.0
        for fa, fb in zip(frames, frames[1:]):
            a, b = fa["figs"][0], fb["figs"][0]
            if a["do"] == b["do"] == "sneak":
                for foot, other in (("foot_b", "foot_f"), ("foot_f", "foot_b")):
                    if a["joints"][foot][1] > a["joints"][other][1] and b["joints"][foot][1] > b["joints"][other][1]:
                        worst = max(worst, abs(b["joints"][foot][0] - a["joints"][foot][0]))
        self.assertLess(worst, 0.5)
        self.assertGreater(frames[-1]["figs"][0]["joints"]["pelvis"][0], 0.45 * SMALL[0])


class DrawTests(unittest.TestCase):
    def test_every_look_draws_every_place(self):
        for look in looks.LOOKS:
            for place in places.PLACES:
                spec = _spec(look, {"a": {"do": "phone"}, "b": {"do": "idea"}}, place,
                             [{"name": "clock", "fig": "b", "at": "side", "size": 0.4}])
                fr = timeline.simulate(spec)[20]
                buf = draw.frame(fr, spec, looks.get(look))
                self.assertEqual(len(buf), SMALL[0] * SMALL[1] * 3, (look, place))

    def test_every_prop_draws(self):
        for look in ("ink_paper", "colour_pop"):
            spec = _spec(look, {"a": {"do": "stand"}}, "void",
                         [{"name": n, "x": 0.1 + 0.8 * (i % 9) / 8, "y": 0.2 + 0.1 * (i // 9), "size": 0.08}
                          for i, n in enumerate(sorted(props.PROPS))])
            fr = timeline.simulate(spec)[-1]
            self.assertEqual(len(fr["props"]), len(props.PROPS))
            draw.frame(fr, spec, looks.get(look))

    def test_place_items_are_props(self):
        for name, p in places.PLACES.items():
            for prop, x, base, size in p["items"]:
                self.assertIn(prop, props.PROPS, name)
                self.assertTrue(0 <= x <= 1 and base >= 0 and 0 < size < 0.6)


class DirectorPhase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        words, dur = fake_words(BODY)
        cls.spec = director.direct(BODY, words, dur, title=TITLE, size=(640, 360), look="colour_pop")

    def test_wide_range_of_actions(self):
        self.assertGreaterEqual(len({b["action"] for b in self.spec["beats"]}), 12)

    def test_props_from_words(self):
        named = [p["name"] for b in self.spec["beats"] for p in b.get("props", [])]
        self.assertIn("cup", named)
        self.assertIn("phone", named)
        self.assertTrue(all(n in props.PROPS for n in named))

    def test_places_change_with_topic_and_hold(self):
        changes = [(b["t"], b["place"]) for b in self.spec["beats"] if b.get("place")]
        self.assertEqual(changes[0][1], "bedroom")
        self.assertGreaterEqual(len({p for _, p in changes}), 3)
        for (ta, _), (tb, _) in zip(changes, changes[1:]):
            self.assertGreaterEqual(tb - ta, director.PLACE_HOLD - 1e-6)


if __name__ == "__main__":
    unittest.main()
