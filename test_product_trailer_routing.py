"""Phase 3.3: narration routes to the strongest existing visual (bars, price ladder, battery cutaway, timeline), not only to flat phones with a figure."""
import unittest

from product_trailer import director as D, review


class Routing(unittest.TestCase):
    def test_performance_claim_is_two_bars_with_the_old_phone_as_baseline(self):
        r = D.scene_for("It runs the same chip, and Apple says its thermal system gives it up to 35 percent better sustained performance than the iPhone 17 Pro.", "iPhone Duo", {})
        self.assertEqual(r["kind"], "bars")
        self.assertEqual(r["rows"][0]["value"], 135)
        self.assertEqual(r["rows"][1]["label"], "IPHONE 17 PRO")
        self.assertIn("APPLE", r["note"])

    def test_price_ladder_spoken_in_dollars(self):
        t = "The price starts at 1,999 dollars for 256 gigabytes, then goes up to 2,199, 2,599, and 3,199 dollars for the 2 terabyte model."
        r = D.scene_for(t, "iPhone Duo", {})
        self.assertEqual(r["kind"], "compare")
        self.assertEqual([c["value"] for c in r["cols"]], [1999, 2199, 2599, 3199])
        self.assertEqual([c["label"] for c in r["cols"]][0::3], ["256 GB", "2 TB"])

    def test_two_battery_figures_draw_battery_cutaways_in_proportion(self):
        r = D.scene_for("It has two batteries, and Apple rates it for up to 44 hours of video on the outer screen and 31 hours on the inner screen.", "iPhone Duo", {})
        ph = r["layer"]["phones"]
        self.assertTrue(all(p["cutaway"] for p in ph))
        self.assertAlmostEqual(ph[1]["cell"] / ph[0]["cell"], 31 / 44, places=1)

    def test_second_date_draws_a_timeline_with_both(self):
        ctx = {}
        D.scene_for("The phone launched on October 23 and owners complained within days of buying it.", "iPhone Duo", ctx)
        r = D.scene_for("It also supports the USB-C Apple Pencil, which arrived with an update on October 26.", "iPhone Duo", ctx)
        self.assertEqual(r["kind"], "timeline")
        self.assertEqual([(e["month"], e["day"]) for e in r["events"]], [(10, 23), (10, 26)])
        shot, make, _ = review.directive_visual(r, "iPhone Duo", [], 0, None, "news")
        lay = make(0.0, 6.0)[0]
        self.assertEqual(lay["type"], "tm_timeline")
        self.assertEqual((lay["from"], lay["to"]), (-1, 4))                         # days from the first date
        self.assertEqual([t["text"] for t in lay["ticks"]], ["OCT 23", "OCT 26"])

    def test_battery_cutaway_is_not_turned_into_floating_figures(self):
        r = D.scene_for("It has two batteries, and Apple rates it for up to 44 hours of video on the outer screen and 31 hours on the inner screen.", "iPhone Duo", {})
        self.assertIsNone(review.flat_facts(r, "iPhone Duo"))

    def test_dollars_normalised_without_touching_other_text(self):
        self.assertIn("$1,999", D.spoken_numbers("It starts at 1,999 dollars."))
        self.assertEqual(D.spoken_numbers("A 5.4 inch display."), "A 5.4 inch display.")

    def test_score_out_of_max_draws_a_dial(self):
        r = D.scene_for("iFixit gave it a provisional repairability score of 5 out of 10, the highest for a foldable.", "iPhone Duo", {})
        self.assertEqual(r["kind"], "gauge")
        self.assertEqual((r["max"], r["gauges"][0]["value"]), (10.0, 5.0))

    def test_event_label_comes_from_the_sentence(self):
        self.assertEqual(D.event_label("On October 26, it acknowledged an inner display issue affecting a few units.", 10, 26), "ACKNOWLEDGED INNER DISPLAY ISSUE")
        self.assertEqual(D.event_label("Nothing dated here.", 10, 26), "")

    def test_date_run_across_months_is_one_timeline(self):
        ctx = {}
        D.scene_for("It launched on October 23.", "iPhone Duo", ctx)
        r = D.scene_for("Then on November 2, Apple sent guidance.", "iPhone Duo", ctx)
        self.assertEqual(r["kind"], "timeline")


    def test_a_bare_year_is_not_a_figure_after_a_unit_sentence(self):
        r = D.scene_for("That is ridiculously low for a 2027 flagship, even for the base model.", "Galaxy S27 Ultra", {"unit": "W", "topic": "charging"})
        self.assertFalse(r and "2,027" in str(r))

if __name__ == "__main__":
    unittest.main()
