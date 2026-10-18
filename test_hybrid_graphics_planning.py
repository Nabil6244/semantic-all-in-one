"""Hybrid Map graphics planning from a REAL transcript (2026-10-19): Whisper's words have no punctuation and no capitals, so the sentence planners
saw one sentence for the whole video and drew nothing (0 narration-driven graphics, 0 place outlines, in all 11 saved projects). The planners now read
the transcript through gfx_templates.display_words (the script's own punctuation when the plan has it, pauses when not), and a narration that writes its
numbers in words ("a hundred metres") is read as numbers."""

from __future__ import annotations

import unittest

import gfx_templates as G
import place_focus


def _plain(text: str, step: float = 0.5, pause_after: "set[int]" = frozenset()):
    """Words as Whisper gives them: lower case, no punctuation, one time per word."""
    out, t = [], 0.0
    for i, w in enumerate(text.lower().replace(",", "").replace(".", "").split()):
        out.append((w, round(t, 3), round(t + step * 0.8, 3)))
        t += step + (0.8 if i in pause_after else 0.0)
    return out


SCRIPT = ("Drive west out of Melbourne and the land flattens. Coal seams more than a hundred metres thick lie under Gippsland. "
          "Bendigo produced well over twenty million ounces of gold, which puts it among the great goldfields. "
          "About thirty-five thousand years ago, magma met groundwater. It happened in 1855.")


class TestSentencesFromRealTranscripts(unittest.TestCase):
    def test_a_transcript_without_punctuation_used_to_be_one_sentence(self):
        words = _plain(SCRIPT)
        self.assertEqual(len(G.sentences(words)), 1)            # the bug, kept as the baseline of what Whisper gives
        self.assertEqual(len(G.sentences(G.display_words(words, SCRIPT))), 5)

    def test_the_scripts_own_tokens_and_the_heard_times(self):
        words = _plain(SCRIPT)
        shown = G.display_words(words, SCRIPT)
        sents = G.sentences(shown)
        self.assertEqual(sents[1][0], "Coal seams more than a hundred metres thick lie under Gippsland.")
        heard = {w[0]: w[1] for w in words}
        self.assertAlmostEqual(sents[1][1], heard["coal"], places=2)       # starts when "coal" is spoken
        self.assertAlmostEqual(sents[4][1], heard["it"], places=2)

    def test_without_a_script_a_pause_ends_a_sentence(self):
        words = _plain("one two three four five six seven eight nine ten eleven twelve", pause_after={5})
        self.assertEqual(len(G.sentences(G.display_words(words))), 2)

    def test_a_punctuated_transcript_is_left_alone(self):
        words = [("Hello", 0.0, 0.3), ("there.", 0.3, 0.6), ("Again", 1.0, 1.3), ("now.", 1.3, 1.6)] * 30
        self.assertEqual(G.display_words(words, "Hello there. Again now."), words)

    def test_a_script_that_is_not_what_was_spoken_is_not_forced_on_it(self):
        words = _plain("alpha bravo charlie delta echo foxtrot golf hotel india juliet " * 3, pause_after={9, 19})
        shown = G.display_words(words, "Completely different words about another subject entirely.")
        self.assertEqual(len(G.sentences(shown)), 3)           # pause based, not the script's one sentence


class TestNumbersWrittenInWords(unittest.TestCase):
    def test_conversions(self):
        f = G._spoken_number
        self.assertEqual(f("more than a hundred metres thick"), "more than 100 metres thick")
        self.assertEqual(f("well over twenty million ounces"), "well over 20 million ounces")
        self.assertEqual(f("About thirty-five thousand years ago"), "About 35,000 years ago")
        self.assertEqual(f("two hundred and fifty thousand people"), "250,000 people")
        self.assertEqual(f("twenty five years"), "25 years")
        self.assertEqual(f("sixty percent of it"), "60 percent of it")

    def test_things_that_are_not_quantities_stay_words(self):
        f = G._spoken_number
        for text in ("one of the best", "a few more", "In nineteen fifty it", "tens of millions of years", "hundred of them"):
            self.assertEqual(f(text), text)

    def test_digits_with_a_scale_word_are_not_doubled(self):
        self.assertEqual(G._spoken_number("almost 10 million square kilometres"), "almost 10 million square kilometres")


class TestAutoGraphicsFromTheRealShape(unittest.TestCase):
    def test_numbers_in_the_script_become_graphics_on_an_unpunctuated_transcript(self):
        text = ("Welcome to the story of a very old land and its rocks, told slowly. " * 2 +
                "Coal seams more than a hundred metres thick lie under Gippsland. And so the story moves on into the next chapter of the tale, "
                "slowly and carefully, with plenty of time for the listener to look at the land and take in what was said before. "
                "Bendigo produced well over twenty million ounces of gold, which puts it among the great goldfields. The end of that part of it all.")
        words = _plain(text, step=3.0)      # more than two minutes apart: the same layout may return
        none = G.auto_events(words, niche="map", script=None, total=words[-1][2])
        ev = G.auto_events(words, niche="map", script=text, total=words[-1][2])
        self.assertEqual(sorted(e["slots"]["value"] for e in ev), [20, 100])
        NUMBER_LAYOUTS = {"big_number", "gold_stat", "stat_countup", "counter_corner"}
        self.assertTrue({e["template"]["id"] for e in ev} <= NUMBER_LAYOUTS)
        self.assertEqual(len({e["template"]["id"] for e in ev}), 2)                  # the second number takes another layout
        said = {e["slots"]["value"]: " ".join(str(v) for v in e["slots"].values()).upper() for e in ev}
        self.assertIn("METRES", said[100])                                          # the unit the narrator used travels with the number, in whichever slot the layout has
        self.assertIn("OUNCES", said[20])
        self.assertTrue(all(e["t_out"] - e["t_in"] >= 2.0 for e in ev))
        self.assertGreaterEqual(len(ev), len(none))

    def test_the_report_says_why_a_graphic_was_not_drawn(self):
        text = ("Welcome to the story of a very old land and its rocks, told slowly. Coal seams more than a hundred metres thick lie under Gippsland. "
                "And so the story moves on into the next chapter of the tale. Bendigo produced well over twenty million ounces of gold, which puts it among the great goldfields.")
        words = _plain(text)
        report = []
        ev = G.auto_events(words, niche="map", script=text, report=report, enabled=("big_number",))      # one layout: its own repeat rule
        self.assertEqual([e["slots"]["value"] for e in ev], [100])
        left_out = [r for r in report if r["reason"] != "not_enough_in_the_sentence"]
        self.assertEqual([(r["template"], r["reason"]) for r in left_out], [("big_number", "same_layout_again")])


class TestPlaceAliases(unittest.TestCase):
    def test_port_is_not_portugal(self):
        index = place_focus._index()
        got = place_focus._mentions("The Yarra River ran out through the narrow entrance at Port Phillip Heads.", index)
        self.assertNotIn("Port", [m.entity_names for m in got])

    def test_a_real_name_still_matches(self):
        index = place_focus._index()
        got = place_focus._mentions("The road crosses Portugal and then Spain.", index)
        self.assertEqual([m.entity_names for m in got], ["Portugal", "Spain"])


if __name__ == "__main__":
    unittest.main()
