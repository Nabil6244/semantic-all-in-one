"""Elder Health Theory: the Rep Theory engine with the calm clinic theme (reptheory/theme.py "elder"): soft-colour Flow pictures of older people and organs, a handwriting board. Rep Theory stays as it was."""
import tempfile, unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from reptheory import app_section as A, beat_art as BA, cards as K, direction as DR, draw as D, theme as T
from ui import style_registry as R


class ElderTheoryTheme(unittest.TestCase):
    def setUp(self):      # the Elder cast file (elder_art._state) goes to a temporary library, never the user's
        td = tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        env = mock.patch.dict("os.environ", {"REP_THEORY_ASSET_DIR": td.name}); env.start(); self.addCleanup(env.stop)

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
        self.assertEqual(len(got), 1); self.assertIn("The person is", got[0]["prompt"]); self.assertTrue(got[0]["refs"]); self.assertEqual(sc["kind"], "checklist")   # the scene stays a board
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

    def test_card_library(self):
        from reptheory import health as HE, health_lib as L, variety as V, direction as DR
        self.assertGreaterEqual(len(L.TOPICS), 100)
        T.set_theme("elder"); sc = {"start": 0.0, "end": 6.0, "words": [], "text": ""}; ctx = D.Ctx(480, 270)
        for tid in L.TOPICS:      # every topic builds and draws, from its first frame
            eng, p = L.forced(tid, dict(sc, text="x"), "x", V._at)
            for t in (0.0, 2.5):
                cv = ctx.backdrop(); before = cv.tobytes(); HE.draw(cv, ctx, eng, p, t, 0.0)
            self.assertNotEqual(cv.tobytes(), before, tid)
        ev = lambda txt: V.evidence(dict(sc, text=txt))
        self.assertEqual(ev("Statins lower your LDL cholesterol.")["meter"][1]["topic"], "ldl")
        self.assertNotIn("value", ev("Low vitamin D is common after seventy.")["meter"][1])   # an age is not a reading
        self.assertEqual(ev("Keep salt under one teaspoon a day.")["tube"][1]["value"], 1)
        self.assertEqual(ev("One in three adults over 65 falls each year.")["people"][1]["topic"], "people_older")
        self.assertEqual(ev("Walking cuts your stroke risk by 30 percent.")["risk"][1]["pct"], 30)
        f = ev("Eat more berries and salmon, and cut back on bacon.")["foods"][1]["items"]
        self.assertEqual([(i["topic"], i["bad"]) for i in f], [("berries", False), ("fish", False), ("processed_meat", True)])
        self.assertEqual(ev("Aim for seven thousand steps a day.")["walk"][1]["value"], 7000)
        self.assertEqual(ev("Lift light weights twice a week.")["weekly"][1]["n"], 2)
        self.assertEqual(ev("Breathe in for four, hold for seven, out for eight.")["breath"][1]["out"], 8)
        self.assertEqual(len(ev("Chest pain, shortness of breath and cold sweats mean call now.")["symptoms"][1]["items"]), 3)
        self.assertNotIn("symptoms", ev("A headache after a long day is normal."))   # one sign alone is not a warning-signs card
        d = ev("Walking after meals helps manage type 2 diabetes.")["disease"][1]; self.assertEqual((d["topic"], d["good"]), ("dz_diabetes", True))
        d = ev("Osteoarthritis slowly wears down the cartilage in your knees.")["disease"][1]; self.assertEqual((d["topic"], d["good"]), ("dz_osteoarthritis", False))
        self.assertEqual(ev("Rheumatoid arthritis is an autoimmune disease.")["disease"][1]["topic"], "dz_rheumatoid")   # the specific one before plain arthritis
        self.assertEqual(DR.norm_look("parkinsons"), ""); self.assertEqual(DR.norm_look("dz_parkinsons"), "disease")
        self.assertEqual(DR.norm_look("cholesterol"), "meter"); self.assertEqual(DR.norm_look("salmon"), "")
        self.assertEqual(DR.norm_look("fish"), "foods")
        T.set_theme("")
        self.assertEqual(DR.norm_look("cholesterol"), ""); self.assertEqual(HE.evidence(sc, "Statins lower your LDL cholesterol.", V._at), {})   # Rep Theory never gets them

    def test_picture_director(self):
        from reptheory import elder_art as EA, beat_art as BA
        T.set_theme("elder"); td0 = tempfile.TemporaryDirectory(); self.addCleanup(td0.cleanup)
        env = mock.patch.dict("os.environ", {"REP_THEORY_ASSET_DIR": td0.name}); env.start(); self.addCleanup(env.stop)
        S = ["Do your knees feel stiff in the morning?", "Walk for twenty minutes after dinner.", "Take your vitamin D with breakfast.", "Osteoarthritis wears down the cartilage in your knees.",
             "Plaque builds up in your arteries silently.", "Your kidneys filter your blood every minute.", "Call your grandchildren once a week.", "Call your grandchildren again tonight."]
        scenes = [{"no": i + 1, "text": t, "hook": i == 0} for i, t in enumerate(S)]
        host = EA.plan(scenes); self.assertIn(host, EA.cast())
        shots = [sc["elder_shot"] for sc in scenes]
        self.assertTrue(all(a != b or a == "organ" for a, b in zip(shots, shots[1:])), shots)   # never the same shot twice running
        ps = [EA.prompt(sc) for sc in scenes]
        for sc, p in zip(scenes, ps):
            if sc["elder_shot"] != "organ": self.assertIn(EA.person(host)["sheet"], p); self.assertEqual(EA.wants_refs(p), host); self.assertTrue(BA.wants_refs(p))
        self.assertIn("osteoarthritis", ps[3]); self.assertIn("plaque narrowing", ps[4]); self.assertIn("kidneys", ps[5]); self.assertFalse(BA.wants_refs(ps[5]))
        self.assertIn("pill organiser", ps[2]); self.assertIn("park path", ps[1])
        self.assertEqual(BA.art_id(ps[1]), BA.art_id(ps[1]))   # the id is known before the reference exists
        self.assertEqual(EA.person(EA.pick_host(["Menopause changes her bones."]))["sex"], "f")
        w = EA.pick_host(["Menopause changes her bones."]); self.assertIn(EA.person(w)["sheet"], EA.own_prompt("the older woman reading a food label", w))
        mine = set(EA.cast()); self.assertEqual(len(mine), 4); self.assertEqual(set(EA.cast()), mine)   # this install's cast is kept
        with mock.patch.object(EA, "_state", return_value={"seed": "another-install"}): self.assertFalse(set(EA.cast()) & mine)   # another user gets other people
        EA.set_per_video(True); a = EA.pick_host(["Walk every day."]); b = EA.pick_host(["Sleep seven hours."])
        self.assertNotIn(a, mine); self.assertNotEqual(a, b); self.assertEqual(a, EA.pick_host(["Walk every day."])); EA.set_per_video(False)   # per video: new, but the same script makes the same person
        made = []
        with tempfile.TemporaryDirectory() as td, mock.patch.object(EA, "host_refs", side_effect=lambda h: made[:]):
            def make_one(pr):
                made.append(str(Path(td) / "ref.png")); Image.new("RGB", (64, 64), "white").save(made[-1]); return made[-1]
            with mock.patch("reptheory.library.register"): self.assertEqual(EA.ensure_refs(host, make_one, log=lambda *a: None), made)
            self.assertIn("reference picture of " + EA.person(host)["name"], EA.ref_prompt(host))
            good = Path(td) / "good.png"; im = Image.new("RGB", (300, 200), "white"); ImageDraw.Draw(im).ellipse((180, 40, 280, 160), fill=(40, 120, 120)); im.save(good)
            room = Path(td) / "room.png"; Image.new("RGB", (300, 200), (150, 120, 90)).save(room)
            self.assertEqual(EA.check(good), []); self.assertEqual(set(EA.check(room)), {"background not plain white", "no empty side for the words"})
            self.assertTrue(EA.stronger("X.", EA.check(room)).startswith("The background must be plain"))
        with tempfile.TemporaryDirectory() as td2:      # the picture uploaded on the Elder page: checked, then the main person of every video, sent as the reference
            small = Path(td2) / "s.png"; Image.new("RGB", (100, 100), "white").save(small); self.assertIn("too small", EA.set_own_picture(str(small)))
            txt = Path(td2) / "x.png"; txt.write_text("no picture"); self.assertIn("not a picture", EA.set_own_picture(str(txt)))
            big = Path(td2) / "me.jpg"; Image.new("RGB", (600, 800), (200, 180, 160)).save(big); self.assertEqual(EA.set_own_picture(str(big)), "")
            EA.set_own_sex("m"); own = EA.pick_host(["Walk every day."]); self.assertTrue(own.startswith("own_"))
            sc0 = {"no": 1, "text": "Walk for twenty minutes after dinner.", "elder_host": own, "elder_shot": "wide"}; pr = EA.prompt(sc0)
            self.assertIn("exactly as in the reference picture", pr); self.assertEqual(EA.wants_refs(pr), own); self.assertEqual(EA.host_refs(own), [EA.own_picture()])
            self.assertNotIn(EA.person(host)["sheet"], pr)   # no random description fighting the photo
            EA.clear_own_picture(); self.assertIsNone(EA.own_picture()); self.assertFalse(EA.pick_host(["Walk every day."]).startswith("own_"))
        T.set_theme("")
        self.assertFalse(BA.wants_refs(ps[1]))   # outside the elder theme the host means nothing

    def test_picker_prompt_and_look(self):
        self.assertEqual(R.BUILT_ON[R.ELDER_THEORY], "Rep Theory")
        out = R.with_extras(("Rep Theory", "Health Cinema"))
        self.assertEqual(out[out.index("Carl Jung Theory") + 1], "Elder Health Theory")
        txt = A.prompt_text("My script.", cat="elder")
        self.assertIn("Elder Health Theory", txt); self.assertTrue(txt.rstrip().endswith("My script.")); self.assertNotIn("<<<PASTE", txt)
        self.assertEqual(DR.norm_look("board"), "checklist")


if __name__ == "__main__":
    unittest.main()
