"""New 3D every time (product_trailer/variety3d.py): no move twice in a row, no move over its share, each shot its own camera,
a different film for a different seed, dark text keeps the bright set. Synthetic specs, no render."""
import unittest

from product_trailer import variety3d as V


def spec_of(moves, dark=()):
    shots = [{"kind": "product", "object": "phone", "move": m, "backdrop": "daylight", "start": i * 3.0, "end": i * 3.0 + 3} for i, m in enumerate(moves)]
    layers = [{"type": "pt_words", "ink": "dark", "start": i * 3.0 + 0.2, "end": i * 3.0 + 2.5} for i in dark]
    return {"shots": shots, "layers": layers}


S27 = ["island", "flip", "island", "edge", "island", "monolith", "monolith", "flip", "port", "monolith", "monolith", "flip", "monolith", "flip",
       "island", "flip", "screen", "rise", "orbit", "rise", "orbit", "rise", "screen", "hero", "orbit", "screen", "hero", "orbit", "screen", "orbit",
       "screen", "hero", "orbit", "hero", "orbit", "rise", "island"]   # the 3D phone moves of the S27 leaks film, in order


class Variety(unittest.TestCase):
    def test_no_move_twice_in_a_row_and_none_over_its_share(self):
        out = V.vary_shots(spec_of(S27), 1)
        moves = [s["move"] for s in out["shots"]]
        self.assertFalse([i for i in range(1, len(moves)) if moves[i] == moves[i - 1]])
        cap = -(-len(moves) * V.SHARE // 1)
        self.assertLessEqual(max(moves.count(m) for m in set(moves)), cap + 1)
        self.assertGreaterEqual(len(set(moves)), 10)

    def test_a_swap_shows_the_same_part_of_the_phone(self):
        before = spec_of(S27)
        out = V.vary_shots(spec_of(S27), 2)
        for a, b in zip(before["shots"], out["shots"]):
            self.assertEqual(V.GROUP_OF[a["move"]], V.GROUP_OF[b["move"]])

    def test_every_shot_its_own_camera(self):
        out = V.vary_shots(spec_of(S27), 3)
        prints = [V.fingerprint(s) for s in out["shots"]]
        self.assertEqual(len(prints), len(set(prints)))
        self.assertTrue(all("vary" in s and s["cam_side"] in ("left", "right") for s in out["shots"]))

    def test_new_video_new_shots(self):
        a = {V.fingerprint(s) for s in V.vary_shots(spec_of(S27), V.film_seed("video1.mp3", "script"))["shots"]}
        b = {V.fingerprint(s) for s in V.vary_shots(spec_of(S27), V.film_seed("video2.mp3", "script"))["shots"]}
        self.assertLess(len(a & b) / len(a), 0.2)
        same = {V.fingerprint(s) for s in V.vary_shots(spec_of(S27), V.film_seed("video1.mp3", "script"))["shots"]}
        self.assertEqual(a, same)                     # the same inputs give the same film

    def test_dark_text_keeps_the_bright_set(self):
        out = V.vary_shots(spec_of(S27, dark=range(len(S27))), 4)
        self.assertEqual({s["backdrop"] for s in out["shots"]}, {"daylight"})
        free = V.vary_shots(spec_of(S27), 4)
        self.assertGreater(len({s["backdrop"] for s in free["shots"]}), 1)


if __name__ == "__main__":
    unittest.main()
