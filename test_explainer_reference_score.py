import unittest

from explainer import reference_score as RS


def _plan(spans, kinds):
    return {"beats": [{"id": f"e{i}", "mode": "footage", "start": a, "end": b, "purpose": k}
                      for i, ((a, b), k) in enumerate(zip(spans, kinds))]}


class ReferenceScore(unittest.TestCase):
    def test_kinds_and_shares(self):
        plan = _plan([(0, 5), (5, 10)], ["explainer cartoon: x", "explainer board: y"])
        rows, share = RS.score(plan)
        self.assertEqual(round(share["cartoon"]), 50)
        self.assertEqual({r[0]: r[3] for r in rows}["R01"], "PASS")

    def test_clause_starts_use_pauses(self):
        words = [["a", 0.0, 0.4], ["b", 0.4, 0.8], ["c", 1.5, 1.9]]
        self.assertEqual(RS.sentence_starts(words, 0.0), [0.0, 1.5])

    def test_long_shot_fails(self):
        rows, _ = RS.score(_plan([(0, 30)], ["explainer board: y"]))
        self.assertEqual({r[0]: r[3] for r in rows}["R03"], "FAIL")


if __name__ == "__main__":
    unittest.main()
