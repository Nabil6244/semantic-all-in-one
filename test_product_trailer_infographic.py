"""Infographic review style: the flat/gauge/tweet directives parse, the paper shots are planned with a paper sheet first, and no shot is a 3D phone."""
import json
import tempfile
import unittest
from pathlib import Path

from product_trailer import review, studio

SCRIPT = Path(__file__).parent / "docs/product_trailer/samples/review_infographic.txt"


class InfographicTests(unittest.TestCase):
    def test_directives_parse(self):
        p = review.parse_script(SCRIPT.read_text())
        kinds = [i["kind"] for c in p["chapters"] for i in c["items"]]
        self.assertTrue({"flat", "tweet", "gauge", "stat"} <= set(kinds))
        flat = next(i for c in p["chapters"] for i in c["items"] if i["kind"] == "flat")
        self.assertEqual(flat["phones"][0]["fill"], 0.95)
        g = next(i for c in p["chapters"] for i in c["items"] if i["kind"] == "gauge")
        self.assertTrue(max(g["gauges"], key=lambda x: x["value"]).get("highlight"))

    def test_infographic_film_is_flat_and_never_stills(self):
        with tempfile.TemporaryDirectory() as d:
            r = studio.plan_film("Review", out_dir=d, script=SCRIPT.read_text(), phone="galaxy s27 ultra", style="infographic", disclaimer_on=False)
            spec = json.loads(Path(r["spec_path"]).read_text())
        self.assertFalse([s for s in spec["shots"] if s["kind"] == "product"])
        types = {L["type"] for L in spec["layers"]}
        self.assertTrue({"pt_paper", "pt_flatphones", "pt_gauge", "pt_tweet", "pt_subtitle"} <= types)
        self.assertTrue(next(L for L in spec["layers"] if L["type"] == "pt_subtitle")["box"])
        self.assertEqual(spec["shots"][-1]["end"], spec["duration"])

    def test_cinematic_keeps_3d_and_new_directives_still_flat(self):
        with tempfile.TemporaryDirectory() as d:
            r = studio.plan_film("Review", out_dir=d, script=SCRIPT.read_text(), phone="galaxy s27 ultra", disclaimer_on=False)
            spec = json.loads(Path(r["spec_path"]).read_text())
        self.assertTrue([s for s in spec["shots"] if s["kind"] == "product"])
        self.assertIn("pt_gauge", {L["type"] for L in spec["layers"]})

    def test_unknown_style_is_refused(self):
        with self.assertRaises(ValueError):
            studio.plan_film("Review", out_dir=tempfile.mkdtemp(), script=SCRIPT.read_text(), phone="x", style="nope")

    def test_thermal_cost_and_desk_room(self):
        p = review.parse_script("[thermal: HEAT | A=41 | B=47]\nOne line.\n[cost: BOM | Display=90 | Camera=120]\nTwo.\n[lineup: x | desk | front]\nThree.")
        items = [i for c in p["chapters"] for i in c["items"]]
        th = next(i for i in items if i["kind"] == "thermal")
        self.assertTrue(th["phones"][1]["highlight"])
        self.assertEqual(next(i for i in items if i["kind"] == "cost")["total"], "$210")
        self.assertEqual(next(i for i in items if i["kind"] == "lineup")["room"], "desk")


if __name__ == "__main__":
    unittest.main()
