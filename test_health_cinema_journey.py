"""Health Cinema journey sampler: deterministic, backend-neutral camera/layer/label frames (no Blender or browser needed)."""
import json, tempfile, unittest
from pathlib import Path
from health_cinema import journey

ANCH = {"anchors": {"body": {"center": [0, 0, 0.88]}, "chest": {"center": [0, 0, 1.26]}, "heart": {"center": [0.02, -0.02, 1.29]}}}
SPEC = {"duration": 4, "background": [0, 0, 0], "camera": [
    {"t": 0, "target": "body", "dist": 4, "az": 0, "el": 0, "fov": 30}, {"t": 4, "target": "heart", "dist": 0.5, "az": 0, "el": 0, "fov": 30}],
    "layers": {"Layer_Skin": [[0, 1], [2, 1], [3, 0]]},
    "labels": [{"id": "h", "text": "Heart", "anchor": "heart", "offset": [0, 0, 0], "t0": 3, "t1": 4}]}

class JourneyTest(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp()); (d / "s.json").write_text(json.dumps(SPEC)); (d / "a.json").write_text(json.dumps(ANCH)); self.p = (d / "s.json", d / "a.json")
    def test_deterministic_and_length(self):
        a = journey.sample(*self.p, 24, 960, 540)[2]; b = journey.sample(*self.p, 24, 960, 540)[2]
        self.assertEqual(len(a), 96); self.assertEqual(a, b)
    def test_camera_ends_framing_target_and_layer_fades(self):
        fr = journey.sample(*self.p, 24, 960, 540)[2]
        self.assertAlmostEqual(fr[0]["cam"][1], -4.0, places=3)
        self.assertEqual(fr[0]["alpha"]["Layer_Skin"], 1.0); self.assertEqual(fr[-1]["alpha"]["Layer_Skin"], 0.0)
        steps = [abs(fr[i + 1]["cam"][1] - fr[i]["cam"][1]) for i in range(len(fr) - 1)]
        self.assertLess(max(steps), 0.2)   # no jump
    def test_look_point_projects_to_centre(self):
        fr = journey.sample(*self.p, 24, 960, 540)[2]
        for f in (fr[0], fr[40], fr[-1]):
            x, y = journey.project(f["cam"], f["look"], f["fov"], f["look"], 960, 540)
            self.assertAlmostEqual(x, 480, delta=0.01); self.assertAlmostEqual(y, 270, delta=0.01)
    def test_label_hidden_until_layer_is_visible(self):
        spec = dict(SPEC, layers={"Layer_Skin": [[0, 0], [3.5, 0], [4, 1]]}, labels=[dict(SPEC["labels"][0], layer="Layer_Skin")])
        d = Path(tempfile.mkdtemp()); (d / "s.json").write_text(json.dumps(spec))
        fr = journey.sample(d / "s.json", self.p[1], 24, 960, 540)[2]
        shown = [f["t"] for f in fr if f["labels"]]
        self.assertTrue(shown); self.assertGreaterEqual(min(shown), 3.5)   # not before the layer is mostly in
    def test_label_hidden_when_anchor_outside_safe_frame(self):
        self.assertFalse(journey.label_visible((5, 270), 960, 540)); self.assertFalse(journey.label_visible(None, 960, 540))
        self.assertTrue(journey.label_visible((480, 270), 960, 540))
    def test_path_is_smooth_no_overshoot_and_continuous_velocity(self):
        fr = journey.sample(*self.p, 48, 960, 540)[2]
        z = [f["cam"][1] for f in fr]; self.assertGreaterEqual(min(z), -4.0 - 1e-6); self.assertLessEqual(max(z), -0.5 + 1e-6)
        v = [z[i + 1] - z[i] for i in range(len(z) - 1)]; acc = [abs(v[i + 1] - v[i]) for i in range(len(v) - 1)]
        self.assertLess(max(acc), 0.05)
    def test_label_hidden_before_window(self):
        fr = journey.sample(*self.p, 24, 960, 540)[2]; self.assertEqual(fr[10]["labels"], [])

if __name__ == "__main__":
    unittest.main()


ANCHORS = Path.home() / "HealthCinemaTools" / "bench" / "anchors.json"   # derived from the licensed evaluation model; kept outside the repo
SPECF = Path(__file__).parent / "health_cinema" / "bench" / "journey_chest_heart.json"

@unittest.skipUnless(ANCHORS.exists(), "local evaluation anchors not present")
class RealJourneyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.spec, cls.A, cls.fr = journey.sample(SPECF, ANCHORS, 24, 1920, 1080)
    def test_layer_alphas_in_range_and_staged(self):
        for f in self.fr:
            for v in f["alpha"].values(): self.assertTrue(0.0 <= v <= 1.0)
        self.assertEqual(self.fr[0]["alpha"]["Layer_Heart"], 0.0); self.assertEqual(self.fr[-1]["alpha"]["Layer_HeartCut"], 1.0)
        self.assertEqual(self.fr[-1]["alpha"]["Layer_Skin"], 0.0)   # the skin is gone before the organ close-ups
    def test_camera_never_enters_subject_and_has_no_jumps(self):
        import math
        for f in self.fr: self.assertGreater(math.dist(f["cam"], f["look"]), 0.3)    # near plane is 0.02 m; heart is ~0.12 m across
        step = [math.dist(a["cam"], b["cam"]) for a, b in zip(self.fr, self.fr[1:])]; self.assertLess(max(step), 0.2)
        look = [math.dist(a["look"], b["look"]) for a, b in zip(self.fr, self.fr[1:])]; self.assertLess(max(look), 0.05)
    def test_labels_follow_layers_and_stay_in_frame(self):
        for f in self.fr:
            for lb in f["labels"]:
                self.assertTrue(journey.label_visible(lb["xy"], 1920, 1080))
                if lb["id"] == "heart": self.assertGreaterEqual(f["alpha"]["Layer_Heart"], journey.LABEL_MIN_LAYER_ALPHA)
                if lb["id"] in ("lv", "rv"): self.assertGreaterEqual(f["alpha"]["Layer_HeartCut"], journey.LABEL_MIN_LAYER_ALPHA)
        self.assertTrue(any(f["labels"] for f in self.fr))
    def test_sampling_deterministic_across_resolutions_in_time(self):
        a = journey.sample(SPECF, ANCHORS, 24, 960, 540)[2]
        self.assertEqual([f["cam"] for f in a], [f["cam"] for f in self.fr])   # camera does not depend on resolution
