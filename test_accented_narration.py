"""Non-English narration (project #085, Spanish): accented letters fold to their base letter in alignment tokens instead
of being dropped ("caminó" was "camin", "ángeles" was "ngeles"), and smart text shows the narration's own word."""

import unittest

from smart_editing import SmartEditingSettings, plan_text_effects
from video_generator import normalize_word, split_words


class AccentedNarration(unittest.TestCase):
    def test_tokens_keep_their_letters(self):
        self.assertEqual(split_words("Enoc caminó con Dios; los ángeles, Génesis y Qumrán."),
                         ["enoc", "camino", "con", "dios", "los", "angeles", "genesis", "y", "qumran"])
        self.assertEqual(normalize_word("Peña"), "pena")

    def test_english_tokens_are_unchanged(self):
        self.assertEqual(split_words("The Watcher's 1,000 years, rock-cut tombs"), ["the", "watcher", "1000", "years", "rock", "cut", "tombs"])

    def test_accent_variants_align(self):
        self.assertEqual(normalize_word("Génesis"), normalize_word("Genesis"))

    def test_smart_text_shows_the_real_word(self):
        rows = [{"scene_number": "1", "script_segment": "Enoc caminó con Dios entre los ángeles."}]
        aligned = [{"scene_number": "1", "start_time": 0.0, "end_time": 6.0}]
        words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(split_words(rows[0]["script_segment"]))]
        texts = [e["text"] for e in plan_text_effects(rows, aligned, words, SmartEditingSettings(text_effects_intensity="high"))]
        self.assertTrue(texts)
        self.assertTrue(all(t in rows[0]["script_segment"] for t in texts), texts)
        self.assertFalse({"camin", "ngeles"} & set(texts))


if __name__ == "__main__":
    unittest.main()
