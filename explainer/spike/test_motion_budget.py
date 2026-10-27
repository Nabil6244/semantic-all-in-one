"""Phase F tests: the effect budget (per-video windows for stamps, plates, count-ups, cross-outs and map lines, and rotating entrance variants). Opt-in (DirectorOptions.budget), offline, deterministic.
usage: python3 -B explainer/spike/test_motion_budget.py   (from the repository root)"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, SCRIPT as KOREA_SCRIPT, WORDS as KOREA_WORDS, DUR as KOREA_DUR, run     # noqa: E402
from explainer.board import render as R                                         # noqa: E402
from explainer.board import layout as LY                                        # noqa: E402
from explainer.director import DirectorOptions, direct                          # noqa: E402
from explainer.motion import budget as BG                                       # noqa: E402
from explainer.motion import presets as P                                       # noqa: E402
from explainer.motion import sprites as MS                                      # noqa: E402

EVIDENCE = ROOT / "docs" / "explainer" / "phase_motion_evidence"
BLOCK = ("The old fortress had stood for centuries above the river. Its walls were thick and its guards were proud. Then the army arrived and the garrison was surrounded within a single week. "
         "Inside there was no water for the soldiers. The siege began in 1944. Every officer knew the plan was worthless. By then 45 percent of the grain was gone. "
         "The soldiers who stayed were caught between the river and the guns. Nobody expected help from the north. The war ended in 1945 and the survivors were freed. ")
LONG = BLOCK * 10
ALL = dict(motion=True, numbers=True)


class Cache:
    _r = {}

    @classmethod
    def get(cls, **kw):
        k = tuple(sorted(kw.items()))
        if k not in cls._r:
            w, d = synth(LONG)
            cls._r[k] = (direct(w, LONG, DirectorOptions(look="reference", **kw), duration=d, materialize=False), w, d)
        return cls._r[k]


def times(rep, key, sub):
    return sorted((c["t"], b, c) for b, v in rep["beat_details"].items() if isinstance(v, dict) and v.get(key) for c in v[key][sub])


class Unit(unittest.TestCase):
    def test_a_window_blocks_the_next_effect_and_says_why(self):
        b = BG.Budget()
        self.assertEqual(b.allow("stamp", 10.0), (True, ""))
        b.commit("stamp", 10.0)
        ok, why = b.allow("stamp", 100.0)
        self.assertFalse(ok)
        self.assertIn("one per 120 s", why)
        self.assertTrue(b.allow("stamp", 130.0)[0])
        self.assertTrue(b.allow("plate", 100.0)[0])                                   # each kind has its own window
        self.assertEqual(b.summary()["refused"][0]["kind"], "stamp")

    def test_variants_rotate_in_order(self):
        b = BG.Budget({"stamp": 0.0, "plate": 0.0, "count": 0.0, "cross": 0.0, "line": 0.0})
        seq = []
        for i in range(7):
            seq.append(b.variant("stamp"))
            b.commit("stamp", i * 200.0)
        self.assertEqual(seq, [0, 1, 2, 0, 1, 2, 0])
        self.assertEqual(b.variant("count"), 0)

    def test_windows_are_the_documented_ones(self):
        self.assertEqual(BG.WINDOW_S, {"stamp": 120.0, "plate": 180.0, "count": 90.0, "cross": 180.0, "line": 150.0})


class Variants(unittest.TestCase):
    def test_every_stamp_variant_settles_on_the_same_stamp_within_8_frames(self):
        self.assertEqual(P.SLAM_VARIANTS[0], P.SLAM)
        for v in range(3):
            self.assertEqual(len(P.SLAM_VARIANTS[v]), P.SLAM_FRAMES)
            self.assertEqual(P.slam_frame(P.SLAM_FRAMES - 1, v), (1.0, 1.0, 0.0, 0, 0))
            self.assertEqual(P.slam_frame(99, v), (1.0, 1.0, 0.0, 0, 0))
        starts = {P.slam_frame(0, v) for v in range(3)}
        self.assertEqual(len(starts), 3)                                              # three different entrances

    def test_the_default_stamp_bytes_are_unchanged_and_the_variants_differ_on_the_way_but_not_at_the_end(self):
        args = ("CAUGHT", "red", 640, 200, 96, "a", False, 3.0)
        d0 = MS.stamp_frame(*args, 0)
        self.assertEqual(MS.stamp_frame(*args, 0, 0)[0].tobytes(), d0[0].tobytes())   # sv=0 is the original
        mid = [MS.stamp_frame(*args, 1, v) for v in range(3)]
        self.assertEqual(len({(m[0].tobytes(), m[1]) for m in mid}), 3)
        end = [MS.stamp_frame(*args, 7, v) for v in range(3)]
        self.assertEqual(len({e[0].tobytes() for e in end}), 1)

    def test_the_variant_reaches_the_drawn_frame_through_the_renderer(self):
        """The unit tests above call stamp_frame directly; this one goes through Cue -> layout -> draw_frame, the path a render takes (a variant dropped on the way would not show above)."""
        from explainer.board.cues import Cue
        from explainer.board.dry import dry_build
        words = [("caught", 0.5, 0.8), ("in", 0.9, 1.0), ("the", 1.1, 1.2), ("act", 1.3, 1.5)] + [("x", 1.6 + i * 0.2, 1.7 + i * 0.2) for i in range(12)]
        frames = {}
        for sv in range(3):
            cue = Cue("s1", "visual", {"index": 0}, text="CAUGHT", role="red", offset_s=0.0, pos=(1000, 600), params={"style": "stamp", "mv": 1, "texture": False, "px": 96, "sv": sv})
            probs, _r, items = dry_build([cue], words, 0.0, 4.0, beat_id="t")
            self.assertEqual(probs, [], sv)
            it = items[0]
            self.assertEqual(it.vparams["sv"], sv)
            frames[sv] = [R.draw_frame(items, it.onset + k / 30, (1920, 1080), None, it.first_frame + k, False).tobytes() for k in (0, 2, 7)]
        self.assertEqual(len({frames[v][0] for v in range(3)}), 3)             # three different first frames
        self.assertEqual(len({frames[v][1] for v in range(3)}), 3)
        self.assertEqual(len({frames[v][2] for v in range(3)}), 1)             # the same settled stamp
        plates = {}
        for pv in range(3):
            cue = Cue("p1", "visual", {"index": 0}, text="1945", role="blue", offset_s=0.0, pos=(1600, 200), params={"style": "plate", "mv": 1, "px": 40, "pv": pv})
            probs, _r, items = dry_build([cue], words, 0.0, 4.0, beat_id="t")
            self.assertEqual(probs, [], pv)
            it = items[0]
            plates[pv] = [R.draw_frame(items, it.onset + k / 30, (1920, 1080), None, it.first_frame + k, False).tobytes() for k in (0, 3, 9)]
        self.assertEqual(len({plates[v][0] for v in range(3)}), 3)
        self.assertEqual(len({plates[v][2] for v in range(3)}), 1)

    def test_every_plate_entrance_lands_on_the_same_place(self):
        for v in range(P.PLATE_VARIANTS):
            self.assertEqual(P.plate_motion(P.SLIDE_FRAMES / 30, v), (0, 0, 1.0))
            self.assertNotEqual(P.plate_motion(0.0, v)[:2], (0, 0))
        self.assertEqual(P.plate_motion(0.1, 0), (0, -P.slide_in(0.1)[0], P.slide_in(0.1)[1]))     # variant 0 is the original slide


class LongVideo(unittest.TestCase):
    def test_the_windows_hold_over_a_long_video_and_bite(self):
        off, w, d = Cache.get(**ALL, maplines=True)
        on, _w, _d = Cache.get(**ALL, maplines=True, budget=True)
        self.assertGreater(d, 300)
        self.assertEqual(on.problems, [])
        self.assertEqual(on.report["hybrid_validate"].get("errors"), [])
        fb = on.report["fx_budget"]
        for kind, window in BG.WINDOW_S.items():
            ts = fb["used"][kind]
            for a, b in zip(ts, ts[1:]):
                self.assertGreaterEqual(b - a, window - 1e-6, (kind, ts))
        # the budget really removed effects: without it far more are authored
        n_off = {k: len(times(off.report, "motion", s) if k in ("stamp", "plate") else times(off.report, "numbers", s)) for k, s in (("stamp", "stamps"), ("plate", "plates"), ("count", "counts"), ("cross", "crosses"))}
        n_on = {k: fb["counts"][k] for k in n_off}
        self.assertGreater(n_off["stamp"], n_on["stamp"])
        self.assertGreater(n_off["count"], n_on["count"])
        self.assertTrue(fb["refused"])
        for k in n_on:
            self.assertLessEqual(n_on[k], n_off[k])

    def test_the_report_counts_equal_what_is_in_the_plan(self):
        on, _w, _d = Cache.get(**ALL, maplines=True, budget=True)
        fb = on.report["fx_budget"]
        self.assertEqual(fb["counts"]["stamp"], len(times(on.report, "motion", "stamps")))
        self.assertEqual(fb["counts"]["plate"], len(times(on.report, "motion", "plates")))
        self.assertEqual(fb["counts"]["count"], len(times(on.report, "numbers", "counts")))
        self.assertEqual(fb["counts"]["cross"], len(times(on.report, "numbers", "crosses")))
        self.assertEqual(fb["used"]["stamp"], [round(t, 3) for t, _b, _c in times(on.report, "motion", "stamps")])

    def test_stamp_and_plate_entrances_rotate_and_no_variant_repeats_within_five_minutes(self):
        on, _w, _d = Cache.get(**ALL, maplines=True, budget=True)
        for kind, key, sub, field in (("stamp", "motion", "stamps", "sv"), ("plate", "motion", "plates", "pv")):
            seq = []
            for t, b, c in times(on.report, key, sub):
                spec = next(x for x in on.report["beat_details"][b]["cue_specs"] if x["id"] == c["cue"])
                seq.append((t, spec["params"][field]))
            self.assertGreaterEqual(len(seq), 2, kind)
            self.assertEqual([v for _t, v in seq], [i % 3 for i in range(len(seq))], kind)                 # in order: 0, 1, 2, 0, ...
            for i, (t, v) in enumerate(seq):
                same = [x for x in seq if abs(x[0] - t) < 300 and x[1] == v]
                self.assertLessEqual(len(same), 1, (kind, seq))

    def test_a_stamp_in_a_variant_still_fits_the_frame_on_every_frame_that_counts(self):
        on, w, _d = Cache.get(**ALL, maplines=True, budget=True)
        from explainer.board.dry import dry_build
        from explainer.board.cues import Cue
        sx0, sy0, sx1, sy1 = LY.SAFE
        for t, b, c in times(on.report, "motion", "stamps"):
            bb = next(x for x in on.plan["beats"] if x["id"] == b)
            _p, _r, items = dry_build([Cue(**x) for x in on.report["beat_details"][b]["cue_specs"]], w, bb["start"], bb["end"], beat_id=b)
            self.assertEqual(_p, [])
            st = next(x for x in items if x.cue_id == c["cue"])
            cx, cy = (st.rect[0] + st.rect[2]) // 2, (st.rect[1] + st.rect[3]) // 2
            sv = next(x for x in on.report["beat_details"][b]["cue_specs"] if x["id"] == c["cue"])["params"]["sv"]
            for f in range(P.IMPACT_FRAME, P.SLAM_FRAMES):
                sp, (dx, dy) = MS.stamp_frame(st.lines[0], st.role, st.rect[2] - st.rect[0], st.rect[3] - st.rect[1], st.px, MS.variant_for(st.cue_id), MS.available_cached(), MS.tilt_for(st.cue_id), f, sv)
                x0, y0 = cx - sp.width // 2 + dx, cy - sp.height // 2 + dy
                self.assertTrue(sx0 <= x0 and sy0 <= y0 and x0 + sp.width <= sx1 and y0 + sp.height <= sy1, (b, sv, f, x0, y0, sp.size))


class MapLineBudget(unittest.TestCase):
    MAPS = ("The war began quietly. Soon the troops crossed from Egypt to Libya in the heat. Nobody at home knew how far they had gone. The camp was quiet and the fires burned low. "
            "Then the army moved from Spain to Italy along the old roads. The generals said the plan could not fail. The harbour was busy and the market was full.")

    def lines(self, plan):
        return [(b["id"], tuple(l["places"])) for b in plan["beats"] if b["mode"] == "map" for l in b.get("layers", []) if l["type"] == "line"]

    def test_a_map_line_is_committed_to_the_budget_and_a_second_one_inside_the_window_is_refused(self):
        w, d = synth(self.MAPS)
        off = direct(w, self.MAPS, DirectorOptions(look="reference", maplines=True, max_map_share=1.0), duration=d, materialize=False)
        on = direct(w, self.MAPS, DirectorOptions(look="reference", maplines=True, budget=True, max_map_share=1.0), duration=d, materialize=False)
        self.assertEqual(on.problems, [])
        self.assertEqual(self.lines(off.plan), [("e1", ("Egypt", "Libya")), ("e4", ("Spain", "Italy"))])       # without the budget both lines are drawn, 13 s apart
        self.assertEqual(self.lines(on.plan), [("e1", ("Egypt", "Libya"))])                                  # with it only the first
        fb = on.report["fx_budget"]
        self.assertEqual(len(fb["used"]["line"]), 1)
        self.assertEqual([x["kind"] for x in fb["refused"]], ["line"])
        self.assertIn("one per 150 s", fb["refused"][0]["why"])
        self.assertTrue(any("map line not drawn" in n for n in on.report["selection"]["notes"]["e4"]))


class OffByDefault(unittest.TestCase):
    def test_budget_alone_changes_nothing_but_the_report(self):
        w, d = synth(BLOCK * 2)
        a = direct(w, BLOCK * 2, DirectorOptions(look="reference"), duration=d, materialize=False)
        b = direct(w, BLOCK * 2, DirectorOptions(look="reference", budget=True), duration=d, materialize=False)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))
        self.assertEqual(b.report["fx_budget"]["counts"], {k: 0 for k in BG.WINDOW_S})
        self.assertNotIn("fx_budget", a.report)
        self.assertNotIn("budget", a.report["options"])

    def test_budget_false_equals_the_recorded_head_plan(self):
        self.assertIs(DirectorOptions().budget, False)
        base = json.loads((EVIDENCE / "disabled_path_baseline_HEAD.json").read_text())
        sha = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()
        for look in ("reference", "classic"):
            r = run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, look=look, budget=False)
            bd = r.report["beat_details"]
            self.assertEqual(sha(r.plan), base[f"korea/{look}"]["plan_sha"], look)
            self.assertEqual({b: v["clip"] for b, v in bd.items() if isinstance(v, dict) and "clip" in v}, base[f"korea/{look}"]["clips"], look)

    def test_the_settings_for_every_phase_default_off_and_bad_values_mean_off(self):
        from explainer.integration import motion_pack, motion_enabled
        off = {"numbers": False, "maplines": False, "variety": False, "budget": False}
        for bad in (None, {}, {"explainer_numbers": None}, {"explainer_budget": "no"}, {"explainer_variety": 2}, {"explainer_maplines": [1]}, "x"):
            self.assertEqual(motion_pack(bad), off, bad)
        self.assertEqual(motion_pack({"explainer_numbers": True, "explainer_maplines": "on", "explainer_variety": 1, "explainer_budget": "TRUE"}), {k: True for k in off})
        self.assertFalse(motion_enabled({"explainer_motion": "false"}))

    def test_the_same_long_plan_twice_is_identical(self):
        on, w, d = Cache.get(**ALL, maplines=True, budget=True)
        again = direct(w, LONG, DirectorOptions(look="reference", budget=True, maplines=True, **ALL), duration=d, materialize=False)
        self.assertEqual(json.dumps(on.plan, sort_keys=True), json.dumps(again.plan, sort_keys=True))
        self.assertEqual(json.dumps(on.report["fx_budget"], sort_keys=True), json.dumps(again.report["fx_budget"], sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
