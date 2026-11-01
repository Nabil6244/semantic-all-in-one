"""Rep Theory changes from the arm-wrestling study (docs/rep_theory/STUDY_tendons_arm_wrestling.md) and the 053 render audit (docs/rep_theory/AUDIT_2026-11-01_gyym.md).
Plan-level and drawing-level checks only: no render, no Flow, no network."""
from __future__ import annotations
import re, unittest

from PIL import Image

from reptheory import cadence as C, direction as DR, gate as G, lexicon as LX, library as L, poses as PO, states as ST, variety as V, picture as PIC, draw as D, scenes as S

def _sc(text, no=1, start=0.0, kind="callout", **kw):
    ws = [{"w": w, "t0": start + 0.35 * i, "t1": start + 0.35 * i + 0.3} for i, w in enumerate(text.split())]
    return dict({"no": no, "kind": kind, "start": start, "end": start + 0.35 * len(ws) + 0.5, "words": ws, "text": text, "pages": [], "decisions": [], "art": "", "section": "X", "topic": ""}, **kw)

class Cards(unittest.TestCase):
    def test_sentence_shapes(self):
        ev = lambda t: {k: v[1] for k, v in V.evidence(_sc(t)).items()}
        s = ev("Every match comes down to four moments. The go. The wrist. The squeeze. And the line.")["slots"]
        self.assertEqual([i["text"] for i in s["items"]], ["THE GO", "THE WRIST", "THE SQUEEZE", "THE LINE"]); self.assertEqual(s["title"], "4 MOMENTS")
        r = ev("Stiff tendons get it there fast. And in an arm wrestle, late loses.")["race"]; self.assertEqual((r["fast"]["text"], r["slow"]["text"]), ("STIFF TENDONS", "STRETCHY TENDONS"))
        f = ev("A stretchy tendon is like slack in a rope.")["formula"]; self.assertEqual((f["a"]["text"], f["sign"], f["b"]["text"]), ("STRETCHY TENDON", "=", "SLACK IN A ROPE"))
        self.assertIn("mechanism", ev("The muscle pulls on a tendon, and the tendon pulls on the bone."))
        p = ev("I'll show you what 8 out of 10 had in common.")["promise"]; self.assertEqual((p["n"], p["of"], p["label"]), (8, 10, "HAD IN COMMON"))

    def test_no_card_without_its_shape(self):
        for t in ("Sleep is when you grow.", "Eat more protein every day.", "Your forearm is a lever."):
            self.assertFalse({"slots", "race", "formula", "mechanism", "promise"} & set(V.evidence(_sc(t))), t)

    def test_cards_draw(self):
        ctx = D.Ctx(640, 360)
        for t in ("Every match comes down to four moments. The go. The wrist.", "Stiff tendons get it there fast. Late loses.", "A stretchy tendon is like slack in a rope.",
                  "The muscle pulls on a tendon, and the tendon pulls on the bone.", "I'll show you what 8 out of 10 had in common."):
            sc = _sc(t); ev = V.evidence(sc); k = next(x for x in ("slots", "race", "formula", "mechanism", "promise") if x in ev); sc[k] = ev[k][1]; sc["kind"] = k
            self.assertEqual(S.frame(ctx, sc, sc["end"] - 0.1, tag=False).size, (640, 360))
            self.assertTrue(any(e["meaningful"] for e in C.events([sc])), k)      # each card's parts are cadence events (and get sounds)

class Director(unittest.TestCase):
    def _plan(self, texts):
        scs, t = [], 0.0
        for i, x in enumerate(texts): sc = _sc(x, i + 1, t); scs.append(sc); t = sc["end"]
        return scs

    def test_opening_is_a_picture_even_when_the_csv_asks_for_words(self):
        scs = self._plan(["Training your tendons can make you win arm wrestles.", "They sit up in your forearm."]); scs[0].update(look="takeaway", directed_look=True)
        V.direct(scs, flow=True); self.assertEqual(scs[0]["look"], "flow"); self.assertTrue(scs[0].get("hook"))

    def test_no_picture_budget(self):
        scs = self._plan([f"The trainee lifts the {w} box onto the shelf." for w in ("red", "blue", "green", "grey", "black", "white", "tall", "small")])
        V.direct(scs, flow=True); self.assertGreaterEqual(sum(1 for sc in scs if sc["look"] == "flow"), 6)

    def test_plate_not_repeated_within_its_gap(self):
        scs = self._plan(["Your tendons carry the force to your fingers.", "Stiff tendons are fast.", "The tendons in your forearm matter."])
        for sc in scs: sc.update(kind="anatomy", art="anat_forearm_v1")
        V.direct(scs, flow=True); self.assertLessEqual(sum(1 for sc in scs if sc.get("look") in (None, "anatomy", "stock") and sc["kind"] == "anatomy"), 1)      # shown once, then other looks

    def test_long_scene_cut_at_sentence_ends(self):
        sc = _sc("The ref says go. The big guy folds. His wrist bends back. He loses the match. Everyone saw it happen.")
        scs = [sc]; self.assertGreaterEqual(V.split_long(scs), 1); self.assertTrue(all(x["end"] - x["start"] <= V.LONG_S + 1e-6 or len(x["words"]) < 6 for x in scs))

class Gate(unittest.TestCase):
    def test_repairs_opening_and_one_picture(self):
        scs = [_sc("Words first.", 1, 0, kind="callout")] + [_sc(f"Your forearm tendons matter here {i}.", i + 2, 2.0 + 3 * i, kind="anatomy", art="anat_forearm_v1") for i in range(5)]
        for sc in scs: sc["look"] = sc["kind"]
        res = G.repair(scs, flow=True); names = {p["check"] for p in res["before"]}
        self.assertIn("opening_text", names); self.assertIn("one_picture", names); self.assertEqual(res["after"], [])
        self.assertEqual(scs[0]["look"], "flow")

    def test_gate_is_plan_only_and_fast(self):
        import time
        scs = [_sc(f"Sentence number {i} about your grip.", i + 1, 3.0 * i) for i in range(400)]
        t0 = time.time(); G.repair(scs, flow=True); self.assertLess(time.time() - t0, 0.5)      # a long video's plan: well under a second, no render time

    def test_shipped_3d_groups_sit_on_their_limbs(self):
        self.assertEqual(G.bad_3d_groups(), set())      # the forearm flexors once included the leg's flexor digitorum longus and framed the thighs

class Fixes(unittest.TestCase):
    def test_hand_hanging_off_a_table_is_not_a_bar_hang(self):
        rx = re.compile(LX.CONCEPTS["hang"]["rx"], re.I)
        self.assertFalse(rx.search("with your hand hanging off the edge.")); self.assertTrue(rx.search("Hang from the bar with straight arms."))

    def test_run_pose_only_for_running(self):
        rx = PO.POSE_RX["rep_run_v1"]
        self.assertFalse(rx.search("the tendons that close your fingers run all the way from your forearm")); self.assertTrue(rx.search("go for a run three times a week"))

    def test_stop_the_clock_is_not_a_warning(self):
        self.assertFalse(ST.DANGER_RX.search("the moment your knuckles drop, stop the clock.")); self.assertTrue(ST.DANGER_RX.search("stop if it hurts"))

    def test_stopwatch_runs_from_hold_to_stop(self):
        scs = [_sc("Now curl your wrist up and hold it there.", 1, 0.0), _sc("The moment your knuckles drop, stop the clock.", 2, 4.0)]
        self.assertEqual(ST.stopwatch(scs), 1); sw = scs[1]["stopwatch"]; self.assertLess(sw["start"], sw["stop"]); self.assertEqual(scs[0]["stopwatch"], sw)

    def test_figure_regions_map_onto_the_cut_out(self):
        x0, y0, x1, y1 = L.crop_frac("rep_stand_v1"); self.assertLess(x1 - x0, 0.5)      # the cut-out is a narrow crop of a wide picture
        (cx, _cy, _w, _h), = L.to_cutout("rep_stand_v1", (ST.BODY["arms"][2][0],)); self.assertLess(cx, 0.3)      # the left arm sits at the cut-out's left edge, not mid-torso

    def test_on_screen_words_must_be_the_sentences_own(self):
        self.assertEqual(DR.on_screen_ok("stiff = fast", "Stiff tendons get it there fast."), "STIFF = FAST")
        self.assertEqual(DR.on_screen_ok("big bicep ≠ safe", "A big bicep can't save you."), "")

class Picture(unittest.TestCase):
    def test_same_picture_is_reframed(self):
        im = Image.new("RGB", (1376, 768), (0, 0, 0)); px = im.load()
        for x in range(300, 700):
            for y in range(200, 600): px[x, y] = (200, 200, 200) if x < 600 else (230, 40, 30)
        import tempfile; f = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name; im.save(f)
        orig = L.find; L.find = lambda ref: {"path": f} if ref == "PIC" else orig(ref)
        try:
            scs = [dict(_sc("Rest your forearm on the table.", 1, 0.0), kind="illus", art="PIC"), dict(_sc("Palm up, hand off the edge.", 2, 3.0), kind="illus", art="PIC")]
            self.assertEqual(PIC.plan(scs), 1); self.assertEqual(scs[0]["cam"]["mode"], "wide"); self.assertEqual(scs[1]["cam"]["mode"], "close")
            self.assertIsNotNone(scs[0]["cam"]["reveal_at"])      # the red part grows in on "forearm"
            ctx = D.Ctx(640, 360); a = S.frame(ctx, scs[0], 0.0, tag=False); b = S.frame(ctx, scs[0], 2.5, tag=False); self.assertNotEqual(a.tobytes(), b.tobytes())
        finally: L.find = orig

if __name__ == "__main__":
    unittest.main()
