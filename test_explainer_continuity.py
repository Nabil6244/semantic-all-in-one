"""Scene, cast and environment continuity (explainer/director/scene_registry.py): deterministic, opt-in, and a no-op when off."""
import itertools
import json
import tempfile
import unittest
from types import SimpleNamespace as NS

from explainer.director import scene_registry as SR
from explainer.director.options import DirectorOptions


def toks(text):
    return text.lower().replace(",", "").replace(".", "").split()


def beat(i, start, end):
    return NS(id=f"e{i}", start=start, end=end)


def plan(reg, i, start, text, end=None, **kw):
    kw.setdefault("scenes2", True)
    return SR.plan_cartoon(reg, beat(i, start, end if end is not None else start + 5.0), toks(text), n_words=len(toks(text)), **kw)


class Decide(unittest.TestCase):
    def test_same_place_continues_and_a_new_place_resets(self):
        r = SR.SceneRegistry()
        a = plan(r, 1, 0.0, "Napoleon walked into the town square with his officers")
        b = plan(r, 2, 5.5, "the crowd in the square cheered Napoleon again")
        c = plan(r, 3, 11.0, "then the ships left the harbour for egypt")
        self.assertFalse(a["continued"])
        self.assertTrue(b["continued"])
        self.assertEqual((a["scene"], b["scene"]), ("old_town", "old_town"))
        self.assertEqual(a["cast"][0], b["cast"][0])
        self.assertFalse(c["continued"])
        self.assertEqual(c["scene"], "harbour")

    def test_time_or_place_change_words_and_gaps_reset(self):
        for text in ("meanwhile in the square the people waited", "years later the square was empty", "the next day the square was quiet", "back in the square napoleon waited"):
            r = SR.SceneRegistry()
            plan(r, 1, 0.0, "Napoleon walked into the town square")
            self.assertFalse(plan(r, 2, 5.5, text)["continued"], text)
        r = SR.SceneRegistry()
        plan(r, 1, 0.0, "Napoleon walked into the town square")
        self.assertFalse(plan(r, 2, 20.0, "napoleon crossed the square")["continued"])

    def test_beat_without_a_scene_word_keeps_the_place(self):
        r = SR.SceneRegistry()
        a = plan(r, 1, 0.0, "Napoleon walked into the town square")
        b = plan(r, 2, 5.5, "he looked at the people around him and smiled")
        self.assertTrue(b["continued"])
        self.assertEqual(b["scene"], a["scene"])

    def test_light_changes_without_rebuilding_the_scene(self):
        r = SR.SceneRegistry()
        a = plan(r, 1, 0.0, "Napoleon walked into the town square")
        b = plan(r, 2, 5.5, "by evening the square was still full")
        self.assertEqual((a["light"], b["light"]), ("day", "dusk"))
        self.assertTrue(b["continued"])
        self.assertEqual((a["scene"], a["cast"]), (b["scene"], b["cast"]))
        c = plan(r, 3, 11.0, "the people stayed in the square")
        self.assertEqual(c["light"], "dusk")                 # the light is remembered
        d = plan(r, 4, 16.5, "next morning is not a restart but the square fills again", end=21.0)
        self.assertIn(d["light"], ("day", "dusk"))

    def test_object_state_is_kept_and_can_be_removed(self):
        r = SR.SceneRegistry()
        a = plan(r, 1, 0.0, "Napoleon walked into the town square and read a letter")
        self.assertEqual(a["props"], ["letter"])
        b = plan(r, 2, 5.5, "the people in the square listened closely")
        self.assertEqual(b["props"], ["letter"])             # stays
        c = plan(r, 3, 11.0, "then the letter was burned in the square")
        self.assertEqual(c["props"], [])                     # the narration removes it
        d = plan(r, 4, 16.5, "a coin rolled across the square")
        self.assertEqual(d["props"], ["coin_stack"])         # a new prop is added

    def test_new_person_joins_the_cast(self):
        r = SR.SceneRegistry()
        a = plan(r, 1, 0.0, "Napoleon walked into the town square")
        b = plan(r, 2, 5.5, "a merchant in the square greeted him")
        self.assertTrue(b["continued"])
        self.assertEqual(b["cast"][0], a["cast"][0])
        self.assertIn("merchant", [t for _x, t in b["cast"]])

    def test_repetition_picks_an_alternative_composition(self):
        r = SR.SceneRegistry()
        a = plan(r, 1, 0.0, "Napoleon walked into the town square")
        b = plan(r, 2, 5.5, "Napoleon stood in the town square")
        self.assertTrue(b["continued"] or b["scene"] != a["scene"])
        self.assertNotEqual(a["ident"], b["ident"], "the same composition must not be repeated")
        seen = {a["ident"], b["ident"]}
        for k in range(3, 9):
            p = plan(r, k, 5.5 * (k - 1), "Napoleon stood in the town square")
            seen.add(p["ident"])
        self.assertGreater(len(seen), 3)

    def test_scene_run_cap_prefers_another_valid_set(self):
        r = SR.SceneRegistry()
        out = [plan(r, k, 5.5 * (k - 1), "the army marched across the field near the village") for k in range(1, 8)]
        scenes = [p["scene"] for p in out]
        longest = max(len(list(g)) for _k, g in itertools.groupby(scenes))
        self.assertLessEqual(longest, SR.MAX_SCENE_RUN)
        self.assertGreater(len(set(scenes)), 1)

    def test_deterministic_and_serialisable(self):
        def go():
            r = SR.SceneRegistry()
            texts = ["Napoleon walked into the town square", "by evening the square was full", "meanwhile the ships left the harbour", "a sailor waved from the harbour"]
            return [plan(r, k + 1, 5.5 * k, t) for k, t in enumerate(texts)], r.to_dict()
        a, b = go(), go()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        r = SR.SceneRegistry()
        r.note_board("b1", 0, 3, ["line"])
        self.assertEqual(r.to_dict()["boards"], 1)


class Authoring(unittest.TestCase):
    def test_a_continued_beat_draws_the_same_set_and_cast_with_the_new_light(self):
        from explainer.director.compose_cartoon import author_cartoon, continuity_plan
        text = "napoleon walked into the town square with the officers by evening the square was full of the people and the officers watched napoleon"
        words = [(w, 0.5 + 0.35 * i, 0.5 + 0.35 * i + 0.3) for i, w in enumerate(text.split())]
        half = 9
        t_mid = words[half][1] - 0.01
        opt = DirectorOptions(scenes2=True, continuity=True)
        reg = SR.SceneRegistry()
        out = []
        for i, (s, e) in enumerate([(0.0, t_mid), (t_mid, words[-1][2] + 0.3)]):
            b = NS(id=f"e{i}", start=s, end=e, sents=[], scene_hint=None)
            from explainer.director.segment import Sent
            gi = [g for g, w in enumerate(words) if s - 1e-6 <= w[1] < e - 1e-6]
            b.sents = [Sent(0, s, e, "x", True, gi)]
            p = continuity_plan(reg, b, words, opt, {}, i)
            out.append((p, author_cartoon(b.id, s, e, b.sents, words, {}, opt, {}, {}, variant=i, plan=p)))
        sets = [[c.params for c in br.cues if (c.params or {}).get("style") == "set"][0] for _p, br in out]
        figs = [[(c.params["cast"], c.pos[0]) for c in br.cues if (c.params or {}).get("style") == "figure"] for _p, br in out]
        self.assertEqual(sets[0]["set"], sets[1]["set"])
        self.assertEqual((sets[0]["tod"], sets[1]["tod"]), ("day", "dusk"))
        self.assertEqual(figs[0][:1], figs[1][:1])

    def test_body_stays_put_across_pose_changes_of_continued_beats(self):
        from explainer.director.compose_cartoon import author_cartoon, continuity_plan
        from explainer.director.segment import Sent
        from explainer.board import styles as ST
        text = "napoleon walked into the town square with the officers by evening the square was full of the people and the officers watched napoleon"
        words = [(w, 0.5 + 0.35 * i, 0.5 + 0.35 * i + 0.3) for i, w in enumerate(text.split())]
        t_mid = words[9][1] - 0.01
        opt, reg, origins = DirectorOptions(scenes2=True, continuity=True), SR.SceneRegistry(), []
        for i, (s, e) in enumerate([(0.0, t_mid), (t_mid, words[-1][2] + 0.3)]):
            b = NS(id=f"e{i}", start=s, end=e, scene_hint=None)
            b.sents = [Sent(0, s, e, "x", True, [g for g, w in enumerate(words) if s - 1e-6 <= w[1] < e - 1e-6])]
            br = author_cartoon(b.id, s, e, b.sents, words, {}, opt, {}, {}, variant=i, plan=continuity_plan(reg, b, words, opt, {}, i))
            o = {}
            for c in br.cues:
                if (c.params or {}).get("style") == "figure":                 # where the sprite's canvas origin lands = the body's ground position
                    o[c.params["cast"]] = c.pos[0] - ST.measure_cartoon("figure", c.params)["ox"]
            origins.append(o)
        poses = {c.params["pose"] for c in br.cues if (c.params or {}).get("style") == "figure"}
        for t in set(origins[0]) & set(origins[1]):
            self.assertEqual(origins[0][t], origins[1][t], t)

    def test_no_plan_is_the_old_authoring(self):
        from explainer.director.compose_cartoon import author_cartoon
        from explainer.director.segment import Sent
        text = "the farmers worked the field all day and the village grew rich from the harvest"
        words = [(w, 0.5 + 0.3 * i, 0.5 + 0.3 * i + 0.25) for i, w in enumerate(text.split())]
        sents = [Sent(0, 0.0, 6.0, text, True, list(range(len(words))))]
        a = author_cartoon("t", 0.0, 6.0, sents, words, {}, DirectorOptions(), {}, {}, variant=1)
        b = author_cartoon("t", 0.0, 6.0, sents, words, {}, DirectorOptions(), {}, {}, variant=1, plan=None)
        c = author_cartoon("t", 0.0, 6.0, sents, words, {}, DirectorOptions(), {}, {}, variant=1, plan={})
        keys = lambda br: [(x.id, x.kind, x.pos, json.dumps(x.params, sort_keys=True, default=str)) for x in br.cues]
        self.assertEqual(keys(a), keys(b))
        self.assertEqual(keys(a), keys(c))


class Director(unittest.TestCase):
    SCRIPT = ("Napoleon walked into the town square with his officers. The people in the square cheered him. By evening the square was still full of people. "
              "Then the ships left the harbour for Egypt. The sailors loaded the ships at the harbour. The army marched across the field to the battle.")

    def _run(self, **kw):
        from explainer.spike.test_director_real_material import synth
        from explainer.director.plan import direct
        words, dur = synth(self.SCRIPT)
        d = self.tmp
        opt = DirectorOptions(look="reference", cartoon_share=1.0, scenes2=True, work_dir=d, **kw)
        return direct(words, self.SCRIPT, opt, duration=dur, materialize=False)

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name
        self.addCleanup(self._td.cleanup)

    def test_off_leaves_the_report_and_plan_unchanged_and_on_records_decisions(self):
        a, b = self._run(), self._run(continuity=False)
        self.assertEqual(json.dumps(a.plan, sort_keys=True, default=str), json.dumps(b.plan, sort_keys=True, default=str))
        self.assertNotIn("continuity", json.dumps(a.report, default=str).replace("explainer_continuity", ""))
        on = self._run(continuity=True)
        self.assertEqual(on.problems, [], on.problems)
        recs = [v["continuity"] for v in on.report["beat_details"].values() if "continuity" in v]
        self.assertTrue(recs)
        self.assertIn("continuity", on.report)
        self.assertEqual(json.dumps(on.report["continuity"], sort_keys=True), json.dumps(self._run(continuity=True).report["continuity"], sort_keys=True))


if __name__ == "__main__":
    unittest.main()
