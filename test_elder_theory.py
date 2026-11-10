"""Elder Health Theory: the Rep Theory engine with the calm clinic theme (reptheory/theme.py "elder"): soft-colour Flow pictures of older people and organs, a handwriting board. Rep Theory stays as it was."""
import unittest

from PIL import Image

from reptheory import app_section as A, beat_art as BA, cards as K, direction as DR, draw as D, theme as T
from ui import style_registry as R


class ElderTheoryTheme(unittest.TestCase):
    def tearDown(self):
        T.set_theme("")

    def test_switch_and_back(self):
        base = (T.BG_TOP, T.WHITE, T.HEAD_FONT, T.P(20, 20, 22, 9))
        self.assertEqual(T.set_theme("elder"), "elder")
        self.assertIn("elder", T.NO_GYM); self.assertIn("elder", T.LIGHT)
        self.assertGreater(sum(T.BG_TOP), 700)          # light canvas
        self.assertLess(sum(T.WHITE), 200)              # dark navy type on it
        self.assertGreater(sum(T.P(20, 20, 22)), 700)   # card panels turn light
        T.set_theme("")
        self.assertEqual((T.BG_TOP, T.WHITE, T.HEAD_FONT, T.P(20, 20, 22, 9)), base)

    def test_prompts_people_and_organs(self):
        T.set_theme("elder")
        organ = BA.prompt_for("Your heart works harder after sixty.")
        self.assertIn("human heart", organ); self.assertIn("medical illustration", organ)
        life = BA.prompt_for("Walk for ten minutes after dinner.")
        self.assertIn("older person", life); self.assertNotIn("medical illustration", life)
        for p in (organ, life, BA.own_prompt("an older man reading in a chair")):
            self.assertNotIn("manga-style young man", p); self.assertIn("white background", p)
        self.assertIn("medical illustration", BA.own_prompt("a cross-section of a knee joint showing the cartilage"))
        T.set_theme("")
        self.assertIn("young man", BA.prompt_for("Hold the bar for ten seconds."))   # Rep Theory still draws its trainee

    def test_board_draws_handwriting(self):
        T.set_theme("elder"); ctx = D.Ctx(640, 360)
        cv = ctx.backdrop(); before = cv.copy()
        K.board(cv, ctx, [{"text": "Walk after meals", "at": 0.0}, {"text": "Drink water", "at": 1.0}], 3.0)
        self.assertNotEqual(cv.tobytes(), before.tobytes())
        cv2 = ctx.backdrop(); K.board_takeaway(cv2, ctx, {"words": [{"w": "Move", "t0": 0.0}, {"w": "daily", "t0": 0.4}]}, 2.0)
        self.assertEqual(cv2.size, (640, 360))

    def test_board_gets_its_own_picture(self):
        T.set_theme("elder")
        sc = {"kind": "checklist", "text": "Walk after meals, drink water and sleep early.", "decisions": [], "no": 3, "look": "board", "directed_look": True}
        self.assertTrue(BA.board_wants_picture(sc))
        got = []; BA.prepare([sc], collect=got, directed=True)
        self.assertEqual(len(got), 1); self.assertIn("older person", got[0]["prompt"]); self.assertEqual(sc["kind"], "checklist")   # the scene stays a board
        ctx = D.Ctx(640, 360); pic = Image.new("RGB", (400, 300), (240, 120, 120))
        a, b = ctx.backdrop(), ctx.backdrop()
        K.board(a, ctx, [{"text": "Walk after meals", "at": 0.0}], 3.0); K.board(b, ctx, [{"text": "Walk after meals", "at": 0.0}], 3.0, pic=pic)
        self.assertNotEqual(a.tobytes(), b.tobytes())   # the picture is pinned on the board
        T.set_theme("")
        self.assertFalse(BA.board_wants_picture(sc))   # Rep Theory boards stay as they were

    def test_board_doodles_and_notes(self):
        self.assertEqual(K.doodle_for("Drink a glass of water")[0], "glass")
        self.assertEqual(K.doodle_for("Walk after every meal")[0], "feet")
        self.assertEqual(K.doodle_for("Sleep before eleven")[0], "moon")
        T.set_theme("elder"); ctx = D.Ctx(640, 360); pic = Image.new("RGB", (400, 300), (240, 120, 120))
        items = [{"text": "Walk after meals", "at": 0.0}, {"text": "Drink water", "at": 0.8}, {"text": "Sleep early", "at": 1.6}]
        a, b = ctx.backdrop(), ctx.backdrop()
        K.board(a, ctx, items, 4.0, pic=pic, caption="Heart"); K.board(b, ctx, items, 4.0, pic=pic, caption="Heart", notes=True)
        self.assertNotEqual(a.tobytes(), b.tobytes())   # sticky notes are a different layout

    def test_health_cards_from_the_words(self):
        from reptheory import health as HE, variety as V, scenes as S
        T.set_theme("elder"); sc = {"start": 0.0, "end": 5.0, "words": [], "text": ""}
        ev = lambda txt: V.evidence(dict(sc, text=txt))
        self.assertEqual(ev("Your heart beats about one hundred thousand times a day.")["vitals"][1]["value"], 100000)
        self.assertEqual(ev("Walking lowers your blood pressure.")["pressure"][1]["trend"], "down")
        self.assertEqual(ev("A short walk after eating lowers blood sugar.")["sugar"][1]["trend"], "down")
        self.assertEqual(ev("Your kidneys clean your blood.")["body"][1]["organ"], "kidneys")
        self.assertEqual(ev("Drink six glasses of water a day.")["water"][1]["n"], 6)
        self.assertEqual(ev("Try to sleep seven hours.")["sleep"][1]["hours"], 7)
        self.assertNotIn("versus", ev("Your heart beats about 100,000 times a day."))   # a heartbeat is not "A beats B"
        self.assertTrue(V._warning(sc, "If your chest feels tight when you walk, sit down and call your doctor."))
        self.assertEqual(len(V._checklist(sc, "Walk after every meal, drink a glass of water each morning, and sleep before eleven.")["items"]), 3)
        ctx = D.Ctx(480, 270)
        for k, p in (("vitals", {"at": 0, "bpm": 72, "value": 5, "unit": "X", "value_at": 0}), ("pressure", {"at": 0, "trend": "down", "trend_at": 0.5}), ("sugar", {"at": 0, "trend": "down", "trend_at": 0.5, "meal": True}),
                     ("body", {"at": 0, "organ": "heart", "label": "HEART"}), ("water", {"at": 0, "n": 4}), ("sleep", {"at": 0, "hours": 7}),
                     ("doctor", HE.doctor_payload("If your chest hurts, call your doctor.", [{"text": "CALL YOUR DOCTOR", "at": 0.5}]))):
            cv = ctx.backdrop(); before = cv.tobytes(); HE.draw(cv, ctx, k, p, 2.0, 0.0); self.assertNotEqual(cv.tobytes(), before, k)
        T.set_theme("")
        self.assertEqual(HE.evidence(sc, "Your heart beats fast.", V._at), {})   # Rep Theory never gets health cards
        self.assertEqual(V._versus(sc, "Consistency beats intensity.")["a"]["text"], "CONSISTENCY")

    def test_picker_prompt_and_look(self):
        self.assertEqual(R.BUILT_ON[R.ELDER_THEORY], "Rep Theory")
        out = R.with_extras(("Rep Theory", "Health Cinema"))
        self.assertEqual(out[out.index("Carl Jung Theory") + 1], "Elder Health Theory")
        txt = A.prompt_text("My script.", cat="elder")
        self.assertIn("Elder Health Theory", txt); self.assertTrue(txt.rstrip().endswith("My script.")); self.assertNotIn("<<<PASTE", txt)
        self.assertEqual(DR.norm_look("board"), "checklist")


if __name__ == "__main__":
    unittest.main()
