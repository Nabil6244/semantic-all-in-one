"""CSV-first director: a loaded CSV that names places is the whole place list; the narration is not searched for more."""
import unittest

from explainer.director.options import DirectorOptions
from explainer.director.select import place_candidates

SCRIPT = "Rome grew. Traders reached Egypt and Carthage. Armies crossed the Alps."


class CsvFirst(unittest.TestCase):
    def test_script_is_searched_by_default(self):
        cands, _ = place_candidates(SCRIPT, DirectorOptions(places=["Rome"]))
        self.assertIn("Rome", cands)
        self.assertIn("Egypt", cands)
        self.assertIn("Carthage", cands)

    def test_csv_places_only_when_csv_first(self):
        cands, weak = place_candidates(SCRIPT, DirectorOptions(places=["Rome", "Egypt"], csv_first=True))
        self.assertEqual(cands, ["Rome", "Egypt"])
        self.assertEqual(weak, set())

    def test_csv_first_without_places_still_searches(self):
        cands, _ = place_candidates(SCRIPT, DirectorOptions(places=[], csv_first=True))
        self.assertIn("Egypt", cands)

    def test_integration_switch(self):
        import inspect
        from explainer import integration
        src = inspect.getsource(integration.direct_plan)
        self.assertIn("explainer_csv_first", src)


if __name__ == "__main__":
    unittest.main()
