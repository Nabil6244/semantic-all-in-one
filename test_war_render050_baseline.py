"""Stage A of the render-050 repair: the preserved baseline, its defect inventory, and the plan audit that measures every later stage.

The fixtures live in test_fixtures/war_render050 (scenes, defects mapped to components, baseline audit, real frames with labels, targets).
"""

import json
import re
import unittest
from pathlib import Path

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import plan_audit as PA

FX = Path(__file__).resolve().parent / "test_fixtures" / "war_render050"


def _scene(no, text, a, b, footage=None, sid=None):
    s = {"scene_no": no, "text": text, "start": a, "end": b}
    if footage:
        s["footage"] = footage
        s["footage_meta"] = {"provider_asset_id": sid}
    return s


class Plan:
    def __init__(self, shots, layers):
        self.shots, self.layers = shots, layers


class FixturesIntact(unittest.TestCase):
    def test_defects_name_known_stages_and_components(self):
        d = json.loads((FX / "defects.json").read_text())
        for item in d["defects"]:
            for st in item["stage"]:
                self.assertIn(st, d["stages"], item["seen"])
            for c in item["component"]:
                self.assertIn(c, d["components"], item["seen"])

    def test_scenes_cover_the_whole_script(self):
        sc = json.loads((FX / "scenes.json").read_text())
        self.assertEqual(len(sc), 255)
        self.assertTrue(all(s["text"].strip() for s in sc))
        self.assertTrue(all(sc[i]["end"] <= sc[i + 1]["start"] + 0.5 for i in range(len(sc) - 1)))

    def test_every_labelled_frame_exists(self):
        labels = json.loads((FX / "frames" / "labels.json").read_text())
        for k in labels:
            if k.startswith("_"):
                continue
            for t in ("t1", "t3"):
                self.assertTrue((FX / "frames" / f"{k}_{t}.jpg").is_file(), k)
        tg = json.loads((FX / "targets.json").read_text())["visual_usability_frames"]
        self.assertEqual(set(tg["must_reject"]), {k for k, v in labels.items() if not k.startswith("_") and not v["usable"]})

    def test_baseline_audit_matches_the_review(self):
        b = json.loads((FX / "baseline_audit.json").read_text())
        self.assertLess(b["footage_share"], 0.3)
        self.assertGreaterEqual(b["keyword_cards"], 70)
        self.assertGreaterEqual(len(b["number_cards_bad"]), 10)
        self.assertGreaterEqual(len(b["map_foreign_places"]), 40)


class PlanAudit(unittest.TestCase):
    def test_a_background_alone_is_not_coverage(self):
        sc = [_scene(1, "A line.", 0, 10)]
        plan = Plan([Shot("/x/war_backdrop_v3.mp4", 0, 10)], [Layer("kit_field", 0, 10), Layer("tac_map", 0, 4)])
        rep = PA.audit(plan, sc)
        self.assertEqual(rep["backdrop_only"], [(4.0, 10.0)])
        self.assertEqual(rep["footage_share"], 0.0)

    def test_reuse_counts_the_source_video_not_the_file(self):
        sc = [_scene(i, f"Line {i}.", i * 10, i * 10 + 10, f"/a/{i:03d}.mp4", "VID") for i in range(4)]
        plan = Plan([Shot(f"/a/{i:03d}.mp4", i * 10, i * 10 + 5) for i in range(4)], [])
        rep = PA.audit(plan, sc)
        self.assertEqual(list(rep["reuse"]), ["VID"])

    def test_touching_pieces_of_one_shot_are_one_use(self):
        sc = [_scene(1, "Line.", 0, 30, "/a/1.mp4", "V")]
        plan = Plan([Shot("/a/1.mp4", 0, 4), Shot("/a/1.mp4", 4, 8), Shot("/a/1.mp4", 8.5, 12)], [])
        self.assertEqual(PA.audit(plan, sc)["reuse"], {})

    def test_kinetic_must_be_a_whole_line(self):
        sc = [_scene(1, "The institute also pointed to reported proposals. The war is far from over.", 0, 10)]
        plan = Plan([], [Layer("kit_kinetic", 0, 3, {"text": "The institute also pointed"}),
                         Layer("kit_kinetic", 6, 9, {"text": "The war is far from over."})])
        frag = PA.audit(plan, sc)["kinetic_fragments"]
        self.assertEqual([f["text"] for f in frag], ["The institute also pointed"])

    def test_number_cards_need_a_stated_quantity(self):
        sc = [_scene(1, "What changed in the last two weeks. Ninety-six of those drones were jet-powered.", 0, 10)]
        plan = Plan([], [Layer("kit_bignum", 0, 3, {"value": "two", "label": "WEEKS WHERE"}),
                         Layer("kit_bignum", 5, 8, {"value": "96", "label": "DRONES"})])
        bad = PA.audit(plan, sc)["number_cards_bad"]
        self.assertEqual([b["value"] for b in bad], ["two"])

    def test_a_digit_inside_a_model_name_is_not_the_figure(self):
        sc = [_scene(1, "Every Pantsir or S-400 battery moved to protect a refinery.", 0, 10)]
        plan = Plan([], [Layer("lay_stat_split", 0, 3, {"value": "400", "label": "battery moved"})])
        self.assertEqual(len(PA.audit(plan, sc)["number_cards_bad"]), 1)

    def test_maps_only_pin_places_the_line_names(self):
        sc = [_scene(1, "Oil products are one of Russia's biggest sources of export income.", 0, 10),
              _scene(2, "Drones hit the port zone of Ust-Luga on the Baltic Sea.", 20, 30)]
        plan = Plan([], [Layer("tac_map", 0, 6, {"places": [{"name": "Washington"}]}),
                         Layer("tac_map", 20, 26, {"places": [{"name": "Ust-Luga"}]})])
        self.assertEqual([m["place"] for m in PA.audit(plan, sc)["map_foreign_places"]], ["Washington"])

    def test_spelled_numbers(self):
        self.assertEqual(PA.spelled_to_digits("Ninety-six drones and three workers"), "96 drones and 3 workers")
        self.assertTrue(re.search(r"\b162\b", PA.spelled_to_digits("162 drones")))


if __name__ == "__main__":
    unittest.main()
