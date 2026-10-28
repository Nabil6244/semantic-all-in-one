"""Voice-over for reviews (product_trailer/voiceover.py, review.plan_review_timed, render mix): alignment, subtitle times, timed film, mix. Real ffmpeg for the mix only."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from product_trailer import review, studio, voiceover as V

ROOT = Path(__file__).resolve().parent
FFMPEG = ROOT / "bin" / "ffmpeg"
SCRIPT = "# R\n## Design\nThe frame is flat and the back is matte.\n[stat: 30W | Fast charging]\nYou hold it in one hand all day.\n## Hinge\n[curve: Crease | x | y | 0:0, 0.5:0.8, 1:0.9]\nWe folded it three thousand times.\n"
LINES = ["The frame is flat and the back is matte.", "You hold it in one hand all day.", "We folded it three thousand times."]


def words_for(lines, wps=3.0, gap=0.6, t0=0.5):
    out, t = [], t0
    for line in lines:
        for w in line.split():
            out.append((w.strip(".,"), round(t, 3), round(t + 1 / wps - 0.05, 3)))
            t += 1 / wps
        t += gap
    return out


class Align(unittest.TestCase):
    def test_lines_follow_the_narrators_words_in_order(self):
        W = words_for(LINES)
        r = V.align_lines(LINES, W, W[-1][2] + 1)
        self.assertTrue(r["ok"])
        starts = [a for a, _ in r["spans"]]
        self.assertEqual(starts, sorted(starts))
        self.assertAlmostEqual(r["spans"][0][0], W[0][1], places=2)
        self.assertAlmostEqual(r["spans"][2][1], W[-1][2], places=2)

    def test_a_voice_over_that_does_not_follow_the_script_is_spread_evenly_and_marked(self):
        W = [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate("totally different words said here about something else entirely".split())]
        r = V.align_lines(LINES, W, 30.0)
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["spans"]), 3)
        self.assertLess(r["spans"][0][1], r["spans"][1][1])
        self.assertAlmostEqual(r["spans"][-1][1], 30.0, places=1)

    def test_subtitle_chunks_are_the_scripts_words_timed_from_the_narrator(self):
        W = words_for(LINES)
        r = V.align_lines(LINES, W, 20.0)
        ch = V.chunks(LINES[0], r["spans"][0], W, r["ranges"][0], r["ok"])
        self.assertEqual(" ".join(c["text"] for c in ch), LINES[0])
        self.assertGreaterEqual(ch[0]["start"], W[0][1] - 0.01)
        for c in ch:
            self.assertLess(c["start"], c["end"])
            self.assertLessEqual(len(c["text"].split()), 9)


class Timed(unittest.TestCase):
    def setUp(self):
        self.parsed = review.parse_script(SCRIPT)
        self.pack = review.plan_review_scenes(self.parsed, "galaxy s27 ultra", ["Black", "Sky Blue", "Pink", "White"])
        self.W = words_for(LINES)
        self.D = self.W[-1][2] + 1.0
        self.voice = V.align_lines(LINES, self.W, self.D)

    def test_the_film_is_as_long_as_the_voice_over_and_cuts_at_the_spoken_lines(self):
        spec = review.plan_review_timed(self.parsed, self.pack, {}, self.voice, self.W, product={"disclaimer": "Concept."})
        body = [s for s in spec["shots"] if s["kind"] != "black"]
        self.assertAlmostEqual(body[-1]["end"], self.D, places=2)
        self.assertEqual(body[0]["start"], 0.0)
        for a, b in zip(spec["shots"], spec["shots"][1:]):
            self.assertAlmostEqual(a["end"], b["start"], places=2)
        starts = {round(s["start"], 1) for s in body}
        for i in (1, 2):
            self.assertIn(round(self.voice["spans"][i][0], 1), starts, "a cut at the start of each spoken line")
        self.assertEqual(spec["shots"][-1]["kind"], "black")
        self.assertTrue(spec["product_trailer"]["voiceover_timed"])

    def test_a_chart_before_a_line_is_shown_while_that_line_is_spoken_and_chapters_get_a_card(self):
        spec = review.plan_review_timed(self.parsed, self.pack, {}, self.voice, self.W)
        types = [L["type"] for L in spec["layers"]]
        self.assertEqual(types.count("tm_title"), 2)
        self.assertEqual(types.count("tm_metric"), 1)
        self.assertEqual(types.count("pt_curve"), 1)
        stat = next(L for L in spec["layers"] if L["type"] == "tm_metric")
        s2 = self.voice["spans"][1]
        self.assertTrue(s2[0] - 0.01 <= stat["start"] <= s2[1], "the stat sits on the line spoken after it")

    def test_subtitles_cover_every_word_of_the_script(self):
        spec = review.plan_review_timed(self.parsed, self.pack, {}, self.voice, self.W)
        sub = next(L for L in spec["layers"] if L["type"] == "pt_subtitle")
        self.assertEqual(sum(len(c["text"].split()) for c in sub["chunks"]), sum(len(t.split()) for t in LINES))

    def test_plan_film_uses_the_voice_over_and_records_it(self):
        with tempfile.TemporaryDirectory() as d:
            vo = Path(d) / "vo.wav"
            vo.write_bytes(b"x")
            r = studio.plan_film("Review", out_dir=d, script=SCRIPT, phone="galaxy s27 ultra", voiceover=str(vo), words=self.W, voice_seconds=self.D)
            import json

            spec = json.loads(Path(r["spec_path"]).read_text(encoding="utf-8"))
            self.assertEqual(spec["product_trailer"]["voiceover"], str(vo))
            self.assertTrue(spec["product_trailer"]["voiceover_timed"])
            # the default Mixed style draws its scenes on paper over a black shot, so the film is checked by its last shot before the disclaimer card
            self.assertAlmostEqual(max(s["end"] for s in spec["shots"] if s["end"] <= self.D + 0.01), self.D, places=2)


@unittest.skipUnless(FFMPEG.is_file(), "bundled ffmpeg not found")
class Mix(unittest.TestCase):
    def tone(self, path, hz, secs):
        subprocess.run([str(FFMPEG), "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={secs}", str(path)], check=True)

    def test_voice_over_is_mixed_with_the_music_far_below_and_cut_to_the_film_length(self):
        with tempfile.TemporaryDirectory() as d:
            vo, mu, out = Path(d) / "vo.wav", Path(d) / "mu.wav", Path(d) / "mix.wav"
            self.tone(vo, 440, 4)
            self.tone(mu, 880, 2)
            V.mix_voiceover(vo, mu, out, 3.0, str(FFMPEG))
            self.assertAlmostEqual(V.audio_seconds(out, str(FFMPEG).replace("ffmpeg", "ffprobe")), 3.0, delta=0.2)
            only = Path(d) / "only.wav"
            V.mix_voiceover(vo, None, only, 2.0, str(FFMPEG))
            self.assertAlmostEqual(V.audio_seconds(only, str(FFMPEG).replace("ffmpeg", "ffprobe")), 2.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
