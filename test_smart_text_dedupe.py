"""Smart text pops dedupe on the spoken word, not the raw token: "In 1822, the French..." used to pop both "1822,"
and "1822" at the same moment (e2e runB, scenes 9 and 13). Shown text carries no trailing sentence punctuation."""

import unittest

from smart_editing import SmartEditingSettings, _find_emphasis_phrases, plan_text_effects
from video_generator import split_words


def _plan(segments, windows, intensity="high"):
    rows = [{"scene_number": str(i + 1), "script_segment": s} for i, s in enumerate(segments)]
    aligned = [{"scene_number": str(i + 1), "start_time": a, "end_time": b} for i, (a, b) in enumerate(windows)]
    return rows, aligned, SmartEditingSettings(text_effects_intensity=intensity)


class SmartTextDedupe(unittest.TestCase):
    def test_number_with_comma_is_one_phrase(self):
        phrases = _find_emphasis_phrases("In 1822, the French engineer Augustin Fresnel invented a new kind of lens.")
        self.assertIn("1822", phrases)
        self.assertNotIn("1822,", phrases)
        self.assertEqual(sum(1 for p in phrases if split_words(p) == ["1822"]), 1, phrases)

    def test_number_keeps_inner_separators(self):
        phrases = _find_emphasis_phrases("It cost $2,500.75. Then 40%, then 3.5.")
        self.assertIn("$2,500.75", phrases)
        self.assertIn("40%", phrases)
        self.assertIn("3.5", phrases)
        self.assertFalse([p for p in phrases if p[-1] in ".,;:!?"], phrases)

    def test_currency_and_bare_number_are_one_phrase(self):
        phrases = _find_emphasis_phrases("They paid $400 for it.")
        self.assertEqual([p for p in phrases if split_words(p) == ["400"]], ["$400"])

    def test_1822_pops_once(self):
        seg = "In 1822, the French engineer Augustin Fresnel invented a new kind of lens."
        rows, aligned, settings = _plan([seg], [(0.0, 6.0)])
        words = [(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(split_words(seg))]
        fx = plan_text_effects(rows, aligned, words, settings)
        texts = [e["text"] for e in fx]
        self.assertIn("1822", texts)
        self.assertNotIn("1822,", texts)
        self.assertEqual(texts.count("1822"), 1, texts)
        self.assertEqual(len(fx), 3)  # budget still filled (high = 3)
        self.assertFalse([t for t in texts if t[-1] in ".,;:!?"], texts)

    def test_weak_words_with_punctuation_stay_filtered(self):
        seg = "The, than. With, granite!"
        phrases = _find_emphasis_phrases(seg)
        self.assertEqual(phrases, ["granite"])
        rows, aligned, settings = _plan([seg], [(0.0, 4.0)])
        words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(split_words(seg))]
        self.assertEqual([e["text"] for e in plan_text_effects(rows, aligned, words, settings)], ["granite"])

    def test_same_word_never_overlaps_across_scene_edge(self):
        # scene windows overlap at the edge; the shared word "granite" sits in both
        segs = ["Smeaton cut granite", "granite blocks interlocking"]
        words = [("smeaton", 0.2, 0.8), ("cut", 0.9, 1.3), ("granite", 1.95, 2.2), ("blocks", 2.4, 2.9), ("interlocking", 3.0, 3.8)]
        rows, aligned, settings = _plan(segs, [(0.0, 2.0), (1.95, 4.5)])
        fx = plan_text_effects(rows, aligned, words, settings)
        granite = [e for e in fx if e["text"].lower() == "granite"]
        self.assertEqual(len(granite), 1, fx)


if __name__ == "__main__":
    unittest.main()
