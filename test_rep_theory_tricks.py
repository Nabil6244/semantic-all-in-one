"""Phase 4 on-picture tricks (reptheory/tricks.py): read from the sentence's words, only on pictures, one top trick per scene, and they draw at every moment."""
import unittest

from PIL import Image

from reptheory import draw as D, tricks as TR


def scene(text, kind="illus", start=10.0):
    ws = [{"w": w, "t0": start + i * 0.3} for i, w in enumerate(text.split())]
    return {"text": text, "words": ws, "start": start, "end": start + len(ws) * 0.3 + 1.0, "kind": kind, "pages": [], "decisions": []}


class Tricks(unittest.TestCase):
    def test_each_trick_from_its_words(self):
        cases = {"strike": ("A planche isn't a strength trick. It's a lever.", "STRENGTH TRICK?"), "bubble": ("Your body says stop.", "STOP!"),
                 "aside": ("This is stupid easy, trust me.", "(stupid easy)")}
        for k, (text, want) in cases.items():
            sc = scene(text); TR.plan([sc]); self.assertEqual(sc[k]["text"], want, text)
        sc = scene("She is 167 cm and 65 kg."); TR.plan([sc]); self.assertEqual((sc["measure"]["height"]["text"], sc["measure"]["weight"]["text"]), ("167 CM", "65 KG"))
        sc = scene("A planche isn't a strength trick. It's a lever."); TR.plan([sc]); self.assertGreater(sc["strike"]["strike_at"], sc["strike"]["at"])

    def test_not_forced(self):
        for text in ("It is not easy.", "Run 30 m and rest.", "Hold it for ten seconds."):
            sc = scene(text); TR.plan([sc]); self.assertFalse([k for k in TR.OVERLAYS if sc.get(k)], text)
        sc = scene("A planche isn't a strength trick.", kind="steps"); TR.plan([sc]); self.assertNotIn("strike", sc)      # never on a card

    def test_one_top_trick_and_hazard_spacing(self):
        sc = scene("Your body says stop, trust me, it isn't a strength trick."); TR.plan([sc]); self.assertEqual([k for k in ("strike", "bubble", "aside") if sc.get(k)], ["strike"])
        a, b, c = scene("Careful, tendons can tear.", start=0), scene("That pain is a warning.", start=10), scene("Danger again here.", start=45)
        TR.plan([a, b, c]); self.assertEqual([bool(x.get("hazard")) for x in (a, b, c)], [True, False, True])

    def test_draws(self):
        ctx = D.Ctx(640, 360)
        sc = scene("Careful: she is 167 cm and 65 kg and isn't a strength trick. It's a lever."); TR.plan([sc])
        for t in (sc["start"], sc["start"] + 1.5, sc["start"] + 3.0, sc["end"] + 2):
            TR.draw(Image.new("RGB", (640, 360)), ctx, sc, t)
        for text in ("Your body says stop.", "This is stupid easy, trust me."):
            s2 = scene(text); TR.plan([s2]); TR.draw(Image.new("RGB", (640, 360)), ctx, s2, s2["end"])


if __name__ == "__main__":
    unittest.main()
