"""War Documentary shot lengths (problem 12): no footage shot under 3 s outside the montage hook, and a footage chip never outlives its clip."""
import unittest
from types import SimpleNamespace

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import direction as D

MIN = 3.0 - 1e-6


def _plan(shots, layers=()):
    return SimpleNamespace(shots=list(shots), layers=list(layers), stats={})


def _rows(total, n=2):
    step = total / n
    return [{"_no": i, "_start": i * step, "_end": (i + 1) * step} for i in range(n)]


def _short(plan, hook_end=0.0):
    return [(s.start, s.end) for s in plan.shots if s.end - s.start < MIN and s.start >= hook_end]


class ShotLengths(unittest.TestCase):
    def test_constants(self):
        self.assertGreaterEqual(D.MIN_SHOT_S, 3.0)
        self.assertGreaterEqual(D.BROLL_MIN_S, 3.0)

    def test_short_source_clip_in_long_scene(self):
        plan = _plan([Shot("yt.mp4", 0, 8, 0), Shot("long.mp4", 8, 16, 0)])
        D._fit_short_clips(plan, {}, probe=lambda p: 3.5 if p == "yt.mp4" else 30.0)
        self.assertAlmostEqual(plan.shots[0].end, 3.45, places=1)
        D._broll_returns(plan, _rows(16), {}, {}, {}, probe=lambda p: 3.5 if p == "yt.mp4" else 30.0)
        self.assertEqual(_short(plan), [])

    def test_clip_that_is_left_with_under_three_seconds_is_dropped(self):
        plan = _plan([Shot("yt.mp4", 0, 8, 0), Shot("long.mp4", 8, 16, 0)])
        counts = {}
        D._fit_short_clips(plan, counts, probe=lambda p: 2.2 if p == "yt.mp4" else 30.0)
        self.assertEqual([s.path for s in plan.shots], ["long.mp4"])
        self.assertEqual(counts["short_clips_dropped"], 1)

    def test_early_ending_clip_with_seek(self):
        plan = _plan([Shot("a.mp4", 0, 8, 5.0), Shot("b.mp4", 8, 16, 0)])
        D._fit_short_clips(plan, {}, probe=lambda p: 7.0 if p == "a.mp4" else 30.0)   # 2 s left after the seek
        self.assertNotIn("a.mp4", [s.path for s in plan.shots])
        D._broll_returns(plan, _rows(16), {}, {}, {}, probe=lambda p: 7.0 if p == "a.mp4" else 30.0)
        self.assertEqual(_short(plan), [])

    def test_remainder_after_a_full_frame_card_is_not_a_sliver(self):
        plan = _plan([Shot("a.mp4", 0, 10, 0), Shot("b.mp4", 10, 20, 0)], [Layer("tac_map", 1.0, 8.2, {}, dim=False)])
        D._final_coverage(plan, 20.0, {})
        self.assertEqual(_short(plan), [])

    def test_broll_return_gaps_under_three_seconds_are_not_cut(self):
        plan = _plan([Shot("a.mp4", 0, 6, 0), Shot("b.mp4", 8.5, 14, 0)])      # a 2.5 s gap
        D._broll_returns(plan, _rows(14), {}, {}, {}, probe=lambda p: 30.0)
        self.assertEqual(_short(plan), [])

    def test_hook_cuts_are_exempt(self):
        plan = _plan([Shot("a.mp4", 0, 2.5, 0), Shot("b.mp4", 2.5, 5.0, 0), Shot("c.mp4", 5.0, 12, 0)])
        D._final_coverage(plan, 12.0, {}, hook_end=5.0)
        self.assertEqual([(s.start, s.end) for s in plan.shots][:2], [(0, 2.5), (2.5, 5.0)])

    def test_source_chip_is_clamped_to_its_clip(self):
        plan = _plan([Shot("a.mp4", 0, 5, 0)], [Layer("bc_source", 1.0, 9.0, {"text": "UNVERIFIED · ABC NEWS"}, dim=False),
                                              Layer("tac_map", 5.0, 9.0, {}, dim=False)])
        D._final_coverage(plan, 9.0, {})
        chips = [ly for ly in plan.layers if ly.kind == "bc_source"]
        self.assertTrue(chips)
        self.assertLessEqual(max(c.end for c in chips), 5.0 + 0.05)

    def test_chip_with_no_footage_at_all_is_removed(self):
        plan = _plan([], [Layer("bc_source", 1.0, 5.0, {"text": "X"}, dim=False), Layer("tac_map", 0.0, 9.0, {}, dim=False)])
        D._final_coverage(plan, 9.0, {})
        self.assertFalse([ly for ly in plan.layers if ly.kind == "bc_source"])


if __name__ == "__main__":
    unittest.main()
