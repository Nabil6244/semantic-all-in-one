import tempfile
import unittest

from explainer.director.options import DirectorOptions
from explainer.director import plan as P

SCRIPT = ("In 1450 the merchants of Venice sailed from the lagoon to the harbour. In 1450 the farmers of the village loaded wheat at the market. "
          "In 1450 the sailors crossed the sea toward the coast and the port.")


def words(text):
    out, t = [], 0.0
    for w in text.replace(".", "").split():
        out.append((w, t, t + 0.34))
        t += 0.38
    return out


class Wiring(unittest.TestCase):
    def _run(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            opt = DirectorOptions(cartoon_share=1.0, scenes2=True, min_beat_s=2.0, work_dir=d, **kw)
            return P.direct(words(SCRIPT), SCRIPT, opt, materialize=False)

    def test_off_changes_nothing(self):
        r = self._run()
        self.assertNotIn("scene_intel", r.report)

    def test_old_period_cartoon_becomes_flow_image(self):
        r = self._run(scene_intel=True, scene_flow_share=1.0)
        rec = r.report.get("scene_intel", {})
        self.assertTrue(rec, r.problems)
        flow_ids = [i for i, v in rec.items() if v["route"] == "flow"]
        self.assertTrue(flow_ids, rec)
        self.assertTrue(all(v["route"] == "compose" for i, v in rec.items() if i not in flow_ids), rec)      # the buildings-free coast set is valid in any year
        flows = [b for b in (r.plan or {}).get("beats", []) if b.get("footage") and b["footage"]["clips"][0]["asset"].startswith("flow_image:")] if r.plan else []
        self.assertTrue(flows)
        self.assertIn("1450", flows[0]["footage"]["clips"][0]["asset"])

    def test_csv_note_forces_flow_with_its_architecture(self):
        notes = [{"start": 0.0, "end": 999.0, "text": "place: canal city; type: coast; period: 1450; architecture: Gothic palazzi; people: merchant"}]
        r = self._run(scene_intel=True, scene_flow_share=1.0, scene_notes=notes)
        rec = r.report["scene_intel"]
        self.assertTrue(rec and all(v["route"] == "flow" and v["source"] == "csv" for v in rec.values()), rec)
        self.assertTrue(all("Gothic palazzi" in v["prompt"] for v in rec.values()), rec)

    def test_share_cap_keeps_the_rest_as_cartoons(self):
        r = self._run(scene_intel=True, scene_flow_share=0.0)
        rec = r.report["scene_intel"]
        self.assertTrue(any("share reached" in v["route"] for v in rec.values()), rec)
        self.assertFalse(any(v["route"] == "flow" for v in rec.values()), rec)


if __name__ == "__main__":
    unittest.main()
