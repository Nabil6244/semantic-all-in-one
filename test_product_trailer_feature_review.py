"""A Review film with a Trailer feature CSV and a voice-over: the CSV is facts (never narration), the voice is the script, each CSV row is shown on the
sentence that says it, no AI call is made, nothing on screen is a fact the narration or CSV did not give, and no flat card stays frozen. Synthetic data only."""
import tempfile
import unittest
from pathlib import Path

from product_trailer import director, llm_director, review, studio, voiceover as V

FEATURE_CSV = """#product,Galaxy S27 Ultra,Titanium Black,Galaxy S27 Ultra,09:41,Tue 03 Nov
#disclaimer,Concept trailer. Not affiliated with Samsung. Logos belong to their owners.
order,feature,kicker,value,sub,look
1,design,,Wider. Bolder,,horizon
2,camera,The next-gen,200MP,main sensor,
3,battery,Longer than ever,5700 mAh,big battery,
4,charging,Fast and steady,60W,wired charging,
5,display,Built-in,Privacy,brighter display,wash:purple
6,chip,Snapdragon,Ultra,top performance,badge
"""
SPOKEN = ["the new ultra may have lost a camera this year",
          "the leak points to a 200 megapixel main camera on the back",
          "samsung would likely advertise that as around 5 700 for the battery",
          "wired charging is listed at 60 watts in the filing",
          "a new leak says the ultra gets an improved privacy display",
          "us buyers will most likely keep getting a snapdragon chip",
          "the s26 ultra dropped to 919 99 at amazon on prime day",
          "tell me in the comments what you think of all this"]


def words_for(lines, wps=3.0, gap=0.7, t0=0.3):
    out, t = [], t0
    for line in lines:
        for w in line.split():
            out.append((w, round(t, 3), round(t + 1 / wps - 0.05, 3)))
            t += 1 / wps
        t += gap
    return out


class FeatureCsv(unittest.TestCase):
    def test_a_feature_csv_is_never_read_as_narration(self):
        self.assertTrue(review.is_feature_csv(FEATURE_CSV))
        self.assertFalse(review.is_feature_csv("text,visual\nThe frame is flat.,\n"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.csv"
            p.write_text(FEATURE_CSV, encoding="utf-8")
            self.assertEqual(review.review_source("", str(p)), "")
            n = Path(d) / "n.csv"
            n.write_text("text\nThe frame is flat.\n", encoding="utf-8")
            self.assertIn("The frame is flat.", review.review_source("", str(n)))

    def test_the_voice_splits_into_sentences_on_its_pauses(self):
        got = V.sentences(words_for(SPOKEN))
        self.assertEqual(got, SPOKEN)

    def test_a_typed_script_finds_its_place_in_the_voice(self):
        typed = ["Samsung’s next Ultra may have lost a camera.", "China’s 3C listing shows 5,534 milliamp hours.", "It dropped to $919.99 at Amazon."]
        spoken = ["samsung next ultra may have lost a camera", "china 3c listing shows 5 534 milliamp hours", "it dropped to 919 99 at amazon"]
        W = words_for(spoken)
        r = V.align_lines(typed, W, W[-1][2] + 1)
        self.assertTrue(r["ok"])
        starts = [a for a, _ in r["spans"]]
        self.assertEqual(starts, [W[0][1], W[8][1], W[16][1]])

    def test_each_row_lands_on_the_sentence_that_says_it(self):
        parsed = review.parse_script("\n".join(SPOKEN))
        from product_trailer.csv_io import parse_csv_text

        out = review.place_features(parsed, parse_csv_text(FEATURE_CSV)["features"])
        items = [it for ch in out["chapters"] for it in ch["items"]]
        before = {items[i + 1]["text"]: it["value"] for i, it in enumerate(items) if it["kind"] == "feature"}
        self.assertEqual(before[SPOKEN[1]], "200MP")
        self.assertEqual(before[SPOKEN[2]], "5700 mAh")
        self.assertEqual(before[SPOKEN[3]], "60W")
        self.assertEqual(before[SPOKEN[4]], "Privacy")
        self.assertEqual(before[SPOKEN[5]], "Ultra")
        self.assertIn("Wider. Bolder", before.values())          # a row nobody says still appears, on a sentence with no scene of its own
        self.assertNotIn("1", [it.get("text") for it in items])

    def test_two_digit_figures_need_their_unit(self):
        self.assertFalse(review.feature_matches({"value": "50MP 5x"}, "a 50 megapixel ultra wide"))
        self.assertTrue(review.feature_matches({"value": "50MP 5x"}, "and a 50 megapixel 5x telephoto"))
        self.assertTrue(review.feature_matches({"value": "5700 mAh"}, "Samsung would likely advertise that as around 5,700."))


class Film(unittest.TestCase):
    def test_review_from_feature_csv_and_voice(self):
        W = words_for(SPOKEN)
        with tempfile.TemporaryDirectory() as d:
            csv = Path(d) / "f.csv"
            csv.write_text(FEATURE_CSV, encoding="utf-8")
            vo = Path(d) / "vo.mp3"
            vo.write_bytes(b"\0")
            calls = []
            r = studio.plan_film("Review", out_dir=Path(d) / "out", csv=str(csv), script="", colour="Titanium Black", disclaimer="", voiceover=str(vo), words=W,
                                 voice_seconds=W[-1][2] + 1, style="mixed", llm_run=lambda s, u: calls.append(1) or "{}", log=lambda m: None)
            import json

            spec = json.loads(Path(r["spec_path"]).read_text())
        self.assertEqual(calls, [])                                           # a CSV run makes no AI call
        self.assertTrue(spec["product_trailer"]["voice_matched"])
        subs = " ".join(c["text"] for L in spec["layers"] if L["type"] == "pt_subtitle" for c in L["chunks"])
        self.assertIn("200 megapixel", subs)
        self.assertNotIn("#product", subs)
        shown = {str(L.get("value") or L.get("title") or L.get("text")) for L in spec["layers"] if L["type"] in ("pt_feature", "pt_badge", "pt_bigtype", "pt_tagline")}
        self.assertTrue({"200MP", "5700 mAh", "60W"} <= shown)
        phones = [s for s in spec["shots"] if s.get("object") == "phone"]
        self.assertTrue(phones and all(s["phone"] == "Galaxy S27 Ultra" and s.get("color") == "Black" for s in phones))
        self.assertTrue(any("Not affiliated with Samsung" in " ".join(L["lines"]) for L in spec["layers"] if L["type"] == "pt_card"))

    def test_no_flat_card_stays_on_screen_longer_than_the_cap(self):
        long_line = "keep in mind a certification proves a battery exists " * 6
        W = words_for([long_line.strip(), "and that is the end of it for now"])
        parsed = director.auto_direct(review.parse_script(long_line.strip() + "\nand that is the end of it for now"))
        pack = review.plan_review_scenes(parsed, "phone", ["Black"])
        voice = V.align_lines([long_line.strip(), "and that is the end of it for now"], W, W[-1][2] + 1)
        spec = review.plan_review_timed(parsed, pack, {}, voice, W, style="follow")
        flat = [s["end"] - s["start"] for s in spec["shots"] if s["kind"] == "black" and s["end"] < spec["duration"] - 4.5]
        self.assertTrue(flat)
        self.assertTrue(all(x <= review.MAX_CARD_S + 0.01 for x in flat))
        self.assertTrue(any(s["kind"] == "product" for s in spec["shots"]))


class Rules(unittest.TestCase):
    def test_whisper_numbers_are_joined(self):
        self.assertEqual(director.spoken_numbers("a capacity of 5 534 mah"), "a capacity of 5,534 mah")
        self.assertEqual(director.spoken_numbers("dropped to 919 99 at amazon, a 1 299 99 list price"), "dropped to $919.99 at amazon, a $1,299.99 list price")
        self.assertEqual(director.spoken_numbers("the 50 megapixel 5x"), "the 50 megapixel 5x")

    def test_figures_win_over_listing_and_rumor_words(self):
        self.assertEqual(director.scene_for("wired charging is listed at 60 watts")["layer"]["phones"][0]["side"]["text"], "60W")
        cams = director.scene_for("this one is a rumor the leak points to a 200 megapixel main camera and a 50 megapixel ultra wide")
        self.assertEqual(cams["layer"]["title"], "Cameras")
        self.assertEqual(director.scene_for("china 3c listing shows 5 534 mah")["layer"]["chip"], "3C CERTIFICATION")
        self.assertEqual(director.scene_for("tipster ice universe says there is no exynos")["kind"], "tweet")

    def test_short_labels_and_zoom_figures_make_no_card(self):
        self.assertNotEqual((director.scene_for("This one is a rumor.") or {}).get("kind"), "tweet")
        got = director.scene_for("Which matters more to you: the bigger battery, or keeping the 3x camera?")
        self.assertNotEqual(((got or {}).get("layer") or {}).get("title"), "Before and now")

    def test_two_rows_said_in_one_sentence_both_show(self):
        lines = ["The leak points to a 200 megapixel main camera and a 50 megapixel 5x telephoto.", "That means the 3x telephoto would be dropped.", "Tell me below."]
        out = review.place_features(review.parse_script("\n".join(lines)), [{"value": "200MP"}, {"value": "50MP 5x"}])
        items = [it for ch in out["chapters"] for it in ch["items"]]
        self.assertEqual([it.get("value") for it in items[:4]], ["200MP", None, "50MP 5x", None])

    def test_prices_and_dimensions(self):
        p = director.scene_for("the s26 ultra dropped to 919 99 at amazon compared to a 1 299 99 list price")["layer"]
        self.assertEqual([x["text"] for x in p["phones"]], ["$919.99", "$1,299.99"])
        self.assertEqual(p["phones"][0]["label"], "Galaxy S26 Ultra")
        self.assertEqual(director.scene_for("163 76x78 25x7 97mm compared to 163 6x78 1x7 9mm")["text"], "Dimensions")


class FactGate(unittest.TestCase):
    def test_the_ai_never_shows_a_fact_the_sentence_did_not_give(self):
        line = "us buyers will keep getting a snapdragon chip"
        self.assertEqual(llm_director.to_item({"type": "chip", "label": "Snapdragon 8 Gen 3", "text": "Next-Gen Processor"}, line)["label"], "CHIP")
        self.assertEqual(llm_director.to_item({"type": "chip", "label": "Snapdragon"}, line)["label"], "SNAPDRAGON")
        self.assertIsNone(llm_director.to_item({"type": "bench", "items": [{"label": "A", "value": 7200}, {"label": "B", "value": 6500}]}, line))
        self.assertIsNone(llm_director.to_item({"type": "phones", "phones": [{"label": "A", "text": "120Hz"}]}, line))
        self.assertIsNone(llm_director.to_item({"type": "fold", "text": "Flex Hinge"}, line))
        self.assertEqual(llm_director.to_item({"type": "xray", "text": "Cooling Vapor Chamber"}, "it comes from certification databases")["text"], "")
        self.assertIsNotNone(llm_director.to_item({"type": "phones", "phones": [{"label": "A", "text": "5,700mAh"}]}, "around 5 700 mah"))


if __name__ == "__main__":
    unittest.main()
