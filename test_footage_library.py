"""Local footage intelligence (product_trailer/footage_library.py): meaning-based matching, honest gaps, trimming that never touches the source."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from product_trailer import footage_library as FL


def shot(n, a, b, concepts, **kw):
    d = {"n": n, "start": a, "end": b, "motion": 8.0, "shows": "x", "concepts": concepts, "usage": "promo", "subject": "iphone_duo", "keep": True, "onscreen": [], "dark": False}
    d.update(kw)
    return d


def index(*shots, name="clip.mp4"):
    return {"files": [{"name": name, "folder": "f", "path": "/x/" + name, "shots": list(shots)}]}


class Matching(unittest.TestCase):
    def test_matches_by_meaning_not_file_name(self):
        idx = index(shot(0, 0, 6, ["hinge"]), name="hinge_zoom.mp4")     # the file name says hinge, the shot is described as a hinge: but only the sentence's meaning decides
        self.assertTrue(FL.match_sentence("It folds like a book.", "product", 3.0, "iPhone Duo", idx, {})["segments"] == [])
        self.assertTrue(FL.match_sentence("The hinge opens flat.", "product", 3.0, "iPhone Duo", idx, {})["segments"])

    def test_other_phone_never_stands_in(self):
        idx = index(shot(0, 0, 6, ["foldable_form"], subject="iphone_18_pro"))
        self.assertEqual(FL.match_sentence("It is a foldable.", "product", 3.0, "iPhone Duo", idx, {})["segments"], [])

    def test_evidence_lines_get_no_promotional_footage(self):
        idx = index(shot(0, 0, 6, ["foldable_form", "inner_display"]))
        r = FL.match_sentence("Some owners report cracks along the fold.", "reported_problem", 3.0, "iPhone Duo", idx, {})
        self.assertEqual(r["segments"], [])

    def test_printed_figures_only_when_narrated(self):
        idx = index(shot(0, 0, 6, ["price", "launch"], onscreen=["1999"]))
        self.assertEqual(FL.match_sentence("The launch price is steep.", "price", 3.0, "iPhone Duo", idx, {})["segments"], [])
        self.assertTrue(FL.match_sentence("The launch price is 1,999 dollars.", "price", 3.0, "iPhone Duo", idx, {})["segments"])

    def test_one_source_many_clips_and_no_moment_twice(self):
        idx = index(shot(0, 0, 12, ["foldable_form", "hinge"]), shot(1, 12, 20, ["foldable_form", "hinge"]))
        used = {}
        a = FL.match_sentence("The foldable hinge opens.", "product", 6.0, "iPhone Duo", idx, used)["segments"]
        b = FL.match_sentence("The foldable hinge closes.", "product", 3.0, "iPhone Duo", idx, used)["segments"]
        self.assertTrue(a and b)
        spans = [(s["path"], s["shot"], s["in"], s["out"]) for s in a + b]
        for i, x in enumerate(spans):
            for y in spans[i + 1:]:
                if x[:2] == y[:2]:
                    self.assertTrue(x[3] <= y[2] or y[3] <= x[2], "the same moment was used twice")

    def test_clip_never_longer_than_its_moment(self):
        idx = index(shot(0, 0, 2.0, ["foldable_form"]))
        for s in FL.match_sentence("It is a foldable.", "product", 2.0, "iPhone Duo", idx, {})["segments"]:
            self.assertLessEqual(s["out"], 2.0)


class Cards(unittest.TestCase):
    def test_long_line_splits_into_cards_each_short(self):
        t = "Others report hinges that won't open or close fully, strange noises, or loose, and damaged hinges"
        parts = FL.clauses(t, 6.0)
        self.assertGreaterEqual(len(parts), 2)
        self.assertTrue(all(len(p.split()) <= 14 for p in parts))


class Trim(unittest.TestCase):
    def test_index_and_cut_leave_the_original_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "lib" / "a.mp4"
            src.parent.mkdir()
            r = subprocess.run([FL._ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=15:duration=4", "-pix_fmt", "yuv420p", str(src)], capture_output=True)
            if r.returncode != 0:
                self.skipTest("cannot make a test clip")
            before = hashlib.md5(src.read_bytes()).hexdigest()
            idx = FL.index_folder(td / "lib", td / "cache", lambda m: None)
            self.assertEqual(len(idx["files"]), 1)
            self.assertTrue(idx["files"][0]["shots"])
            again = FL.index_folder(td / "lib", td / "cache", lambda m: None)           # second run is served from the cache
            self.assertEqual(again["files"][0]["shots"], idx["files"][0]["shots"])
            out = FL.cut_segment({"path": str(src), "in": 1.0, "out": 2.5}, td / "o" / "c.mp4", width=320, height=180)
            self.assertTrue(out.is_file() and out.stat().st_size > 0)
            self.assertEqual(hashlib.md5(src.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()


class Hybrid(unittest.TestCase):
    def test_key_fact_and_source_label_come_from_the_sentence(self):
        self.assertEqual(FL.hl_of("the damage appeared after about six hours"), "about six hours")
        self.assertEqual(FL.hl_of("and fewer than 20 openings"), "fewer than 20 openings")
        self.assertEqual(FL.kicker_of("Some owners report cracks along the fold.", {"secondary": {}}), "Owner reports")
        self.assertEqual(FL.kicker_of("Apple has now responded.", {"secondary": {}}), "Apple's response")
        self.assertEqual(FL.kicker_of("It has two batteries.", {"secondary": {}}), "")

    def test_beats_keep_every_word_and_the_narrators_timing(self):
        text = "Others report hinges that won't open or close fully, strange noises, or loose, and damaged hinges"
        W = [(w.lower().strip(",'"), 10.0 + 0.3 * j, 10.2 + 0.3 * j) for j, w in enumerate(text.split())]
        bt = FL.make_beats(text, W, (0, len(W) - 1), (10.0, 13.0), True)
        self.assertEqual(" ".join(b["text"] for b in bt).split(), text.split())
        self.assertAlmostEqual(bt[0]["times"][0], 10.0)
        self.assertTrue(all(len(b["text"].split()) >= 3 for b in bt))
        tail = FL.make_beats(text, W, (0, len(W) - 1), (10.0, 13.0), True, from_t=12.0)
        self.assertTrue(tail and tail[0]["times"][0] >= 11.95)

    def test_flex_cover_never_loops_and_leaves_a_readable_remainder(self):
        idx = index(shot(0, 0, 4.0, ["foldable_form"]), shot(1, 4, 7.0, ["foldable_form"]), shot(2, 7, 9.2, ["foldable_form"]))
        r = FL.match_sentence("A book-style foldable.", "figure", 12.0, "iPhone Duo", idx, {}, flex=True)
        segs = r["segments"]
        self.assertTrue(segs)
        self.assertLessEqual(sum(s["out"] - s["in"] for s in segs), 12.0)
        for s in segs:
            sh = next(x for x in idx["files"][0]["shots"] if x["n"] == s["shot"])
            self.assertLessEqual(s["out"], sh["end"])
        left = 12.0 - sum(s["out"] - s["in"] for s in segs)
        self.assertTrue(left == 0 or left >= 1.9 or r["covers_slot"], left)

    def test_screen_captures_only_under_figures_about_what_they_show(self):
        idx = index(shot(0, 0, 6, ["inner_display", "chip"], usage="ui"))
        self.assertEqual(FL.match_sentence("It has a 7.6 inch inner display.", "figure", 3.0, "iPhone Duo", idx, {}, flex=True)["segments"], [])
        self.assertTrue(FL.match_sentence("It runs the same A20 Pro chip.", "figure", 3.0, "iPhone Duo", idx, {}, flex=True)["segments"])

    def test_shot_about_something_specific_needs_that_concept(self):
        idx = index(shot(0, 0, 6, ["inner_display", "outer_display"]))
        self.assertEqual(FL.match_sentence("Apple rates the battery for 44 hours on the outer screen.", "figure", 3.0, "iPhone Duo", idx, {}, flex=True)["segments"], [])


class Facts(unittest.TestCase):
    def test_director_figures_become_a_footage_overlay(self):
        from product_trailer import review
        f = review.flat_facts({"kind": "sides", "items": [{"value": '5.4"', "sub": "Outer Display", "side": "left", "at": 0.0}, {"value": '7.6"', "sub": "Inner Display", "side": "right", "at": 5.0}]}, "iPhone Duo")
        self.assertEqual([x["value"] for x in f["items"]], ['5.4"', '7.6"'])
        lay = review.over_layers({"kind": "sides", "items": [{"value": "1", "sub": "a"}]}, "iPhone Duo", 10.0, 14.0)
        self.assertEqual(lay[0]["type"], "pt_fact")
        self.assertEqual((lay[0]["start"], lay[0]["end"]), (10.1, 13.95))
