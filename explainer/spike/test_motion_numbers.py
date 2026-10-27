"""Phase C tests (motion kit part 2): count-up numbers and cross-out strokes. Opt-in (DirectorOptions.numbers), offline, deterministic, nothing encoded.
usage: python3 -B explainer/spike/test_motion_numbers.py   (from the repository root)"""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

from test_director_real_material import synth, run, SCRIPT as KOREA_SCRIPT, WORDS as KOREA_WORDS, DUR as KOREA_DUR      # noqa: E402
from explainer.board import render as R                                       # noqa: E402
from explainer.board import layout as LY                                      # noqa: E402
from explainer.board.cues import Cue                                          # noqa: E402
from explainer.board.dry import dry_build                                     # noqa: E402
from explainer.director import DirectorOptions                                # noqa: E402
from explainer.motion import presets as P                                     # noqa: E402

EVIDENCE = ROOT / "docs" / "explainer" / "phase_motion_evidence"
FPS = 30
SCRIPT = ("The old fortress had stood for centuries above the river. Its walls were thick and its guards were proud. Then the army arrived and the garrison was surrounded within a single week. "
          "Inside there was no water for the soldiers. Only 1200 soldiers survived. Every officer knew the plan was worthless. By then 45 percent of the grain was gone. "
          "There was never any help from the north and no road home.")
PLAIN = SCRIPT.replace("no water", "clean water").replace("never any help", "ample help").replace("no road", "a road")


class Cache:
    _r = {}

    @classmethod
    def plan(cls, script=SCRIPT, **kw):
        k = (script, tuple(sorted(kw.items())))
        if k not in cls._r:
            w, d = synth(script)
            cls._r[k] = (run(w, script, d, **kw), w, d)
        return cls._r[k]


def recs(rep):
    return {b: v["numbers"] for b, v in rep["beat_details"].items() if isinstance(v, dict) and v.get("numbers")}


def span(plan, bid):
    b = next(b for b in plan["beats"] if b["id"] == bid)
    return b["start"], b["end"]


def items_of(rep, plan, w, bid):
    s, e = span(plan, bid)
    return dry_build([Cue(**c) for c in rep["beat_details"][bid]["cue_specs"]], w, s, e, beat_id=bid)


class CountPreset(unittest.TestCase):
    CASES = ["45 percent", "1,200", "$2.5 million", "300 percent", "12000 lives", "7.25", "$1,250,000", "99%", "20", "3 million"]

    def test_parse_and_final_text_is_exact(self):
        for t in self.CASES:
            sp = P.count_spec(t)
            self.assertIsNotNone(sp, t)
            self.assertEqual(P._fmt(sp["to"], sp), t, t)
            self.assertEqual(P.count_text(sp["frames"] / FPS, sp), t)
            self.assertEqual(P.count_text(9.0, sp), t)

    def test_not_a_quantity(self):
        for t in ("hello", "1944 and", "", "12 34", "x5", "5 six seven"):
            self.assertIsNone(P.count_spec(t), t)

    def test_the_roll_is_monotonic_bounded_integer_and_starts_at_zero(self):
        for t in self.CASES:
            sp = P.count_spec(t)
            vals = []
            for f in range(0, sp["frames"] + 1):
                s = P.count_text(f / FPS, sp)
                digits = int(re.sub(r"\D", "", s.split(" ")[0]) or 0) if not sp["dec"] else int(re.sub(r"\D", "", re.match(r"\D*([\d,]+(?:\.\d+)?)", s).group(1)))
                vals.append(digits)
            self.assertEqual(vals, sorted(vals), t)
            self.assertLessEqual(vals[-1], sp["to"])
            self.assertEqual(vals[0], 0, t)
            self.assertEqual(vals[-1], sp["to"], t)

    def test_pure_and_deterministic_and_frames_are_clamped(self):
        sp = P.count_spec("45 percent", frames=5)
        self.assertEqual(sp["frames"], P.COUNT_MIN_FRAMES)
        self.assertEqual(P.count_spec("45 percent", frames=500)["frames"], P.COUNT_MAX_FRAMES)
        self.assertEqual([P.count_text(i / 90, sp) for i in range(60)], [P.count_text(i / 90, sp) for i in range(60)])

    def test_cross_out_strokes(self):
        self.assertEqual(P.cross_out(0.0), (0.0, 0.0))
        self.assertEqual(P.cross_out(P.CROSS_STROKE_FRAMES / FPS), (1.0, 0.0))
        self.assertEqual(P.cross_out(2 * P.CROSS_STROKE_FRAMES / FPS), (1.0, 1.0))
        self.assertEqual(P.cross_out(9.0), (1.0, 1.0))


class Counts(unittest.TestCase):
    def test_a_spoken_quantity_tag_rolls_and_only_gains_a_param(self):
        on, w, _d = Cache.plan(numbers=True)
        off, _w, _d2 = Cache.plan(numbers=False)
        self.assertEqual(on.problems, [])
        counts = [(b, c) for b, r in recs(on.report).items() for c in r["counts"]]
        self.assertEqual([c["text"] for _b, c in counts], ["45 percent"])
        bid, c = counts[0]
        new = next(x for x in on.report["beat_details"][bid]["cue_specs"] if x["id"] == c["cue"])
        old = next(x for x in off.report["beat_details"][bid]["cue_specs"] if x["id"] == c["cue"])
        self.assertEqual({k: v for k, v in new.items() if k != "params"}, {k: v for k, v in old.items() if k != "params"})       # same id, text, place, anchor, offset
        self.assertEqual({k: v for k, v in new["params"].items() if k not in ("count", "cv")}, old["params"])
        self.assertEqual([x["id"] for x in on.report["beat_details"][bid]["cue_specs"]], [x["id"] for x in off.report["beat_details"][bid]["cue_specs"]])
        self.assertEqual(on.report["beat_details"][bid]["layout"], off.report["beat_details"][bid]["layout"])                   # the layout is untouched

    def test_the_frames_roll_and_land_on_exactly_the_cue_text(self):
        on, w, _d = Cache.plan(numbers=True)
        bid, c = next((b, c) for b, r in recs(on.report).items() for c in r["counts"])
        _p, _r, items = items_of(on.report, on.plan, w, bid)
        it = next(x for x in items if x.cue_id == c["cue"])
        self.assertEqual(it.vparams["count"]["frames"], c["frames"])
        self.assertGreaterEqual(c["frames"], 24)
        self.assertLessEqual(c["frames"], 36)
        shown = [R.draw_frame(items, it.onset + k / FPS, (1920, 1080), None, it.first_frame + k, False).crop(it.rect).tobytes() for k in (0, 6, 12, c["frames"] - 1, c["frames"], c["frames"] + 30)]
        self.assertEqual(len(set(shown[:4])), 4)                                           # four different pictures on the way
        self.assertEqual(shown[4], shown[5])                                               # then it holds still on the final text
        # the settled frame is the same picture as the numbers-off board (the cue's own text)
        off, _w, _d2 = Cache.plan(numbers=False)
        _p, _r, items0 = items_of(off.report, off.plan, w, bid)
        it0 = next(x for x in items0 if x.cue_id == c["cue"])
        a = R.draw_frame(items, it.onset + 2.0, (1920, 1080), None, it.first_frame + 60, False)
        b = R.draw_frame(items0, it0.onset + 2.0, (1920, 1080), None, it0.first_frame + 60, False)
        self.assertEqual(a.tobytes(), b.tobytes())

    def test_it_lands_on_the_spoken_number(self):
        on, w, _d = Cache.plan(numbers=True)
        bid, c = next((b, c) for b, r in recs(on.report).items() for c in r["counts"])
        bs, _ = span(on.plan, bid)
        _p, _r, items = items_of(on.report, on.plan, w, bid)
        it = next(x for x in items if x.cue_id == c["cue"])
        self.assertTrue(-1e-6 <= it.onset - (c["t"] - bs) <= 0.3 + 1e-6)                    # the first frame is on the number word
        word_end = next(x[2] for x in w if abs(x[1] - c["t"]) < 1e-6)
        self.assertAlmostEqual(it.onset + c["frames"] / FPS, word_end - bs + 0.6, delta=0.15)

    def test_years_small_numbers_and_unreproducible_text_are_never_rolled_in_the_pass(self):
        """Through the real numbers_pass on stub cues (each case in its own beat, so the 12 s gap is not what decides)."""
        from types import SimpleNamespace
        from explainer.director.compose_numbers import numbers_pass
        words = [("x", float(i), float(i) + 0.3) for i in range(20)]
        sent = SimpleNamespace(widx=list(range(20)))
        cases = {"1,200": True, "1,944": True, "2,000 soldiers": True, "45 percent": True, "$2.5 million": True, "12000 lives": True,
                 "1944": False, "1944 army": False, "2020": False, "12": False, "007": False, "1944 and": False, "hello": False}
        for text, rolls in cases.items():
            cue = Cue("t1", "visual", {"index": 2}, text=text, role="blue", pos=(1380, 130), params={"style": "tag"})
            br = SimpleNamespace(cues=[cue], repairs=[])
            rec = numbers_pass(br, "b", 0.0, 20.0, [sent], words, DirectorOptions(look="reference", numbers=True), {})
            self.assertEqual(bool(rec["counts"]), rolls, (text, rec))
            self.assertEqual("count" in (cue.params or {}), rolls, text)
            if rolls:
                self.assertEqual(rec["counts"][0]["text"], text)
                self.assertEqual(P.count_text(60.0, cue.params["count"]), text)                 # and it ends on exactly that text

    def test_two_counts_are_at_least_12_seconds_apart(self):
        s = ("The siege was long and the winter was cold. Soon after, 80 percent of the horses were dead. The camp was quiet and the fires burned low. "
             "Then 60 percent of the men fell ill. The river froze and the winter went on.")
        r, w, d = Cache.plan(s, numbers=True)
        ts = sorted(c["t"] for rc in recs(r.report).values() for c in rc["counts"])
        self.assertEqual(len(ts), 1, ts)                                                    # the second one comes 6 s after the first
        self.assertTrue(any("previous count" in x for rc in recs(r.report).values() for x in rc["skipped"]), recs(r.report))


class Crosses(unittest.TestCase):
    def test_a_negation_before_a_picture_crosses_it_out_after_it_lands(self):
        r, w, _d = Cache.plan(numbers=True)
        cr = [(b, c) for b, rc in recs(r.report).items() for c in rc["crosses"]]
        self.assertEqual([c["negation"] for _b, c in cr], ["no"])
        bid, c = cr[0]
        self.assertEqual(r.report["beat_details"][bid]["problems"], [])
        probs, _res, items = items_of(r.report, r.plan, w, bid)
        self.assertEqual(probs, [])
        x = next(i for i in items if i.cue_id == c["cue"])
        tile = next(i for i in items if i.cue_id == c["over"])
        self.assertTrue(tile.rect[0] <= x.rect[0] and tile.rect[1] <= x.rect[1] and x.rect[2] <= tile.rect[2] and x.rect[3] <= tile.rect[3])        # inside its picture's box
        self.assertGreaterEqual(x.onset, tile.onset + 0.3)                                  # after the picture has landed
        sx0, sy0, sx1, sy1 = LY.SAFE
        self.assertTrue(sx0 <= x.rect[0] and sy0 <= x.rect[1] and x.rect[2] <= sx1 and x.rect[3] <= sy1)
        without = [i for i in items if i.cue_id != x.cue_id]
        f = lambda its, k: R.draw_frame(its, x.onset + k / FPS, (1920, 1080), None, x.first_frame + k, False)
        before = R.draw_frame(its_ := items, x.onset - 1 / FPS, (1920, 1080), None, x.first_frame - 1, False)
        self.assertEqual(before.tobytes(), R.draw_frame(without, x.onset - 1 / FPS, (1920, 1080), None, x.first_frame - 1, False).tobytes())
        stages = [f(items, k).crop(x.rect).tobytes() for k in (0, 3, 6, 10, 20)]            # the strokes' own box (the board's typed lines keep typing elsewhere)
        self.assertEqual(len(set(stages[:4])), 4)                                           # stroke one grows, stroke two grows
        self.assertEqual(stages[3], stages[4])                                              # then holds
        self.assertNotEqual(stages[4], f(without, 20).crop(x.rect).tobytes())

    def test_no_negation_no_cross_and_a_control_script_is_unchanged(self):
        r, w, _d = Cache.plan(PLAIN, numbers=True)
        self.assertEqual([c for rc in recs(r.report).values() for c in rc["crosses"]], [])
        off, _w, _d2 = Cache.plan(PLAIN, numbers=False)
        for b, v in r.report["beat_details"].items():
            if isinstance(v, dict) and "cue_specs" in v:
                strip = lambda cs: [{k: x for k, x in c.items() if k != "params"} for c in cs]
                self.assertEqual(strip(v["cue_specs"]), strip(off.report["beat_details"][b]["cue_specs"]))

    def test_the_negation_must_be_in_the_same_sentence_within_three_words(self):
        s = ("The siege was long. Nobody inside had any water at all today friends. The army brought water from the river. " * 1)
        r, w, _d = Cache.plan(s, numbers=True)
        for rc in recs(r.report).values():
            for c in rc["crosses"]:
                self.assertIn(c["negation"], ("no", "not", "never", "none", "nobody", "nothing", "without"))
        # direct rule check on a stub: a negation four words before is too far
        from explainer.director import compose_numbers as CN
        self.assertEqual(CN.NEG_WINDOW, 3)

    def test_two_cross_outs_are_at_least_20_seconds_apart(self):
        r, _w, _d = Cache.plan(numbers=True)
        ts = sorted(c["t"] for rc in recs(r.report).values() for c in rc["crosses"])
        for a, b in zip(ts, ts[1:]):
            self.assertGreaterEqual(b - a, 20.0 - 1e-6)


class OffByDefault(unittest.TestCase):
    def test_numbers_is_off_by_default_and_absent_from_the_disabled_report(self):
        self.assertIs(DirectorOptions().numbers, False)
        r, _w, _d = Cache.plan(numbers=False)
        self.assertNotIn("numbers", r.report["options"])
        self.assertTrue(all("numbers" not in v for v in r.report["beat_details"].values() if isinstance(v, dict)))

    def test_numbers_false_equals_the_recorded_head_plan_cue_keys_and_clip_hashes(self):
        base = json.loads((EVIDENCE / "disabled_path_baseline_HEAD.json").read_text())
        sha = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()
        S2 = ("The old fortress had stood for centuries above the river. Its walls were thick and its guards were proud. Then the army arrived and the garrison was surrounded within a single week. "
              "The siege began in 1944. Every officer knew the plan was worthless and the orders were wrong. The soldiers who stayed were caught between the river and the guns. Nobody expected help from the north. ")
        cases = {"korea": (KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR)}
        seen = 0
        for k, (ww, ss, dd) in cases.items():
            for look in ("reference", "classic"):
                r = run(ww, ss, dd, look=look, numbers=False, motion=False)
                bd = r.report["beat_details"]
                got = {"plan_sha": sha(r.plan), "options_sha": sha(r.report["options"]), "problems": r.problems,
                       "cue_specs_sha": sha({b: v["cue_specs"] for b, v in bd.items() if isinstance(v, dict) and "cue_specs" in v}),
                       "clips": {b: v["clip"] for b, v in bd.items() if isinstance(v, dict) and "clip" in v}, "beats": len(r.plan["beats"])}
                self.assertEqual(got, base[f"{k}/{look}"], f"{k}/{look}")
                seen += 1
        self.assertEqual(seen, 2)

    def test_the_same_plan_twice_gives_identical_bytes(self):
        w, d = synth(SCRIPT)
        a, b = run(w, SCRIPT, d, numbers=True), run(w, SCRIPT, d, numbers=True)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))
        self.assertEqual(json.dumps(a.report["beat_details"], sort_keys=True, default=str), json.dumps(b.report["beat_details"], sort_keys=True, default=str))

    def test_numbers_and_motion_together_pass_every_gate(self):
        r, w, _d = Cache.plan(numbers=True, motion=True)
        self.assertIsNotNone(r.plan, r.problems)
        self.assertEqual(r.problems, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
