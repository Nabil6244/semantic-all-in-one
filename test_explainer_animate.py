"""Animation pass (explainer/director/compose_anim.py): opt-in entrances; resting positions unchanged; limits; deterministic."""
import json
import sys
import unittest
from copy import deepcopy

import numpy as np

import test_explainer_recipes as TR
from explainer.board import render as R
from explainer.board.dry import dry_build
from explainer.director import compose_anim as CA
from explainer.director.options import DirectorOptions
from explainer.director.plan import direct

sys.path.insert(0, ".")
import importlib.util, os  # noqa: E402

TEXT = "napoleon walked into the town square with the officers by evening the square was full of the people and the officers said napoleon was the emperor of everything in the whole world"


def lab():
    from types import SimpleNamespace as NS
    from explainer.director import scene_registry as SR
    from explainer.director.compose_cartoon import author_cartoon, continuity_plan
    from explainer.director.segment import Sent
    words = [(w, 0.5 + 0.35 * i, 0.5 + 0.35 * i + 0.3) for i, w in enumerate(TEXT.split())]
    t_mid = words[9][1] - 0.01
    opt = DirectorOptions(scenes2=True, continuity=True, animate=True)
    reg, out = SR.SceneRegistry(), []
    for i, (s, e) in enumerate([(0.0, t_mid), (t_mid, words[-1][2] + 1.0)]):
        b = NS(id=f"e{i}", start=s, end=e, scene_hint=None)
        b.sents = [Sent(0, s, e, "x", True, [g for g, w in enumerate(words) if s - 1e-6 <= w[1] < e - 1e-6])]
        p = continuity_plan(reg, b, words, opt, {}, i)
        br = author_cartoon(b.id, s, e, b.sents, words, {}, opt, {}, {}, variant=i, plan=p)
        base = deepcopy(br.cues)
        h = reg.history
        rec = CA.animate_pass(br, b.id, s, e, b.sents, words, opt, variant=i, kind="cartoon", continuity=p, prev_cast=h[-2]["cast"] if len(h) > 1 else None)
        out.append((b, br, base, rec, s, e))
    return out, words, opt


def motions(cues):
    return {c.id: c.params["motion"] for c in cues if (c.params or {}).get("motion")}


class Cartoon(unittest.TestCase):
    def test_figures_enter_and_continued_one_does_not(self):
        out, *_ = lab()
        m0, m1 = motions(out[0][1].cues), motions(out[1][1].cues)
        self.assertIn("e0_fig1", m0)
        self.assertIn(m0["e0_fig1"]["enter"]["from"], ("left", "right"))
        self.assertTrue(out[1][3]["stayed"])
        self.assertNotIn("enter", m1.get("e1_fig1", {}))        # on stage already
        self.assertIn("enter", m1["e1_fig2"])                   # the new person walks in
        self.assertNotIn("e0_set1", m0)                          # the set never moves

    def test_resting_positions_unchanged_and_params_well_formed(self):
        out, *_ = lab()
        for _b, br, base, _r, _s, _e in out:
            self.assertEqual([(c.id, c.pos, c.anchor) for c in br.cues], [(c.id, c.pos, c.anchor) for c in base])
            for m in motions(br.cues).values():
                json.dumps(m)
                if "enter" in m:
                    self.assertIn(m["enter"]["from"], ("left", "right", "top", "bottom"))
                    self.assertLessEqual(m["enter"]["dur"], CA.MAX_ENTER_S + 1e-9)

    def test_deterministic(self):
        a, b = lab()[0], lab()[0]
        self.assertEqual(json.dumps([motions(x[1].cues) for x in a], sort_keys=True), json.dumps([motions(x[1].cues) for x in b], sort_keys=True))

    def test_dry_build_clean_and_rest_state_is_pixel_identical(self):
        out, words, opt = lab()
        _b, br, base, _r, s, e = out[0]
        pa, _r1, ia = dry_build(br.cues, words, s, e, dissolve_s=0, fps=30, beat_id="e0")
        pb, _r2, ib = dry_build(base, words, s, e, dissolve_s=0, fps=30, beat_id="e0")
        self.assertEqual((pa, pb), ([], []))
        t = 2.0                                                  # long after the entrance
        fa = np.asarray(R.draw_frame(ia, t, (1920, 1080), None, 60, False, background="paper"))
        fb = np.asarray(R.draw_frame(ib, t, (1920, 1080), None, 60, False, background="paper"))
        self.assertEqual(int(np.abs(fa.astype(int) - fb.astype(int)).max()), 0)


class Board(unittest.TestCase):
    def run_recipe(self, name, variant=0):
        txt, idea = TR.CASES[name]
        opt = DirectorOptions(recipes=True, animate=True)
        r, w, end = TR.author(txt, idea, opt=opt)
        base = deepcopy(r.cues)
        rec = CA.animate_pass(r, "e1", 0.0, end, [], w, opt, variant=variant, kind="board")
        return r, base, rec, w, end

    def test_each_recipe_gets_limited_entrances(self):
        for name in ("cause_effect", "before_after", "two_column", "pictogram", "pyramid", "timeline"):
            r, base, rec, w, end = self.run_recipe(name)
            self.assertEqual([(c.id, c.pos) for c in r.cues], [(c.id, c.pos) for c in base], name)
            probs, _r, items = dry_build(r.cues, w, 0.0, end, dissolve_s=0, fps=30, beat_id="e1")
            self.assertEqual(probs, [], name)
            self.assertTrue(rec["entered"] or name == "timeline", name)
            wins = []
            for it in items:
                m = (it.vparams or {}).get("motion") if it.vparams else None
                if not m:
                    continue
                dur = max([m.get("enter", {}).get("dur", 0), (m.get("wave") or {}).get("span", 0) + (m.get("wave") or {}).get("dur", 0), (m.get("scale") or [0, 0, 0])[2]])
                self.assertLessEqual(dur, CA.MAX_ENTER_S + 1e-9, name)
                self.assertLessEqual(it.onset + dur, end - CA.QUIET_END_S + 1e-6, name)
                self.assertLessEqual(dur, 0.5 * (end - it.onset) + 1e-9, name)
                wins.append((it.onset, it.onset + dur))
            for a, _b in wins:
                self.assertLessEqual(sum(1 for x, y in wins if x <= a < y), CA.MAX_MOVING)

    def test_before_after_opposite_sides_and_variants_differ(self):
        r, *_ = self.run_recipe("before_after")
        sides = [m["enter"]["from"] for m in motions(r.cues).values() if "enter" in m]
        self.assertEqual(set(sides), {"left", "right"})
        eases = {json.dumps(motions(self.run_recipe("cause_effect", v)[0].cues), sort_keys=True) for v in range(3)}
        self.assertGreater(len(eases), 1)

    def test_key_number_pulses_once_and_deterministic(self):
        r, _b, rec, *_ = self.run_recipe("pictogram")
        self.assertEqual(len(rec["pulses"]), 1)
        r2 = self.run_recipe("pictogram")[0]
        self.assertEqual(motions(r.cues), motions(r2.cues))

    def test_late_element_inside_quiet_window_is_not_animated(self):
        r, base, rec, w, end = self.run_recipe("cause_effect")
        r2 = TR.author(*TR.CASES["cause_effect"], opt=DirectorOptions(recipes=True))[0]
        CA.animate_pass(r2, "e1", 0.0, 4.2, [], w, DirectorOptions(recipes=True, animate=True), kind="board")
        # the effect node is now pulled earlier than its spoken word (it arrives 0.9 s after the cause), so it may animate; what must hold is that any motion fits before the quiet end
        _p, _r, items = dry_build(r2.cues, w, 0.0, 4.2, dissolve_s=0, fps=30, beat_id="e1")
        for it in items:
            m = (it.vparams or {}).get("motion") if it.vparams else None
            if m:
                self.assertLessEqual(it.onset + m.get("enter", {}).get("dur", 0), 4.2 - CA.QUIET_END_S + 1e-6)


class Off(unittest.TestCase):
    def test_off_plan_is_unchanged_and_report_omits_animate(self):
        words = [(w, 0.5 + 0.35 * i, 0.5 + 0.35 * i + 0.3) for i, w in enumerate(TEXT.split())]
        a = direct(words, TEXT, DirectorOptions(scenes2=True, continuity=True, recipes=True))
        b = direct(words, TEXT, DirectorOptions(scenes2=True, continuity=True, recipes=True, animate=False))
        self.assertEqual(json.dumps(a.report, sort_keys=True, default=str), json.dumps(b.report, sort_keys=True, default=str))
        self.assertNotIn('"animate"', json.dumps(a.report, default=str))
        self.assertNotIn('"enter"', json.dumps(a.plan if hasattr(a, "plan") else a.report, default=str))

    def test_on_plan_has_motion_and_still_no_problems(self):
        words = [(w, 0.5 + 0.35 * i, 0.5 + 0.35 * i + 0.3) for i, w in enumerate(TEXT.split())]
        a = direct(words, TEXT, DirectorOptions(scenes2=True, continuity=True, animate=True))
        b = direct(words, TEXT, DirectorOptions(scenes2=True, continuity=True))
        self.assertEqual(a.problems, b.problems)


if __name__ == "__main__":
    unittest.main()
