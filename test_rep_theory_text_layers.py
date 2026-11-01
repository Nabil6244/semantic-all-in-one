"""The words beside a picture (draw.callout_column, states.picture_text, states._beam): a two-level headline, a kicker and a value from the sentence's shape, and a wider
signal-beam trigger. Plan-level and single frames only: no render, no Flow."""
from __future__ import annotations
import unittest

from reptheory import draw as D, scenes as S, states as ST

def _sc(text, no=1, start=0.0, kind="illus", **kw):
    ws = [{"w": w.strip(".,"), "p": w[-1] if w[-1] in ".,!?" else "", "t0": start + 0.35 * i, "t1": start + 0.35 * i + 0.3} for i, w in enumerate(text.split())]
    return dict({"no": no, "kind": kind, "start": start, "end": start + 0.35 * len(ws) + 0.5, "words": ws, "text": text, "decisions": [], "art": "", "section": "X", "topic": "",
                 "pages": [{"at": start + 0.1, "headline": "SOME WORDS HERE", "headline_at": start + 0.1, "value": "", "chips": [], "kicker": ""}]}, **kw)

class TextLayers(unittest.TestCase):
    def test_kicker_from_the_sentence_shape_on_any_topic(self):
        cases = {"Rest your forearm on the table, palm up.": "CUE", "Hold the plank for thirty seconds.": "CUE", "But first, a quick test.": "TEST",
                 "The most common mistake is rounding your back.": "MISTAKE", "Researchers followed 200 runners for a year.": "STUDY", "Sleep is when you recover.": ""}
        for text, want in cases.items():
            sc = _sc(text); ST.picture_text([sc]); self.assertEqual(sc["pages"][0].get("kicker", ""), want, text)

    def test_value_from_a_stated_number(self):
        sc = _sc("Hold a backpack with a few books in it, about 5 kilos."); ST.picture_text([sc]); self.assertEqual(sc["pages"][0]["value"], "5 KG")
        sc = _sc("Hold a backpack, about 5 kilos."); sc["pages"][0]["headline"] = "ABOUT 5 KILOS"; ST.picture_text([sc]); self.assertEqual(sc["pages"][0]["value"], "")      # already in the headline

    def test_only_picture_scenes_get_them(self):
        sc = _sc("Rest your forearm on the table.", kind="callout"); ST.picture_text([sc]); self.assertEqual(sc["pages"][0]["kicker"], "")

    def test_beam_fires_on_common_ways_of_saying_it(self):
        for text in ("Your brain tells your forearm to squeeze harder.", "Their force reaches your fingers through your forearm.", "Your nervous system sends the signal to your legs."):
            ws = _sc(text)["words"]; self.assertIsNotNone(ST._beam(ws, text), text)
        self.assertIsNone(ST._beam(_sc("Your forearm gets tired.")["words"], "Your forearm gets tired."))

    def test_two_level_headline(self):
        self.assertEqual(D.split_headline("REST YOUR FOREARM"), ("REST YOUR", "FOREARM")); self.assertEqual(D.split_headline("ABOUT FIVE KILOS"), ("ABOUT", "FIVE KILOS"))
        for whole in ("STIFF = FAST", "LATE LOSES", "HOLD IT THERE", "WHAT ABOUT SLEEP?"): self.assertEqual(D.split_headline(whole), ("", whole))
        self.assertEqual(D.key_colour("NEVER LOCK YOUR ELBOW"), D.T.RED); self.assertEqual(D.key_colour("KEEP IT SAFE"), (74, 222, 128))
        ctx = D.Ctx(960, 540); one = _sc("Rest your forearm.", kind="callout"); two = _sc("Rest your forearm.", kind="callout"); one["pages"][0]["headline"] = "FOREARM"; two["pages"][0]["headline"] = "REST YOUR FOREARM"
        self.assertNotEqual(S.frame(ctx, one, 1.0, tag=False).tobytes(), S.frame(ctx, two, 1.0, tag=False).tobytes())

if __name__ == "__main__":
    unittest.main()
