"""Layered picture shots (reptheory/picture.py plan_cues / overlays): the marks a Flow picture gets come from the sentence's own shape (a body part, a direction, an edge,
an alignment, a number with its unit, an object held), on any topic. Plan-level checks plus one drawing check on a synthetic picture; no render, no Flow."""
from __future__ import annotations
import tempfile, unittest

from PIL import Image

from reptheory import draw as D, library as L, picture as PIC, scenes as S

def _sc(text, kind="illus", start=0.0, step=0.35, **kw):
    ws = [{"w": w.strip(".,!?"), "p": w[-1] if w[-1] in ".,!?" else "", "t0": start + 0.2 + step * i, "t1": start + 0.2 + step * i + 0.3} for i, w in enumerate(text.split())]
    return dict({"no": 1, "kind": kind, "start": start, "end": start + 0.4 + step * len(ws) + 0.6, "words": ws, "text": text, "pages": [], "decisions": [], "art": "", "section": "X", "topic": ""}, **kw)

kinds = lambda sc: [c["kind"] for c in PIC.plan_cues(sc)]

class Cues(unittest.TestCase):
    def test_shapes_on_different_topics(self):
        self.assertIn("part", kinds(_sc("Squeeze your glutes at the top of the bridge.")))
        self.assertIn("arrow", kinds(_sc("Now curl your wrist up toward you and hold it there.")))
        self.assertIn("edge", kinds(_sc("Lower until your chest is just above the floor.")))
        self.assertIn("align", kinds(_sc("Stand tall with your head and hips in one straight line.")))
        b = [c for c in PIC.plan_cues(_sc("Drink about 500 millilitres of water after training.")) if c["kind"] == "badge"] or [c for c in PIC.plan_cues(_sc("Hold it for 30 seconds every morning.")) if c["kind"] == "badge"]
        self.assertTrue(b and b[0]["text"] in ("500", "30"))
        self.assertIn("inset", kinds(_sc("Hold a towel in both hands and pull hard.")))

    def test_every_part_said_gets_its_word(self):
        cues = PIC.plan_cues(_sc("Rest your forearm on the bench, palm up, and keep your shoulders down."))
        self.assertEqual([c["word"] for c in cues if c["kind"] == "part"][:3], ["FOREARM", "PALM", "SHOULDERS"])

    def test_limits_order_and_spacing(self):
        cues = PIC.plan_cues(_sc("Grip the bar with your hands, pull your elbows down, squeeze your back, stand tall, hold 10 seconds and lower slowly to the floor."))
        self.assertLessEqual(len(cues), PIC.CUE_MAX); self.assertTrue(all(b["at"] - a["at"] >= PIC.CUE_GAP_S - 1e-6 for a, b in zip(cues, cues[1:])))

    def test_no_marks_on_cards_or_analogies_or_loose_words(self):
        self.assertEqual(PIC.plan_cues(_sc("Every hold, how heavy, how long.", kind="checklist")), [])
        self.assertNotIn("inset", kinds(_sc("A stretchy tendon is like slack in a rope.")))      # an analogy: the rope is not in the picture
        self.assertNotIn("inset", kinds(_sc("Sit at a table.")))      # an object not held cannot be found in the picture
        self.assertNotIn("arrow", kinds(_sc("Strength goes up to about thirty percent.")))      # "up to" a number is no direction

    def test_works_from_words_alone_and_counts(self):
        sc = _sc("Push the floor away and keep your arms straight.")
        self.assertIsInstance(PIC.plan_cues(dict(sc)), list)      # the quality gate calls it at plan time, before any picture exists
        PIC.plan_cues(sc); self.assertGreaterEqual(PIC.cue_count(sc), 2)

class Drawing(unittest.TestCase):
    def test_marks_change_the_frame_on_their_words(self):
        im = Image.new("RGB", (1376, 768), (0, 0, 0)); px = im.load()
        for x in range(500, 900):
            for y in range(120, 720): px[x, y] = (230, 40, 30) if (520 < x < 700 and 300 < y < 360) else (190, 190, 190)
        f = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name; im.save(f); PIC._cache.pop(f, None)
        orig = L.find; L.find = lambda ref: {"path": f} if ref == "PC" else orig(ref)
        try:
            sc = _sc("Rest your forearm on the table and curl your wrist up.", art="PC"); PIC.plan([sc]); ctx = D.Ctx(960, 540)
            self.assertTrue(sc["pic_cues"])
            first = sc["pic_cues"][0]["at"] - sc["start"]
            a = S.frame(ctx, dict(sc), max(0.0, first - 0.15), tag=False); b = S.frame(ctx, dict(sc), sc["end"] - sc["start"] - 0.05, tag=False)
            plain = dict(sc, pic_cues=[], glows=[]); c = S.frame(ctx, plain, sc["end"] - sc["start"] - 0.05, tag=False)
            self.assertNotEqual(b.tobytes(), c.tobytes())      # the marks are drawn
            self.assertNotEqual(a.tobytes(), b.tobytes())
        finally: L.find = orig

if __name__ == "__main__":
    unittest.main()
