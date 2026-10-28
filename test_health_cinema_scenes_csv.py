import unittest
import tempfile
from pathlib import Path

from health_cinema import scenes_csv as C

HEAD = "text,start,end,chapter,footage,source_title,source_citation,source_url,source_year,source_population,source_context\n"
SCRIPT = ["Your heart beats about one hundred thousand times a day.", "In a large study of adults, resting heart rate was linked to longer life.",
          "Talk to your doctor before changing anything."]


def words_for(sentences, step=0.4, gap=0.3):
    out, t = [], 0.0
    for s in sentences:
        for w in s.split():
            out.append((w, t, t + step)); t += step
        t += gap
    return out


class Parse(unittest.TestCase):
    def test_timed_rows_sources_and_times(self):
        rows = C.parse_csv_text(HEAD + 'Hello there friend.,0:00,0:04.5,Intro,walking in park,Heart study,"Smith, Lancet",https://x.org/a,2021,"4,200 adults","resting rate, 10 y"\n'
                                       'Second line here.,0:04.5,9,,,,,,,,\n')
        self.assertEqual(rows[0]["start"], 0.0); self.assertEqual(rows[0]["end"], 4.5); self.assertEqual(rows[1]["end"], 9.0)
        self.assertEqual(rows[0]["chapter"], "Intro"); self.assertEqual(rows[0]["footage"], "walking in park")
        self.assertEqual(rows[0]["sources"], [{"title": "Heart study", "citation": "Smith, Lancet", "url": "https://x.org/a", "year": 2021, "population": "4,200 adults", "context": "resting rate, 10 y"}])
        self.assertNotIn("sources", rows[1]); self.assertEqual([r["scene_no"] for r in rows], [1, 2])
        self.assertFalse(C.needs_alignment(rows))

    def test_two_sources_in_one_row(self):
        rows = C.parse_csv_text("text,source_title,source_year\nA fact here.,Study one | Study two,2019 | 2022\n")
        self.assertEqual([s["title"] for s in rows[0]["sources"]], ["Study one", "Study two"]); self.assertEqual(rows[0]["sources"][1]["year"], 2022)

    def test_untimed_and_aliases_semicolon_bom(self):
        rows = C.parse_csv_text("﻿Narration;Section\nOne two three four.;Intro\n\nFive six seven eight.;\n")
        self.assertEqual(len(rows), 2); self.assertTrue(C.needs_alignment(rows)); self.assertEqual(rows[0]["chapter"], "Intro")

    def test_errors_name_the_row(self):
        bad = {"text,start,end\nA b c d.,1,\n": "row 2", "text,start,end\nA b c d.,5,3\n": "row 2", "text\n\n": "no rows", "start,end\n1,2\n": "'text' column",
               "text,start,end\nA b.,0,2\nC d.,,\n": "row 3", "text,start,end\nA b.,0,5\nC d.,2,6\n": "row 3", "text,start,end\nA b.,x,5\n": "not a time",
               "text,source_year\nA b.,21\n": "4-digit", "text,source_context\nA b.,only context\n": "no title, citation or url", "": "empty"}
        for txt, frag in bad.items():
            with self.assertRaises(ValueError, msg=txt) as cm:
                C.parse_csv_text(txt)
            self.assertIn(frag, str(cm.exception), txt)

    def test_cp1252_file(self):
        d = Path(tempfile.mkdtemp()); p = d / "s.csv"; p.write_bytes("text\nCafé olé tonight friend.\n".encode("cp1252"))
        self.assertEqual(C.read_scenes_csv(str(p))[0]["text"], "Café olé tonight friend.")


class Align(unittest.TestCase):
    def rows(self, lines=SCRIPT):
        return C.parse_csv_text("text\n" + "\n".join('"%s"' % t for t in lines) + "\n")

    def test_exact_alignment_is_contiguous_with_words(self):
        w = words_for(SCRIPT); out, frac = C.align_to_words(self.rows(), w, w[-1][2])
        self.assertEqual(frac, 1.0); self.assertEqual(out[0]["start"], 0.0)
        for a, b in zip(out, out[1:]):
            self.assertAlmostEqual(a["end"], b["start"])
        self.assertAlmostEqual(out[1]["start"], w[len(SCRIPT[0].split())][1]); self.assertEqual(" ".join(x["w"] for x in out[2]["words"]), SCRIPT[2])
        self.assertAlmostEqual(out[-1]["end"], w[-1][2])

    def test_transcript_noise_still_aligns(self):
        w = words_for(SCRIPT); w[3] = ("hurts", w[3][1], w[3][2]); w.insert(10, ("um", w[10][1], w[10][1] + 0.1))
        out, frac = C.align_to_words(self.rows(), w, 0); self.assertGreater(frac, 0.8)
        self.assertAlmostEqual(out[2]["start"], [x for x in w if x[0] == "Talk"][0][1], places=3)

    def test_unmatched_row_sits_between_neighbours(self):
        heard = [SCRIPT[0], SCRIPT[2]]; w = words_for(heard)
        out, frac = C.align_to_words(self.rows(), w, 0)
        self.assertLessEqual(out[0]["start"], out[1]["start"]); self.assertLessEqual(out[1]["start"], out[2]["start"]); self.assertGreater(out[1]["end"], out[1]["start"])

    def test_wrong_voiceover_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            C.align_to_words(self.rows(), words_for(["Completely different narration about weather and storms across the coast tonight."]), 0)
        self.assertIn("does not look like this narration", str(cm.exception))

    def test_no_words_refused_and_total_extends_last_scene(self):
        with self.assertRaises(ValueError): C.align_to_words(self.rows(), [], 0)
        w = words_for(SCRIPT); out, _ = C.align_to_words(self.rows(), w, w[-1][2] + 5); self.assertAlmostEqual(out[-1]["end"], w[-1][2] + 5)

    def test_feeds_the_planner(self):
        from health_cinema import planner
        rows = C.parse_csv_text("text,source_title,source_year\nOne in four adults has high blood pressure.,BP survey,2020\nYour heart pumps blood around the body.,\n")
        w = words_for([r["text"] for r in rows]); out, _ = C.align_to_words(rows, w, 0)
        plan = planner.plan(out)
        self.assertTrue(plan["scenes"]); self.assertEqual(plan["scenes"][0].sources[0]["title"], "BP survey")


if __name__ == "__main__":
    unittest.main()
