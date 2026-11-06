"""Ring highlight on a named part (REVIEW_REFERENCE_4 gap 5): "the 5x lens looks smaller" -> a lens macro in 3D with a yellow ring drawn round
that lens (pt_ring, tracked by the 3D phone's projected lens positions); inside a lens-callout scene the ring goes round that callout's lens."""
import unittest

from product_trailer import director, lenses as LZ, review, wordcue as C


def words(text, t0=0.0, wps=3.0):
    out, t = [], t0
    for w in text.split():
        out.append((w.strip(".,?'"), round(t, 3), round(t + 1 / wps - 0.05, 3)))
        t += 1 / wps
    return out


class Director(unittest.TestCase):
    def test_a_lens_that_looks_smaller_gets_a_ringed_macro(self):
        it = director.scene_for("People say the 5X camera lens on the S27 Ultra looks much smaller compared to the S26 Ultra.", "Galaxy S27 Ultra", {})
        self.assertEqual(it["kind"], "macro")
        self.assertEqual(it["move"], "island")
        self.assertEqual(it["ring"]["index"], -1)
        self.assertEqual(it["ring"]["phrase"].lower(), "5x")

    def test_main_lens_is_the_second_part(self):
        it = director.scene_for("The main camera lens looks bigger this year.", "Galaxy S27 Ultra", {})
        self.assertEqual(it["ring"]["index"], 1)

    def test_no_looks_word_no_ring(self):
        it = director.scene_for("The camera bar is back on the S27 Ultra.", "Galaxy S27 Ultra", {})
        self.assertNotIn("ring", it or {})


class Visual(unittest.TestCase):
    def test_macro_with_ring_adds_a_ring_layer_on_the_word(self):
        it = {"kind": "macro", "text": "5x lens", "move": "island", "ring": {"index": -1, "phrase": "5X"}}
        shot, make, _ = review.directive_visual(it, "galaxy s27 ultra", ["Black"], 0, {}, "mixed")
        self.assertEqual(shot["move"], "island")
        L = [x for x in make(10.0, 15.0) if x["type"] == "pt_ring"]
        self.assertEqual(len(L), 1)
        self.assertEqual(L[0]["index"], -1)
        C.cue_layers(L, C.wtimes(words("the 5X camera lens looks smaller", t0=10.0)))
        self.assertAlmostEqual(L[0]["at"], 0.23, places=1)   # layer starts 0.1 s after the shot


class InCallouts(unittest.TestCase):
    def test_looks_smaller_rings_that_callout(self):
        L = {"type": "pt_lenses", "start": 0.0, "end": 12.0, "phones": [{"label": "S27"}],
             "lenses": [{"kind": "main", "value": "50MP", "at": 0.2}, {"kind": "telephoto", "value": "10MP", "at": 1.0}]}
        LZ.follow([L], C.wtimes(words("and the telephoto lens looks much smaller", t0=4.0)))
        tele = next(x for x in L["lenses"] if x["kind"] == "telephoto")
        self.assertAlmostEqual(tele["ring_at"], 4.67, places=1)
        self.assertNotIn("ring_at", L["lenses"][0])


if __name__ == "__main__":
    unittest.main()
