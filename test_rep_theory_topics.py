"""Rep Theory on topics it was not built around (reptheory/topic_eval.py, docs/rep_theory/UPGRADE_LIST.md section 0). 13 scripts on different topics are planned and measured; the
numbers may only get better than the recorded baseline (test_fixtures/rep_theory_topics/baseline.json), never worse. After an improvement, record it with
`python -m reptheory.topic_eval --write-baseline`. No render, no Flow call, no network."""
from __future__ import annotations
import json, unittest

from reptheory import beats as B, narrative as N, planner as P, topic_eval as T

TOL = 0.005
HIGHER = ("picture_share_mean", "picture_share_min", "looks_mean")
LOWER = ("fallback_share_mean", "fallback_share_max", "anatomy_unnamed_total", "still_share_mean", "held_no_change_total", "opening_overlap_max", "opening_overlap_mean", "bad_headlines_total", "empty_scenes_total", "repeat_headlines_total")

class NewTopics(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = T.run(); cls.base = json.loads(T.BASELINE.read_text())

    def test_the_set_covers_many_topics(self):
        per = self.r["per_script"]; self.assertGreaterEqual(len(per), 13)
        self.assertEqual(len({m["title"] for m in per.values()}), len(per), "every script is a different topic")
        for k, m in per.items(): self.assertGreater(m["scenes"], 3, k)

    def test_no_worse_than_the_baseline(self):
        a = self.r["aggregate"]
        for k in HIGHER: self.assertGreaterEqual(a[k], self.base[k] - TOL, f"{k} fell from {self.base[k]} to {a[k]}")
        for k in LOWER: self.assertLessEqual(a[k], self.base[k] + TOL, f"{k} rose from {self.base[k]} to {a[k]}")

    def test_no_reference_video_constants_in_code(self):
        self.assertEqual(self.r["aggregate"]["reference_strings"], [], "values from the studied reference video must come from the script, not the code")

    def test_body_part_check_needs_a_named_part(self):
        for s in ("Your hamstrings take the load.", "Keep your shoulder blades down.", "It helps your brain."): self.assertTrue(T.BODY_RX.search(s), s)
        for s in ("Muscle is built from it.", "Muscle grows when you rest.", "Your body adapts."): self.assertFalse(T.BODY_RX.search(s), s)

    def test_timings_follow_the_script(self):
        title, ss = T.sentences("Title: A test\nFirst line here. Second one!\nThird?")
        self.assertEqual(title, "A test"); self.assertEqual([s["text"] for s in ss], ["First line here.", "Second one!", "Third?"])
        self.assertTrue(all(a["end"] <= b["start"] for a, b in zip(ss, ss[1:])))

class Step0Bugs(unittest.TestCase):
    """The render-046 faults (UPGRADE_LIST.md section 2), as rules on any script."""
    def _ws(self, script, transcript=None):
        toks = (transcript or script).split(); return P.respell(script, [{"w": w, "t0": i * 0.4, "t1": i * 0.4 + 0.3} for i, w in enumerate(toks)])

    def test_script_spelling_on_transcript_words(self):
        ws = self._ws("You can't spot-reduce fat, they're wrong.", "you cant spot-reduce fat theyre wrong")
        self.assertEqual([w["w"] for w in ws], ["you", "can't", "spot-reduce", "fat", "they're", "wrong"]); self.assertEqual(ws[3]["p"], ","); self.assertEqual(ws[1]["t0"], 0.4)

    def test_headlines_are_phrases(self):
        ws = self._ws("Lifting the same weight for six months gives you the same body for six months.")
        self.assertEqual(N.phrase("SIX MONTHS GIVES", ws), "SIX MONTHS")
        ws = self._ws("Lift with purpose, eat with intention, sleep like it matters.")
        self.assertNotEqual(N.phrase("INTENTION SLEEP", ws), "INTENTION SLEEP")
        ws = self._ws("Rule five is that consistency beats intensity.")
        self.assertEqual(N.phrase("THAT CONSISTENCY BEATS INTENSITY", ws), "CONSISTENCY BEATS INTENSITY")
        ws = self._ws("Three solid sessions a week will outperform six brutal weeks followed by quitting.")
        self.assertEqual(N.phrase("OUTPERFORM SIX BRUTAL", ws), "")
        ws = self._ws("Move one way, then side to side.")
        self.assertEqual(N.phrase("SIDE SIDE", ws), "")

    def test_muscle_alone_is_no_body_part(self):
        for text, anat in (("Either way, get enough protein, because muscle is built from it.", False), ("Your forearms burn after a minute.", True)):
            kinds = [sc["kind"] for sc in B.plan([{"text": text, "start": 0.0, "end": 4.0}], art_ok=lambda a: True)["scenes"]]
            self.assertEqual("anatomy" in kinds, anat, text)

    def test_never_an_empty_scene(self):
        mk = lambda no, words: {"no": no, "kind": "callout", "start": no * 3.0, "end": no * 3.0 + 3, "decisions": [], "words": self._ws(words),
                                "pages": [{"at": no * 3.0, "headline": "", "headline_at": 0, "value": "", "chips": [], "kicker": ""}]}
        out = P.never_empty([dict(mk(0, "Start here."), pages=[{"at": 0, "headline": "START", "headline_at": 0, "value": "", "chips": [], "kicker": ""}]), mk(1, "Eat slightly above."), mk(2, "so")])
        self.assertEqual(out[1]["pages"][0]["headline"], "EAT SLIGHTLY ABOVE"); self.assertEqual(len(out), 2); self.assertEqual(out[1]["end"], 9.0)

    def test_step0_targets_hold_on_every_topic(self):
        a = T.run()["aggregate"]
        for k in ("bad_headlines_total", "empty_scenes_total", "repeat_headlines_total", "anatomy_unnamed_total"): self.assertEqual(a[k], 0, k)

class Step1Sound(unittest.TestCase):
    def test_every_topic_gets_spaced_sounds_on_its_own_events(self):
        from reptheory import sound as SND
        for k, t in T.scripts().items():
            *_, scenes = T.plan(t); cs = SND.cues(scenes); dur = scenes[-1]["end"]
            self.assertGreaterEqual(60 * len(cs) / dur, 15, k); self.assertTrue(any(c["sfx"] == "soft_transition" for c in cs), k)
            for a, b in zip(cs, cs[1:]): self.assertGreaterEqual(b["t"] - a["t"], SND.MIN_GAP_S - 1e-6, k)
            for c in cs: self.assertLessEqual(sum(1 for x in cs if 0 <= c["t"] - x["t"] < SND.WINDOW_S), SND.MAX_PER_WINDOW + 1, k)

class Step2Motion(unittest.TestCase):
    def test_a_text_scene_keeps_moving_and_scenes_hand_over_by_focus(self):
        from PIL import ImageChops, ImageStat
        from reptheory import draw as D, scenes as S
        *_, scenes = T.plan(T.scripts()["08_hydration"]); ctx = D.Ctx(640, 360); sc = next(x for x in scenes if x["kind"] == "callout" and x["end"] - x["start"] > 4)
        a, b = S.frame(ctx, sc, 3.0), S.frame(ctx, sc, 3.5)      # well after every entrance: only the camera moves
        self.assertEqual(a.size, (640, 360)); self.assertGreater(ImageStat.Stat(ImageChops.difference(a, b).convert("L")).mean[0], 0.3)
        mid = S.transition(a, b, 0.5, ctx); edge = lambda im: ImageStat.Stat(im.convert("L").filter(__import__("PIL.ImageFilter", fromlist=["x"]).FIND_EDGES)).mean[0]
        self.assertLess(edge(mid), 0.6 * edge(a), "half way through a hand-over the frame is out of focus")

class States5b(unittest.TestCase):
    def test_named_parts_light_up_and_warnings_tint(self):
        from reptheory import states as ST
        ws = lambda text: [{"w": w, "t0": i * 0.5, "t1": i * 0.5 + 0.4} for i, w in enumerate(text.lower().split())]
        t = "Your hamstrings and your calves take the load."; self.assertEqual([p for p, _ in ST.parts_named(ws(t), t)], ["legs", "calves"])
        t = "Come back to it next week."; self.assertEqual(ST.parts_named(ws(t), t), [])
        sc = [{"kind": "callout", "art": "", "text": "The most common mistake is letting your hips sag.", "start": 0.0, "end": 4.0, "decisions": []}]; sc[0]["words"] = ws(sc[0]["text"])
        ST.apply(sc, lambda a: True); self.assertEqual((sc[0]["kind"], sc[0]["glows"][0]["label"]), ("trainee", "HIPS")); self.assertAlmostEqual(sc[0]["tint"]["at"], 1.5)
        sc = [{"kind": "callout", "art": "", "text": "Eat enough protein every day.", "start": 0.0, "end": 3.0, "decisions": []}]; sc[0]["words"] = ws(sc[0]["text"])
        ST.apply(sc, lambda a: True); self.assertEqual(sc[0]["kind"], "callout"); self.assertNotIn("tint", sc[0])

class Step3Cadence(unittest.TestCase):
    def test_a_long_text_scene_gets_its_next_phrase_at_its_word(self):
        from reptheory import states as ST
        text = "Everyone tells you to eat more protein, but nobody tells you how much. Too little and your training is wasted."
        ws = P.respell(text, [{"w": w, "t0": i * 0.42, "t1": i * 0.42 + 0.35} for i, w in enumerate(text.split())])
        sc = {"kind": "callout", "start": 0.0, "end": len(ws) * 0.42, "words": ws, "text": text, "decisions": [], "pages": [{"at": 0.0, "headline": "EAT MORE PROTEIN", "headline_at": 0.2, "value": "", "chips": [], "kicker": ""}]}
        self.assertGreaterEqual(ST.develop([sc]), 1); heads = [p["headline"] for p in sc["pages"]]
        self.assertTrue(set(heads[1:]) & {"NOBODY TELLS YOU HOW MUCH", "TRAINING IS WASTED"}, heads)
        for a, b in zip(sc["pages"], sc["pages"][1:]): self.assertLessEqual(b["at"] - a["at"], 6.0)

class Rule3Memory(unittest.TestCase):
    def test_recent_videos_steer_the_next_opening_and_are_remembered(self):
        import tempfile, os
        from reptheory import engine as E, states as ST, variety as V
        title, ss = T.sentences(T.scripts()["05_grip"])
        def opening(recent):
            sc = B.plan(T.transcript_words(ss), title=title, art_ok=T.art_ok)["scenes"]; ST.apply(sc, T.art_ok); V.direct(sc, total_s=sc[-1]["end"], recent=recent); return sc
        a = opening([]); la = [T.look_of(x) for x in a if x["start"] < 60]
        self.assertEqual(la, [T.look_of(x) for x in opening([]) if x["start"] < 60], "same script, same video")
        self.assertLessEqual(T.overlap(la, [T.look_of(x) for x in opening([la] * 3) if x["start"] < 60]), 0.5)
        with tempfile.TemporaryDirectory() as d:
            proj = os.path.join(d, "Video_001"); os.mkdir(proj); E.remember_opening(proj, a, title); self.assertEqual(len(E.recent_openings(os.path.join(d, "Video_002"))), 1)

class Step4Cards(unittest.TestCase):
    def test_each_card_needs_its_sentence_shape(self):
        from reptheory import variety as V
        sc = {"start": 0.0, "words": []}
        tl = V._timeline(sc, "10 seconds in, your legs start to burn. 20 seconds, your hands shake. 30, everything wants to stop.")
        self.assertEqual([i["mark"] for i in tl["items"]], ["10S", "20S", "30S"])
        self.assertIsNone(V._timeline(sc, "Week one, run for one minute, then walk for two minutes."), "a schedule is not a timeline of what you feel")
        mk = V._mistake(sc, "The biggest mistake is eating too little protein. Keep a portion at every meal.")
        self.assertEqual((mk["wrong"]["text"], mk["right"]["text"]), ("EATING TOO LITTLE PROTEIN", "KEEP A PORTION AT EVERY MEAL"))
        sl = V._slider(sc, "Too hard? Do it against a wall. Too easy? Add a backpack.")
        self.assertEqual((sl["easier"]["text"], sl["harder"]["text"]), ("DO IT AGAINST A WALL", "ADD A BACKPACK"))
        self.assertEqual(V._dial(sc, "Run at a 6 out of 10 effort.")["value"], 6.0)
        self.assertEqual((V._study(sc, "A study of 140 runners found less pain.")["value"], V._study(sc, "A study of 140 runners found less pain.")["noun"]), (140.0, "RUNNERS"))
        for t in ("Sleep seven to nine hours.", "Drink water before training.", "Protein keeps you full."):
            self.assertFalse(any(f(sc, t) for f in (V._timeline, V._mistake, V._slider, V._dial, V._study)), t)

class Step4MoreCards(unittest.TestCase):
    def test_each_new_card_needs_its_sentence_shape(self):
        from reptheory import variety as V
        sc = {"start": 0.0, "words": []}
        self.assertEqual([s["dir"] for s in V._graph(sc, "Your strength drops for a week, then climbs past where it was.")["segs"]], ["down", "up"])
        self.assertEqual((V._bars(sc, "About 1 in 3 adults sleep too little.")["lit"], V._bars(sc, "About 1 in 3 adults sleep too little.")["of"]), (1.0, 3.0))
        self.assertEqual([d["day"] for d in V._calendar(sc, "Run three days a week with a rest day between.")["days"]], [0, 2, 4])
        self.assertEqual([x["mark"] for x in V._result(sc, "Under 20 seconds, you are a beginner. 20 to 40 seconds, you are solid. Over 40, you are strong.")["tiers"]], ["UNDER 20S", "20-40S", "40+"])
        self.assertEqual(V._warning(sc, "If it hurts to press on the bone, take a few days off.")["rules"][0]["text"], "TAKE A FEW DAYS OFF")
        self.assertEqual(V._engage(sc, "Comment your best time below.")["kind"], "comment")
        for t in ("Sleep seven to nine hours.", "Your body rises a couple of centimeters.", "Start today, not Monday.", "Protein keeps you full.", "Eat slightly under what you burn."):
            self.assertFalse(any(f(sc, t) for f in (V._graph, V._bars, V._calendar, V._result, V._warning, V._engage)), t)

    def test_new_cards_draw(self):
        from PIL import Image
        from reptheory import cards as K, draw as D, variety as V
        sc = {"start": 0.0, "words": []}; ctx = D.Ctx(640, 360)
        for name, p in (("graph", V._graph(sc, "Your strength drops for a week, then climbs.")), ("bars", V._bars(sc, "1 in 4 adults.")), ("calendar", V._calendar(sc, "Train 4 days a week.")),
                        ("result", V._result(sc, "Under 10 reps, start easy. 10 to 20, keep going. Over 20, add weight.")), ("warning", V._warning(sc, "Stop if you feel sharp pain.")),
                        ("engage", V._engage(sc, "Subscribe for more.")), ("engage", V._engage(sc, "Comment your time."))):
            cv = Image.new("RGB", (640, 360)); getattr(K, name)(cv, ctx, p, 3.0); self.assertGreater(max(cv.convert("L").getextrema()), 100, name)

class Step2StampsAndBlueprint(unittest.TestCase):
    def test_short_emphatic_sentences_are_stamped_not_signposts(self):
        from reptheory import states as ST
        def scene(text):
            ws = P.respell(text, [{"w": w, "t0": i * 0.4, "t1": i * 0.4 + 0.3} for i, w in enumerate(text.split())])
            return {"kind": "callout", "start": 0.0, "end": len(ws) * 0.4, "words": ws, "text": text, "decisions": [], "pages": []}
        a = scene("Most people quit too early. Be patient. It works."); ST.stamps([a]); self.assertEqual(a["stamp"]["text"], "BE PATIENT")
        b = scene("Here are three moves to try today. Part one, chin tucks."); ST.stamps([b]); self.assertNotIn("stamp", b)

    def test_units_get_a_next_teaser_and_only_real_slots(self):
        from reptheory import blueprint as BP
        mk = lambda s, a, b: {"section": s, "topic": "T", "start": a, "end": b, "kind": "callout", "text": "", "decisions": [], "pages": []}
        sc = [mk("T", 0, 5), mk("MOVE 1", 5, 10), mk("MOVE 1", 10, 15), mk("MOVE 2", 15, 20)]
        n = BP.apply(sc); self.assertEqual((n["units"], n["teasers"], n["locks"], n["safety_chips"]), (2, 1, 0, 0)); self.assertEqual(sc[2]["teaser"]["text"], "MOVE 2")

if __name__ == "__main__":
    unittest.main()
