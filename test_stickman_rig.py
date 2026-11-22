"""Stickman Phase 1: rig, poses, 3 s rule, feet on the ground, no foot sliding."""
import copy
import json
import math
import unittest
from pathlib import Path

from stickman import poses, rig, timeline

DEMO = json.loads((Path(__file__).parent / "stickman" / "demos" / "phase1.json").read_text())


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class RigTests(unittest.TestCase):
    def test_forty_poses(self):
        self.assertEqual(len(poses.ALL), 40)
        for name in poses.STATIC:
            for facing in (1, -1):
                j = rig.fk(poses.STATIC[name], facing)
                self.assertAlmostEqual(_dist(j["elbow_f"], j["hand_f"]), rig.FOREARM, places=9)
                self.assertAlmostEqual(_dist(j["knee_b"], j["foot_b"]), rig.SHIN, places=9)
                self.assertTrue(all(math.isfinite(v) for p in j.values() for v in p))

    def test_facing_mirrors(self):
        a, b = rig.fk(poses.STATIC["point"], 1), rig.fk(poses.STATIC["point"], -1)
        self.assertAlmostEqual(a["hand_f"][0], -b["hand_f"][0])
        self.assertGreater(a["hand_f"][0], 0.2)          # pointing arm reaches forward

    def test_hand_reaches_face(self):
        for name in ("think", "facepalm"):
            j = rig.fk(poses.STATIC[name])
            self.assertLess(_dist(j["hand_f"], j["head"]), rig.HEAD_R * 1.6, name)

    def test_jump_lifts(self):
        self.assertEqual(poses.jump(0.1)[1], 0.0)
        self.assertGreater(poses.jump(0.5)[1], 0.3)
        self.assertEqual(poses.jump(0.9)[1], 0.0)


class TimelineTests(unittest.TestCase):
    def test_demo_valid(self):
        self.assertAlmostEqual(timeline.validate(DEMO), 20.0)

    def test_hold_over_3s_rejected(self):
        spec = copy.deepcopy(DEMO)
        spec["beats"][0]["dur"] = 3.5
        for b in spec["beats"][1:]:
            b["t"] += 1.0
        spec["duration"] = 21.0
        with self.assertRaisesRegex(timeline.TimelineError, "holds 3.5 s"):
            timeline.validate(spec)

    def test_empty_beat_rejected(self):
        spec = copy.deepcopy(DEMO)
        spec["beats"][3] = {"t": 7.5, "dur": 2.5}
        with self.assertRaisesRegex(timeline.TimelineError, "changes nothing"):
            timeline.validate(spec)

    def test_unknown_action_rejected(self):
        spec = copy.deepcopy(DEMO)
        spec["beats"][1]["acts"]["sam"] = {"do": "moonwalk"}
        with self.assertRaises(timeline.TimelineError):
            timeline.validate(spec)


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = timeline.simulate(DEMO)
        cls.ground = cls.frames[0]["ground"]

    def test_feet_on_ground(self):
        for fr in self.frames:
            for f in fr["figs"]:
                low = max(f["joints"]["foot_b"][1], f["joints"]["foot_f"][1])
                if f["lift"] == 0:
                    self.assertAlmostEqual(low, self.ground, delta=0.5)
                else:
                    self.assertLess(low, self.ground)

    def test_planted_foot_never_slides(self):
        worst = 0.0
        for a, b in zip(self.frames, self.frames[1:]):
            for fa, fb in zip(a["figs"], b["figs"]):
                if fa["do"] not in ("walk", "run") or fb["do"] != fa["do"]:
                    continue
                for foot in ("foot_b", "foot_f"):
                    pa, pb = fa["joints"][foot], fb["joints"][foot]
                    other = "foot_f" if foot == "foot_b" else "foot_b"
                    if pa[1] > fa["joints"][other][1] and pb[1] > fb["joints"][other][1]:
                        worst = max(worst, abs(pb[0] - pa[0]))
        self.assertLess(worst, 0.5)

    def test_walk_stops_at_target(self):
        W = DEMO["size"][0]
        fr = self.frames[int(2.45 * 30)]
        sam = fr["figs"][0]
        self.assertEqual(sam["do"], "stand")
        self.assertLess(abs(sam["joints"]["pelvis"][0] - 0.32 * W), 0.05 * W)

    def test_both_run_off_screen(self):
        W = DEMO["size"][0]
        for f in self.frames[-1]["figs"]:
            self.assertGreater(f["joints"]["pelvis"][0], W * 0.9)


if __name__ == "__main__":
    unittest.main()
