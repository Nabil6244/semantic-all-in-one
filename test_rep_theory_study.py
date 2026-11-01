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
            self.assertEqual(PIC.plan(scs), 1); self.assertEqual(scs[0]["cam"]["mode"], "wide"); self.assertEqual(scs[1]["cam"]["mode"], "medium")      # a repeated picture is re-framed medium first, never straight to a close-up
            self.assertIsNotNone(scs[0]["cam"]["reveal_at"])      # the red part grows in on "forearm"
            ctx = D.Ctx(640, 360); a = S.frame(ctx, scs[0], 0.0, tag=False); b = S.frame(ctx, scs[0], 2.5, tag=False); self.assertNotEqual(a.tobytes(), b.tobytes())
        finally: L.find = orig

if __name__ == "__main__":
    unittest.main()


class Final2Fixes(unittest.TestCase):
    """docs/rep_theory/AUDIT_2026-11-01_final2.md: too much zoom, and the older overlays dropped on picture scenes."""
    def _pic(self, w=1376, h=768, top=150, red=True):
        im = Image.new("RGB", (w, h), (0, 0, 0)); px = im.load()
        for x in range(350, 1000):
            for y in range(top, h - 40): px[x, y] = (230, 40, 30) if (red and 600 < x < 700 and 300 < y < 450) else (190, 190, 190)
        import tempfile; f = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name; im.save(f); PIC._cache.pop(f, None); return f

    def test_zoom_keeps_most_of_the_picture_and_the_head(self):
        info = PIC.study(self._pic())
        for mode, least in (("wide", 0.80), ("medium", 0.62), ("close", 0.45)):
            for p in (0.0, 1.0):
                x0, y0, x1, y1 = PIC._window(info, {"mode": mode, "focus": info["subject"]}, p, 1920, 1080)
                self.assertGreaterEqual((x1 - x0) / info["size"][0], least, f"{mode} at {p}")
                if mode != "close": self.assertLessEqual(y0, info["top"] * info["size"][1], f"{mode} cut the head")

    def test_picture_is_framed_with_room_around_the_subject(self):
        f = self._pic(); orig = L.find; L.find = lambda ref: {"path": f} if ref == "P2" else orig(ref)
        try:
            sc = dict(_sc("The trainee rests his forearm on the table.", 1, 0.0), kind="illus", art="P2"); PIC.plan([sc]); info = PIC.study(f)
            for t in (0.0, sc["end"] - sc["start"]):
                S.frame(D.Ctx(960, 540), sc, t, tag=False); (x0, y0, x1, y1), (rx0, ry0, rx1, ry1) = sc["_shown"]; iw, ih = info["size"]; bx0, by0, bx1, by1 = info["bbox"]
                h = (by1 - by0) * ih * (ry1 - ry0) / (y1 - y0) / 540; top = ry0 + (by0 * ih - y0) * (ry1 - ry0) / (y1 - y0)
                self.assertLessEqual(h, 0.80); self.assertGreater(top, 540 * 0.04)      # render final 3: the subject filled 97-100% of the height and touched the edge
        finally: L.find = orig

    def test_glow_label_and_tint_are_drawn_on_pictures(self):
        f = self._pic(); orig = L.find; L.find = lambda ref: {"path": f} if ref == "P3" else orig(ref)
        try:
            base = dict(_sc("Rest your forearm on it.", 1, 0.0), kind="illus", art="P3"); PIC.plan([base])
            lit = dict(base, glows=[{"at": 0.3, "regions": [], "label": "FOREARMS"}], tint={"at": 0.2}); ctx = D.Ctx(960, 540)
            a = S.frame(ctx, dict(base), 1.4, tag=False); b = S.frame(ctx, lit, 1.4, tag=False)
            self.assertNotEqual(a.tobytes(), b.tobytes()); self.assertGreater(PIC.overlays(b.copy(), ctx, lit, 1.4), 0)
        finally: L.find = orig

    def test_slot_names_come_from_the_short_rows_that_follow(self):
        def sc(text, no, s0, s1): return dict(_sc(text, no, s0), end=s1)
        scs = [sc("Training makes you strong.", 1, 0, 2), sc("Every match comes down to four moments.", 2, 2, 4.5), sc("The go.", 3, 4.5, 5.3), sc("The wrist.", 4, 5.3, 6.1), sc("The squeeze.", 5, 6.1, 7.0), sc("And the line.", 6, 7.0, 8.0), sc("You have seen it happen in a match.", 7, 8.0, 10)]
        V.direct(scs, flow=True); s = next(x for x in scs if x["kind"] == "slots")
        self.assertEqual([i["text"] for i in s["slots"]["items"]], ["THE GO", "THE WRIST", "THE SQUEEZE", "THE LINE"]); self.assertGreaterEqual(s["end"], 8.0)      # it may borrow time from the next scene to finish (variety.let_cards_finish)

    def test_detectors_take_the_csv_sentences(self):
        ev = lambda t: V.evidence(_sc(t))
        self.assertIn("race", ev("Stiff tendons get it there fast.")); self.assertIn("race", ev("Whoever gets his force into the hand first takes the wrist."))
        self.assertIn("study", ev("Researchers watched 74 of them.")); self.assertEqual(ev("Researchers watched 74 of them.")["study"][1]["noun"], "")      # no invented noun
        self.assertIn("promise", ev("At the end, I'll tell you what your time means."))
        self.assertIn("checklist", ev("Every hold, how heavy, how long.")); self.assertEqual(ev("It's called Tendon Theory, and it's linked below.")["engage"][1]["kind"], "link")
        self.assertNotIn("race", ev("Sleep fast tonight.")); self.assertNotIn("study", ev("Researchers watched you."))

    def test_aligner_matches_contractions_and_spelled_numbers(self):
        from health_cinema import scenes_csv
        rows = [{"text": "Researchers watched seventy-four of them."}, {"text": "I'll show you what eight out of ten had in common."}, {"text": "It's called the plan."}]
        words = [(w, 0.4 * i, 0.4 * i + 0.3) for i, w in enumerate("researchers watched 74 of them ill show you what 8 out of 10 had in common it called the plan".split())]
        out, frac = scenes_csv.align_to_words(rows, words, 12.0)
        self.assertEqual([r["words"][0]["w"] for r in out], ["researchers", "ill", "it"]); self.assertGreater(frac, 0.95)

    def test_csv_log_names_what_each_card_needs(self):
        self.assertTrue(all(k in DR.NEEDS for k in DR.CARDS))

    def test_chip_alone_becomes_the_headline(self):
        from reptheory import planner as P
        sc = _sc("Every hold, how heavy, how long."); sc["pages"] = [{"at": 0.1, "headline": "", "value": "", "chips": [{"text": "HOW HEAVY", "at": 0.6}], "kicker": ""}]
        P.never_empty([sc]); self.assertEqual(sc["pages"][0]["headline"], "HOW HEAVY")


class Final3Fixes(unittest.TestCase):
    """docs/rep_theory/AUDIT_2026-11-01_final3.md, checked on my own preview render."""
    def test_vague_line_reuses_the_neighbouring_picture(self):
        def sc(t, no, s0, s1, **kw): return dict(_sc(t, no, s0), end=s1, section="TEST", **kw)
        scs = [sc("Researchers watched 74 of them.", 1, 0, 3), sc("But first, a quick test.", 2, 3, 5), sc("Sit at a table.", 3, 5, 7, directed_look=True, look="flow", flow_prompt="the trainee seated at a table")]
        V.direct(scs, flow=True); self.assertEqual(scs[1].get("flow_prompt"), "the trainee seated at a table")
        own = [sc("Researchers watched 74 of them.", 1, 0, 3), sc("Grip the towel with both hands.", 2, 3, 5), sc("Sit at a table.", 3, 5, 7, directed_look=True, look="flow", flow_prompt="the trainee seated at a table")]
        V.direct(own, flow=True); self.assertNotEqual(own[1].get("flow_prompt"), "the trainee seated at a table")      # a line with its own object gets its own picture

    def test_no_stamp_on_a_card_that_spells_its_words(self):
        for k in ("slots", "race", "checklist", "promise"): self.assertIn(k, ST.NO_STAMP)

    def test_card_check_falls_back_to_the_transcript_words(self):
        sc = _sc("and if you want every tendon trained we wrote it all into a 12 week plan."); sc["script_text"] = "And if you want every tendon trained, we wrote it all into a twelve-week plan."
        rows = [{"text": sc["script_text"], "start": 0.0, "end": sc["end"], "look": "stat"}]; sc["words"] = sc["words"]
        DR.apply([sc], rows); self.assertEqual(sc.get("look"), "stat")      # the CSV's "twelve-week" is not read as a number, the transcript's "12 week" is
