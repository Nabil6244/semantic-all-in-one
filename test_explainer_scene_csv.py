import unittest

from explainer import csv_hints, scene_csv
from explainer import scene_intel as SI

WORDS = [(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(
    "in 1450 the merchants of venice sailed into the lagoon and then the farmers of the village loaded wheat at the market near the station".split())]
CSV = """row,scene,vo_anchor,id,name,look,place,type,region,period,architecture,background,people,activity,objects,mood,continues,route
cast,,,doge,The Doge,"old man, white beard, crimson robe and horn-shaped cap",,,,,,,,,,,,
scene,1,in 1450 the merchants,,,,canal city,coast,Venice,1450,Gothic palazzi,green lagoon with galleys,doge,sailing,galleys,dusk,,
scene,2,then the farmers,,,,hill village,village,Veneto,1450,,fields and mill,,loading wheat,,morning,,
"""


class SceneCsv(unittest.TestCase):
    def test_reads_scenes_with_times_and_cast_looks(self):
        got = scene_csv.read(CSV, WORDS, 12.0)
        self.assertEqual(got["problems"], [], got)
        n = got["scene_notes"]
        self.assertEqual(len(n), 2)
        self.assertEqual(n[0]["start"], 0.0)
        self.assertAlmostEqual(n[0]["end"], n[1]["start"])
        self.assertIn("looks: The Doge, old man", n[0]["text"])
        spec = SI.from_notes(n[0]["text"])
        d = SI.decide(spec)
        self.assertEqual(d.route, "flow")
        p = SI.flow_prompt(spec)
        self.assertIn("crimson robe", p)
        self.assertIn("green lagoon with galleys", p)

    def test_hints_route_to_the_scene_reader(self):
        h = csv_hints.read(CSV, WORDS, 12.0)
        self.assertEqual(len(h["scene_notes"]), 2)
        self.assertEqual(h["spans"], [])
        self.assertIn("Venice", h["places"])

    def test_unknown_cast_is_reported(self):
        bad = CSV.replace(",doge,sailing", ",king,sailing")
        self.assertIn("no cast row", " ".join(scene_csv.read(bad, WORDS, 12.0)["problems"]))

    def test_same_backdrop_twice_in_a_row_is_reported_unless_it_continues(self):
        twice = CSV + "scene,3,loaded wheat,,,,hill village,village,Veneto,1450,,fields and mill,,,,,,\n"
        self.assertIn("same place", " ".join(scene_csv.read(twice, WORDS, 12.0)["problems"]))
        ok = CSV + "scene,3,loaded wheat,,,,hill village,village,Veneto,1450,,fields and mill,,,,,yes,\n"
        self.assertEqual(scene_csv.read(ok, WORDS, 12.0)["problems"], [])

    def test_missing_anchor_and_unknown_kind(self):
        got = scene_csv.read("row,scene,vo_anchor\nscene,1,\nsong,2,x\n", WORDS, 5.0)
        self.assertEqual(len(got["problems"]), 2)

    def test_detects_only_its_own_header(self):
        self.assertTrue(scene_csv.is_scene_csv(CSV))
        self.assertFalse(scene_csv.is_scene_csv("beat,row,vo_anchor,mode"))


if __name__ == "__main__":
    unittest.main()


class PromptExample(unittest.TestCase):
    def test_prompt_example_loads_and_decides_sensibly(self):
        import re
        from pathlib import Path
        text = (Path(__file__).resolve().parent / "composition_styles" / "explainer_scene_csv_prompt.txt").read_text(encoding="utf-8")
        script = re.search(r'Script: "(.*?)"', text).group(1)
        csv_text = text[text.rindex("row,scene,vo_anchor,id"):text.index("NOW WRITE")].strip()
        words, t = [], 0.0
        for w in script.split():
            words.append((w.strip(".,").lower(), t, t + 0.35))
            t += 0.4
        got = scene_csv.read(csv_text, words, t)
        self.assertEqual(got["problems"], [], got)
        self.assertEqual(len(got["scene_notes"]), 2)
        for n in got["scene_notes"]:
            self.assertEqual(SI.decide(SI.from_notes(n["text"])).route, "flow")
