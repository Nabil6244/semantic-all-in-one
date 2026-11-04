"""Explainer sentences get a picture of their own point: section labels, reliability tags, dates, named sources, verdicts, choices,
contradictions, sizes, a lost camera, a dropped zoom, who-gets-it lists, and a bare figure read in the unit of the sentence before it.
CSV rows go in after the director, and filler shots follow the subject. Synthetic sentences only."""
import unittest

from product_trailer import director as D, review

PHONE = "Galaxy S27 Ultra"


def pick(text, ctx=None):
    return D.scene_for(text, PHONE, ctx)


class Talk(unittest.TestCase):
    def test_section_labels_and_reliability(self):
        self.assertEqual((pick("Second, the cameras.")["kicker"], pick("Second, the cameras.")["value"]), ("SECOND", "Cameras"))
        self.assertEqual(pick("This one is a rumor.")["value"], "Rumor")
        self.assertEqual(pick("This is the most reliable certification so far.")["value"], "Certified")
        self.assertEqual(pick("I'd call this medium reliability, because it is early.")["value"], "Medium")
        self.assertEqual(pick("That's a tipster, not Samsung.")["value"], "Unconfirmed")
        self.assertEqual(pick("Everything here is a rumor, a leak, or a certification.")["value"], "Rumor · Leak · Certified")

    def test_dates_and_prices_not_known(self):
        c = pick("Samsung hasn't announced it, and it's expected in early 2027.")
        self.assertEqual((c["value"], c["sub"]), ("Early 2027", "not announced yet"))
        self.assertEqual(pick("If you need a phone now, Black Friday is November 27th.")["value"], "Nov 27")
        self.assertEqual(pick("I don't have confirmed Black Friday prices yet.")["value"], "Not confirmed")

    def test_named_sources(self):
        self.assertEqual(pick("Android Headlines built dummy units from files.")["author"], "Android Headlines")
        self.assertEqual(pick("Tipster Ice Universe says there is no Exynos.")["author"], "Ice Universe")
        self.assertNotEqual((pick("Samsung said nothing about it today.") or {}).get("author"), "Samsung")

    def test_verdicts_choices_contradictions(self):
        self.assertEqual(pick("If your phone still works fine, wait.")["value"], "Wait")
        c = pick("The battery looks like the real upgrade, and the camera change is the risk.")
        self.assertEqual((c["value"], c["sub"]), ("Battery", "the risk: camera"))
        q = pick("Which matters more to you: the bigger battery, or keeping the 3x camera?")["layer"]
        self.assertEqual([p["top"] for p in q["phones"]], ["Bigger battery", "3x camera"])
        k = pick("It was first rumored to look Google-inspired, and now the leaks say iPhone-like.")["layer"]
        self.assertEqual(k["title"], "Conflicting leaks")
        w = pick("Should you wait for this phone or buy the S26 Ultra now?")["layer"]
        self.assertEqual([p["text"] for p in w["phones"]], ["WAIT?", "BUY?"])
        self.assertEqual(pick("Your S26 Ultra case probably won't fit.")["value"], "Won't fit")


class Figures(unittest.TestCase):
    def test_sizes_cameras_zoom(self):
        s = pick("It is slightly bigger than the S26 Ultra: 163.76 by 78.25 by 7.97 millimeters, compared to 163.6 by 78.1 by 7.9.")["layer"]
        self.assertEqual([p["top"] for p in s["phones"]], ["163.6 x 78.1 x 7.9", "163.76 x 78.25 x 7.97"])
        self.assertEqual(s["phones"][1]["badge"], "+0.16 mm")
        c = pick("The next Ultra may have lost a camera.")["layer"]
        self.assertEqual([p["cams"] for p in c["phones"]], [4, 3])
        self.assertEqual(pick("That means the 3x telephoto would be dropped.")["layer"]["phones"][0]["badge"], "Dropped")
        self.assertEqual(pick("New dummies show a wide camera bar on the back.")["text"], "Camera bar")

    def test_who_gets_it(self):
        L = pick("The S27 Pro and S27 Ultra get a Privacy Display, while the S27 and S27 Plus won't get it.")["layer"]
        self.assertEqual({p["label"]: p["badge"] for p in L["phones"]},
                         {"Galaxy S27 Pro": "Yes", "Galaxy S27 Ultra": "Yes", "Galaxy S27": "No", "Galaxy S27 Plus": "No"})

    def test_a_bare_figure_takes_the_unit_of_the_point_before_it(self):
        L = pick("The S26 Ultra has 5,000, so that's about 700 more, roughly 14 percent.", {"unit": "mAh", "topic": "battery"})["layer"]
        self.assertEqual([p["top"] for p in L["phones"]], ["5,000mAh", "5,700mAh"])
        self.assertEqual(L["phones"][1]["badge"], "+700mAh · +14%")
        parsed = D.auto_direct(review.parse_script("The 3C listing shows 5,534 milliamp hours.\nThe S26 Ultra has 5,000, so that's about 700 more."))
        scenes = [it for it in parsed["chapters"][0]["items"] if it["kind"] == "scene"]
        self.assertEqual(scenes[-1]["layer"]["phones"][1]["top"], "5,700mAh")

    def test_evidence_shows_the_figure(self):
        self.assertEqual(pick("China's 3C listing shows a rated capacity of 5,534 milliamp hours.")["layer"]["stamp"], "5,534mAh")


class Planning(unittest.TestCase):
    def test_a_csv_filler_row_never_takes_a_sentence_that_has_its_own_scene(self):
        parsed = D.auto_direct(review.parse_script("The S26 Ultra has 5,000 mAh, about 700 mAh more.\nIt is what it is today."))
        out = review.place_features(parsed, [{"value": "Less. But more"}])
        items = out["chapters"][0]["items"]
        i = next(n for n, it in enumerate(items) if it["kind"] == "feature")
        self.assertEqual(items[i + 1]["text"], "It is what it is today.")

    def test_filler_follows_the_subject(self):
        self.assertEqual(review._filler_shot("p", ["Black"], 0, ["island"], "battery")["object"], "xray")
        self.assertEqual(review._filler_shot("p", ["Black"], 0, ["edge"], "camera")["move"], "island")
        self.assertEqual(review._filler_shot("p", ["Black"], 0, ["edge"])["move"], "edge")


if __name__ == "__main__":
    unittest.main()
