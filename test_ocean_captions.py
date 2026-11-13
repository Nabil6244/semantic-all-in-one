"""Ocean style step 3: short keyword captions (docs/ocean/PATTERNS.md section 4)."""

import unittest

from PIL import ImageStat

from ocean import captions as C


def _keys(text, **kw):
    kw.setdefault("every_s", 0)
    return [(c["lead"], c["key"], c["color"]) for c in C.plan(C.words_from_text(text, 0, 10), **kw)]


class KeyPickTest(unittest.TestCase):
    def test_number_with_unit_beats_everything(self):
        self.assertIn(("about", "300 TEETH", "orange"), _keys("It has about 300 teeth and nothing hunts it."))
        self.assertIn("12 MILLION YEARS", [k for _, k, _ in _keys("It swam for 12 million years.")])
        self.assertIn("3 TO 4 M", [k for _, k, _ in _keys("The smaller ones, 3 to 4 m long, hung back.")])
        self.assertIn("A FEW HUNDRED METERS", [k for _, k, _ in _keys("A few hundred meters down, it changes.")])

    def test_superlative_needs_the_and_keeps_it(self):
        self.assertIn("THE MOST OBVIOUS", [k for _, k, _ in _keys("The first one is the most obvious.")])
        self.assertIn("THE BIGGEST", [k for _, k, _ in _keys("The biggest sharks took the blubber.")])
        self.assertNotIn("MOST PEOPLE", [k for _, k, _ in _keys("When most people think about sharks, they panic.")])

    def test_danger_words_are_red(self):
        ks = _keys("They didn't die, they fled.")
        self.assertTrue(any(c == "red" for _, _, c in ks))
        self.assertIn("WIPING OUT", [k for _, k, _ in _keys("Two orcas started wiping out the sharks.")])

    def test_quantity_keeps_its_lead(self):
        self.assertIn(("only", "A FEW", "orange"), _keys("And why only a few animals can do it."))

    def test_question_mark_stays_on_the_key(self):
        self.assertTrue(any(k.endswith("?") for _, k, _ in _keys("Is it simply too big?")))

    def test_leading_filler_is_dropped(self):
        for lead, _, _ in _keys("Below you is a 5-meter great white shark."):
            self.assertFalse(lead.startswith(("is", "a ")), lead)

    def test_bare_one_is_not_a_number(self):
        self.assertNotIn("ONE", [k for _, k, _ in _keys("It grows one giant eye.")])


class PlanTest(unittest.TestCase):
    def test_weak_clauses_wait_for_a_gap(self):
        words = C.words_from_text("Picture this. You are floating off the coast. The water is calm.", 0, 4)
        self.assertEqual(C.plan(words), [])
        self.assertTrue(C.plan(words, every_s=0))

    def test_captions_never_overlap_and_hold_within_limits(self):
        text = ("It has about 300 teeth. It weighs more than a small car. In 2009, 17 of them vanished. "
                "They didn't die, they ran. Only a few animals can scare the biggest predator. ") * 3
        items = C.plan(C.words_from_text(text, 0, 40))
        self.assertGreater(len(items), 5)
        for a, b in zip(items, items[1:]):
            self.assertLessEqual(a["t1"], b["t0"])
        for c in items:
            self.assertLessEqual(c["t1"] - c["t0"], C.MAX_HOLD + 1e-6)

    def test_first_caption_of_a_chapter_goes_top(self):
        text = "Great whites are huge. The biggest one wins. The smallest one hides. Nothing is calm."
        items = C.plan(C.words_from_text(text, 0, 12), chapters=[3.0], every_s=0)
        self.assertIn("top", [c["pos"] for c in items])
        self.assertEqual(items[0]["pos"], "bottom")

    def test_word_dicts_are_accepted(self):
        ws = [{"word": "about", "start": 0.0, "end": 0.3}, {"word": "300", "start": 0.3, "end": 0.6},
              {"word": "teeth.", "start": 0.6, "end": 1.0}]
        self.assertEqual(C.plan(ws)[0]["key"], "300 TEETH")


class RenderTest(unittest.TestCase):
    def test_layer_draws_only_while_live_and_fades(self):
        item = {"t0": 1.0, "t1": 3.0, "lead": "only", "key": "A FEW", "color": "orange", "pos": "bottom"}
        p = {"items": [item]}
        self.assertIsNone(C.lay_captions(0.5, 10, p))
        self.assertIsNone(C.lay_captions(3.1, 10, p))
        full = C.lay_captions(2.0, 10, p)
        early = C.lay_captions(1.05, 10, p)
        self.assertEqual(full.size, (C.W, C.H))
        a_full = ImageStat.Stat(full.getchannel("A")).sum[0]
        self.assertGreater(a_full, 0)
        self.assertLess(ImageStat.Stat(early.getchannel("A")).sum[0], a_full)

    def test_top_and_bottom_positions(self):
        base = {"t0": 0, "t1": 2, "lead": "", "key": "THE TARGET", "color": "red"}
        top = C.lay_captions(1, 2, {"items": [dict(base, pos="top")]}).getchannel("A")
        bot = C.lay_captions(1, 2, {"items": [dict(base, pos="bottom")]}).getchannel("A")
        self.assertIsNotNone(top.crop((0, 0, C.W, C.H // 3)).getbbox())
        self.assertIsNotNone(bot.crop((0, C.H * 2 // 3, C.W, C.H)).getbbox())

    def test_card_table_entry(self):
        self.assertIs(C.CARDS["ocean.lay_captions"], C.lay_captions)


if __name__ == "__main__":
    unittest.main()
