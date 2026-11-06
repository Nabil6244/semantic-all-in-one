"""Two-sided figures (product_trailer/sides.py + layers/pt_sides.mjs, REVIEW_REFERENCE_5 gap 17): two figures of one kind in a sentence sit
either side of one phone, each with a small line under it and each landing on its word ("$1299 / S26 Ultra Launch Price | $1499 / S27 Ultra
Leaked Price"); "X instead of Y" reads "X / Not Y". The older flat before/now scenes stay in rotation."""
import unittest

from product_trailer import director, review, sides as SD, wordcue as C


def words(text, t0=0.0, wps=3.0):
    out, t = [], t0
    for w in text.split():
        out.append((w.strip(".,?'"), round(t, 3), round(t + 1 / wps - 0.05, 3)))
        t += 1 / wps
    return out


class Find(unittest.TestCase):
    def test_two_capacities(self):
        it = SD.sides_for("It sits right in between the 6,000 mAh and the 5,500 mAh battery we heard about.", "Galaxy S27 Ultra")
        self.assertEqual([x["value"] for x in it["items"]], ["6,000mAh", "5,500mAh"])
        self.assertEqual([x["side"] for x in it["items"]], ["left", "right"])

    def test_prices_with_models_and_kind(self):
        it = SD.sides_for("The S27 Ultra leaked price is $1,499, while the S26 Ultra launch price was $1,299.", "Galaxy S27 Ultra")
        a, b = it["items"]
        self.assertEqual((a["value"], b["value"]), ("$1,499", "$1,299"))
        self.assertEqual(a["sub"], "S27 Ultra Leaked Price")
        self.assertEqual(b["sub"], "S26 Ultra Launch Price")

    def test_watts_per_model(self):
        it = SD.sides_for("A listing shows 25 watts of charging on the regular S27 and then 45 watts on the S27 Plus.", "Galaxy S27")
        self.assertEqual([(x["value"], x["sub"]) for x in it["items"]], [("25W", "S27"), ("45W", "S27 Plus")])

    def test_instead_of_reads_not(self):
        it = SD.sides_for("It gets LPDDR5X memory instead of LPDDR6 and UFS 4.0 storage rather than UFS 5.0.", "Galaxy S27 Ultra")
        self.assertEqual([(x["value"], x["sub"]) for x in it["items"]], [("LPDDR5X", "Not LPDDR6"), ("UFS 4.0", "Not UFS 5.0")])

    def test_one_figure_or_a_range_is_not_two_sided(self):
        self.assertIsNone(SD.sides_for("The battery is 5,000 mAh.", "Galaxy S27"))
        self.assertIsNone(SD.sides_for("It charges from 0 to 50% in thirty minutes.", "Galaxy S27"))
        self.assertIsNone(SD.sides_for("Two numbers of different kinds: 45 watts and 5,000 mAh.", "Galaxy S27"))

    def test_prices_in_words_and_a_bare_second_price(self):
        it = SD.sides_for("Replacing the inner cover layer costs 49 dollars without AppleCare Plus, or 19 with it.", "iPhone Duo")
        self.assertEqual([(x["value"], x["sub"]) for x in it["items"]], [("$49", "Without AppleCare Plus"), ("$19", "With AppleCare Plus")])

    def test_inch_sizes_named_by_what_follows(self):
        it = SD.sides_for("It's a book-style foldable with a 5.4 inch outer display and a 7.6 inch inner display.", "iPhone Duo")
        self.assertEqual([(x["value"], x["sub"]) for x in it["items"]], [('5.4"', "Outer Display"), ('7.6"', "Inner Display")])

    def test_hours_named_by_what_follows(self):
        it = SD.sides_for("Apple rates it for up to 44 hours of video on the outer screen and 31 hours on the inner screen.", "iPhone Duo")
        self.assertEqual([(x["value"], x["sub"]) for x in it["items"]], [("44 hrs", "Outer Screen"), ("31 hrs", "Inner Screen")])

    def test_a_price_ladder_is_not_two_sided(self):
        self.assertIsNone(SD.sides_for("It starts at 1,999 dollars, then goes up to 2,199, 2,599, and 3,199 dollars.", "iPhone Duo"))


class Director(unittest.TestCase):
    def test_rotation_keeps_the_older_scene(self):
        ctx = {}
        a = director.scene_for("It sits right in between the 6,000 mAh and the 5,500 mAh battery we heard about.", "Galaxy S27 Ultra", ctx)
        b = director.scene_for("The S26 had 4,000 mAh and the S27 gets 5,000 mAh.", "Galaxy S27 Ultra", ctx)
        self.assertEqual(a["kind"], "sides")
        self.assertNotEqual((b or {}).get("kind"), "sides")

    def test_non_model_pairs_always_use_sides(self):
        ctx = {"sides_n": 1}                     # the next model pair would go to the older scene
        it = director.scene_for("Apple rates it for up to 44 hours of video on the outer screen and 31 hours on the inner screen.", "iPhone Duo", ctx)
        self.assertEqual(it["kind"], "sides", "outer / inner screen is not a before / after: never the older Previous / Now scene")


class Visual(unittest.TestCase):
    IT = {"kind": "sides", "items": [{"value": "$1,299", "sub": "S26 Ultra Launch Price", "side": "left"}, {"value": "$1,499", "sub": "S27 Ultra Leaked Price", "side": "right"}]}

    def test_3d_phone_in_the_middle_with_the_figures_either_side(self):
        shot, make, _ = review.directive_visual(dict(self.IT), "galaxy s27 ultra", ["Black"], 0, {}, "mixed")
        self.assertEqual(shot["kind"], "product")
        self.assertNotIn("frame_side", shot)
        L = [x for x in make(10.0, 16.0) if x["type"] == "pt_sides"][0]
        self.assertEqual(len(L["items"]), 2)
        self.assertEqual(L["ink"], "dark", "dark ink on the bright review set")

    def test_infographic_draws_it_on_the_paper(self):
        shot, make, _ = review.directive_visual(dict(self.IT), "galaxy s27 ultra", ["Black"], 0, {}, "infographic")
        types = [x["type"] for x in make(0.0, 5.0)]
        self.assertEqual(types[0], "pt_paper")
        self.assertIn("pt_flatphones", types)
        self.assertIn("pt_sides", types)

    def test_each_figure_lands_on_its_word(self):
        _, make, _ = review.directive_visual(dict(self.IT), "galaxy s27 ultra", ["Black"], 0, {}, "mixed")
        L = [x for x in make(10.0, 16.0) if x["type"] == "pt_sides"]
        C.cue_layers(L, C.wtimes(words("up from the $1,299 launch price to $1,499 now", t0=10.0)))
        ats = [x["at"] for x in L[0]["items"]]
        self.assertLess(ats[0], ats[1])
        self.assertAlmostEqual(L[0]["start"] + ats[1], 10.0 + 7 / 3, places=1)


if __name__ == "__main__":
    unittest.main()
