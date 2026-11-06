"""Lens callouts (product_trailer/lenses.py + layers/pt_lenses.mjs, REVIEW_REFERENCE_4 gap 4): a camera sentence draws the phone's lenses with a
line out to each named lens ("ultrawide 12MP"); a lens asked about shows "??"; when a later sentence gives the answer the "??" turns into it, on
the word, in the same scene, or in a short recap of the callouts after the shot where the answer is said. The older camera scenes stay in rotation."""
import unittest

from product_trailer import director, lenses as LZ, wordcue as C


def words(text, t0=0.0, wps=3.0):
    out, t = [], t0
    for w in text.split():
        out.append((w.strip(".,?'"), round(t, 3), round(t + 1 / wps - 0.05, 3)))
        t += 1 / wps
    return out


def lens(L, kind):
    return next((x for x in L["lenses"] if x["kind"] == kind), None)


class Parse(unittest.TestCase):
    def test_values_go_to_the_nearest_lens(self):
        m = LZ.mentions("a 12MP ultra wide a 50MP main and a 3x telephoto".split())
        got = {k: v for k, _i, v in m}
        self.assertEqual(got, {"ultrawide": "12MP", "main": "50MP", "telephoto": "3x"})

    def test_megapixel_and_zoom_together(self):
        m = LZ.mentions("an outdated 3x 10MP telephoto lens".split())
        self.assertEqual(m[0][0], "telephoto")
        self.assertEqual(m[0][2], "10MP")

    def test_the_ultra_model_is_not_an_ultrawide(self):
        self.assertEqual(LZ.mentions("the s27 ultra gets a new main sensor".split()), [("main", 6, None)])


class Director(unittest.TestCase):
    def test_two_lenses_named_give_callouts(self):
        sc = director.scene_for("We've also heard about the main and ultra-wide cameras on the S27 and S27 Plus.", "Galaxy S27 Ultra", {})
        L = sc["layer"]
        self.assertEqual(L["type"], "pt_lenses")
        self.assertEqual([x["kind"] for x in L["lenses"]], ["ultrawide", "main"])
        self.assertEqual([p["label"] for p in L["phones"]], ["Galaxy S27", "Galaxy S27 Plus"])

    def test_a_lens_asked_about_is_unknown(self):
        sc = director.scene_for("But what about the telephoto camera and the main camera?", "Galaxy S27", {})
        self.assertEqual(lens(sc["layer"], "telephoto")["value"], "??")

    def test_older_camera_scenes_stay_in_rotation(self):
        ctx = {}
        a = director.scene_for("It has a 200MP main camera and a 50MP ultrawide.", "Galaxy S27 Ultra", ctx)
        self.assertIsNone(director.scene_for("The cameras keep the same sensors as before.", "Galaxy S27 Ultra", ctx), "a camera follow-up keeps the scene")
        director.scene_for("The battery stays the same this year.", "Galaxy S27 Ultra", ctx)
        b =director.scene_for("The S26 had a 200MP main camera and a 12MP ultrawide.", "Galaxy S27 Ultra", ctx)
        self.assertEqual(a["layer"]["type"], "pt_lenses")
        self.assertNotEqual((b.get("layer") or {}).get("type"), "pt_lenses")


class FollowUps(unittest.TestCase):
    def layer(self, start=0.0, end=20.0):
        return {"type": "pt_lenses", "title": "Cameras", "start": start, "end": end, "phones": [{"label": "Galaxy S27"}],
                "lenses": [{"kind": "ultrawide", "cap": "ultrawide", "value": "12MP"}, {"kind": "main", "cap": "main", "value": "50MP"}]}

    def test_lenses_appear_on_their_words(self):
        L = self.layer(start=1.0)
        LZ.follow([L], C.wtimes(words("the 12MP ultra wide and the 50MP main", t0=1.0)))
        self.assertAlmostEqual(lens(L, "ultrawide")["at"], 0.33, places=1)
        self.assertGreater(lens(L, "main")["at"], lens(L, "ultrawide")["at"])

    def test_a_question_adds_an_unknown_lens(self):
        L = self.layer()
        LZ.follow([L], C.wtimes(words("but what about the telephoto camera", t0=5)))
        t = lens(L, "telephoto")
        self.assertEqual(t["value"], "??")
        self.assertAlmostEqual(t["at"], 6.33, places=1)

    def test_the_answer_turns_the_question_marks_into_the_value(self):
        L = self.layer()
        L["lenses"].append({"kind": "telephoto", "cap": "telephoto", "value": "??", "at": 2.0})
        LZ.follow([L], C.wtimes(words("they keep the same 3x telephoto camera", t0=9)))
        t = lens(L, "telephoto")
        self.assertEqual((t["was"], t["value"]), ("??", "3x"))
        self.assertAlmostEqual(t["set_at"], 10.33, places=1)


class Recap(unittest.TestCase):
    def test_an_answer_after_the_scene_gets_a_short_recap(self):
        L = {"type": "pt_lenses", "title": "Cameras", "start": 0.0, "end": 6.0, "phones": [{"label": "Galaxy S27"}],
             "lenses": [{"kind": "main", "cap": "main", "value": "50MP", "at": 0.5}, {"kind": "telephoto", "cap": "telephoto", "value": "??", "at": 2.0}]}
        tweet = {"type": "pt_tweet", "text": "x", "start": 6.05, "end": 15.95}
        shots = [{"id": "s01", "kind": "black", "start": 0.0, "end": 6.0}, {"id": "s02", "kind": "black", "start": 6.0, "end": 16.0}]
        layers = [{"type": "pt_paper", "start": 0.0, "end": 6.0}, L, {"type": "pt_paper", "start": 6.0, "end": 16.0}, tweet, {"type": "pt_subtitle", "chunks": []}]
        W = C.wtimes(words("samsung has fitted an outdated 3x 10MP telephoto lens", t0=7.0))
        LZ.resolve_later(shots, layers, W)
        self.assertEqual(len(shots), 3)
        cut = shots[1]["end"]
        self.assertEqual(shots[2]["start"], cut)
        self.assertEqual(shots[2]["end"], 16.0)
        self.assertGreaterEqual(cut - 6.0, LZ.MIN_KEEP_S, "the tweet keeps its read")
        self.assertLessEqual(tweet["end"], cut)
        R = [x for x in layers if x["type"] == "pt_lenses"][-1]
        self.assertIsNot(R, L)
        self.assertEqual(R["start"], cut)
        tele = lens(R, "telephoto")
        self.assertEqual((tele["was"], tele["value"]), ("??", "10MP"))
        self.assertEqual(lens(L, "telephoto")["value"], "??", "the first scene still asks")
        self.assertTrue(any(x["type"] == "pt_paper" and x["start"] == cut for x in layers))
        self.assertEqual(layers[-1]["type"], "pt_subtitle", "the recap draws under the subtitles")

    def test_no_answer_no_recap(self):
        L = {"type": "pt_lenses", "start": 0.0, "end": 6.0, "phones": [{"label": "S27"}], "lenses": [{"kind": "telephoto", "value": "??"}]}
        shots = [{"id": "s01", "kind": "black", "start": 0.0, "end": 6.0}, {"id": "s02", "kind": "product", "start": 6.0, "end": 12.0}]
        LZ.resolve_later(shots, [L], C.wtimes(words("nothing about it here", t0=7)))
        self.assertEqual(len(shots), 2)


class Planner(unittest.TestCase):
    def test_question_then_answer_in_one_canvas(self):
        from product_trailer import review, voiceover as V
        lines = ["We have heard about the main and ultra wide cameras on the S27.", "But what about the telephoto camera?",
                 "The S27 keeps the same 3x telephoto camera.", "Battery life should be the same as last year."]
        parsed = director.auto_direct(review.parse_script("# R\n" + "\n".join(lines) + "\n"), "Galaxy S27")
        pack = review.plan_review_scenes(parsed, "galaxy s27", ["Black"])
        W, t = [], 0.5
        for ln in lines:
            for w in ln.split():
                W.append((w.strip(".,?"), round(t, 3), round(t + 0.28, 3)))
                t += 1 / 3
            t += 0.6
        voice = V.align_lines(lines, W, W[-1][2] + 1.0)
        spec = review.plan_review_timed(parsed, pack, {}, voice, W, style="mixed")
        L = next(x for x in spec["layers"] if x["type"] == "pt_lenses")
        tele = lens(L, "telephoto")
        self.assertIsNotNone(tele)
        self.assertEqual(tele["value"], "3x")
        self.assertEqual(tele["was"], "??")


if __name__ == "__main__":
    unittest.main()
