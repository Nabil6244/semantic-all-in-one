"""Colour cards (product_trailer/swatches.py + layers/pt_swatches.mjs, REVIEW_REFERENCE_4 gap 3): a colour sentence becomes a row of colour cards
in spoken order; later sentences add an "online exclusive" card, drop a "?" on every card when the shades are unknown, and slide an older
model's colour card over the one it is compared with. The older colour-phones scene stays in rotation."""
import unittest

from product_trailer import director, swatches as SW, wordcue as C


def words(text, t0=0.0, wps=3.0):
    out, t = [], t0
    for w in text.split():
        out.append((w.strip(".,'"), round(t, 3), round(t + 1 / wps - 0.05, 3)))
        t += 1 / wps
    return out


LINE = "Samsung is planning four standard colour options for the S27 Ultra, black, blue, light pink, and white."


class Director(unittest.TestCase):
    def test_colour_sentence_gives_cards_in_spoken_order(self):
        sc = director.scene_for(LINE, "Galaxy S27 Ultra", {})
        L = sc["layer"]
        self.assertEqual(L["type"], "pt_swatches")
        self.assertEqual([c["name"] for c in L["cards"]], ["Black", "Blue", "Light Pink", "White"])
        self.assertIn("S27 Ultra", L["title"])

    def test_the_older_colour_phones_stay_in_rotation(self):
        ctx = {}
        first = director.scene_for(LINE, "Galaxy S27 Ultra", ctx)["layer"]
        second = director.scene_for("The S28 comes in green, gold, silver and navy colours.", "Galaxy S27 Ultra", ctx)["layer"]
        self.assertEqual(first["type"], "pt_swatches")
        self.assertEqual(second.get("type", "pt_flatphones"), "pt_flatphones")

    def test_online_only_colour_gets_a_tag(self):
        sc = director.scene_for("Colour options are black, blue, white and an online exclusive violet.", "Galaxy S27 Ultra", {})
        cards = sc["layer"]["cards"]
        self.assertEqual(cards[-1]["name"], "Violet")
        self.assertEqual(cards[-1].get("tag"), "Online Exclusive")
        self.assertNotIn("tag", cards[0])


class FollowUps(unittest.TestCase):
    def layer(self, start=0.0, end=30.0):
        return {"type": "pt_swatches", "title": "S27 Ultra colour options", "start": start, "end": end,
                "cards": [{"name": "Black", "color": "#2b2b2e"}, {"name": "Blue", "color": "#3f6fb5"}, {"name": "Light Pink", "color": "#e9b4c4"}, {"name": "White", "color": "#ecebea"}]}

    def test_a_later_online_only_colour_is_added_on_its_word(self):
        L = self.layer()
        W = C.wtimes(words("there will also be an online only violet variant", t0=10))
        SW.follow([L], W)
        self.assertEqual(L["cards"][-1]["name"], "Violet")
        self.assertEqual(L["cards"][-1]["tag"], "Online Exclusive")
        self.assertAlmostEqual(L["cards"][-1]["at"], 12.33, places=1)

    def test_unknown_shades_drop_a_question_mark(self):
        L = self.layer()
        W = C.wtimes(words("now we still don't know the exact shades", t0=6))
        SW.follow([L], W)
        self.assertAlmostEqual(L["q_at"], 7.0, places=1)

    def test_an_older_model_colour_slides_over_its_match(self):
        L = self.layer()
        W = C.wtimes(words("whether the blue will be similar to the S26 Ultra sky blue or the light pink like the pink gold option", t0=0))
        SW.follow([L], W)
        blue = next(c for c in L["cards"] if c["name"] == "Blue")
        self.assertEqual(blue["ref"]["label"], "Galaxy S26 Ultra")
        self.assertEqual(blue["ref"]["name"], "Sky Blue")
        self.assertEqual(len(L["cards"]), 4, "a compared colour is not a new card")

    def test_own_model_is_not_a_reference(self):
        L = self.layer()
        W = C.wtimes(words("the S27 Ultra black looks great", t0=0))
        SW.follow([L], W)
        self.assertFalse(any("ref" in c for c in L["cards"]))

    def test_cards_pop_on_their_words(self):
        L = self.layer(start=20.0, end=30.0)
        W = C.wtimes(words("black blue light pink and white", t0=20.3))
        C.cue_layers([L], W)
        ats = [c["at"] for c in L["cards"]]
        self.assertEqual(ats, sorted(ats))
        self.assertAlmostEqual(ats[1], 0.63, places=1)


class Planner(unittest.TestCase):
    def test_the_colour_canvas_carries_into_the_next_colour_sentence(self):
        from product_trailer import review, voiceover as V
        lines = [LINE, "There will also be an online only violet variant for the Ultra.", "Battery life should be the same as last year."]
        parsed = review.parse_script("# R\n" + "\n".join(lines) + "\n")
        parsed = director.auto_direct(parsed, "Galaxy S27 Ultra")
        pack = review.plan_review_scenes(parsed, "galaxy s27 ultra", ["Black"])
        W, t = [], 0.5
        for ln in lines:
            for w in ln.split():
                W.append((w.strip(".,"), round(t, 3), round(t + 0.28, 3)))
                t += 1 / 3
            t += 0.6
        voice = V.align_lines(lines, W, W[-1][2] + 1.0)
        spec = review.plan_review_timed(parsed, pack, {}, voice, W, style="mixed")
        L = next(x for x in spec["layers"] if x["type"] == "pt_swatches")
        self.assertGreater(L["end"], voice["spans"][1][0] + 1.0, "the cards stay up through the violet sentence")
        self.assertLess(L["end"], voice["spans"][2][0] + 0.1, "and end when the narration moves on")
        self.assertEqual(L["cards"][-1]["name"], "Violet")


if __name__ == "__main__":
    unittest.main()
