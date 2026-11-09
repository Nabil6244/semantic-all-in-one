"""War Documentary pace (owner, 2026-11-09: "the scene change is very very fast, irritating"): no shot under the minimum hold."""
import unittest
from types import SimpleNamespace

from cinematic_explainer.render import Shot
from cinematic_explainer.war import direction as D, engagement as E, storyline as SL


class CalmPace(unittest.TestCase):
    def test_constants_are_calm(self):
        self.assertGreaterEqual(D.CUT_MIN, 4.0)
        self.assertGreaterEqual(SL.PACE_MIN_S, 3.5)
        self.assertGreaterEqual(E.CUT_SLOW_S, 8.0)
        self.assertGreaterEqual(E.FIX_PIECE_S, 4.0)

    def test_sliver_of_same_clip_is_folded(self):
        plan = SimpleNamespace(shots=[Shot("a.mp4", 0, 5, 0), Shot("a.mp4", 5, 5.6, 5), Shot("b.mp4", 5.6, 10, 0)], layers=[])
        counts = {}
        D._fold_slivers(plan, counts)
        self.assertEqual([(s.path, s.start, s.end) for s in plan.shots], [("a.mp4", 0, 5.6), ("b.mp4", 5.6, 10)])
        self.assertEqual(counts["slivers_folded"], 1)

    def test_sliver_before_seekable_shot_starts_it_earlier(self):
        plan = SimpleNamespace(shots=[Shot("x.mp4", 0, 0.8, 0), Shot("b.mp4", 0.8, 6, 3.0)], layers=[])
        D._fold_slivers(plan, {})
        self.assertEqual(len(plan.shots), 1)
        self.assertEqual((plan.shots[0].start, plan.shots[0].seek), (0, 2.2))

    def test_long_shots_untouched(self):
        shots = [Shot("a.mp4", 0, 4, 0), Shot("b.mp4", 4, 8, 0)]
        plan = SimpleNamespace(shots=list(shots), layers=[])
        D._fold_slivers(plan, {})
        self.assertEqual(plan.shots, shots)

    def test_clip_glimpse_after_a_map_is_folded_into_the_next_clip(self):
        from cinematic_explainer.render import Layer
        plan = SimpleNamespace(shots=[Shot("a.mp4", 0, 6, 0), Shot("b.mp4", 6, 10, 0.5, dissolve_in=0.4)],
                               layers=[Layer("tac_map", 1.0, 5.76, {}, dim=False)])
        counts = {}
        D._fold_glimpses(plan, counts)
        self.assertEqual([(s.path, s.start, s.end) for s in plan.shots], [("a.mp4", 0, 5.76), ("b.mp4", 5.76, 10)])
        self.assertAlmostEqual(plan.shots[1].seek, 0.26)
        self.assertEqual(plan.shots[1].dissolve_in, 0.0)

    def test_clip_wholly_after_a_card_goes_when_short(self):
        from cinematic_explainer.render import Layer
        plan = SimpleNamespace(shots=[Shot("k.mp4", 0, 5, 0), Shot("x.mp4", 5, 6.4, 0), Shot("y.mp4", 6.4, 12, 2.0)],
                               layers=[Layer("kit_kinetic", 1.0, 5.0, {}, dim=False)])
        D._fold_glimpses(plan, {})
        self.assertEqual([(s.path, s.start) for s in plan.shots][-1], ("y.mp4", 5.0))
        self.assertNotIn("x.mp4", [s.path for s in plan.shots])

    def test_long_tail_after_a_card_is_kept(self):
        from cinematic_explainer.render import Layer
        shots = [Shot("a.mp4", 0, 8, 0), Shot("b.mp4", 8, 12, 0)]
        plan = SimpleNamespace(shots=list(shots), layers=[Layer("tac_map", 1.0, 4.0, {}, dim=False)])
        D._fold_glimpses(plan, {})
        self.assertEqual(plan.shots, shots)

    def test_clip_glimpse_before_a_card_is_folded(self):
        from cinematic_explainer.render import Layer
        plan = SimpleNamespace(shots=[Shot("a.mp4", 0, 10, 0), Shot("a.mp4", 10, 12, 10)],
                               layers=[Layer("tac_map", 10.48, 12.0, {}, dim=False)])
        D._fold_glimpses(plan, {})
        self.assertEqual([(s.start, s.end) for s in plan.shots], [(0, 10.48), (10.48, 12)])

    def test_clip_glimpse_before_a_card_with_nothing_before_moves_the_card(self):
        from cinematic_explainer.render import Layer
        card = Layer("tac_map", 0.5, 4.0, {}, dim=False)
        plan = SimpleNamespace(shots=[Shot("a.mp4", 0, 4, 0)], layers=[card])
        D._fold_glimpses(plan, {})
        self.assertEqual(card.start, 0)


if __name__ == "__main__":
    unittest.main()
