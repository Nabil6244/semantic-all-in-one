"""Stickman Phase 2: director (script -> beats) and the checker's repairs. No network."""
import copy
import re
import unittest
from pathlib import Path

from stickman import checker, director, make, timeline

TEXT = (Path(__file__).parent / "stickman" / "demos" / "tired.txt").read_text()
TITLE, BODY = make.split_title(TEXT)


def fake_words(text, step=0.33, pause=0.35):
    """Word times like the Edge voice gives: no punctuation, a pause after sentence ends."""
    t, out = 0.2, []
    for tok in text.split():
        w = re.sub(r"[^\w']", "", tok)
        out.append({"word": w, "start": round(t, 3), "end": round(t + step * 0.85, 3)})
        t += step + (pause if tok[-1] in ".?!" else 0.12 if tok[-1] in ",:" else 0)
    return out, t + 0.3


class DirectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.words, cls.dur = fake_words(BODY)
        cls.spec = director.direct(BODY, cls.words, cls.dur, title=TITLE, size=(1280, 720))

    def test_title_split(self):
        self.assertEqual(TITLE, "Why You're Always Tired")
        self.assertTrue(BODY.startswith("You wake up tired."))

    def test_captions_are_short_single_lines(self):
        for b in self.spec["beats"]:
            line = b["caption"].replace("*", "")
            self.assertLessEqual(len(line), director.MAX_CHARS + 8, line)
            self.assertLessEqual(len(line.split()), director.MAX_WORDS * 2)
            self.assertLessEqual(b["caption"].count("*"), 2)

    def test_every_word_spoken_once_in_order(self):
        said = [w["w"] for b in self.spec["beats"] for w in b["words"]]
        self.assertEqual(said, BODY.split())
        times = [w["t"] for b in self.spec["beats"] for w in b["words"]]
        self.assertEqual(times, sorted(times))

    def test_plan_is_valid_and_close_to_voice(self):
        total = timeline.validate(self.spec)
        self.assertGreater(total, self.dur - 0.01)
        self.assertLess(total, self.dur + 1.5)

    def test_hook_runs_in(self):
        self.assertEqual(self.spec["beats"][0]["acts"]["lead"]["do"], "run")
        self.assertEqual(self.spec["title"]["text"], TITLE)

    def test_friend_walks_in_when_mentioned(self):
        first = next(i for i, b in enumerate(self.spec["beats"]) if "other" in (b.get("acts") or {}))
        self.assertIn("friend", " ".join(w["w"].lower() for w in self.spec["beats"][first]["words"]))
        self.assertEqual(self.spec["beats"][first]["acts"]["other"]["do"], "walk")

    def test_uses_many_actions(self):
        used = {b["action"] for b in self.spec["beats"]}
        self.assertGreaterEqual(len(used), 7, used)

    def test_sfx_spaced(self):
        ts = [e["t"] for e in self.spec["audio"]["sfx"][1:]]
        self.assertTrue(all(b - a >= director.SFX_GAP - 1e-6 for a, b in zip(ts, ts[1:])))

    def test_checker_leaves_nothing(self):
        fixed, notes, left = checker.repair(self.spec)
        self.assertEqual(left, [], notes)


class CheckerTests(unittest.TestCase):
    def setUp(self):
        words, dur = fake_words(BODY)
        self.spec = director.direct(BODY, words, dur, title=TITLE, size=(1280, 720))

    def test_long_beat_is_split(self):
        s = copy.deepcopy(self.spec)
        a, b = s["beats"][3], s["beats"][4]
        a["dur"] = round(a["dur"] + b["dur"], 3)
        a["words"] += b["words"]
        a["caption"] += " " + b["caption"]
        del s["beats"][4]
        if a["dur"] <= timeline.MAX_HOLD:
            a["dur"] = timeline.MAX_HOLD + 0.6
            s["beats"][4]["t"] = round(a["t"] + a["dur"], 3)
            for x, y in zip(s["beats"][4:], s["beats"][5:]):
                y["t"] = round(x["t"] + x["dur"], 3)
            s["duration"] = round(s["beats"][-1]["t"] + s["beats"][-1]["dur"], 3)
        self.assertTrue(any(p.startswith("hold") for p in checker.check(s)))
        fixed, notes, left = checker.repair(s)
        self.assertFalse(any(p.startswith("hold") for p in left))
        timeline.validate(fixed)

    def test_repeated_pose_is_varied(self):
        s = copy.deepcopy(self.spec)
        for b in s["beats"][2:5]:
            b["acts"] = {"lead": {"do": "think"}}
        self.assertTrue(any(p.startswith("variety") for p in checker.check(s)))
        fixed, notes, left = checker.repair(s)
        self.assertFalse(any(p.startswith("variety") for p in left))

    def test_missing_hook_fixed(self):
        s = copy.deepcopy(self.spec)
        s["beats"][0]["acts"] = {"lead": {"do": "stand"}}
        s["figures"]["lead"]["x"] = 0.36
        fixed, notes, left = checker.repair(s)
        self.assertIn(fixed["beats"][0]["acts"]["lead"]["do"], ("jump", "run", "walk"))

    def test_same_camera_three_times_fixed(self):
        s = copy.deepcopy(self.spec)
        for b in s["beats"][1:4]:
            b["camera"] = {"zoom": 1.18, "x": 0.4, "kind": "close"}
        fixed, notes, left = checker.repair(s)
        self.assertFalse(any(p.startswith("camera") for p in left))


if __name__ == "__main__":
    unittest.main()
