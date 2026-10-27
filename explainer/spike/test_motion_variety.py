"""Phase E tests: scene variety (no picture-layout family three times in a row; a lamp-lit dossier backdrop for beats about secrets). Opt-in (DirectorOptions.variety), offline, deterministic.
usage: python3 -B explainer/spike/test_motion_variety.py   (from the repository root)"""
import hashlib
import itertools
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True

import numpy as np                                                              # noqa: E402
from m4_topics import TOPICS                                                    # noqa: E402
from test_director_real_material import synth, run, SCRIPT as KOREA_SCRIPT, WORDS as KOREA_WORDS, DUR as KOREA_DUR      # noqa: E402
from explainer.board import backdrops as BD                                     # noqa: E402
from explainer.board import layout as LY                                        # noqa: E402
from explainer.director import DirectorOptions, direct                          # noqa: E402
from explainer.director import compose_variety as CV                            # noqa: E402

EVIDENCE = ROOT / "docs" / "explainer" / "phase_motion_evidence"
LONG = " ".join(TOPICS.values()) * 2
SECRET = ("The old fortress had stood for centuries above the river. Its walls were thick and its guards were proud. Then the army arrived and the garrison was surrounded within a single week. "
          "The commander received a secret message from the capital. Nobody inside the walls knew who had written it. The soldiers waited and watched the road. "
          "A second secret letter arrived the next morning. The generals argued about the plan for hours. The winter came early and the river froze. "
          "The spy had been inside the walls all along. Every officer suspected the others. In the spring the siege ended quietly.")


class Cache:
    _r = {}

    @classmethod
    def get(cls, script, **kw):
        k = (script, tuple(sorted(kw.items())))
        if k not in cls._r:
            w, d = synth(script)
            cls._r[k] = (direct(w, script, DirectorOptions(look="reference", **kw), duration=d, materialize=False), w, d)
        return cls._r[k]


def sigs(rep):
    return [(b, tuple(sorted({p["as"] for p in v["phrases"]}))) for b, v in rep["beat_details"].items() if isinstance(v, dict) and "cue_specs" in v]


def longest(seq):
    return max(len(list(g)) for _k, g in itertools.groupby(s for _b, s in seq))


class Family(unittest.TestCase):
    def test_without_the_switch_a_family_can_repeat_three_times_and_with_it_never(self):
        off, _w, _d = Cache.get(LONG)
        on, _w2, _d2 = Cache.get(LONG, variety=True)
        self.assertGreaterEqual(longest(sigs(off.report)), 3)                       # the control: the problem exists without the rule
        self.assertLessEqual(longest(sigs(on.report)), CV.MAX_SAME_FAMILY)
        self.assertEqual(on.problems, [])
        self.assertEqual(on.report["hybrid_validate"].get("errors"), [])

    def test_a_reauthored_beat_keeps_its_sentences_and_says_why(self):
        on, w, _d = Cache.get(LONG, variety=True)
        off, _w, _d2 = Cache.get(LONG)
        changed = [(b, v["variety"]["family"]) for b, v in on.report["beat_details"].items() if isinstance(v, dict) and v.get("variety", {}).get("family")]
        self.assertTrue(changed)
        for b, fam in changed:
            self.assertEqual(on.report["beat_details"][b]["labels"], off.report["beat_details"][b]["labels"])        # the same sentences
            self.assertNotEqual(fam["was"], fam["now"])
            self.assertIn("same family", fam["why"])
            self.assertEqual(on.report["beat_details"][b]["problems"], [])

    def test_beats_that_did_not_need_the_rule_are_identical_to_the_switch_off_plan(self):
        on, _w, _d = Cache.get(LONG, variety=True)
        off, _w2, _d2 = Cache.get(LONG)
        changed = {b for b, v in on.report["beat_details"].items() if isinstance(v, dict) and v.get("variety", {}).get("family")}
        for b, v in off.report["beat_details"].items():
            if isinstance(v, dict) and "cue_specs" in v and b not in changed:
                self.assertEqual(on.report["beat_details"][b]["cue_specs"], v["cue_specs"], b)


class Dossier(unittest.TestCase):
    def test_a_beat_that_says_secret_gets_the_dossier_backdrop_but_never_the_first_board_beat_or_two_in_three(self):
        on, w, _d = Cache.get(SECRET, variety=True)
        off, _w, _d2 = Cache.get(SECRET)
        self.assertEqual(on.problems, [])
        vs = [(b, v["variety"]) for b, v in on.report["beat_details"].items() if isinstance(v, dict) and v.get("variety")]
        dos = [b for b, v in vs if v.get("dossier")]
        self.assertTrue(dos, vs)
        order = [b for b, _v in vs]
        self.assertNotEqual(order[0] if order else None, dos[0] if dos and dos[0] == order[0] else None)       # not the first board beat
        flags = [bool(v.get("dossier")) for _b, v in vs]
        for i in range(len(flags) - 2):
            self.assertLessEqual(sum(flags[i:i + 3]), 1, flags)
        for b in dos:                                                                  # only the clip name changes: the cues are the same as with the switch off
            self.assertNotEqual(on.report["beat_details"][b]["clip"], off.report["beat_details"][b]["clip"])
            self.assertEqual(on.report["beat_details"][b]["cue_specs"], off.report["beat_details"][b]["cue_specs"])
        said = {b: [x[0] for x in w if next(bb for bb in on.plan["beats"] if bb["id"] == b)["start"] - 1e-6 <= x[1] < next(bb for bb in on.plan["beats"] if bb["id"] == b)["end"] - 1e-6] for b in dos}
        for b in dos:
            self.assertTrue(set(said[b]) & CV.DARK, said[b])                           # the beat's own narration says it

    def test_a_skipped_dossier_says_why(self):
        on, _w, _d = Cache.get(SECRET, variety=True)
        why = [v["variety"]["dossier_skipped"] for v in on.report["beat_details"].values() if isinstance(v, dict) and v.get("variety", {}).get("dossier_skipped")]
        self.assertTrue(why)

    def test_the_dossier_paper_keeps_the_ink_readable_in_the_content_area(self):
        im = np.asarray(BD.image(BD.DOSSIER, (1920, 1080))).astype(float)
        x0, y0, x1, y1 = 720, 110, 1824, 890
        reg = im[y0:y1, x0:x1]
        lum = lambda c: (0.2126 * ((c[..., 0] / 255) ** 2.2) + 0.7152 * ((c[..., 1] / 255) ** 2.2) + 0.0722 * ((c[..., 2] / 255) ** 2.2))
        ink = np.array([50.0, 50.0, 56.0])
        l_ink = lum(ink[None, None, :])[0, 0]
        ratio = (lum(reg) + 0.05) / (l_ink + 0.05)
        self.assertGreaterEqual(float(np.percentile(ratio, 1)), 4.5, "ink on the dossier paper must keep a 4.5:1 contrast across the content area")
        grey = np.asarray(BD.image("paper", (1920, 1080))).astype(float)
        self.assertLess(im.mean(), grey.mean() - 25)                                    # it is visibly darker than the plain paper overall
        self.assertEqual(BD.image(BD.DOSSIER, (1920, 1080)).tobytes(), BD.image(BD.DOSSIER, (1920, 1080)).tobytes())

    def test_the_dossier_is_not_a_user_choice_and_unknown_names_still_fail(self):
        self.assertNotIn(BD.DOSSIER, BD.STYLES)
        with self.assertRaises(ValueError):
            BD.image("nonsense", (64, 64))
        r = run(*synth("The army waited by the river.")[:1], "The army waited by the river.", 6.0, background="dossier")
        self.assertTrue(any("unknown background" in p for p in r.problems))


class OffByDefault(unittest.TestCase):
    def test_variety_is_off_by_default_and_the_disabled_plan_equals_recorded_head(self):
        self.assertIs(DirectorOptions().variety, False)
        base = json.loads((EVIDENCE / "disabled_path_baseline_HEAD.json").read_text())
        sha = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()
        for look in ("reference", "classic"):
            r = run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, look=look, variety=False)
            self.assertNotIn("variety", r.report["options"])
            bd = r.report["beat_details"]
            got = {"plan_sha": sha(r.plan), "options_sha": sha(r.report["options"]),
                   "cue_specs_sha": sha({b: v["cue_specs"] for b, v in bd.items() if isinstance(v, dict) and "cue_specs" in v}),
                   "clips": {b: v["clip"] for b, v in bd.items() if isinstance(v, dict) and "clip" in v}}
            want = base[f"korea/{look}"]
            self.assertEqual({k: want[k] for k in got}, got, look)

    def test_the_classic_look_ignores_the_switch(self):
        a = run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, look="classic", variety=True)
        b = run(KOREA_WORDS, KOREA_SCRIPT, KOREA_DUR, look="classic", variety=False)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))

    def test_the_same_plan_twice_is_identical(self):
        w, d = synth(SECRET)
        a = direct(w, SECRET, DirectorOptions(look="reference", variety=True), duration=d, materialize=False)
        b = direct(w, SECRET, DirectorOptions(look="reference", variety=True), duration=d, materialize=False)
        self.assertEqual(json.dumps(a.plan, sort_keys=True), json.dumps(b.plan, sort_keys=True))
        self.assertEqual(json.dumps(a.report["beat_details"], sort_keys=True, default=str), json.dumps(b.report["beat_details"], sort_keys=True, default=str))


if __name__ == "__main__":
    unittest.main(verbosity=2)
