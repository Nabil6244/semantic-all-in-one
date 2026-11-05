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


class FirstRenderFixes(unittest.TestCase):      # found in the first 1-minute render, 2026-11-02
    def test_measure_clear_of_left_text_column(self):
        """haseeb_rep 00:02: the "140 LB" chip landed on the left headline ("MOTORCYCLE") of a full-frame picture. A left column moves the ruler + chip to the right edge."""
        ctx = D.Ctx(1920, 1080); c = {"height": {"text": "180 CM", "at": 0.0}, "weight": {"text": "140 LB", "at": 0.0}}
        def orange_cols(col_x):
            ctx.col_x = col_x; cv = Image.new("RGB", (1920, 1080), (0, 0, 0)); TR.draw_measure(cv, ctx, c, 5.0)
            px = cv.load(); return [x for x in range(0, 1920, 4) for y in range(0, 1080, 6) if px[x, y][0] > 200 and 80 < px[x, y][1] < 200 and px[x, y][2] < 80]
        xs = orange_cols(None); self.assertTrue(xs and max(xs) < 960)      # no column / column on the right: left edge as before
        xs = orange_cols(1130); self.assertTrue(xs and max(xs) < 960)
        xs = orange_cols(110); self.assertTrue(xs and min(xs) > 1300)      # column on the left: nothing orange left of it
        ctx.col_x = None

    def test_strike_headline_not_repeated_and_bubble_on_verb(self):
        sc = scene("A planche isn't a strength trick."); sc["pages"] = [{"headline": "STRENGTH TRICK", "at": 10.5}]; TR.plan([sc]); self.assertEqual(sc["pages"][0]["headline"], "")
        sc = scene("When the wrists hurt, your body says stop."); TR.plan([sc]); self.assertLess(sc["bubble"]["at"], sc["words"][-1]["t0"])

    def test_question_is_not_a_warning(self):
        sc = scene("You asked: will it hurt my wrists?"); TR.plan([sc]); self.assertNotIn("hazard", sc)

    def test_faded_text_is_faded(self):
        from PIL import ImageDraw
        ctx = D.Ctx(400, 100)
        for a, want in ((0, 0), (128, 128), (255, 255)):
            cv = Image.new("RGB", (400, 100)); D.text_spaced(ImageDraw.Draw(cv, "RGBA"), (10, 10), "Q1", ctx.font("Manrope-ExtraBold.ttf", 60), (255, 255, 255, a), 2)
            self.assertEqual(max(cv.convert("L").get_flattened_data()), want)
