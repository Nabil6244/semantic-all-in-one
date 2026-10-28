"""Mixed and review modes (product_trailer/mixed.py, review.py): spec shape, fallbacks, chapters, charts, subtitles. No browser, no Flow."""
import tempfile
import unittest
from pathlib import Path

from product_trailer import mixed, review, scenepack as S

FEATS = [{"feature": f, "value": f.title()} for f in ["design", "display", "camera", "chip", "battery", "durability"]]
DATA = {"product": {"name": "Galaxy S27 Ultra", "phone": "galaxy s27 ultra", "disclaimer": "Concept film. Not affiliated."}, "features": FEATS}
COLS = ["Black", "Sky Blue", "Pink", "White"]


def png(d, name):
    p = Path(d) / name
    p.write_bytes(b"\x89PNG" + b"0" * 20)
    return str(p)


class Mixed(unittest.TestCase):
    def setUp(self):
        self.pack = S.plan_scene_pack(FEATS, "galaxy s27 ultra", COLS, max_clips=1)

    def test_no_pictures_means_a_full_3d_film_with_notes(self):
        spec = mixed.plan_mixed(DATA, self.pack, {})
        kinds = {s["kind"] for s in spec["shots"]}
        self.assertEqual(kinds, {"product", "black"})
        self.assertTrue(spec["whatif"]["notes"])
        self.assertEqual(spec["duration"], spec["shots"][-1]["end"])

    def test_pictures_become_image_shots_with_a_slow_push_and_the_chip_stays_3d(self):
        with tempfile.TemporaryDirectory() as d:
            res = {s["n"]: {"status": "done", "path": png(d, f"p{s['n']}.png")} for s in self.pack["scenes"] if s["source"] != "3d"}
            spec = mixed.plan_mixed(DATA, self.pack, res, media_dir=Path(d) / "media")
            imgs = [s for s in spec["shots"] if s["kind"] == "image"]
            self.assertGreaterEqual(len(imgs), 3)
            for s in imgs:
                self.assertTrue((Path(d) / "media" / s["file"]).is_file())
                self.assertNotEqual(s["drift"]["from"], s["drift"]["to"])
            self.assertTrue(any(s.get("object") == "chip" for s in spec["shots"]))
            self.assertEqual(spec["media_dir"], str(Path(d) / "media"))

    def test_a_failed_scene_falls_back_to_a_lineup(self):
        res = {s["n"]: {"status": "failed", "error": "x"} for s in self.pack["scenes"] if s["source"] != "3d"}
        spec = mixed.plan_mixed(DATA, self.pack, res)
        self.assertFalse([s for s in spec["shots"] if s["kind"] == "image"])
        self.assertTrue([s for s in spec["shots"] if s.get("object") == "lineup"])

    def test_shots_are_contiguous_one_caption_each_and_the_card_is_last(self):
        spec = mixed.plan_mixed(DATA, self.pack, {})
        for a, b in zip(spec["shots"], spec["shots"][1:]):
            self.assertEqual(a["end"], b["start"])
        self.assertEqual(spec["shots"][-1]["kind"], "black")
        self.assertEqual(sum(1 for L in spec["layers"] if L["type"] == "pt_caption"), 1 + len(self.pack["scenes"]))
        self.assertEqual(spec["layers"][-1]["type"], "pt_card")

    def test_an_ai_clip_uses_the_clip_file_when_there_is_one(self):
        clip_scene = next(s for s in self.pack["scenes"] if s["source"] == "ai_clip")
        with tempfile.TemporaryDirectory() as d:
            res = {clip_scene["n"]: {"status": "done", "path": png(d, "a.png")}, "clips": {clip_scene["n"]: png(d, "c.mp4")}}
            spec = mixed.plan_mixed(DATA, self.pack, res, media_dir=Path(d) / "m")
            self.assertEqual(sum(1 for s in spec["shots"] if s["kind"] == "video"), 1)


SCRIPT = """# Duo review
## Design
The frame is flat and the back is matte. You hold it in one hand all day.
[stat: 1h40min | Full charge, as tested]
## Durability
We ran the hinge test three thousand times. The crease got deeper then settled.
[bars: Crease depth | After 100 folds=1.0 | After 3000 folds=3.2]
The chip scored well in every benchmark we ran.
"""


class Review(unittest.TestCase):
    def setUp(self):
        self.parsed = review.parse_script(SCRIPT)
        self.pack = review.plan_review_scenes(self.parsed, "galaxy s27 ultra", COLS)

    def test_parse_chapters_lines_bars_and_stats(self):
        self.assertEqual(self.parsed["title"], "Duo review")
        self.assertEqual([c["title"] for c in self.parsed["chapters"]], ["Design", "Durability"])
        kinds = [[i["kind"] for i in c["items"]] for c in self.parsed["chapters"]]
        self.assertEqual(kinds[0], ["line", "line", "stat"])
        self.assertEqual(kinds[1], ["line", "line", "bars", "line"])
        bars = self.parsed["chapters"][1]["items"][2]
        self.assertEqual([r["value"] for r in bars["rows"]], [1.0, 3.2])
        self.assertTrue(bars["rows"][0]["highlight"])

    def test_scene_types_follow_the_words_and_the_chip_stays_3d(self):
        free = review.plan_review_scenes(self.parsed, "galaxy s27 ultra", COLS, max_ai_share=1.0)
        by = {s["text"]: s for s in free["scenes"]}
        self.assertEqual(by["We ran the hinge test three thousand times."]["type"], "lab_rig")
        capped = review.plan_review_scenes(self.parsed, "galaxy s27 ultra", COLS, max_ai_share=0.0)
        self.assertLessEqual(sum(1 for s in capped["scenes"] if s["source"] == "ai_still"), 1, "the AI share cap keeps most lines 3D")
        by = {s["text"]: s for s in self.pack["scenes"]}
        self.assertEqual(by["The chip scored well in every benchmark we ran."]["source"], "3d")
        for s in self.pack["scenes"]:
            if s["source"] == "ai_still":
                self.assertIn("no text and no logo", s["prompt"])
        types = [s["type"] for s in self.pack["scenes"] if s["source"] == "ai_still"]
        for a, b in zip(types, types[1:]):
            self.assertNotEqual(a, b)

    def test_the_pack_works_with_the_scene_pack_runner_shape(self):
        for s in self.pack["scenes"]:
            if s["source"] == "ai_still":
                self.assertTrue(1 <= len(s["refs"]) <= S.FLOW_REF_LIMIT and s["key"])

    def test_spec_has_chapter_cards_a_chart_a_stat_and_subtitles_covering_every_line(self):
        spec = review.plan_review(self.parsed, self.pack, {}, product={"disclaimer": "Concept."})
        types = [L["type"] for L in spec["layers"]]
        self.assertEqual(types.count("tm_title"), 2)
        self.assertEqual(types.count("pt_bench"), 1)
        self.assertEqual(types.count("tm_metric"), 1)
        sub = next(L for L in spec["layers"] if L["type"] == "pt_subtitle")
        words = sum(len(c["text"].split()) for c in sub["chunks"])
        lines = [i["text"] for c in self.parsed["chapters"] for i in c["items"] if i["kind"] == "line"]
        self.assertEqual(words, sum(len(t.split()) for t in lines))
        for c in sub["chunks"]:
            self.assertLessEqual(len(c["text"].split()), 9)
            self.assertLess(c["start"], c["end"])
        self.assertEqual(spec["shots"][-1]["kind"], "black")
        for a, b in zip(spec["shots"], spec["shots"][1:]):
            self.assertEqual(a["end"], b["start"])

    def test_a_missing_picture_becomes_a_3d_shot_and_a_present_one_an_image(self):
        with tempfile.TemporaryDirectory() as d:
            ai = next(s for s in self.pack["scenes"] if s["source"] == "ai_still")
            spec = review.plan_review(self.parsed, self.pack, {ai["n"]: {"status": "done", "path": png(d, "a.png")}}, media_dir=Path(d) / "m")
            self.assertEqual(sum(1 for s in spec["shots"] if s["kind"] == "image"), 1)
            self.assertTrue(spec["whatif"]["notes"])

    def test_line_length_follows_the_words(self):
        self.assertLess(review.line_seconds("one two three"), review.line_seconds("one two three four five six seven eight nine ten"))



DIRECTIVES = """## Hinge
We folded it three thousand times.
[curve: Crease depth | Time spent folded | Depth | 0:0, 0.1:0.55, 0.3:0.85, 1:0.95 | 0.3=Rapid deepening]
[compare: Peak brightness | nit | Foldable=300 | Max=300 | Pro=280]
[xray: Inside the hinge]
[fold: The fold, slowed]
"""


class Graphics(unittest.TestCase):
    def test_curve_compare_xray_and_fold_directives_become_the_right_shots_and_layers(self):
        parsed = review.parse_script(DIRECTIVES)
        kinds = [i["kind"] for i in parsed["chapters"][0]["items"]]
        self.assertEqual(kinds, ["line", "curve", "compare", "xray", "fold"])
        cur = parsed["chapters"][0]["items"][1]
        self.assertEqual(cur["points"][1], [0.1, 0.55])
        self.assertEqual(cur["marks"], [{"x": 0.3, "text": "Rapid deepening"}])
        cmp_ = parsed["chapters"][0]["items"][2]
        self.assertTrue(cmp_["cols"][0]["highlight"])
        pack = review.plan_review_scenes(parsed, "x", COLS)
        spec = review.plan_review(parsed, pack, {})
        types = [L["type"] for L in spec["layers"]]
        for t in ("pt_curve", "pt_compare3"):
            self.assertIn(t, types)
        objs = [s.get("object") for s in spec["shots"] if s["kind"] == "product"]
        self.assertIn("xray", objs)
        self.assertIn("fold", objs)
        for a, b in zip(spec["shots"], spec["shots"][1:]):
            self.assertEqual(a["end"], b["start"])

    def test_a_bad_curve_or_compare_is_skipped_not_fatal(self):
        parsed = review.parse_script("## A\n[curve: t | x | y | nonsense]\n[compare: t | u | only=1]\nA line.")
        self.assertEqual([i["kind"] for i in parsed["chapters"][0]["items"]], ["line"])



EVERYTHING = """# Duo review
[intro: The Galaxy S27 Ultra review]
## Design
We start with how it looks and feels in the hand.
[lineup: All four colours | gallery | fan]
[macro: The camera module | island]
[bigtype: 6.9 INCH]
## Performance
[chip: Exynos 2700 | Reported speed]
It scored well in every benchmark we ran.
[bars: Geekbench | Exynos=13000 | Snapdragon=11000]
## Hinge
[curve: Crease | x | y | 0:0, 0.5:0.8, 1:0.9]
[xray: Inside the hinge]
[fold: The fold, slowed]
[compare: Peak brightness | nit | A=300 | B=300 | C=280]
[stat: 3000 | Folds tested]
We folded it three thousand times.
[outro: Galaxy S27 Ultra]
"""


class Everything(unittest.TestCase):
    def setUp(self):
        self.parsed = review.parse_script(EVERYTHING)
        self.pack = review.plan_review_scenes(self.parsed, "galaxy s27 ultra", COLS)

    def test_every_directive_kind_parses(self):
        kinds = {i["kind"] for c in self.parsed["chapters"] for i in c["items"]}
        self.assertEqual(kinds, {"intro", "line", "lineup", "macro", "bigtype", "chip", "bars", "curve", "xray", "fold", "compare", "stat", "outro"})
        lu = next(i for c in self.parsed["chapters"] for i in c["items"] if i["kind"] == "lineup")
        self.assertEqual((lu["room"], lu["pose"]), ("gallery", "fan"))

    def test_untimed_review_has_a_shot_and_the_right_layer_for_each(self):
        spec = review.plan_review(self.parsed, self.pack, {}, product={"name": "Galaxy S27 Ultra", "disclaimer": "Concept."})
        objs = {s.get("object") for s in spec["shots"] if s["kind"] == "product"}
        self.assertTrue({"lineup", "chip", "xray", "fold", "phone"} <= objs)
        types = {L["type"] for L in spec["layers"]}
        self.assertTrue({"pt_bench", "pt_curve", "pt_compare3", "tm_metric", "pt_bigtype", "pt_reveal", "pt_caption", "pt_subtitle", "pt_card", "tm_title"} <= types)
        for a, b in zip(spec["shots"], spec["shots"][1:]):
            self.assertEqual(a["end"], b["start"])

    def test_timed_review_keeps_every_directive_and_is_as_long_as_the_voice(self):
        from product_trailer import voiceover as V

        lines = [i["text"] for c in self.parsed["chapters"] for i in c["items"] if i["kind"] == "line"]
        W, t = [], 0.5
        for ln in lines:
            for w in ln.split():
                W.append((w.strip(".,"), round(t, 3), round(t + 0.3, 3)))
                t += 0.33
            t += 0.5
        voice = V.align_lines(lines, W, t + 1)
        spec = review.plan_review_timed(self.parsed, self.pack, {}, voice, W, product={"name": "Galaxy S27 Ultra"})
        types = [L["type"] for L in spec["layers"]]
        for need in ("pt_bench", "pt_curve", "pt_compare3", "tm_metric", "pt_bigtype", "pt_reveal"):
            self.assertIn(need, types)
        body = [s for s in spec["shots"] if s["kind"] != "black"]
        self.assertAlmostEqual(body[-1]["end"], t + 1, places=2)
        for a, b in zip(spec["shots"], spec["shots"][1:]):
            self.assertAlmostEqual(a["end"], b["start"], places=2)

    def test_an_ai_clip_plays_instead_of_the_still(self):
        pack = review.plan_review_scenes(review.parse_script("## A\nYou hold it in one hand."), "x", COLS, max_ai_share=1.0)
        ai = next(s for s in pack["scenes"] if s["source"] == "ai_still")
        with tempfile.TemporaryDirectory() as d:
            res = {ai["n"]: {"status": "done", "path": png(d, "a.png")}, "clips": {ai["n"]: png(d, "c.mp4")}}
            spec = review.plan_review(review.parse_script("## A\nYou hold it in one hand."), pack, res, media_dir=Path(d) / "m")
            self.assertEqual(sum(1 for s in spec["shots"] if s["kind"] == "video"), 1)



class PlainAndCsv(unittest.TestCase):
    PLAIN = "The frame is flat and the back is matte. You hold it in one hand all day.\n\nWe folded it three thousand times. The crease got deeper then settled."

    def test_plain_text_needs_no_markup_one_shot_per_sentence_and_no_chapter_cards(self):
        parsed = review.parse_script(self.PLAIN)
        self.assertEqual(len(parsed["chapters"]), 1)
        self.assertEqual([i["kind"] for i in parsed["chapters"][0]["items"]], ["line"] * 4)
        pack = review.plan_review_scenes(parsed, "x", COLS)
        spec = review.plan_review(parsed, pack, {})
        self.assertEqual([L["type"] for L in spec["layers"]].count("tm_title"), 0)
        self.assertEqual(sum(1 for s in spec["shots"] if s["kind"] == "product"), 4)

    def test_a_csv_becomes_the_same_script_with_chapters_and_visuals(self):
        csv = "chapter,text,visual\nDesign,The frame is flat.,\nDesign,You hold it all day.,lineup: Four colours | gallery | fan\nHinge,We folded it a lot.,xray: Inside the hinge\n"
        script = review.csv_to_script(csv)
        self.assertEqual(script.splitlines(), ["## Design", "The frame is flat.", "[lineup: Four colours | gallery | fan]", "You hold it all day.", "## Hinge", "[xray: Inside the hinge]", "We folded it a lot."])
        kinds = [[i["kind"] for i in c["items"]] for c in review.parse_script(script)["chapters"]]
        self.assertEqual(kinds, [["line", "lineup", "line"], ["xray", "line"]])

    def test_the_apps_scene_csv_and_a_header_less_csv_both_work(self):
        self.assertEqual(review.csv_to_script("scene_number,script_segment,asset_type,prompt\n1,Hello there.,image,x\n2,Second line.,video,y\n").splitlines(), ["Hello there.", "Second line."])
        self.assertEqual(review.csv_to_script("Just a line.\nAnother line.\n").splitlines(), ["Just a line.", "Another line."])
        self.assertEqual(review.csv_to_script(""), "")

    def test_review_source_prefers_the_pasted_text_then_the_csv(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "r.csv"
            f.write_text("text\nFrom the file.\n", encoding="utf-8")
            self.assertEqual(review.review_source("Pasted.", str(f)), "Pasted.")
            self.assertEqual(review.review_source("  ", str(f)).strip(), "From the file.")
            self.assertEqual(review.review_source("", None), "")

    def test_plan_film_review_from_a_csv_alone(self):
        from product_trailer import studio

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "r.csv"
            f.write_text("text,visual\nThe frame is flat.,\nWe folded it.,fold: The fold\n", encoding="utf-8")
            r = studio.plan_film("Review", out_dir=Path(d) / "o", csv=str(f), phone="galaxy s27 ultra")
            self.assertIn("Review", r["summary"])
            with self.assertRaises(ValueError):
                studio.plan_film("Review", out_dir=Path(d) / "o2", csv=None, script="")


if __name__ == "__main__":
    unittest.main()
