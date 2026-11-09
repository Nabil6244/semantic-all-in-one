"""War final-render QA (cinematic_explainer/war/render_qa.py): bare / sparse grid, blank frames and short shots, on synthetic frames."""

import unittest

import numpy as np

from cinematic_explainer.war import render_qa as Q

H, W = Q.QH, Q.QW
FPS = 10


def plate(shift=0):
    f = np.full((H, W, 3), (38, 44, 56), np.uint8)
    f[:, (np.arange(W) + shift) % 12 == 0] = (58, 66, 80)            # grid lines
    f[(np.arange(H) + shift) % 12 == 0, :] = (58, 66, 80)
    return f


def footage(seed):
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (H // 10, W // 10, 3), dtype=np.uint8)
    return np.kron(base, np.ones((10, 10, 1), np.uint8)) // 2 + rng.integers(0, 120, (H, W, 3), dtype=np.uint8)


def card_on_plate(share):
    f = plate()
    w = int(W * share)
    f[:, :w] = (230, 225, 210)                                         # a pale card over part of the grid
    f[10:20, 5:w - 5] = (20, 20, 20)
    return f


def run(segments):
    """segments: [(seconds, frame_fn)] -> analysed result."""
    frames = []
    for secs, fn in segments:
        frames += [fn(i) for i in range(int(secs * FPS))]
    plates = np.stack([plate(s) for s in range(4)])
    return Q.analyse(np.stack(frames), plates, FPS)


class RenderQATest(unittest.TestCase):
    def test_bare_grid_is_found_with_its_time(self):
        r = run([(3, lambda i: footage(1)), (2, lambda i: plate(i % 4)), (3, lambda i: footage(2))])
        self.assertEqual(len(r["bare_plate"]), 1)
        self.assertAlmostEqual(r["bare_plate"][0]["start"], 3.0, delta=0.15)
        self.assertAlmostEqual(r["bare_plate_s"], 2.0, delta=0.2)

    def test_small_card_on_grid_is_sparse_full_card_is_not(self):
        r = run([(2, lambda i: card_on_plate(0.15)), (2, lambda i: card_on_plate(0.9))])
        self.assertAlmostEqual(r["sparse_plate_s"], 2.0, delta=0.2)
        self.assertEqual(r["bare_plate_s"], 0.0)

    def test_blank_frames(self):
        r = run([(3, lambda i: footage(3)), (1, lambda i: np.zeros((H, W, 3), np.uint8)), (3, lambda i: footage(4))])
        self.assertAlmostEqual(r["blank_s"], 1.0, delta=0.15)
        self.assertEqual(r["bare_plate_s"], 0.0)                       # black is blank, never counted as grid

    def test_one_second_clip_is_a_flash_and_a_short_shot(self):
        r = run([(4, lambda i: footage(5)), (1, lambda i: footage(6)), (4, lambda i: footage(7))])
        self.assertEqual(len(r["flash_shots"]), 1)
        self.assertAlmostEqual(r["flash_shots"][0]["start"], 4.0, delta=0.15)
        self.assertEqual(len(r["short_shots"]), 1)

    def test_ordinary_shots_pass(self):
        r = run([(4, lambda i: footage(8)), (5, lambda i: footage(9)), (3.5, lambda i: footage(10))])
        self.assertEqual((r["short_shots"], r["bare_plate"], r["blank"]), ([], [], []))
        self.assertEqual(len(r["shots"]), 3)

    def test_montage_window_is_excused(self):
        frames = [footage(20 + k) for k in range(3) for _ in range(10)] + [footage(30)] * 40
        r = Q.analyse(np.stack(frames), None, FPS, montage=[(0.0, 3.0)])
        self.assertEqual(len(r["montage_cuts"]), 3)
        self.assertEqual(r["short_shots"], [])

    def test_no_backdrop_means_no_grid_report(self):
        frames = np.stack([plate()] * 20)
        r = Q.analyse(frames, None, FPS)
        self.assertEqual(r["bare_plate"], [])

    def test_text_report_lists_timestamps(self):
        r = run([(3, lambda i: footage(1)), (2, lambda i: plate()), (1, lambda i: footage(2)), (3, lambda i: footage(3))])
        t = Q.text(dict(r, video="x.mp4"))
        self.assertIn("BARE  0:03.00", t)
        self.assertIn("SHORT 0:05.00", t)


if __name__ == "__main__":
    unittest.main()
