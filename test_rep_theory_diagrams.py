"""Phase 3 diagrams (reptheory/diagrams.py): each is read from the sentence's shape, never from one script, and draws without error at every moment."""
import unittest

from PIL import Image

from reptheory import cards as K, diagrams as DG, draw as D, variety as V


def scene(text, start=10.0):
    ws = [{"w": w, "t0": start + i * 0.3} for i, w in enumerate(text.split())]
    return {"text": text, "words": ws, "start": start, "end": start + len(ws) * 0.3 + 0.5, "kind": "callout", "pages": [], "decisions": []}


CASES = {
    "lever": "Load is weight times distance, so a 10 kg backpack makes it heavier.",
    "seesaw": "Lean too far forward and you tip over.",
    "gap": "Your muscles get stronger faster than your tendons.",
    "split": "A planche is half strength, half balance.",
    "panels": "Turn a weak lean into a solid hold.",
    "tearoff": "Some get it in a few months, others take one to two years, some never.",
    "battery": "Training drains your tendons; rest rebuilds them.",
    "clipboard": "Your plan: warm up, three leans, two frog stands, push-ups.",
    "road": "This is the road to the planche.",
    "silrow": "Start with a plank, then a push-up, then a squat.",
}


class Diagrams(unittest.TestCase):
    def test_each_shape_found(self):
        for kind, text in CASES.items():
            sc = scene(text); ev = DG.evidence(sc, text)
            self.assertIn(kind, ev, text)
            c = ev[kind][1]; self.assertTrue(all(sc["start"] <= m <= sc["end"] + 1.5 for m in c["marks"]), (kind, c["marks"]))

    def test_payload_words_come_from_the_sentence(self):
        c = DG.lever(scene(CASES["lever"]), CASES["lever"]); self.assertEqual((c["a"], c["b"], c["obj"]), ("WEIGHT", "DISTANCE", "+10 KG BACKPACK"))
        c = DG.gap(scene(CASES["gap"]), CASES["gap"]); self.assertEqual((c["fast"], c["slow"]), ("MUSCLES", "TENDONS"))
        c = DG.tearoff(scene(CASES["tearoff"]), CASES["tearoff"]); self.assertEqual([p["text"] for p in c["pages"]], ["FEW MONTHS", "1-2 YEARS", "SOME NEVER"])
        c = DG.clipboard(scene(CASES["clipboard"]), CASES["clipboard"]); self.assertEqual([i["text"] for i in c["items"]], ["WARM UP", "THREE LEANS", "TWO FROG STANDS", "PUSH-UPS"])

    def test_not_forced(self):
        for text in ("Do 3 sets of 10 reps.", "Rest 60 seconds between sets.", "Both arms and legs stay straight.", "Train 4 days a week.",
                     "Write down how your workouts feel and how you sleep.", "A planche is half strength, half balance."):
            ev = DG.evidence(scene(text), text)
            self.assertFalse(set(ev) - {"split"} if "half" in text else ev, text)

    def test_wired_as_full_cards(self):
        for k in DG.KINDS: self.assertIn(k, V.FULL_CARDS); self.assertIn(k, K.CARD_DONE)
        sc = scene(CASES["gap"]); self.assertIn("gap", V.evidence(sc))

    def test_draws_at_every_moment(self):
        ctx = D.Ctx(640, 360)
        for kind, text in CASES.items():
            sc = scene(text); c = DG.evidence(sc, text)[kind][1]
            for t in (sc["start"] - 0.5, sc["start"] + 0.4, c["marks"][-1], K.CARD_DONE[kind](c) + 1):
                cv = Image.new("RGB", (640, 360)); DG.draw(cv, ctx, kind, c, t)


if __name__ == "__main__":
    unittest.main()
