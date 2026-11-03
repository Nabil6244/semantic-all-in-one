"""Explainer rules from the Stibnite render review (docs/explainer/STIBNITE_RENDER_FIX_PLAN.md): synthetic narration, never that video's own data."""

import unittest

from explainer import scene_csv


def _words(text: str, start: float = 0.0, step: float = 0.4):
    return [(w, round(start + i * step, 3), round(start + i * step + step * 0.9, 3)) for i, w in enumerate(text.split())]


def _filler(n: int):
    return " ".join(["and", "the", "valley", "kept", "growing", "slowly"] * (n // 6 + 1)).split()[:n]


class SceneAnchorsTest(unittest.TestCase):
    """Scene rows have no narration text between them: an anchor minutes after the previous one is still found where it is spoken."""

    def setUp(self):
        parts = ["every time a soldier fires"] + [" ".join(_filler(300))] + ["by the 1930s a town grew"] + [" ".join(_filler(300))] \
            + ["6 500 feet up the pit flooded"] + [" ".join(_filler(300))] + ["during its first six years the mill ran"] + [" ".join(_filler(60))]
        self.words = _words(" ".join(parts))
        self.duration = self.words[-1][2]
        self.at = {w: t for w, t, _ in self.words}

    def _csv(self, anchors):
        rows = ["row,scene,vo_anchor,place"] + [f"scene,{i + 1},{a},place {i + 1}" for i, a in enumerate(anchors)]
        return "\n".join(rows) + "\n"

    def test_far_anchors_land_where_spoken(self):
        got = scene_csv.read(self._csv(["Every time a soldier", "By the 1930s", "Sixty-five hundred feet up", "During its first six years"]), self.words, self.duration)
        starts = [n["start"] for n in got["scene_notes"]]
        idx = [i for i, w in enumerate(self.words) if w[0] == "by"][0]
        self.assertAlmostEqual(starts[1], self.words[idx][1], delta=0.5)
        six = [i for i, w in enumerate(self.words) if w[0] == "6"][0]
        self.assertAlmostEqual(starts[2], self.words[six][1], delta=0.5)        # "Sixty-five hundred" = the transcript's "6 500"
        dur = [i for i, w in enumerate(self.words) if w[0] == "during"][0]
        self.assertAlmostEqual(starts[3], self.words[dur][1], delta=0.5)
        self.assertLess(got["scene_notes"][-1]["end"] - starts[3], 0.2 * self.duration)   # the last scene does not take over the video

    def test_unheard_anchor_goes_between_neighbours(self):
        got = scene_csv.read(self._csv(["Every time a soldier", "By the 1930s", "words nobody said here", "During its first six years"]), self.words, self.duration)
        s = [n["start"] for n in got["scene_notes"]]
        self.assertTrue(s[1] < s[2] < s[3])
        self.assertAlmostEqual(s[2], (s[1] + s[3]) / 2, delta=1.0)
        self.assertTrue(any("not heard" in x for x in got["notes"]))


class OnScreenTextTest(unittest.TestCase):
    def test_unfinished_phrases_are_trimmed_or_dropped(self):
        from explainer.director.onscreen import finish_phrase as f
        self.assertEqual(f("obscure element buried on the"), "obscure element buried")
        self.assertEqual(f("heavy concentrations of"), "heavy concentrations")
        self.assertEqual(f("makes Stibnite unique in"), "makes Stibnite unique")
        for bare in ("becomes", "after", "bottom of a", "0 metric"):
            self.assertEqual(f(bare), "", bare)
        for whole in ("it still takes years to build", "three weeks", "100 tons", "Stibnite", "mined rock from the\nwest end pit"):
            self.assertEqual(f(whole), whole)
        self.assertEqual(f("187 per"), "187")
        self.assertEqual(f("15 year"), "15-year")

    def test_cues_are_finished_and_empty_ones_removed(self):
        from explainer.board.cues import Cue
        from explainer.director.onscreen import finish_texts
        cues = [Cue("a", "type", {"index": 0}, text="after"), Cue("b", "type", {"index": 1}, text="heavy concentrations of"), Cue("n", "narrator", {"index": 0})]
        finish_texts(cues)
        self.assertEqual([(c.id, c.text) for c in cues], [("b", "heavy concentrations"), ("n", "")])

    def test_split_thousands_are_one_number(self):
        from anchor_clock import join_number_words
        got = join_number_words([("6", 0.0, 0.2), ("500", 0.25, 0.6), ("feet", 0.6, 0.9), ("300", 1.0, 1.2), ("0", 1.25, 1.4), ("ounces", 1.4, 1.8), ("in", 2.0, 2.1), ("1941", 2.1, 2.5)])
        self.assertEqual([w for w, _, _ in got], ["6500", "feet", "300000", "ounces", "in", "1941"])


class SenseTest(unittest.TestCase):
    def test_verdict_and_cry_words_only_when_they_end_the_thought(self):
        from explainer.director.onscreen import stands_alone
        w = _words("beneath it lies a canyon and it was all lies")
        self.assertFalse(stands_alone(w, 2, len(w) - 1))
        self.assertTrue(stands_alone(w, len(w) - 1, len(w) - 1))
        w = _words("enough to drive heavy trucks")
        self.assertFalse(stands_alone(w, 0, len(w) - 1))

    def test_icons_need_their_sense_nearby(self):
        from explainer.director.onscreen import icon_in_sense
        w = _words("the crushed ore is fed into the mill")
        self.assertFalse(icon_in_sense(w, 1, "prop:swords"))
        w = _words("the army crushed the rebels at dawn")
        self.assertTrue(icon_in_sense(w, 2, "prop:swords"))
        w = _words("the bank of the united states approved the loan")
        self.assertFalse(icon_in_sense(w, 5, "prop:castle"))

    def test_echo_line_is_never_a_description(self):
        from explainer.director import compose_dialogue as D
        from explainer.director.segment import Sent
        text = "every morning the traders read the wall street headlines of lithium and copper prices again"
        w = _words(text)
        sents = [Sent(0, 0.0, w[-1][2], text, True, list(range(len(w))))]
        for c in D._echo(sents, w, {g: g for g in range(len(w))}):
            self.assertNotIn(" of ", " " + c["text"].lower() + " ")


class NumbersTest(unittest.TestCase):
    def _author(self, text):
        from test_explainer_recipes import author
        return author(text, "quantitative")[0]

    def test_crowd_only_counts_people(self):
        from explainer.director.compose_recipes import counts_people
        self.assertTrue(counts_people("miners"))
        self.assertTrue(counts_people("workers"))
        for t in ("dollars", "years", "miles", "minerals"):
            self.assertFalse(counts_people(t), t)

    def test_bars_need_one_unit(self):
        r = self._author("Domestic output was 1 national reserve against 100 tons of demand.")
        bars = [c for c in (r.cues if r else []) if (c.params or {}).get("style") == "bars"]
        self.assertEqual(bars, [])


class SpellingAndPlacesTest(unittest.TestCase):
    def test_misheard_word_takes_the_script_spelling(self):
        from explainer.director import segment as SG
        got = SG.spelling([("antimonyde", 0, 1), ("stibnites", 1, 2)], "Refined antimony and indium make indium antimonide. Stibnite is a mineral.")
        self.assertEqual(got, {"antimonyde": "antimonide"})
        self.assertEqual(SG.spelling([("antimonyde", 0, 1)], None), {})

    def test_place_words_are_capitalised(self):
        from explainer.director import select as SL
        got = SL.place_words(_words("america and china and china again idaho mobile reading state"))
        for name in ("America", "China", "Idaho"):
            self.assertIn(name, got)
        for word in ("Mobile", "Reading", "State"):
            self.assertNotIn(word, got)

    def test_opening_map_is_the_story_home(self):
        from explainer.director import select as SL
        from explainer.director.options import DirectorOptions
        o = DirectorOptions()
        o.places = ["Middle East", "Idaho"]
        o.scene_notes = [{"start": 0, "end": 1, "text": "region: Middle East"}] + [{"start": i, "end": i + 1, "text": "region: Stibnite, Idaho"} for i in range(1, 5)]
        self.assertEqual(SL.home_places(_words("the mine sits in the mountains"), o)[0], "Idaho")


class CsvMapPlacesTest(unittest.TestCase):
    def test_comma_places_are_split(self):
        from explainer.director import select as SL
        from explainer.director.options import DirectorOptions
        o = DirectorOptions(csv_first=True)
        o.places = ["Stibnite, Idaho, USA", "remote mountain canyon"]
        cands, _weak = SL.place_candidates(None, o)
        self.assertIn("Idaho", cands)
        self.assertIn("USA", cands)

    def test_a_csv_run_still_finds_the_places_the_narration_names(self):
        import inspect
        from explainer.director import select as SL
        src = inspect.getsource(SL.choose_kinds)
        self.assertNotIn("not (opt.csv_first and opt.places)", src)

    def test_narration_places_are_quick_and_careful(self):
        import time
        from explainer.director import select as SL
        text = ("china and russia control the supply while idaho waits " * 40 + "washington treated it lightly and miners pitched washington the plan "
                "the west end pit flooded and they flew to beijing")
        t = time.time()
        got = SL.transcript_places(_words(text))[0]
        self.assertLess(time.time() - t, 3.0)
        for name in ("China", "Russia", "Idaho", "Beijing"):
            self.assertIn(name, got)
        self.assertNotIn("Washington", got)          # said for the government
        self.assertNotIn("West End", got)            # a pit, not a province


class PicturesTest(unittest.TestCase):
    def test_plate_prompt_never_asks_for_variations(self):
        from explainer.director import plan as PL
        self.assertNotIn("third", PL.plate_stage("left"))
        self.assertIn("no panels", PL.plate_stage("left"))

    def test_panelled_picture_is_cut_to_one_panel(self):
        import tempfile
        import numpy as np
        from PIL import Image
        from pakmap import sourcing as S
        rng = np.random.default_rng(1)
        img = (rng.normal(120, 6, (180, 320, 3))).clip(0, 255).astype("uint8")
        with tempfile.TemporaryDirectory() as d:
            plain = f"{d}/plain.png"
            Image.fromarray(img).save(plain)
            self.assertEqual(S.panel_seams(plain), [])
            img[:, 100:200] = (img[:, 100:200].astype(int) + 70).clip(0, 255).astype("uint8")
            img[:, 99] = img[:, 200] = 10
            pan = f"{d}/panels.png"
            Image.fromarray(img).save(pan)
            self.assertTrue(S.panel_seams(pan))
            self.assertTrue(S.unpanel(pan))
            self.assertEqual(S.panel_seams(pan), [])
            self.assertEqual(Image.open(pan).size, (320, 180))


if __name__ == "__main__":
    unittest.main()
