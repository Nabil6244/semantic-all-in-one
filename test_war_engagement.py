"""War Documentary engagement check (war/engagement.py): finds where a plan would sag, fixes slow stretches of fitting footage, no render."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from cinematic_explainer.render import Layer, Shot
from cinematic_explainer.war import engagement as E


class P:
    def __init__(self, shots=(), layers=()):
        self.shots, self.layers = list(shots), list(layers)


def rows(n, d, text="Fighting went on through the night.", clip=None, meta=None):
    return [{"_start": i * d, "_end": (i + 1) * d, "_no": i + 1, "text": text, "footage": clip, "footage_meta": dict(meta or {})} for i in range(n)]


class EngagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clip = str(Path(cls.tmp.name, "c.mp4"))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:d=30", "-r", "25", cls.clip], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_lively_plan_passes(self):
        sh = [Shot(self.clip, i * 3.0, (i + 1) * 3.0, 0.0) for i in range(20)]
        r = rows(10, 6.0, "So why did it matter? Then the answer came.")
        rep = E.check(P(sh), r)
        self.assertEqual(rep["issues"], [])
        self.assertEqual(rep["score"], 100)

    def test_finds_slow_still_same_and_no_turns(self):
        sh = [Shot(self.clip, i * 12.0, (i + 1) * 12.0, 0.0) for i in range(15)]          # 12 s shots for 3 minutes
        ly = [Layer("tac_map", 30.0, 62.0, {}, dim=False)]                                 # 32 s of one map
        rep = E.check(P(sh, ly), rows(30, 6.0))
        kinds = {x["kind"] for x in rep["issues"]}
        self.assertTrue({"slow", "same", "still", "turn"} <= kinds)
        self.assertLess(rep["score"], 70)
        self.assertIn("Where it may sag", E.text(rep))

    def test_fix_recuts_only_fitting_footage(self):
        sh = [Shot(self.clip, i * 12.0, (i + 1) * 12.0, 0.0) for i in range(15)]
        p = P(list(sh))
        rep = E.check(p, rows(30, 6.0, clip=self.clip))
        self.assertEqual(E.fix(p, rows(30, 6.0, clip=self.clip), rep), 0)                # no match data: untouched
        n = E.fix(p, rows(30, 6.0, clip=self.clip, meta={"csv_pick": True}), rep)
        self.assertGreater(n, 0)
        self.assertLessEqual(max(s.end - s.start for s in p.shots), 4.5)
        self.assertAlmostEqual(sum(s.end - s.start for s in p.shots), 180.0, places=2)

    def test_animated_card_may_hold_ten_seconds(self):
        sh = [Shot(self.clip, 0.0, 3.0, 0.0), Shot(self.clip, 12.0, 15.0, 0.0)]
        rep = E.check(P(sh, [Layer("kit_chart", 3.0, 12.0, {}, dim=False)]), rows(3, 5.0, "So why? Then this."))
        self.assertFalse([x for x in rep["issues"] if x["kind"] == "still"])


if __name__ == "__main__":
    unittest.main()
