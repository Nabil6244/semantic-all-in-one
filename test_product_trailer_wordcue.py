"""Word-timed builds (product_trailer/wordcue.py): each item of a graphic appears on the word that names it, as in the S27 reference videos
(docs/product_trailer/REVIEW_REFERENCE_4.md, gap 1). Items that are never named keep the layer's own stagger."""
import unittest

from product_trailer import wordcue as C


def words(text, t0=0.0, wps=3.0):
    out, t = [], t0
    for w in text.split():
        out.append((w.strip(".,"), round(t, 3), round(t + 1 / wps - 0.05, 3)))
        t += 1 / wps
    return out


class PhraseTime(unittest.TestCase):
    def test_finds_a_word_inside_the_window_only(self):
        W = C.wtimes(words("the ultra is big and the ultra is fast", t0=10))
        self.assertAlmostEqual(C.phrase_time(W, "Ultra", 10.0, 20.0), 10.333, places=2)
        self.assertAlmostEqual(C.phrase_time(W, "Ultra", 11.0, 20.0), 12.0, places=2)
        self.assertIsNone(C.phrase_time(W, "Ultra", 12.1, 20.0))

    def test_number_with_unit_matches_split_or_joined_words(self):
        W = C.wtimes(words("all four start with 12 GB of RAM", t0=0))
        self.assertAlmostEqual(C.phrase_time(W, "12GB RAM", 0, 9), 1.333, places=2)
        W2 = C.wtimes(words("all four start with 12GB of RAM", t0=0))
        self.assertAlmostEqual(C.phrase_time(W2, "12GB", 0, 9), 1.333, places=2)


class CueLayers(unittest.TestCase):
    def test_colour_phones_pop_in_spoken_order(self):
        W = C.wtimes(words("four colours black blue light pink and white", t0=20))
        L = {"type": "pt_flatphones", "start": 20.0, "end": 26.0,
             "phones": [{"label": "Black"}, {"label": "Blue"}, {"label": "Light Pink"}, {"label": "White"}]}
        C.cue_layers([L], W)
        ats = [p.get("at") for p in L["phones"]]
        self.assertEqual(ats, sorted(ats))
        self.assertAlmostEqual(ats[0], 0.67, places=1)     # "black" is the third word
        self.assertAlmostEqual(ats[3], 2.33, places=1)

    def test_shared_words_do_not_cue_and_distinct_word_does(self):
        W = C.wtimes(words("the pro gets the regular chip but the ultra gets extreme", t0=0))
        L = {"type": "pt_flatphones", "start": 0.0, "end": 6.0,
             "phones": [{"label": "Galaxy S27 Pro"}, {"label": "Galaxy S27 Ultra"}]}
        C.cue_layers([L], W)
        self.assertAlmostEqual(L["phones"][0]["at"], 0.33, places=1)
        self.assertAlmostEqual(L["phones"][1]["at"], 2.67, places=1)

    def test_badge_named_later_gets_its_own_time(self):
        W = C.wtimes(words("all four models start with twelve gigs and the ultra adds 16GB of RAM", t0=0))
        L = {"type": "pt_flatphones", "start": 0.0, "end": 8.0,
             "phones": [{"label": "Base"}, {"label": "Ultra", "badge": "16GB RAM"}]}
        C.cue_layers([L], W)
        self.assertAlmostEqual(L["phones"][1]["at"], 3.0, places=1)          # "ultra"
        self.assertAlmostEqual(L["phones"][1]["badge_at"], 3.67, places=1)   # "16GB"
        self.assertNotIn("at", L["phones"][0])                               # "Base" is never said: its own stagger

    def test_nothing_named_leaves_layer_untouched(self):
        W = C.wtimes(words("nothing here matches at all", t0=0))
        L = {"type": "pt_compare3", "start": 0.0, "end": 5.0, "cols": [{"label": "Alpha", "value": 1}, {"label": "Beta", "value": 2}]}
        before = repr(L)
        C.cue_layers([L], W)
        self.assertEqual(repr(L), before)

    def test_every_list_layer_is_cued(self):
        W = C.wtimes(words("exynos scores fourteen thousand while snapdragon scores less", t0=5))
        for typ, key, field in (("pt_bench", "rows", "label"), ("pt_compare3", "cols", "label"), ("pt_glass", "cards", "title"),
                                ("pt_gauge", "gauges", "label"), ("pt_thermal", "phones", "label"), ("pt_coststack", "rows", "label")):
            L = {"type": typ, "start": 5.0, "end": 10.0, key: [{field: "Exynos 2700", "value": 1}, {field: "Snapdragon", "value": 2}]}
            C.cue_layers([L], W)
            self.assertAlmostEqual(L[key][0]["at"], 0.0, places=1, msg=typ)
            self.assertAlmostEqual(L[key][1]["at"], 1.67, places=1, msg=typ)

    def test_word_said_before_the_layer_is_not_used(self):
        W = C.wtimes(words("blue and black", t0=0))
        L = {"type": "pt_flatphones", "start": 5.0, "end": 9.0, "phones": [{"label": "Blue"}, {"label": "Black"}]}
        C.cue_layers([L], W)
        self.assertNotIn("at", L["phones"][0])

    def test_missing_items_follow_the_one_before(self):
        W = C.wtimes(words("first the blue one then more", t0=0))
        L = {"type": "pt_flatphones", "start": 0.0, "end": 5.0, "phones": [{"label": "Blue"}, {"label": "Green"}]}
        C.cue_layers([L], W)
        self.assertGreater(L["phones"][1]["at"], L["phones"][0]["at"])

    def test_tweet_marker_sweeps_when_the_phrase_is_read(self):
        W = C.wtimes(words("samsung has fitted an outdated 3x 10MP telephoto lens", t0=40))
        L = {"type": "pt_tweet", "start": 40.0, "end": 46.0, "text": "x", "highlight": "outdated 3x 10MP telephoto lens"}
        C.cue_layers([L], W)
        self.assertAlmostEqual(L["highlight_at"], 1.33, places=1)

    def test_held_copy_is_left_alone_and_lists_are_not_shared(self):
        W = C.wtimes(words("blue then black", t0=0))
        shared = [{"label": "Blue"}, {"label": "Black"}]
        L = {"type": "pt_flatphones", "start": 0.0, "end": 4.0, "phones": shared}
        H = {"type": "pt_flatphones", "start": 4.0, "end": 8.0, "phones": shared, "hold": True, "t0": 0.0}
        C.cue_layers([L, H], W)
        self.assertIn("at", L["phones"][0])
        self.assertNotIn("at", shared[0])
        self.assertIs(H["phones"], shared)


class FirstItem(unittest.TestCase):
    def test_a_fresh_canvas_is_never_empty_for_long(self):
        W = C.wtimes(words("samsung is planning a new colour for the ultra", t0=0))
        L = {"type": "pt_flatphones", "start": 0.0, "end": 4.0, "phones": [{"label": "Galaxy S27 Ultra"}, {"label": "Black"}]}
        C.cue_layers([L], W)
        self.assertLessEqual(min(p.get("at", 0) for p in L["phones"]), C.FIRST_MAX)


class PlannerHook(unittest.TestCase):
    def test_timed_review_pops_each_colour_on_its_word(self):
        from product_trailer import review, voiceover as V
        lines = ["Samsung is planning four colours for the Ultra.", "They are black blue light pink and white this year."]
        script = ("# R\n" + lines[0] + "\n"
                  '[scene: {"title": "Colours", "phones": [{"label": "Black"}, {"label": "Blue"}, {"label": "Light Pink"}, {"label": "White"}]}]\n' + lines[1] + "\n")
        parsed = review.parse_script(script)
        pack = review.plan_review_scenes(parsed, "galaxy s27 ultra", ["Black", "Blue"])
        W, t = [], 0.5
        for ln in lines:
            for w in ln.split():
                W.append((w.strip(".,"), round(t, 3), round(t + 0.28, 3)))
                t += 1 / 3
            t += 0.6
        voice = V.align_lines(lines, W, W[-1][2] + 1.0)
        spec = review.plan_review_timed(parsed, pack, {}, voice, W, style="infographic")
        L = next(x for x in spec["layers"] if x["type"] == "pt_flatphones" and x["phones"][0].get("label") == "Black")
        ats = [p.get("at") for p in L["phones"]]
        self.assertTrue(all(a is not None for a in ats), ats)
        said = {w[0].lower(): w[1] for w in W}
        self.assertAlmostEqual(L["start"] + ats[1], said["blue"], places=1)
        self.assertEqual(ats, sorted(ats))


if __name__ == "__main__":
    unittest.main()
