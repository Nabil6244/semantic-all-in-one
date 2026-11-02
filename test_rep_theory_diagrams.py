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

    def test_frame_up_before_first_word(self):      # first render: the split circle sat on a blank screen until "strength"
        ctx = D.Ctx(640, 360)
        for kind in ("split", "gap", "panels", "tearoff", "road"):
            text = "So, after all of this, " + CASES[kind][0].lower() + CASES[kind][1:]; sc = scene(text); c = DG.evidence(sc, text)[kind][1]
            self.assertGreater(c["at"] - sc["start"], 1.0, kind)
            cv = Image.new("RGB", (640, 360)); DG.draw(cv, ctx, kind, c, sc["start"] + 0.5); self.assertIsNotNone(cv.getbbox(), kind)

    def test_draws_at_every_moment(self):
        ctx = D.Ctx(640, 360)
        for kind, text in CASES.items():
            sc = scene(text); c = DG.evidence(sc, text)[kind][1]
            for t in (sc["start"] - 0.5, sc["start"] + 0.4, c["marks"][-1], K.CARD_DONE[kind](c) + 1):
                cv = Image.new("RGB", (640, 360)); DG.draw(cv, ctx, kind, c, t)


if __name__ == "__main__":
    unittest.main()


class JoinAndCut(unittest.TestCase):      # found in the first 1-minute render, 2026-11-02
    def test_comma_split_sentence_joined_for_its_diagram(self):
        a = scene("Some people get it in a few months,", 0.0); b = scene("others take one to two years, some never.", a["end"]); ss = [a, b]
        self.assertEqual(V.join_for_diagrams(ss), 1); self.assertEqual(len(ss), 1); self.assertEqual(len(DG.tearoff(ss[0], ss[0]["text"])["pages"]), 3)
        a = scene("Hold the bar,", 0.0); b = scene("then pull.", a["end"]); ss = [a, b]; self.assertEqual(V.join_for_diagrams(ss), 0)

    def test_question_starts_its_own_scene(self):
        text = "This is the road to your first free handstand. Question one: do I need a wall?"; ws = []
        for i, w in enumerate(text.split()): ws.append({"w": w.rstrip(".?:"), "p": w[-1] if w[-1] in ".?:" else "", "t0": i * 0.35})
        sc = {"text": text, "words": ws, "start": 0.0, "end": len(ws) * 0.35 + 0.5, "kind": "callout", "pages": [], "decisions": [], "no": 1}; ss = [sc]
        V.split_for_cards(ss); self.assertEqual(len(ss), 2); self.assertTrue(ss[1]["text"].lower().startswith("question one"))


class GateKeepsCards(unittest.TestCase):      # 1-minute render: the quality gate replaced the plan clipboard because it still carried the figure's art name
    def test_one_picture_ignores_cards(self):
        from reptheory import gate as G
        ss = []
        for i in range(6):
            sc = scene("Your plan: warm up, two holds, push-ups." if i == 3 else "Your shoulders do the work here.", start=i * 4.0); sc["no"] = i + 1; sc["art"] = "rep_stand_v1"
            sc["kind"], sc["look"] = ("clipboard", "clipboard") if i == 3 else ("trainee", "stock"); ss.append(sc)
        G.repair(ss, flow=True); self.assertEqual(ss[3]["kind"], "clipboard"); self.assertNotEqual(ss[3].get("look"), "flow")


class StrongDiagramBeatsFigure(unittest.TestCase):
    def test_lit_figure_never_beats_a_full_diagram(self):
        for k in range(12):      # every script seed: the variety nudge must never flip it
            pre = [scene(f"Filler line number {k} {i} about training.", start=i * 3.0) for i in range(3)]
            sc = scene("Your plan: wrist warm-up, two wall holds, three kick-ups.", start=9.0); sc["kind"] = "trainee"; sc["art"] = "rep_stand_v1"; sc["glows"] = [{"at": 9.3, "label": "WRIST", "regions": []}]
            ss = pre + [sc, scene(f"And that is all for today {k}.", start=14.0)]      # not the last scene (the closing key line has its own rule)
            for i, x in enumerate(ss): x["no"] = i + 1
            V.direct(ss, total_s=ss[-1]["end"], three_d=False, flow=False)
            self.assertEqual(ss[-2]["kind"], "clipboard", k)
