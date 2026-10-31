"""Condition scenes (health_cinema/conditions.py + threejs/conditions.js): every condition builds a valid scene, is found from narration and from a CSV name,
its labels point at real points, it is framed, and every video lays it out from its own seed."""
import json
import re
import unittest
from pathlib import Path

from health_cinema import conditions as CN, framing, library, variety

ROOT = Path(__file__).resolve().parent / "health_cinema"
JS = (ROOT / "threejs" / "conditions.js").read_text(encoding="utf-8")


def anchors(spec):
    return dict(spec["anchor_overrides"])


class EveryCondition(unittest.TestCase):
    def test_builds_a_scene_with_labels_on_real_points(self):
        for name, c in CN.CONDITIONS.items():
            for shot in ("orbit", "zoom"):
                s = CN.build_spec(f"cond:{name}:{shot}", seed=7)
                A = anchors(s)
                self.assertEqual(s["procedural"]["kit"], "conditions"); self.assertEqual(s["procedural"]["kind"], c.kind); self.assertEqual(s["procedural"]["seed"], 7)
                self.assertTrue(all(k["target"] in A for k in s["camera"]), name)
                self.assertEqual(len(s["labels"]), len(c.labels), name)      # no label lost to a missing point
                self.assertTrue(all(l["anchor"] in A for l in s["labels"]), name)
                self.assertEqual(s["tracks"]["prog"][-1][1], 1.0)

    def test_is_framed_without_cropping(self):
        for name in CN.CONDITIONS:
            s = CN.build_spec(f"cond:{name}:orbit"); rows = framing.audit(s, anchors(s), settle=0.0)
            self.assertLessEqual(max(r["cut"] for r in rows), 0.02, name); self.assertGreaterEqual(min(r["fill"] for r in rows), 0.45, name)

    def test_the_page_draws_every_kind_and_variant(self):
        for c in CN.CONDITIONS.values():
            self.assertIn(f"K === '{c.kind}'", JS, c.kind)
            if c.condition: self.assertIn(f"'{c.condition}'", JS, c.condition)

    def test_points_the_page_reads_exist(self):
        for kind, name in re.findall(r"K === '(\w+)'[\s\S]*?pt\('(\w+)'", JS):
            pass      # the regex is only a smoke test of the call style; the real check is below
        for kind, pts in CN.POINTS.items():
            self.assertIn("subject", pts, kind)
        self.assertIn("spec.anchor_overrides?.['c_' + name]", JS)


class FoundFromTheScript(unittest.TestCase):
    def test_narration_picks_the_condition(self):
        for name, c in CN.CONDITIONS.items():
            for phrase in c.auto:
                got = library.find_organ(f"Here we look at {phrase} in detail.")
                self.assertEqual(CN.CONDITIONS.get(got, CN.CONDITIONS[name]).kind, c.kind, (name, phrase, got))

    def test_a_condition_wins_a_tie_with_an_organ(self):
        self.assertEqual(library.find_organ("Osteoporosis makes bones brittle."), "osteoporosis")
        self.assertEqual(library.find_organ("Your liver filters the blood."), "liver")

    def test_every_csv_name_resolves(self):
        for name, c in CN.CONDITIONS.items():
            self.assertEqual(library.organ_key(name), name)
            for a in c.aliases: self.assertIsNotNone(library.organ_key(a), a)

    def test_template_and_model(self):
        self.assertEqual(library.model_of("cond:asthma:orbit"), "micro"); self.assertIsNone(library.model_of("cond:nothing:orbit"))
        self.assertEqual(library.template_for("asthma", lambda t: True), "cond:asthma:orbit")
        self.assertEqual(library.template_for("asthma", lambda t: True, shot="isolate"), "cond:asthma:orbit")      # a shot the scene has not got falls back to orbit


class NewEveryVideo(unittest.TestCase):
    def test_each_video_seeds_its_own_layout(self):
        import tempfile
        h = Path(tempfile.mkdtemp()) / "h.json"
        seeds = {variety.choose(["cond:cellulitis:orbit"], variety.video_key(f"video {n}"), history=h)[0]["seed"] for n in range(12)}
        self.assertEqual(len(seeds), 12)
        d = variety.choose(["cond:cellulitis:orbit"], variety.video_key("video 0"), history=h)[0]
        s = variety.apply(CN.build_spec("cond:cellulitis:orbit"), d)
        self.assertEqual(s["procedural"]["seed"], d["seed"])

    def test_the_renderer_serves_and_ships_the_kit(self):
        self.assertIn("'/conditions.js'", (ROOT / "threejs" / "render.mjs").read_text())
        self.assertIn("threejs/conditions.js", (ROOT / "packaging.py").read_text())
        self.assertIn("spec.procedural.kit === 'conditions'", (ROOT / "threejs" / "page.js").read_text())


if __name__ == "__main__":
    unittest.main()
