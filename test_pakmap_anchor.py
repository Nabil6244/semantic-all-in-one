"""pakMap narration anchoring: find where a phrase is spoken in the Whisper word list."""

import unittest

from pakmap.anchor import Transcript, norm_token, tokenize
from pakmap.words import estimate_words, load_words, save_words

WORDS = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(
    "Kenya has forty seven million people, but the north is empty. Turkana and Marsabit are huge. "
    "Kenya has the Rift Valley. Kaliningrad is far away".split())]


class TestTokens(unittest.TestCase):
    def test_punctuation_case_and_numbers(self):
        self.assertEqual(tokenize("The North, is EMPTY!"), ["the", "north", "is", "empty"])
        self.assertEqual(norm_token("47,000"), "47000")
        self.assertEqual(tokenize("Mont-Blanc"), ["mont", "blanc"])
        self.assertEqual(tokenize("   "), [])


class TestFind(unittest.TestCase):
    def setUp(self):
        self.tr = Transcript(WORDS)

    def test_finds_the_words_and_their_times(self):
        m, nxt = self.tr.find("north is empty")
        self.assertEqual((m.t_start, m.t_end), (WORDS[8][1], WORDS[10][2]))
        self.assertEqual(m.text, "north is empty.")
        self.assertFalse(m.fuzzy or m.out_of_order)
        self.assertEqual(nxt, 10)  # the cursor counts tokens: "forty seven" is one token, so this is one less than the word index

    def test_spoken_numbers_meet_digits_both_ways(self):
        self.assertEqual(self.tr.find("forty seven million")[0].first, 2)
        self.assertEqual(self.tr.find("47 million")[0].first, 2)
        digits = Transcript([("it", 0, 0.2), ("is", 0.2, 0.4), ("47", 0.4, 0.8), ("million", 0.8, 1.2)])
        self.assertEqual(digits.find("forty seven million")[0].first, 2)

    def test_a_repeated_phrase_is_found_where_the_script_says_it_in_order(self):
        first, cur = self.tr.find("Kenya has")
        second, _ = self.tr.find("Kenya has", cur)
        self.assertEqual((first.first, second.first), (0, 16))
        self.assertFalse(second.out_of_order)

    def test_going_back_is_found_but_flagged(self):
        _, cur = self.tr.find("Kaliningrad")
        again, _ = self.tr.find("Marsabit", cur)
        self.assertTrue(again.out_of_order)

    def test_spelling_variants_plurals_and_one_extra_word(self):
        m, _ = self.tr.find("Kalinigrad")
        self.assertTrue(m.fuzzy and m.text == "Kaliningrad")
        self.assertIsNotNone(self.tr.find("million peoples"))
        m2, _ = self.tr.find("Turkana Marsabit")  # 'and' was spoken between them
        self.assertTrue(m2.fuzzy)
        self.assertEqual(m2.text, "Turkana and Marsabit")

    def test_not_found_and_empty(self):
        self.assertIsNone(self.tr.find("Nairobi"))
        self.assertIsNone(self.tr.find("   "))
        self.assertIsNone(Transcript([]).find("anything"))

    def test_short_words_are_not_matched_loosely(self):
        self.assertIsNone(Transcript([("cat", 0, 1), ("sat", 1, 2)]).find("cut"))


class TestRealSpeech(unittest.TestCase):
    """Things a real Whisper transcript does that a typed script does not."""

    def words(self, text):
        return [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(text.split())]

    def test_spoken_numbers_meet_digits_hundreds_thousands_and_all(self):
        tr = Transcript(self.words("less than 250 millimetres and up to 2,000 millimetres in 1984"))
        self.assertEqual(tr.find("two hundred and fifty")[0].first, 2)
        self.assertEqual(tr.find("up to two thousand")[0].first, 5)
        self.assertEqual(tr.find("nineteen eighty four")[0].first, 10)
        spoken = Transcript(self.words("less than two hundred and fifty millimetres and up to two thousand"))
        self.assertEqual(spoken.find("250 millimetres")[0].last, 6)
        self.assertEqual(spoken.find("2000")[0].first, 10)

    def test_number_words_are_not_over_eager(self):
        from pakmap.anchor import _merge_numbers, tokenize
        m = lambda t: _merge_numbers(tokenize(t))
        self.assertEqual(m("forty seven million"), [("47", 2), ("million", 1)])
        self.assertEqual(m("thirteen five"), [("13", 1), ("5", 1)])
        self.assertEqual(m("five and ten"), [("5", 1), ("and", 1), ("10", 1)])
        self.assertEqual(m("twelve thousand five hundred"), [("12500", 4)])
        self.assertEqual(m("a hundred"), [("a", 1), ("hundred", 1)])
        self.assertEqual(m("one hundred and five"), [("105", 4)])
        self.assertEqual(m("nineteen eighty four"), [("1984", 3)])
        self.assertEqual(m("twenty twenty four"), [("2024", 3)])
        self.assertEqual(m("twenty one"), [("21", 2)])

    def test_a_name_heard_as_two_words_is_still_found(self):
        tr = Transcript(self.words("the town of Marsa Bit is dry"))
        hit = tr.find("Marsabit")
        self.assertIsNotNone(hit)
        self.assertEqual(hit[0].text, "Marsa Bit")
        self.assertTrue(hit[0].fuzzy)
        self.assertIsNone(Transcript(self.words("the town of two bits is dry")).find("Marsabit"))

    def test_when_nothing_matches_the_closest_heard_words_are_offered(self):
        tr = Transcript(self.words("then Turkana and marcebid are home to few"))
        text, t = tr.nearest("Marsabit")
        self.assertEqual(text, "marcebid")
        self.assertAlmostEqual(t, 1.2)
        self.assertIsNone(tr.nearest("zzzzzzzz"))
        self.assertIsNone(Transcript([]).nearest("x"))


class TestWordFiles(unittest.TestCase):
    def test_estimated_words_are_ordered_and_pause_at_sentence_ends(self):
        w = estimate_words("One two three. Four five six.")
        self.assertEqual(len(w), 6)
        self.assertTrue(all(b[1] >= a[2] for a, b in zip(w, w[1:])))
        self.assertGreater(w[3][1] - w[2][2], 0.3)

    def test_round_trip_and_formats(self):
        import json, tempfile, pathlib
        d = pathlib.Path(tempfile.mkdtemp())
        save_words(WORDS[:3], d / "w.json")
        self.assertEqual(load_words(d / "w.json"), [(w, s, e) for w, s, e in WORDS[:3]])
        (d / "a.json").write_text(json.dumps([{"word": " hi", "start": 0, "end": 1}, {"word": "there", "start": 1, "end": 2}]))
        self.assertEqual(load_words(d / "a.json")[0][0], "hi")
        (d / "b.json").write_text(json.dumps({"segments": [{"words": [{"word": "x", "start": 0, "end": 1}]}]}))
        self.assertEqual(len(load_words(d / "b.json")), 1)
        (d / "c.json").write_text(json.dumps([["b", 2, 3], ["a", 1, 2]]))
        with self.assertRaisesRegex(ValueError, "must be in order"):
            load_words(d / "c.json")
        (d / "e.json").write_text(json.dumps([["a", 0]]))
        with self.assertRaisesRegex(ValueError, "entry 1"):
            load_words(d / "e.json")


if __name__ == "__main__":
    unittest.main()
